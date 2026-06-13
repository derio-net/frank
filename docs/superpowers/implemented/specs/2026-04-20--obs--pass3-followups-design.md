# Pass 3 Follow-ups — Closing the Signal Gaps

*Date: 2026-04-20*
*Status: Stub — to be fleshed out in a brainstorming session.*

## Context

Pass 3 of the Derio Ops board restoration (`2026-04-16--platform--derio-ops-layers-restoration-design.md`) wired 19 Grafana alert rules — one per Layer tracker on the board — to drive the Lifecycle field via the Health Bridge.

While deploying those rules, several gaps surfaced where the intended signal couldn't be expressed because the underlying metric or probe wasn't available. Fallback rules were used (documented per-Layer in the Pass 3 plan's Deployment Deviations section), and follow-up comments were posted on the affected tracker Issues.

This spec collects those follow-ups in one place so they can be scoped + planned together in an upcoming brainstorming session.

## Concrete motivating incident (2026-05-11)

The Let's Encrypt leaf for `omni.frank.derio.net` expired on 2026-05-09 (notAfter `13:52:36 UTC`). The cluster's entire management plane went dark — `kubectl` OIDC discovery, `omnictl` gRPC, and the Omni Web UI all returned 500 because Traefik was rejecting Omni's upstream cert. Detection took ~46 hours and only happened when a `kubectl` call hit the failure path. **A global `probe_ssl_earliest_cert_expiry - time() < 14*86400` rule subscribed to Telegram would have paged at 2026-04-25 (T-14d), well before any expiry.**

Two concrete gaps this incident exposes:

1. `omni.frank.derio.net` is not in any blackbox probe target — `apps/blackbox-exporter/manifests/vmprobe.yaml` only probes the workloads it knows about. Cluster-management-plane endpoints have no probe coverage at all.
2. The cert-expiry rule scoped in this spec exists as a placeholder *comment* at `apps/grafana-alerting/manifests/alert-rules-cm.yaml:1173`, inside the Layer 18 (Hop) block. Even if implemented in-place, it would only cover Hop's blog probe — not Omni, ArgoCD UI, Authentik, or any other internal-cert-bearing service.

The right shape for the resolved follow-up is therefore *both* widening probe coverage (a probe per external-facing hostname) *and* a global rule keyed on `probe_ssl_earliest_cert_expiry` regardless of which Probe instance produced it. See `docs/investigations/2026-05-11--omni--cert-expiry-incident.md` for the full incident write-up.

## Candidate follow-ups

### Missing metrics — Longhorn (affects `frank-ops#4` + `frank-ops#9`)

- **Longhorn native metrics are not scraped.** Add a `VMServiceScrape` (or equivalent) for the Longhorn Manager's `/metrics` endpoint.
- **Layer 4 rule should be rewritten** to target per-volume `longhorn_volume_robustness` (values: 0=unknown, 1=healthy, 2=degraded, 3=faulted) with `{{ $labels.volume }}` templating. Current fallback fires on `longhorn-manager-*` pod readiness only.
- **Layer 9 rule should be rewritten** to target `longhorn_backup_target_*` (true per-volume backup age) instead of the current `kube_cronjob_status_last_successful_time` proxy.

### Missing metrics — ArgoCD (affects `frank-ops#6`)

- **ArgoCD app metrics are not scraped.** Add a `VMServiceScrape` for `argocd-metrics` / `argocd-server-metrics`.
- **Layer 6 rule should be extended** with a per-app sub-rule on `argocd_app_info{health_status!~"Healthy|Missing"}` surfacing `{{ $labels.name }}` + `{{ $labels.health_status }}` in the annotation. Current rule covers pod readiness only.

### Layer 16 Media Generation (blocked by design) — `frank-ops#16`

- Layer is currently `blocked` pending a Traefik route for ComfyUI + model downloads. Once unblocked, add a rule covering ComfyUI + GPU Switcher pod readiness with `severity=warning`, `github_issue=frank-ops#16`. Placeholder `DEFERRED` comment already in `apps/grafana-alerting/manifests/alert-rules-cm.yaml`.

### Layer 17 Public Edge — extended basis (`frank-ops#17`)

Pass 3 shipped only the blog blackbox probe. The spec's extended basis also called for:

- **Headscale mesh peer count** — needs a headscale metrics exporter (Caddy sidecar or separate deployment on Hop).
- **TLS cert expiry** — can be added today via `probe_ssl_earliest_cert_expiry - time() < 7*86400` against the blog probe (Blackbox already exports this — just needs the rule).
- **Hetzner API status** — needs a new exporter (`prometheus-hetzner-exporter` or similar) with the Hetzner API token.

### Cluster hygiene — Grafana PVC + RollingUpdate deadlock

- Every Grafana pod restart (e.g. to reload provisioning) risks a `RWO PVC + RollingUpdate` deadlock when the Deployment's pod template changes (ConfigMap checksum annotation). Documented in `.claude/rules/frank-gotchas.md`.
- **Fix:** switch the Grafana Helm chart's `strategy.type` from `RollingUpdate` to `Recreate` in `apps/victoria-metrics/values.yaml` (or wherever Grafana's strategy is templated). Single-replica deployment — no availability cost.

## Next step

Run `/brainstorming` against this spec to:
1. Decide scope — one bundled plan, or one plan per layer/gap?
2. Order by dependency (Longhorn scrape unblocks both L4 and L9; ArgoCD scrape unblocks L6; Hetzner exporter is net-new work).
3. Decide whether Grafana `strategy: Recreate` goes in this bundle or as its own fix plan.
4. Identify any missing items surfaced during brainstorming (e.g. the endpoint-down + agent-pod-not-running enrichment pattern might want to be applied more broadly).

## References

- Pass 3 plan: `docs/superpowers/plans/2026-04-16--platform--derio-ops-pass3-grafana-wiring.md` (see Deployment Deviations section)
- Follow-up comments on the trackers: `frank-ops#4`, `#6`, `#9`, `#16`, `#17`
- Grafana gotcha: `.claude/rules/frank-gotchas.md` (RWO PVC + RollingUpdate)

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| Obs — Cert-Expiry Alerting Implementation Plan |  | `2026-05-11--obs--cert-expiry-alerting` | — |
