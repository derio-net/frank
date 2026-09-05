# Journal: 2026-08-03-hermes-retrieval-store-sidecar

<!-- fr:journal kind=decision scope=plan id=p1-no-shared-test-helper created=2026-08-03T17:32:37 phase=1 -->
### p1-no-shared-test-helper · decision · P1.T2.S3: no shared test-helper module — the duplication is two trivial lines (phase 1)

Evaluated the optional refactor and declined it. test_hermes_gbrain_sidecar.py duplicates exactly \ (one line: yaml.safe_load(path.read_text())) and \ (two lines) from test_hermes_ssh_byok_env_snapshot.py, plus a REPO constant every test in scripts/tests/ already computes for itself. Extracting a module would add an import surface and require editing the ssh guard — a file whose whole job is to be a locked snapshot — to save three lines. Left alone deliberately, per the step's own instruction to say so.

<!-- fr:journal kind=discovery scope=plan id=p1-devcontainer-tmp-exhaustion created=2026-08-03T17:33:20 phase=1 -->
### p1-devcontainer-tmp-exhaustion · discovery · The fr devcontainer's /tmp exhausts across repeated full-suite runs, and it looks like 27 real failures (phase 1)

Baseline `scripts/tests/` on this branch before any edit: **576 passed, 1 xfailed**.
After adding the phase-1 tests the same command reported **5 failed, 559 passed,
1 xfailed, 22 errors** — in files this phase does not touch (`test_fetch_text.py`,
`test_sync_dossier_to_data.py`, `test_ovms_retrieval_bench.py`,
`test_check_blog_build_supersession.py`, `test_generate_images_entry_references.py`).

Every one of them was the same cause:

    OSError: could not create numbered dir with prefix pytest- in /tmp/pytest-of-vscode after 10 tries

plus one Hugo `panic: publishDir is empty` downstream of the same thing. It is
**not** disk exhaustion — `df` showed 11G free and 28% inode use — it is the
accumulated `/tmp/pytest-of-vscode/pytest-N`, `/tmp/frank-hugo-s_*` and
`/tmp/tmp.*` trees that several consecutive full-suite runs leave behind in a
long-lived isolation container.

`rm -rf /tmp/pytest-of-vscode /tmp/frank-hugo-s_* /tmp/tmp.*` cleared it
completely: the very next run was **586 passed, 1 xfailed** (576 baseline + the
10 new tests), zero failures, zero errors.

Worth knowing because the failure presents as a broad, alarming regression in
unrelated subsystems immediately after an unrelated edit — the shape that makes
you go looking for a manifest bug that is not there. Check `/tmp` in the
container before believing a cross-cutting suite failure.

<!-- fr:journal kind=discovery scope=plan id=p1-pytest-invocation-in-this-workspace created=2026-08-03T17:33:22 phase=1 -->
### p1-pytest-invocation-in-this-workspace · discovery · Phase 1 test invocation: the venv is container-only, and rtk hides pytest's exit status (phase 1)

Recorded so phase 2 does not rediscover it.

The worktree's `.venv/bin/python` is a symlink into
`/home/vscode/.local/share/uv/python/...` — a **Linux** interpreter — so it does
not resolve on the macOS host at all (`No such file or directory`). The suite
only runs inside the isolation container:

    fr isolation exec --branch feat/hermes-retrieval-store-sidecar -- \
      bash -lc ".venv/bin/python -m pytest scripts/tests/ -q"

Two traps around that command:

- The host's `rtk` hook rewrites bare `python -m pytest` and **summarises** the
  result: a genuine `No module named pytest` came back as the benign-looking
  "Pytest: No tests collected". `rtk proxy python …` is no escape here either —
  it failed with "Target Python binary 'python' not found in project. Most likely
  running 'rye sync' will resolve this." Wrapping the whole thing in `sh -c '…'`
  is what actually gets raw pytest output.
- `fr isolation exec -- python …` fails with `executable file not found in $PATH`;
  the container needs the explicit `.venv/bin/python` (or a login shell).

The worktree is mounted in the container at the *same* absolute path as on the
host, so no path translation is needed.

<!-- fr:journal kind=decision scope=plan id=p1-acceptance-stays-not-implemented created=2026-08-03T17:33:51 phase=1 -->
### p1-acceptance-stays-not-implemented · decision · Acceptance row orch-hermes-retrieval-store-available stays not-implemented after phase 1, deliberately (phase 1)

`fr plan edit --complete-phase 1` warns that the acceptance row is still
`not-implemented`. That is correct and intended, not an oversight.

The plan prose says it outright: the local design gate is evidence for the
*design*, not the *deployment* — it ran on a laptop against a Docker volume, not
on Longhorn under a kubelet that re-walks `fsGroup` on every remount. Phase 1
ships manifests and offline guards; nothing here has observed a running
container. The row flips in phase 4, on live output from the pod.

<!-- fr:journal kind=discovery scope=plan id=p2-mutation-pgdata created=2026-08-03T17:47:00 phase=2 -->
### p2-mutation-pgdata · discovery · PGDATA guard: fails on both broken shapes, survives a rename — mutation-checked three ways (phase 2)

Phase 1 shipped a PGDATA test, but it compared against MODULE CONSTANTS
(`GBRAIN_MOUNT`, `GBRAIN_PGDATA`) and ended on `assert pgdata == GBRAIN_PGDATA`
— a literal restatement of the YAML. Rewritten in phase 2 to read the mountPath
back off the manifest (whichever volumeMount is backed by the gbrain PVC) and
assert the RELATIONSHIP. Then doctored three ways:

- **M1 — `PGDATA: /opt/gbrain`** (the mount root, the failure the design gate
  actually found): **FAILED as it should.**
  `AssertionError: PGDATA ('/opt/gbrain') must not BE the mount root …
  assert '/opt/gbrain' != '/opt/gbrain'`
- **M1b — `PGDATA: /var/lib/postgresql/data`** (off the volume entirely, so the
  database would not survive a pod recreate): **FAILED as it should**, on the
  `startswith(mount_path + "/")` half. Worth doing separately: the two
  assertions catch different bugs and only one of them was exercised by M1.
- **M1c — POSITIVE CONTROL: renamed the mountPath AND PGDATA together**
  (`/opt/gbrain` -> `/opt/store`, PGDATA -> `/opt/store/pgdata`): **stayed
  GREEN**, which is the claim the rewrite exists to make. Under phase 1's
  constant-based version this rename would have failed while breaking nothing.

Restored after each; `git diff -- apps/` empty at the end.

<!-- fr:journal kind=discovery scope=plan id=p2-mutation-probes created=2026-08-03T17:47:16 phase=2 -->
### p2-mutation-probes · discovery · Probe guard: the port assertion only stops restating the YAML once it is derived from the server's own args (phase 2)

The probe guard now derives the port from the container's `-c port=` arg
(`_configured_port`) instead of matching the literal `"5434"`, and checks the
ABSENCE of `httpGet`/`tcpSocket` keys rather than only the presence of `exec`
(both can be declared at once, and the kubelet would honour the wrong one).
Three mutations:

- **M2 — readinessProbe swapped for `tcpSocket: {port: 5434}`** (the shape that
  cost the `hindsight` sidecar 37 restarts): **FAILED as it should.**
  `readinessProbe must not declare tcpSocket — the kubelet dials the POD IP and
  gbrain binds 127.0.0.1 only`
- **M2b — livenessProbe port 5434 -> 5433, server arg untouched**: **FAILED as
  it should.** This is the one phase 1's literal check could not have caught in
  general: a probe naming a plausible Postgres port reads as correct, and 5433
  is the Hindsight database next door — the probe would have passed against the
  WRONG healthy server, reporting gbrain ready while gbrain was not running.
- **M2c — server arg `port=5434` -> `port=5433`, probes untouched**: **FAILED as
  it should, in TWO guards at once** —
  `test_gbrain_binds_loopback_only_on_its_own_port` (collision: both servers
  share this pod's single netns, so the second to start cannot bind) and
  `test_gbrain_probes_are_exec_pg_isready_on_loopback` (probe/server
  disagreement). The derived-port check is symmetric — it catches the drift
  whichever side moved.

Restored after each; manifest diff empty.

<!-- fr:journal kind=discovery scope=plan id=p2-mutation-hindsight-untouched created=2026-08-03T17:47:36 phase=2 -->
### p2-mutation-hindsight-untouched · discovery · "Hindsight is untouched" is now three assertions, and all three were doctored into failing (phase 2)

#759's headline justification turned into mechanical checks, each
mutation-verified:

- **M3 — `pvc-hindsight.yaml` 5Gi -> 10Gi** (reviving the withdrawn expansion,
  the single riskiest thing in the original issue — an RWO detach-and-expand on
  a volume holding a live database): **FAILED as it should**
  (`test_hindsight_pvc_still_requests_its_original_size`, `- 5Gi / + 10Gi`).
- **M4a — gbrain additionally mounts the `hindsight-data` volume**: **FAILED as
  it should** on the shared-volume-name assertion.
- **M4b — gbrain's mountPath nested INSIDE Hindsight's**
  (`/opt/hindsight/gbrain`, PGDATA moved with it): **FAILED as it should**, at a
  DIFFERENT assertion line than M4a. This is why the disjointness check is a
  prefix test and not `!=`: nesting recouples the two stores' lifecycles exactly
  as sharing does, while leaving every volume name distinct and reading as a
  mount tidy-up.
- **M5 — ssh wrapper `exec /usr/sbin/sshd -D -e` instead of the image
  entrypoint** (the tempting way to land the sibling plan's Bun runtime in a
  hurry): **FAILED as it should**, in both the new non-regression test and the
  pre-existing `test_hermes_ssh_byok_env_snapshot.py` that owns the full
  contract. The overlap is deliberate and bounded — this file asserts only the
  one line this plan could plausibly break, per the step's instruction not to
  duplicate that guard.

Restored after each; `git diff -- apps/` empty before commit.

<!-- fr:journal kind=discovery scope=plan id=p2-mutation-config-exemption created=2026-08-03T17:47:55 phase=2 -->
### p2-mutation-config-exemption · discovery · The config-mount exemption is load-bearing for the initdb CM specifically — checked by deleting it, not by reading it (phase 2)

Task 4 only asked for a reason-string edit plus a green run, but "still green"
cannot distinguish a live exemption from a dead one, so the entry was doctored
too.

**M6 — deleted the `apps/hermes-agent-shell/manifests:hermes-agent-shell` EXEMPT
entry**: `test_no_unreviewed_plain_configmap_mounts` **FAILED as it should**,
and the failure message enumerated the covered ConfigMaps:

    {'apps/hermes-agent-shell/manifests:hermes-agent-shell':
      ['hermes-agent-shell-gbrain-initdb', 'hermes-agent-shell-env',
       'hermes-agent-shell-fetch-text']}

That is the evidence the spec's claim needed. The exemption is app-scoped, so
the new initdb ConfigMap is genuinely inside it — not tripping the tripwire, and
not silently outside its remit either. The reason string now says why that is
CORRECT rather than merely tolerable: initdb.d is read once, when the entrypoint
has to initialise an empty PGDATA, and skipped entirely on every later start, so
rolling the pod on a change to it could not deliver that change. One entry, not
two — the key is app-scoped and a second would be a dead entry by construction
(`test_exempt_list_has_no_dead_entries` keys on the app, not the ConfigMap).

**Operational trap worth recording:** restoring a mutation with
`git checkout -- <file>` reverts the WHOLE file, so mutating a test file you
have also legitimately edited silently discards your own work. It ate the Task 4
reason edit; caught and re-applied. Mutate manifests where possible, and check
`git diff` after restoring rather than assuming.

<!-- fr:journal kind=discovery scope=plan id=p3-onrootmismatch-load-bearing created=2026-08-03T18:05:14 phase=3 -->
### p3-onrootmismatch-load-bearing · discovery · fsGroupChangePolicy: OnRootMismatch is LOAD-BEARING for gbrain, not belt-and-braces — a stock image has no chmod hook (phase 3)

Writing the gotcha surfaced an asymmetry the spec states only implicitly (Test
Plan row 4, "the fsGroup re-walk did not re-loosen it").

The existing `hindsight` gotcha records that the pod-level `fsGroup` re-walk
re-loosens a POPULATED `PGDATA` to group-rwx on every remount, and that Postgres
then refuses to start. Its fix is primarily IMAGE-side — the hindsight image
runs `chmod 700 $PGDATA` at boot — with `fsGroupChangePolicy: OnRootMismatch` on
the pod as "the belt to its braces" (deployment.yaml:57-68 says exactly that).

`gbrain` is a STOCK image. There is no boot hook, and adding one means building
an image, which is the entire thing decision 3 avoids. So for this container
`OnRootMismatch` is not defence-in-depth — it is the ONLY thing standing between
the second boot and a refusing Postgres. The first boot would look fine either
way (`fsGroup` runs on an empty volume, then `initdb` creates PGDATA at 0700),
which is the same delayed-failure shape the hindsight entry warns about.

Consequence for a future reader: a "tidy-up" that drops `fsGroupChangePolicy`
from the pod securityContext now breaks a container that has no local defence,
and it breaks it one recreate later, not on the change. Documented in all three
deliverables (README, one-liner, prose) with the recovery
(`kubectl exec … -c gbrain -- chmod 700 /opt/gbrain/pgdata` — the container runs
as the owning uid, so it can fix itself).

Not a defect in the spec or the manifest: the shipped manifest already carries
`OnRootMismatch`, and the deployment comment already explains the mechanism. It
is the WEIGHT that differs between the two containers, and nothing said so.

<!-- fr:journal kind=discovery scope=plan id=p3-runbook-parity-checked created=2026-08-03T18:05:39 phase=3 -->
### p3-runbook-parity-checked · discovery · The runbook is generated, so plan block and runbook entry must match EXACTLY — checked by parsing both, and it caught a drift I introduced by eye (phase 3)

P3.T2.S1 warns that `docs/runbooks/manual-operations.yaml` is generated and a
later fix must edit the plan block or the next `/sync-runbook` reverts it. The
same trap applies at WRITE time, and it bit immediately.

`/sync-runbook` was performed as the skill prescribes but by hand rather than by
tool: the file is 2223 lines of hand-formatted YAML with folded scalars, and a
PyYAML round-trip would reflow all 142 existing entries into a diff nobody can
review. The two new entries were therefore inserted in place, at the correct
sorted position (both are `layer: orch`; ids sort between `default-qwen64k` and
`litellm-virtual-key`, and after `soul-fetch-text` respectively).

Then verified mechanically rather than by reading: parse the runbook, parse the
two fenced blocks out of `_prose.md` (dedented), and compare every required
field except `status`. **The first run FAILED** — the third `commands:` entry of
`orch-hermes-ssh-bun-repin` had drifted while I was editing the runbook copy
("see the rollout note below", which is meaningless outside the plan, vs the
fuller Recreate sentence). Invisible in review, and the next `/sync-runbook`
would have silently rewritten it. Plan block corrected to match; second run
green on both entries.

Also asserted: no duplicate ids, all nine required fields present and non-empty
on both, `status: pending` on both, and the `orch` block still id-sorted
(142 -> 144 operations). Global `(layer, id)` ordering is False both BEFORE and
AFTER the change — a pre-existing out-of-order id in some other layer, not
something this phase introduced. Worth knowing before someone "fixes" the sort
and produces a 2000-line diff.

Reusable check:
`/Users/derio/.claude-tmp/.../scratchpad/check_runbook.py` (scratch, not
committed) — parse both sides, diff the fields, exit non-zero. There is no test
in `scripts/tests/` covering `manual-operations.yaml` at all, so nothing else
would have caught this.

<!-- fr:journal kind=decision scope=plan id=p3-readme-scope-and-postdeploy-hook created=2026-08-03T18:06:04 phase=3 -->
### p3-readme-scope-and-postdeploy-hook · decision · Two judgement calls in phase 3: the README needed its topology tables edited too, and the Post-Deploy Checklist hook was declined on purpose (phase 3)

Both are places where I did more (or less) than the step literally says.

**1. The README got more than "a short section."** The file opens
"running as a three-container pod", tables "Four RWO Longhorn PVCs", and closes
with "The pod has three containers, so `kubectl exec` needs an explicit `-c`".
Adding a section about a fourth container while leaving those three claims
standing produces a document that contradicts itself on its own first line — and
the `-c` note is the one an operator actually reads under pressure. So the
container table gained a `gbrain` row, the PVC table gained
`hermes-agent-shell-gbrain`, the counts moved 3 -> 4 and 4 -> 5, and the exec
note now names all four containers. No manifest was touched; this is prose about
prose.

**2. The `plan-post-deploy-checklist` PostToolUse hook fires on every edit to
this plan and was deliberately not obeyed.** It says "This standard layer plan is
missing the Post-Deploy Checklist (blog post, README update, runbook sync)". The
rule it cites (`agents/rules/plan-post-deploy-checklist.md`) exempts exactly this
case: "Fix/extension plans: skip blog posts (update the existing layer post
instead)". `orch` is a deployed layer with both posts already written
(`building/33-hermes-shell`, `operating/28-hermes-shell`), and this plan adds a
sidecar to an existing pod. The other two items it asks for are already covered
by this very phase (app README, `/sync-runbook`) and by phase 4 (deploy
verification, plan status). Adding a fifth phase to satisfy a heuristic would
also mean re-cutting an approved plan mid-execution.

The hook has no way to tell an extension from a new layer, so it fires on both.
Recording the reasoning here rather than leaving the next executor to re-derive
it — the hook will fire again on phase 4.

Not decided here: whether the building/operating posts should gain a paragraph
about the retrieval store. That is a phase-4-or-later call, once the thing has
actually run on the cluster, and it is post-deploy work by the rule s own
sequencing.

<!-- fr:journal kind=finding scope=plan id=r-f1-onrootmismatch-corrected created=2026-08-03T18:39:16 state=fixed -->
### r-f1-onrootmismatch-corrected · finding [fixed] · CORRECTION to p3-onrootmismatch-load-bearing: the stock entrypoint DOES chmod PGDATA on every boot — reproduced

The phase-3 entry `p3-onrootmismatch-load-bearing` is **wrong**, and the claim it
made was propagated into four places (`agents/rules/frank-gotchas.md`,
`docs/runbooks/frank-gotchas/agent-shells.md`, `apps/hermes-agent-shell/README.md`,
and implicitly the spec). It said a stock Postgres image "has no boot-time chmod
hook", making `fsGroupChangePolicy: OnRootMismatch` load-bearing for gbrain.

**It has one, upstream.** `docker-entrypoint.sh` calls
`docker_create_db_directories` at `_main` line 340 — BEFORE the
`DATABASE_ALREADY_EXISTS` branch at line 347, i.e. on every start — and it runs:

    mkdir -p "$PGDATA"
    chmod 00700 "$PGDATA" || :

**Reproduced locally 2026-08-03**, docker, the pinned digest
`pgvector/pgvector:0.8.6-pg18@sha256:691673…`, `--user 1000:1000 --cap-drop ALL`,
volume root `chown 0:1000 && chmod 2775`, `PGDATA=/vol/pgdata`, trust auth,
`-c listen_addresses=127.0.0.1 -c port=5434`:

- first boot: `pg_isready` OK after 3 s; `/vol/pgdata` = `drwx------ 1000 1000`
- stop, then `chgrp 1000 + chmod 2770 /vol/pgdata` (simulating the fsGroup
  re-walk): `drwxrws--- 19 1000 1000`
- `docker start` the SAME container: **`pg_isready` OK after 1 s, and
  `/vol/pgdata` is back to `drwx------`**. Log shows the normal
  "PostgreSQL Database directory appears to contain a database; Skipping
  initialization" path — the chmod ran anyway, because it is upstream of that
  branch.

So the entrypoint is the primary fix for gbrain exactly as the image-side
`chmod 700 $PGDATA` is for hindsight. `OnRootMismatch` is kept (correct, free,
and it does spare a recursive re-walk of a growing DB dir) but is **no longer
described as load-bearing** anywhere.

**The correct mechanism is strictly more useful, because ONE fact explains BOTH
observations.** Reproduced the mount-root form too, same posture, `PGDATA=/vol`:
exit 1, and the logs show the swallow happening —

    chmod: changing permissions of /vol: Operation not permitted
    …
    initdb: error: could not change permissions of directory "/vol": Operation not permitted

The entrypoint chmod EPERMs on the root-owned mount root, `|| :` discards it
silently, and the failure surfaces one step later in initdb, which does its own
chmod and treats EPERM as fatal. (A stray observation from the same logs: the
entrypoint`s `chmod 03775 /var/run/postgresql` EPERMs and is swallowed on every
boot too — harmless, since the image already ships that path at 3777, but it is
the same `|| :` in action.)

**Also corrected: the volume root is `2775`, not `0775`** — kubelet
`SetVolumeOwnership` does `Lchown(-1, fsGroup)` (group only, owner stays root)
then `Chmod(mode | 0660 | 0110 | ModeSetgid)` for directories.

**PARTIAL REFUTATION of the review on that point.** The review said the setgid
bit "is WHY the entrypoint`s `mkdir pgdata` inherits gid 1000". Measured both
parent modes as uid 1000: parent `2775` -> child `drwxr-sr-x 1000 1000`; parent
`0775` -> child `drwxr-xr-x 1000 1000`. **The gid is 1000 either way**, because
the container`s own `runAsGroup: 1000` already makes its egid 1000; the setgid
bit only propagates the setgid bit itself. It would be load-bearing for a
container whose PRIMARY gid differed and which received 1000 as a supplemental
group via fsGroup — not this one. The mode number is fixed as asked; the causal
claim is written accurately instead of as given.

Not verifiable from this workspace: the live `2775` on the actual Longhorn mount
root (no kubeconfig in the fr worktree). Test Plan row 4 was widened to read
`/opt/gbrain` as well as `/opt/gbrain/pgdata` so the mode gets observed rather
than only derived.

<!-- fr:journal kind=finding scope=plan id=r-f2-f4-vacuous-guards created=2026-08-03T18:54:38 state=fixed -->
### r-f2-f4-vacuous-guards · finding [fixed] · Three phase-2 guards were vacuous to an edit that never touched what they read — all three now parse, all three mutation-checked

The phase-2 guards were mutation-checked against the mutations their AUTHOR
thought of. Review found three that pass while the property they name is false.

**F2 — the loopback guard was a substring test.**
`assert "listen_addresses=127.0.0.1" in " ".join(args)`. PostgreSQL applies `-c`
settings LEFT TO RIGHT, so APPENDING `-c listen_addresses=0.0.0.0` leaves the
substring intact while the server binds every interface — and with
`POSTGRES_HOST_AUTH_METHOD=trust` that is `host all all all trust`, i.e.
unauthenticated superuser Postgres on the pod IP. The spec calls
`listen_addresses` "the only thing standing between this database and anything
that can route to the pod", so it was the single worst place in the file for a
substring assertion. Now parsed by `_server_settings()` into a dict with
last-wins semantics; asserted `== "127.0.0.1"`. `_configured_port` had the
identical blind spot and shares the parser.

- **R2** append `-c listen_addresses=0.0.0.0`: FAILED as it should
  (`effective (last-wins) listen_addresses is 0.0.0.0`).
- **R2b** append `-c port=5433`: FAILED as it should, in TWO guards — the
  loopback/collision check and the probe/server port agreement. Worth doing
  separately because the port helper is used by a different test than the one
  F2 named.

**F3 — "share no storage" compared names and paths, never claimName.**
Repointing the `hindsight-data` volume at `claimName:
hermes-agent-shell-gbrain` leaves every volume NAME distinct and every
mountPath distinct, and puts two Postgres instances on one RWO Longhorn
volume — precisely the coupling the revised issue exists to prevent, reached by
a one-word edit in a field no assertion read. Now resolves each container
mounts through the volume list via `_claim_names()` and asserts the two claim
SETS are disjoint (plus a non-empty check on each, so the assertion cannot pass
by resolving nothing).

- **R3** repoint the claimName: FAILED as it should
  (`must resolve to DISJOINT PVCs, found [hermes-agent-shell-gbrain]`).

**F4 — the initdb ConfigMap name was anchored on one side only.**
The ConfigMap test never asserted `metadata.name`; the deployment test asserted
a hardcoded literal. A rename therefore passed green — and the failure it
produces is not cosmetic: that volume is NOT `optional: true`, so an
unresolvable ConfigMap leaves the WHOLE POD in ContainerCreating, taking hermes,
ssh and hindsight down with it on a `Recreate` deployment. Both sides now assert
against one `INITDB_CM_NAME` constant, the way the PVC name already was.

- **R4** rename `metadata.name` only: FAILED as it should.

All restored byte-identical (backup-copy harness, never `git checkout` — the
phase-2 journal records that trap and I had legitimate edits in both mutated
files). `git diff -- apps/` afterwards contains comment/prose corrections only.

<!-- fr:journal kind=finding scope=plan id=r-f5-npm-squat-runbook created=2026-08-03T18:54:56 state=fixed -->
### r-f5-npm-squat-runbook · finding [fixed] · The runbook told the operator to bun install from npm, which the issue says is SQUATTED — onto a PVC holding gh + claude credentials

The manual op `orch-hermes-gbrain-cli-install` said:

    bun install -g <client CLI package>

frank#759 is explicit that the CLI is installed **from a pinned git ref, not
from the npm registry — an unrelated package squats the name there.** That
sentence was lost between the issue and the plan, and the plan is what an
operator actually types.

The blast radius is why this is not a documentation nit. The install target is
`$HOME=/opt/data/home`, the SAME Longhorn PVC that holds this pod `gh` and
`claude` credentials, in a pod with cluster access. A squatted package
postinstall script runs there, as the shell own user, and nothing in this repo
would notice.

Fixed in `_prose.md` (the source of truth) as
`bun install -g "git+<client CLI repo URL>#<pinned ref>"` plus an explicit
"NOT from npm — the name is SQUATTED there" warning in both the command and
`why_manual`, then re-synced into `docs/runbooks/manual-operations.yaml`
preserving `status: pending`. Editing the runbook alone would have been
silently reverted by the next `/sync-runbook`. The same correction went into
`apps/hermes-agent-shell/README.md` and into the spec (decision 2 now says
"from a PINNED GIT REF (never npm — the name is squatted)", with a new
"The npm name is squatted" section carrying the reasoning).

Neither the package nor the repo is named anywhere — discretion rule holds.

**Parity verified mechanically after the re-sync**, the way the phase-3 executor
did: parse every `# manual-operation` block out of `_prose.md`, parse
`manual-operations.yaml`, compare every field except `status`. 2 blocks, 2
matched, `PARITY OK`. The checker lives in the gitignored `scripts/tmp/` so it
is not committed.

<!-- fr:journal kind=finding scope=plan id=r-f6-discretion-scan-had-rotted created=2026-08-03T18:55:20 state=fixed -->
### r-f6-discretion-scan-had-rotted · finding [fixed] · F6 went deeper than reported: FOUR of the discretion scan twelve paths had pointed at nothing since the plan was archived

The review said `test_third_party_discretion.py` has a hardcoded `SCANNED_PATHS`
that includes no file this branch adds, so its "6 passed" is evidence about a
different piece of work. True, and fixed — this plan spec, plan folder, both
journals, the README, three manifests and the gbrain test file are now scanned.

**But the list had already rotted, and nothing said so.** `_files()` skipped
any entry that did not exist. When the #748 plan was archived (frank#757) its
spec, plan folder and BOTH journals moved under
`docs/superpowers/implemented/`, so four of the twelve entries — the four most
PROSE-HEAVY artefacts, i.e. exactly where a discretion leak lives — silently
dropped out of the scan while the file kept reporting green. Verified by
existence-checking each entry: 4 MISSING, 8 EXISTS. Repointed at
`implemented/`; they scan clean.

The blanket `assert out, "the path list has rotted"` at the end of `_files()`
could not catch this — it only fires when EVERY entry has rotted. Coverage that
degrades one path at a time needs a per-path assertion, so
`test_every_scanned_path_exists` now fails on any missing entry.

- **R6a** plant an unaccounted-for issue reference (a four-digit hash-number,
  written literally in the mutation and deliberately not reproduced here) next
  to "external client" in the NEWLY-scanned `deployment.yaml`: FAILED as it
  should. This is the positive control for the widening — it proves the added
  paths are genuinely read, not merely listed.

  Reproducing the literal in THIS entry tripped the same guard on the next full
  run, because the journal is itself one of the newly-scanned paths. That is the
  guard working, and it is a second positive control I did not plan; the file
  own instruction for a benign match is to rephrase rather than widen the
  allowlist, which is what this bullet now does.
- **R6b** rot one `SCANNED_PATHS` entry (rename `pvc-gbrain.yaml`): FAILED as it
  should, naming the missing path.

**A DELIBERATE NARROWING, flagged because it is a judgement call.** Widening the
paths produced 8 hits on `test_no_issue_number_is_correlatable_with_the_requester`
— and every one was a reference to **frank OWN public issues** (`frank#759` in a
manifest provenance comment; "the iGPU retrieval tier from #748" in the spec).
The rule targets the PRIVATE repo issue number, which is a correlatable
identifier; `#\d+` cannot tell the two apart. Scrubbing them would have
satisfied the regex while changing the actual risk not at all, and would have
stripped provenance that every other comment in the same file carries
(`frank#496`, `frank#688`, `frank#715`…). So the rule now exempts an explicit,
reasoned `_PUBLIC_FRANK_ISSUES = {748, 751, 759}` — same shape as the existing
`_PUBLIC_ORGS` allowlist — and still fails on any OTHER number next to
requester-words, which is the shape a private-repo number would have. R6a is the
proof it still bites. If a reviewer prefers the strict reading, the alternative
is rewriting three prose passages and one manifest comment to drop the numbers;
I judged that worse and am recording the choice rather than burying it.

<!-- fr:journal kind=finding scope=plan id=r-f7-f10-minors created=2026-08-03T18:55:45 state=fixed -->
### r-f7-f10-minors · finding [fixed] · Minors: two unasserted properties that break the container while staying green, a premature tense, a shm gap, an over-claiming docstring

**F7a — no guard against a `command:` override.** Adding
`command: ["postgres"]` to the gbrain container reads as harmless explicitness
and bypasses `docker-entrypoint.sh` entirely: no initdb, no
`/docker-entrypoint-initdb.d` (so `CREATE EXTENSION vector` never runs and the
ConfigMap becomes decorative), and — per the F1 correction — no per-boot
`chmod 00700 "$PGDATA"`, which is the thing that actually protects a populated
PGDATA from the fsGroup re-walk. That makes this guard the practical
replacement for the "OnRootMismatch is load-bearing" advice the F1 fix removed.
New `test_gbrain_does_not_override_the_image_entrypoint`.

- **R7a** add `command: ["postgres"]`: FAILED as it should.

**F7b — the startup budget was deliberate everywhere except in a test.** Both
the manifest comment and the spec call the 150 s generous on purpose (first boot
runs initdb on a freshly-provisioned Longhorn volume before `pg_isready` can
answer), and nothing asserted it. A `failureThreshold: 1` would kill the
container mid-initdb and restart it onto a half-written PGDATA. New
`test_gbrain_startup_probe_allows_time_for_initdb` asserts both
`failureThreshold > 1` and `periodSeconds * failureThreshold >= 150`.

- **R7b** `failureThreshold: 30 -> 1`: FAILED as it should.

**F8 — the README described the ssh sidecar as ALREADY carrying Bun**, in a file
whose header says it documents the DEPLOYED state. It does not: this branch does
not change the ssh image pin at all (that is the sibling agent-images plan, and
`orch-hermes-ssh-bun-repin` is a back-loaded manual op). Now a blockquote marked
"NOT YET DEPLOYED" naming both manual ops, plus future tense in the paragraph,
plus an explicit note that `gbrain` itself does NOT wait for either.

**F9 — `/dev/shm` is 64 MiB and pgvector builds HNSW indexes in parallel through
it** (DSM segments; classic symptom `could not resize shared memory segment`).
Added to the spec Named gaps WITH its fix rather than acted on: the `hindsight`
sidecar in the same pod has the identical 64 MiB and has run that way since the
2026-07-09 cutover, so this is a pre-existing family posture, not a regression
this work introduces — and pre-emptively changing only gbrain would ship an
unexercised difference between two Postgres sidecars in one pod. Fix when it
bites: an `emptyDir` `medium: Memory` at `/dev/shm` (counts against the 1 Gi
limit), or `-c max_parallel_maintenance_workers=0`.

**F10 — the module docstring claimed more than the file asserts.** It said
Hindsight "same image, same env, same mount" is "asserted here mechanically";
only the PVC size and storage disjointness are. Corrected the docstring rather
than adding the assertions, per the review preference and for a concrete reason
now written down: pinning hindsight image tag would fight the agent-images bump
workflow every month. The docstring now states the scope precisely and says why
image/env are deliberately out of it. Also documented the two vacuity classes
(last-wins parse, claimName indirection) at the top, so the next author does not
re-introduce them.

<!-- fr:journal kind=finding scope=plan id=rv2-guc-parser-bypass created=2026-08-15T16:52:24 phase=2 state=fixed -->
### rv2-guc-parser-bypass · finding [fixed] · The loopback guard was still bypassable by two GUC spellings Postgres accepts (phase 2)

`_server_settings` stored GUC names verbatim, but Postgres does not compare them
verbatim: `ParseLongOption` rewrites `-` to `_` and lookup is case-insensitive. So
`--listen-addresses=0.0.0.0` and `-c LISTEN_ADDRESSES=0.0.0.0` both bound every
interface while `settings['listen_addresses']` still read `127.0.0.1` — with
`trust`, unauthenticated superuser Postgres on the pod IP. This is the guard the
2026-08-03 round had *just* upgraded from a substring check for exactly this
reason; it was upgraded to a narrower substring check.

Fixed by normalising keys on write (`lower()`, `-`->`_`) and by additionally
recognising the space-separated `--key value` long form, which nothing had tested.
Mutation-checked across 7 spellings (both reported, plus space-form, mixed-case,
joined `-c`, and a port drift): all 7 now fail the guard, baseline unchanged.

<!-- fr:journal kind=finding scope=plan id=rv2-readiness-probe-withdraws-ssh created=2026-08-15T16:52:24 phase=1 state=fixed -->
### rv2-readiness-probe-withdraws-ssh · finding [fixed] · gbrain's readinessProbe would have withdrawn operator SSH from the LoadBalancer (phase 1)

Pod `Ready` is an all-containers condition and `service.yaml` has no
`publishNotReadyAddresses`, so a gbrain readiness failure removes the pod from
192.168.55.226 — taking SSH (22->2222) and all sixteen mosh ports with it. The
failure is self-blocking: the store you would log in to debug is what removed the
way in. It also gated nothing, since gbrain deliberately declares no `ports:` and
no Service routes to it.

Removed, and its ABSENCE is now asserted (`test_gbrain_declares_no_readiness_probe`)
together with the premise it rests on — that the Service is still Ready-gated —
because re-adding it is the most natural-looking edit anyone could make here.
`ssh` keeps its readinessProbe: there the LB withdrawal is the wanted behaviour.

<!-- fr:journal kind=finding scope=plan id=rv2-collation-provider-first-boot created=2026-08-15T16:52:25 phase=1 state=fixed -->
### rv2-collation-provider-first-boot · finding [fixed] · The cluster would have initialised with a glibc-bound libc collation, permanently (phase 1)

With no `POSTGRES_INITDB_ARGS` the image's `ENV LANG en_US.utf8` wins and initdb
builds under the LIBC provider. Measured on the pinned digest: `datlocprovider` 'c',
`datcollate` 'en_US.utf8'. That binds collation to the glibc inside the image, so a
later rebuild emits a collation-version mismatch and every text/btree index needs
REINDEX. It is a first-boot-only decision — after initdb the entrypoint never runs it
again — so the window closes the moment the volume initialises.

Fixed with `--locale-provider=builtin --builtin-locale=C.UTF-8` and guarded.
VERIFIED EMPIRICALLY against the pinned digest on amd64 rather than asserted: with
the arg, `datlocprovider` 'b' / `datlocale` 'C.UTF-8'; pgvector 0.8.6 still installs
from the initdb.d ConfigMap; an hnsw index builds and answers a `<->` query; and on a
second boot over the already-initialised volume the arg is an inert no-op with no
collation warning and the data intact. Byte-order sorting is the accepted trade and
matches the hindsight sidecar's baked C.UTF-8 recipe.

<!-- fr:journal kind=finding scope=plan id=rv2-stale-pgdata-mechanism-in-tests created=2026-08-15T16:52:26 phase=2 state=fixed -->
### rv2-stale-pgdata-mechanism-in-tests · finding [fixed] · The test file still taught the false PGDATA mechanism the rest of the branch had corrected (phase 2)

Three places in `test_hermes_gbrain_sidecar.py` — plus `_prose.md`, `02.yaml` and
`03.yaml` — still explained the failure as 'the mount root is 0775 and Postgres
refuses a data dir wider than 0750'. That is not the mechanism: the volume root is
2775, and the 0750 postmaster check is only reachable had it got past the
entrypoint's `chmod 00700 $PGDATA || :`, which EPERMs on a root-owned directory and
is swallowed. The manifests, runbook and README already carried the correction; the
test file is what a future engineer reads FIRST when the guard goes red. All five
artefacts now carry the same corrected mechanism, with the retraction stated.

<!-- fr:journal kind=finding scope=plan id=rv2-discretion-scan-missed-riskiest-file created=2026-08-15T16:52:27 phase=2 state=fixed -->
### rv2-discretion-scan-missed-riskiest-file · finding [fixed] · The discretion scan omitted the artefact most likely to leak (phase 2)

`docs/runbooks/manual-operations.yaml` was unscanned, yet it is where the
`bun install -g 'git+<client CLI repo URL>#<pinned ref>'` placeholder lives — a blank
a future operator is actively invited to fill in with the identifier the guard exists
to keep out. It could not simply be appended: it registers all 144 manual ops, and
scanning it whole imports unrelated `github.com/<org>/` hits whose only cure is
widening the allowlist, which is how such a guard rots into a rubber stamp.

Added a scoped-scan mechanism (`_scan_units()`): whole files, plus extracts scoped by
op id for partly-in-scope artefacts. Mutation-checked — injecting a private org and a
foreign-qualified issue number into the scoped text both fire. `agent-shells.md` was
measured clean and added whole. `agents/rules/frank-gotchas.md` is deliberately still
excluded, with the measurement recorded: it trips a genuine false positive from an
unrelated upstream ArgoCD citation, and this work's footprint there is one summary
line whose full prose lives in the scanned runbook.

<!-- fr:journal kind=finding scope=plan id=rv2-issue-allowlist-bare-numbers created=2026-08-15T16:52:27 phase=2 state=fixed -->
### rv2-issue-allowlist-bare-numbers · finding [fixed] · The public-issue allowlist exempted bare numbers regardless of which repo they named (phase 2)

`_PUBLIC_FRANK_ISSUES` matched on the number alone, so a private-repo reference
that happened to collide with 748/751/759 would have been exempted silently. Now the
repo qualifier is captured: an unqualified `#748` stays exempt (unambiguous in this
repo's prose) and `frank#748`/`derio-net/frank#748` are exempt, but
`someotherrepo#748` is not. Mutation-checked.

<!-- fr:journal kind=finding scope=plan id=rv2-minor-cluster created=2026-08-15T16:52:28 phase=2 state=fixed -->
### rv2-minor-cluster · finding [fixed] · Five smaller defects: vacuous initdb assertion, wrong docstring, missing schema field, probe threshold, posture (phase 2)

* The initdb ConfigMap check was two independent substrings over the concatenation
  of every .sql key, so `CREATE EXTENSION hstore;` plus the word 'vector' in a comment
  would pass. Now one regex.
* A docstring claimed 'this plan changes the ssh container's IMAGE pin' — it changes
  nothing about that container; the pin is moved by the scheduled bump workflow.
* The three new acceptance rows were the only ones of 66 omitting `levels:`. Added —
  `unit` for the two with real structural guards, an explicitly-empty `{}` with its
  reason for the JS-runtime row, which nothing in this repo can verify statically.
* `livenessProbe.failureThreshold` 3 -> 10: at 3x30s the kubelet kills Postgres
  mid-WAL-replay after an unclean stop, restarting recovery from scratch each time.
* Added `seccompProfile: RuntimeDefault`, the only field between this container and
  the `restricted` level the namespace audits at.

<!-- fr:journal kind=finding scope=plan id=rv2-prestop-shutdown-hook created=2026-08-15T16:52:29 state=refuted -->
### rv2-prestop-shutdown-hook · finding [refuted] · REFUTED: adding a preStop pg_ctl hook for graceful shutdown

Review suggested a `lifecycle.preStop` running `pg_ctl -m fast stop` as
belt-and-braces, in case plain SIGTERM (a SMART shutdown, which waits for clients)
outlived the 45s grace period. Not taken. The official postgres image sets
`STOPSIGNAL SIGINT` and containerd honours image stop signals, so fast shutdown is
already what happens; adding a redundant hook introduces a second shutdown path that
can itself fail or mask the first, on a container whose termination behaviour is not
otherwise instrumented here. The reviewer raised it as optional and I agree with the
reasoning while declining the change — recorded so the option is findable if a real
unclean-shutdown incident ever argues for it.

<!-- fr:journal kind=decision scope=plan id=rv2-manual-phase-overtaken created=2026-08-15T16:52:30 phase=4 -->
### rv2-manual-phase-overtaken · decision · Phase 4's re-pin step was overtaken by events; the verify half still stands (phase 4)

P4.T1.S1 asked the operator to re-pin `hermes-agent-shell-ssh` to an agent-images
build carrying Bun, manual because that image did not exist when the plan was written.
agent-images#158 merged 2026-08-13 as c04eaab, and the scheduled bump re-pinned frank
main (#766); rebasing this branch inherited it. So the EDIT half is done and the
manual op has been rewritten to say so — but the VERIFY half is untouched, because
ArgoCD syncs from main and `bun --version` over a LOGIN shell is a different claim
from the pin looking right. The step is deliberately NOT ticked: completing a manual
phase is the operator's, not this session's.
