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
