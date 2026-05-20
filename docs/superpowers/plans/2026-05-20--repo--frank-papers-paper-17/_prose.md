# The Frank Papers — Paper 17: Agentic Orchestration & Safe Agent Workstations

**Spec:** `docs/superpowers/specs/2026-04-15--repo--frank-papers-series-design.md`
**Status:** In progress (2026-05-20) — Paper 17 drafting on branch `paper-17`.

**Prerequisite:** `2026-05-16--repo--frank-papers-phase-0` complete (scripts,
shortcodes, dossier gate, `agents/skills/papers/SKILL.md`). Papers 00, 10, 04,
11, 14, 06, 07, 02 published.

Paper 17 is the next capability Paper to land in the series: 2400–4200
words, the standard skeleton (§1 capability → §2 landscape → §3 architecture
per vendor → §4 scale → §5 Frank's choice → §6 generalization → §7 roadmap),
the orchestrator-Paper companion to the agent shells Frank now runs in
production. The question is not *can an agent run code* (every shell does
that), it is *where does it run, with what blast radius, and who watches it
when it strays?*

The capability question is: *if you want to run other people's (or your
own) coding agents — Claude, Codex, opencode, hermes — on real
infrastructure, with real network access and real source-checkout
privileges, what runs them, what isolates them, and who orchestrates the
fleet?* The vendor space splits along two axes: workstation isolation
model (laptop devcontainer vs cloud VM vs per-PV pod vs vCluster) and
orchestration model (single-shell-per-human vs ticket-bridge-fanout vs
managed cloud IDE). Six candidates make the landscape, with **secure-
agent-pod + VibeKanban + Paperclip + Sympozium** as Frank's case
study — a four-layer composition Frank discovered by deploying each layer
in isolation and watching how they interact (often badly) at the seams.

The scars are the point. The s6-overlay v3 PID-1 fight with
`shareProcessNamespace: true` that left a pod silently broken. The
30-second MCP RPC timeout on the vk-issue-bridge that cascades into
zombie execution_processes in the vk-local database, stuck `status='running'`
forever, with the UI lying to you about workspace state. The `vk-local`
4Gi cgroup limit that drifted past 8Gi under sustained bridge feeding —
because `VK_MAX_CONCURRENT_EXECUTIONS=4` does not bound the cgroup, only
image-side resource reservations do. The `cont-init.d/30-authorized-keys`
boot-only behaviour that copies (not symlinks) SSH keys, so rotating a
SOPS-managed key requires a pod restart. The Paperclip "Test environment"
running in the *app* container, NOT the *shell* sidecar — so agent-CLIs
installed via the shell PVC are invisible at runtime unless the shared
volume bridge is wired through. These aren't decorations on the §5
narrative — they're why the §6 decision tree has the leaves it does.

## Phase 1: Dossier construction

Six vendors, ≥5 primary sources across ≥3 type values, ≥3 Frank artefacts
across ≥2 kinds, the named gap on the absence of an apples-to-apples
"agent-workstation safety tax" benchmark (per-agent CPU/RAM overhead,
network egress per agent-hour, supervisor blast-radius probability,
debugging time on long-tail s6 / cgroup / PID-namespace failures), and
the counter-argument that for a solo dev with one agent and a laptop,
a plain devcontainer is the rational choice and per-PV pod isolation is
overkill. Parallel subagents per vendor are appropriate — one each for
secure-agent-pod, VibeKanban, Paperclip+Sympozium, Coder.com, GitPod, and
plain devcontainers/Codespaces — with a merger pass.

## Phase 2: Gate validation

Run `validate-dossier.py`. Human gate: author reviews the named gap and
the counter-argument. The counter to nail: *"for a solo dev running one
Claude session in a devcontainer, why does the per-PV pod, sshd, mosh,
s6-overlay setup ever pay back?"* Same shape as Paper 04's framing applied
to the agent-workstation capability.

## Phase 3: Scaffold + draft

Standard capability-paper skeleton. Section order is fixed:

- TL;DR (≤150 words) — write last
- §1 The capability (200–350 words) + `flowchart LR` stack-position diagram
- §2 The landscape (400–600 words) + `{{< papers/landscape >}}` + `{{< papers/capability-matrix >}}` reading from `data/vendors.yaml`
- §3 How each option handles the hard part (800–1400 words) + one `flowchart TD` per vendor with shared visual language
- §4 What scale changes (300–600 words) + benchmark callouts (per-agent RAM floor, network egress per agent-hour, supervisor overhead at N pods)
- §5 Frank's choice, and what happened (300–600 words) + 1–3 `{{< papers/scar >}}` callouts (vk-issue-bridge 30s timeout zombies, shareProcessNamespace+s6 PID-1 fight, vk-local 4Gi-doesn't-bound-cgroup)
- §6 When Frank's answer doesn't generalize (200–400 words) + decision flowchart, ≤4 leaves
- §7 Roadmap & where this space is going (200–400 words)
- §8 References — auto-rendered from frontmatter

## Phase 4: Media fill

Per-paper cover: Frank surveying a fleet of identical safe agent
workstations (each a glowing terminal podlet on a rack panel), with one
workstation in the row visibly dimmed (the per-PV scar). Weighing
expression, thin black tie, round reading glasses. Mermaid diagrams: §1
stack position, §2 landscape (quadrantChart) + capability matrix, §3
four-to-six architecture flowcharts, §6 decision tree. Optional VK board
or Sympozium-fleet screenshot captured live from the cluster.
Cluster-side captures may be deferred with `-TODO.png` placeholders.

## Phase 5: Review + publish

Voice pass (Frank speaks as the cluster — first-person plural or third-
person cluster, not academic). TL;DR ≤150 words written last. Dossier-link
rendering check (use either inline shortcode OR rely on automatic injection
— not both). Set `draft: false`, `status: published`. CI deploys via the
existing blog pipeline.

## Phase 6: Post-deploy checklist

Standard checklist for a published Paper: update `_index.md`, verify the
auto-rendered cross-link chips appear on Building 21-secure-agent-pod
and Operating 14-secure-agent-pod, update README if relevant, set
plan status to Complete.

## Phase summary

| # | Phase | Depends on |
|---|-------|-----------|
| 1 | Dossier construction | — |
| 2 | Gate validation | 1 |
| 3 | Scaffold + draft | 2 |
| 4 | Media fill | 3 |
| 5 | Review + publish | 4 |
| 6 | Post-deploy checklist | 5 |
