# Cert-Expiry Canary — Design

**Issue:** [frank#251](https://github.com/derio-net/frank/issues/251) (option 1 — permanent canary path)
**Parent plan:** `docs/superpowers/implemented/plans/2026-05-11--obs--cert-expiry-alerting/` (Deployed, with documented verification gap)
**Layer:** obs (extension — Layer 08, tracker `frank-ops#8`)
**Date:** 2026-06-07

## Problem

The `tls-cert-expiring-14d` / `tls-cert-expiring-7d` rules are deployed but have
never fired on real metric data: the default `http_2xx` blackbox module aborts
the TLS handshake against expired certs before cert inspection, so
`probe_ssl_earliest_cert_expiry` is never emitted and `noDataState: OK` keeps
the rules inactive. Phase 3 of the parent plan verified rule machinery and the
Telegram credential path, but not a rule-driven fire.

**Empirical prerequisite (confirmed in parent plan deviations):** on
`prom/blackbox-exporter:v0.25.0`, a module with
`tls_config.insecure_skip_verify: true` DOES emit
`probe_ssl_earliest_cert_expiry` for `https://expired.badssl.com/`
(value `1.428883199e9` = 2015-04-12, `probe_success=1`).

## Goal

A permanent canary that keeps both tls-cert rules perpetually exercised
(metric → eval → `for: 1h` → Firing), visible in the Grafana alert list as a
heartbeat, with **zero Telegram noise and zero health-bridge bug issues** —
plus a watchdog that notices when the heartbeat itself dies.

## Design

Four config changes, all in existing apps (no new ArgoCD Application):

### 1. Blackbox module — `apps/blackbox-exporter/manifests/configmap.yaml`

New module `http_2xx_insecure_tls`, identical in shape to `http_2xx_no_redirect`
plus `tls_config.insecure_skip_verify: true`:

```yaml
http_2xx_insecure_tls:
  prober: http
  timeout: 10s
  http:
    # See note above — keep in sync with facts.PROBE_UA_TOKEN.
    headers:
      User-Agent: "Frank-Blackbox-Probe/1.0 (+https://blog.derio.net)"
    valid_status_codes: [200]
    follow_redirects: false
    preferred_ip_protocol: ip4
    tls_config:
      insecure_skip_verify: true
```

Keeps the `Frank-Blackbox-Probe` UA for consistency with the edge-filter
contract (irrelevant to badssl, but uniform across modules).

### 2. Canary VMProbe — `apps/blackbox-exporter/manifests/vmprobe.yaml`

Third VMProbe document in the existing file:

```yaml
apiVersion: operator.victoriametrics.com/v1beta1
kind: VMProbe
metadata:
  name: expired-cert-canary
  namespace: monitoring
spec:
  targets:
    staticConfig:
      targets:
        - https://expired.badssl.com/
      labels:
        probe_group: cert_canary   # distinct group — keeps feature-health dashboards clean
        canary: "true"
  module: http_2xx_insecure_tls
  vmProberSpec:
    url: blackbox-exporter.monitoring.svc:9115
```

The expired cert (2015) is permanently below both the 14d and 7d thresholds, so
the canary produces **two perpetual alert instances**: one `severity=warning`
(14d rule) and one `severity=critical` (7d rule). Both carry `canary="true"`
(staticConfig labels flow into metric labels and then alert instance labels).

### 3. Notification policy — `apps/grafana-alerting/manifests/notification-policy-cm.yaml`

Two additions to the same provisioning file (`notification-policy.yaml` key —
one file may carry multiple provisioning sections):

**a. Always-active mute time interval** (Grafana has no null receiver; the
idiomatic permanent mute is a route bound to an always-active interval):

```yaml
muteTimes:
  - orgId: 1
    name: perma-mute
    time_intervals:
      - times:
          - start_time: "00:00"
            end_time: "24:00"
```

**b. Two new routes, prepended in this exact order** (before all existing
routes):

```yaml
routes:
  # 1. Canary watchdog — health-bridge ONLY. severity=critical is required
  #    for health-bridge's dead→bug-issue lifecycle, but must NOT reach the
  #    Telegram severity routes below — hence first position + continue:false.
  - receiver: "Health Bridge Webhook"
    matchers:
      - canary_watchdog="true"
    continue: false
  # 2. Canary heartbeat instances — permanently muted, but still visible in
  #    the Grafana alert list (that visibility IS the heartbeat). Catches
  #    BOTH the warning (14d) and critical (7d) instances before the
  #    severity routes and before the feature-health → health-bridge route
  #    (which would otherwise mint a never-closing bug issue).
  - receiver: "Telegram - Willikins"   # explicit for readability — never delivers (perma-muted)
    matchers:
      - canary="true"
    mute_time_intervals:
      - perma-mute
    continue: false
  # ... existing routes unchanged ...
```

**Route-order analysis** (why this exact order):

| Alert | Labels | First matching route | Outcome |
|---|---|---|---|
| canary 14d instance | `canary=true, severity=warning` | route 2 (mute) | suppressed, visible in alert list |
| canary 7d instance | `canary=true, severity=critical` | route 2 (mute) | suppressed, visible in alert list |
| watchdog | `canary=true, canary_watchdog=true, severity=critical, github_issue=frank-ops#8` | route 1 (health-bridge) | bug issue on fire, auto-close on heal, NO Telegram |
| all existing alerts | unchanged | existing routes | unchanged |

⚠️ The watchdog alert ALSO carries `canary="true"` — `absent()` propagates the
equality matchers of its selector into the result vector's labels. If the mute
route came first, it would swallow the watchdog. Watchdog route MUST precede
the mute route.

### 4. Watchdog rule — `apps/grafana-alerting/manifests/alert-rules-cm.yaml`

New rule in the existing `tls-cert-expiry-1h` group (same 1h interval):

```yaml
- uid: tls-cert-canary-absent
  title: TLS cert-expiry canary absent
  condition: C
  data:
    - refId: A
      relativeTimeRange: { from: 3600, to: 0 }
      datasourceUid: P4169E866C3094E38
      model:
        refId: A
        expr: 'absent(probe_ssl_earliest_cert_expiry{canary="true"})'
        instant: true
        intervalMs: 1000
        maxDataPoints: 43200
    - refId: B   # reduce, last, dropNN (3-step A→B→C per Grafana 12 SSE gotcha)
    - refId: C   # threshold > 0
  noDataState: OK      # absent() returns EMPTY when the metric exists → noData = healthy
  execErrState: Error
  for: 3h              # generous — tolerates transient badssl.com outages
  labels:
    severity: critical            # health-bridge: dead → bug issue (auto-closed on heal)
    github_issue: "frank-ops#8"   # Layer 08 — Observability tracker
    canary_watchdog: "true"       # routes to Health Bridge ONLY (first-position route)
  annotations:
    summary: "Cert-expiry canary heartbeat lost: probe_ssl_earliest_cert_expiry{canary=\"true\"} absent >3h"
    runbook: "Check https://expired.badssl.com/ reachability, blackbox-exporter http_2xx_insecure_tls module, and VMProbe expired-cert-canary. See docs/superpowers/specs/2026-06-07--obs--cert-expiry-canary-design.md"
```

`absent()` semantics: returns a 1-element vector when the metric is missing
(→ threshold C fires), an EMPTY result when present (→ noData → `OK`). The
inversion means `noDataState: OK` is the *healthy* path here, unlike the
cert rules where it papers over a missing metric.

### health-bridge contract (verified against `bridge.go`)

- Alerts **without** a `github_issue` label are skipped entirely — the existing
  tls-cert rules have none, so even if the mute route failed, health-bridge
  would no-op on the canary instances. Defense in depth, not a reason to skip
  the mute (Telegram would still fire).
- `firing` + `severity=critical` → state `dead` → **creates a bug issue**
  (deduped per alertname + feature ref).
- `resolved` → auto-closes that bug with outage duration (v0.3.1, deployed
  2026-06-06).
- `frank-ops#8` ("Layer 08 — Observability") exists and follows the
  per-layer-tracker convention used by all other `github_issue` labels.

## Q&A decisions (2026-06-07)

1. **Mute mechanism:** first-position `canary="true"` route + provisioned
   always-active mute time interval, `continue: false`. No blackhole contact
   point; health-bridge never sees the canary.
2. **Watchdog:** yes — routed to health-bridge only (bug issue on death,
   auto-close on heal), generous `for: 3h`, zero Telegram.
   *Refinement vs the Q&A option text:* achieving the promised bug-issue
   lifecycle requires `severity: critical` (health-bridge only creates bugs on
   `dead`), so Telegram suppression comes from the dedicated first-position
   route rather than from omitting the severity label.
3. **Test Plan:** interactive, agent-driven post-merge (below).

## Deployment notes

- **Grafana** mounts each provisioning file via `subPath` (kubelet never
  live-updates) and reads provisioning at boot only →
  `kubectl rollout restart deployment` of the Grafana pod after sync.
- **blackbox-exporter** has no config-reloader sidecar; the CM volume is
  non-subPath (kubelet propagates in ~1min) but blackbox only loads config at
  startup/SIGHUP → `kubectl rollout restart deployment/blackbox-exporter -n monitoring`
  (or `POST /-/reload`).
- ArgoCD picks up both apps from `main` after merge; restarts are post-sync
  imperative steps (Test Plan), not manifest changes.
- No new secrets, no new Application, no ingress, no homepage tile.

## Acceptance (from issue #251, option 1, + watchdog)

- [ ] `http_2xx_insecure_tls` module added; ArgoCD synced.
- [ ] `expired-cert-canary` VMProbe picked up by vmagent;
      `probe_ssl_earliest_cert_expiry{canary="true"}` ≈ `1.428883199e9`,
      `probe_success == 1`.
- [ ] Both tls-cert alert instances for the canary reach `Pending` then
      `Firing` (rule interval 1h + `for: 1h` → ≤ ~2.5h wall clock).
- [ ] No Telegram message for the canary instances; no health-bridge comment
      or bug issue.
- [ ] Watchdog rule `health=ok`, state `Normal` while the canary metric flows.
- [ ] Closes the #251 verification gap: a Grafana rule fire driven by real
      metric data crossing the threshold, including the `for` debounce and
      notification-policy routing (delivery deliberately muted at the last
      hop, which is itself part of what's verified).

## Test Plan (post-merge — operator-driven, agent-assisted)

1. Merge PR; confirm ArgoCD syncs `blackbox-exporter` and `grafana-alerting`
   apps (`kubectl get application -n argocd -o wide`).
2. `kubectl rollout restart deployment/blackbox-exporter -n monitoring`; wait
   Ready.
3. Restart the Grafana pod (provisioning re-read); wait Ready.
4. Verify metric: query VictoriaMetrics for
   `probe_ssl_earliest_cert_expiry{canary="true"}` → ≈1.428883199e9;
   `probe_success{canary="true"}` → 1.
5. Verify provisioning landed: Grafana API — notification policy shows the two
   new first-position routes + `perma-mute` interval; rule
   `tls-cert-canary-absent` present, `health=ok`.
6. Watch `tls-cert-expiring-14d`/`-7d` canary instances: `Pending` within ~1h,
   `Firing` within ~2.5h (`/api/prometheus/grafana/api/v1/rules`).
7. Confirm silence: no Telegram message for the canary; no new comment on
   `frank-ops#8`; no new bug issue in `frank-ops`.
8. Watchdog negative check: rule evaluates `Normal` (absent() empty while
   metric flows).
9. (Optional, destructive, ≥3h) Watchdog fire test: live-delete the canary
   VMProbe with root+leaf selfHeal suspended, wait `for: 3h` → bug issue on
   `frank-ops`; restore, confirm auto-close. Deferred by default — the
   absent() inversion is verified by step 8 and the rule shares its machinery
   with the proven tls-cert rules.

## Risks / trade-offs

- **External dependency on badssl.com** — accepted by issue design; the
  watchdog turns "badssl died" into a self-healing health-bridge bug issue
  rather than silence. `for: 3h` absorbs transient outages.
- **badssl cert renewal**: expired.badssl.com's cert is intentionally expired
  (fixed at 2015-04-12); if badssl ever rotates it to a *valid* cert, the
  canary instances resolve and only manual alert-list inspection notices (the
  watchdog only covers metric absence). Low likelihood; documented here.
- **Provisioning schema**: `muteTimes` + `mute_time_intervals` verified
  against current Grafana file-provisioning docs; final verification is
  Test Plan step 5 (12.x renamed the UI concept to "time intervals" but the
  file-provisioning keys are unchanged).

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| 2026-06-07-cert-expiry-canary | `derio-net/frank` | `2026-06-07-cert-expiry-canary` | — |

## Out of scope

- Issue option 2 (time-bounded real-fire test with a self-hosted ~13-day
  cert) — the canary closes the watchdog gap; option 2 remains available
  later on the same `http_2xx_insecure_tls` module.
- Blog posts / README (fix-extension of obs layer — parent-plan precedent);
  a gotcha one-liner lands if implementation surfaces a new non-obvious
  pattern.
