---
title: "Operating the Hermes Shell With Its Hindsight Memory Sidecar"
series: [operating]
layer: agents
date: 2026-07-11
draft: true
tags: [operations, hermes, nous-research, agents, litellm, hindsight, sidecar, postgres,
  pgvector, memory, ssh, troubleshooting]
summary: "Day-to-day commands for the rebuilt hermes pod on the official image: checking the Hindsight memory sidecar's health, the two-tier memory backup story, the claude-code retain provider and its auth caveat, and the pg_dump/pg_restore restore mechanic. Includes troubleshooting for retain-vs-recall split-brain, Postgres permission flips, and probe misconfiguration."
reader_goal: "Check Hindsight memory sidecar health, verify the two-tier backup story (Longhorn + pg_dump), and troubleshoot retain-vs-recall split-brain when Claude session auth lapses."
diataxis: [how-to, reference]
last_updated: 2026-07-15
last_updated_commit: https://github.com/derio-net/frank/commit/a8bed9a1d358b7ad87bb6dcaa9b0162e5fb0e127
weight: 29
---
{{< last-updated >}}

Companion to [Rebuilding the Hermes Shell on the Official Image, With a Hindsight
Memory Sidecar]({{< relref "/docs/building/33-hermes-shell" >}}). Everything here
assumes the Frank kubeconfig (`source .env` from the repo root, and mind the
[relative-path trap]({{< relref "/docs/operating/01-cluster-nodes" >}})).

The pod is now **three containers**: `hermes` (the bare official image), `ssh` (the
SSH/Mosh sidecar), and `hindsight` (the self-hosted memory backend). Most of what
changed since the original operating guide is that memory is a real, supervised
container instead of a hand-run tmux stack, so that is where this guide spends its
words. The BYOK inference surface (provider pinning, `ollama_chat/`, context
budgets) is unchanged; the [building post's history]({{< relref "/docs/building/33-hermes-shell" >}})
still owns that chain.

```bash
source .env   # sets KUBECONFIG
```


## What "Healthy" Looks Like

```bash
kubectl -n hermes-agent-shell get pods,svc,pvc
```

- One pod `Running` on **gpu-1**, all three containers Ready
- The SSH/Mosh Service holding **192.168.55.226** (TCP 22 + UDP 60032-60047)
- The PVCs `Bound`, including the isolated Hindsight data volume
  (`hermes-agent-shell-hindsight`) alongside the agent's data/home/repos volumes

Pod status is not the health check. As with the original build, the surface can be
green while the real path is broken. The memory backend has its own liveness door,
and it is loopback-only by design:

```bash
kubectl exec -n hermes-agent-shell -c hindsight deploy/hermes-agent-shell -- \
  curl -sf http://127.0.0.1:8888/health
#   → {"status":"healthy","database":"connected"}
```

Run it against the `hindsight` container specifically (`-c hindsight`). The
kubelet's own probes are `exec` probes that do exactly this from inside the
container, because `hindsight-api` binds `127.0.0.1` only and a pod-IP `httpGet`
probe draws connection-refused forever (the build post's failure five).

From the agent's side, `hermes` sees the same backend over loopback:

```bash
kubectl exec -n hermes-agent-shell -c hermes deploy/hermes-agent-shell -- \
  bash -lc 'hermes memory status'
```

This should report the Hindsight backend reachable and the bank populated; it is
the agent-facing view of the same `/health` the sidecar answers.

### Verify

Confirm the hindsight memory sidecar is healthy and accessible:

```bash
# Hindsight health endpoint
kubectl exec -n hermes-agent-shell -c hindsight deploy/hermes-agent-shell -- \
  curl -sf http://127.0.0.1:8888/health

# Memory count from Postgres
kubectl exec -n hermes-agent-shell -c hindsight deploy/hermes-agent-shell -- \
  psql -h 127.0.0.1 -p 5433 -U hindsight -d postgres -tAc 'select count(*) from memory_units'
```

Expected: `{"status":"healthy","database":"connected"}` and a count > 0.


## Checking the Memory Store Directly

Recall count, straight from Postgres, is the ground truth. 369 `memory_units`
survived the migration, so that number is the canary:

```bash
kubectl exec -n hermes-agent-shell -c hindsight deploy/hermes-agent-shell -- \
  psql -h 127.0.0.1 -p 5433 -U hindsight -d postgres \
  -tAc 'select count(*) from memory_units'
#   → 369
```

Two connection details worth pinning, because they are not the Postgres defaults:
the port is **5433** (not 5432, so nothing collides with a default expectation),
and the database is **`postgres`**, owned by role **`hindsight`** (the table lives
in the `postgres` database, not in a database named `hindsight`). Loopback auth is
trust, so no password is needed from inside the container.

## The Memory Backup Story

This is the part that got materially better in the migration, and it is worth being
explicit about, because "where is the memory backed up" used to have an
uncomfortable answer.

**Tier one: Longhorn recurring backups.** Because the Hindsight data now lives on
its own isolated PVC, that volume auto-joined Longhorn's existing recurring-backup
group. Nothing was configured specially; isolating the volume is what enrolled it.
The previously-unbacked-memory gap closed as a side effect of the architecture.

**Tier two: a portable logical dump.** Longhorn snapshots are volume-level and
cluster-bound. For a portable, restorable-anywhere copy, take a logical dump:

```bash
kubectl exec -n hermes-agent-shell -c hindsight deploy/hermes-agent-shell -- \
  pg_dump -h 127.0.0.1 -p 5433 -U hindsight -Fc postgres > hindsight-$(date +%F).dump
```

The two tiers answer different questions. Longhorn answers "the volume died";
`pg_dump` answers "I need this memory on a different cluster, a different Postgres,
or my laptop."

## The Retain Provider and Its One Caveat

Writing new memories (retain) uses the **`claude-code`** provider: Sonnet 4.5
(`claude-sonnet-4-5-20250929`, the provider's built-in default), through a baked
`claude` CLI and the `claude-agent-sdk` inside the `hindsight` sidecar. Auto-retain
fires roughly every ten turns.

The caveat that will bite someone: **retain only fires if an authenticated Claude
session is present in the sidecar.** The `claude-code` provider authenticates
through the Claude Agent SDK (a logged-in `claude` session), not through an
`ANTHROPIC_API_KEY` env var, so wiring a key into the manifest does nothing for it.
If no session is authenticated, new memories are not written, and the failure is
quiet. Recall is unaffected: it uses the local `BAAI/bge-small-en-v1.5` embeddings
and needs no LLM at all, so the pod keeps reading its memory back perfectly while
silently not writing new memories in.

So "memory works" splits into two questions with two different answers. Recall
working is cheap to verify (the psql count, a recall query). Retain working
requires that the sidecar's Claude session is live, and there is a trap here:

```bash
# proves the BINARY exists, NOT that a session is authenticated:
kubectl exec -n hermes-agent-shell -c hindsight deploy/hermes-agent-shell -- \
  claude --version
```

`claude --version` tells you the CLI is installed, which is not the same as a
logged-in session. Durable retain-auth across restarts is an open item (see the
building post's "What's Next"); until it is settled, treat retain as best-effort and
recall as the guarantee, and if new memories stop appearing, suspect the session
before anything else.

## Restore / Migration Mechanic

To pull memory out of an old PostgreSQL (the migration case, or a recovery from a
`pg_dump`), the shape is:

1. `chmod 700` the old data directory first, then stand the old Postgres up on a
   spare loopback port (the same `fsGroup` widening from the build post's failure
   four applies to any data directory Kubernetes has remounted).
2. `pg_dump -Fc` the old database.
3. `pg_restore` into the sidecar's Postgres over loopback (`127.0.0.1:5433`). The
   sidecar's `initdb` has already auto-created an empty schema via Alembic, so
   restore with `--clean --if-exists` to overwrite it cleanly rather than collide
   with it.
4. Restart the pod and re-count `memory_units` to prove continuity.

```bash
# on the OLD data dir, before starting it (Postgres refuses a group-readable dir):
chmod 700 "$OLD_PGDATA"
# then: start old PG on a spare port → pg_dump -Fc → pg_restore --clean --if-exists
#       into 127.0.0.1:5433 → restart pod → recall count should return 369
```

The full end-to-end of this (how the old PG is stood up, exact flags, cleanup) is
in `docs/runbooks/frank-gotchas/agent-shells.md`; the sketch above is the shape,
not the paste-at-2am procedure.

## Connecting

SSH and Mosh are unchanged from the original operating guide, served by the `ssh`
sidecar on **192.168.55.226**:

```bash
ssh agent@192.168.55.226

mosh --ssh="ssh agent@192.168.55.226" \
     --server="mosh-server new -p 60032:60047" 192.168.55.226
```

Scripted access still wants `kubectl exec ... -c <container> -- bash -lc '<cmd>'`
rather than `ssh host -- cmd` (non-interactive SSH skips the profile.d BYOK shim);
name the container explicitly now that the pod has three.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `hermes` container CrashLoops on start | Missing `args: ["gateway","run"]`: the bare entrypoint runs an interactive TUI | Ensure the manifest sets the gateway args |
| Migration/start "hangs" with no error | Restored data directory is root-owned; breaks the CLI privilege-drop shim | `chown -R hermes:hermes /opt/data` |
| `hindsight` CrashLoops after a restart (worked on first boot) | `fsGroup: 1000` re-loosened PGDATA to group-rwx on remount; Postgres refuses wider than 0750 | `chmod 700 $PGDATA` on every boot (baked into the sidecar's start) |
| Pod flaps / many restarts, but `/health` is 200 on loopback | Probe was `httpGet` on the pod IP; `hindsight-api` binds 127.0.0.1 only | `exec` probes that curl loopback, plus a `startupProbe` for the cold start |
| Recall works, new memories never appear | Retain's `claude-code` provider has no authenticated Claude session in the sidecar | Authenticate the sidecar's Claude session; recall is unaffected |
| Embedding model fails to load though files are present | Revision-pinned `snapshot_download` wrote no `refs/main` | Bake to a fixed `local_dir` and load by path, not by `main` revision |
| `memory_units` count is 0 / unexpected after restore | pg_restore target wrong, or continuity check off | Re-run the restore mechanic (`-d postgres`, port 5433); count should return 369 |

## What's Retired

- **The relocatable venv-on-PVC seed ([#496])**: gone. The official image is the
  source of truth; there is no baked-`root:root` venv to relocate.
- **The venv-on-PVC seed cont-init and the auto-continue patch**: gone. Tracking
  upstream means running upstream's venv and behaviour, not maintained edits.
- **The custom-image maintenance**: gone. `hermes` is the bare official image plus
  `args`. The only image still owned here is the Hindsight backend, which exists
  because upstream ships the client and not the server.
- **The hand-run tmux memory stack**: gone. Memory is a supervised container on a
  backed-up volume.


## Missteps

The layer's design took a few wrong turns before it settled. These are the ones worth remembering so the next operator doesn't repeat them.

| What we assumed | Why it was wrong | What it cost |
|---|---|---|
| Retain works automatically as long as the hindsight sidecar is running | The claude-code provider needs an authenticated Claude session in the sidecar — no ANTHROPIC_API_KEY env var works; without a logged-in session, new memories are silently not written | Periods where recall worked perfectly but no new memories were retained, going unnoticed until a spot-check of memory_units count |
| PostgreSQL data directory permissions survive Kubernetes pod restarts | fsGroup: 1000 re-loosens PGDATA to group-rwx on every remount; Postgres refuses group-writable directories | Hindsight container crash on every restart until chmod 700 was baked into the sidecar's startup |
| A httpGet probe against the pod IP works for the hindsight health endpoint | hindsight-api binds 127.0.0.1 only — a pod-IP httpGet probe draws connection-refused forever, causing the kubelet to restart the container | Pod flapping with false-negative health checks until exec probes curling loopback replaced httpGet |
| claude --version reliably indicates retain capability | The binary exists but needs a logged-in OAuth session; --version tells you it's installed, not authenticated — the failure path is completely silent | Troubleshooting 'why no new memories' required digging into the sidecar's session state rather than a simple version check |

## References

- [Building post]({{< relref "/docs/building/33-hermes-shell" >}}): the rebuild narrative and the five on-cluster failures
- [willikins#285](https://github.com/derio-net/willikins/issues/285): the official-image migration and Hindsight sidecar
- [agent-images repo](https://github.com/derio-net/agent-images): the `hermes-agent-shell-hindsight` backend image
- `docs/runbooks/frank-gotchas/agent-shells.md`: memory sidecar operations, retain-auth, and the restore mechanic
- [Operating on Local Inference]({{< relref "/docs/operating/07-inference" >}}): LiteLLM gateway operations
- [LiteLLM Ollama provider docs](https://docs.litellm.ai/docs/providers/ollama): the BYOK inference path, unchanged

[#496]: https://github.com/derio-net/frank/issues/496
