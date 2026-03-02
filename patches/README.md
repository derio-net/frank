# Frank Cluster Config Patches & Deployment Runbook

Machine ID mapping:
| Machine ID | Hostname | IP | Role |
|-----------|----------|-----|------|
| `ce4d0d52-6c10-bdc9-746c-88aedd67681b` | mini-1 | 192.168.55.21 | control-plane |
| `6ea7c1c6-6ba6-b59d-c77a-88aedd676447` | mini-2 | 192.168.55.22 | control-plane |
| `d1f01c97-d17e-e3ef-12ee-88aedd6768b6` | mini-3 | 192.168.55.23 | control-plane |
| `03ff0210-04e0-05b0-ab06-300700080009` | gpu-1 | 192.168.55.31 | worker |
| `03de0294-0480-05ab-3106-410700080009` | pc-1 | 192.168.55.71 | worker |
| `30303031-3030-3030-3662-353662376100` | raspi-1 | 192.168.55.41 | worker |
| `30303031-3030-3030-3337-613762353000` | raspi-2 | 192.168.55.42 | worker |

## Phase 1: Node Labels & Control Plane Scheduling

### Step 1a: Allow scheduling on control planes

```bash
source .env_devops
omnictl apply -f patches/01-cluster-wide-scheduling.yaml
```

Verify:
```bash
source .env
kubectl describe node mini-1 | grep -A 2 "Taints:"
# Expected: Taints: <none>
```

### Step 1b: Apply node labels (all nodes)

```bash
source .env_devops
omnictl apply -f patches/03-labels-mini-1.yaml
omnictl apply -f patches/03-labels-mini-2.yaml
omnictl apply -f patches/03-labels-mini-3.yaml
omnictl apply -f patches/03-labels-gpu-1.yaml
omnictl apply -f patches/03-labels-pc-1.yaml
omnictl apply -f patches/03-labels-raspi-1.yaml
omnictl apply -f patches/03-labels-raspi-2.yaml
```

Or apply all at once:
```bash
source .env_devops
for f in patches/03-labels-*.yaml; do omnictl apply -f "$f"; done
```

Verify:
```bash
source .env
kubectl get nodes -L zone,tier,accelerator,igpu,model-server
```

Expected:
```
NAME      ROLES           zone         tier        accelerator   igpu          model-server
gpu-1     <none>          ai-compute   standard    nvidia                      true
mini-1    control-plane   core         standard    amd-igpu      radeon-780m
mini-2    control-plane   core         standard    amd-igpu      radeon-780m
mini-3    control-plane   core         standard    amd-igpu      radeon-780m
pc-1      <none>          edge         standard
raspi-1   <none>          edge         low-power
raspi-2   <none>          edge         low-power
```

---

## Phase 2: CNI Migration (Flannel -> Cilium)

### CAUTION: This causes a brief network outage (~5 min)

### Step 2a: Disable default CNI in Talos config

```bash
source .env_devops
omnictl apply -f patches/02-cluster-wide-cni-none.yaml
```

### Step 2b: Remove Flannel and kube-proxy

```bash
source .env
kubectl delete daemonset kube-flannel -n kube-system --ignore-not-found
kubectl delete daemonset kube-proxy -n kube-system --ignore-not-found
```

### Step 2c: Install Cilium via Helm

```bash
helm repo add cilium https://helm.cilium.io/
helm repo update

helm install cilium cilium/cilium \
  --namespace kube-system \
  --set ipam.mode=kubernetes \
  --set kubeProxyReplacement=true \
  --set k8sServiceHost=127.0.0.1 \
  --set k8sServicePort=7445 \
  --set securityContext.capabilities.ciliumAgent="{CHOWN,KILL,NET_ADMIN,NET_RAW,IPC_LOCK,SYS_ADMIN,SYS_RESOURCE,DAC_OVERRIDE,FOWNER,SETGID,SETUID}" \
  --set securityContext.capabilities.cleanCiliumState="{NET_ADMIN,SYS_ADMIN,SYS_RESOURCE}" \
  --set cgroup.autoMount.enabled=false \
  --set cgroup.hostRoot=/sys/fs/cgroup \
  --set hubble.enabled=true \
  --set hubble.relay.enabled=true \
  --set hubble.ui.enabled=true \
  --set operator.replicas=2
```

### Step 2d: Verify

```bash
source .env
cilium status --wait
kubectl get nodes
cilium connectivity test
```

---

## Phase 3: Longhorn Storage

### Step 3a: Install Longhorn via Helm

```bash
helm repo add longhorn https://charts.longhorn.io
helm repo update

kubectl create namespace longhorn-system

helm install longhorn longhorn/longhorn \
  --namespace longhorn-system \
  --set defaultSettings.defaultReplicaCount=3 \
  --set defaultSettings.storageMinimalAvailablePercentage=15 \
  --set defaultSettings.nodeDownPodDeletionPolicy=delete-both-statefulset-and-deployment-pod \
  --set defaultSettings.defaultDataLocality=best-effort \
  --set persistence.defaultClassReplicaCount=3 \
  --set persistence.defaultClass=true
```

### Step 3b: Verify

```bash
source .env
kubectl get pods -n longhorn-system
kubectl get sc
```

Expected: `longhorn` StorageClass marked as default.

### Step 3c: Test PVC

```bash
source .env
kubectl apply -f - <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: longhorn-test-pvc
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: longhorn
  resources:
    requests:
      storage: 1Gi
EOF

# Wait, then check
kubectl get pvc longhorn-test-pvc
# Expected: STATUS = Bound

# Clean up
kubectl delete pvc longhorn-test-pvc
```

### Step 3d: Create GPU local storage class (after gpu-1 disks are mounted)

```bash
source .env
kubectl apply -f - <<EOF
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: longhorn-gpu-local
provisioner: driver.longhorn.io
reclaimPolicy: Delete
volumeBindingMode: Immediate
allowVolumeExpansion: true
parameters:
  numberOfReplicas: "1"
  dataLocality: strict-local
  nodeSelector: "zone=ai-compute"
EOF
```

---

## Phase 4: Nvidia GPU Stack

### Step 4a: Update gpu-1 image schematic in Omni

In the Omni UI:
1. Go to Machines > gpu-1
2. Edit the machine schematic
3. Add extensions:
   - `siderolabs/nvidia-container-toolkit`
   - `siderolabs/nvidia-open-gpu-kernel-modules`
4. This will trigger a reboot of gpu-1 with the new image

### Step 4b: Apply kernel module patch

```bash
source .env_devops
omnictl apply -f patches/04-gpu-nvidia-modules.yaml
```

### Step 4c: Verify extensions loaded

```bash
source .env
talosctl --context frank -n 192.168.55.31 get extensions
talosctl --context frank -n 192.168.55.31 dmesg | grep -i nvidia | head -10
```

### Step 4d: Install Nvidia GPU Operator

```bash
helm repo add nvidia https://helm.ngc.nvidia.com/nvidia
helm repo update

kubectl create namespace gpu-operator

helm install gpu-operator nvidia/gpu-operator \
  --namespace gpu-operator \
  --set driver.enabled=false \
  --set toolkit.enabled=false \
  --set operator.defaultRuntime=containerd
```

### Step 4e: Verify GPU

```bash
source .env
kubectl get pods -n gpu-operator
kubectl get runtimeclass
kubectl get node gpu-1 -o jsonpath='{.status.allocatable.nvidia\.com/gpu}'
# Expected: 1
```

### Step 4f: Run nvidia-smi test

```bash
source .env
kubectl run nvidia-test --rm -it --restart=Never \
  --image=nvcr.io/nvidia/cuda:12.8.0-base-ubuntu24.04 \
  --overrides='{"spec":{"runtimeClassName":"nvidia","tolerations":[{"key":"nvidia.com/gpu","operator":"Exists","effect":"NoSchedule"}],"nodeSelector":{"accelerator":"nvidia"}}}' \
  -- nvidia-smi
```

---

## Full Verification Checklist

```bash
source .env

# 1. Nodes with labels
kubectl get nodes -L zone,tier,accelerator -o wide

# 2. Control plane scheduling
kubectl describe node mini-1 | grep "Taints:"

# 3. CNI
cilium status

# 4. Storage
kubectl get sc
kubectl get pods -n longhorn-system | grep -c Running

# 5. GPU
kubectl get node gpu-1 -o jsonpath='{.status.allocatable.nvidia\.com/gpu}'
kubectl get runtimeclass nvidia
```

## Rollback

### Revert CP scheduling:
```bash
source .env_devops
omnictl delete configpatch 100-cluster-allow-cp-scheduling
```

### Revert labels (per node):
```bash
source .env_devops
omnictl delete configpatch 200-labels-mini-1
# ... repeat for each node
```

### Revert Cilium -> Flannel:
```bash
source .env_devops
omnictl delete configpatch 100-cluster-cni-none
# Flannel will be re-deployed by Talos automatically

source .env
helm uninstall cilium -n kube-system
```

### Revert Longhorn:
```bash
source .env
helm uninstall longhorn -n longhorn-system
kubectl delete ns longhorn-system
```

### Revert GPU Operator:
```bash
source .env
helm uninstall gpu-operator -n gpu-operator
kubectl delete ns gpu-operator

source .env_devops
omnictl delete configpatch 300-gpu-nvidia-modules
```
