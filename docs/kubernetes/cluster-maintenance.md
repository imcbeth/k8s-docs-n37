---
title: "Cluster Maintenance"
description: "Procedures for graceful cluster shutdown, startup, and post-maintenance health verification"
sidebar_position: 3
---

# Cluster Maintenance

This guide covers procedures for gracefully shutting down and bringing up the Kubernetes homelab cluster, including NAS maintenance scenarios where iSCSI volumes must be safely detached.

## Cluster Topology

| Node | IP Address | Role | SSH User |
|------|-----------|------|----------|
| control-plane | 10.0.10.214 | Control Plane | imcbeth |
| node01 | 10.0.10.235 | Worker | imcbeth |
| node02 | 10.0.10.211 | Worker | imcbeth |
| node03 | 10.0.10.244 | Worker | imcbeth |
| node04 | 10.0.10.220 | Worker | imcbeth |

**SSH Key:** `~/.ssh/id_ed25519_k8s`

## NAS-Dependent Workloads

These workloads have PersistentVolumeClaims backed by the Synology NAS via iSCSI (`synology-iscsi-retain` StorageClass):

| Workload | Namespace | Type | PVC Size |
|----------|-----------|------|----------|
| Prometheus | default | StatefulSet | 50Gi |
| Grafana | default | Deployment | 5Gi |
| Loki | loki | StatefulSet | 20Gi |
| Trivy Server | trivy-system | StatefulSet | 5Gi |
| Falco Redis | falco | StatefulSet | 2Gi |

## After any kubeadm upgrade: re-check static pod customizations

`kubeadm upgrade apply` **rewrites** `/etc/kubernetes/manifests/*.yaml` and silently discards local edits. These files are host-level and **not in git**, so nothing detects the drift — no ArgoCD diff, no alert on the manifest.

The 1.36 upgrade reverted `--bind-address=0.0.0.0` → `127.0.0.1` on **both** kube-controller-manager and kube-scheduler. Their Prometheus scrape targets went dark for **38 days** before anyone noticed (2026-07-30 → 2026-09-06). `TargetDown` fired correctly the whole time.

```bash
# Verify after every upgrade
ssh -i ~/.ssh/id_ed25519_k8s imcbeth@10.0.10.214 \
  "sudo grep -H bind-address /etc/kubernetes/manifests/kube-controller-manager.yaml \
                             /etc/kubernetes/manifests/kube-scheduler.yaml"
# Expect --bind-address=0.0.0.0 on BOTH. 127.0.0.1 breaks metrics scraping.
```

If reverted, back up and restore:

```bash
ssh -i ~/.ssh/id_ed25519_k8s imcbeth@10.0.10.214 "
  TS=\$(date +%Y%m%d%H%M%S)
  sudo mkdir -p /root/k8s-manifest-backups
  for f in kube-controller-manager kube-scheduler; do
    sudo cp /etc/kubernetes/manifests/\$f.yaml /root/k8s-manifest-backups/\$f.yaml.\$TS
    sudo sed -i 's/--bind-address=127.0.0.1/--bind-address=0.0.0.0/' /etc/kubernetes/manifests/\$f.yaml
  done"
# kubelet reloads static pods automatically within ~30s.
```

:::tip A firing alert nobody reads is the same as no alert
This is a distinct failure from the [Velero PrometheusRule that never loaded](../applications/velero.md#fault-2--the-alert-that-would-have-caught-it-had-never-loaded). Here detection worked perfectly for 77 days on two other targets and 38 days on these — the gap was *attention*, not instrumentation.

When reviewing cluster health, enumerate firing alerts explicitly rather than assuming quiet means healthy:

```bash
kubectl -n default exec prometheus-kube-prometheus-stack-prometheus-0 -c prometheus -- \
  wget -qO- 'http://localhost:9090/api/v1/query?query=ALERTS{alertstate="firing"}'
```

:::

## Graceful Shutdown

Use this procedure when the NAS needs maintenance, or for any planned full cluster shutdown.

:::danger Critical
Never power off the NAS while iSCSI volumes are attached. This risks filesystem corruption on all persistent volumes.
:::

### Step 1: Disable ArgoCD Auto-Sync

ArgoCD will fight any manual scale-downs if auto-sync is enabled. Disable it on all applications first:

```bash
kubectl get applications.argoproj.io -n argocd \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' | \
  while read app; do
    kubectl patch application "$app" -n argocd --type=merge \
      -p '{"spec":{"syncPolicy":{"automated":null}}}'
  done
```

### Step 1b: Suspend CronJobs and Stop the PVC Prober

:::danger Do not skip this
`pvc-ro-remediator` runs **every two minutes** and mounts PVCs to repair read-only mounts. It
will fire mid-shutdown and re-attach a volume you have just detached — stalling Step 3, or
re-establishing an iSCSI session after you believed the NAS was clear.

`pvc-writability-prober` (Deployment, `synology-csi`) probes every PVC and has the same effect.
:::

```bash
# Suspend every CronJob — they simply miss a run while the cluster is down
kubectl get cronjobs -A \
  -o jsonpath='{range .items[*]}{.metadata.namespace}{" "}{.metadata.name}{"\n"}{end}' | \
  while read ns name; do
    kubectl patch cronjob "$name" -n "$ns" --type=merge -p '{"spec":{"suspend":true}}'
  done

kubectl scale deployment pvc-writability-prober -n synology-csi --replicas=0

# Verify nothing is left unsuspended
kubectl get cronjobs -A --no-headers \
  -o custom-columns='NS:.metadata.namespace,NAME:.metadata.name,SUSPEND:.spec.suspend'
```

Suspending the rest (`remediator-deadman`, `vsc-orphan-janitor`, `compliance-reporter`,
`uptime-kuma-monitor-drift`, `velero-restore-validator`) also prevents false alerts firing
while the cluster is down.

**Reverse this on startup.** Leaving the remediator suspended is a silent loss of the
read-only-remount safety net, and it will not announce itself.

### Step 2: Scale Down NAS-Dependent Workloads

:::warning Prometheus Operator
The Prometheus Operator continuously reconciles the Prometheus StatefulSet. You **must** scale the operator to 0 before scaling the StatefulSet, or it will be immediately restored to the desired replica count.
:::

```bash
# Scale operator FIRST
kubectl scale deployment kube-prometheus-stack-operator -n default --replicas=0
sleep 5

# Then scale the workloads
kubectl scale statefulset prometheus-kube-prometheus-stack-prometheus -n default --replicas=0
kubectl scale deployment kube-prometheus-stack-grafana -n default --replicas=0
kubectl scale statefulset loki -n loki --replicas=0
kubectl scale statefulset trivy-server -n trivy-system --replicas=0
kubectl scale statefulset tempo -n tempo --replicas=0
kubectl scale statefulset zot -n zot --replicas=0
kubectl scale deployment uptime-kuma -n uptime-kuma --replicas=0
kubectl scale deployment localstack -n localstack --replicas=0
```

:::note `falco-falcosidekick-ui-redis` is deliberately absent
Its 2Gi PVC was removed and the pod is now ephemeral, so it is not volume-relevant. The drain
in Step 4 handles it. Verified 2026-10-24.
:::

**Then confirm every PVC still exists.** A StatefulSet with
`persistentVolumeClaimRetentionPolicy.whenScaled: Delete` has its claim **deleted** by
`--replicas=0`. The Loki chart defaulted to exactly that, so this procedure was destroying
`storage-loki-0` on every run until 2026-10-24 — see
[Loki: the chart default that deletes the PVC](../applications/loki.md).

```bash
# Expect 8. A missing PVC means a whenScaled=Delete policy consumed it.
kubectl get pvc -A --no-headers | wc -l

# Any StatefulSet that will delete its claim on scale-down:
kubectl get sts -A -o json | python3 -c "
import json,sys
for s in json.load(sys.stdin)['items']:
    pol = s['spec'].get('persistentVolumeClaimRetentionPolicy') or {}
    if pol.get('whenScaled') == 'Delete':
        print('HAZARD:', s['metadata']['namespace'] + '/' + s['metadata']['name'], pol)"
```

### Step 3: Verify Volume Detachment

Wait for all pods to terminate, then confirm the iSCSI volumes are detached:

```bash
# Wait for pods to terminate
kubectl wait --for=delete pod \
  -l app.kubernetes.io/name=prometheus -n default --timeout=120s

# Verify NO VolumeAttachments remain
kubectl get volumeattachments
```

:::danger
Do NOT proceed to node shutdown until this command returns **no results**. Any remaining `csi.san.synology.com` VolumeAttachments indicate volumes still mounted on a node.
:::

**VolumeAttachment count is not proof.** It is Kubernetes' bookkeeping, not the initiator
state. The check that actually licenses powering off the NAS is asking the nodes directly:

```bash
for ip in 10.0.10.235 10.0.10.211 10.0.10.244 10.0.10.220; do
  echo -n "  $ip: "
  ssh -i ~/.ssh/id_ed25519_k8s -o StrictHostKeyChecking=no -o ConnectTimeout=8 \
      imcbeth@$ip "sudo iscsiadm -m session 2>&1 | head -5"
done
```

Expect `iscsiadm: No active sessions.` from every node. If a session persists, a pod still
holds the volume — most likely `pvc-ro-remediator` re-attached it because Step 1b was skipped.

### Step 4: Cordon and Drain Nodes

:::tip Delete the Gatekeeper PDB first, not reactively
It has `minAvailable: 1` across 2 replicas, so the **second** node drained always blocks and
burns the full timeout — node02 stalled for 2m30s this way on 2026-10-24. ArgoCD restores the
PDB on the next sync.

```bash
kubectl delete pdb -n gatekeeper-system --all
```

Run one drain per command as well: four drains in a single shell invocation can exceed a
two-minute tool timeout and leave you unsure which node finished.
:::

```bash
# Cordon all nodes
kubectl cordon control-plane node01 node02 node03 node04

# Drain workers
for node in node01 node02 node03 node04; do
  kubectl drain $node \
    --ignore-daemonsets \
    --delete-emptydir-data \
    --force \
    --timeout=120s
done
```

**If Gatekeeper PDB blocks the drain**, delete it — ArgoCD restores it automatically on next startup:

```bash
kubectl delete pdb -n gatekeeper-system --all
```

### Step 5: Shutdown Nodes

Workers first, control plane last:

```bash
SSH_KEY=~/.ssh/id_ed25519_k8s
SSH_OPTS="-i $SSH_KEY -o ConnectTimeout=10"

# Workers (can be parallel)
for ip in 10.0.10.235 10.0.10.211 10.0.10.244 10.0.10.220; do
  ssh $SSH_OPTS imcbeth@$ip "sudo shutdown -h now" &
done
wait

# Verify workers are down
sleep 15
for ip in 10.0.10.235 10.0.10.211 10.0.10.244 10.0.10.220; do
  ping -c 1 -W 2 $ip > /dev/null 2>&1 \
    && echo "$ip: STILL UP" \
    || echo "$ip: DOWN"
done

# Control plane LAST
ssh $SSH_OPTS imcbeth@10.0.10.214 "sudo shutdown -h now"
```

### Shutdown Verification Checklist

- [ ] All 5 nodes unreachable via ping
- [ ] All iSCSI VolumeAttachments released before shutdown
- [ ] ArgoCD auto-sync disabled on all apps
- [ ] NAS is safe for maintenance

---

## Startup and Health Check

### Boot Order

:::info Boot Sequence

1. **NAS first** — iSCSI target service must be online
2. **Control plane** (10.0.10.214) — wait for `kubectl get nodes` to respond
3. **Workers** (node01–04) — can power on simultaneously
:::

### Step 1: Verify All Nodes Ready

```bash
kubectl get nodes -o wide
```

All 5 nodes should show `Ready`. They will show `SchedulingDisabled` from the pre-shutdown cordon — this is expected and fixed in the next step.

:::tip Kernel Updates
Unattended-upgrades may run during the boot process, upgrading the kernel. Verify with `uname -r` if you notice unexpected version changes.
:::

### Step 2: Uncordon All Nodes

```bash
kubectl uncordon control-plane node01 node02 node03 node04
```

### Step 3: Re-enable ArgoCD Auto-Sync

```bash
kubectl get applications.argoproj.io -n argocd \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' | \
  while read app; do
    kubectl patch application "$app" -n argocd --type=merge \
      -p '{"spec":{"syncPolicy":{"automated":{"prune":true,"selfHeal":true}}}}'
  done
```

Wait 60–90 seconds for ArgoCD to reconcile, then check:

```bash
kubectl get applications.argoproj.io -n argocd \
  -o custom-columns='NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status'
```

### Step 3b: Un-suspend CronJobs and Restart the Prober

Symmetric to Step 1b, and easy to forget because nothing complains:

```bash
kubectl get cronjobs -A \
  -o jsonpath='{range .items[*]}{.metadata.namespace}{" "}{.metadata.name}{"\n"}{end}' | \
  while read ns name; do
    kubectl patch cronjob "$name" -n "$ns" --type=merge -p '{"spec":{"suspend":false}}'
  done

kubectl scale deployment pvc-writability-prober -n synology-csi --replicas=1

# All six should read false
kubectl get cronjobs -A --no-headers \
  -o custom-columns='NS:.metadata.namespace,NAME:.metadata.name,SUSPEND:.spec.suspend'
```

### Step 4: Handle Stuck Syncs

ArgoCD may enter auto-sync backoff after the outage. If apps show `OutOfSync` but aren't syncing, trigger manual syncs:

```bash
kubectl patch application <app-name> -n argocd --type=merge \
  -p '{"operation":{"initiatedBy":{"username":"manual"},"sync":{"syncStrategy":{"apply":{"force":false}},"prune":true}}}'
```

#### kube-prometheus-stack Hook Issue

The `kube-prometheus-stack` sync frequently gets stuck waiting on PreSync hooks after a
restart.

:::warning Read the full `operationState.message` — do not truncate it
On 2026-10-24 the message named `/ServiceAccount/kube-prometheus-stack-crds-upgrade`, and that
ServiceAccount **did not exist** — ArgoCD was waiting to delete something already gone.
Truncating the message at 90 characters hid which hook was blocking and sent the
investigation after the wrong one (`admission-create`) for several cycles.

```bash
kubectl get app kube-prometheus-stack -n argocd \
  -o jsonpath='{.status.operationState.message}'; echo
```

The release was deleting the sibling `crds-upgrade` Job, ClusterRole and ClusterRoleBinding.
:::

To fix:

```bash
# Clear the stuck operation
kubectl patch application kube-prometheus-stack -n argocd --type json \
  -p '[{"op":"remove","path":"/status/operationState"}]'
kubectl patch application kube-prometheus-stack -n argocd --type json \
  -p '[{"op":"remove","path":"/operation"}]'

# Manually restore the workloads
kubectl scale deployment kube-prometheus-stack-operator -n default --replicas=1
kubectl scale deployment kube-prometheus-stack-grafana -n default --replicas=1
sleep 5
kubectl scale statefulset prometheus-kube-prometheus-stack-prometheus -n default --replicas=1
```

### Step 5: Verify NAS Volumes

```bash
# All PVCs should be Bound
kubectl get pvc -A

# VolumeAttachments should exist (one per PVC)
kubectl get volumeattachments
```

### Step 6: Verify Workloads

```bash
# NAS-dependent workloads
echo -n "Prometheus Operator: "; kubectl get deploy kube-prometheus-stack-operator -n default -o jsonpath='{.status.readyReplicas}'; echo
echo -n "Prometheus: "; kubectl get sts prometheus-kube-prometheus-stack-prometheus -n default -o jsonpath='{.status.readyReplicas}'; echo
echo -n "Grafana: "; kubectl get deploy kube-prometheus-stack-grafana -n default -o jsonpath='{.status.readyReplicas}'; echo
echo -n "Loki: "; kubectl get sts loki -n loki -o jsonpath='{.status.readyReplicas}'; echo
echo -n "Trivy Server: "; kubectl get sts trivy-server -n trivy-system -o jsonpath='{.status.readyReplicas}'; echo
echo -n "Falco Redis: "; kubectl get sts falco-falcosidekick-ui-redis -n falco -o jsonpath='{.status.readyReplicas}'; echo
```

All should report `1`.

### Step 7: DaemonSet Health

```bash
kubectl get ds -A -o custom-columns='NS:.metadata.namespace,NAME:.metadata.name,DESIRED:.status.desiredNumberScheduled,READY:.status.numberReady'
```

| DaemonSet | Expected Count |
|-----------|---------------|
| calico-node, csi-node-driver, node-exporter, falco, istio-cni-node, ztunnel, kube-proxy, promtail, metallb-speaker | 5 |
| loki-canary, synology-csi-node | 4 (worker-only) |

### Step 8: Metrics API

```bash
kubectl top nodes
```

If unavailable, restart the metrics server:

```bash
kubectl rollout restart deployment metrics-server -n kube-system
```

### Step 9: Non-Running Pods

```bash
kubectl get pods -A --field-selector='status.phase!=Running,status.phase!=Succeeded'
```

**Expected:** No results. If `falco-falcosidekick-ui` is stuck in `Init:Error`, delete the pod to reschedule it near its Redis instance:

```bash
kubectl delete pod -n falco -l app.kubernetes.io/name=falcosidekick-ui
```

### Step 10: External Access

```bash
# Verify LoadBalancer IP
kubectl get svc -A --field-selector=spec.type=LoadBalancer

# Test ingress endpoints
curl -sk https://argocd.k8s.n37.ca/ | head -5
curl -sk https://grafana.k8s.n37.ca/ | head -5
```

### Step 11: Check the Prometheus Target Count

:::danger Application status will not catch a ztunnel blackhole
After a cold boot, ztunnel can lose XDS and silently reset connections to every
ambient-enrolled pod on its node while everything reports `Running` and `Synced + Healthy`.
The **only** symptom is a reduced target count. See
[Istio: ztunnel without XDS blackholes its whole node](../applications/istio.md).
:::

```bash
kubectl port-forward -n default svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 &
sleep 8
curl -s 'http://127.0.0.1:9090/api/v1/targets?state=active' | python3 -c "
import json,sys
from collections import Counter
ts = json.load(sys.stdin)['data']['activeTargets']
c = Counter(t['health'] for t in ts)
print(f\"total={len(ts)} up={c.get('up',0)} down={c.get('down',0)}\")
for t in ts:
    if t['health'] != 'up':
        print('  DOWN:', t.get('scrapePool'), t.get('labels',{}).get('instance'))"
```

Expect **98 total, 0 down** (count as of 2026-10-26). A target down with
`connection reset by peer` — rather than a timeout — is the ztunnel case.

### Startup Verification Checklist

- [ ] 5/5 nodes Ready and uncordoned
- [ ] ArgoCD auto-sync re-enabled
- [ ] 24+ apps Synced + Healthy
- [ ] 5/5 PVCs Bound with VolumeAttachments
- [ ] All NAS workloads running (Prometheus, Grafana, Loki, Trivy, Falco Redis)
- [ ] DaemonSets at expected counts
- [ ] Metrics API responsive (`kubectl top nodes`)
- [ ] No stuck pods
- [ ] LoadBalancer IP assigned (10.0.10.10)
- [ ] Gatekeeper PDB restored
- [ ] External endpoints accessible

---

## Verification Baseline

Application status is necessary but not sufficient. Several failure modes leave every
application `Synced + Healthy`, so compare against these counts after any maintenance.
Values as of **2026-10-26**:

| Check | Expected |
|---|---|
| Applications `Synced + Healthy` | 38 / 38 |
| Nodes `Ready` | 5 / 5 |
| Running pods | ~143 |
| PVCs `Bound` | 8 / 8 |
| VolumeAttachments | 8 |
| Certificates `Ready` | 11 / 11 |
| DaemonSets at desired count | 13 / 13 |
| CronJobs with `suspend=false` | 6 / 6 |
| **Prometheus targets up** | **98 / 98** |
| `loki` `whenScaled` | `Retain` |
| `--bind-address` on controller-manager + scheduler | `0.0.0.0` |

:::tip An `OutOfSync` immediately after startup is often a stale comparison
`zot` reported `OutOfSync` on 2026-10-24 purely because ArgoCD's rendered target carried
`serviceName: ""` while its normalized live state dropped the empty string. A hard refresh
cleared it with no actual drift:

```bash
kubectl patch application <app> -n argocd --type=merge \
  -p '{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}'
```

Likewise `localstack` sitting at `Progressing` with reason `NewReplicaSetAvailable` is a
**completed** rollout ArgoCD has not settled on yet, not a stalled one.
:::

## OS Updates

Ubuntu patching is best done **inside an existing drain window**. When nodes are already
cordoned and drained for a shutdown, apply updates then: a drained node is the safest moment
to touch the OS, and if a kernel reboot is pending the shutdown doubles as that reboot.

### `apt-get upgrade` silently holds back split packages

`upgrade` never installs **new** packages by design. When an upstream package is split into
sub-packages, it therefore sits in `apt list --upgradable` indefinitely while `upgrade`
reports success and exits 0.

`linux-firmware` hit exactly this: it was split into ~18 sub-packages
(`-broadcom-wireless`, `-intel-*`, `-mellanox-*`, …), so it survived a full `upgrade` run on
2026-10-24 and only moved under `dist-upgrade` on 2026-10-26.

```bash
# Gate on the dry run showing zero removals before trusting dist-upgrade
sudo apt-get --dry-run dist-upgrade | awk '/^Remv/{c++} END{print "removals:", c+0}'
```

Proceed only when that prints `0`.

:::warning Verify by re-querying state, never by exit code
`apt-get upgrade ... | tail -25; echo "EXIT:$?"` always prints `EXIT:0` — that is `tail`'s
status, not apt's. Confirm the real outcome with `apt list --upgradable` and `dpkg -l`
afterwards.
:::

### `dpkg -l` counts removed packages unless you anchor on `^ii`

State `rc` means *removed, conffiles remain* — the files are already gone. Counting
`dpkg -l | grep linux-image` therefore over-reports badly: on 2026-10-24 it produced a
phantom "19 installed kernels, autoremove has never run" when the real state was **3 `ii`**
(current, previous, and the `linux-image-raspi` meta) against **16 `rc`**, with
`autoremove` removing **0** packages on every node.

```bash
dpkg -l | awk '/linux-image/ {print $1}' | sort | uniq -c   # see the ii/rc split
dpkg -l | awk '/^ii.*linux-image/ {print $2, $3}'           # what is actually installed
ls -1 /boot/vmlinuz-*                                        # cross-check on disk
```

What *does* accumulate is `/lib/modules/` trees for kernels whose packages are long gone — 18
of them in October 2026, but only **108 MB** of a 337 MB tree. Not worth touching boot
configuration to reclaim.

### `linux-firmware` does not touch the Pi boot path

`dpkg -L linux-firmware` writes only to `/lib/firmware` and `/usr/share`. The Raspberry Pi
boot path lives in `linux-firmware-raspi`, `rpi-eeprom` and `rpi-eeprom-firmware`. Treating a
`linux-firmware` bump as boot-risky is overcautious — it ships device blobs (Broadcom
wireless, GPU), not bootloader.

### Rolling pattern

One node at a time, canary first, control-plane last. Pick as canary the node with real
workload but **no PVC-backed pods**, so the canary carries no iSCSI reattach risk.

Per node: drain → dry-run gated on zero removals → `dist-upgrade` → verify `/boot` files
intact **before** rebooting → reboot → confirm kernel, firmware version and
`systemctl --failed` → wait `Ready` → uncordon.

On 2026-10-26 all five nodes completed in ~105 s each with zero failed units, and rolling
reboots avoided the ztunnel XDS blackhole entirely because `istiod` stayed reachable.

## Quick Reference: Claude Code Skills

These procedures are also available as Claude Code slash commands:

| Command | Purpose |
|---------|---------|
| `/cluster-shutdown` | Execute graceful cluster shutdown |
| `/cluster-healthcheck` | Run post-maintenance health check |
