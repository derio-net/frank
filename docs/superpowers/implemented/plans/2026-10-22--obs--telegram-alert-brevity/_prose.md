# Telegram alert brevity — implementation plan

**Status:** In Progress

Spec: `docs/superpowers/specs/2026-10-22--obs--telegram-alert-brevity-design.md`.

One agentic phase, because the whole change is a single reviewable ask: a provisioned
Grafana notification template plus the one `message:` setting that wires it into the
`Telegram - Willikins` receiver, guarded by offline tests and proven by a render through
Grafana's own template engine before merge.

There is no `[manual]` phase. The only operator actions are post-merge verification: confirm the live
ConfigMap, roll Grafana (provisioning is read at boot), and watch a real firing/resolved pair.
They live in the spec's Test Plan and the `verify: live` acceptance rows.

Approaches considered:
- **Provisioned template in the contact-points file (chosen):** declarative, no new mount, and
  it keeps the template next to the only receiver that uses it.
- Separate `templates.yaml` ConfigMap key and mount: cleaner separation, but it needs a chart-values
  change and a new subPath mount for a ~40-line template.
- Inline the whole Go template in `settings.message`: no `define`s, but unreadable, and it
  cannot be previewed with the templates/test endpoint.
