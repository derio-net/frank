# Enterprise AI-Hybrid Kubernetes Platform

**Status:** Approved Specification
**IaC Strategy:** Hybrid (Ansible for Management Host, Pulumi for Cluster Infrastructure)
**Provisioning Method:** Network Boot (PXE) via Sidero Booter

## 1. Physical Infrastructure Zones

### Zone A: The Management Plane (Bootstrapped Host)

* **Hardware:** Raspberry Pi 5 (8GB RAM)
* **Hostname:** `raspi-omni`
* **OS:** Raspberry Pi OS (managed via Ansible)
* **Roles:**
  * **Sidero Omni:** Central control plane.
  * **OIDC/Identity:** Authentik (SSO).
  * **Traefik:** Reverse proxy, fetches SSL Certificates (acme.json). Could then be used by Talos bootstrapping
  * **State Backend:** Postgres (for Omni/Authentik).



### Zone B: The Core Cluster (HA Control Plane)

* **Hardware:** 3x ASUS NUCs (64GB RAM, 1TB nvme)
* **Role:** `controlplane` + `worker`
* **Hostname:** frank-mini-{1,3}
* **Storage:** **Longhorn** (Replicated Block Storage).
* **Critical Services:** Etcd, API, ArgoCD, Monitoring, Cilium Control Plane.

### Zone C: The AI Compute (GPU Acceleration)

* **Hardware:** 1x Desktop (Intel i9, 128GB RAM, **Nvidia RTX 5070**, 1TB nvme, 2x4TB SSDs)
* **Role:** `worker` (GPU Optimized)
* **Hostname:** frank-gpu-1
* **Taints:** `nvidia.com/gpu=present:NoSchedule` (Optional: prevents boring web apps from eating AI RAM).
* **Labels:** `accelerator=nvidia`, `model-server=true`.
* **Extensions:** `siderolabs/nvidia-container-toolkit`.

### Zone D: The Edge & Burst Pool

* **Hardware:** 3x Raspberry Pi 4 + 2x Legacy Desktops.
* **Role:** `worker` (General Purpose).
* **Hostname:** frank-raspi-{1,3}, frank-pc-{1,2}
* **Labels:** `tier=low-power` (Pis), `tier=standard` (Desktops).

---

## 2. Infrastructure as Code (IaC) Architecture

We will adhere to a strict separation of tools based on the target environment's capabilities.

### Layer 1: Host Provisioning (Ansible)

**Target:** `raspi-omni` (Raspberry Pi 5)
**Why:** It runs a standard Linux OS (Ubuntu), so Ansible is perfect for setting up Docker, Systemd, and firewall rules.

* **Playbook Scope:**
* Install Docker & Compose.
* Deploy `omni` and `booter` containers.
* Configure `authentik` for OIDC.
* Configure Gateway/NAT (if using the Pi as a router).



### Layer 2: Cluster Provisioning (Pulumi)

**Target:** Talos Nodes (Zones B, C, D)
**Why:** Talos is API-driven. Pulumi's Talos provider allows you to define machine configs (YAML) as objects in TypeScript/Python and apply them via the Talos API securely.

* **Stack Scope:**
* Generate Machine Secrets.
* Generate Machine Configurations (Control Plane vs. Worker vs. GPU Node).
* **Patching:** Automatically inject `allowSchedulingOnControlPlanes` and Nvidia extensions.
* **Bootstrap:** Execute `talosctl bootstrap` on the first node.
* **Kubeconfig:** Retrieve and decrypt the admin kubeconfig.



### Layer 3: Application State (ArgoCD)

**Target:** Kubernetes API
**Why:** GitOps ensures that if the cluster burns down, the applications (Manifests/Helm Charts) are restored automatically.

* **Stack Scope:** Cilium, Longhorn, Nvidia GPU Operator, KubeRay / JupyterHub.

---

## 3. Implementation Workflow

### Step 1: Management Node Setup (Ansible)

* **Input:** Inventory file pointing to `raspi-omni`.
* **Action:** Run Ansible Playbook.
* **Result:**
* Omni is running on `https://omni.lan`.
* **Booter** is listening on the network (DHCP Proxy).
* You have an "Enrollment Key" from Omni.



### Step 2: "Hands-Free" PXE Boot

* **Action:** Turn on the NUCs, the AI Desktop, and the Pis. Ensure they are set to **Network Boot (PXE)** in BIOS.
* **Process:**
1. Machines broadcast DHCP request.
2. `booter` (on `raspi-omni`) sees request, responds with the Sidero Omni ISO image.
3. Machines boot, connect to Omni, and appear in the "Unallocated" list in the Omni UI.



### Step 3: Cluster Definition (Pulumi)

You will write a Pulumi program (TypeScript recommended) to define the node roles.

```typescript
// Conceptual Pulumi Code
import * as talos from "@pulumiverse/talos";

// 1. Define the AI Node Config (Zone C)
const aiNodeConfig = new talos.machine.Configuration("ai-node", {
    clusterName: "frank-cluster",
    machineType: "worker",
    machineSecrets: secrets.machineSecrets,
    configPatches: [
        // Enable Nvidia Drivers
        JSON.stringify({
            machine: {
                install: {
                    extensions: ["ghcr.io/siderolabs/nvidia-container-toolkit:v1.17.0"]
                },
                kernel: {
                    modules: [{ name: "nvidia" }, { name: "nvidia-uvm" }, { name: "nvidia-modeset" }, { name: "nvidia-drm" }]
                }
            }
        })
    ]
});

// 2. Define Control Plane Config (Zone B)
const cpConfig = new talos.machine.Configuration("cp-node", {
    // ... config allowing scheduling on CP ...
});

```

### Step 4: The AI Stack (GitOps)

Once the cluster is up, ArgoCD will sync the **Nvidia GPU Operator**.

* **Validation:**
* Run `kubectl get nodes -L accelerator` -> Should show `nvidia`.
* Run `kubectl get runtimeclasses` -> Should show `nvidia`.
* **Workload:** Deploy a Jupyter Notebook requesting `resources: limits: nvidia.com/gpu: 1`.



---

## 4. Logical Network Diagram

| Network Flow | Source | Destination | Protocol | Purpose |
| --- | --- | --- | --- | --- |
| **Boot** | Bare Metal Nodes | `raspi-omni` (Booter) | DHCP/TFTP/HTTP | PXE Booting the OS |
| **Control** | `raspi-omni` (Omni) | All Nodes | TCP 443 | State/Upgrade Management |
| **API** | `raspi-omni` (Pulumi) | Zone B (NUCs) | TCP 6443 | Talos API Configuration |
| **Storage** | Zone B | Zone B | TCP 9500 | Longhorn Data Replication |
| **AI Work** | Zone D (Desktops) | Zone C (AI Node) | HTTP/GRPC | Sending Inference Requests |