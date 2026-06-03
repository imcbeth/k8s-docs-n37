---
sidebar_position: 4
title: "Resource Quotas"
description: "Per-namespace object-count quotas to cap blast radius from runaway controllers or resource leaks"
---

# Resource Quotas

`ResourceQuota` is a built-in Kubernetes admission control that caps the total resources or object counts in a namespace. The homelab uses **object-count quotas** on 14 stable namespaces to detect runaway pod creation or resource leaks before they consume the cluster.

## Goal

A misbehaving controller in `argocd` shouldn't be able to spawn 500 pods and starve `falco`. ResourceQuotas turn that scenario from a cluster-wide degradation into a clear admission rejection with an instant signal in `kubectl describe quota`.

## What this implements

| Property | Value |
|----------|-------|
| **Source** | `manifests/base/resource-quotas/quotas.yaml` |
| **ArgoCD app** | `resource-quotas`, sync-wave `-38` |
| **Object name** | `object-count-quota` (consistent across namespaces) |
| **Scope** | 14 stable namespaces (see below) |
| **Counts** | `count/pods`, `count/persistentvolumeclaims`, `count/services`, `count/configmaps`, `count/secrets` |

Intentionally **not** CPU/memory quotas. Object-count admission rejection is recoverable (the create just fails); a too-low memory quota would block valid scale-up of running workloads under load.

## Namespaces covered

Sizing rule of thumb: 3-5x current observed count, with reasonable floors. Two namespaces have higher pod caps to accommodate multi-component workloads.

| Namespace | Pods | PVCs | Services | ConfigMaps | Secrets |
|-----------|-----:|-----:|---------:|-----------:|--------:|
| argocd | 40 | 10 | 25 | 100 | 50 |
| cert-manager | 15 | 5 | 10 | 30 | 30 |
| external-dns | 10 | 5 | 10 | 20 | 20 |
| ingress-nginx | 15 | 5 | 10 | 20 | 20 |
| lifeonabike | 15 | 5 | 10 | 20 | 20 |
| localstack | 10 | 5 | 10 | 20 | 20 |
| metallb-system | 15 | 5 | 10 | 20 | 20 |
| oauth2-proxy | 10 | 5 | 10 | 20 | 20 |
| synology-csi | 25 | 5 | 10 | 30 | 30 |
| tempo | 10 | 5 | 10 | 20 | 20 |
| unipoller | 10 | 5 | 10 | 20 | 20 |
| uptime-kuma | 10 | 5 | 10 | 20 | 20 |
| velero | 20 | 5 | 10 | 30 | 30 |
| zot | 10 | 5 | 10 | 20 | 20 |

argocd's `count/configmaps: 100` looks high but matches reality — ArgoCD creates a configmap per app definition and per cluster, so headroom matters.

## Namespaces NOT covered

Intentionally excluded because their object counts are dynamic, operator-managed, or already protected by another mechanism:

- **`argo-workflows`, `argo-events`** — workflow pods spawn on every CI run; a quota would block builds.
- **`flink-demo`, `flink-operator`, `kafka`, `strimzi-system`** — operator-managed scale; the operators add/remove pods as jobs run.
- **`trivy-system`** — creates one scan Job per cluster image (~100+ active scans is normal).
- **`falco`** — DaemonSet; pod count = node count and scales with cluster, not workload.
- **`loki`** — singleBinary + sidecars; tight memory margin and operator-rebalanced.
- **`chaos-mesh`** — *intentionally* injects pods for failure testing.
- **`istio-system`** — controlled by the istio operator.
- **`default`** — catch-all with mixed workloads (Prometheus + Grafana + blackbox + alertmanager + node-exporter DaemonSet).
- **`kube-system`, `calico-system`, `tigera-operator`** — control plane; quota'ing these is dangerous.
- **`gatekeeper-system`** — already has `gatekeeper-critical-pods` quota from its Helm chart (`pods: 100`).

## How sizing works

For each included namespace:

1. **Measure current count** — `kubectl get pods,pvc,svc,cm,secrets -n <ns> --no-headers | wc -l` per kind.
2. **Multiply by 3-5×** — gives room for rolling updates (double-up during a deploy), debug pods, normal growth.
3. **Set a sensible floor** — single-replica apps still get at least 10 pod headroom for ad-hoc work.

Before applying, sanity-check that **no namespace is already over quota**:

```bash
for ns in argocd cert-manager external-dns ingress-nginx lifeonabike localstack \
          metallb-system oauth2-proxy synology-csi tempo unipoller uptime-kuma velero zot; do
  pods=$(kubectl get pods -n $ns --no-headers 2>/dev/null | wc -l)
  cms=$(kubectl get cm -n $ns --no-headers 2>/dev/null | wc -l)
  printf "%-18s pods=%-3s cms=%-3s\n" "$ns" "$pods" "$cms"
done
```

If any number is approaching the planned quota, raise the cap *before* applying. A `ResourceQuota` does not retroactively evict — it only blocks *new* creations.

## Operational queries

```bash
# Current usage vs hard limit across all quota'd namespaces
kubectl get resourcequota -A

# Detailed view for one namespace
kubectl describe quota object-count-quota -n argocd

# Find namespaces with high utilisation (>70% of quota)
kubectl get resourcequota -A -o json | jq -r '
  .items[] | select(.status.hard != null) |
  .status as $s | .metadata.namespace as $ns |
  ($s.hard | keys[]) as $k |
  select(($s.used[$k] | tonumber) / ($s.hard[$k] | tonumber) > 0.7) |
  "\($ns) \($k) \($s.used[$k])/\($s.hard[$k])"
'
```

## When admission is blocked

A pod create that hits the quota fails like this:

```
Error from server (Forbidden): pods "my-pod" is forbidden:
exceeded quota: object-count-quota,
requested: count/pods=1, used: count/pods=10, limited: count/pods=10
```

Three things to check:

1. **Is the spike legitimate?** A new service or scaled-up Deployment may genuinely need more. Update the quota.
2. **Are there orphaned pods?** Look for `Completed`/`Failed` pods that aren't being garbage-collected. CronJobs with `successfulJobsHistoryLimit` too high are a common offender.
3. **Is there a controller loop?** Same name, repeated creates. Check controller logs.

## Adding quotas to a new namespace

1. Decide whether the namespace is "stable" (predictable pod count) or "dynamic" (operator-managed or workload-driven). Only quota the stable ones.
2. Measure baseline usage (see above).
3. Add a new entry to `manifests/base/resource-quotas/quotas.yaml`:

   ```yaml
   ---
   apiVersion: v1
   kind: ResourceQuota
   metadata:
     name: object-count-quota
     namespace: <new-namespace>
   spec:
     hard:
       count/pods: "<N>"
       count/persistentvolumeclaims: "<N>"
       count/services: "<N>"
       count/configmaps: "<N>"
       count/secrets: "<N>"
   ```

4. PR + merge. ArgoCD auto-syncs on next reconcile (sync-wave -38).
5. Verify with `kubectl describe quota -n <new-namespace>`.

## Related

- **[Gatekeeper](../applications/gatekeeper.md)** — admission-control for per-pod limits (resource requests/limits, allowed registries, required labels). ResourceQuota caps the aggregate; Gatekeeper enforces per-pod policy. They complement each other.
- **[Network Policies](./network-policies.md)** — namespace isolation at the network layer; ResourceQuota does it at the resource layer.
