# Omni legacy-config recovery

Break-glass tooling for one specific Omni v1.5 failure: **a rollback that Omni
never resends.**

## When you need this

A cluster-wide ConfigPatch rebooted machines (e.g. a `machine.files` entry Talos
rejects — see [`omni.md`](../../docs/runbooks/frank-gotchas/omni.md), *"Talos
`machine.files create` must stay under `/var`"*). You reverted the patch, and
some machines came back while others stayed on the bad config.

The reason is a hash race. Omni v1.5 had already pushed the reboot-requiring bad
config **without confirming it**. Reverting restored the original desired config,
whose recorded hash still matches what Omni believes it sent — so Omni sees no
divergence and never resends the rollback to the machines that persisted the bad
version. They sit there, wrong, indefinitely.

Symptoms: `omnictl get clustermachinestatuses` shows machines that are not
`stage 4` / `ready` / `configuptodate`, and reverting the patch changed nothing.

## What it does

Writes a harmless per-machine marker file under `/var`. **The file does nothing —
the point is the hash change**, which forces Omni to send each node its full
corrected config. Once every machine is stable, the markers are deleted.

## Procedure

```bash
cd scripts/omni-legacy-recovery

./force-recovery.sh --dry-run   # inspect the generated patches first
./force-recovery.sh --apply     # write the markers
./wait-recovery.sh              # block until every machine is stable
./remove-recovery.sh            # clean up — ONLY after wait exits 0
```

All three read `.env` and `.env_devops` from the repo root. They default
`BASE_REPO` to their own checkout and fail with a clear message if those files
are absent — which is what happens inside an fr worktree, since `.talos/` is
gitignored and not carried there. Set `BASE_REPO` to the operator checkout:

```bash
BASE_REPO=~/Docs/projects/DERIO_NET/frank ./force-recovery.sh --dry-run
```

## Three things that will bite you

**The marker content must change on every run.** The mechanism *is* the hash
change. The original incident scripts hardcoded the content and had to be
hand-bumped (`…-v1`, `-v2`, `-v3`) because re-running with identical content
produces no hash change and therefore no resend — a no-op that looks exactly
like the problem you are trying to fix. `force-recovery.sh` timestamps the
marker so this cannot happen.

**One healthy sample is not recovery.** Omni can report a config applied
immediately *before* a scheduled reboot. `wait-recovery.sh` requires every
machine stable across `STABLE_SAMPLES` consecutive polls (default 6 × 10s) and
exits non-zero on timeout. Do not remove the patches until it exits 0.

**Machines are derived from Omni, never hardcoded.** The original scripts pinned
seven UUIDs. Those UUIDs are hardware-derived and survived the Omni rebuild, so
they would still work today — but a replaced node would be silently skipped, and
"all recovered" would be measured against the wrong denominator. Both scripts
query Omni instead.

## Provenance

Reconstructed from the scratch scripts used during the 2026-08-01 dual-issuer
authentication incident, which took out etcd quorum on all three control planes.
Incident write-up: `docs/superpowers/journals/debug/2026-08-01-structured-auth-machine-files.md`.
Runbook prose: `docs/runbooks/frank-gotchas/omni.md`.

Never exercised end-to-end since that incident; the generation path is covered by
`scripts/tests/test_omni_recovery_tooling.py`, and `--dry-run` is safe to run any
time to confirm it still renders a patch per live machine.
