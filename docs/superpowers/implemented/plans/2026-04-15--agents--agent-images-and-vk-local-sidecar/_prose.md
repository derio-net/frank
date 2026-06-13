# Agent Images & vk-local Sidecar — Implementation Plan

## Phase 0: Bootstrap `agent-images` repo with base + kali

### Task 1: Create the `agent-images` repo on GitHub

- P0.T1.S1: Verify the repo exists and is cloneable.

### Task 2: Write `base/Dockerfile`

- P0.T2.S1: Write the base Dockerfile at `agent-images/base/Dockerfile`.

- P0.T2.S2: Smoke-test locally. *(skipped — no docker daemon available in agent pod; CI build validates)*

### Task 3: Write matrix CI workflow

- P0.T3.S1: Write the workflow at `agent-images/.github/workflows/build.yaml`.

- P0.T3.S2: Configure `DISPATCH_PAT` secret. *(deferred — manual operation, dispatch-frank job will fail gracefully until PAT is configured)*

### Task 4: Port kali Dockerfile into `kali/`

- P0.T4.S1: Copy runtime assets from the existing `secure-agent-kali` repo.

- P0.T4.S2: Write `kali/Dockerfile`.

- P0.T4.S3: Strip VibeKanban from the entrypoint.

- P0.T4.S4: Commit and push.

- P0.T4.S5: Verify CI green and images published. *(both agent-base and secure-agent-kali pushed to GHCR at sha bc6322c; dispatch-frank fails as expected — DISPATCH_PAT not yet configured)*

### Task 5: Validate kali image parity

- P0.T5.S1: Boot the new image locally and check tool surface. *(validated via CI build log — all tools installed: claude-code, gh, node, kubectl, talosctl, omnictl, sshd, kali-tools-top10, nmap, netcat; both images pushed to GHCR at sha bc6322c)*

- P0.T5.S2: Confirm no VibeKanban residue. *(verified: no vibe-kanban, vibekanban, or 8081 references in entrypoint.sh or Dockerfile)*

## Phase 1: VK fork artifact + `vk-local` image

### Task 1: Add `vibe-kanban-build` artifact job to fork CI

- P1.T1.S1: Write the artifact Dockerfile.

- P1.T1.S2: Extend fork CI to build and push the artifact.

- P1.T1.S3: Dispatch to agent-images.

- P1.T1.S4: Commit, push, verify.

### Task 2: Add `vk-local/Dockerfile` to agent-images

- P1.T2.S1: Write `vk-local/Dockerfile`.

- P1.T2.S2: Extend the agent-images matrix.

- P1.T2.S3: Commit, push, verify vk-local published.

### Task 3: Smoke-test vk-local

- P1.T3.S1: Boot locally, check it serves. *(skipped — no docker daemon in agent pod; replaced by dispatch chain verification below, which confirmed `vk-local:325b23e` built and published successfully)*

- P1.T3.S2: Identify the health endpoint.

## Phase 2: Sidecar deployment + kali cutover

## Phase 3: Lockstep bumper workflow

### Task 1: Write the bumper workflow

- P3.T1.S1: Write the workflow. *(written as `.yml` for consistency; uses GHCR tag resolution instead of private repo query; adds SHA validation — see Deployment Deviations)*

- P3.T1.S2: Commit and push. *(committed as `81ab54b` on `vk/49aa-ffe-39-gh-82`)*

### Task 2: Dry-run the bumper

- P3.T2.S1: Trigger manually with the current agent-images SHA. *(2026-04-17 post-merge of PR #85; run [24586433455](https://github.com/derio-net/frank/actions/runs/24586433455) — SHA resolution + manifest update succeeded, `gh pr create` step failed on Actions permissions — see deviation below)*

- P3.T2.S2: Inspect the generated PR. *(PR [#105](https://github.com/derio-net/frank/pull/105) created manually from the workflow-pushed `bump/agent-images-325b23e` branch; diff touched only `apps/vk-remote/manifests/deployment.yaml` — both vk-remote refs bumped `1cce857` → `5bd749c`. kali + vk-local already at current agent-images SHA, so no diff there — expected behavior after Phase 2 cutover.)*

- P3.T2.S3: Close without merging (dry-run only). *(PR #105 closed, branch deleted. Workflow logic validated end-to-end.)*

### Task 3: Verify the full dispatch chain

- P3.T3.S1: Push a trivial change to the fork. *(2026-04-18: vibe-kanban PR #6 `fix/server-embed-local-web-dist` — the frontend-embed fix — triggered via `workflow_dispatch` on the feature branch; later agent-images README update pushed to main as SHA `95e364f`)*

- P3.T3.S2: Follow the chain. *(2026-04-18: full chain verified end-to-end — vibe-kanban run [24597591042](https://github.com/derio-net/vibe-kanban/actions/runs/24597591042) → agent-images run [24598258993](https://github.com/derio-net/agent-images/actions/runs/24598258993) → frank bumper run [24598275621](https://github.com/derio-net/frank/actions/runs/24598275621) → PR [#107](https://github.com/derio-net/frank/pull/107) auto-opened bumping all three images — secure-agent-kali + vk-local → `95e364f`, vk-remote → `91f09db`)*

## Phase 4: Post-Deploy Checklist
