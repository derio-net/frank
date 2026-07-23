# agent-images Sweep — Frank-side verification and docs

Spec: `docs/superpowers/specs/2026-07-23--agents--agent-images-upstream-version-sweep-design.md`
Paired plan: `derio-net/agent-images:docs/superpowers/plans/2026-07-23--agents--agent-images-version-sweep`

## Why this plan is small

Frank needs **no manual pin edit**. `agent-images` `repository_dispatch`es on main push, and
`.github/workflows/agent-images-bump.yml` opens the bump PR here, rewriting every
`ghcr.io/derio-net/<img>:<sha>` under `apps/` and failing loudly on any image missing from
`AGENT_IMAGES`. That path is already proven — Frank is currently pinned at `a59f499`, exactly
`agent-images` main HEAD, so there is no frank-side drift to fix. All drift in this sweep is
upstream-of-the-image.

What Frank owns is therefore the two things the other repo cannot do: **write down what the sweep
taught** (Phase 1), and **prove the rebuilt images actually work in the cluster** (Phase 2).

## Phase 1 is not busywork

Four findings from the sweep are the kind that cost a future session hours if unrecorded, and none
of them are discoverable from the code:

- **`talosctl` must track the cluster, not "latest".** The shells sat three minors behind the
  cluster with no alert and no symptom until a command needed the newer API. The naive fix —
  "bump it to latest" — re-creates the same drift in the opposite direction.
- **agent-images CI never runs on `pull_request`**, and its `push` trigger is restricted to `main`.
  So a bump PR there is green-looking and entirely unbuilt. Anyone who merges one on the strength
  of a green checkmark is merging blind.
- **A Hermes bump can ship in the image while the pod serves the old venv**, because the venv is
  PVC-resident behind a `.seed-version` marker. The image is not the evidence; the pod is.
- **GitHub's compare API caps `.files[]` at 300 entries**, so a `grep` over a large range reports a
  confident false "nothing changed here". Measuring the ruflo drift properly — tree SHAs, then blob
  SHAs, at the subtree actually built — turned "607 commits behind" into exactly one changed file.

Phase 1 also corrects a claim this sweep disproved: the runbook records the ruvocal GridFS fix as
upstreamed, but `ruvnet/ruflo#2293` is **open, not merged**, and upstream HEAD carries none of it.
Left uncorrected, someone eventually drops a still-required local patch.

## Phase 2 is manual by necessity, not by preference

It cannot run until the agent-images build has published *and* the automatic bump PR has merged
here — cross-repo sequencing this plan cannot drive. It is back-loaded so no agentic work waits on
it, and it carries every acceptance row in the spec, because in this repo's terms a layer is not
done when ArgoCD says Synced; it is done when the thing has been observed working.

The verification is deliberately per-surface rather than a single smoke check: the sweep's waves
have different failure modes (s6 stops containers booting, Hermes degrades quietly, ruflo breaks
file I/O specifically, supercronic breaks a cron nobody watches), so one green pod proves very
little about the others.
