<!-- fr:journal-schema=2 -->
# Journal: 2026-10-13-mirror-reconcile-kid-laptops

<!-- fr:journal kind=root-cause scope=debug id=5e04492bd47d created=2026-10-13T21:50:19+00:00 -->
### 5e04492bd47d · root-cause · mirror-reconcile never covered derio-homelab/kid-laptops

Built in #851 against the agentic-stoa-main-sync trigger only; kid-laptops has its own trigger (derio-homelab-kid-laptops-main-sync, different GitHub App + webhook secret). The guard test derived its expected list from that one trigger, so it passed while a sibling was uncovered. Also: the job used one GITHUB_TOKEN (agentic-stoa App), which 404s on derio-homelab private repos, so adding the repo to the list alone would have failed every run.

<!-- fr:journal kind=finding scope=debug id=d2c6e32d22fd created=2026-10-13T21:50:27+00:00 state=fixed -->
### d2c6e32d22fd · finding [fixed] · Add derio-homelab/kid-laptops with a per-org GitHub token

MAIN_REPOS (both stages) gains the repo (not PR_REPOS: push trigger only). plan.py token_for + push.sh auth_for pick GITHUB_TOKEN_<ORG> else GITHUB_TOKEN; GITHUB_TOKEN_DERIO_HOMELAB wired from derio-homelab-github-mirror/token, optional:true so a missing Secret cannot stop the agentic-stoa repairs. Guard now unions every *-main-sync trigger. Red first (4 failed), green after: 43 passed. auth_for verified under the production alpine/git busybox ash. Secret verified live (key token, ESO SecretSynced). SSH to Gitea uses stoa-bot, already proven to write kid-laptops.

<!-- fr:journal kind=review scope=debug id=98533cee3201 created=2026-10-13T21:50:36+00:00 -->
### 98533cee3201 · review · Self-review (no independent reviewer)

Read the diff myself. Checked: optional secretKeyRef (a missing derio Secret cannot CreateContainerConfigError the Job); fallback to GITHUB_TOKEN yields a loud 404 into errors.txt rather than a KeyError; kid-laptops stays out of PR_REPOS (no PR trigger); the behaviour test records the real credential via a git shim; busybox path checked in the production image. Residual: not exercised against live GitHub until the CronJob runs post-merge; the reconciler cannot repair a corrupt Gitea repo (same unpacker error); the alpine variant of the new behaviour test skips by design (shim is host-side).
