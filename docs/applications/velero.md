---
title: "Velero"
description: "Kubernetes backup and disaster recovery solution"
---

# Velero

Velero provides backup and disaster recovery capabilities for the Raspberry Pi 5 Kubernetes homelab cluster, protecting critical persistent volumes and cluster resources.

## Overview

- **Namespace:** `velero`
- **Helm Chart:** `vmware-tanzu/velero`
- **Chart Version:** `8.2.0`
- **App Version:** `v1.16.0`
- **Deployment:** Managed by ArgoCD
- **Backup Storage:** Backblaze B2 (production)
- **Backup Strategy:** Daily PVC backups + Weekly cluster resource backups

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Velero Server (1 pod)                                   │
│ - 100m CPU / 256Mi RAM                                  │
│ - Manages backup/restore operations                     │
│ - CSI snapshot coordination                            │
└─────────────────────────────────────────────────────────┘
                          ↓
        ┌─────────────────┴──────────────────┐
        ↓                                    ↓
┌──────────────────────────────────┐  ┌──────────────────────┐
│ CSI Snapshots (Primary Method)  │  │ S3 Storage           │
│ - snapshot-controller v8.2.1    │  │ - Backblaze B2 (prod)│
│ - Synology CSI driver            │  │ - 11 nines durability│
│ - Storage-native snapshots       │  │ - Backup metadata    │
│ - Fast backup/restore            │  │ - Offsite DR         │
└──────────────────────────────────┘  └──────────────────────┘
                ↓
┌──────────────────────────────────┐
│ Synology NAS Storage             │
│ - iSCSI LUN snapshots            │
│ - Hardware-accelerated           │
│ - Instant snapshot creation      │
└──────────────────────────────────┘
```

**Components:**

- **Velero Server**: Manages backup/restore operations, schedules, creates VolumeSnapshot resources
- **snapshot-controller v8.2.1**: Kubernetes controller that processes VolumeSnapshot requests
- **Synology CSI Driver**: Creates storage-native snapshots on Synology NAS
- **S3 Storage**: Object storage for backup metadata (LocalStack for testing, Backblaze B2 for production)

**Note:** Kopia file-level backups were disabled (2026-01-05) in favor of CSI snapshots, which are more efficient for block storage.

## Backup Strategy

### Backup Schedule Overview

| Schedule | Time | Retention | Scope | Method |
|----------|------|-----------|-------|--------|
| `velero-daily-argocd` | 1:30 AM | 30 days | argocd namespace | Resources only |
| `velero-daily-critical-pvcs` | 2:00 AM | 30 days | default, loki, pihole | CSI snapshots |
| `velero-weekly-cluster-resources` | 3:00 AM Sunday | 90 days | All namespaces | Resources only |

### Daily ArgoCD Configuration Backup (1:30 AM)

- **Schedule**: Every day at 1:30 AM
- **Retention**: 30 days
- **Namespaces**: argocd only
- **Method**: Kubernetes resources (Applications, AppProjects, ConfigMaps, Secrets)
- **Data**: ~50 resources (stateless, no PVCs)
- **Purpose**: Daily recovery point for ArgoCD configuration changes

### Daily Critical PVC Backup (2:00 AM)

- **Schedule**: Every day at 2:00 AM
- **Retention**: 30 days
- **Namespaces**: default (Prometheus, Grafana), loki, pihole
- **Method**: CSI snapshots only (storage-native snapshots on Synology NAS)
- **Total Data**: ~80Gi (Prometheus 50Gi, Loki 20Gi, Grafana 5Gi, Pi-hole 5Gi)
- **Backup Duration**: ~20 seconds (instant snapshot creation)

### Weekly Cluster Resource Backup (3:00 AM Sunday)

- **Schedule**: Every Sunday at 3:00 AM
- **Retention**: 90 days
- **Scope**: All cluster resources (ArgoCD apps, ConfigMaps, Secrets, etc.)
- **Method**: Kubernetes resource backup only (no PVCs)

## Critical PVCs Backed Up

| Component | Namespace | Size | Storage Class | Data Type |
|-----------|-----------|------|---------------|-----------|
| **Prometheus** | default | 50Gi | synology-iscsi-retain | Metrics TSDB (10-day retention) |
| **Loki** | loki | 20Gi | synology-iscsi-retain | Log chunks/TSDB (7-day retention) |
| **Grafana** | default | 5Gi | synology-iscsi-retain | Dashboards, datasources, plugins |
| **Pi-hole** | pihole | 5Gi | synology-iscsi-retain | DNS blocklists, query history |

## Storage Backends

### Backblaze B2 (Production - Active)

**Current Configuration (as of 2026-01-15):**

```yaml
configuration:
  backupStorageLocation:
    - name: default
      provider: aws
      bucket: velero-backups-homelab-n37
      config:
        region: us-west-004
        s3Url: https://s3.us-west-004.backblazeb2.com

credentials:
  useSecret: true
  existingSecret: "velero-b2-credentials"  # SealedSecret
```

**Features:**

- ✅ 11 nines (99.999999999%) data durability
- ✅ Offsite disaster recovery
- ✅ S3-compatible API
- ✅ Credentials managed via SealedSecret (GitOps-compatible)

**Cost Estimate:**

- Storage: $0.006/GB/month ($6/TB)
- ~100Gi stored ≈ $0.60/month
- Egress: $0.01/GB (first 1GB/day free)
- Total: ~$2-6/month for homelab

### LocalStack (Testing - Available)

LocalStack remains deployed for local testing purposes:

```yaml
config:
  region: us-east-1
  s3ForcePathStyle: "true"
  s3Url: http://localstack.localstack:4566
  insecureSkipTLSVerify: "true"

credentials:
  aws_access_key_id: test
  aws_secret_access_key: test
```

**Use Case:** Testing backup/restore procedures locally
**Limitations:**

- ⚠️ Ephemeral storage - backups lost on pod restart
- ❌ NOT suitable for production disaster recovery

## Deployment via ArgoCD

The Velero deployment is managed through GitOps with ArgoCD using a multi-source configuration:

**Application Manifest:** `manifests/applications/velero.yaml`

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: velero
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "-5"
spec:
  project: infrastructure
  sources:
    # Source 1: Helm chart from VMware Tanzu
    - repoURL: https://vmware-tanzu.github.io/helm-charts
      chart: velero
      targetRevision: 8.2.0
      helm:
        releaseName: velero
        valueFiles:
          - $values/manifests/base/velero/values.yaml
    # Source 2: Values file reference
    - repoURL: git@github.com:imcbeth/homelab.git
      path: manifests/base/velero
      targetRevision: HEAD
      ref: values
    # Source 3: Additional resources (SealedSecrets for B2 credentials)
    - repoURL: git@github.com:imcbeth/homelab.git
      path: manifests/base/velero
      targetRevision: HEAD
  destination:
    server: https://kubernetes.default.svc
    namespace: velero
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

**Note:** The third source deploys the kustomization resources including the SealedSecret for B2 credentials.

## Resource Allocation

### Velero Server

```yaml
resources:
  requests:
    cpu: 100m
    memory: 256Mi
  limits:
    cpu: 200m
    memory: 512Mi
```

**Total Cluster Overhead:**

- CPU: 100m (~0.5% of 20 cores)
- Memory: 256Mi (~0.3% of 80GB)

**Note:** With CSI snapshots, no node-agent DaemonSet is required, significantly reducing resource overhead compared to Kopia file-level backups.

## Manual Backup Commands

### Create Backups

```bash
# Backup specific namespace with CSI snapshots
velero backup create grafana-manual \
  --include-namespaces default \
  --selector app.kubernetes.io/name=grafana \
  --snapshot-volumes=true

# Backup entire cluster with resources
velero backup create cluster-backup-$(date +%Y%m%d) \
  --include-cluster-resources=true \
  --snapshot-volumes=true

# Backup namespaces with PVCs (CSI snapshots)
velero backup create critical-pvcs-manual \
  --include-namespaces default,loki,pihole \
  --snapshot-volumes=true \
  --wait

# Check backup status
velero backup describe critical-pvcs-manual
```

**CSI Snapshot Configuration:**

- `--snapshot-volumes=true`: Use CSI snapshots for PVCs
- `--default-volumes-to-fs-backup=false`: Disable Kopia file-level backups (default in current config)
- VolumeSnapshots are created automatically for PVCs with CSI storage class

### View Backups

```bash
# List all backups
velero backup get

# Describe specific backup
velero backup describe daily-critical-pvcs-20251227020000

# View backup logs
velero backup logs daily-critical-pvcs-20251227020000

# Check backup in S3 (LocalStack)
kubectl -n localstack exec deployment/localstack -- \
  awslocal s3 ls s3://velero-backups/backups/
```

## Restore Commands

### Restore from Backup

```bash
# List available backups
velero backup get

# Restore from latest scheduled backup
velero restore create --from-backup daily-critical-pvcs-latest

# Restore specific namespace
velero restore create grafana-restore \
  --from-backup grafana-manual \
  --include-namespaces default

# Check restore status
velero restore describe grafana-restore
velero restore logs grafana-restore
```

### Disaster Recovery Scenarios

**Scenario 1: Single PVC Loss (Grafana)**

```bash
# 1. Scale down deployment
kubectl -n default scale deployment kube-prometheus-stack-grafana --replicas=0

# 2. Delete PVC
kubectl -n default delete pvc kube-prometheus-stack-grafana

# 3. Find latest backup
LATEST_BACKUP=$(velero backup get | awk '/^daily-critical-pvcs-/ {print $1}' | sort | tail -n 1)

# 4. Restore from backup
velero restore create grafana-pvc-restore \
  --from-backup "$LATEST_BACKUP" \
  --include-namespaces default \
  --include-resources pvc,pv

# 5. Scale up deployment
kubectl -n default scale deployment kube-prometheus-stack-grafana --replicas=1

# Time to recovery: < 15 minutes
```

**Scenario 2: Full Cluster Rebuild**

```bash
# 1. Deploy new Kubernetes cluster (same version)
# 2. Install Velero with same configuration
# 3. Point to same S3 bucket
# 4. Restore all namespaces

velero restore create cluster-restore \
  --from-backup weekly-cluster-resources-2024-12-01-000000

# Time to recovery: < 4 hours
```

## Monitoring

### Prometheus Metrics

Velero exports metrics that are automatically scraped by Prometheus:

```promql
# Backup success rate
velero_backup_success_total{schedule="daily-critical-pvcs"}

# Backup failure count
velero_backup_failure_total

# Backup duration
velero_backup_duration_seconds{schedule="daily-critical-pvcs"}

# Last successful backup timestamp
velero_backup_last_successful_timestamp
```

### Velero Backup Alerts

The following PrometheusRule alerts monitor backup health:

**Critical Alerts:**

- **VeleroBackupFailed**: Backup failures detected in last hour
- **VeleroBackupDelayed**: No successful backup in 24+ hours
- **VeleroBackupStorageLocationUnavailable**: S3 storage unreachable
- **VeleroBackupMetricAbsent**: Velero metrics not being scraped

**Warning Alerts:**

- **VeleroBackupDurationHigh**: Backup taking >30 minutes
- **VeleroVolumeSnapshotLocationUnavailable**: CSI snapshot location unavailable
- **VeleroPartialBackupFailure**: Some resources not backed up

See [kube-prometheus-stack](./kube-prometheus-stack.md) for alert configuration details.

### Check Backup Health

```bash
# Pod status
kubectl get pods -n velero

# Backup storage location status
kubectl get backupstoragelocation -n velero

# Recent backups
velero backup get

# Backup schedules
velero schedule get

# Velero server logs
kubectl -n velero logs deployment/velero
```

## Troubleshooting

### LocalStack Not Deployed

**Symptoms:**

```
BackupStorageLocation "default" is unavailable: rpc error: code = Unknown desc = Get "http://localstack.localstack:4566/": dial tcp: lookup localstack.localstack on 10.96.0.10:53: no such host
```

**Resolution:**

Deploy LocalStack first, OR reconfigure Velero for production S3 (see Backblaze B2 section above).

### General S3 Connection Issues

```bash
# Verify B2 credentials secret exists
kubectl -n velero get secret velero-b2-credentials

# Check SealedSecret status
kubectl -n velero get sealedsecret velero-b2-credentials

# Test S3 connectivity from Velero pod
kubectl -n velero exec deployment/velero -- velero backup-location get

# Check backup storage location status
kubectl get backupstoragelocation -n velero -o yaml
```

**Common B2 Issues:**

- **Invalid credentials**: Verify keyID and applicationKey are correct
- **Bucket permissions**: Ensure the application key has read/write access to the bucket
- **Region mismatch**: Check the region matches your B2 bucket location

### Backup Failing

```bash
# Check backup status
velero backup describe <backup-name> --details

# View backup logs
velero backup logs <backup-name>

# Common issues:
# 1. S3 connectivity - check s3Url and credentials
# 2. CSI snapshot issues - check VolumeSnapshot CRDs
# 3. Kopia timeout - check node-agent logs
```

### Node-Agent Permission Issues

```bash
# Check node-agent pods
kubectl -n velero get pods -l name=node-agent -o wide

# View node-agent logs
kubectl -n velero logs daemonset/node-agent -c node-agent --tail=100

# Verify DAC_READ_SEARCH capability is sufficient
# If permission errors persist, check:
# 1. SELinux/AppArmor policies
# 2. PodSecurityPolicy/PodSecurityStandards
# 3. hostPath mount for /var/lib/kubelet/pods
```

## Security Considerations

### Node-Agent Capabilities

The Velero node-agent runs with **minimal Linux capabilities** instead of privileged mode:

```yaml
containerSecurityContext:
  privileged: false
  allowPrivilegeEscalation: false
  capabilities:
    add:
      - DAC_READ_SEARCH  # Bypass file read permission checks
```

**Why DAC_READ_SEARCH?**

- Allows Kopia to read PVC data from `/var/lib/kubelet/pods` regardless of file ownership
- Much safer than `privileged: true` or `SYS_ADMIN` capability
- Sufficient for file-level backup operations

**Security Comparison:**

| Configuration | Privileges | Security Risk | Recommendation |
|--------------|------------|---------------|----------------|
| `privileged: true` | All capabilities + host access | Very High | ❌ Avoid |
| `capabilities: [SYS_ADMIN]` | Broad system admin | High | ⚠️ Only if necessary |
| `capabilities: [DAC_READ_SEARCH]` | File read bypass only | Low | ✅ Recommended |

### Credential Management

**Current Implementation (SealedSecrets):**

B2 credentials are managed via SealedSecret for GitOps compatibility:

- **SealedSecret:** `manifests/base/velero/b2-credentials-sealed.yaml`
- **Decrypted Secret:** `velero-b2-credentials` in `velero` namespace
- **Kustomization:** `manifests/base/velero/kustomization.yaml`

```bash
# View credential secret (base64 encoded)
kubectl get secret velero-b2-credentials -n velero -o yaml

# Check SealedSecret status
kubectl get sealedsecret velero-b2-credentials -n velero
```

**Updating B2 Credentials:**

```bash
# 1. Create temporary secret file (DO NOT COMMIT)
cat > /tmp/velero-b2-credentials.yaml <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: velero-b2-credentials
  namespace: velero
type: Opaque
stringData:
  cloud: |
    [default]
    aws_access_key_id=<NEW_B2_KEY_ID>
    aws_secret_access_key=<NEW_B2_APPLICATION_KEY>
EOF

# 2. Seal the secret
kubeseal --cert <(kubectl get secret -n kube-system \
  -l sealedsecrets.bitnami.com/sealed-secrets-key=active \
  -o jsonpath='{.items[0].data.tls\.crt}' | base64 -d) \
  --format yaml < /tmp/velero-b2-credentials.yaml > manifests/base/velero/b2-credentials-sealed.yaml

# 3. Delete temporary file and commit
rm /tmp/velero-b2-credentials.yaml
git add manifests/base/velero/b2-credentials-sealed.yaml
git commit -m "feat: Update Velero B2 credentials"
git push
```

See [Secrets Management](../security/secrets-management.md) for more details on SealedSecrets.

## Migration from LocalStack to Production S3

### Migration Status: ✅ Completed (2026-01-15)

The migration from LocalStack to Backblaze B2 has been completed successfully:

- **PR #239:** feat: Migrate Velero backups from LocalStack to Backblaze B2
- **Bucket:** velero-backups-homelab-n37
- **Region:** us-west-004
- **Credentials:** Managed via SealedSecret

### Verification Results

```bash
# BackupStorageLocation status
$ kubectl get backupstoragelocation -n velero
NAME      PHASE       LAST VALIDATED   AGE   DEFAULT
default   Available   1s               17d   true

# Test backup completed successfully
$ velero backup create test-b2-migration --include-namespaces velero --wait
Backup completed with status: Completed
Items backed up: 54
```

### Migration Reference (For Future Providers)

If you need to migrate to a different S3 provider in the future:

**Step 1: Create SealedSecret for new credentials**

```bash
# Create temporary secret
cat > /tmp/velero-new-credentials.yaml <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: velero-new-credentials
  namespace: velero
type: Opaque
stringData:
  cloud: |
    [default]
    aws_access_key_id=<NEW_KEY_ID>
    aws_secret_access_key=<NEW_SECRET_KEY>
EOF

# Seal and commit
kubeseal ... < /tmp/velero-new-credentials.yaml > manifests/base/velero/new-credentials-sealed.yaml
rm /tmp/velero-new-credentials.yaml
```

**Step 2: Update values.yaml**

```yaml
configuration:
  backupStorageLocation:
    - name: default
      provider: aws
      bucket: <new-bucket-name>
      config:
        region: <new-region>
        s3Url: <new-s3-endpoint>

credentials:
  useSecret: true
  existingSecret: "velero-new-credentials"
```

**Step 3: Update kustomization.yaml and deploy**

```bash
git add manifests/base/velero/
git commit -m "feat: Migrate Velero to new S3 provider"
git push
```

## Testing Procedures

### Test 1: ConfigMap Backup/Restore

```bash
# Create test data
kubectl create namespace velero-test
kubectl -n velero-test create configmap test-data --from-literal=foo=bar

# Backup
velero backup create test-configmap \
  --include-namespaces velero-test \
  --wait

# Delete namespace
kubectl delete namespace velero-test

# Restore
velero restore create test-restore \
  --from-backup test-configmap \
  --wait

# Verify
kubectl -n velero-test get configmap test-data -o yaml

# Cleanup
kubectl delete namespace velero-test
```

### Test 2: PVC Backup/Restore

For comprehensive PVC testing procedures, see `manifests/base/velero/README.md` in the homelab repository.

**Example PVC Test:**

```bash
# Create test namespace and PVC
kubectl create namespace velero-test

cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: test-pvc
  namespace: velero-test
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: synology-iscsi-retain
  resources:
    requests:
      storage: 1Gi
EOF

# Create pod with data
kubectl run test-pod -n velero-test --image=busybox --restart=Never \
  --overrides='{"spec":{"containers":[{"name":"busybox","image":"busybox","command":["/bin/sh","-c","echo test-data > /data/test.txt && sleep 3600"],"volumeMounts":[{"name":"data","mountPath":"/data"}]}],"volumes":[{"name":"data","persistentVolumeClaim":{"claimName":"test-pvc"}}]}}'

# Backup with CSI snapshots
velero backup create test-pvc-backup \
  --include-namespaces velero-test \
  --snapshot-volumes=true \
  --wait

# Check VolumeSnapshot was created
kubectl get volumesnapshot -n velero-test

# Delete namespace
kubectl delete namespace velero-test

# Restore
velero restore create test-pvc-restore \
  --from-backup test-pvc-backup \
  --wait

# Verify data
kubectl -n velero-test exec test-pod -- cat /data/test.txt

# Cleanup
kubectl delete namespace velero-test
```

## Best Practices

1. **Test Restores Regularly**: Monthly disaster recovery drills
2. **Monitor Backup Success**: Check Prometheus metrics and AlertManager notifications
3. **Verify S3 Storage**: Monthly audit of S3 bucket and costs
4. **Update Retention Policies**: Adjust based on compliance and storage requirements
5. **Document Procedures**: Keep disaster recovery runbooks up-to-date
6. **Plan for Growth**: Monitor backup sizes and adjust resources accordingly
7. **Secure Credentials**: Use git-crypt, Vault, or external secret management for production
8. **Test Production Migration**: Validate S3 migration before relying on it

## Known Issues and Solutions

### Issue 1: snapshot-controller v8.x VolumeSnapshot Failures

**Date Noted:** 2026-01-05
**Severity:** Critical (backup failure)
**Status:** Resolved by downgrading to v6.3.1

**Symptoms:**

- All VolumeSnapshots stuck with `READYTOUSE: false`
- Velero backups showing `PartiallyFailed` status
- Error message: `VolumeSnapshotContent is invalid: spec: Invalid value: sourceVolumeMode is required once set`
- VolumeSnapshotContent objects unable to be updated by snapshot-controller

**Root Cause:**

snapshot-controller v8.2.0 has strict immutability validation on the `sourceVolumeMode` field. When the controller attempts to add annotations to VolumeSnapshotContent objects during snapshot creation, the Kubernetes API server rejects the updates due to field validation rules that treat any update as potentially modifying the immutable field.

This is a known issue with the v8.x series: [kubernetes-csi/external-snapshotter#866](https://github.com/kubernetes-csi/external-snapshotter/issues/866)

**Investigation Commands:**

```bash
# Check VolumeSnapshot status
kubectl get volumesnapshot -A

# Describe failed snapshot
kubectl describe volumesnapshot -n default <snapshot-name>

# Check snapshot-controller version
kubectl get deployment -n synology-csi snapshot-controller -o yaml | grep "image:"

# View snapshot-controller logs
kubectl logs -n synology-csi deployment/snapshot-controller
```

**Solution:**

Downgrade to snapshot-controller v8.2.1 or v7.0.2, which are stable and compatible with Kubernetes 1.35:

**Step 1: Clean up stuck VolumeSnapshot resources**

```bash
# Remove finalizers to allow deletion
kubectl patch volumesnapshot -n <namespace> <snapshot-name> \
  -p '{"metadata":{"finalizers":null}}' --type=merge

# Repeat for all stuck VolumeSnapshotContent objects
kubectl patch volumesnapshotcontent <snapcontent-name> \
  -p '{"metadata":{"finalizers":null}}' --type=merge
```

**Step 2: Update snapshot-controller version**

In `manifests/base/synology-csi/kustomization.yaml`:

```yaml
resources:
  - github.com/kubernetes-csi/external-snapshotter/client/config/crd?ref=v7.0.2
  - github.com/kubernetes-csi/external-snapshotter/deploy/kubernetes/snapshot-controller?ref=v7.0.2
```

**Step 3: Deploy and verify**

```bash
# ArgoCD will auto-sync
argocd app sync synology-csi

# Wait for new snapshot-controller pods
kubectl get pods -n synology-csi -l app.kubernetes.io/name=snapshot-controller

# Test VolumeSnapshot creation
kubectl apply -f - <<EOF
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshot
metadata:
  name: test-snapshot
  namespace: default
spec:
  volumeSnapshotClassName: synology-snapshot-class
  source:
    persistentVolumeClaimName: <your-pvc-name>
EOF

# Verify snapshot reaches READYTOUSE: true
kubectl get volumesnapshot -n default test-snapshot
```

**Expected Result:**

- VolumeSnapshots reach `READYTOUSE: true` in 8-10 seconds
- Velero backups complete with status `Completed` (not `PartiallyFailed`)
- CSI snapshots: `csiVolumeSnapshotsCompleted: 3`, `Errors: 0`

**Related PRs:**

- homelab#189: Downgrade snapshot-controller to v7.0.2 for stability
- homelab#188: Add snapshot-controller to Synology CSI deployment (introduced issue)
- homelab#187: Configure Velero to use CSI snapshots only

---

### Issue 2: LocalStack Connection Required for Initial Deployment

**Date Noted:** 2025-12-27
**Severity:** Medium (deployment blocker)

**Symptoms:**

- Velero pod fails to start if LocalStack is not deployed first
- BackupStorageLocation shows "Unavailable"

**Root Cause:**

- Default `values.yaml` is configured for LocalStack testing
- Velero validates S3 connectivity on startup

**Solution:**

- Deploy LocalStack before Velero (for testing), OR
- Configure production S3 credentials before first deployment

**Related PRs:**

- homelab#149: Deploy Velero with Kopia file-level backup support

---

## Related Documentation

- [kube-prometheus-stack](./kube-prometheus-stack.md) - Velero backup alerts
- [Monitoring Overview](../monitoring/overview.md)
- [ArgoCD](./argocd.md)
- [Storage Configuration](../storage/synology-csi.md)

## References

- [Velero Documentation](https://velero.io/docs/)
- [Velero CSI Snapshot Support](https://velero.io/docs/main/csi/)
- [Velero File System Backup (Kopia)](https://velero.io/docs/v1.15/file-system-backup/)
- [Backblaze B2 with Velero](https://www.backblaze.com/blog/kubernetes-backups-with-backblaze-b2-and-velero/)
