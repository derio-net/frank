# Least-Privilege Run Credentials — Design (Seed)

**Status:** Seed (pre-design — captures a brainstorm, not yet a resolved spec)
**Layer:** agents (12 — Agentic Control Plane)
**Date:** 2026-06-11
**Repos touched (anticipated):** `frank` (broker, RBAC, ArgoCD wiring), `super-fr` (policy
layer in runner/dispatch), `agent-images` (per-principal injection), possibly `runs-fr`
**Builds on:** [`2026-06-07--agents--k8s-native-runs-design.md`](./2026-06-07--agents--k8s-native-runs-design.md)
— this is one of the "full capability composition / privilege" follow-ups that spec defers
(its non-goals; §155 "Component A must explicitly revisit the layering / privilege"; §195
"broad RBAC is justified by being a single trusted tenant" — that justification is what this
spec is meant to retire).

> **This is a seed.** It records decisions made in conversation and the open questions, so the
> thinking survives between sessions. It is intentionally under-specified — it will bloom into
> a multi-repo design. Do not treat the structure below as settled.

## Why this exists

The k8s-native-runs substrate makes the **unit of isolation a pod**. It gives each run a
`credsRef` and a `capabilitiesRef`, but in the walking skeleton the run pod is a *single
trusted tenant with broad RBAC* and one harness credential. That is fine to prove the seam;
it is not the target.

The target is the operator's stated end state: a dispatch agent writes GitHub Issues, and the
**correct agents receive the correct one-use credentials — and only those** — to do their
task, returning documented multi-repo PRs. The standing secure-agent-pod that holds the
cluster keys today is retired as a consequence: once credentials are minted per-task and
scoped, nothing needs to sit holding the crown jewels. **The offboarding plan and the
safe-agentic-dev plan are the same plan, seen from two ends.**

## The core idea

**A run's credential profile is a function of `(phase, role, lifecycle-stage)` — not just the
target repo.** A deterministic, testable **policy layer** maps task metadata (the Issue, its
labels, target repos, plan phase, role) to a **credential scope**. A **broker** mints
short-TTL, narrowly-scoped, one-use credentials against that scope. The LLM never sits in the
privilege-granting path — it proposes work; a deterministic control plane grants privilege.

Principals identified so far (each a distinct minted identity, distinct scope):

- **Developing agent** — read its scoped repos, write a branch, open a PR. No cluster, no deploy.
- **Merge / post-merge agent** — wakes *after* the PR merges; may need cluster/ArgoCD reach
  (watch/trigger a rollout) the developer never had. A different principal entirely,
  deploy-adjacent. (The substrate spec already observes the merge event — §172 — but assumes
  the same tenant; this splits it.)
- **Per-phase agents** — phase A and phase B of one plan may touch different repos / need a
  registry push / etc. Different rows in the same policy mapping.
- **Dispatch / control plane (likely Willikins)** — proposes Issues, triggers runners. Holds
  **no task credentials and no mint authority**. See the trap below.

## Decisions already made (2026-06-11)

1. **Policy layer is deterministic and testable.** No LLM in the grant decision. This is what
   makes everything below — especially the autonomy gate — possible.
2. **Human-gated mint first, measured autonomy later.** Not a vibe-based "feels ready." During
   human-gated operation, log every case where the human-approved grant matched what the
   policy *would have* auto-granted; autonomy ships on N real tasks with **zero divergences**
   against an Issue-fixture → expected-scope test corpus. (Quantitative gate before the
   architectural shift.)
3. **Pods over containers** for the runtime boundary — RBAC, NetworkPolicy egress lock,
   resource limits, literal ephemerality. (Inherited from the substrate spec.)
4. **PR is the only output.** Agent branches never auto-merge into anything with deploy
   authority; review is the gate. A compromised task-agent's blast radius ends at "wrote a PR
   nobody approved."
5. **Cluster creds are never the omniconfig/talosconfig.** Short-lived SA tokens
   (TokenRequest, audience + expiry) with tight RBAC, generalizing the existing in-cluster-SA
   principle.
6. **VK bridge and the secure-pod dev-box are retired when their replacement is *proven*, not
   on a schedule.** Prove the runner alongside VK; retire VK once reliable.

## The trap to name explicitly

Willikins is a standing LLM agent that coordinates and delegates — the natural dispatch/control
plane. The failure mode: the convenient standing agent quietly accretes the same broad
credentials the dev-box has today, and the problem is rebuilt with extra steps. **The control
plane must hold no task credentials and no mint authority** — only "create Issue" and "spawn
runner" rights. This must be a design invariant, not an afterthought.

## Components (sketch — not settled)

- **Broker** — mints short-TTL scoped secrets per principal per task. Candidates: Infisical
  dynamic secrets / OpenBao / Vault. Becomes the new trust root; mints from *task metadata*,
  never from agent request. Must not be reachable by a task-agent with enough authority to
  self-escalate.
- **GitHub App** (not PATs) — installation tokens scope to specific repos + permissions at
  mint time, ~1h TTL. The natural fit for scoped multi-repo PRs and the piece not yet built.
- **Policy layer** — deterministic mapping `(issue/labels/repos/phase/role) → cred scope`,
  CI-tested against fixtures. Lives in `super-fr` (runner/dispatch side).
- **Egress policy** — per-run NetworkPolicy: GitHub + broker + needed registry, nothing else.

## Rough dependency order

1. Broker + deterministic policy layer (trust root), human-gated mint.
2. GitHub App — scoped multi-repo installation tokens.
3. Per-task runner pod — ephemeral, scoped token, NetworkPolicy egress lock, PR-only output.
   (Substrate from k8s-native-runs.)
4. Prove runner against real tasks *alongside* VK → once reliable, retire VK bridge.
5. Decompose secure-pod tenants: crons → CronJobs, Willikins → control-plane pod (no task
   creds), Telegram bots → own pods/crons.
6. Dev-box has no tenants → retire; cluster keys never return to it.

Steps 1–3 are the real build; 4–6 are migration that falls out once the substrate works. The
ordering trap: don't retire VK or the dev-box on a calendar — retire on *proven replacement*.

## Open questions

- **Merge-agent trigger & scope** — what exactly does a post-merge ArgoCD-rollout agent need,
  and how is that scope derived from the merged PR's metadata? Is the merge agent a fixed
  principal or per-plan?
- **Phase-scope granularity** — does the policy read scope from the plan file's phase table,
  from Issue labels, or both? Where is the source of truth?
- **Broker choice** — Infisical (already in play) dynamic secrets vs. OpenBao/Vault. What can
  actually mint scoped GitHub-App tokens + short-lived k8s SA tokens cleanly?
- **Control-plane identity** — is Willikins literally the dispatch layer, or a separate minimal
  non-LLM dispatcher that Willikins drives? (The invariant holds either way; the topology doesn't.)
- **Autonomy corpus** — what's N? What counts as a "divergence"? How is the shadow-grant logged
  during human-gated operation?
- **Dev-box decomposition order** — which tenant moves first without breaking the others
  (Willikins persistent session, VK bridge, crons, Telegram bots)?
- **Transcript redaction** — a harness transcript can leak a minted credential (already flagged
  as a risk in the substrate spec); one-use + short-TTL reduces but does not eliminate this.

## Relation to dev-box offboarding

"Retire the secure-agent-pod" is **decomposing a bundle**, not one move. Its tenants each get a
home and a privilege profile; the pod retires when it has no tenants left. This spec covers the
agent-runtime tenant (the hardest one). The crons, bots, and the Willikins persistent session
are separate migration tracks that this design's invariants (no standing broad creds, scoped
per principal) should govern.
