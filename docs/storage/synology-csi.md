---
title: "Synology CSI Driver"
description: "Container Storage Interface driver for Synology NAS iSCSI storage"
---

# Synology CSI Driver

The Synology CSI (Container Storage Interface) driver enables Kubernetes to provision persistent volumes on Synology NAS devices using iSCSI protocol.

## Overview

- **Namespace:** `synology-csi`
- **Protocol:** iSCSI
- **NAS Device:** Synology DS925+ at 10.0.1.204
- **Deployment:** Managed by ArgoCD
- **Sync Wave:** `-30` (deploys after networking, before applications)

## Purpose

The Synology CSI driver provides:

- Dynamic volume provisioning
- Persistent storage for stateful applications
- Volume expansion capabilities
- Snapshot support
- Integration with Synology DSM storage management

## Storage Classes

The cluster provides four storage classes with different characteristics:

### synology-iscsi-retain (Default)

**Use Case:** Production data that should be preserved

```yaml
storageClassName: synology-iscsi-retain
```

**Configuration:**

- **Location:** `/volume2` (HDD storage pool)
- **Filesystem:** btrfs
- **Reclaim Policy:** Retain (PV kept after PVC deletion)
- **Volume Expansion:** Enabled
- **Default:** ✅ Yes

**When to Use:**

- Database persistent volumes
- Application state that must be preserved
- Any critical data requiring manual cleanup

### synology-iscsi-delete

**Use Case:** Temporary or development data

```yaml
storageClassName: synology-iscsi-delete
```

**Configuration:**

- **Location:** `/volume2` (HDD storage pool)
- **Filesystem:** btrfs
- **Reclaim Policy:** Delete (PV auto-deleted with PVC)
- **Volume Expansion:** Enabled
- **Default:** ❌ No

**When to Use:**

- Development environments
- Cache storage
- Temporary data that can be recreated
- Testing and experimentation

### synology-iscsi-retain-ssd

**Use Case:** High-performance production storage

```yaml
storageClassName: synology-iscsi-retain-ssd
```

**Configuration:**

- **Location:** `/volume4` (SSD storage pool)
- **Filesystem:** btrfs
- **Reclaim Policy:** Retain
- **Volume Expansion:** Enabled
- **Default:** ❌ No

**When to Use:**

- High-IOPS database workloads
- Performance-critical applications
- Frequently accessed data
- Low-latency requirements

### synology-iscsi-delete-ssd

**Use Case:** High-performance temporary storage

```yaml
storageClassName: synology-iscsi-delete-ssd
```

**Configuration:**

- **Location:** `/volume4` (SSD storage pool)
- **Filesystem:** btrfs
- **Reclaim Policy:** Delete
- **Volume Expansion:** Enabled
- **Default:** ❌ No

**When to Use:**

- High-performance cache layers
- Temporary high-speed storage
- Performance testing
- Build caches

## Architecture

### Components

**CSI Controller:**

- Handles volume provisioning and deletion
- Manages snapshots and cloning
- Communicates with Synology DSM API
- Runs as a Deployment (1 replica)

**CSI Node Driver:**

- Runs on every Kubernetes node (DaemonSet)
- Mounts iSCSI volumes to pods
- Handles volume attach/detach operations
- Manages local mount points

**Snapshotter (Optional):**

- Enables volume snapshots
- Creates point-in-time copies
- Supports snapshot-based backups

## Network Configuration

### iSCSI Connection

- **NAS IP:** 10.0.1.204
- **Protocol:** iSCSI (TCP port 3260)
- **Authentication:** CHAP (credentials in secret)
- **Network:** Direct connection via cluster network

### Requirements

**Kubernetes Nodes:**

- `open-iscsi` package installed
- `iscsid` service running
- iSCSI initiator configured

**Verify on nodes:**

```bash
# Check iscsid service
sudo systemctl status iscsid

# Verify iSCSI tools installed
which iscsiadm

# List iSCSI sessions
sudo iscsiadm -m session
```

## Deployment Configuration

### Application Manifest

**Location:** `manifests/applications/synology-csi.yaml`

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: synology-csi
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "-30"
spec:
  project: infrastructure
  source:
    path: manifests/base/synology-csi
    repoURL: git@github.com:imcbeth/homelab.git
    targetRevision: HEAD
  destination:
    server: https://kubernetes.default.svc
    namespace: synology-csi
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

### Base Manifests

**Location:** `manifests/base/synology-csi/`

**Files:**

- `namespace.yml` - Namespace definition
- `controller.yml` - CSI controller deployment
- `node.yml` - CSI node DaemonSet
- `csi-driver.yml` - CSIDriver resource
- `storage-class.yml` - Four storage class definitions
- `configs/` - ConfigMaps and Secrets
- `snapshotter/` - Snapshot controller (optional)

## Using Persistent Volumes

### Creating a PVC

**Example with default storage class:**

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: my-app-data
  namespace: default
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
  # storageClassName not specified = uses default (synology-iscsi-retain)
```

**Example with specific storage class:**

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-data
  namespace: default
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: synology-iscsi-retain-ssd  # Use SSD storage
  resources:
    requests:
      storage: 50Gi
```

### Using PVC in Pod

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: my-app
spec:
  containers:
  - name: app
    image: my-app:latest
    volumeMounts:
    - name: data
      mountPath: /data
  volumes:
  - name: data
    persistentVolumeClaim:
      claimName: my-app-data
```

### Access Modes

**ReadWriteOnce (RWO):**

- Volume can be mounted read-write by a single node
- Most common for databases and stateful apps
- Supported by iSCSI

**ReadOnlyMany (ROX):**

- Volume can be mounted read-only by many nodes
- Supported by iSCSI

**ReadWriteMany (RWX):**

- Volume can be mounted read-write by many nodes
- **NOT supported** by iSCSI (use NFS for RWX)

## Volume Operations

### Expanding a Volume

Volumes can be expanded by editing the PVC:

```bash
# Edit PVC to increase size
kubectl edit pvc my-app-data

# Change storage request:
spec:
  resources:
    requests:
      storage: 20Gi  # Increased from 10Gi
```

**Notes:**

- Volume can only be expanded, not shrunk
- Pod may need restart to recognize new size
- Filesystem will be automatically resized

### Viewing Volumes

```bash
# List PVCs
kubectl get pvc -A

# List PVs
kubectl get pv

# Describe PVC
kubectl describe pvc my-app-data

# Check volume details
kubectl get pv <pv-name> -o yaml
```

### Deleting Volumes

**With Retain policy:**

```bash
# Delete PVC (PV remains)
kubectl delete pvc my-app-data

# PV status changes to Released
kubectl get pv

# Manually delete PV when ready
kubectl delete pv <pv-name>

# Clean up iSCSI LUN on Synology DSM
```

**With Delete policy:**

```bash
# Delete PVC (PV and iSCSI LUN auto-deleted)
kubectl delete pvc my-app-data
```

## Volume Snapshots

### Creating a Snapshot

```yaml
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshot
metadata:
  name: my-app-snapshot
  namespace: default
spec:
  volumeSnapshotClassName: synology-snapshot-class
  source:
    persistentVolumeClaimName: my-app-data
```

### Restoring from Snapshot

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: my-app-data-restored
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: synology-iscsi-retain
  dataSource:
    name: my-app-snapshot
    kind: VolumeSnapshot
    apiGroup: snapshot.storage.k8s.io
  resources:
    requests:
      storage: 10Gi
```

## Monitoring Storage

### Check CSI Driver Status

```bash
# CSI controller pod
kubectl get pods -n synology-csi | grep controller

# CSI node pods (should be one per node)
kubectl get pods -n synology-csi | grep node

# View controller logs
kubectl logs -n synology-csi deployment/synology-csi-controller -c csi-provisioner

# View node driver logs
kubectl logs -n synology-csi daemonset/synology-csi-node -c csi-driver
```

### Storage Capacity

```bash
# Total PV capacity
kubectl get pv -o custom-columns=NAME:.metadata.name,CAPACITY:.spec.capacity.storage,STORAGECLASS:.spec.storageClassName

# PVC usage (requires metrics-server)
kubectl top pvc -A
```

### Synology DSM

**Web UI:** `https://10.0.1.204:5001`

**Storage Manager:**

- View iSCSI LUNs
- Monitor storage pool capacity
- Check disk health
- Review snapshot usage

## Troubleshooting

### PVC Stuck in Pending

**Check PVC events:**

```bash
kubectl describe pvc <pvc-name>
```

**Common causes:**

- CSI controller not running
- Synology NAS unreachable
- Storage pool out of space
- Authentication failure
- Invalid storage class

**Verify CSI pods:**

```bash
kubectl get pods -n synology-csi
```

### Volume Mount Failures

**Check pod events:**

```bash
kubectl describe pod <pod-name>
```

**Common causes:**

- iSCSI initiator not running on node
- Network connectivity to NAS
- Volume already attached to another node
- Filesystem corruption

**Verify iSCSI sessions on node:**

```bash
# SSH to the node
sudo iscsiadm -m session
```

### Volume Not Expanding

**Check PVC status:**

```bash
kubectl describe pvc <pvc-name>
```

**Steps:**

1. Verify allowVolumeExpansion: true in storage class
2. Check CSI controller logs
3. Restart pod using the PVC
4. Verify filesystem resized inside container

### CSI Driver Not Working

**Check node prerequisites:**

```bash
# On each Kubernetes node
sudo systemctl status iscsid
sudo systemctl status open-iscsi
which iscsiadm
```

**Restart CSI pods:**

```bash
kubectl rollout restart deployment/synology-csi-controller -n synology-csi
kubectl rollout restart daemonset/synology-csi-node -n synology-csi
```

## Current Usage

### Critical Volumes

**Prometheus Metrics Storage:**

- **PVC:** `prometheus-kube-prometheus-stack-prometheus-db-...`
- **Size:** 50Gi
- **Class:** synology-iscsi-retain
- **Purpose:** Long-term metrics retention
- **Status:** CRITICAL - do not delete

### Viewing All PVCs

```bash
kubectl get pvc -A --sort-by=.spec.resources.requests.storage
```

## Performance Considerations

### Raspberry Pi Cluster

**Network:**

- Gigabit Ethernet on all 5 Pi nodes
- iSCSI over standard network
- Typical throughput: 100-300 MB/s
- Latency: 1-5ms

**Storage Pools:**

- `/volume2` (HDD): Higher capacity, lower IOPS
- `/volume4` (SSD): Lower capacity, higher IOPS

**Optimization:**

- Use SSD storage class for databases
- Use HDD storage class for bulk data
- Enable btrfs compression for better efficiency
- Monitor NAS network utilization

## Security

### Authentication

- CHAP authentication for iSCSI
- Credentials managed via SealedSecret (`manifests/base/synology-csi/client-info-sealed.yaml`)
- SealedSecrets safely stored in Git, decrypted at runtime by Sealed Secrets controller

See [Secrets Management](../security/secrets-management.md) for details on managing SealedSecrets.

### Network Security

- iSCSI traffic on trusted cluster network
- No exposure to external networks
- NAS firewall restricts access to cluster nodes

### Access Control

- CSI driver has specific RBAC permissions
- Service accounts scoped to synology-csi namespace
- No privileged access outside of storage operations

## Backup Strategy

### Volume Snapshots

- Use VolumeSnapshot CRD for point-in-time copies
- Snapshots stored on Synology NAS
- Minimal space usage with btrfs CoW

### Synology Snapshots

- Additional snapshot layer in DSM
- Scheduled snapshots via Snapshot Replication
- Protects against accidental deletion

### Offsite Backup

- Synology Hyper Backup for offsite replication
- Critical PVs should be backed up regularly
- Test restore procedures periodically

## Related Documentation

- [ArgoCD Application Management](../applications/argocd.md)
- [kube-prometheus-stack Storage](../applications/kube-prometheus-stack.md)
- [Monitoring Overview](../monitoring/overview.md)

## References

- [Synology CSI Driver GitHub](https://github.com/SynologyOpenSource/synology-csi)
- [Kubernetes CSI Documentation](https://kubernetes-csi.github.io/)
- [Synology DSM Documentation](https://www.synology.com/en-us/support/documentation)
