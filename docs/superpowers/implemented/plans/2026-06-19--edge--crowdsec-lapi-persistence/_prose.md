# CrowdSec LAPI Persistence — Fix the Broken Ban Pipeline

> Plan for spec `docs/superpowers/specs/2026-06-19--edge--crowdsec-lapi-persistence-design.md`.
> Layer: edge (Hop). Single repo: `derio-net/frank`. Fully agentic — no manual phase.

## Why

Malicious scanners hitting the public blog edge aren't banned even though CrowdSec is
"Synced/Healthy." The LAPI's SQLite DB lives in an **emptyDir**; every LAPI pod restart wipes
it — including the CrowdSec agent's registered-machine row. The still-running agent then fails
its next LAPI call with `ent: machine not found` and **crashloops**, so it parses zero Caddy
logs and produces zero ban decisions. The LAPI **config** volume (community-blocklist console
enrollment) is wiped the same way — a second latent bug.

## Approach

Persist **both** LAPI volumes onto static `hostPath` PVs (`type: DirectoryOrCreate`) carved as
subdirectories of the already-attached Hetzner Volume — no new volume, no manual `mkdir`, fully
GitOps. The chart's PVC template has no `volumeName`, and Hop has no default StorageClass, so
each PV sets `storageClassName: hetzner-volume` and is pinned to its chart PVC from the PV side
via `claimRef`. The storage app's `sync-wave: -1` guarantees the PVs exist before the chart
creates its PVCs.

### The load-bearing coupling (guarded by the TDD test)

```
PV.claimRef.name  ==  "<helm releaseName>-db-pvc"  ==  chart PVC name
```

`releaseName: crowdsec` ⇒ `crowdsec-db-pvc` / `crowdsec-config-pvc`. A chart bump that renames
the PVCs, or a `releaseName` change, would silently break binding (PVC Pending → LAPI down → no
bans — the exact failure we're fixing, now silent). The Phase 1 test reads `releaseName` live
from the Application CR and asserts each `claimRef.name` matches the derived chart PVC name.

## Phases

1. **Persist LAPI data + config (TDD).** RED: a pytest guard (`scripts/tests/`) asserting PV
   shape, values, size-fits-capacity, and the claimRef coupling. GREEN: add the two hostPath
   PVs; enable `lapi.persistentVolume.{data,config}` with `storageClassName: hetzner-volume`;
   rewrite the values comment. Test goes green; full `scripts/tests/` suite stays green.
2. **Docs (fix/extension of the edge-observability layer).** Hop-gotchas one-liner + obs-digest
   cross-ref; retroactive building/operating post updates; refresh the two CrowdSec manual-op
   notes (now durable) + `/sync-runbook`. No new blog post (fix/extension policy).

## Verification

- **In-PR:** the Phase 1 pytest, run locally (`uv run --with pytest --with pyyaml python -m
  pytest scripts/tests/test_crowdsec_lapi_persistence.py -q`). The repo has no general CI job
  for `scripts/tests/`, so this is a developer/local guard, not a PR gate.
- **Post-merge (operator-driven, agent runs the checks):** the spec's `## Test Plan` — PVs
  Bound; the **mandatory one-time agent DaemonSet roll** at cutover (the agent registers only in
  an initContainer, so it does NOT self-heal the emptyDir→persistent transition); then agent
  Running with no `machine not found`, `cscli machines list` validated, persistence survives a
  `rollout restart` of the LAPI, and the real end-to-end proof: replay sensitive-file probes from
  an allowed source → a `ban` appears in `cscli decisions list` and the Caddy bouncer returns
  403. Only then is the layer marked **Deployed**.

## Out of scope

Agent-side config persistence; scenario/collection tuning; migrating Hop to a dynamic provisioner.
