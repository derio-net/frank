---
title: "Rebuilding the Hermes Shell on the Official Image, With a Hindsight Memory Sidecar"
series: ["building"]
layer: agents
date: 2026-07-11
draft: true
tags: ["hermes", "nous-research", "agents", "ai", "litellm", "hindsight", "sidecar", "postgres", "pgvector", "memory", "ssh"]
summary: "Retiring the custom agent-shell image and rebuilding hermes on Nous Research's official hermes-agent image as a three-container pod: bare official image, an ssh sidecar, and a self-hosted Hindsight memory backend. Five more failures where every surface check passed while the real path stayed broken."
weight: 34
---

The [hermes shell]({{< relref "/docs/building/33-hermes-shell" >}}) that first
answered a question on 2026-06-06 was a great deal of scaffolding wrapped around a
small CLI. I ran it on my own `agent-shell-base` lineage, and to keep it working I
carried two patches the upstream image knew nothing about: a
relocatable-venv-on-PVC dance ([#496]) so I could write to a venv that shipped
baked `root:root`, and an auto-continue gate-widening patch so `qwen36-a3b` would
stop announcing work and then going quietly idle. Both were real fixes. Both were
mine to re-apply forever.

This post is about handing them back. Nous Research now publishes an official
`nousresearch/hermes-agent` image, and the honest move is to track it rather than
maintain a fork-by-Dockerfile. So the pod was rebuilt from the ground up on the
official image (v2026.7.7.2), the custom patches retired, and the one thing worth
keeping (the entire memory) carried across intact.

That last clause is where most of the work went, and it handed me five more
failures of exactly the kind the original post was about. Each one passed its
surface check (pod Healthy, build green, `/health` fine on loopback) while the
actual path was broken. Two of them were invisible to local Docker and only
catchable on-cluster. They are the spine of this post.

## What This Layer Ships Now

```
nousresearch/hermes-agent:v2026.7.7.2       ← bare official image (main container)
hermes-agent-shell (agent-images)           ← ssh sidecar
hermes-agent-shell-hindsight (agent-images) ← NEW: self-hosted Hindsight backend
```

One pod on **gpu-1**, three containers sharing a single network namespace:

- **`hermes`** runs the bare official image, no build layer on top. It needs
  `args: ["gateway", "run"]`: the bare entrypoint launches an interactive TUI,
  which in a TTY-less pod exits instantly and CrashLoops. It runs as root with
  `HERMES_UID`/`HERMES_GID=1000`, which makes the image's own s6 init drop the
  gateway worker to uid 1000 while leaving the supervisor as root. Root to init,
  1000 to work. (Hold that split. It becomes failure one.)
- **`ssh`** is the thin sidecar from the [agent-images]({{< relref "/docs/building/28-agent-images-sidecar" >}})
  batch, giving the pod its SSH/Mosh front door without baking sshd into the
  official image. It keeps the strict non-root posture the shell family always
  used.
- **`hindsight`** is new, and it is the centerpiece: the Hindsight memory
  *backend*, self-hosted, Kubernetes-supervised, on its own Longhorn volume.

The BYOK wiring to Frank's in-cluster LiteLLM gateway is unchanged from the
original build, so the three-act inference chain from that post (provider pinning,
`ollama_chat/`, honest context budgets) still holds. This post does not relitigate
it.

## Why Memory Needs a Sidecar at All

The official image ships the Hindsight *client*, not the backend. Hermes can talk
to a Hindsight server, but nothing in the image *is* one: `hermes gateway run`
spawns no Postgres, no API. The old pod had been getting away with a hand-run tmux
stack for this, which is precisely the sort of arrangement that survives right up
until the day it doesn't, and takes the memory with it when it goes.

So the backend becomes a real container that Kubernetes supervises like everything
else. I baked a new agent-images image, `hermes-agent-shell-hindsight` (tag
`28de3ab`): a micromamba environment carrying PostgreSQL 18.4, pgvector 0.8.3,
`hindsight-api-slim[local-ml]==0.8.4`, and the `BAAI/bge-small-en-v1.5` embedding
model on torch-CPU, all baked into the image. Hermes reaches it in `local_external`
mode over the shared pod network namespace at `127.0.0.1:8888`, its client config
unchanged from the old external-backend arrangement.

The whole software stack lives in the image; only *data* lives on the PVC
(`PGDATA=/opt/hindsight/pgdata`, its own Longhorn volume, mounted into the sidecar
alone). That split earns two things. First, the sidecar runs strict non-root:
Postgres `initdb` as uid 1000 is perfectly legal, unlike the root-bound main
container beside it. Second, the free win: because memory now sits on its own
isolated volume instead of tangled into the agent's home PVC, it auto-joined
Longhorn's existing recurring-backup group the moment it got that volume. A
previously-unbacked-memory gap closed itself as a side effect of the architecture.
I did not plan that. I will take it.

Retain (writing new memories) uses the `claude-code` provider, Sonnet 4.5, through
a baked `claude` CLI and the `claude-agent-sdk`. Recall works with no LLM at all,
and that asymmetry is the important one: the pod can always read its memory back,
even when nothing is authenticated to write new memory in.

## Failure One: The Migration That Looked Stuck Was a `chown`

Restore the old data, start the pod, watch it do nothing. No crash, no error, no
progress: the kind of hang that invites you to add logging in six places before
you look at the boring thing.

The restored `/opt/data` came back **root-owned**. The official image's CLI runs a
privilege-drop shim on start, and a root-owned data directory broke it silently.
Not a crash: a stall, because nothing in that path was designed to complain about
it.

```bash
chown -R hermes:hermes /opt/data
```

That was the entire fix. The lesson is the one this series keeps relearning:
"nothing is happening" is a symptom, and file ownership is one of its most common
and most boring causes.

## Failure Two: The Sidecar That CrashLooped Because It Had No Home

The first cut of the Hindsight sidecar was built `FROM` the multi-agent-shell
image, on the tidy-sounding theory that reusing the base was the frugal choice. It
inherited the base's interactive-shell init scripts, and those scripts assume a
writable, *mounted* `$HOME`. A headless backend sidecar has no such mount. So when
`initdb` reached its `micromamba run` step, micromamba could not create its cache
lock under a `$HOME` that wasn't there, the init chain aborted, s6 called it fatal,
and the container CrashLooped before Postgres ever existed. Every surface said
"image builds, container starts"; the container just refused to stay started.

The fix was to stop pretending a backend is a shell. Strip the inherited init
scripts down to the three that belong (initdb, Postgres, hindsight-api), redirect
the micromamba cache to a writable in-image path instead of an absent `$HOME`, and
chown the home directory in the image. A backend sidecar is not a login
environment, and building one from a login environment imports assumptions that
quietly do not hold.

## Failure Three: The Embedding Model That Was Present But Unloadable

Bake the embedding model into the image so recall works fully offline. Every file
downloaded. `snapshot_download` reported success. Then, at load time, the loader
refused:

```
SentenceTransformer('BAAI/bge-small-en-v1.5')  →  cannot resolve revision 'main'
```

Every file was on disk and the model still would not load. The cause: a
revision-pinned `snapshot_download` writes the model files but does *not* write a
`refs/main` entry, and `SentenceTransformer`'s default `main` revision then has
nothing to resolve against. The presence of the files is not the same as the
presence of the pointer the loader looks for.

The fix is to sidestep revision resolution entirely: bake to a fixed `local_dir`
and load by path.

```python
snapshot_download("BAAI/bge-small-en-v1.5", local_dir="/opt/models/bge-small-en-v1.5")
# load by path, not by revision:
SentenceTransformer("/opt/models/bge-small-en-v1.5")
```

## Failure Four: The Restart CrashLoop That First Boot Hid

First boot: clean. Postgres came up, `initdb` ran, the pod went Healthy. Restart
the pod, and Postgres refused to start:

```
data directory "/opt/hindsight/pgdata" has group or world access
```

`fsGroup: 1000` did it. Kubernetes, under the default `fsGroupChangePolicy:
Always`, recursively re-applies group permissions to a mounted PVC on *every*
remount, which reopened PGDATA to group-rwx. Postgres refuses to start on any data
directory wider than 0750, on principle, and it is right to.

Why first boot worked and only a restart broke is worth stating plainly, because
that gap is the whole trap. On first boot, `fsGroup` ran across an *empty* volume,
and `initdb` then created PGDATA at a correct 0700 afterwards. On a restart,
`fsGroup` ran across the now-populated volume and re-loosened the very directory
`initdb` had locked down on the previous boot. The failure was structurally
invisible until the second start.

```bash
chmod 700 "$PGDATA"   # every boot, before Postgres starts
```

The same one-liner had to run against the old data directory before dumping it
during the restore, for exactly the same reason.

## Failure Five: The Endless Flap With a Perfectly Healthy App

Data restored, memory intact, and the pod would not stay up: 37 restarts and
climbing. Every diagnostic insisted the app was fine. `curl 127.0.0.1:8888/health`
from inside the container returned `{"status":"healthy","database":"connected"}`
all day long. The process was genuinely alive. Kubernetes killed it anyway, on a
loop.

The kubelet's `httpGet` probes hit the **pod IP**. `hindsight-api` binds
`127.0.0.1` only. So the probe drew connection-refused every single time, forever,
while the process it was probing sat there perfectly alive on loopback. The
liveness probe was knocking on a door the app had deliberately never opened.

The fix is to make the probe use the same door the app does: `exec` probes that
`curl` loopback from *inside* the container, plus a `startupProbe` to cover the
cold start (Postgres init and the offline embedder load) before liveness begins
firing.

```yaml
startupProbe:
  exec:
    command: ["sh", "-c", "curl -sf http://127.0.0.1:8888/health"]
  periodSeconds: 10
  failureThreshold: 30      # ~300s of headroom for the cold start
livenessProbe:
  exec:
    command: ["sh", "-c", "curl -sf http://127.0.0.1:8888/health"]
```

Failures four and five share a property the local-Docker workflow simply cannot
catch: `fsGroup` remount semantics and pod-IP probing are *Kubernetes* behaviours.
On a laptop the image builds green, the container runs, `/health` answers on
loopback, everything looks finished. Both bugs only exist once the pod is scheduled
on a real node with real volume mounts and a real kubelet watching it. The cluster
is the only test rig that reproduces them, which is a humbling thing for a cluster
to have to admit.

## Continuity: The 369 Memories Came Across

None of the above would matter if the memory did not survive. The pre-migration
backend held **369 `memory_units`**. Those were `pg_dump`ed out of the old
PostgreSQL and `pg_restore`d into the sidecar's fresh database, and then the real
test: delete the pod, let it restart, count again. `initdb` skipped on the
already-initialized PVC, and recall still returned **369**. Same memory, now on its
own supervised, backed-up volume.

## The Memory Architecture, Briefly

The Hindsight sidecar is one layer of a deliberately layered memory,
retrieval-first and lean:

1. **Built-in memory**: compact, stable preferences. Small, always loaded.
2. **Hindsight**: episodic and semantic recall, with auto-recall and auto-retain
   firing roughly every ten turns. This is the sidecar this post builds.
3. **Session DB**: raw transcripts, the unfiltered record.
4. **`hermes-brain` git mirror**: a versioned copy of the memory store.
5. **Obsidian**: distilled long-term notes, the human-curated top.

Each layer trades size for permanence in a different direction. Hindsight is the
one that had to become a real, supervised, backed-up container, because it is the
one doing active recall and retention on every session.

## What Got Retired

The point of the migration, restated at the end where it belongs:

- The **relocatable-venv-on-PVC seed** ([#496]) is gone. The official image is the
  source of truth; there is no baked-`root:root` venv left to work around.
- The **auto-continue gate patch** is gone as a maintained artifact. Tracking
  upstream means living with upstream's behaviour, not `git apply`ing a fix onto it
  forever.
- The **custom-image maintenance** as a whole is gone. `hermes` is now the bare
  official image plus three words of `args`, which is the smallest surface I can
  maintain.

What replaced them is one new image I *do* own (`hermes-agent-shell-hindsight`),
but it owns a thing upstream deliberately does not ship (the backend). That is the
honest place to draw the build-versus-adopt line: adopt the client, build only the
server nobody hands you.

## What's Next

The retain path depends on an authenticated `claude-code` session living inside the
sidecar; recall does not. Making that authentication durable across restarts is the
obvious next thread, and until it is settled, retain is best-effort while recall is
the load-bearing guarantee. The operating companion documents how to tell which of
the two is actually working on any given day.

## References

- [Nous Research hermes](https://github.com/NousResearch/hermes): now the official `nousresearch/hermes-agent` image
- [agent-images repo](https://github.com/derio-net/agent-images): new `hermes-agent-shell-hindsight` backend image; existing `hermes-agent-shell` ssh sidecar
- [willikins#285](https://github.com/derio-net/willikins/issues/285): the migration to the official image and the Hindsight sidecar
- [Building post 28: Agent Images and the VK-Local Sidecar]({{< relref "/docs/building/28-agent-images-sidecar" >}}): the sidecar pattern this reuses
- [Operating on Hermes Agent Shell]({{< relref "/docs/operating/28-hermes-shell" >}}): the companion day-to-day guide
- [LiteLLM Ollama provider docs](https://docs.litellm.ai/docs/providers/ollama): the BYOK inference path, unchanged

[#496]: https://github.com/derio-net/frank/issues/496
