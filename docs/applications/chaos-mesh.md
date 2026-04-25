---
title: "Chaos Mesh"
description: "CNCF chaos engineering platform for controlled failure injection on ARM64"
---

# Chaos Mesh

Chaos Mesh is a CNCF incubating chaos engineering platform that enables controlled failure injection to test cluster resilience. It was selected over Litmus due to its official ARM64 multi-arch support.

## Overview

| Property | Value |
|----------|-------|
| **Namespace** | `chaos-mesh` |
| **Chart** | `chaos-mesh/chaos-mesh` v2.8.2 |
| **ArgoCD App** | `chaos-mesh` (project: `infrastructure`, wave: `0`) |
| **Architecture** | ARM64 (`ghcr.io/chaos-mesh/*` images) |
| **Dashboard** | Port-forward only (no external ingress) |

## Purpose

Chaos Mesh provides controlled failure injection for:

- **Pod kill** — Randomly terminate pods to verify restart behaviour
- **Network chaos** — Inject latency, packet loss, or partition namespaces
- **Time chaos** — Skew system clock for time-sensitive workloads
- **Stress testing** — CPU and memory stress on specific pods

## Why Chaos Mesh (not Litmus)

Litmus has no official ARM64 container images and cannot run on the Raspberry Pi 5 cluster. Chaos Mesh provides official multi-arch images via `ghcr.io/chaos-mesh/*` with `linux/arm64` support.

## Architecture

```
chaos-controller-manager (Deployment)
   │
   ├── Webhook server (port 10250) — mutates Chaos CR objects
   ├── Controller loops — reconciles Schedule, Workflow, Experiment CRs
   └── chaos-daemon (DaemonSet) — executes chaos actions on each node
            │
            └── Uses Linux kernel features (eBPF, cgroups, tc, nsenter)
                 to inject failures at the OS level
```

## Deployment Notes

### Webhook Port

The chaos-controller-manager mutation webhook listens on container port **10250** (not 443). The Service exposes 443 and forwards to 10250 internally.

:::warning Bare port rule required for NetworkPolicy
The API server (hostNetwork on control-plane) reaches the webhook across nodes via IPIP-encapsulated traffic. Calico IPIP rewrites the source IP so `ipBlock` rules matching the control-plane CIDR fail for cross-node traffic. Use a bare port rule (no `from` selector) for port 10250 in any NetworkPolicy.
:::

### Mutation Webhook Behaviours

The Chaos Mesh mutation webhook modifies Chaos CR objects at admission time. Two behaviours affect git manifests:

**`startingDeadlineSeconds: null`** — Added to all Schedule objects. Include this in git YAML or ArgoCD will detect perpetual drift.

**`gracePeriod: 0` is stripped** — For pod-kill Schedules, `gracePeriod: 0` is equivalent to the Kubernetes default and is removed by the webhook. Remove it from git manifests.

### Certificate Secrets

Four Secrets (`chaos-mesh-*-certs`) are auto-populated by the controller with TLS certificates. Add `ignoreDifferences` for `/data` on each to prevent ArgoCD drift:

```yaml
ignoreDifferences:
  - group: ""
    kind: Secret
    name: chaos-mesh-controller-manager-certs
    jsonPointers:
      - /data
  # ... repeat for each chaos-mesh-*-certs secret
```

### Helm `rollme` Annotation

The chart uses `randAlphaNum 5` for a `rollme` pod annotation, generating a new value on every render and causing rolling restarts on every ArgoCD sync. Pin it to a fixed string:

```yaml
controllerManager:
  podAnnotations:
    rollme: "pinned"

chaosDaemon:
  podAnnotations:
    rollme: "pinned"
```

## Gatekeeper Exclusions

The chaos-daemon DaemonSet and helper pods do not carry standard labels. Add `chaos-mesh` to excluded namespaces for these constraints:

- `require-labels`
- `container-limits`
- `require-resource-limits`

## Running Experiments

### Pod Kill Schedule

```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: Schedule
metadata:
  name: random-pod-kill
  namespace: chaos-mesh
spec:
  schedule: "0 */6 * * *"  # every 6 hours
  type: PodChaos
  podChaos:
    action: pod-kill
    mode: one
    selector:
      namespaces:
        - default
      labelSelectors:
        app: my-app
  # Note: startingDeadlineSeconds: null added by webhook — include in git
  startingDeadlineSeconds: null
```

### Network Latency

```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: network-delay
  namespace: chaos-mesh
spec:
  action: delay
  mode: one
  selector:
    namespaces:
      - default
  delay:
    latency: "100ms"
    jitter: "10ms"
  duration: "5m"
```

### Accessing the Dashboard

The Chaos Mesh dashboard has no external ingress. Use port-forward:

```bash
kubectl port-forward svc/chaos-dashboard -n chaos-mesh 2333:2333
# Open http://localhost:2333
```

## Resource Usage

| Component | CPU Request | CPU Limit | Memory Request | Memory Limit |
|-----------|-------------|-----------|----------------|--------------|
| controller-manager | 25m | 500m | 256Mi | 1Gi |
| chaos-daemon (per node) | 25m | 500m | 256Mi | 1Gi |
| chaos-dashboard | 25m | 200m | 64Mi | 256Mi |

## Troubleshooting

### Experiment stuck in "Running"

Check controller-manager logs for reconciliation errors:

```bash
kubectl logs -n chaos-mesh deployment/chaos-controller-manager --tail=50
```

### Webhook rejected (cert not ready)

The four cert Secrets are populated on first startup. If a webhook call arrives before certs are ready, it will be rejected. Wait for the controller to fully initialize:

```bash
kubectl get secret -n chaos-mesh | grep certs
kubectl wait pod -n chaos-mesh -l app.kubernetes.io/component=controller-manager --for=condition=Ready
```

### NetworkChaos not applying

chaos-daemon must be running on the target node. Verify:

```bash
kubectl get pods -n chaos-mesh -l app.kubernetes.io/component=chaos-daemon -o wide
```

## References

- [Chaos Mesh Documentation](https://chaos-mesh.org/docs/)
- [Chaos Mesh GitHub](https://github.com/chaos-mesh/chaos-mesh)
- [CNCF Project Page](https://www.cncf.io/projects/chaosmesh/)

---

**Last Updated:** 2026-04-25
