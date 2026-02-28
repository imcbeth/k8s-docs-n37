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
kubectl scale statefulset falco-falcosidekick-ui-redis -n falco --replicas=0
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

### Step 4: Cordon and Drain Nodes

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

### Step 4: Handle Stuck Syncs

ArgoCD may enter auto-sync backoff after the outage. If apps show `OutOfSync` but aren't syncing, trigger manual syncs:

```bash
kubectl patch application <app-name> -n argocd --type=merge \
  -p '{"operation":{"initiatedBy":{"username":"manual"},"sync":{"syncStrategy":{"apply":{"force":false}},"prune":true}}}'
```

#### kube-prometheus-stack Hook Issue

The `kube-prometheus-stack` sync frequently gets stuck waiting on 174+ PreSync admission webhook hooks after a restart. To fix:

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

## Quick Reference: Claude Code Skills

These procedures are also available as Claude Code slash commands:

| Command | Purpose |
|---------|---------|
| `/cluster-shutdown` | Execute graceful cluster shutdown |
| `/cluster-healthcheck` | Run post-maintenance health check |
