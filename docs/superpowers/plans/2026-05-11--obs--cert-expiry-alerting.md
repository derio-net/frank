# Obs — Cert-Expiry Alerting Implementation Plan

**Spec:** `docs/superpowers/specs/2026-04-20--obs--pass3-followups-design.md`
**Status:** In Progress

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

- [ ] **Step 3: Commit + push + sync + restart Grafana**

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

- [ ] **Step 4: Verify rules are loaded**

  ```bash
  GRAFANA_PASS=$(kubectl -n monitoring get secret victoria-metrics-grafana -o jsonpath='{.data.admin-password}' | base64 -d)
  kubectl -n monitoring exec deploy/victoria-metrics-grafana -- \
    wget -qO- --user=admin --password="$GRAFANA_PASS" \
    'http://localhost:3000/api/v1/provisioning/alert-rules' \
    | grep -oE '"uid":"tls-cert-expiring-[0-9]+d"'
  ```

  Expected output:
  ```
  "uid":"tls-cert-expiring-14d"
  "uid":"tls-cert-expiring-7d"
  ```

---

## Phase 3: End-to-end verification [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/245 -->

**Depends on:** Phase 2

Drive the full alert path with a deliberately-expired probe target (`badssl.com/expired/`). This is the gating test — Phases 1 + 2 only count as done once Telegram delivery is observed.

### Task 1: Trigger alert with `badssl.com/expired/`

- [ ] **Step 1: Temporarily add `https://expired.badssl.com/` to the management-plane probe**

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

- [ ] **Step 2: Confirm the probe is actually emitting the metric**

  ```bash
  kubectl -n monitoring exec deploy/victoria-metrics-grafana -- \
    wget -qO- 'http://vmsingle-victoria-metrics-victoria-metrics-k8s-stack.monitoring.svc.cluster.local:8428/api/v1/query?query=probe_ssl_earliest_cert_expiry%7Binstance%3D%22https%3A%2F%2Fexpired.badssl.com%2F%22%7D-time()'
  ```

  Expected: a `result` entry with a large negative `value` (e.g. `[-1.2e8]`).

- [ ] **Step 3: Confirm the rule evaluates to Alerting**

  ```bash
  GRAFANA_PASS=$(kubectl -n monitoring get secret victoria-metrics-grafana -o jsonpath='{.data.admin-password}' | base64 -d)
  kubectl -n monitoring exec deploy/victoria-metrics-grafana -- \
    wget -qO- --user=admin --password="$GRAFANA_PASS" --post-data='' \
    'http://localhost:3000/api/v1/provisioning/alert-rules/tls-cert-expiring-14d/preview'
  ```

  Expected: response includes `"state":"Alerting"` and an `Alerts:` array with the badssl.com instance.

- [ ] **Step 4: Wait `for: 1h` and confirm Telegram delivery**

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

- [ ] **Step 5: Revert the test probe**

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
- [ ] **Step 6: Update plan status** to `Deployed` once Phase 3 end-to-end test passes
