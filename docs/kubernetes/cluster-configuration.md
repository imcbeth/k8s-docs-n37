---
title: "Cluster Configuration"
description: "Current cluster component versions, upgrade history, and post-installation configuration"
---

# Cluster Configuration

## Current version state (as of 2026-07-30)

| Component | Version | Notes |
|---|---|---|
| **Kubernetes** | **v1.36.3** | Upgraded 2026-07-30 from v1.35.0 via kubeadm |
| kubelet (all 5 nodes) | v1.36.3-1.1 | apt-managed, hold-pinned |
| kube-apiserver / -scheduler / -controller-manager | v1.36.3 | Static pods on control-plane |
| kube-proxy | v1.36.3 | DaemonSet |
| CoreDNS | v1.14.2 | Bumped by kubeadm during 1.36 upgrade (was v1.13.1) |
| etcd | 3.6.8-0 | Bumped by kubeadm during 1.36 upgrade (was 3.6.6-0) |
| containerd | 2.2.1 | Unchanged through k8s minor bumps |
| CNI: Calico (via Tigera Operator) | v3.31.4 | Independent of k8s upgrades |
| Ambient mesh: Istio | 1.30.3 | Independent |
| OS (all nodes) | Ubuntu 24.04.3 LTS | ARM64 |
| Kernel (all nodes) | 6.8.0-1057-raspi | 6.8.0-1060 available; not yet applied |

See [Hardware](../getting-started/hardware.md) for the per-node breakdown.

## Kubernetes upgrade procedure

Full runbook lives in the homelab repo at `runbooks/k8s-1.36-upgrade.md` (parameterized for the 1.35 → 1.36 bump; re-use the same shape for future minor bumps).

**Summary of the kubeadm upgrade path:**

1. **Pre-flight audit** against the target-version urgent-upgrade-notes. Grep the cluster for any deprecated APIs / values / metrics that the release notes call out.
2. **Take a Velero backup within 24h** of starting.
3. **Switch apt repo** from `v1.<old>/deb` to `v1.<new>/deb` on the control-plane node.
4. **Install target kubeadm** (`apt-mark unhold kubeadm && apt-get install kubeadm=<version>`).
5. **`kubeadm upgrade plan`** — dry-run report; verify the proposed CoreDNS/etcd bumps look sane.
6. **`kubeadm upgrade apply v<version>`** on control-plane. Static pods (apiserver, scheduler, controller-manager, etcd) roll automatically.
7. **Drain control-plane**, upgrade `kubelet` + `kubectl`, restart kubelet, uncordon.
8. **Per worker (rolling one at a time):**
   - Drain
   - Switch apt repo + install kubeadm
   - `kubeadm upgrade node`
   - Install kubelet + kubectl, restart kubelet
   - Uncordon
   - Observe ~5-10 min before moving to the next
9. **Post-upgrade validation:** all nodes on the new version, ArgoCD 100% Synced+Healthy, no PVC RO cascades, alerts inactive.

**Rollback:** feasible via apt re-pin to the previous version IF caught before etcd data-schema evolves significantly. Full etcd restore from Velero is the fallback.

## Upgrade history

| Date | From | To | Notes |
|---|---|---|---|
| 2026-07-30 | v1.35.0 | v1.36.3 | ~35 min total. Zero incidents, zero rollbacks. Pre-flight showed 0 incompatibilities. |
| _(earlier)_ | prior versions | v1.35.0 | See git history of `runbooks/` in the homelab repo |

## Cluster-specific quirks to know

### PVC RO cascade risk during drain

Each worker drain detaches all its RWO iSCSI PVCs. iSCSI reattach on the target node has historically been the flaky path (2026-06-04 + 2026-06-21 incidents). The `pvc-ro-remediator` DaemonSet (see [PVC RO Mount Auto-Remediation](../storage/pvc-ro-automation.md)) will auto-heal within ~4 min if a RO mount happens. If the same PVC RO's twice, cordon the node and manually reschedule.

**2026-07-30 upgrade result:** zero RO cascades — the biggest anticipated risk didn't fire.

### Chaos-mesh Wednesday fires

`pod-kill-prometheus`, `network-delay-loki`, `cpu-stress-unipoller` all fire Wed 09:00-11:00 UTC. **Do NOT run kubeadm upgrades on Wednesday.** Chaos-mesh Schedule CRD (v2.8.x) has no `spec.suspend` field, so to disable Schedules you have to comment them out of the kustomization or edit the cron. For short (&lt;24h) upgrade windows on other days, the day-of-week gap is usually sufficient.

### Gatekeeper PDB drain wait

Gatekeeper controller-manager has 2 replicas with `PodDisruptionBudget: minAvailable: 1`. If both replicas end up on the same node (e.g. after selfHeal / rescheduling), a drain of that node will block on eviction until the PDB timeout (5 min by default in `kubectl drain`). Proceed with `--force --grace-period=60 --timeout=5m` — the pods will still terminate, just after the wait. Consider adding pod anti-affinity to the gatekeeper Deployment to prevent replicas from co-locating.

### Kernel updates surface during kubelet install

`apt-get install kubelet` prints "Newer kernel available (X vs Y). Restarting the system to load the new kernel will not be handled automatically." This is a `needrestart` heuristic — the kernel update is NOT applied by the k8s upgrade; it's a separate coordinated reboot task. As of 2026-07-30, `6.8.0-1060-raspi` is pending on all nodes (running `6.8.0-1057-raspi`).

## Static-pod manifest locations

kubeadm-managed static pods on the control plane:

```
/etc/kubernetes/manifests/
├── etcd.yaml
├── kube-apiserver.yaml
├── kube-controller-manager.yaml
└── kube-scheduler.yaml
```

Modifying these directly is possible but strongly discouraged — `kubeadm upgrade apply` will overwrite them. Configuration lives in the `kubeadm-config` and `kubelet-config` ConfigMaps in `kube-system`.

## kubeadm ConfigMap

```bash
kubectl -n kube-system get cm kubeadm-config -o yaml
kubectl -n kube-system get cm kubelet-config -o yaml
```

These are the source of truth for the next `kubeadm upgrade apply`. Certificate validity, DNS domain, pod CIDR, and other cluster-wide settings live here.

## Related pages

- [Kubernetes Installation](./installation.md) — initial kubeadm bootstrap
- [Cluster Maintenance](./cluster-maintenance.md) — shutdown/startup + NAS iSCSI safety
- [Hardware](../getting-started/hardware.md) — per-node breakdown
- [PVC RO Mount Auto-Remediation](../storage/pvc-ro-automation.md) — biggest upgrade-time risk
