---
title: "ArgoCD PVC Protection"
description: "Preventing ArgoCD from deleting and recreating iSCSI PVCs during chart upgrades"
sidebar_position: 3
---

# ArgoCD PVC Protection

## The Problem

Applications using `prune: true` + `ServerSideApply=true` can have their PVCs silently deleted and
reprovisioned during chart upgrades. With the `Retain` reclaim policy, the old iSCSI LUN is
orphaned on the Synology NAS — consuming storage indefinitely.

**Confirmed affected applications (April 2026):**

| App | Namespace | PVC Type | Incident |
|-----|-----------|----------|----------|
| Grafana | default | Standalone | 2026-04-17 |
| Trivy Server | trivy-system | StatefulSet VCT | 2026-02-11, 2026-04-17 |
| Loki | loki | StatefulSet VCT | 2026-01-05 |

---

## Root Cause

There are two distinct mechanisms depending on PVC type:

### Standalone PVCs (e.g. Grafana)

ArgoCD manages the PVC as a first-class resource. When a chart upgrade changes any field (e.g.
`storageClassName`, labels, annotations), ArgoCD with `prune: true` marks the old PVC for deletion
and creates a new one.

### StatefulSet VolumeClaimTemplates (e.g. Loki, Trivy)

StatefulSet VCT fields are immutable in Kubernetes. When ArgoCD detects a diff in
`.spec.volumeClaimTemplates` (even a cosmetic one added upstream), it deletes and recreates the
entire StatefulSet — triggering new PVC creation. Old PVCs are released but not deleted (Retain
policy).

---

## Fixes

### Fix 1: `Prune=false` annotation (standalone PVCs)

Add the annotation to the PVC via chart values so ArgoCD never deletes it:

```yaml
# manifests/base/kube-prometheus-stack/values.yaml (Grafana example)
grafana:
  persistence:
    enabled: true
    storageClassName: synology-iscsi-retain
    annotations:
      argocd.argoproj.io/sync-options: "Prune=false"
```

### Fix 2: `ignoreDifferences` for StatefulSet VCTs

Prevent ArgoCD from detecting VCT diffs and triggering StatefulSet recreation:

```yaml
# manifests/applications/loki.yaml
ignoreDifferences:
  - group: apps
    kind: StatefulSet
    jqPathExpressions:
      - .spec.volumeClaimTemplates
      - .status
```

### Fix 3: `existingClaim` (manual PVC management)

For apps that support it, pre-provision the PVC manually and reference it by name. ArgoCD will
never touch a PVC it didn't create.

---

## Current Protection Status

| App | Fix Applied | Location |
|-----|------------|----------|
| Grafana | `Prune=false` annotation | `manifests/base/kube-prometheus-stack/values.yaml` |
| Loki | `ignoreDifferences: .spec.volumeClaimTemplates` | `manifests/applications/loki.yaml` |
| Trivy Server | `ignoreDifferences: .spec.volumeClaimTemplates` | `manifests/applications/trivy-operator.yaml` |

---

## Detecting Orphaned LUNs

Released PVs = orphaned LUNs consuming NAS storage. Audit regularly:

```bash
# Any "Released" PV is an orphaned LUN
kubectl get pv | grep Released

# Get the NAS target IQN from a Released PV
kubectl get pv <pv-name> -o jsonpath='{.spec.csi.volumeAttributes.targetIQN}'
```

**To clean up:**

1. Delete the LUN in DSM → iSCSI Manager → LUN tab
2. Delete the PV object: `kubectl delete pv <pv-name>`
3. Remove stale iscsid entries from nodes (see [iSCSI Troubleshooting](../storage/iscsi-troubleshooting))

---

## Related

- [iSCSI Troubleshooting](../storage/iscsi-troubleshooting)
- [Synology CSI](../storage/synology-csi)
