---
title: "Velero"
description: "Kubernetes backup and disaster recovery solution"
---

# Velero

Velero provides backup and disaster recovery capabilities for the Raspberry Pi 5 Kubernetes homelab cluster, protecting critical persistent volumes and cluster resources.

## Overview

- **Namespace:** `velero`
- **Helm Chart:** `vmware-tanzu/velero`
- **Chart Version:** `8.3.1`
- **App Version:** `v1.15.0`
- **Deployment:** Managed by ArgoCD
- **Backup Strategy:** Daily PVC backups + Weekly cluster resource backups

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Velero Server (1 pod)                                   │
│ - 100m CPU / 256Mi RAM                                  │
│ - Manages backup/restore operations                     │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Node-Agent DaemonSet (5 pods, one per node)            │
│ - 100m CPU / 256Mi RAM per pod                          │
│ - Kopia file-level backup                              │
│ - Tolerates control-plane taint                        │
└─────────────────────────────────────────────────────────┘
                          ↓
        ┌─────────────────┴──────────────────┐
        ↓                                    ↓
┌──────────────────┐              ┌──────────────────────┐
│ CSI Snapshots    │              │ S3 Storage           │
│ - Synology CSI   │              │ - LocalStack (test)  │
│ - Fast recovery  │              │ - Future: B2 (prod)  │
└──────────────────┘              └──────────────────────┘
```

**Components:**

- **Velero Server**: Manages backup/restore operations, schedules
- **Node-Agent (Kopia)**: DaemonSet on all 5 nodes for file-level PVC backup
- **CSI Snapshots**: Storage-native snapshots via Synology CSI
- **S3 Storage**: Object storage for backup data (LocalStack for testing, Backblaze B2 for production)

## Backup Strategy

### Daily Critical PVC Backup (2 AM)

- **Schedule**: Every day at 2:00 AM
- **Retention**: 30 days
- **Namespaces**: default (Prometheus, Grafana), loki, pihole
- **Method**: Kopia file-level + CSI snapshots
- **Total Data**: ~80Gi (Prometheus 50Gi, Loki 20Gi, Grafana 5Gi, Pi-hole 5Gi)

### Weekly Cluster Resource Backup (3 AM Sunday)

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

### LocalStack (Testing - Default Configuration)

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

**Use Case:** Testing and validation
**Limitations:**

- ⚠️ Ephemeral storage - backups lost on LocalStack pod restart
- ✅ Good for testing backup/restore procedures
- ❌ NOT suitable for production disaster recovery

### Backblaze B2 (Production - Recommended)

**Setup Steps:**

1. Sign up at [https://www.backblaze.com/b2/](https://www.backblaze.com/b2/)
2. Create bucket: `velero-backups-<YOUR-IDENTIFIER>` (e.g., `velero-backups-homelab-n37`)
3. Generate application key with read/write permissions
4. Update `values.yaml`:

```yaml
config:
  region: us-west-004  # Your B2 region
  s3Url: https://s3.us-west-004.backblazeb2.com

credentials:
  aws_access_key_id: <B2_KEY_ID>
  aws_secret_access_key: <B2_APPLICATION_KEY>
```

**Cost Estimate:**

- Storage: $6/TB/month
- ~100Gi stored ≈ $0.60/month
- Egress: Free for first 3× of stored data
- Total: ~$1–2/month for homelab

## Deployment via ArgoCD

The Velero deployment is managed through GitOps with ArgoCD:

**Application Manifest:** `manifests/applications/velero.yaml`

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: velero
  namespace: argocd
spec:
  project: infrastructure
  sources:
    - repoURL: https://vmware-tanzu.github.io/helm-charts
      chart: velero
      targetRevision: 8.3.1
      helm:
        valueFiles:
          - $values/manifests/base/velero/values.yaml
    - repoURL: git@github.com:imcbeth/homelab.git
      path: manifests/base/velero
      targetRevision: HEAD
      ref: values
  destination:
    server: https://kubernetes.default.svc
    namespace: velero
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

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

### Node-Agent (per node)

```yaml
resources:
  requests:
    cpu: 100m
    memory: 256Mi
  limits:
    cpu: 500m
    memory: 1Gi
```

**Total Cluster Overhead:**

- CPU: 600m (100m server + 500m node-agents) (~3% of 20 cores)
- Memory: 1.53Gi (256Mi server + 1.28Gi node-agents) (~1.9% of 80GB)

## Manual Backup Commands

### Create Backups

```bash
# Backup specific namespace
velero backup create grafana-manual \
  --include-namespaces default \
  --selector app.kubernetes.io/name=grafana \
  --default-volumes-to-fs-backup

# Backup entire cluster
velero backup create cluster-backup-$(date +%Y%m%d) \
  --include-cluster-resources=true \
  --default-volumes-to-fs-backup

# Backup single PVC
velero backup create loki-pvc-backup \
  --include-namespaces loki \
  --default-volumes-to-fs-backup \
  --wait
```

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
# Verify S3 credentials
kubectl -n velero get secret cloud-credentials -o yaml

# Test S3 connectivity from Velero pod
kubectl -n velero exec deployment/velero -- velero backup-location get

# Check backup storage location status
kubectl get backupstoragelocation -n velero -o yaml
```

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

**Production Best Practice:**

- **Do NOT commit real S3 credentials in plaintext**
- Use git-crypt encryption for secrets
- Or use external secret management (Vault, External Secrets Operator)
- The example `values.yaml` uses plaintext for LocalStack testing only

## Migration from LocalStack to Production S3

### Prerequisites

1. ✅ LocalStack testing completed successfully
2. ✅ At least 3 successful backup/restore cycles
3. ✅ External S3 account created (Backblaze B2 recommended)
4. ✅ S3 bucket created

### Migration Steps

**Step 1: Update values.yaml**

```yaml
configuration:
  backupStorageLocation:
    - name: default
      provider: aws
      bucket: velero-backups-homelab-n37
      config:
        region: us-west-004
        s3Url: https://s3.us-west-004.backblazeb2.com
        # Remove: s3ForcePathStyle, insecureSkipTLSVerify

credentials:
  useSecret: true
  existingSecret: velero-b2-credentials
```

**Step 2: Create Production Secret**

```bash
kubectl create secret generic velero-b2-credentials -n velero \
  --from-literal=cloud=$'[default]\naws_access_key_id=<YOUR_B2_KEY_ID>\naws_secret_access_key=<YOUR_B2_APPLICATION_KEY>'
```

**Step 3: Deploy Changes**

```bash
git add manifests/base/velero/values.yaml
git commit -m "feat: Migrate Velero to production Backblaze B2 storage"
git push

# ArgoCD will auto-sync
argocd app sync velero
```

**Step 4: Verify Migration**

```bash
# Check backup storage location
kubectl get backupstoragelocation -n velero
# Status should be "Available"

# Create test backup
velero backup create test-production-s3 \
  --include-namespaces velero-test \
  --wait

# Verify in B2 web UI or CLI
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

# Backup with Kopia
velero backup create test-pvc-backup \
  --include-namespaces velero-test \
  --default-volumes-to-fs-backup \
  --wait

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

### Issue 1: LocalStack Connection Required for Initial Deployment

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
