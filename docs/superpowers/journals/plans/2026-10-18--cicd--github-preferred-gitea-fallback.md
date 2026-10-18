<!-- fr:journal-schema=2 -->
# Journal: 2026-10-18--cicd--github-preferred-gitea-fallback

<!-- fr:journal kind=decision scope=plan id=plan-shape created=2026-10-18T14:47:33+00:00 -->
### plan-shape · decision · Five agentic phases (one per ask) plus a trailing manual phase

Skeleton = tier config + gate-coverage checker (the cross-repo PRs validate against it). Cross-repo PRs (R17) are dispatched by the orchestrator after phase 1 lands and tracked in the manual phase; PRE-MERGE gates are manual ops that hold the PR in draft.

<!-- fr:journal kind=discovery scope=plan id=gate-coverage-baseline created=2026-10-18T14:51:17+00:00 phase=1 -->
### gate-coverage-baseline · discovery · Gate-coverage baseline across the eleven cross-repo targets (work list) (phase 1)

Checker run read-only on 2026-10-18 against the local clones (all workflows; the cnc repos are gitea-only here, so their numbers are wider than the release.yml-only scope of R17).
willikins 6 ungated; herdr-vertical-tabs 2 ungated; presentation-craft 3 ungated; vibe-kanban 28 ungated (VK_PRIVATE_DEPLOY_KEY passed as gitea_secret); runs-fr 7 ungated;
proxmox-cluster 3 ungated; omada-controller 2 ungated; homelab 2 ungated; ansible-pihole 1 missing-rerun-triggers (gates already present);
cnc-frd 1 ungated + 1 fallback-github-token-to-github + 1 fallback-secret-not-mirrored + 2 missing-rerun-triggers; cnc-fru 1 ungated + 1 fallback-github-token-to-github + 2 fallback-secret-not-mirrored + 2 missing-rerun-triggers.
Only release.yml in cnc-frd/cnc-fru gets the GitHub pin (spec section 6); the other cnc findings are context, not work.

<!-- fr:journal kind=discovery scope=plan id=worktree-has-no-venv created=2026-10-18T14:51:17+00:00 phase=1 -->
### worktree-has-no-venv · discovery · Worktree has no .venv; use the base clone's venv python/pytest by absolute path (phase 1)

The checker needs PyYAML, so the baseline was run with the base clone's .venv python.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t2 created=2026-10-18T14:51:17+00:00 phase=1 -->
### no-refactor-p1-t2 · discovery · no-refactor-because P1.T2 (phase 1)

tiers.yaml and its test are data plus plain assertions; nothing to clean.
