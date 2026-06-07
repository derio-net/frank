# Cert-Expiry Canary (issue #251, option 1)

**Spec:** `docs/superpowers/specs/2026-06-07--obs--cert-expiry-canary-design.md`
**Issue:** [frank#251](https://github.com/derio-net/frank/issues/251)
**Parent plan:** `docs/superpowers/implemented/plans/2026-05-11--obs--cert-expiry-alerting/`
**Layer:** obs (fix/extension of Layer 08 — tracker `frank-ops#8`)

## Why

The deployed `tls-cert-expiring-{14d,7d}` rules have never fired on real metric
data — the default blackbox `http_2xx` module aborts TLS handshakes against
expired certs before cert inspection, so the metric is never emitted and
`noDataState: OK` keeps the rules silently inactive. This plan adds the
permanent canary (issue option 1): an `insecure_skip_verify` blackbox module
probing `https://expired.badssl.com/`, whose perpetually-firing alert instances
ARE the heartbeat, muted at the notification-policy layer so neither Telegram
nor health-bridge ever hears them — plus an `absent()` watchdog that turns a
dead heartbeat into a self-healing health-bridge bug issue.

## Load-bearing invariants (read before editing)

1. **Route order is the whole design.** Watchdog route (`canary_watchdog="true"`
   → Health Bridge, `continue: false`) MUST precede the mute route
   (`canary="true"` → perma-muted, `continue: false`), which MUST precede all
   existing routes. The watchdog alert also carries `canary="true"` (absent()
   propagates its selector's equality matchers) — wrong order silently mutes
   the watchdog. Both new routes must also precede the severity routes: the
   canary fires BOTH tls-cert rules (warning + critical), and the watchdog
   carries `severity: critical` (required for health-bridge's dead→bug-issue
   lifecycle) that must never reach Telegram.
2. **`noDataState: OK` is inverted for the watchdog.** absent() returns EMPTY
   when the metric exists — noData is the healthy path.
3. **health-bridge contract** (verified against bridge.go): no `github_issue`
   label → alert skipped; firing+critical → `dead` → bug issue; resolved →
   auto-close (v0.3.1).

## Phases

- **Phase 1 (agentic):** blackbox `http_2xx_insecure_tls` module +
  `expired-cert-canary` VMProbe, TDD via
  `scripts/tests/test_cert_expiry_canary.py` (pytest + pyyaml manifest
  invariants).
- **Phase 2 (agentic):** `perma-mute` time interval + two prepended routes +
  `tls-cert-canary-absent` rule, same test file extended (routing-order
  assertions included).
- **Phase 3 (manual):** post-merge deploy verification — the spec's Test Plan
  (ArgoCD sync, blackbox + Grafana restarts, metric check, Pending→Firing
  watch, silence checks, watchdog Normal). Back-loaded per fr-goal; the PR
  ships with this phase deliberately unimplemented.

## Post-deploy checklist

Skipped per `plan-config.yaml` `skip_when` (fix/extension plan): no blog
posts, no README change, no external exposure (consistent with the parent
plan's precedent). No `# manual-operation` blocks — the restarts are one-time
deploy actions, not durable manual operations. A gotcha one-liner lands only
if implementation surfaces a new non-obvious pattern.
