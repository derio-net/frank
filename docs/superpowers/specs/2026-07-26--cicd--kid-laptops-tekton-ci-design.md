# kid-laptops CI on Frank — cluster-side design

**Date:** 2026-07-26
**Layer:** `cicd` (19) — CI/CD Platform
**Status:** Designed
**Answers:** `derio-homelab/kid-laptops` issue #43 and `docs/ci/frank-infra-request.md`
**Companion:** [`2026-07-26--virt--kubevirt-vms-design.md`](2026-07-26--virt--kubevirt-vms-design.md)
  — the hypervisor half, deliberately not built here.

## Scope in one sentence

Everything in the request that does not need a hypervisor, built now; the VM half
named, deferred, and specified rather than half-built.

The request assumes KubeVirt exists on Frank. **It does not** — no CRDs, no
operator, nothing. That is a whole layer (companion spec), so this run ships the
CI that can go green today and reports the rest back rather than leaving a
pipeline that can never pass.

## Two corrections to the request's premises

Both are load-bearing, and both were stated the wrong way round.

**1. The registry is Zot, not Harbor.** `harbor.frank.derio.net` does not exist
and never has. Frank's OCI registry is **Zot at `192.168.55.210:5000`**. Two
consequences make this better than the request assumed:

- every node already trusts it cluster-wide via
  `patches/phase06-cicd/06-cluster-zot-registry.yaml`, and
- Zot's `accessControl` grants `anonymousPolicy: ["read"]`,

so **requirement 6's pull secret is not needed at all**. Only push needs
credentials, and `zot-push-creds` already exists in `tekton-pipelines`.
Coordinates become `192.168.55.210:5000/kid-laptops/fedora-ci:f43`.

**2. The build host claim is inverted.** `provisioning/build-containerdisk.sh`
says *"Not on the operator's MacBook. That machine has packer and docker but no
qemu-system-x86_64 … This script runs on frank, which has the hypervisor."*

Measured, both halves are backwards:

| | MacBook | Frank |
|---|---|---|
| CPU | Intel Core i9-9980HK (**x86_64**) | x86_64 |
| `qemu-system-x86_64` | **present**, HVF-accelerated | absent |
| `packer` | present | absent |
| `docker` | present | absent (containerd, no shell) |
| `mkksiso` | absent (Linux-only, from `lorax`) | absent |

Frank runs **Talos**: immutable, no package manager, no shell, no hypervisor
tooling. It cannot run that script at all. The MacBook is Intel, so x86 guests
run under HVF at near-native speed — no emulation penalty. **The containerDisk
gets built on the laptop and pushed to Zot**, which is also what the operator
chose.

The one real laptop gap is `mkksiso`, and it is incidental: kid-laptops' *other*
packer template (`kid-laptops-box.pkr.hcl`) already serves its kickstart over
HTTP from `provisioning/packer/http/`. Only the containerDisk template reached
for `mkksiso`. Converging the two removes the sole Linux-only dependency.

## Requirement-by-requirement

| # | Request | Verdict |
|---|---|---|
| 1 | Confirm Tekton install + git resolver | **Answered** — below |
| 2 | Gitea repo synced from GitHub | **Built** — push-sync, not pull-mirror |
| 3 | Push webhook → EventListener | **Built** + one manual webhook step |
| 4 | TriggerBinding + TriggerTemplate | **Built** |
| 5 | ServiceAccount + RBAC for VMIs | **Built** — RBAC needs no CRD to exist |
| 6 | Harbor project + robot + pull secret | **Re-pointed to Zot**; pull secret unnecessary |
| 7 | Build and publish the containerDisk | **Deferred** — laptop build, once KubeVirt lands |
| 8 | Stretch: GitHub commit status | **Deferred** — mechanism named below |

### 1 — Tekton install (answer)

| | |
|---|---|
| Pipelines | **v1.6.0** |
| Triggers | **v0.34.0** |
| Dashboard | v0.63.1 (`192.168.55.217:9097`) |
| Namespace | `tekton-pipelines` |
| Resolvers | `tekton-pipelines-resolvers` (separate namespace) |
| `enable-git-resolver` | **`true`** |

The resolver flag lives in `resolvers-feature-flags` in the **resolvers**
namespace, not in `feature-flags` in `tekton-pipelines` — looking in the obvious
place returns `NotFound` and reads like "not installed". It is installed and on,
so `pipelineRef.resolver: git` works and the design's central decision stands.

### 2 — Gitea sync: push, not pull

No `derio-homelab` org and no kid-laptops mirror exist in Gitea today (confirmed
via the admin API; the request was right to ask rather than assume).

Frank already has a proven GitHub→Gitea path used by every `agentic-stoa` repo:
a GitHub webhook hits `el-github-listener`, which runs the **`github-pull-sync`**
Pipeline — a full clone from GitHub and a `git push --force` into Gitea over SSH.

This is chosen over a Gitea pull-mirror precisely because of the concern the
request raises: a pull-mirror's sync does not reliably fire push webhooks, and
would need polling. A **real push** produces a **real push webhook**. The request
named this trade-off and the push path resolves it rather than working around it.

New: a Gitea org `derio-homelab`, repo `kid-laptops`, **public within Gitea**.

Public is required, not cosmetic: Tekton's git resolver in URL mode — the mode
the contract pins — has no way to pass credentials. Gitea is LAN-only
(192.168.55.209, no ingress, no public DNS) and there is precedent in the public
`tekton-bot/frank` mirror. **Trade-off accepted and stated: a repo that is
private on GitHub is readable by anything on the LAN that can reach Gitea.**

### 3 — Webhook → EventListener

Two hops, matching the existing stoa topology:

```
GitHub push ──▶ webhooks.hop.derio.net (Caddy on Hop, over Tailscale)
            ──▶ el-github-listener (192.168.55.223:8080)
            ──▶ github-pull-sync ──▶ force-push into Gitea
                                 ──▶ Gitea push webhook
                                 ──▶ el-gitea-listener
                                 ──▶ kid-laptops PipelineRun
```

**Manual step, and the one most likely to be forgotten:** adding a trigger to
`gitea-listener` provisions nothing that delivers to it. The Gitea webhook is a
separate, per-repo, manual API call. The failure mode is maximally deceptive —
the mirror syncs, everything reads green, and no PipelineRun is ever created.
This is a known Frank trap (it bit the `site`→www promotion the day before this
spec). Recorded as a manual operation.

**Defect this design must not introduce.** The generic `gitea-push` trigger
filters on `!body.repository.full_name.startsWith('agentic-stoa/')` — so a
`derio-homelab/kid-laptops` push would *also* fire the generic `gitea-ci`
pipeline, producing a second, failing PipelineRun on every push. The filter must
exclude `derio-homelab/` too. A tripwire test asserts this stays true.

### 4 — TriggerBinding + TriggerTemplate

Produces exactly `ci/tekton/pipelinerun-example.yaml`, in namespace
`kid-laptops-ci`:

- `repo-url` — the Gitea clone URL
- `revision` — `body.after`, the pushed **SHA** (not a branch), so the resolved
  pipeline and the code under test are the same commit
- `run-id` — `<short-sha>-$(uid)`, where the short SHA comes from a CEL overlay
  and `$(uid)` is Tekton Triggers' built-in random postfix.

  The request is emphatic here: two concurrent runs sharing a `run-id` create and
  destroy each other's VM. `$(uid)` alone is the obvious choice but is documented
  only as *"a random value, just like the postfix generated by … `generateName`"*
  — random, not guaranteed unique. Concatenating the short SHA makes a collision
  require two concurrent runs on the *same commit* **and** a `$(uid)` collision,
  and it makes the VMI name greppable back to a commit. Costs nothing; the
  failure it prevents is a silently destroyed VM in someone else's run.
- workspace `source` — `volumeClaimTemplate`, 2Gi, `longhorn-cicd`

`taskRunSpecs` binds `kid-laptops-ci-kubevirt` to the two molecule tasks only, so
clone and lint stay unprivileged — kept verbatim from the contract even though
those tasks are skipped for now.

`tekton-triggers-sa` currently has a RoleBinding in `tekton-pipelines` only, so
it gains one in `kid-laptops-ci` — otherwise the EventListener cannot create the
PipelineRun there.

### 5 — ServiceAccount + RBAC

Built now, despite KubeVirt's absence: **RBAC rules are strings**, and the API
server does not validate that `kubevirt.io/virtualmachineinstances` resolves to
an installed CRD. The SA, Role and RoleBinding can therefore exist and be correct
ahead of the hypervisor, and requirement 5 is satisfiable today.

Namespace `kid-laptops-ci`, SA `kid-laptops-ci-kubevirt`, verbs exactly as
requested. It cannot be *proven* until KubeVirt lands — `kubectl auth can-i` will
answer `yes` for a resource that does not exist yet, which is a true answer to a
question nobody should mistake for an end-to-end proof.

### 6 — Registry

Zot repo `kid-laptops/fedora-ci`. Push via the existing `tekton-push` account and
`zot-push-creds`; pull anonymous. Nothing to create beyond the coordinates
agreeing in three places, which is the companion kid-laptops PR's job.

### 7 — containerDisk (deferred)

Not buildable in-pipeline today and not built here. When KubeVirt lands: build on
the laptop with the HVF-accelerated qemu already installed, and push to Zot. The
`mkksiso`→HTTP-kickstart change makes the script actually runnable there.

### 8 — GitHub commit status (deferred, mechanism named)

Not achievable purely cluster-side. Tekton cannot append a reporting step to a
pipeline it does not own, and this pipeline is resolved from kid-laptops' repo at
the tested commit — by design. The mechanism, for whoever picks it up:

- a `finally` task in `ci/tekton/pipeline.yaml` posting to GitHub's status API
  (frank's `apps/tekton/tasks/github-status.yaml` is a working model), plus
- a GitHub token Secret in `kid-laptops-ci`, minted by the same App-installation
  generator as the mirror credential, needing `statuses:write`.

Deferring is also right on sequencing: a merge gate that gates on lint alone,
while the molecule half is skipped, would assert more confidence than the
pipeline currently earns.

## Credential

The mirror needs read access to a **private repo in a third GitHub org**.
`derio-homelab` is neither `derio-net` nor `agentic-stoa`, so neither existing
generator covers it. Following the established least-privilege pattern: install
the existing `derio-fr-automation` App (3994132) into `derio-homelab`, and add a
`github-app-derio-homelab` ClusterGenerator + ExternalSecret.

ESO resolves `auth.privateKey.secretRef` in the **consuming ExternalSecret's**
namespace and ignores `secretRef.namespace` — so the App private key must exist
in `tekton-pipelines`. This exact trap left `frank-gitops-push` in
`SecretSyncedError` for seven days while ArgoCD stayed green, so it is called out
here rather than discovered again.

Capturing the new `installID` is a manual step (GitHub UI).

## What ships

```
apps/tekton/triggers/eventlistener-github.yaml   # + kid-laptops main-sync trigger
apps/tekton/triggers/eventlistener.yaml          # + kid-laptops CI trigger;
                                                 #   generic filter excludes derio-homelab/
apps/tekton/triggers/kid-laptops-ci.yaml         # TriggerBinding + TriggerTemplate
apps/tekton/manifests/clustergenerator-derio-homelab-github-app.yaml
apps/tekton/manifests/externalsecret-derio-homelab-github-mirror.yaml
apps/tekton/manifests/kid-laptops-ci-rbac.yaml   # ns, SA, Role, RoleBindings
apps/root/templates/ns-kid-laptops-ci.yaml
scripts/tests/test_kid_laptops_ci_triggers.py    # tripwires
docs/runbooks/manual-operations.yaml             # + 4 manual ops
```

## Manual operations

1. Install the `derio-fr-automation` GitHub App into `derio-homelab`; record `installID`.
2. Create the Gitea org `derio-homelab` and public repo `kid-laptops`; grant the
   Gitea push bot write access.
3. Create the GitHub webhook on `derio-homelab/kid-laptops` → `webhooks.hop.derio.net`.
4. Create the **Gitea** push webhook on the mirror → `el-gitea-listener`.

## Test plan (post-merge, operator-driven)

1. Push a trivial commit to `derio-homelab/kid-laptops` on GitHub.
2. Confirm `el-github-listener` logs the event and a `github-pull-sync`
   PipelineRun succeeds.
3. Confirm the commit appears in Gitea at the same SHA.
4. Confirm `el-gitea-listener` logs the mirror's push and creates **exactly one**
   PipelineRun in `kid-laptops-ci` — not two. A second `gitea-ci-*` run means the
   generic-trigger exclusion regressed.
5. `tkn pipelinerun logs -f` — `clone`, `lint`, `syntax`, `unit-tests` succeed;
   `molecule-base` and `molecule-teardown` report **skipped**, not failed.
6. Confirm the run is green overall.
7. `kubectl auth can-i create virtualmachineinstances -n kid-laptops-ci
   --as=system:serviceaccount:kid-laptops-ci:kid-laptops-ci-kubevirt` → `yes`.
8. Report the run on kid-laptops#43. **Do not flip acceptance rows** —
   `every-push-runs-ci-pipeline` is only partly satisfied while molecule is
   skipped, and `base-role-verified-in-ci-vm` is not satisfied at all.

## Named gaps

- **The pipeline is green without testing the thing the repo exists to test.**
  `roles/base` is not verified against anything until KubeVirt lands. A green
  check that means less than it appears to is a real hazard; the report and the
  acceptance rows must both say so plainly.
- **Gitea push identity** — reusing the existing `stoa-bot` SSH key for a
  non-stoa repo is expedient and badly named. Worth a rename pass when a third
  consumer appears.
- **No alerting** on mirror-sync failure. If `github-pull-sync` starts failing,
  CI silently tests stale code. Not addressed here.
