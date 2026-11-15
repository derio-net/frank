# kid-laptops mirror: PR heads, a repair alert, and the pull-sync diagnosis

**Status:** In Progress
**Layer:** cicd (fix/extension)
**Spec:** `docs/superpowers/specs/2026-11-15--cicd--kid-laptops-mirror-pr-heads-design.md`
**Issues:** frank#952, frank#850, frank#798 (closed by the PR; none is a phase tracking issue)

## Shape

There is one agentic phase. The three asks share a single mirror pipeline, and the diff is
mostly list edits plus one alert rule and their guards, which one reviewer can hold at once.
The only work beyond it is the post-merge GitHub webhook change, carried as a devops op
(`ops.yaml`) rather than a phase, as `2026-11-14--auth--root-agents-least-privilege` does.

1. **#952 + R4.** Add kid-laptops to `derio-homelab-pr-sync`, the `webhooks.yaml` declaration,
   and `PR_REPOS` in `mirror-reconcile` (`heads` + `plan`) and `ci-delivery-check`. Make the
   Gitea-side `kid-laptops-push` trigger main-only.
2. **#850 + #798.** Add the `layer-25-mirror-repair-recurring` VictoriaLogs rule (per repo,
   ≥2 repairs in 6h, warning, `ci_outcome`) and correct the stale
   `layer-25-mirror-sync-failing` runbook.
3. Coupled blog posts, gotchas and the manual-operation block.
4. Quality gate.

## Ordering with kid-laptops#139

This PR can merge before derio-homelab/kid-laptops#139, but be clear about what merging does.
Gitea reads `on.push` from the pushed commit, so the backfilled `sync-pr-139` runs molecule at
once, while #104 and #105 start nothing. The first reconcile repairs all three sync-pr refs and
fires `layer-25-mirror-repair-recurring` once: an expected one-off, and the rule's positive
control (ops `first-reconcile-backfill`). Apply the webhook op before merging.

## Manual operations

```yaml
# manual-operation
id: cicd-kid-laptops-github-webhook-pull-request
layer: cicd
app: tekton
plan: docs/superpowers/plans/2026-11-15--cicd--kid-laptops-mirror-pr-heads
when: Before (or right after) the frank PR merges. Before is safe, because the live derio-homelab-pr-sync CEL drops kid-laptops pull_request events until the merge syncs.
why_manual: The GitHub repo webhook is configured on GitHub with org-owner credentials the cluster does not hold; it is not reconciled from git (webhooks.yaml is a declaration, checked offline only).
commands:
  - "GITHUB_TOKEN must be UNSET so gh uses the account that owns derio-homelab."
  - "env -u GITHUB_TOKEN gh api repos/derio-homelab/kid-laptops/hooks --jq '.[]|select(.config.url==\"https://webhooks.hop.derio.net\")|{id,events}'   # expect id 657693217, events [push]"
  - "env -u GITHUB_TOKEN gh api -X PATCH repos/derio-homelab/kid-laptops/hooks/657693217 -f 'events[]=push' -f 'events[]=pull_request'"
verify:
  - "env -u GITHUB_TOKEN gh api repos/derio-homelab/kid-laptops/hooks/657693217 --jq .events   # [\"pull_request\",\"push\"]"
  - "env -u GITHUB_TOKEN gh api -X POST repos/derio-homelab/kid-laptops/hooks/657693217/pings ; kubectl -n tekton-pipelines logs deploy/el-github-listener --tail=20   # ping/delivery shows"
  - "After the next push to a same-repo kid-laptops PR: git ls-remote http://192.168.55.209:3000/derio-homelab/kid-laptops.git 'refs/heads/sync-pr-*'"
status: pending
```
