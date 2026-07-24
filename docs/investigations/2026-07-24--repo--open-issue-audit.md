# Open-Issue Audit — derio-net/frank

**Date:** 2026-07-24
**Layer:** repo (meta)
**Type:** investigation / backlog triage
**Scanned:** all 13 open issues, cross-referenced against `main` @ `428454f0` (#685) and the implemented/planned specs & plans.

> Investigation/audit doc — no cluster changes. Per `plan-post-deploy-checklist.md`,
> investigation work skips the blog/README/runbook close-out. This file **is** the deliverable.

## TL;DR

Of 13 open issues:

- **2 recommend CLOSE** as obsolete — they describe components/artifacts that no longer exist (#477, #162).
- **1 recommend UPDATE** — partial progress already landed, the body is stale (#609: 13→5 remaining).
- **2 gate has LIFTED** — were "when Omni's back"; Omni access is effectively restored, re-evaluate + schedule (#597, #599).
- **2 stay PARKED** — real gating triggers genuinely unmet (#160, #161); **1 stays gated** on GPU hand-back (#554).
- **2 actionable, need SCHEDULING** (#688, #394).
- **2 orchestration experiments** to re-verify + consolidate (#472 ⟵ #475).
- **1 systemic, partly addressed** — re-scope to the residual work (#581).

Three merge candidates identified (see §Consolidation).

## Summary table

| # | Title (short) | Age | Verdict | Action |
|---|---|---|---|---|
| 160 | B2 — vk-local child spawn → kali sibling cgroup | Apr 30 | **Park** (valid backlog) | Keep open; triggers unmet |
| 161 | B3 — per-task K8s Jobs for vk executions | Apr 30 | **Park** (valid backlog) | Keep open; triggers unmet |
| 162 | investigate 9× OOM on vk image `dc414b4` | Apr 30 | **Stale → CLOSE** | Image + measurement window gone |
| 394 | No Metrics API — serve `metrics.k8s.io` | May 25 | **Actionable seed** | Schedule `/brainstorming` |
| 472 | ruflo-shell ANTHROPIC_* shim (local models) | Jun 04 | **Blocked-by #475** | Consolidate w/ #475; re-verify |
| 475 | ruflo `hive-mind spawn --claude` fails (MCP drift) | Jun 04 | **Re-verify** | Version-drift may be stale |
| 477 | obs trace-analyst deferred follow-ups | Jun 04 | **Stale → CLOSE** | 2/3 items ref retired code |
| 554 | live GPU-switch-flip health-probe test | Jun 15 | **Gated** (valid) | Keep open; runs on GPU hand-back |
| 581 | skill drift — repo skills not first-class | Jun 19 | **Partly fixed → re-scope** | Surfacing done; actuation+guard remain |
| 597 | revive staging-vCluster e2e gate (Omni) | Jun 21 | **Gate lifted** | Rebase PR #551 + Phase 7; schedule |
| 599 | CrowdSec canary + alert-agent triage (Omni) | Jun 21 | **Gate lifted** | Schedule; alert-agent bug is real |
| 609 | papers: capture pending screenshots | Jul 04 | **Update** | 8 done (#612), 5 remain |
| 688 | hermes ssh sidecar BYOK env dead | Jul 24 | **Actionable** | Schedule; sibling fix already landed |

---

## Detail & evidence

### CLOSE — obsolete

**#477 — obs: trace-analyst deferred follow-ups.** Two of three items reference the
**FastAPI `ai-alert-helper`, which was RETIRED → `alert-agent` on 2026-06-16**
(obs-digest gotcha: *"Old gotchas referencing the FastAPI endpoints/`apps/ai-alert-helper`
are historical"*). Confirmed on `main`: no `apps/ai-alert-helper`, no `alert api.py`, no
`build-ai-alert-helper` workflow. So:
- Item 1 (analyst INFO logging in `api.py`) — the file no longer exists.
- Item 3 (`build-ai-alert-helper` workflow tag hardcoded) — the workflow is gone.
- Item 2 (CrowdSec LAPI read-only over mesh) — was *conditional/dormant*; its premise
  ("local scenarios never fire") was itself overtaken by the CrowdSec pipeline fixes
  (#583/#584) and the ban-pipeline canary (#595/#596/#598) where local bans now do fire.

→ **Recommend CLOSE** as obsolete. If the deterministic-logging idea has residual value it
belongs as a fresh `alert-agent`-scoped issue, not this ai-alert-helper-era tracker.

**#162 — investigate 9× OOM-rate escalation on vk image `dc414b4`.** A forensic question
gated on #157's Phase 2 cadvisor pipeline. **#157 closed 2026-05-03.** The practical OOM
pressure was resolved by the vk-local `4Gi → 8Gi` bump (current gotcha: *"Keep at 8 Gi until…"*),
and the image `dc414b4` is many agent-images bumps stale (latest sweep #679/#681/#685). The
17.4 h vs 48 h measurement windows can't be reconstructed. The investigation is no longer
reproducible and its practical driver is gone.

→ **Recommend CLOSE** (forensic value expired; superseded by the 8 Gi steady-state).

### UPDATE — partial progress landed

**#609 — papers: capture 13 pending screenshots.** **8 of 13 already captured** in #612
(*"docs(papers): capture 8 pending papers screenshots"*). `find … -name '*-TODO.png'` on
`main` returns **5**:
- `02-immutable-os/omni-machines-TODO.png` (Omni UI — was blocked by the Pi death; **now
  capturable**, Omni access restored)
- `05-gpu-scheduling/gpu-utilisation-TODO.png` (Grafana, needs a live Ollama workload — couples
  to the GPU hand-back, cf. #554)
- `10-self-hosted-inference/grafana-inference-TODO.png`
- `13-self-hosted-cicd/tekton-pipelinerun-TODO.png`
- `14-progressive-delivery/argo-rollouts-canary-TODO.png`

→ **Keep open, update the checklist** to the remaining 5 (tick the 8 captured). Note the two
GPU/Ollama-coupled shots (05, and the inference dashboard 10) are best captured while the GPU
is on Ollama — piggyback on #554's hand-back window.

### Gate LIFTED — re-evaluate & schedule (Omni is effectively back)

Both #597 and #599 were filed 2026-06-21 as *"when Omni's back"* siblings after the
**frank-omni Pi died (hardware) 2026-06-20**. Evidence that Frank/Omni access is **restored**
since:
- **#618** documents a *working* fr-isolation `cluster-admin` Omni **service-account kubeconfig**
  (`system:masters` on cluster `frank`) — a JWT that only a **live Omni** mints/serves.
- **#642** (2026-07-16) records a **live Talos config apply** to gpu-1 (realtek-firmware) —
  reconcile that only happens through a functioning Omni.
- **#640** documents `OMNI_SERVICE_ACCOUNT_KEY` renewal / per-tower shutdown SAs — active Omni ops.

(omni.md still frames the *durable* fix as rehoming Omni onto Proxmox HA + UPS — a separate
Layer 2 build — but day-to-day access is back.)

**#597 — staging-vCluster e2e release gate.** PR #551 (open) + runs-fr#21 hold phases 1–6.
Remaining: **rebase both PRs** (they predate ~106 commits on `main`), **Phase 7 manual cluster
wiring** (SOPS the external-cluster Secret, gate secrets, EventListener trigger, CEL-validate
`sha`), then the green/red end-to-end test. → **Schedule**; verify the Omni-restored assumption
holds before the manual wiring.

**#599 — CrowdSec canary dead-man's-switch + alert-agent triage.** Two parts:
1. Make #598's Telegram-direct routing live (`rollout restart deploy/grafana` to reload
   provisioning) + finish the deferred Test-2 delivery confirmation.
2. **Investigate the alert-agent's confidently-false triage** — it surfaced the resolved #594
   incident *verbatim* as if current and misattributed unrelated Azure IPs. This is a genuine
   **correctness bug** (stale context bleeding into live triage) worth prioritising above the
   routing chore — a real future page could be drowned in false history.

→ **Schedule both**; treat 599.2 as a real bug, not a verification chore.

### Stay PARKED / gated (triggers genuinely unmet)

**#160 (B2 sibling cgroup)** & **#161 (B3 per-task Jobs)** — parked follow-ups from the
**closed** #157. Each carries explicit, currently-**unmet** trigger conditions (B2: ≥2
OOMKills/mo at cap after 30 d housekeeping, or an OS-isolation requirement; B3: cap≥8 + queue
p99>1 for 7 d + isolation need). vk-local is stable at 8 Gi. → **Keep open as backlog.** They
are mutually-exclusive architectural *options* for the same problem — see Consolidation.

**#554 — live GPU-switch-flip health-probe test.** Legitimately gated: gpu-1 time-shares
Ollama/ComfyUI one-at-a-time, Ollama is scaled to 0 "for the foreseeable future," and the test
*requires* Ollama active to prove the tiles flip both ways. Steady-state is already verified
(#552). → **Keep open, parked-until-GPU-handback.** Batch with #609's Ollama-coupled shots
(05, 10) and any other Ollama-only verification.

### Actionable now — schedule

**#688 — hermes ssh sidecar BYOK env re-export is dead.** Newest (today). The *sibling*
`FR_ISOLATION_TARGET` static-export fix already landed (#686/#689, closed out #690), but that
only covers the static value; the **BYOK `OPENAI_*` secrets remain dead** because sshd is PID 1
and clobbers `/proc/1/environ`, and secrets can't be hardcoded. Real, well-scoped bug with two
fix candidates in the body (frank-side `command` override dumping env to tmpfs, or an
agent-images-side tiny init). → **Schedule** (`fr-debugging`/`fr-plan`).

**#394 — No Metrics API on Frank.** Still valid: no `metrics-server` / prometheus-adapter under
`apps/` (only `victoria-metrics`), so `kubectl top` + CPU/mem HPA remain dead. Filed as a
brainstorming seed with a real design fork (standalone metrics-server vs VM-backed adapter). →
**Schedule `/brainstorming`** to make the scoping call, then plan if warranted.

### Orchestration experiments — re-verify + consolidate

**#475 — ruflo `hive-mind spawn --claude` fails** (claude-flow writes no `mcpServers`; CC
2.1.150 rejects). **#472 — ruflo-shell ANTHROPIC_* shim** for local-model workers, explicitly
*"blocked on [#475] launching at all."* Both 2026-06-04, untouched since; ruflo apps still
present. The specific version pins (claude-flow v3.10.37 × CC 2.1.150) are stale after repeated
agent-images bumps, so #475's schema-drift symptom **must be re-verified** on current versions
before either is worth pursuing. Low priority (competing-paradigms experiment). → **Re-verify
#475; consolidate the pair** into one tracked "ruflo local-model swarm" experiment (#472 as the
downstream half).

### Systemic — partly addressed, re-scope

**#581 — skill drift (repo skills not first-class).** The core symptom appears **resolved**:
in this very session the repo-local skills (`blog-post`, `update-readme`, `bump-image`,
`deploy-app`, `expose-service`, `falco-triage`, `media`, `oidc-onboard`, `papers`,
`sync-runbook`, `awx-onboard-hosts`, `hop-trace-analysis`, plus `frank-alert-triage`) **are
surfaced in the available-skills block as first-class invocable skills** — proposed fix #1
(surfacing parity) is effectively in place. Still open from the issue: **fix #3** (a single
`post-deploy`/`fix-extension` orchestrator *verb* chaining blog→readme→sync-runbook) and
**fix #4** (a cross-agent registration guard so drift can't silently recur). → **Re-scope** the
issue down to the residual actuation-verb + guard; drop the "skills invisible" framing.

---

## Consolidation (merge candidates)

1. **#160 + #161** — mutually-exclusive architectural options (sibling cgroup vs per-task Jobs)
   for the *same* vk-local scaling decision. Already cross-linked. Could collapse into one
   "vk-local scaling architecture — decide B2 vs B3 when a trigger trips" decision issue, keeping
   both sketches inline. Low urgency (both parked).
2. **#472 + #475** — same ruflo local-model-swarm experiment, hard dependency (#472 blocked by
   #475). Consolidate; pursue only if #475 re-verifies as still-broken-and-fixable.
3. **#597 + #599** — Omni-blocked siblings (599 self-declares "Sibling of #597"). Keep separate
   (different layers: cicd vs obs) but **schedule as one Omni-restored unblock batch**, sharing
   the "confirm Omni access is stable" preflight.

## Recommended dispositions (one-liners)

- CLOSE: **#477** (ai-alert-helper retired), **#162** (image/window gone, 8 Gi resolved it).
- UPDATE body: **#609** (8 done, 5 remain).
- SCHEDULE now: **#688** (BYOK bug), **#394** (brainstorm metrics API), **#597**/**#599**
  (Omni unblock batch), **#599.2** as a prioritised bug.
- RE-VERIFY then decide: **#475** (→ **#472**).
- RE-SCOPE: **#581** (surfacing done; actuation-verb + guard remain).
- KEEP PARKED/GATED: **#160**, **#161** (backlog), **#554** (GPU hand-back).
