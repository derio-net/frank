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
