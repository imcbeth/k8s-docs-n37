---
sidebar_position: 2
title: "Disaster Recovery"
description: "Recovery procedures for node failure, control plane failure, full cluster rebuild, and PVC corruption — single source of truth for the bad days"
---

# Disaster Recovery

When a runbook isn't enough. Each scenario below assumes the cluster is degraded enough that you need a planned procedure, not just a `kubectl rollout restart`.

The cluster is **5 nodes**: 1 control-plane (`10.0.10.214`) + 4 workers (`10.0.10.235/211/244/220`). All persistent data lives on the Synology NAS (`10.0.1.204`) via iSCSI, plus offsite in Backblaze B2 via Velero.

## RTO / RPO Targets

| Scenario | RTO target | RPO target | Notes |
|----------|------------|------------|-------|
| Single worker node lost | 30 minutes | 0 | Pods reschedule to other workers automatically |
| Control plane lost | 4 hours | 24h max (Velero daily) | Single control-plane, no HA |
| PVC corrupted / lost | 1 hour | 24h max | Restore from Velero CSI snapshot |
| Full cluster rebuild | 8 hours | 24h max | Provision → bootstrap → Velero restore |
| Synology NAS lost | days | 7d max | Velero offsite backups to B2 + manual NAS rebuild |

These are realistic for a homelab; treat them as targets to verify against, not SLAs.

## Single worker node failure

### Symptoms

- Node `NotReady` for 5+ minutes (kubelet stopped, hardware fault, network drop).
- Pods on that node stuck `Unknown` or `Terminating`.

### Recover

```bash
# 1. Identify the failed node
kubectl get nodes
kubectl describe node <node> | tail -30

# 2. Cordon to prevent scheduling
kubectl cordon <node>

# 3. Drain — moves pods off, respecting PDBs
kubectl drain <node> --ignore-daemonsets --delete-emptydir-data

# 4. Power-cycle the Pi (PoE switch port toggle, see Hardware doc)

# 5. Once node is Ready, uncordon
kubectl uncordon <node>
```

### Verify

```bash
# All nodes Ready
kubectl get nodes

# Pods rebalanced — none stuck on the recovered node
kubectl get pods -A --field-selector=spec.nodeName=<node> -o wide

# Chaos Mesh "pod-failure-node04" experiment validates this monthly
kubectl get podchaos -A
```

### Pitfall

If iSCSI sessions are stuck after the reboot, persistent volumes for Loki / Prometheus / Grafana / Falco-redis may remount read-only. Symptoms: "Read-only file system" in pod logs. Fix:

```bash
# Pick the affected PVC; delete the pod and let it remount
kubectl delete pod <pod> -n <ns>
```

This is the recovery pattern that worked after the UDR factory reset on 2026-04-19.

---

## Control plane failure

### Symptoms

- `kubectl` requests time out.
- Control-plane node unreachable but workers are still Ready (workloads keep serving traffic for ~5 minutes before liveness/readiness updates stall).

### Recover

The cluster has a **single control-plane node**. Recovery requires either:

**A. The control-plane node is recoverable (network blip, transient OS issue):**

```bash
ssh imcbeth@10.0.10.214
sudo systemctl status kubelet containerd
sudo systemctl restart kubelet
journalctl -u kubelet -n 100
```

**B. Control-plane node is unrecoverable — restore from etcd backup:**

Velero's daily ArgoCD config backup (1:30 AM) includes etcd snapshots indirectly via the ArgoCD CRD state. For a true etcd restore:

```bash
# 1. Provision a fresh Pi 5 with the same IP (10.0.10.214) and hostname
#    Follow docs/kubernetes/installation.md to bootstrap kubeadm

# 2. Stop kubelet on the new node
ssh imcbeth@10.0.10.214 sudo systemctl stop kubelet

# 3. Restore the latest etcd snapshot from Velero / NAS backup
#    Etcd backups live at: /etc/kubernetes/backups/etcd-*.db on the NAS

ssh imcbeth@10.0.10.214
sudo etcdctl --data-dir=/var/lib/etcd-restored \
  snapshot restore /tmp/etcd-snapshot.db

sudo mv /var/lib/etcd /var/lib/etcd.broken
sudo mv /var/lib/etcd-restored /var/lib/etcd

# 4. Restart kubelet — control plane comes up on the restored state
sudo systemctl start kubelet

# 5. Wait for the apiserver pod to be Ready, then verify
kubectl get pods -n kube-system
kubectl get nodes
```

### Verify

```bash
# All workers Ready, all critical workloads Healthy
kubectl get nodes
kubectl get application -n argocd -o json | jq '.items[] | "\(.metadata.name) \(.status.health.status)"'
```

### Pitfall

`etcd` restore reverts the cluster state to the snapshot timestamp. **Any workloads created between snapshot and now are gone** unless their definitions live in git (which they do — ArgoCD will re-sync them). PVCs survive because they're on the NAS, not in etcd; only PVCs created via ArgoCD-managed manifests will be reconciled.

The single-control-plane limitation is intentional for this homelab. Adding a second control-plane node would require either:

- A second NAS-backed `/var/lib/etcd` volume (etcd needs SSD, not iSCSI HDD)
- An odd number of control planes (3 = quorum)

If RPO < 4 hours becomes a requirement, plan for HA control plane and Synology RAID failover before adding more apps.

---

## PVC corrupted or accidentally deleted

### Symptoms

- Pod CrashLoopBackOff with "no such file" / "permission denied" on a mounted path.
- `kubectl describe pvc` shows the PVC is missing or in `Lost`.

### Recover

**Restore from Velero CSI snapshot (RPO 24h, faster):**

```bash
# 1. List recent backups
velero backup get

# 2. Pick the most recent one before corruption (daily-pvc-backup-*)
velero restore create --from-backup daily-pvc-backup-<date> \
  --include-namespaces <ns> \
  --include-resources persistentvolumeclaims,persistentvolumes

# 3. Watch the restore
velero restore describe <restore-name>
```

**Restore from B2 (off-NAS, RPO up to 7d, slower):**

```bash
# Velero is configured with the B2 BackupStorageLocation as primary
# (see docs/applications/velero.md). Same restore command works:
velero restore create --from-backup weekly-cluster-backup-<date> \
  --include-namespaces <ns>
```

### Verify

```bash
kubectl get pvc -n <ns>
kubectl logs <pod> -n <ns> --tail=50
# Pod should start cleanly; the volume mount should have the restored data
```

### Pitfall

Snapshot restores recreate the PV/PVC pair, but the **PV claim ref** points at the new PVC. If a workload was already attached to the old PVC, you need to scale it down first:

```bash
kubectl scale deployment <name> -n <ns> --replicas=0
velero restore create ...
kubectl scale deployment <name> -n <ns> --replicas=1
```

For StatefulSets the pattern is the same but with `kubectl delete pod <pod>` after restore to force a fresh mount.

---

## Full cluster rebuild

### When to use

The control plane is gone, multiple worker nodes are unrecoverable, **or** you're intentionally redoing the cluster (Kubernetes major version upgrade, hardware migration).

### Recover

```bash
# 1. Provision all 5 Pis from scratch
#    Follow docs/kubernetes/installation.md
#    - Flash Raspberry Pi OS
#    - Apply cluster-configuration.md tweaks
#    - kubeadm init on control-plane
#    - kubeadm join on workers

# 2. Bootstrap ArgoCD — manual apply of the bootstrap secret
kubectl apply -f secrets/argocd-git-access.yaml

# 3. Apply the root ArgoCD Application (self-management)
kubectl apply -f manifests/applications/argocd.yaml

# 4. Wait for sync waves to complete (this can take ~30-45 min)
#    Watch ArgoCD UI at https://argocd.k8s.n37.ca

# 5. Restore stateful data from Velero
velero restore create --from-backup weekly-cluster-backup-<latest> \
  --exclude-namespaces argocd,kube-system,calico-system,tigera-operator
```

### Verify

Use the `/cluster-healthcheck` skill for a full validation sweep:

```bash
# Expected output: all 40+ ArgoCD apps Synced+Healthy
kubectl get application -n argocd
```

### Pitfall

The order of operations matters. `kubeadm init` provisions CoreDNS in `kube-system`; if you Velero-restore the kube-system namespace, you'll overwrite the freshly-generated certs and the new cluster won't trust its own apiserver. **Exclude kube-system, calico-system, and tigera-operator from the Velero restore** — these are bootstrap-time concerns, not data.

---

## Synology NAS failure

### When to use

NAS unreachable, RAID degraded beyond recovery, or you're moving to a new NAS.

### Impact

- All PVCs become `Lost` (iSCSI sessions error out).
- Loki / Prometheus / Grafana / Falco-redis / Velero / Argo Workflows / Tempo / Uptime Kuma / Zot all lose their data.
- The cluster itself keeps running on local node state — workloads that don't use PVCs (cert-manager, external-dns, ingress-nginx, oauth2-proxy, metallb, sealed-secrets, tigera, gatekeeper, falco, alloy) stay healthy.

### Recover

```bash
# 1. Rebuild / replace the NAS hardware. Follow Synology DSM setup.
#    - Re-create the iSCSI targets with the SAME target IQNs (see Hardware.md)
#    - Re-attach the SAME volume2 / volume4 mount points

# 2. Restart Synology CSI on every node so iSCSI sessions re-establish
kubectl rollout restart daemonset/synology-csi-node -n kube-system

# 3. Restore data from Velero B2 backups (offsite — survived NAS loss)
velero backup get --selector=schedule=weekly-cluster-backup
velero restore create --from-backup weekly-cluster-backup-<latest>
```

### Verify

```bash
# All PVCs Bound
kubectl get pvc -A

# Critical workloads Healthy
kubectl get pods -n default -l app.kubernetes.io/name=prometheus
kubectl get pods -n loki
kubectl get pods -n velero
```

### Pitfall

The Velero backup is what saves you here — **without it, NAS loss = data loss**. Confirm the daily/weekly backup schedule is running before relying on this procedure:

```bash
velero backup get --selector=schedule=daily-pvc-backup | head -5
velero backup get --selector=schedule=weekly-cluster-backup | head -5
```

If the schedule hasn't run in >48h, fix that **before** the NAS dies, not after.

## Case study — the 16-day silent outage (2026-06-21)

This is a postmortem of a multi-workload outage that went undetected for sixteen days. It's documented here because the failure mode and the design fix matter more than the incident itself — they shape every future "let's add monitoring or auto-remediation" decision.

### What happened

On 2026-06-21 a routine `/cluster-healthcheck` run found five workloads in `CrashLoopBackOff`:

- `prometheus-kube-prometheus-stack-prometheus-0`
- `loki-0` (144 restarts over 16 days)
- `kube-prometheus-stack-grafana-*`
- `uptime-kuma-*` (144 restarts)
- `falco-falcosidekick-ui-redis-0`

All five had the same root cause: their iSCSI-backed PVCs had been remounted read-only by btrfs after some session interruption around 2026-06-05. The kernel-level mount was RO. Three of the four globalmounts on `node04` were RO at the device level, not just the pod bind-mount.

ArgoCD reported every app `Synced + Healthy` the entire time.

### Why nothing alerted

The `pvc-ro-remediator` CronJob had been verified working end-to-end on 2026-06-07. The original design queried Prometheus for firing `PVCMountReadOnly` alerts:

```sh
curl http://prometheus:9090/api/v1/alerts
  | jq '.data.alerts[] | select(.labels.alertname=="PVCMountReadOnly" and .state=="firing")'
```

When Prometheus's own PVC went RO, Prometheus crashed → the curl failed → the Job exited non-zero → `BackoffLimitExceeded`. The CronJob's `failedJobsHistoryLimit: 3` pruned the failure history within ~6 minutes. Every subsequent 2-minute run failed the same way.

AlertManager kept running fine (different PVC, RW). But it had no alerts to deliver because Prometheus rule evaluation was down.

### The dependency cycle

The remediator's failure mode is what makes this important. It's not just "Prometheus broke." It's that the remediator system **depended on Prometheus to know what was broken**. When Prometheus went down, the *entire* observability + auto-remediation stack went silent at the same time.

```
Prometheus PVC goes RO
  ↓
Prometheus crashes
  ↓
Rule evaluation stops (no alerts evaluated)
  ↓
Remediator curl to Prometheus fails
  ↓
CronJob Jobs all fail (BackoffLimitExceeded)
  ↓
Jobs prune from history within 6 min
  ↓
Other workloads keep crashing for 16 days
```

This is the textbook "monitor the system from the system" anti-pattern.

### Recovery

Manual, step by step:

1. **Deleted Prometheus, Loki, Grafana pods on `node03`** — node03's globalmount was still RW, fresh pods got clean mounts.
2. **Discovered 3 of 4 globalmounts on `node04`** were RO at the kernel level — pod delete alone wasn't enough.
3. **Cordoned `node04`**, deleted the 3 affected pods (Grafana, Falco-Redis, Uptime Kuma). They rescheduled to other nodes; CSI driver did fresh attaches.
4. **Uncordoned `node04`** — its RO globalmounts cleaned up when the next pod requested a volume.

Total recovery time: ~45 minutes once the issue was identified.

### The fix

[PR #753](https://github.com/imcbeth/homelab/pull/753) rewrote the remediator to query the `pvc-mount-monitor` DaemonSet pods directly via the Service endpoints, bypassing Prometheus entirely. See [PVC RO Mount Auto-Remediation](../storage/pvc-ro-automation.md#why-query-the-monitors-directly-not-via-prometheus) for the full design rationale.

### Lessons that apply beyond this incident

1. **An auto-remediation system that depends on the system being remediated is worse than no automation.** People stop watching because "the automation has it covered."

2. **ArgoCD `Synced + Healthy` ≠ "the automation works."** ArgoCD checks resource definitions match git. It doesn't run the CronJobs and verify the output. The signal lived inside Job pod logs, which got pruned by `failedJobsHistoryLimit: 3`.

3. **Dead-man switches need to run on a path independent of the system they're watching.** If a Prometheus alert is your only signal that the remediator stopped working, you'll lose both at the same time.

4. **Failure-history retention should be longer than the detection window.** `failedJobsHistoryLimit: 3` at a 2-minute cadence means 6 minutes of history. Useful for normal debugging, completely inadequate as a forensics tool for a 16-day incident.

5. **iSCSI RO can be at the globalmount layer, not just the pod bind-mount.** Pod delete creates a fresh pod but it bind-mounts the same RO device. Cross-node reschedule (drain or cordon-then-delete) forces a fresh CSI attach.

### Open follow-ups

- **Dead-man-switch alert** for the remediator — should fire if no successful Job has completed in the last N hours, *and the alert path must not depend on Prometheus rule evaluation*. The hard part is "not depending on Prom" — possibilities being considered: AlertManager external heartbeat receiver, healthchecks.io style external monitoring, or a sidecar that emits to a non-Prom path.
- **Failure-history retention** — bump `failedJobsHistoryLimit` on the remediator to something like 50 so a forensics review N days later still has data. Trade-off is etcd object count.

## Validating the DR posture

The cluster runs a monthly DR validation CronWorkflow (deployed 2026-03-25, see `manifests/base/argo-workflows/dr-validation-cronworkflow.yaml`) that:

1. Lists current backups
2. Creates a fresh backup
3. Verifies it landed in B2
4. Restores into the `velero-test` namespace
5. Verifies restored resources match source
6. Cleans up the test namespace

If the next-run timestamp is in the past, the validation isn't running — investigate before assuming DR works.

```bash
kubectl get cronworkflow -n argo-workflows dr-validation -o jsonpath='{.status}{"\n"}'
```

## Related

- **[Runbooks](./runbooks.md)** — first-line fixes for things that aren't quite a disaster yet
- **[Velero](../applications/velero.md)** — backup schedules, retention, restore command reference
- **[Sealed Secrets](../security/secrets-management.md)** — restoring secrets after a cluster rebuild
- **[Synology CSI](../storage/synology-csi.md)** — iSCSI configuration, troubleshooting stale sessions
