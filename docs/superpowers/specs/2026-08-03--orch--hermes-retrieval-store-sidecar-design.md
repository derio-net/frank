# Hermes Agent Shell — a dedicated retrieval-store sidecar, and Bun in the ssh sidecar

**Date:** 2026-08-03
**Layer:** `orch` (15) — AI Agent Orchestrator
**Status:** Designed
**Prompted by:** `derio-net/frank` issue #759, itself a follow-on to #748 / #751
**Repos:** `derio-net/frank` (sidecar, PVC, wiring) and `derio-net/agent-images`
(the `hermes-agent-shell-ssh` image)

An external client wants to *use* the iGPU retrieval tier from #748 from inside
the `hermes-agent-shell` pod. That needs somewhere to keep the vectors, and a
runtime to run the client with. Two containers change. No new services, no new
nodes, no new LoadBalancer IP.

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| 2026-08-03-hermes-retrieval-store-sidecar | `derio-net/frank` | `2026-08-03-hermes-retrieval-store-sidecar` | — |
| 2026-08-03-hermes-ssh-bun-runtime | `derio-net/agent-images` | `2026-08-03-hermes-ssh-bun-runtime` | — |

The two plans are independent to *write* and independent to *merge*. They are
ordered only at the pin: see [Sequencing](#sequencing).

## One correction to the issue, up front

#759 says the revised shape needs **"no restart required by this work."** That is
true in the sense it was written — no Longhorn volume detach, no scheduled
maintenance window, none of the risk the withdrawn 5Gi → 10Gi expansion carried.

It is not true literally. `hermes-agent-shell` is `strategy: Recreate`
(`apps/hermes-agent-shell/manifests/deployment.yaml:11`) because every one of its
volumes is RWO and cannot double-mount. **Adding a fourth container to the pod
recreates the pod**, so Hindsight goes down for as long as the new pod takes to
become ready, and any live `tmux` / SSH / mosh sessions on the shell are dropped.

The distinction that matters and survives: a *detach-and-expand* is a scheduled,
risky operation on a volume holding a live database; a *pod recreate* is the
routine thing every manifest change to this pod already does. The revised design
still avoids the former. It does not avoid the latter, and nothing can — that is
the cost of putting a container in an existing pod rather than a new one.

Practically: whoever merges chooses when the restart happens, because ArgoCD
syncs on merge. There is no separate window to book.

## Decisions

| # | Decision | Choice | Why |
|---|---|---|---|
| 1 | Scope | **Both repos this run** | The Bun half turned out not to depend on the CLI's identity — see decision 2 — so nothing is blocked |
| 2 | The CLI | **Bun in the image; the CLI installed by hand onto the home PVC** | The image ships a generic runtime that names nothing. `$HOME=/opt/data/home` is a Longhorn PVC, so a one-time global install persists across restarts — the same persistent-agent pattern these shells already use for `claude` and `gh` auth. Keeps a private tool's name out of two public repos, honouring the discretion rule #748 established |
| 3 | Postgres image | **Stock `pgvector/pgvector:0.8.6-pg18`, digest-pinned** | Nothing to build or bump. Precedent in-repo: `apps/vk-remote` runs stock `postgres:16-alpine`. Verified live — see [the gate](#the-gate-run-during-design) |
| 4 | DB auth | **`trust` on `127.0.0.1`** | What the Hindsight sidecar already does. No secret to provision means nothing can crashloop the shared pod at first boot. The cost is real and named below |

### What decision 4 actually costs

With `trust`, **every container in the pod can connect to the retrieval store as
any role** — including the `hermes` container, which is unmodified upstream
`nousresearch/hermes-agent` running LLM-driven agent code. An agent that decides
to `DROP TABLE` can.

Three things bound it, and they are why the choice is defensible rather than
merely convenient:

- `listen_addresses=127.0.0.1` keeps the socket inside the pod's network
  namespace. Nothing off-pod can reach it, with or without credentials.
- Hindsight — the more valuable of the two stores — already runs on exactly this
  posture. This adds no new class of exposure to the pod.
- The alternative fails *worse*. A password Secret must exist before first boot;
  if it is missing or mistyped, the `gbrain` container crashloops **inside the
  shared pod**, which is noisy for Hindsight and the SSH sidecar too. Trading a
  within-pod confidentiality boundary for a new way to break two working
  containers is a bad trade at this blast radius.

If that judgement changes, the migration is a `POSTGRES_HOST_AUTH_METHOD` flip
plus an `ALTER ROLE … PASSWORD`, not a redesign.

## The gate, run during design

The riskiest assumption in decision 3 is that a stock upstream image tolerates
this pod's security posture — strict non-root, `cap-drop: ALL`, and a volume root
that `fsGroup` leaves at `root:1000 0775`. That was tested rather than asserted,
locally, before the spec was finished.

Setup mirrored the pod exactly: `--user 1000:1000`, `--cap-drop ALL`, volume root
`chown 0:1000` + `chmod 0775`, `PGDATA` a **subdirectory** of the mount, `trust`
auth, `-c listen_addresses=127.0.0.1 -c port=5434`, and a
`/docker-entrypoint-initdb.d` script.

| Question | Result |
|---|---|
| Does `initdb` succeed as uid 1000? | **Yes** — and it creates `PGDATA` itself as `drwx------ 1000:1000` |
| Does the extension get created declaratively? | **Yes** — the issue's own acceptance query returns `extversion 0.8.6` |
| Does pgvector actually work? | **Yes** — `hnsw` index built, cosine ordering returned the right row |
| Server version | **PostgreSQL 18.4** (Debian `18.4-1.pgdg12+1`) |
| Are the `-c` overrides honoured? | **Yes** — `listening on IPv4 address "127.0.0.1", port 5434` |
| Does it survive a restart on a **populated** volume? | **Yes** — healthy, rows intact |

Two findings changed the design:

1. **`PGDATA` must be a subdirectory of the mount, not the mount root.** The
   entrypoint creating that directory is precisely what makes it uid-1000-owned
   and `0700`. Pointing `PGDATA` at the mount root — which `fsGroup` has already
   set to `0775` — is how this fails. Both `apps/vk-remote` and the Hindsight
   sidecar use the subdirectory form; now there is a recorded reason.
2. **The `-k /tmp` socket-directory flag the Hindsight image carries is not
   needed here.** The official Postgres image ships `/var/run/postgresql` at mode
   `3777` for exactly this arbitrary-uid case. One fewer flag, verified rather
   than inherited.

**One check in the gate was invalid, and is reported as such.** The
"is it reachable off-loopback?" probe used a published Docker port; Docker's
userland proxy accepts the client's TCP connection before anything reaches the
container's network namespace, so it cannot disprove a loopback-only bind. The
loopback claim rests entirely on the server's own startup log line, which is
direct evidence. The probe is not repeated in the test plan.

## Frank's half

### The volume

`apps/hermes-agent-shell/manifests/pvc-gbrain.yaml` — `hermes-agent-shell-gbrain`,
**10 Gi**, RWO, `storageClassName: longhorn`. Sized as headroom, not projection:
the working set is expected in the low hundreds of MB.

Because it is its own Longhorn volume it **auto-joins the existing backup group**,
exactly as the Hindsight PVC did — the retrieval store is backed up from the
moment it exists, for free.

That is the mechanism, verified rather than repeated from a comment: Longhorn
labels any volume carrying no explicit recurring-job labels with
`recurring-job-group.longhorn.io/default: enabled`, and two jobs select that
group — `daily-nas` (`0 2 * * *`, retain 7) and `weekly-r2` (`0 3 * * 0`,
retain 4). The Hindsight volume carries exactly that label today despite its PVC
manifest never setting one, and has **10 backups** on record. Nothing in the new
PVC needs to opt in; opting *out* would be the thing that took an edit.

**Headroom was checked, not assumed.** Frank refused a PVC expansion as recently
as 2026-07-27 because Longhorn's provisioning ceiling counts each replica's
*declared* size, and `status.capacity` simply never changes while ArgoCD stays
green. Measured today at the current `storageOverProvisioningPercentage: 150`:
mini-1 289 GiB of scheduling headroom, mini-2 360 GiB, mini-3 264 GiB, gpu-1
~5 TiB. A 10 Gi volume at replica count 3 is noise against that.

### The container

A fourth container, `gbrain`, mirroring the `hindsight` sidecar's shape:

| Aspect | Value |
|---|---|
| Image | `pgvector/pgvector:0.8.6-pg18`, pinned by digest `sha256:691673308c99…` (the multi-arch index digest, so the node resolves its own architecture) |
| Mount | `hermes-agent-shell-gbrain` at `/opt/gbrain`, **sidecar-only** — not shared with `hermes`, `ssh` or `/opt/data` |
| `PGDATA` | `/opt/gbrain/pgdata` — a subdirectory, per the gate |
| Port | **5434** on loopback (`5432` unused, `5433` is Hindsight). **No `containerPort`** — declaring one would be misleading, since nothing off-pod can reach it |
| Args | `-c listen_addresses=127.0.0.1 -c port=5434` |
| Env | `POSTGRES_DB=gbrain`, `POSTGRES_USER=gbrain`, `POSTGRES_HOST_AUTH_METHOD=trust`, `PGDATA` |
| Security | `runAsUser/Group: 1000`, `runAsNonRoot: true`, `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]` — strict, like `hindsight` and `ssh`; only the upstream `hermes` container needs root |
| Resources | requests `100m` / `256Mi`; limits `500m` / `1Gi` |
| Probes | `exec` + `pg_isready` on loopback. **Not `httpGet`/`tcpSocket`** — the kubelet probes the *pod IP*, and this server binds `127.0.0.1` only, so a kubelet-side probe would be refused forever. Hindsight learned this the expensive way (37 restarts) and the fix is recorded in its manifest comments |

`CREATE EXTENSION vector` ships as a ConfigMap mounted into
`/docker-entrypoint-initdb.d/`, so the extension is declarative rather than a
manual `psql` step.

### What is deliberately *not* built

- **No env shim exposing a `DATABASE_URL` to login shells.** The obvious move is
  a `/etc/profile.d` shim like the BYOK one, exporting a DSN — but the CLI is
  installed by hand and nobody here knows which variable it reads. Shipping a
  guessed variable name is shipping a thing that is never read. The DSN
  (`postgres://gbrain@127.0.0.1:5434/gbrain`) is documented in the app README
  instead; wiring it is a one-line follow-up once the CLI's contract is known.
- **No Service, no `containerPort`, no LB IP, no IngressRoute.** Loopback only.
- **Nothing touching Hindsight** — same image, same PVC, same 5 Gi, same env.
- **No change to the `ssh` container's `command`/`args`.**
  `scripts/tests/test_hermes_ssh_byok_env_snapshot.py` locks that script exactly
  — the snapshot write, the `exec` of the image entrypoint, and the absence of a
  raw `sshd` invocation. Bun arrives through the *image*, so that guard keeps
  holding untouched, which is the point of not routing this through the wrapper.

### Two existing guards this has to stay inside

- `scripts/tests/test_config_reaches_the_process.py` forbids plain-ConfigMap
  mounts that a pod reads without a rolling mechanism. This app is **already
  exempt** (`apps/hermes-agent-shell/manifests:hermes-agent-shell`), and the
  exemption is app-scoped, so a new ConfigMap does not trip it. It is also
  *correct* here for a stronger reason than the recorded one: an
  `initdb.d` script is read once, at database initialisation, so rolling the pod
  on a change would achieve nothing anyway. The exemption's reason string should
  be extended to say so, rather than leaving a future reader with a rationale
  that only covers profile.d shims.
- The Application at `apps/root/templates/hermes-agent-shell.yaml` syncs the
  whole `manifests/` directory with `prune: false` and no kustomization, so new
  files are picked up automatically and no root-template change is needed.

## agent-images' half

`hermes-agent-shell-ssh/Dockerfile` gains Bun, and only Bun.

- Installed **as root, to `/usr/local/bin`**, before the `USER ${AGENT_USER}`
  switch. This is load-bearing: Bun's own installer targets `~/.bun`, and
  `$HOME` here is `/opt/data/home`, which is a **PVC mount at runtime** — so
  anything the image bakes under that path is hidden the moment the volume
  mounts. The image installs outside `$HOME`; only the operator's later global
  install lives on the PVC, which is where persistence is wanted.
- **Pinned version, checksum-verified** against the release's own
  `SHASUMS256.txt`, with the architecture derived at build time rather than
  hardcoded — the image builds `amd64` today, and a hardcoded x64 URL is how a
  future multi-arch build would produce a silently broken image.
- A `/etc/profile.d/36-hermes-bun-path.sh` shim putting `$HOME/.bun/bin` on
  `PATH`, so hand-installed globals resolve in login shells. This is required,
  not cosmetic: sshd scrubs the container environment, so a login shell's `PATH`
  comes from `/etc/profile.d` or from nowhere.

  The number was chosen against what this container **actually** has, listed from
  the running pod rather than assumed from the family: only
  `35-hermes-agent-shell-byok-env.sh` (mounted by frank, not baked) and
  `70-systemd-shell-extra.sh`. Note there is **no `50-…-motd.sh` here** — that
  belongs to the sibling `hermes-agent-shell` image, and the usual "number it
  below the MOTD" rule is about a file this image does not contain. `36` simply
  sits immediately after frank's mounted shim and well clear of `70`.
- The existing `smoke-test-hermes-agent-shell-ssh` CI job gains a `bun --version`
  assertion and a check that the shim actually puts the global bin dir on `PATH`
  **in a login shell** — `ssh host -- cmd` skips `profile.d` entirely, so the
  assertion has to run under `bash -lc` or it proves nothing.

## Sequencing

The two PRs are independent except at one point: frank pins the ssh sidecar image
by SHA, so the Bun image must exist before frank can point at it.

1. **agent-images PR merges first.** The `main` build publishes a new
   `hermes-agent-shell-ssh` tag.
2. **frank's PR re-pins** to that SHA — the final commit, pushed to the open PR.

Order is a preference, not a constraint. If frank merges first it is still
correct: the sidecar and PVC land, and `hermes-agent-shell-ssh` is already in the
`AGENT_IMAGES` allowlist, so the scheduled bump workflow re-pins it later. The
only consequence is that `bun --version` does not answer until then.

Because the re-pin depends on a build that does not exist while the plan is being
written, it is **back-loaded into a manual phase** with nothing depending on it —
alongside the one-time CLI install, which is manual by decision 2.

## Named gaps

- **`/docker-entrypoint-initdb.d` runs only at `initdb`.** If the SQL ever needs
  to change, editing the ConfigMap does nothing to an initialised volume — it is
  first-boot-only by design. Any later schema or extension change is a `psql`
  operation or a migration the CLI owns, and the manifest says so.
- **The CLI is installed by hand and therefore is not reproducible from git.**
  That is decision 2's accepted cost. If the home PVC is ever rebuilt, the
  install must be repeated; the runbook entry exists for that reason.
- **We do not know what the CLI needs.** Schema, migrations, connection-variable
  name and the retrieval endpoints it calls are all outside this repo. This spec
  provisions a working, empty, extension-enabled database and a runtime — no
  more. If the CLI turns out to need a role with different privileges or a second
  database, that is a follow-up.
- **gpu-1's memory *limits* are already 119% of capacity** (requests are 25%).
  Adding a 1 Gi limit continues an existing overcommit rather than creating one,
  and the requests — the number the scheduler actually enforces — have ample
  room. Worth knowing, not worth blocking on.

## Counter-arguments considered

- **"Reuse the Hindsight Postgres — one less container."** This is what #759
  withdrew, and the reasoning holds: it would have coupled two memory layers with
  different write patterns and different recovery expectations, made a Hindsight
  restore take the retrieval store with it, and required an RWO expansion whose
  detach risk is the very thing the revision avoids. The only saving was one
  container image.
- **"Build a custom image like `hermes-agent-shell-hindsight`."** Justified there
  — that image carries an API server, an embedder and a baked model. Here the
  requirement is *stock Postgres plus a stock extension*, which the stock image
  is. A third image would add a build, a bump and a pin for zero added
  capability.
- **"Give it its own pod instead of a fourth container."** Then the client would
  reach it over the network rather than loopback, needing a Service, and the
  store would be schedulable away from the shell that uses it. Co-location in one
  pod is what makes `127.0.0.1` correct and keeps the surface at zero.
- **"Skip Bun; run the CLI with Node."** The tool is a Bun/TypeScript CLI; Bun is
  its stated runtime. Substituting a runtime the tool does not target trades a
  ~40 MB binary for an unbounded compatibility problem.

## Test Plan (post-merge, operator-driven)

| # | Step | Pass condition | Owner |
|---|---|---|---|
| 1 | After ArgoCD syncs, `kubectl -n hermes-agent-shell get pod` | Pod `4/4 Running`. **Hindsight's PVC still reports `5Gi` and its container is healthy** — the "untouched" claim, asserted on the artifact | Frank |
| 2 | `psql -h 127.0.0.1 -p 5434 -U gbrain -d gbrain -c 'select extversion from pg_extension where extname = $$vector$$'` from inside the pod | Returns `0.8.6` | Frank |
| 3 | `df -h /opt/gbrain` in the `gbrain` container | Its **own** volume, ~10 Gi, distinct from Hindsight's mount | Frank |
| 4 | `kubectl -n hermes-agent-shell exec -c gbrain -- ls -ld /opt/gbrain/pgdata` | `drwx------` and uid 1000 — the `fsGroup` re-walk did not re-loosen it | Frank |
| 5 | Delete the pod, let it come back | `gbrain` returns healthy on the **populated** volume, and a row written before the delete is still there. This is the check the local gate can only approximate | Frank |
| 6 | Re-pin the ssh sidecar (or wait for the bump), then `bun --version` over **SSH** | Prints a version in a login shell, not just under `kubectl exec` | Frank |
| 7 | Hand-install the CLI, then `<cli> --version` in a fresh SSH login | Resolves via the `profile.d` PATH shim | Frank |
| 8 | Restart the pod after step 7 | The CLI still resolves — proving the PVC-global-install actually persists, which is the entire basis of decision 2 | Frank |
| 9 | The client's own retrieval workload against these endpoints | Meets the targets stated in the private issue | **Requesting repo** |

Row 9 cannot be verified here — it depends on a corpus this cluster does not have
and this repo must not contain. Frank's job is to make it runnable.

Row 8 deserves its place: decision 2 rests on a claim about PVC persistence that
is easy to state and easy to be wrong about. If it fails, decision 2 is wrong and
the CLI belongs in the image after all.

## Discretion

`derio-net/frank` and `derio-net/agent-images` are both public; the requesting
repo is not. No file, test, comment or commit message added by this work names
the consumer repo, its product, its corpus or its tooling. `gbrain` is the
codename #759 itself uses in the public issue. Decision 2 exists largely to keep
it that way — the image ships a general-purpose runtime, and the one named thing
is typed by the operator into a shell.
