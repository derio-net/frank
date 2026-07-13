# Frank alert-triage skill + alert-agent report fixes

**Layer:** obs · **Spec:** `docs/superpowers/specs/2026-07-13--obs--alert-triage-and-agent-report-fixes-design.md`

Two related deliverables, one PR, unified by a shared alert-classification
decision tree and a compact plain-text report format.

## Why

"Grafana is alerting on Frank" is a recurring, fully-deterministic triage: every
firing alert maps to a documented pattern (canary → muted; `gpu_timeshare` →
by-design; a terminal/absent pod behind a readiness rule → false-positive;
`github_issue` label → known tracker). That belongs in a skill. Separately, the
autonomous alert-agent misbehaves in five operator-visible ways — all root-caused
to a **stale `SKILL.md`** (written against an earlier Telegram sender) plus a
hard-coded "Hacker News" example and a leaky JSON envelope.

## Approach

- **Phase 1** builds the shared brain: a pure, stdlib-only
  `classify(labels, pod_state) → Verdict` with a test per decision-tree branch,
  using the real alert label shapes captured during this session's live triage.
  Pure means the classifier never touches the cluster — the caller supplies the
  resolved pod state — so it is deterministically unit-tested.
- **Phase 2** wraps it in the operator-facing `frank-alert-triage` skill: fetch
  firing alerts from the Grafana API, resolve readiness-rule pods live (the
  live-vs-ghost-tombstone check), classify, and print a compact table.
  Classify-and-recommend only — never mutate (the auto-mode classifier correctly
  blocks pod deletes).
- **Phase 3** fixes the alert-agent, TDD-first where there's logic
  (`render_payload` string-envelope unwrap; prompt-content assertions), edits
  where it's prose (`SKILL.md`). The key realisation: `tg_send` already sends
  plain text with no `parse_mode`, so the "no tables / no `<>&`" rule is stale
  and actively prevents the table the operator wants.
- **Phase 4** is the back-loaded manual Test Plan: the skill and the agent both
  need a kube-credentialed host + the live Telegram bot to prove, so they are
  verified after merge, operator-driven.

## Deployment

Every alert-agent file (`SKILL.md`, `orchestration.py`, `bridge.py`) is mounted
from a **hash-suffixed ConfigMap** — any edit changes the hash and rolls the pod
automatically (the Application has `prune: true`). Deploy = git merge + ArgoCD
sync; **no image rebuild**. The `frank-alert-triage` skill is repo-only (no
cluster artifact).

## Non-goals

No cluster mutation from the skill; no auto-remediation; no raising
`DM_TIMEOUT_S` (the timeout fix is behavioural — bound the turn); the skill and
agent stay separate implementations (different execution contexts) sharing only
the documented decision-tree + format contract.
