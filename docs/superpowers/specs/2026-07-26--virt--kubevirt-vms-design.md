# Virtualization — KubeVirt, CDI, and a VM Manager

**Date:** 2026-07-26
**Layer:** `virt` (21) — Virtualization
**Status:** Designed — not deployed. Implementation is a follow-up plan.
**Supersedes:** `docs/superpowers/specs/2026-03-07--hw--vms-design.md`
**Prompted by:** `derio-homelab/kid-laptops` issue #43 (cluster-side CI), which needs
a strict subset of this.

## Why this spec exists twice

The March 2026 spec designed exactly this and was never built — it sat at
`Status: Deferred — KubeVirt never deployed (no apps/kubevirt); spec retained as
future-work reference`, and `blog/data/roadmap.yaml` still carries its reserved
`Virtual Machines — upcoming` entry.

Four months of not-building it turned out to be informative. The original spec
had one use case ("specific use cases will emerge from experimentation"). There
are now two real ones, they pull in different directions, and the version
assumptions have gone stale in a way that would have failed on first apply.
That is worth a rewrite rather than an edit.

## The two use cases

| | **A — CI VMs (kid-laptops)** | **B — Persistent Windows VM** |
|---|---|---|
| Lifetime | Minutes; one per pipeline run | Months; survives reboots |
| Disk source | `containerDisk` (OCI image) | ISO → CDI `DataVolume` → Longhorn PVC |
| Persistence | None — deliberately | Everything, including firmware state |
| Firmware | BIOS default | UEFI + SecureBoot + vTPM (hard Win11 requirement) |
| Console | Never (Ansible over SSH) | Constantly (installer, driver install, desktop) |
| Concurrency | Several at once | Exactly one |
| Needs CDI | **No** | **Yes** |
| Needs a UI | **No** | **Yes** |

The temptation is to build only A, because A is what has a ticket. That is the
wrong read: A exercises none of the storage, firmware, or console paths, so a
KubeVirt install shaped only around A would be re-architected the first time
anyone tried B. **B is what determines the shape.** A is nearly free once B works.

## Version floor — the stale assumption

Frank runs **Kubernetes v1.35.3** (Talos v1.12.6, kernel 6.18.18).

KubeVirt supports the three Kubernetes releases current at its own release date.
Per the [support matrix][matrix], v1.7 tops out at Kubernetes 1.34 — **it would
not have been a supported install on this cluster**. The floor is v1.8.

| Component | Version | Notes |
|---|---|---|
| KubeVirt | **v1.8.4** (2026-06-16) | Newest v1.8 patch; v1.9 exists but v1.8 is the conservative line on 1.35 |
| CDI | **v1.65.0** (2026-03-31) | Containerized Data Importer |
| kubevirt-manager | chart **0.6.0**, app **1.5.4** | Still maintained — releases Jan and Apr 2026 |

Pin all three. Bump via the normal upstream-watcher path, checking the matrix
each time — this is a component where "latest" and "supported" diverge.

[matrix]: https://github.com/kubevirt/sig-release/blob/main/releases/k8s-support-matrix.md

## Hardware — verified, not assumed

The March spec asserted KVM support. It has now been checked on the live cluster:

| Node | Arch | `/dev/kvm` | `cpu-cpuid.VMX` | VM-capable |
|---|---|---|---|---|
| mini-1 / mini-2 / mini-3 | amd64 | present | true | yes (control-plane) |
| gpu-1 | amd64 | present | true | yes |
| pc-1 | amd64 | present | true | yes |
| raspi-1 / raspi-2 | **arm64** | — | — | **no** |

`/dev/kvm` is present on all five x86 nodes with mode `crw-rw-rw-`, and node
feature discovery reports `feature.node.kubernetes.io/cpu-cpuid.VMX: "true"`.

**Scheduling.** VMs must be kept off the arm64 Raspberry Pis — not as a
preference but as a hard constraint, since a VMI scheduled there can never
start. Once KubeVirt is running, `virt-handler` advertises
`devices.kubevirt.io/kvm` only on capable nodes, so a resource request is
self-enforcing and preferable to a hand-maintained `nodeSelector`. Until then,
node affinity on `kubernetes.io/arch: amd64` is the belt.

`gpu-1` should additionally be excluded from general VM scheduling: it is the
GPU time-share node and a long-lived VM there would contend with Ollama and
ComfyUI. Windows goes on a mini or pc-1.

## Talos specifics

Talos enforces the **baseline** Pod Security Standard cluster-wide by default
(`kube-system` excepted). `virt-handler` and CDI's importer pods both need
`privileged`. Frank's existing idiom applies unchanged — see
`apps/root/templates/ns-longhorn.yaml` and `ns-gpu-operator.yaml`:

```yaml
metadata:
  name: kubevirt
  labels:
    pod-security.kubernetes.io/enforce: privileged
    pod-security.kubernetes.io/enforce-version: latest
    pod-security.kubernetes.io/audit: privileged
    pod-security.kubernetes.io/warn: privileged
```

One namespace each for `kubevirt` and `cdi`, both templated in `apps/root/templates/`.

No Talos machine-config change is expected: the KVM modules are already loaded
(that is what `/dev/kvm` proves), and no new kernel arguments or system
extensions are required. This is the one claim in this spec most worth
re-verifying at deploy time rather than trusting.

## Storage

VM disks are Longhorn PVCs created by CDI `DataVolume`s. Longhorn's default
class is RWO, which is correct for a single non-migrating VM.

**Live migration would need RWX** (Longhorn provides it via share-manager/NFS).
Migration is explicitly out of scope: one Windows VM pinned to one node has no
migration story worth the complexity, and CI VMs are ephemeral. Revisit only if
a VM ever needs to survive a node drain.

| Volume | Size | Class | Notes |
|---|---|---|---|
| Windows system disk | 100Gi | `longhorn` | Win11 + apps; grow later, Longhorn expands |
| Windows install ISO | 8Gi | `longhorn` | CDI import target; deletable post-install |
| virtio-win ISO | 1Gi | `longhorn` | Driver disk, mounted as a second CD-ROM |
| VM firmware state | ~1Gi (auto) | `longhorn` | vTPM + EFI NVRAM, see below |

## Windows 11 — the requirements that shape everything

Windows 11 hard-requires a TPM 2.0 and UEFI with Secure Boot. In KubeVirt that is:

```yaml
spec:
  template:
    spec:
      domain:
        features:
          smm:
            enabled: true          # required for Secure Boot
        firmware:
          bootloader:
            efi:
              secureBoot: true     # implied by efi unless set false
              persistent: true     # NVRAM survives restart
        devices:
          tpm:
            persistent: true       # vTPM survives restart
```

`persistent: true` on either field requires the **`VMPersistentState` feature
gate** on the KubeVirt CR — still gated as of v1.8. Without it the VM boots but
loses its TPM on every restart, which BitLocker and Windows activation both
notice. Set `vmStateStorageClass: longhorn` on the CR so the state PVC lands on
Longhorn rather than an unset default.

Machine type must be `q35`. Drivers come from the virtio-win ISO mounted as a
second CD-ROM during install; `virtio-win-gt-x64.msi` afterwards.

**Named gap:** Windows licensing is not addressed here. The VM will need a key.

## Components and ArgoCD layout

Three apps, following `frank-argocd.md`:

**`kubevirt`** (ns `kubevirt`) — operator manifests + a `KubeVirt` CR carrying
the `VMPersistentState` feature gate and `vmStateStorageClass`. Vendored release
YAML under `apps/kubevirt/vendor/`, matching how `apps/tekton/vendor/` is
handled, since KubeVirt ships manifests rather than a chart.

**`cdi`** (ns `cdi`) — CDI operator + `CDI` CR. Same vendoring pattern.

**`kubevirt-manager`** (ns `kubevirt-manager`) — Helm chart 0.6.0.
LoadBalancer on **192.168.55.205** (already reserved by the March spec and still
free), plus, per `plan-post-deploy-checklist.md`:
- a Traefik IngressRoute at `vms.cluster.derio.net` with `authentik-forwardauth`
- an Authentik proxy provider entry, and the manual outpost-assignment step
- a homepage tile in `apps/homepage/manifests/files/services.yaml`

The UI earns its keep on use case B specifically: its noVNC console is how you
watch a Windows installer run. `virtctl vnc` works but needs a local client and
a port-forward every time — acceptable for an occasional debug, poor for an
install that wants watching over an hour.

## What the CI use case needs (and does not)

For `kid-laptops`, once KubeVirt exists:

- a `kid-laptops-ci` namespace
- a `kid-laptops-ci-kubevirt` ServiceAccount + Role:
  `kubevirt.io` / `virtualmachineinstances` / get,list,watch,create,delete
- the containerDisk `192.168.55.210:5000/kid-laptops/fedora-ci:f43` in Zot

No CDI, no DataVolume, no PVC, no UI, no firmware config. The VMI boots from an
OCI image, gets an SSH key via `cloudInitNoCloud`, is converged against, and is
deleted. Nodes already trust Zot cluster-wide
(`patches/phase06-cicd/06-cluster-zot-registry.yaml`) and Zot allows anonymous
read, so **no pull secret is required** — the original request's requirement 6
asked for one against a Harbor that does not exist.

## Sequencing

1. **KubeVirt + CR + privileged namespace** — prove it with the stock
   `quay.io/containerdisks/fedora:43` containerDisk. Smallest possible first VM.
2. **CDI** — prove it by importing the virtio-win ISO.
3. **kubevirt-manager** — exposure, SSO, homepage tile.
4. **Windows VM** — the real target of B.
5. **kid-laptops CI namespace + RBAC** — unblocks the deferred half of #43.

Steps 1 and 5 alone would satisfy the CI request. Doing 1–4 first is the
deliberate choice: B is what proves the design.

## Named gaps

- **Talos claim unverified.** "No machine-config change required" is inferred
  from `/dev/kvm` existing. Nothing has actually started a VM on this cluster.
- **Windows licensing** — unaddressed.
- **Backup** — a Longhorn-backed VM disk is in scope for existing Longhorn
  backups, but nobody has tested restoring a VM from one.
- **Node capacity** — pc-1 has 4 vCPU / 32Gi total and already runs the CI
  workload; a persistent Windows VM plus concurrent CI VMs there would be tight.
  Placement is deferred to the implementation plan.
- **Live migration** — out of scope, RWX unproven for this workload.

## Counter-arguments considered

**"Just use Proxmox."** The Omni rebuild is already heading toward
Ansible/Proxmox, and Proxmox is a better VM host than Kubernetes by most
measures. Rejected for the CI case specifically: the kid-laptops molecule
scenario targets `kubevirt.io/v1` objects and reaches the VM over the pod
network from inside a Tekton task. Proxmox would mean rewriting their scenario
and solving cross-network SSH. For the Windows case it remains a legitimate
alternative — and if Proxmox lands first, this spec's use case B is worth
re-examining rather than assumed.

**"Skip CDI, use a containerDisk for Windows too."** containerDisks are
read-only and ephemeral by construction; the writable layer is discarded on
stop. Precisely wrong for a VM whose whole point is persistence.

**"Skip the UI."** Defensible on security grounds — it is another exposed
surface. Rejected because a Windows install without a console is not debuggable,
and the forward-auth + homepage-tile path is well-worn on Frank by now.

## Test plan (post-deploy, operator-driven)

1. `kubectl get kubevirt -n kubevirt kubevirt -o jsonpath='{.status.phase}'` → `Deployed`.
2. Boot a stock Fedora containerDisk VMI; `virtctl console` reaches a login prompt.
3. Confirm the VMI is scheduled on an amd64 node and that no VMI can schedule
   onto a raspi.
4. CDI: import the virtio-win ISO into a DataVolume; PVC `Bound`, importer pod
   `Succeeded`.
5. kubevirt-manager reachable at `vms.cluster.derio.net`, gated by Authentik,
   listing the VMI from (2).
6. Windows VM: installs, reboots, and **retains its vTPM across a full
   stop/start** — this is the specific claim `VMPersistentState` exists for and
   the one most likely to be silently wrong.
7. Delete every test object; confirm no orphaned PVCs.
