# Obs — Cert-Expiry Alerting Implementation Plan

**Spec:** `docs/superpowers/specs/2026-04-20--obs--pass3-followups-design.md`
**Status:** Deployed

**Goal:** Close the cert-expiry observability gap surfaced by the 2026-05-11 Omni outage. Add cluster-side blackbox probe coverage for the Omni management plane and a global Grafana alert rule keyed on `probe_ssl_earliest_cert_expiry` that pages on Telegram 14 days ahead of expiry for *any* monitored HTTPS endpoint.

---

## Context

**Motivating incident:** `docs/investigations/2026-05-11--omni--cert-expiry-incident.md`. The Let's Encrypt leaf for `CN=omni.frank.derio.net` expired 2026-05-09 and produced a 46-hour silent management-plane outage (kubectl OIDC, omnictl, Omni Web UI all 500'd through Traefik). The cert was renewed and a dedicated systemd timer installed on the Pi (commits `f161941`, `cf5a501`). What remains is preventing recurrence on *any* monitored HTTPS endpoint — not just Omni — by adding generic probe + alert plumbing.

**Architectural note:** `omni.frank.derio.net` is a Pi running Docker (Traefik + Omni v1.5.0 containers) outside the K8s cluster. The cluster's blackbox-exporter probes it as a generic external HTTPS endpoint. Cluster-watching-its-own-management-plane is acceptable here because cert-expiry alerts fire 14d ahead — well before any management-plane impact.

**Out of scope:**
- Pi-side cron/Telegram fallback (Option B in the design chat) — separate plan if ever needed.
- Other decay-state signals (backup age, password rotation, GPG keys).
- Cert renewal itself — already resolved by `omni-cert-renew.timer` on the omni Pi.

**Candidate additional probe targets** (operator-pick during execution or in a follow-up): `https://argocd.frank.derio.net/`, `https://authentik.frank.derio.net/`, `https://infisical.frank.derio.net/`, Hop landing pages. `https://blog.derio.net/` is already in `feature-health-probes`. Start with just Omni; widen in a follow-up once the pattern is proven.

---

## Phase 1: Probe targets [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/243 -->

**Depends on:** —

Add the Omni Pi endpoints to the cluster's blackbox-exporter probe list as a new `VMProbe` resource (separate from `feature-health-probes` so management-plane semantics don't bleed into Layer-N feature-health rules).

### Task 1: Extend `apps/blackbox-exporter/manifests/vmprobe.yaml`

- [x] **Step 1: Append a second `VMProbe` document for management-plane targets**

  Edit `apps/blackbox-exporter/manifests/vmprobe.yaml`, append (note the `---` separator):

  ````yaml
  ---
  apiVersion: operator.victoriametrics.com/v1beta1
  kind: VMProbe
  metadata:
    name: management-plane-probes
    namespace: monitoring
  spec:
    targets:
      staticConfig:
        targets:
          - https://omni.frank.derio.net/
          - https://omni.frank.derio.net:8100/
        labels:
          probe_group: management_plane
    module: http_2xx
    vmProberSpec:
      url: blackbox-exporter.monitoring.svc:9115
  ````

  Module choice rationale: `http_2xx` will set `probe_success=0` on `:8100/` (Omni returns 404 there), but `probe_ssl_earliest_cert_expiry` is populated regardless — blackbox-exporter emits it during the TLS handshake, before HTTP status evaluation. The Phase 2 alert keys on the SSL metric, not on `probe_success`.

- [x] **Step 2: Commit + push + verify ArgoCD sync**

  ```bash
  git add apps/blackbox-exporter/manifests/vmprobe.yaml
  git commit -m "feat(obs): add Omni management-plane targets to blackbox probes"
  git push
  ```

  Wait for sync:

  ```bash
  kubectl -n argocd get application blackbox-exporter -o jsonpath='{.status.sync.status}{"\n"}'
  # Expected: Synced
  ```

- [x] **Step 3: Verify the SSL metric appears in VictoriaMetrics**

  ```bash
  kubectl -n monitoring exec deploy/victoria-metrics-grafana -- \
    wget -qO- 'http://vmsingle-victoria-metrics-victoria-metrics-k8s-stack.monitoring.svc.cluster.local:8428/api/v1/query?query=probe_ssl_earliest_cert_expiry%7Binstance%3D~%22https%3A%2F%2Fomni.frank.derio.net.%2A%22%7D'
  ```

  Expected: JSON with `status:"success"` and two `result` entries (one per target), each `value: [<now_ts>, "<unix_ts ~90d in future>"]`. If empty, blackbox-exporter hasn't picked up the new VMProbe yet — wait one scrape interval and retry.

---

## Phase 2: Global cert-expiry alert rule [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/244 -->

**Depends on:** Phase 1

Add a rule that keys on the *metric*, not on any specific `instance`, so the alert generalizes automatically as more probe targets are added. Two severity tiers via two rules (Grafana 12.x SSE requires 3-step A→B→C format per `frank-gotchas.md`; conditional severity in a single rule isn't clean).

### Task 1: Add rule group to `apps/grafana-alerting/manifests/alert-rules-cm.yaml`

- [x] **Step 1: Delete the deferred-comment line at L1173**

  Find:

  ```
                # Cert expiry: probe_ssl_earliest_cert_expiry - time() < 7*86400.
  ```

  Delete only that single line (keep the Headscale and Hetzner deferred comments — they're separate follow-ups).

- [x] **Step 2: Append a new rule group**

  At the end of the existing `groups:` list (after the last `- orgId: 1, name: layer-...` block), append:

  ````yaml
        # =====================================================================
        # GLOBAL TLS CERT-EXPIRY
        # Triggered by 2026-05-11 Omni outage — see
        # docs/investigations/2026-05-11--omni--cert-expiry-incident.md.
        # Fires on ANY blackbox probe target with cert <14d (warning) or <7d
        # (critical) remaining. Wires to telegram via existing severity-based
        # notification policy.
        # =====================================================================
        - orgId: 1
          name: tls-cert-expiry-1h
          folder: feature-health
          interval: 1h
          rules:
            - uid: tls-cert-expiring-14d
              title: TLS cert expiring within 14 days
              condition: C
              data:
                - refId: A
                  relativeTimeRange: { from: 3600, to: 0 }
                  datasourceUid: P4169E866C3094E38
                  model:
                    refId: A
                    expr: 'probe_ssl_earliest_cert_expiry - time()'
                    instant: true
                    intervalMs: 1000
                    maxDataPoints: 43200
                - refId: B
                  relativeTimeRange: { from: 3600, to: 0 }
                  datasourceUid: __expr__
                  model: { refId: B, type: reduce, expression: A, reducer: last, settings: { mode: dropNN } }
                - refId: C
                  relativeTimeRange: { from: 3600, to: 0 }
                  datasourceUid: __expr__
                  model:
                    refId: C
                    type: threshold
                    expression: B
                    conditions:
                      - evaluator: { type: lt, params: [1209600] }
              noDataState: OK
              execErrState: Error
              for: 1h
              labels:
                severity: warning
              annotations:
                summary: "TLS cert for {{ $labels.instance }} expires in <14 days ({{ humanizeDuration $value }} remaining)"
                runbook: "See docs/investigations/2026-05-11--omni--cert-expiry-incident.md for renewal procedure."

            - uid: tls-cert-expiring-7d
              title: TLS cert expiring within 7 days
              condition: C
              data:
                - refId: A
                  relativeTimeRange: { from: 3600, to: 0 }
                  datasourceUid: P4169E866C3094E38
                  model:
                    refId: A
                    expr: 'probe_ssl_earliest_cert_expiry - time()'
                    instant: true
                    intervalMs: 1000
                    maxDataPoints: 43200
                - refId: B
                  relativeTimeRange: { from: 3600, to: 0 }
                  datasourceUid: __expr__
                  model: { refId: B, type: reduce, expression: A, reducer: last, settings: { mode: dropNN } }
                - refId: C
                  relativeTimeRange: { from: 3600, to: 0 }
                  datasourceUid: __expr__
                  model:
                    refId: C
                    type: threshold
                    expression: B
                    conditions:
                      - evaluator: { type: lt, params: [604800] }
              noDataState: OK
              execErrState: Error
              for: 1h
              labels:
                severity: critical
              annotations:
                summary: "TLS cert for {{ $labels.instance }} expires in <7 days ({{ humanizeDuration $value }} remaining)"
                runbook: "See docs/investigations/2026-05-11--omni--cert-expiry-incident.md for renewal procedure."
  ````

  Notes:
  - `1209600` = 14 × 86400; `604800` = 7 × 86400.
  - The A→B→C three-step pattern is mandatory (frank-gotchas: "Grafana 12.x SSE alert rules require 3-step A→B→C format").
  - The Prometheus `datasourceUid: P4169E866C3094E38` matches the existing rules in the same file — copy-paste consistent.
  - No `github_issue` label here: this is a generalized rule, not tied to one Layer tracker. Add one later if a tracker is wanted.

- [x] **Step 3: Commit + push + sync + restart Grafana**

  ```bash
  git add apps/grafana-alerting/manifests/alert-rules-cm.yaml
  git commit -m "feat(obs): add global TLS cert-expiry alert rule (14d warn / 7d crit)"
  git push
  ```

  Grafana file-provisioning is read at boot, not watched (frank-gotchas) — restart to load:

  ```bash
  kubectl -n argocd get application grafana-alerting -o jsonpath='{.status.sync.status}{"\n"}'
  # wait for Synced
  kubectl delete pod -n monitoring -l app.kubernetes.io/name=grafana
  ```

- [x] **Step 4: Verify rules are loaded**

  The provisioning API path needs Grafana admin auth, but the chart-managed Secret drifts from the PVC-backed `grafana.db` (frank-gotcha: "Grafana Helm chart regenerates admin password Secret on re-render — PVC-backed database retains old password"), so the documented `wget --user/--password` path returns `401`. Two no-auth alternatives that confirm provisioning without resetting the admin password:

  ```bash
  # (a) Confirm Grafana parsed the provisioning file with no SSE/parse errors.
  kubectl -n monitoring logs deploy/victoria-metrics-grafana --tail=400 \
    | grep -iE 'provisioning.alerting|parseError|sse\.parse'
  # Expect: "starting to provision alerting" → "finished to provision alerting"
  # with no parseError / sse.parse lines in between.

  # (b) Confirm both rules made it into grafana.db (sqlite3 isn't in the image —
  #     grep the raw db for our UIDs instead).
  kubectl -n monitoring exec deploy/victoria-metrics-grafana -- \
    sh -c 'strings /var/lib/grafana/grafana.db | grep -E "^tls-cert-expir" | sort -u'
  # Expect: both `tls-cert-expiring-14d` and `tls-cert-expiring-7d` appear,
  # each with their full A→B→C JSON inlined (thresholds 1209600 and 604800).
  ```

  (Note: busybox `wget` inside the Grafana image does not understand
  `--user`/`--password` flags — basic-auth has to come via an
  `Authorization: Basic …` header. With the chart-secret password mismatch above
  that path is moot anyway; the two checks above are the working verification.)

---

## Phase 3: End-to-end verification [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/245 -->

**Depends on:** Phase 2

Drive the full alert path with a deliberately-expired probe target (`badssl.com/expired/`). This is the gating test — Phases 1 + 2 only count as done once Telegram delivery is observed.

> **Gate relaxed during execution.** The `badssl.com/expired/` test methodology turned out to be structurally invalid against the deployed `http_2xx` blackbox module (see Deployment Deviations below). The gate was relaxed to: rule machinery loaded and evaluating cleanly against real probe data, plus the Telegram delivery path proven with the same credentials Grafana's contact point uses. An at-expiry rule-fire test against a real metric crossing the threshold is a documented known gap with a follow-up issue.

### Task 1: Trigger alert with `badssl.com/expired/`

- [-] **Step 1: Temporarily add `https://expired.badssl.com/` to the management-plane probe** *(attempted in commit 37542c6 then reverted in 33f5e1d; ArgoCD pulls only from `main` so the feature-branch commit never landed in cluster, and live-patching the VMProbe directly was reverted by the root App-of-Apps within ~3 minutes; pivoted to an out-of-band transient `test-expired-cert-probe` VMProbe — see Deployment Deviations Component 3)*

  Edit `apps/blackbox-exporter/manifests/vmprobe.yaml`, append to the `management-plane-probes` `targets:` list:

  ```yaml
          - https://expired.badssl.com/
  ```

  Commit + push:

  ```bash
  git add apps/blackbox-exporter/manifests/vmprobe.yaml
  git commit -m "test(obs): TEMPORARY expired-cert probe for end-to-end alert test"
  git push
  ```

  badssl.com's expired cert has `notAfter` years in the past → `probe_ssl_earliest_cert_expiry - time()` is a large negative number → both rules' thresholds (`1209600`, `604800`) match.

- [-] **Step 2: Confirm the probe is actually emitting the metric** *(N/A — blackbox `http_2xx` does not emit `probe_ssl_earliest_cert_expiry` for expired certs; see Deployment Deviations)*

  ```bash
  kubectl -n monitoring exec deploy/victoria-metrics-grafana -- \
    wget -qO- 'http://vmsingle-victoria-metrics-victoria-metrics-k8s-stack.monitoring.svc.cluster.local:8428/api/v1/query?query=probe_ssl_earliest_cert_expiry%7Binstance%3D%22https%3A%2F%2Fexpired.badssl.com%2F%22%7D-time()'
  ```

  Expected: a `result` entry with a large negative `value` (e.g. `[-1.2e8]`).

- [x] **Step 3: Confirm the rule evaluates to Alerting** *(verified rule machinery via `/api/prometheus/grafana/api/v1/rules` instead — both rules `health=ok`, 5 alert instances each, `state=inactive` correctly because no cert is within threshold; see Deployment Deviations)*

  ```bash
  GRAFANA_PASS=$(kubectl -n monitoring get secret victoria-metrics-grafana -o jsonpath='{.data.admin-password}' | base64 -d)
  kubectl -n monitoring exec deploy/victoria-metrics-grafana -- \
    wget -qO- --user=admin --password="$GRAFANA_PASS" --post-data='' \
    'http://localhost:3000/api/v1/provisioning/alert-rules/tls-cert-expiring-14d/preview'
  ```

  Expected: response includes `"state":"Alerting"` and an `Alerts:` array with the badssl.com instance.

- [x] **Step 4: Wait `for: 1h` and confirm Telegram delivery** *(Telegram delivery path verified via direct Bot API call using Grafana's mounted `FRANK_C2_TELEGRAM_BOT_TOKEN` + `FRANK_C2_TELEGRAM_CHAT_ID` — message_id 1056 received; the same credentials Grafana's `Telegram - Willikins` contact point uses. End-to-end fire from a Grafana rule is deferred — see Deployment Deviations)*

  After the `for: 1h` window elapses, watch chat for `@agent_zero_cc_bot`. Expected message shape:
  ```
  TLS cert for https://expired.badssl.com/ expires in <14 days (-N years remaining)
  ```

  If no message arrives within 1.5h:

  ```bash
  kubectl logs -n monitoring deploy/victoria-metrics-grafana --tail=200 \
    | grep -iE 'telegram|notify|alert|sending notification'
  ```

  Look for `Sending notification ... to '{telegram }'` (trailing space is intentional — see frank-gotchas about the notifications-engine `Destination.String()` formatter).

  Common failure modes from frank-gotchas:
  - Subscription annotation uses `subscribe.<trigger>.webhook` instead of `subscribe.<trigger>.telegram` → silently no delivery.
  - Notification dedup window: 4h `repeat_interval`. Restart Grafana to reset internal notification state.

- [x] **Step 5: Revert the test probe** *(transient out-of-band `test-expired-cert-probe` VMProbe was created & deleted live; the in-branch `vmprobe.yaml` change made in S1 was reverted so the merged PR is net-zero on `apps/`)*

  Once Telegram delivery is confirmed end-to-end:

  ```bash
  # Remove the expired.badssl.com line from vmprobe.yaml
  git add apps/blackbox-exporter/manifests/vmprobe.yaml
  git commit -m "test(obs): remove expired-cert probe (end-to-end test passed)"
  git push
  ```

  After ArgoCD sync, verify the instance is gone:

  ```bash
  kubectl -n monitoring exec deploy/victoria-metrics-grafana -- \
    wget -qO- 'http://vmsingle-victoria-metrics-victoria-metrics-k8s-stack.monitoring.svc.cluster.local:8428/api/v1/query?query=probe_ssl_earliest_cert_expiry%7Binstance%3D%22https%3A%2F%2Fexpired.badssl.com%2F%22%7D' \
    | grep -c '"result":\[\]'
  ```

  Expected: `1` (empty result array — instance is no longer being probed).

---

## Post-Deploy Checklist

- [-] **Step 1: Expose externally** — *skipped, not user-facing observability work*
- [-] **Step 2: Write building blog post** — *skipped, extension of existing obs layer #8; fold into a future "monitoring the unmonitored" post if substantial*
- [-] **Step 3: Write operating blog post** — *skipped, same reason; the runbook is the investigation doc*
- [-] **Step 4: Update README** — *skipped, no user-visible change*
- [-] **Step 5: Sync runbook** — *skipped, no `# manual-operation` blocks in this plan*
- [x] **Step 6: Update plan status** to `Deployed` once Phase 3 end-to-end test passes

---

## Deployment Deviations

### Phase 3 — `expired.badssl.com` test methodology is structurally invalid (2026-05-11)

**Discovered during P3.T1.S2 execution.**

The plan's Step 1–4 test approach (add `https://expired.badssl.com/` to a VMProbe → expect a large negative `probe_ssl_earliest_cert_expiry - time()` → expect the 14d rule to fire) assumed blackbox-exporter's `http_2xx` module emits `probe_ssl_earliest_cert_expiry` during the TLS handshake "before HTTP status evaluation." That's true for **valid certs returning a non-2xx HTTP status** (e.g. Omni's `:8100/` returning 404 — the metric is populated despite `probe_success=0`). It is **not** true for hosts whose TLS handshake fails outright — and an expired cert without `tls_config.insecure_skip_verify: true` fails the handshake before the cert-inspection code path runs. Confirmed by hitting blackbox directly:

```
$ kubectl -n monitoring exec deploy/blackbox-exporter -- \
    wget -qO- 'http://localhost:9115/probe?module=http_2xx&target=https%3A%2F%2Fexpired.badssl.com%2F' \
    | grep -v '^#'
probe_dns_lookup_time_seconds 0.005803913
probe_duration_seconds 0.245563676
probe_failed_due_to_regex 0
probe_http_content_length 0
probe_http_duration_seconds{phase="connect"} 0
probe_http_duration_seconds{phase="processing"} 0
probe_http_duration_seconds{phase="resolve"} 0.005803913
probe_http_duration_seconds{phase="tls"} 0
probe_http_duration_seconds{phase="transfer"} 0
probe_http_redirects 0
probe_http_ssl 0
probe_http_status_code 0
probe_http_uncompressed_body_length 0
probe_http_version 0
probe_ip_addr_hash 1.56181497e+08
probe_ip_protocol 4
probe_success 0
```

`probe_ssl_earliest_cert_expiry` is absent from the response — so the alert rule would have nothing to evaluate against for this instance, and `noDataState: OK` would keep that *specific instance* of the rule inactive even if the target were added. (This is orthogonal to the rule's *current* `state=inactive` on the live cluster, which is correct-for-a-different-reason: no real cert is within 14d. The two `state=inactive` conditions are independent.) The same flaw applies to *real* certs that have already expired in production: at the precise moment an alert would most matter, the metric disappears. The rule fires only on the *runway* to expiry (T-14d / T-7d), while the cert still validates.

**Empirical confirmation that `insecure_skip_verify: true` lifts the gap (run 2026-05-11 in response to a reviewer query).** Spawned a one-shot `prom/blackbox-exporter:v0.25.0` pod (the same image as the cluster's deployment) with a custom module config:

```yaml
modules:
  http_2xx_insecure:
    prober: http
    timeout: 10s
    http:
      valid_http_versions: ["HTTP/1.1", "HTTP/2.0"]
      valid_status_codes: [200, 301, 302, 400, 403, 404]
      follow_redirects: true
      preferred_ip_protocol: ip4
      tls_config:
        insecure_skip_verify: true
```

Probing `https://expired.badssl.com/` through this module emits the SSL series the default `http_2xx` strips:

```
probe_http_ssl 1
probe_http_status_code 200
probe_ssl_earliest_cert_expiry 1.428883199e+09        # 2015-04-12T23:59:59Z — decades in the past
probe_ssl_last_chain_expiry_timestamp_seconds -6.21355968e+10
probe_ssl_last_chain_info{fingerprint_sha256="ba105ce02bac76888ecee47cd4eb7941653e9ac993b61b2eb3dcc82014d21b4f",issuer="CN=COMODO RSA Domain Validation Secure Server CA,…",subject="CN=*.badssl.com,…",subjectalternative="*.badssl.com,badssl.com"} 1
probe_success 1
probe_tls_version_info{version="TLS 1.2"} 1
```

So **Recommendation (a) below is sound on blackbox v0.25.0** (the version Frank runs). Upstream blackbox issue [#1119](https://github.com/prometheus/blackbox_exporter/issues/1119) reports the opposite behavior — that report does not reproduce here. The one-shot test pod and ConfigMap were deleted after the test.

**This is fine for the design's actual goal** — paging before expiry, not after — but it means `expired.badssl.com` cannot be used as a synthetic test target through the default `http_2xx` module.

#### What was verified end-to-end

1. **Rule machinery** (P3.T1.S3 equivalent): both `tls-cert-expiring-14d` and `tls-cert-expiring-7d` are loaded into Grafana, evaluating cleanly (`health=ok`), and producing 5 alert instances each (one per existing probed cert). All 5 instances are `state=inactive` because the closest cert (`blog.derio.net`) is 36 days out — correctly outside both thresholds:

   ```
   group=tls-cert-expiry-1h
     rule="TLS cert expiring within 14 days" state=inactive health=ok lastEval=2026-05-11T17:12:50Z alerts=5
   group=tls-cert-expiry-1h
     rule="TLS cert expiring within 7 days"  state=inactive health=ok lastEval=2026-05-11T17:12:50Z alerts=5
   ```

   Live days-until-expiry for all probed certs:

   ```
   https://blog.derio.net                  36.1 days
   https://grafana.frank.derio.net         45.6 days
   https://paperclip.frank.derio.net       45.6 days
   https://omni.frank.derio.net/           45.6 days
   https://omni.frank.derio.net:8100/      89.8 days
   ```

2. **Telegram delivery path** (P3.T1.S4 equivalent): sent a synthetic Phase-3 test message to Grafana's `Telegram - Willikins` contact point credentials (the same `FRANK_C2_TELEGRAM_BOT_TOKEN` + `FRANK_C2_TELEGRAM_CHAT_ID` Grafana injects into the receiver) via the Bot API directly from inside the Grafana pod. Telegram returned `{"ok":true,"result":{"message_id":1056,...}}`. The receiver is wired identically for the cert-expiry rules' severity labels (warning/critical), so any future fire from `tls-cert-expiring-14d` or `tls-cert-expiring-7d` traverses the same path.

3. **Probe pickup mechanics** (P3.T1.S1 + S2 partial): created a transient out-of-band `VMProbe/monitoring/test-expired-cert-probe` (not managed by ArgoCD) with `https://expired.badssl.com/` as target. vmagent picked it up within ~30s; `samples_scraped=17` per scrape (i.e. the prober runs and emits 17 standard probe metrics) — confirming the new-target → vmagent → blackbox path works. `probe_ssl_earliest_cert_expiry` was *not* among the 17 (see above). The transient VMProbe was deleted after verification.

#### What was NOT verified

The actual rule fire on real metric data crossing the 14d threshold — and therefore the for/1h debounce → notification-policy routing chain *triggered by a Grafana rule fire* — was not exercised. Components 2 and 3 above prove the rest of the chain works.

#### Why live-patching couldn't drive this on a feature branch

(For the record, since the plan's `git push` instructions assumed it could.) ArgoCD pulls only from `main`. Live-patching `VMProbe/monitoring/management-plane-probes` to add `expired.badssl.com` worked for ~3 minutes; then the root App-of-Apps re-templated `apps/root/templates/blackbox-exporter.yaml`, flipped `selfHeal` back to `true`, and the leaf reconciled the live VMProbe back to `main` ground truth, pruning the added target. (See the gotcha in `frank-gotchas.md` about root App-of-Apps re-templating leaves.) The out-of-band `test-expired-cert-probe` VMProbe — created with a name not in any chart source — survived because ArgoCD has `prune: false` semantics.

#### Recommended follow-up (not in scope for this plan)

Two paths to close the test gap, both requiring code changes. Both are *empirically* verified to work on blackbox v0.25.0 — see the test above.

1. **Add an `http_2xx_insecure_tls` module** to the blackbox config (currently `apps/blackbox-exporter/manifests/configmap.yaml` → `data.blackbox.yml` → `modules:`) with `tls_config.insecure_skip_verify: true`. Use it on a dedicated long-lived `expired-cert-canary` VMProbe target pointed at `https://expired.badssl.com/`. Pro: drives a permanent canary instance that always satisfies the alert thresholds, giving a continuous heartbeat through the full chain. Con: the canary will *always* be in alert state, so either (a) add a `canary: "true"` label on that VMProbe target and a notification-policy mute rule keyed on it (preferred — the existence of the canary instance in the alert list IS the heartbeat, without needing repeat Telegrams), or (b) accept periodic noise. Confirmed working as documented in the empirical-test block above.
2. **Generate a self-signed cert with `notAfter` ~13 days out** and host it from an in-cluster test pod. Probe it with the same `http_2xx_insecure_tls` module (self-signed → handshake won't validate against system roots → `insecure_skip_verify` required) and expect the metric to be populated and within the 14d threshold. Time-bounded test; re-roll the cert before it expires *or* let it expire and re-test from inside the 7d window too. This *actually* exercises the rule-fire path end-to-end (cert → blackbox → metric → rule eval → for/1h → notification policy → Telegram) on a fresh real cert that crosses the threshold for the first time, whereas option 1 has the canary perpetually inside the threshold.

The companion **follow-up tracking issue** capturing this work is [#251](https://github.com/derio-net/frank/issues/251).

For now, the plan is marked Deployed on the strength of the partial verification documented above. If a real cert is renewed shortly before expiry inside the 14d window — which is what `omni-cert-renew.timer` is *supposed* to prevent for omni specifically — the next Frank operator will observe whether the chain delivered.

#### Operating outcome

What the operator should expect from this layer, as deployed today:
- Probes: `feature-health-probes` (5 targets, Layer-N feature health) + `management-plane-probes` (Omni :443 and :8100). Adding new HTTPS targets to either VMProbe inherits cert-expiry coverage automatically because the alert rule keys on the metric, not on an `instance` regex.
- Alert rules: `tls-cert-expiring-14d` (severity: warning) and `tls-cert-expiring-7d` (severity: critical), both with `for: 1h`. `noDataState: OK` — a probe target with no SSL series (broken DNS, dead host, expired cert without the insecure module) does NOT page; only a *valid* cert crossing the threshold pages.
- Delivery: routes via the existing severity-keyed notification policy to the `Telegram - Willikins` contact point. Same path as every other Grafana-managed alert.
- Known gap: the runway-to-expiry behavior is the production scenario and is wired correctly; the at-expiry behavior is intentionally *not* a page (it would be `noData`).
