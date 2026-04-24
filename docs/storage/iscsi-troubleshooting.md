---
title: "iSCSI Troubleshooting"
description: "Diagnosing and resolving Synology iSCSI storage issues in the homelab cluster"
---

# iSCSI Troubleshooting

This cluster uses the Synology CSI driver with iSCSI LUNs provisioned on the NAS at `10.0.1.204`.
PVCs use either `synology-iscsi-retain` (Retain reclaim policy) or `synology-iscsi-delete` (Delete reclaim policy) depending on the workload. Cleanup steps differ — `Retain` PVCs leave orphaned LUNs on the NAS that must be manually deleted; `Delete` PVCs clean up automatically.

## Quick Diagnostics

```bash
# Check all PV states — any "Released" = orphaned LUN on NAS
kubectl get pv

# Check VolumeAttachments — one per active PVC, node shows where iSCSI session lives
kubectl get volumeattachment

# Check which node the iSCSI session is on vs where the pod is scheduled
kubectl get volumeattachment <name> -o jsonpath='{.spec.nodeName}'
kubectl get pod <name> -n <ns> -o jsonpath='{.spec.nodeName}'

# Check CSI node pod logs for login errors
kubectl logs -n synology-csi <synology-csi-node-pod> -c csi-plugin --since=30m

# List active iSCSI node entries on a node
kubectl exec -n synology-csi <synology-csi-node-pod> -c csi-plugin -- \
  ls /host/etc/iscsi/nodes/
```

---

## Issue: "Portal doesn't exist" Warning in NAS Logs

**Symptom:** Synology DSM logs show:

```
Initiator [iqn.2004-10.com.ubuntu:01:65feca77e5f9] failed to login to iSCSI Target
[k8s-csi-pvc-<uuid>-<suffix>] due to Portal doesn't exist.
```

**Cause:** A Released PV's NAS target has been deleted, but nodes still have a stale
`/etc/iscsi/nodes/<iqn>/` entry on disk. With `node.startup=manual` these don't mount on boot, but
the broken target causes the NAS to log the warning on each connection attempt.

**Fix:**

```bash
# 1. Identify the Released PV
kubectl get pv | grep Released

# 2. Note the target IQN from the PV
kubectl get pv <pv-name> -o jsonpath='{.spec.csi.volumeAttributes.targetIQN}'

# 3. Delete the NAS LUN from DSM → iSCSI Manager → LUN tab (if not already deleted)

# 4. Delete the PV object from Kubernetes
kubectl delete pv <pv-name>

# 5. Remove stale iscsid entries from all nodes
kubectl get pods -n synology-csi -o name | grep synology-csi-node
# Run for each matching node pod:
kubectl exec -n synology-csi <node-pod> -c csi-plugin -- \
  rm -rf /host/etc/iscsi/nodes/<target-iqn>
```

> **Note:** All 5 nodes share the same initiator IQN (`iqn.2004-10.com.ubuntu:01:65feca77e5f9`)
> — they were cloned from the same Ubuntu image. This is normal for this cluster.

---

## Issue: iSCSI REOPEN Loop

**Symptom:** CSI node logs show repeated `REOPEN` messages. Pod is stuck in ContainerCreating.
NAS session is stale after a network blip.

**Fix:**

```bash
# 1. In DSM → iSCSI Manager → Target tab: disable then re-enable the target
# (This forces the NAS to drop the stale session)

# 2. Force a clean detach/re-attach cycle in Kubernetes
kubectl get volumeattachment | grep <pvc-uid>
kubectl delete volumeattachment <name>
# Kubernetes will re-create the VolumeAttachment and trigger a fresh iSCSI login
```

> Data is never at risk during a REOPEN loop — the volume is not mounted.

---

## Issue: VolumeAttachment Node Mismatch (After Cluster Restart)

**Symptom:** Pod restarts after cluster maintenance but lands on a different node than where the
VolumeAttachment (iSCSI session) exists. Kubelet logs show `readdirent: input/output error`.

**Cause:** The existing VolumeAttachment points to the old node. Synology NAS enforces exclusive
iSCSI access per LUN — the new node's login is rejected.

**Fix:**

```bash
# Check where the VolumeAttachment says the volume is attached
kubectl get volumeattachment | grep <pvc-name>
kubectl get volumeattachment <name> -o jsonpath='{.spec.nodeName}'

# Compare to where the pod is running
kubectl get pod <name> -n <ns> -o jsonpath='{.spec.nodeName}'

# If they differ, delete the pod — StatefulSet reschedules to the correct node
kubectl delete pod <name> -n <ns>
```

---

## Issue: Transport Offline / Login Failure

**Symptom:** `kubectl describe pv` or CSI logs show `non-retryable iSCSI login failure (error 19)`.

**Cause:** Another node already holds an exclusive iSCSI session to this LUN.

**Diagnosis:**

```bash
# Find which node owns the active session
kubectl get volumeattachment -o wide | grep <pvc-name>

# Check if the pod and VolumeAttachment are on the same node
# If not, see "VolumeAttachment Node Mismatch" above
```

---

## Orphaned LUN Cleanup

Released PVs = orphaned iSCSI LUNs consuming NAS storage indefinitely. The `Retain` policy means
Kubernetes never deletes them.

```bash
# Audit for Released PVs (each = orphaned LUN)
kubectl get pv | grep Released

# For each Released PV:
# 1. Get the NAS LUN IQN suffix (last part of targetIQN)
kubectl get pv <pv-name> -o jsonpath='{.spec.csi.volumeAttributes.targetIQN}'

# 2. Delete LUN in DSM → iSCSI Manager → LUN tab
#    (LUN name matches the PV name or IQN suffix)

# 3. Delete the PV object
kubectl delete pv <pv-name>

# 4. Remove stale iscsid entries from nodes (see above)
```

> **Rule of thumb:** Run `kubectl get pv | grep Released` after every chart upgrade or major
> cluster maintenance to catch orphaned LUNs early.

---

## Node IQN Reference

All 5 nodes share the same initiator IQN (cloned from same Ubuntu image):

```
iqn.2004-10.com.ubuntu:01:65feca77e5f9
```

| Node | IP |
|------|----|
| control-plane | 10.0.10.214 |
| node01 | 10.0.10.235 |
| node02 | 10.0.10.211 |
| node03 | 10.0.10.244 |
| node04 | 10.0.10.220 |

---

## Related

- [ArgoCD PVC Protection](../troubleshooting/argocd-pvc-protection.md) — preventing PVC deletion during upgrades
- [Synology CSI](synology-csi.md) — CSI driver configuration and StorageClass reference
