---
sidebar_position: 3
title: "Capacity Planning"
description: "Current baselines, headroom, growth forecasting, and decision rubric for when to add nodes or storage"
---

# Capacity Planning

This doc is the answer to "do we have room to deploy &lt;new thing&gt;?" and "when do we need a sixth Pi?" It's deliberately numbers-first, not theory.

The cluster baselines below are point-in-time; query the live metrics for current state.

## Total physical capacity

| Resource | Total | Per node | Notes |
|----------|-------|----------|-------|
| **Nodes** | 5 | — | 1 control-plane + 4 workers |
| **CPU cores** | 20 | 4 | ARM64 Cortex-A76 (Pi 5) |
| **Memory** | 80 GB | 16 GB | Allocatable ~15.5 GB after reservations |
| **NIC** | 5 × 1 Gbit | 1 Gbit | Single port, no LAG |
| **Local storage** | 5 × NVMe | 256 GB SSD | Boot + container images + emptyDir |
| **Network storage** | 1 × Synology DS925+ | — | iSCSI targets on volume2 (SSD) + volume4 (HDD) |
| **Off-site backup** | Backblaze B2 | — | Velero schedules — daily + weekly |

## Current baseline (2026-06-03)

Snapshot of typical steady-state utilization. Refresh with `kubectl top nodes` for current.

| Node | CPU % | Memory % | Mem requests | Mem limits |
|------|-------|----------|--------------|-----------|
| control-plane | 19 | 36 | 7% | 23% |
| node01 | 28 | 36 | 27% | **80%** |
| node02 | 13 | 37 | 24% | 45% |
| node03 | 32 | 43 | 34% | 69% |
| node04 | 18 | 41 | 30% | 65% |

**Key observations:**

- **CPU is well under-utilized** (13-32%) — plenty of headroom for compute work.
- **Memory requests are conservative** (24-34% on workers). The cluster is far from request-saturated.
- **Memory limits are aggressive** (45-80% on workers). This is intentional: VPA's recommender values point to limits below 2× requests for most pods, so the limits matter more than requests in practice. **Node01 at 80% is the watch-this-first node.**
- 38 ArgoCD apps deployed, 149 GiB of PVCs (84 GiB Retain + 65 GiB Delete policy).

## Per-resource detail

### CPU

Cluster never exceeds ~35% CPU at any node. CPU is currently a non-constraint.

**When CPU becomes the constraint:** when sustained `kubectl top nodes` shows any worker above 80% for hours, or when `NodeCPUSaturationPredicted` (proposed alert — not yet deployed) fires. With ARM64 Pi 5 hardware the only vertical option is replacing nodes; the cheap path is **horizontal scale-out + workload distribution** via topology spread constraints.

```promql
# Average CPU utilization per node, 1h window
avg by (instance) (1 - irate(node_cpu_seconds_total{mode="idle"}[5m]))
```

### Memory

The constrained resource — node01 already runs at 80% memory limits, so an aggressive new workload could trigger OOMKills.

**Forecasting growth:** Memory requests and limits are tracked by `kube_pod_container_resource_{requests,limits}`. To project when we'd hit per-node saturation:

```promql
# 14-day predict — when does node01 memory requests hit 14 GiB (87%)?
predict_linear(
  sum by (node) (kube_pod_container_resource_requests{resource="memory", node="node01"})[7d:1h],
  14 * 24 * 3600
)
```

If the result exceeds `14 * 1024 * 1024 * 1024`, the projection is "node01 hits 87% memory requests within 14 days."

**Actions when approaching saturation:**

1. **Right-size with VPA recommendations.** VPA recommender (deployed PR #522) has run long enough on most workloads to have credible numbers:

   ```bash
   kubectl get vpa -A
   kubectl describe vpa <name> -n <ns> | grep -A 10 Recommendation
   ```

2. **Drain + rebalance** if one node is hot but others have headroom. Topology spread constraints help most workloads.
3. **Add a 6th node** if cluster-wide memory requests cross 65 GB / 80 GB total (~80%). See "When to add hardware" below.

### Storage (Synology NAS)

| Volume | Size | Used (PVCs) | Headroom |
|--------|------|-------------|----------|
| volume2 (SSD) | TBD | ~84 GiB Retain class | NAS dashboard for live total |
| volume4 (HDD) | TBD | ~65 GiB Delete class | NAS dashboard |

Get current NAS utilization from `synology_*` Prometheus metrics or directly from DSM.

**Forecasting NAS volume growth:**

Storage capacity alerts already use `predict_linear` (deployed in `storage-alerts.yaml`):

- `NodeFilesystemSpacePredicted` — node local disk projected to fill within 24h.
- `PersistentVolumeSpacePredicted` — same for any K8s PVC.
- `SynologyVolumeSpaceLow` / `Critical` — NAS volume thresholds at 80% / 90%.

Day-to-day capacity sanity check:

```bash
# Current PVC requests by storage class
kubectl get pvc -A -o json | jq -r '
  .items[]
  | "\(.spec.storageClassName // "-") \(.spec.resources.requests.storage)"
' | sort | uniq -c | sort -rn

# Total committed bytes per class
kubectl get pvc -A -o json | python3 -c "
import json, sys, re
data = json.load(sys.stdin); by_sc = {}
for pvc in data['items']:
    req = pvc.get('spec',{}).get('resources',{}).get('requests',{}).get('storage','0')
    sc = pvc.get('spec',{}).get('storageClassName','?')
    m = re.match(r'(\d+)([GMK]i?)', str(req))
    if m:
        n = int(m.group(1)); gi = n if 'G' in m.group(2) else (n/1024 if 'M' in m.group(2) else 0)
        by_sc[sc] = by_sc.get(sc, 0) + gi
for sc, gi in sorted(by_sc.items(), key=lambda x: -x[1]):
    print(f'{sc}: {gi:.1f} GiB')
"
```

**Actions when approaching saturation:**

1. **Expand the NAS volume** — DSM supports online expansion if free pool space exists.
2. **Move retention** — Prometheus 30d, Loki 720h, Tempo 720h are tunable; halve them and reclaim quickly.
3. **Move PVCs between SSD and HDD class** by recreating the PVC with `storageClassName: synology-iscsi-delete` (HDD) for non-latency-sensitive workloads (Velero artifacts, Argo Workflows workspace, log archives).

### Network

Per-NIC saturation is monitored by `network-alerts.yaml` (deployed PR #710):

- `NodeNetworkReceive/TransmitSaturation` at >85% gigabit for 15m
- `NodeNetworkReceive/TransmitErrors` and `Drops`
- `NodeConntrackTableNearFull/Full`

The cluster's never come close to gigabit saturation under normal operation. The most likely cause of a sustained saturation alert is a Velero backup window or a Kaniko build pushing a large image — both are intentional, not concerning.

## When to add hardware

The cluster is over-provisioned for current load. These are the concrete thresholds at which adding a 6th worker becomes the right move, not just a "nice to have":

| Threshold | Signal |
|-----------|--------|
| Cluster-wide memory **requests** > 65 GB / 80 GB total (81%) | Sustained for 7 days. Scheduling pressure is imminent. |
| Any worker memory **limits** > 90% | Sustained for 7 days. OOMKill risk on bursty workloads. |
| `kube_pod_status_unschedulable` > 0 | New pods can't fit. Usually because of memory requests across topology spread constraints. |
| NAS volume > 80% capacity | Synology alert thresholds. NAS expansion is usually cheaper than another Pi. |
| New workload needs > 1 GiB request and there's no node with headroom | Decision-time: add hardware or shrink something. |

**6th node addition** would be straightforward — kubeadm join, label, let workloads rebalance. Plan ~2h of work and a maintenance window. Storage and network capacity don't scale per node addition (Synology is centralized), so adding workers is purely a CPU/memory bump.

## Growth projection methodology

For any resource we monitor in Prometheus, the standard recipe is:

```promql
predict_linear(<metric>[7d:1h], <seconds_into_future>)
```

This fits a least-squares line to the last 7 days and projects forward. It's accurate for **monotonic, steady-trend** signals (storage usage, accumulating object counts) and misleading for **bursty or seasonal** signals (CPU under load, daily backup windows).

Existing predict_linear alerts:

- `NodeFilesystemSpacePredicted` — 24h projection
- `PersistentVolumeSpacePredicted` — 24h projection

Useful one-off queries for planning:

```promql
# When does total cluster memory requests cross 65 GiB (81%)?
predict_linear(
  sum(kube_pod_container_resource_requests{resource="memory"})[14d:1h],
  30 * 24 * 3600
) > 65 * 1024 * 1024 * 1024

# When does volume2 (SSD) hit 80%?
predict_linear(
  synology_volume_usage_percent{volume="volume2"}[30d:1h],
  30 * 24 * 3600
) > 80

# When do total PVC count hit 30? (informal; PVCs grow with new workloads)
predict_linear(
  count(kube_persistentvolumeclaim_info)[30d:1d],
  90 * 24 * 3600
) > 30
```

The 30-day lookback is more stable than 7-day for storage planning; 7-day is fine for CPU/memory which fluctuates faster.

## Reviewing the plan

Quarterly:

1. Refresh the baseline table at the top of this doc against `kubectl top nodes`.
2. Run the predict_linear queries; if any project saturation within 30 days, add it to TODO.md.
3. Check VPA recommendations against current requests — significant drift means right-sizing is overdue.
4. Verify NAS volume utilization against capacity; expand if necessary.

Yearly:

- Review whether ARM64 Pi 5 is still the right substrate — newer Pi models, x86 mini-PCs, etc. The constraint at 16 GB per node will eventually limit growth.
- Review whether the 1× Synology DS925+ is still the right storage — adding a second NAS for replication is significantly more impactful for resilience than another Pi.

## Related

- **[Runbooks](./runbooks.md)** — fast fixes when something exceeds capacity unexpectedly
- **[Disaster Recovery](./disaster-recovery.md)** — what to do when a capacity issue causes an outage
- **[Resource Quotas](../security/resource-quotas.md)** — per-namespace caps that prevent runaway consumption
- **[Synology CSI](../storage/synology-csi.md)** — iSCSI configuration, volume layout
- **[Hardware](../getting-started/hardware.md)** — physical hardware spec
