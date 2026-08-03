# Hermes Agent Shell — retrieval-store sidecar (frank half)

**Spec:** `docs/superpowers/specs/2026-08-03--orch--hermes-retrieval-store-sidecar-design.md`
**Issue:** derio-net/frank#759
**Layer:** `orch` (15)

Adds a fourth container to the `hermes-agent-shell` pod: a stock
PostgreSQL 18 + pgvector store on loopback, with its own Longhorn volume.
Hindsight's container, image, env and 5 Gi PVC are untouched.

The sibling half — Bun in the `hermes-agent-shell-ssh` image — lives in
`derio-net/agent-images` under its own plan. See the spec's Sequencing
section: the two are independent to write and to merge, and meet only at
the image pin, which is back-loaded here into phase 4.

## What is already proven, and what is not

The design was gated locally before this plan was written: stock
`pgvector/pgvector:0.8.6-pg18` was run under this pod's exact posture
(`--user 1000:1000`, `--cap-drop ALL`, volume root `root:1000 0775`,
`PGDATA` a subdirectory, `trust`, `-c listen_addresses=127.0.0.1 -c
port=5434`, an initdb.d script). It initialised, created the extension,
built an `hnsw` index, honoured both `-c` overrides, and survived a
restart on a populated volume.

That is evidence for the **design**, not for the **deployment**. It ran on
a laptop with a Docker volume, not on Longhorn under a kubelet that
re-walks `fsGroup`. Every acceptance row therefore stays
`not-implemented` until phase 4 produces live output. Do not let the gate
tempt you into closing them early.

Two findings from the gate are load-bearing in the phases below:

1. **`PGDATA` must be a subdirectory of the mount.** The entrypoint
   creating that directory is what makes it uid-1000-owned and `0700`.
   The mount root has already been widened to `0775` by `fsGroup`, and
   Postgres refuses a data directory wider than `0750`. Phase 2 guards the
   relationship, not the literal path.
2. **The `-k /tmp` socket flag the Hindsight image carries is not needed.**
   The official image ships `/var/run/postgresql` at mode `3777` for
   exactly this arbitrary-uid case.

## Why phase 2 exists at all

Phase 1 alone would pass review and pass CI. Every one of the four failures
phase 2 guards is invisible in a diff and green in a suite:

- a `PGDATA` at the mount root fails only against a real `fsGroup` re-walk;
- an `httpGet` probe against a loopback-only server is refused forever —
  the `hindsight` container above cost 37 restarts learning this;
- a future edit reviving the withdrawn 5 Gi → 10 Gi Hindsight expansion
  would contradict the entire premise of the revised issue while touching
  one number;
- and an exemption whose recorded reason no longer describes what it
  exempts is how a guard quietly stops guarding.

Each guard in phase 2 is **mutation-checked**: doctor the manifest, confirm
the test fails, restore, and journal the result. This repo has already been
bitten by guards that passed against their own doctored input — a
seed-source check that matched its explanatory comment, a "must not push"
check that passed for `!=`, `==` and `true`, and a capacity tripwire that
walked only dict keys. An unmutated guard is a claim, not a check.

## Rollout honesty

Merging this recreates the pod. `strategy: Recreate` is not a choice here —
every volume is RWO and cannot double-mount — so Hindsight bounces and live
tmux/SSH/mosh sessions drop when ArgoCD syncs. The issue's "no restart
required by this work" means no volume *detach*, which is the risky,
schedulable operation the revision avoids. It does not mean no restart, and
the documentation added in phase 3 says so plainly.
