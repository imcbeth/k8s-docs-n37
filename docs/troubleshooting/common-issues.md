---
title: "Common Issues"
description: "Frequently encountered issues and their solutions in the homelab cluster"
sidebar_position: 2
---

# Common Issues and Solutions

This page documents frequently encountered issues and their solutions discovered during cluster operations.

## DNS Issues

### External-DNS Not Creating Records for Subdomains

**Symptom:** External-DNS detects ingresses but skips record creation with "no hosted zone matching record DNS Name was detected".

**Cause:** Using `--domain-filter=subdomain.example.com` when the Cloudflare zone is `example.com`. The zone name must match the domain filter.

**Example error (debug log):**

```
zone "example.com" not in domain filter
Skipping record "app.subdomain.example.com" because no hosted zone matching record DNS Name was detected
```

**Solution:** Use the parent zone as domain-filter:

```yaml
args:
  - --domain-filter=example.com  # NOT subdomain.example.com
```

Since ingresses specify exact hostnames, external-dns will only create records for those specific subdomains.

**Note:** At `--log-level=info`, no-op syncs don't produce logs, making it appear stuck. Use debug logging or check metrics to verify sync activity.

---

## Storage Issues

### Synology CSI fsGroup Race Condition

**Error:**

```
MountVolume.SetUp failed for volume "pvc-xxx" : applyFSGroup failed for vol xxx:
lstat /var/lib/kubelet/pods/.../grafana.db-journal: no such file or directory
```

**Cause:** Race condition between Kubernetes fsGroup recursive application and transient files (like SQLite journal files). The file is deleted between directory listing and `lstat`.

**Solution:** Add `fsGroupChangePolicy: OnRootMismatch` to skip recursive fsGroup traversal:

```yaml
podSecurityContext:
  fsGroupChangePolicy: OnRootMismatch
```

This tells Kubernetes to only apply fsGroup at the volume root, avoiding the race condition with transient files.

---

### Synology CSI v1.2.1 iscsiadm Error

**Error:**

```
MountVolume.SetUp failed: env: can't execute 'iscsiadm': No such file or directory (exit status 127)
```

**Cause:** Synology CSI v1.2.1 changed how it locates `iscsiadm` for Talos Linux compatibility.

**Solution:** Add these arguments to the CSI node plugin:

```yaml
args:
  - --chroot-dir=/host
  - --iscsiadm-path=/usr/sbin/iscsiadm
```

**Reference:** [Synology CSI Documentation](/docs/storage/synology-csi#iscsiadm-no-such-file-or-directory-error-v121)

---

### VolumeSnapshot Stuck with Finalizers

**Symptom:** VolumeSnapshot shows `READYTOUSE: false` and cannot be deleted.

**Solution:**

```bash
# Remove finalizers
kubectl patch volumesnapshot -n <namespace> <snapshot-name> \
  -p '{"metadata":{"finalizers":null}}' --type=merge

kubectl patch volumesnapshotcontent <content-name> \
  -p '{"metadata":{"finalizers":null}}' --type=merge
```

---

### Snapshot-Controller v8.x RBAC Issues

**Symptom:** VolumeSnapshots fail with `sourceVolumeMode` validation errors.

**Cause:** v8.x requires additional RBAC permissions.

**Solution:** Ensure ClusterRole includes:

```yaml
rules:
  - apiGroups: ["snapshot.storage.k8s.io"]
    resources: ["volumesnapshotcontents"]
    verbs: ["get", "list", "watch", "update", "patch"]  # patch required
  - apiGroups: ["groupsnapshot.storage.k8s.io"]
    resources: ["volumegroupsnapshotcontents", "volumegroupsnapshotclasses"]
    verbs: ["get", "list", "watch", "update", "patch"]
```

---

## Monitoring Issues

### Trivy ServiceMonitor Not Discovered

**Symptom:** Grafana Trivy dashboard shows no data.

**Cause:** Trivy Helm chart uses `serviceMonitor.labels` (not `additionalLabels`).

**Solution:**

```yaml
# In values.yaml
serviceMonitor:
  enabled: true
  labels:  # NOT additionalLabels
    release: kube-prometheus-stack
```

**Quick fix:**

```bash
kubectl label servicemonitor -n trivy-system trivy-operator release=kube-prometheus-stack
```

---

### PrometheusRule Not Picked Up

**Symptom:** AlertManager not receiving alerts from PrometheusRule.

**Cause:** Missing required label for Prometheus discovery.

**Solution:** Add label to PrometheusRule:

```yaml
metadata:
  labels:
    release: kube-prometheus-stack
```

---

### SNMP Exporter v0.30.0 Health Check Failure

**Symptom:** SNMP Exporter pod fails liveness/readiness probes.

**Cause:** `/health` endpoint removed in v0.30.0.

**Solution:** Update probes to use `/`:

```yaml
livenessProbe:
  httpGet:
    path: /
    port: 9116
readinessProbe:
  httpGet:
    path: /
    port: 9116
```

---

## Loki Issues

### Loki singleBinary Memory Exhaustion

**Symptom:** Loki pods OOM killed or using excessive memory.

**Cause:** External caches trigger distributed mode in singleBinary deployment.

**Solution:** Use internal caching only:

```yaml
# In values.yaml
chunksCache:
  enabled: false
  replicas: 0
resultsCache:
  enabled: false
  replicas: 0

loki:
  limits_config:
    ingestion_rate_mb: 10
    ingestion_burst_size_mb: 20

extraEnv:
  - name: GOMEMLIMIT
    value: "700MiB"
```

---

### Loki Distributed Mode Conflict

**Error:**

```
Error: You have more than zero replicas configured for both the single binary and distributed targets
```

**Cause:** Cache configurations create separate StatefulSets.

**Solution:** Explicitly set replicas to 0:

```yaml
chunksCache:
  replicas: 0
resultsCache:
  replicas: 0
```

---

## ArgoCD Issues

### ArgoCD Application Manifest Updates Not Applied

**Symptom:** Changing `targetRevision` in Application YAML doesn't update the deployment.

**Solution:** Apply the Application manifest directly:

```bash
kubectl apply -f manifests/applications/<app>.yaml
```

ArgoCD will then sync the new version.

---

## Velero Issues

### Velero CSI + Kopia Conflict

**Symptom:** Backups show "PartiallyFailed" with conflicting backup methods.

**Solution:** Use CSI snapshots exclusively:

```yaml
# In values.yaml
configuration:
  features: EnableCSI
  defaultVolumesToFsBackup: false  # Disable Kopia
```

---

## ARM64/Raspberry Pi Issues

### Trivy ARM64 Image Not Available

**Symptom:** Trivy pods fail with image pull errors from ghcr.io.

**Solution:** Use mirror.gcr.io:

```yaml
trivy:
  image:
    registry: mirror.gcr.io
    repository: aquasecurity/trivy
```

---

### Scan Jobs Timing Out

**Symptom:** Trivy scan jobs fail with timeout.

**Cause:** ARM64 scans slower than x86.

**Solution:** Increase timeout and reduce concurrency:

```yaml
operator:
  scanJobTimeout: 10m
  scanJobsConcurrentLimit: 3
```

---

## Git-Crypt Issues

### ArgoCD Cannot Read Encrypted Secrets

**Symptom:** ArgoCD sync fails on secret files.

**Cause:** ArgoCD doesn't have git-crypt keys.

**Solution:**

1. Exclude encrypted files from kustomization.yaml
2. Apply secrets manually:

```bash
kubectl apply -f secrets/<secret>.yaml
```

---

### Base64 Control Characters

**Symptom:** Secret data appears corrupted.

**Cause:** Newline character in base64 encoding.

**Solution:** Use `echo -n`:

```bash
echo -n "secret-value" | base64
```

---

## Quick Reference

| Issue | Key Solution |
|-------|--------------|
| external-dns subdomain | Use parent zone as domain-filter |
| CSI fsGroup race | Add `fsGroupChangePolicy: OnRootMismatch` |
| CSI v1.2.1 iscsiadm | Add `--iscsiadm-path=/usr/sbin/iscsiadm` |
| VolumeSnapshot stuck | Remove finalizers with `kubectl patch` |
| Trivy ServiceMonitor | Use `labels` not `additionalLabels` |
| SNMP v0.30.0 probes | Change `/health` to `/` |
| Loki memory | Disable external caches, set GOMEMLIMIT |
| snapshot-controller v8 | Add `patch` verb to RBAC |
| ARM64 Trivy | Use mirror.gcr.io registry |
