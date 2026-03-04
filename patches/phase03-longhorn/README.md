# Phase 3: Longhorn Storage

**Tools:** `omnictl apply -f` + `talosctl` + `helm` + `kubectl`
**Status:** DONE (applied 2026-03-02)

## What This Does

1. Adds the `iscsi-tools` Talos extension to all nodes (required by Longhorn)
2. Installs Longhorn distributed block storage across all nodes
3. Creates the default `longhorn` StorageClass (3 replicas, best-effort locality)
4. Mounts gpu-1's 2x4TB Samsung SSDs and adds them as dedicated Longhorn disks
5. Creates a `longhorn-gpu-local` StorageClass targeting those disks

## Disk Inventory

| Node | System Disk | Extra Disks | Longhorn Role |
| ---- | ----------- | ----------- | ------------- |
| mini-1 | nvme0n1 (1TB NVMe) | — | replica node (EPHEMERAL partition) |
| mini-2 | nvme0n1 (1TB NVMe) | — | replica node (EPHEMERAL partition) |
| mini-3 | nvme0n1 (1TB NVMe) | — | replica node (EPHEMERAL partition) |
| gpu-1 | nvme0n1 (1TB NVMe) | sda (4TB SSD), sdb (4TB SSD) | replica + dedicated GPU storage |
| pc-1 | sdc (64GB SSD) | sda (500GB HDD), sdb (640GB HDD), sdd (640GB HDD) | replica node |
| raspi-1 | mmcblk0 (32GB) | — | minimal (SD card) |
| raspi-2 | mmcblk0 (32GB) | — | minimal (SD card) |

## Files

| File | Tool | Purpose |
| ---- | ---- | ------- |
| `400-cluster-iscsi-tools.yaml` | omnictl | Adds iscsi-tools extension to all nodes |
| `401-gpu1-extra-disks.yaml` | omnictl | Mounts sda/sdb on gpu-1 at /var/mnt/longhorn-{sda,sdb} |
| `longhorn-values.yaml` | helm | Longhorn Helm chart values |
| `longhorn-gpu-local-sc.yaml` | kubectl | GPU-local StorageClass manifest |

## Apply

### Step 0: Add iscsi-tools extension (triggers rolling reboot)

**CAUTION:** This rebuilds node images and reboots all 7 nodes in a rolling fashion.

```bash
source .env_devops
omnictl apply -f patches/phase3-longhorn/400-cluster-iscsi-tools.yaml
```

Wait for all nodes to come back Ready:

```bash
source .env
kubectl get nodes -w
# Wait until all 7 nodes show Ready
```

Verify iscsi-tools is loaded:

```bash
source .env
talosctl -n 192.168.55.21 get extensions | grep iscsi
# Expected: siderolabs/iscsi-tools
```

### Step 1: Wipe gpu-1's extra disks and mount them

**IMPORTANT:** If sda has existing partitions (e.g. old Linux install), wipe them first.
`machine.disks` in Talos will NOT wipe existing partition tables automatically.

```bash
source .env
# Check for existing partitions
talosctl -n 192.168.55.31 get discoveredvolumes --output table | grep -E "sda|sdb"

# Wipe if partitions exist
talosctl -n 192.168.55.31 wipe disk sda
talosctl -n 192.168.55.31 wipe disk sdb
```

Then apply the disk mount config (triggers gpu-1 reboot):

```bash
source .env_devops
omnictl apply -f patches/phase3-longhorn/401-gpu1-extra-disks.yaml
```

Wait for gpu-1 to come back and verify mounts:

```bash
source .env
kubectl get node gpu-1 -w
# Wait until Ready

talosctl -n 192.168.55.31 get mountstatus | grep longhorn
# Expected:
#   /dev/sda1  /var/mnt/longhorn-sda  xfs
#   /dev/sdb1  /var/mnt/longhorn-sdb  xfs
```

### Step 2: Label the namespace for privileged PSS

Longhorn requires privileged pod security (hostPath, privileged containers).

```bash
source .env
kubectl create namespace longhorn-system
kubectl label namespace longhorn-system \
  pod-security.kubernetes.io/enforce=privileged \
  pod-security.kubernetes.io/enforce-version=latest \
  pod-security.kubernetes.io/audit=privileged \
  pod-security.kubernetes.io/warn=privileged
```

### Step 3: Install Longhorn via Helm

```bash
helm repo add longhorn https://charts.longhorn.io
helm repo update

source .env
helm install longhorn longhorn/longhorn --version 1.11.0 \
  --namespace longhorn-system \
  -f patches/phase3-longhorn/longhorn-values.yaml
```

### Step 4: Wait for Longhorn to be ready

```bash
source .env
kubectl -n longhorn-system rollout status ds/longhorn-manager --timeout=300s
kubectl -n longhorn-system rollout status deploy/longhorn-driver-deployer --timeout=300s
kubectl -n longhorn-system rollout status deploy/longhorn-ui --timeout=120s
kubectl get pods -n longhorn-system
# All pods should be Running (some CSI replicas may CrashLoop — only the leader needs to run)
```

### Step 5: Verify default StorageClass + test PVC

```bash
source .env
kubectl get sc
# Expected: longhorn (default)

kubectl apply -f - <<'EOF'
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

# Wait ~30s, then check
kubectl get pvc longhorn-test-pvc
# Expected: STATUS = Bound

# Clean up
kubectl delete pvc longhorn-test-pvc
```

### Step 6: Add gpu-1's extra disks to Longhorn

```bash
source .env
kubectl -n longhorn-system patch nodes.longhorn.io gpu-1 --type merge -p '{
  "spec": {
    "disks": {
      "gpu-sda-4000000000000": {
        "allowScheduling": true,
        "diskType": "filesystem",
        "evictionRequested": false,
        "path": "/var/mnt/longhorn-sda/",
        "storageReserved": 0,
        "tags": ["gpu-local"]
      },
      "gpu-sdb-4000000000000": {
        "allowScheduling": true,
        "diskType": "filesystem",
        "evictionRequested": false,
        "path": "/var/mnt/longhorn-sdb/",
        "storageReserved": 0,
        "tags": ["gpu-local"]
      }
    }
  }
}'
```

### Step 7: Create GPU-local StorageClass + test

```bash
source .env
kubectl apply -f patches/phase3-longhorn/longhorn-gpu-local-sc.yaml

# Test
kubectl apply -f - <<'EOF'
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: gpu-local-test-pvc
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: longhorn-gpu-local
  resources:
    requests:
      storage: 1Gi
EOF

# Wait ~30s, then check
kubectl get pvc gpu-local-test-pvc
# Expected: STATUS = Bound

# Clean up
kubectl delete pvc gpu-local-test-pvc
```

## Verify

```bash
source .env
kubectl get sc
# Expected: longhorn (default), longhorn-gpu-local, longhorn-static
kubectl get pods -n longhorn-system
kubectl -n longhorn-system get nodes.longhorn.io
# All 7 nodes should be True/true/True
```

## Rollback

```bash
# Remove Longhorn
source .env
helm uninstall longhorn -n longhorn-system
kubectl delete ns longhorn-system
kubectl delete sc longhorn-gpu-local 2>/dev/null

# Remove gpu-1 disk mounts
source .env_devops
omnictl delete configpatch 401-gpu1-extra-disks

# Remove iscsi-tools extension (triggers another rolling reboot)
source .env_devops
omnictl delete extensionsconfiguration 400-cluster-iscsi-tools
```
