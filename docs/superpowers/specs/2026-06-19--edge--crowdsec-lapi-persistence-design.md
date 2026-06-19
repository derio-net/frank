# CrowdSec LAPI Persistence — Fix the Broken Ban Pipeline on Hop

**Layer:** edge (Hop — `clusters/hop/apps/crowdsec`, `clusters/hop/apps/storage`)
**Status:** Deployed (verified end-to-end 2026-06-19 — PR #583 persistence + #584 `container_runtime: containerd` together fixed the broken ban pipeline; a real scan now produces a local ban, bouncer-enforced)
**Date:** 2026-06-19
**Repo:** `derio-net/frank` (single-repo)
**Extends:** Layer 31 edge-observability (`blog/content/docs/building/31-edge-observability`, `operating/26-edge-observability`)

## Implementation Plans

| Plan | Target repo | Slug | Status |
|------|-------------|------|--------|
| 2026-06-19--edge--crowdsec-lapi-persistence | `derio-net/frank` | `2026-06-19--edge--crowdsec-lapi-persistence` | — |

## Problem — proven live, today

Malicious scanners hitting the public blog edge are **not being banned**, despite CrowdSec
being deployed and "Synced/Healthy" in ArgoCD. Operator evidence (2026-06-19):

| IP | Hits / span | Paths | Scenario that *should* have fired |
|----|-------------|-------|-----------------------------------|
| `4.201.96.144` | 300 in 81s (222/min) | WordPress webshell names (`wp_filemanager.php`, `jj.php`, …) | `crowdsecurity/http-sensitive-files` |
| `45.148.10.200` (`l9explore/1.2.2`) | 53 in 1s (~3000/min) | `.env`, `.env.production`, `.git/config`, `aws.env`, … | `crowdsecurity/http-sensitive-files` (textbook trigger) |
| `161.97.125.94` | 9 in 28s | `app/etc/env.php`, `.mcp/settings.json`, `.gitlab-ci.yml` | `crowdsecurity/http-sensitive-files` (likely) |
| `91.92.241.196` | 2 | `.git/config`, `.git/HEAD` | none — genuinely too sparse |

Timing is **not** the cause: the three main scanners hit in dense bursts that would blow
through any leaky-bucket capacity instantly. The pipeline itself is broken — no logs are
being parsed, so no decisions are produced.

## Root cause

`clusters/hop/apps/crowdsec/values.yaml` disables both LAPI persistent volumes
(`lapi.persistentVolume.data.enabled: false`, `config.enabled: false`), so the LAPI's
SQLite DB (`/var/lib/crowdsec/data/crowdsec.db`) lives in an **emptyDir**. On every LAPI
pod restart the DB — including the **agent's registered-machine row** — is wiped. The
CrowdSec **agent** (which tails Caddy logs and runs the scenarios) still holds its machine
credentials from the previous LAPI, so its next call to the now-empty LAPI fails with
`ent: machine not found`, and the agent **crashloops**. A crashlooping agent parses zero
Caddy logs → fires zero scenarios → produces zero decisions → bans nothing.

The original `emptyDir` choice was justified in a code comment as "avoid burning a Hetzner
Volume." That conflates a **subdirectory** on the already-attached Hetzner Volume with a
whole new volume — Hop's other stateful apps (caddy, headscale) already persist into
subdirectories of `/var/mnt/hop-data/` at zero extra cost.

### Second, latent bug (same class)

The LAPI **config** volume (`/etc/crowdsec`) holds `online_api_credentials.yaml` — the
community-blocklist **console enrollment** set by the `obs-crowdsec-community-blocklists`
manual-op. With config in emptyDir, every LAPI restart also wipes that enrollment, silently
forcing a manual re-enroll. Persisting config fixes this too. The chart's init container
seeds config with `cp -nR` (no-clobber), so a persistent config is seeded once then preserved.

## Approach (decided)

Persist **both** LAPI volumes onto static PVs backed by the existing Hetzner Volume, fully
declaratively (no manual node step), and pin the binding deterministically.

### Decisions

1. **Persist scope:** data **and** config. Kills the reported crashloop *and* the
   enrollment-wipe latent bug.
2. **PV backing:** `hostPath` PVs with `type: DirectoryOrCreate`. Hop's `hetzner-volume`
   StorageClass is `no-provisioner` (static PVs only) and has **no default** SC. A `local:`
   PV (the caddy/headscale convention) requires the directory to pre-exist on the node — an
   undocumented manual `mkdir`. `hostPath` + `DirectoryOrCreate` makes kubelet create the
   directory on first mount, so the fix is 100% GitOps with **zero manual phase** — aligned
   with the cluster's "declarative everything" value. Acceptable here: single-node edge,
   `crowdsec-system` is already PSA `privileged`, the chart pod runs on the only node.
3. **Binding:** the chart's PVC template supports `storageClassName`/`existingClaim` but
   **not** `volumeName`. So set `storageClassName: hetzner-volume` in values (required — no
   default SC, else PVC hangs Pending forever) and pin each static PV from the PV side via
   `claimRef` to the chart's PVC name. The chart names them `<release>-db-pvc` and
   `<release>-config-pvc`; the Application sets `releaseName: crowdsec` ⇒
   `crowdsec-db-pvc` and `crowdsec-config-pvc` in namespace `crowdsec-system`.

### The load-bearing coupling

The binding works **only** while three values agree:

```
PV.claimRef.name  ==  "<helm releaseName>-db-pvc"  ==  chart PVC name
```

A chart bump that renames the PVC, or a change to `releaseName`, silently breaks the binding
(PVC Pending → pod stuck → agent down → no bans — the exact failure we are fixing, now
*silent*). This invariant is the regression risk and must be guarded by a test (below).

## Files changed

1. **`clusters/hop/apps/storage/manifests/pv-crowdsec-data.yaml`** (new) — hostPath PV
   `crowdsec-data`, `type: DirectoryOrCreate`, path `/var/mnt/hop-data/crowdsec/data`,
   `storageClassName: hetzner-volume`, `1Gi`, `ReadWriteOnce`, `persistentVolumeReclaimPolicy: Retain`,
   `claimRef → crowdsec-system/crowdsec-db-pvc`, nodeAffinity `kubernetes.io/hostname Exists`.
2. **`clusters/hop/apps/storage/manifests/pv-crowdsec-config.yaml`** (new) — same shape,
   name `crowdsec-config`, path `/var/mnt/hop-data/crowdsec/config`, `128Mi`,
   `claimRef → crowdsec-system/crowdsec-config-pvc`.
3. **`clusters/hop/apps/crowdsec/values.yaml`** — set
   `lapi.persistentVolume.data.enabled: true` + `storageClassName: hetzner-volume` (size `1Gi`)
   and `lapi.persistentVolume.config.enabled: true` + `storageClassName: hetzner-volume`
   (size `100Mi`); rewrite the leading comment to explain durable LAPI state (replacing the
   "avoid burning a volume" rationale). Keep the bouncer-registration `postStart` hook — it
   is idempotent and still seeds the bouncer on a fresh (first-deploy) persistent DB.
4. **`scripts/tests/test_crowdsec_lapi_persistence.py`** (new) — TDD guard for the coupling
   and the values (see Verification).
5. **Docs (fix/extension):** one-liner in `agents/rules/frank-gotchas.md` (or
   `hop-gotchas.md`) + full prose in the matching per-topic runbook; retroactively update the
   edge-observability building post (gotcha) and operating post (the now-durable LAPI state +
   verification commands). No new blog post (fix/extension policy).

## Manual operations impact

- **No new manual op** (hostPath `DirectoryOrCreate` removes the only candidate).
- Existing CrowdSec manual-ops (`obs-crowdsec-bouncer-api-key`, `obs-crowdsec-community-blocklists`)
  become **one-time / durable** rather than "re-run after every restart." Update their notes;
  run `/sync-runbook` if any block text changes.

## Verification (TDD test — developer/local guard)

`scripts/tests/test_crowdsec_lapi_persistence.py` (pytest, mirrors existing `scripts/tests/`
style — **note:** the repo has no general CI job running `scripts/tests/`, so this is a
local/manual regression guard, run via
`uv run --with pytest --with pyyaml python -m pytest scripts/tests/test_crowdsec_lapi_persistence.py -q`,
not a PR gate). It parses the YAML and asserts:

- Both PV manifests: `kind: PersistentVolume`, `hostPath.type == DirectoryOrCreate`,
  `storageClassName == hetzner-volume`, `persistentVolumeReclaimPolicy == Retain`,
  `accessModes == [ReadWriteOnce]`, hostPath under `/var/mnt/hop-data/crowdsec/`.
- `values.yaml`: `lapi.persistentVolume.{data,config}.enabled == true`, both
  `storageClassName == hetzner-volume`, sizes (`data 1Gi`, `config 100Mi`) **≤** the matching
  PV capacity.
- **The coupling:** each PV's `claimRef.{namespace,name}` equals the chart-derived PVC name
  for `releaseName` read live from `clusters/hop/apps/root/templates/crowdsec.yaml`
  (`<release>-db-pvc` / `-config-pvc`, namespace `crowdsec-system`). Fails loudly if the
  release name or chart naming drifts.

## Test Plan (post-merge — operator-driven; agent runs the checks)

After the operator merges and ArgoCD syncs the storage + crowdsec apps on Hop
(`source .env_hop`):

1. **PVs bind:** `kubectl get pv crowdsec-data crowdsec-config` → both `Bound` to
   `crowdsec-system/crowdsec-db-pvc` / `-config-pvc`.
2. **MANDATORY cutover step — re-register the agent.** The CrowdSec agent is a **DaemonSet**
   that registers its machine **only in an initContainer** (`cscli lapi register`). On the
   emptyDir→persistent cutover the new LAPI DB is fresh-empty and the running agent keeps stale
   creds → it crashloops `ent: machine not found` and does **not** self-heal (a container
   crash-restart never re-runs initContainers; the agent pod template is unchanged so kubelet
   won't recreate it). Force the re-registration once:
   `kubectl -n crowdsec-system rollout restart daemonset/crowdsec-agent`.
3. **Agent healthy:** `kubectl -n crowdsec-system get pods` → agent `Running`, restart count
   stops climbing; `kubectl -n crowdsec-system logs daemonset/crowdsec-agent | grep -i "machine not found"`
   → empty after the step-2 restart.
4. **Machine validated:** `kubectl -n crowdsec-system exec deploy/crowdsec-lapi -- cscli machines list`
   → the agent machine present and **validated** (`✔`).
5. **Persistence survives restart:** `kubectl -n crowdsec-system rollout restart deploy/crowdsec-lapi`,
   wait Ready, re-run step 3/4 → still validated, agent does **not** crashloop (this time WITHOUT
   an agent restart — proving the machine row now persists, which step 2 did not exercise).
6. **End-to-end ban (the real proof):** from an allowed test source, replay a burst of
   sensitive-file probes against the public edge (e.g. ~15× `curl -s https://blog.derio.net/.env`,
   `/.git/config`, `/.env.production`), then
   `kubectl -n crowdsec-system exec deploy/crowdsec-lapi -- cscli decisions list` → a `ban`
   decision for the test source IP; a follow-up request from that IP returns **403** at the
   Caddy bouncer. (Use a disposable/VPN egress so the operator's own IP isn't banned.)
7. **Community blocklist intact:** `cscli decisions list` still shows community-blocklist
   entries after the LAPI restart in step 5 (proves config persistence).

Only after steps 1–7 pass is the layer marked **Deployed**.

## Out of scope

- Persisting the **agent** config (`agent.persistentVolume.config` stays `false`). The agent
  re-registers via its initContainer when the DaemonSet is rolled — required **once** at cutover
  (Test Plan step 2); thereafter the machine row is durable in the persistent LAPI DB and
  survives every later LAPI restart with no agent action.
- Wiring `scripts/tests/` into a CI job (no general test workflow exists today; a repo-wide job
  would also surface a pre-existing unrelated failure first). The guard is a developer/local
  TDD check — worthwhile follow-up, out of scope here.
- Tuning scenario capacities / adding new collections.
- Migrating Hop to a dynamic storage provisioner.
