# LiteLLM amd64 Affinity + Open-Issue Close-outs

**Spec:** `docs/superpowers/specs/2026-06-06--infer--litellm-amd64-affinity-closeouts-design.md`
**Issues:** #478 (primary code change), #476 (README remainder + verifications), #474 (close-only)
**Branch:** `feat/issue-cleanup-474-476-478`

## Why this shape

Issue #478 proposed four remediations on the premise that chart
`litellm-helm 1.81.13` supports no scheduling control on the Prisma
migrations Job. Pulling the pinned chart from `docker.litellm.ai/berriai`
disproved that premise for `affinity`/`tolerations`:

- `templates/migrations-job.yaml:106` — `{{- with .Values.affinity }}`
- `templates/migrations-job.yaml:110` — `{{- with .Values.tolerations }}`
- `templates/deployment.yaml:226/:230` — the same top-level values

So one top-level `affinity` block (require `kubernetes.io/arch=amd64`) fixes
both the main gateway pods (the values.yaml TODO's item 1, minus resources)
and the migrations Job (TODO item 2 / #478). No Pi taint, no upstream PR, no
chart bump. Arch — not hostname — is the chosen key: the Pis are ARM, and a
broken upstream arm64 image layer was a prior failure mode (PR #220), so
amd64 encodes the actual constraint rather than the current node names.

**Deliberately deferred:** resources requests/limits (TODO item 1's other
half) stay TODO — the numbers need live usage data and the Metrics API is
dead (#394). The rewritten TODO notes VictoriaMetrics as the verification
path.

## Rollout consequence (accepted)

litellm is an Argo Rollouts canary (`workloadRef` → the chart Deployment)
with two indefinite manual gates. The affinity edit changes the pod template,
so merging triggers a gated canary that an operator must promote (Phase 3).
The migrations Job needs no gate — it picks the affinity up on the next
ArgoCD sync (PreSync hook).

## TDD shape

Phase 1 uses an offline render assertion (`helm template` of the pinned chart
against the repo values file) as the red/green check: red proves neither the
Deployment nor the Job currently renders affinity; green proves both do after
the one-block edit. The script lives in gitignored `scripts/tmp/` — it's a
one-shot structural assertion for this change, not a CI suite.

## Phase 2 — README

The only #476 remainder that is repo work: run the `update-readme` skill so
Current Status / Service Access reflect the ai-alert-helper 0.2.0 analyst
(PR #469) and anything else stale since. Digest item 10 is already closed by
operator evidence (2026-06-06 08:00 digest arrived in Telegram — Q&A,
2026-06-06); the cosmetic ArgoCD `Degraded` check moves to Phase 3.

## Phase 3 — manual, back-loaded

Post-merge verification and ceremony: promote the canary with the canary pod
evidence-gated onto amd64 first, confirm the next migrations Job pod lands
non-Pi, confirm README rendering, clear the appTree-cache `Degraded` if still
present, then close #474/#476/#478 with the evidence trail. #474 needs no
code at all — building `33-hermes-shell`, operating `28-hermes-shell`, the
series index, and the cluster-roadmap entries all shipped in `ce2fcd9e`.

No `# manual-operation` blocks: nothing here creates non-declarative cluster
state — Phase 3 is one-time verification/promotion, already covered by the
Rollouts gotcha docs, not a reproducibility-critical setup step.
