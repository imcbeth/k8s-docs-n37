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
| **Chart** | `chaos-mesh/chaos-mesh` v2.8.3 (as of 2026-06-21, via Renovate PR #749) |
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

### Safe Schedule configuration (lessons from a real incident)

Before writing new Schedules, know the four things that will bite you. All four came from actual production incidents documented in the homelab's `.claude/notes/`.

**1. `startingDeadlineSeconds: null` means "catch up ALL missed slots on recovery."** If the chaos-mesh controller is down for a day and comes back up, chaos-mesh will fire every missed cron slot immediately. On 2026-07-12 this cascade-killed Prometheus mid-debugging. Always set an explicit small window:

```yaml
spec:
  startingDeadlineSeconds: 60   # drop missed slots older than 60s
```

**2. `mode: all` on a `nodeSelectors:` scope is self-destructive.** If chaos-mesh's own reconciler pods land on the target node, they get pause-swapped and can't restore the swap → deadlock. The 2026-07-01 `pod-failure-node04 mode: all nodeSelectors: {kubernetes.io/hostname: node04}` incident caused an 11-day chaos-mesh self-lockup (3130 restarts per pod).

Safe pattern: use a positive `namespaces:` allowlist. `expressionSelectors NotIn [chaos-mesh]` looks correct but **silently returns "no pod is selected"** in this cluster (verified 2026-07-13):

```yaml
selector:
  nodeSelectors:
    kubernetes.io/hostname: node04
  namespaces:               # allowlist of user-workload namespaces
    - falco
    - loki
    - unipoller
    - lifeonabike
    - argo-workflows
    - argo-events
mode: all
```

**3. Verify the labelSelector actually matches something.** `cpu-stress-unipoller` had `labelSelectors.app.kubernetes.io/name: unipoller` — but the real pod label is `unifi-poller` (with hyphen). `Selected=False, records=0` on every fire since inception; the StressChaos was a silent no-op for months. `kubectl get pod -l <selector>` before you commit.

**4. NetworkChaos needs chaos-daemon gRPC (port 31767, not 31766).** See [Troubleshooting → `unable to flush ip sets`](#unable-to-flush-ip-sets--chaos-daemon-has-two-ports) below.

### Pod Kill Schedule (example)

```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: Schedule
metadata:
  name: pod-kill-example
  namespace: chaos-mesh
spec:
  schedule: "0 */6 * * *"  # every 6 hours
  type: PodChaos
  concurrencyPolicy: Forbid
  historyLimit: 5
  startingDeadlineSeconds: 60   # drop backlog on recovery
  podChaos:
    action: pod-kill
    mode: one
    selector:
      namespaces:
        - default
      labelSelectors:
        app.kubernetes.io/name: my-app
```

:::note pod-kill has no recovery phase
`AllRecovered=False` is expected on any pod-kill experiment — there's nothing to un-kill; the workload controller recreates the pod fresh. Monitoring/verification logic must check `AllInjected=True` (not AllRecovered) for pod-kill success. See `scripts/verify-chaos-week.sh` in the homelab repo for the pattern.
:::

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

Use the homelab's `scripts/verify-chaos-week.sh` for a per-schedule verdict (✅/⚠️/❌/⏭️) plus global cluster health signals.

### `unable to flush ip sets` — chaos-daemon has TWO ports

The `chaos-daemon` DaemonSet listens on **two** TCP ports:

| Port | Purpose |
|---|---|
| **31766** | HTTP metrics endpoint (Prometheus scrape) |
| **31767** | gRPC endpoint — **what controller-manager calls for injection** |

NetworkPolicy scoping chaos-mesh must allow BOTH ports on the intra-namespace ingress + egress rules. Allowing only 31766 lets HTTP metrics scrape succeed but silently breaks NetworkChaos and mode≠kill PodChaos with `unable to flush ip sets for pod <name>` errors. Discovered 2026-07-15 after Wednesday's chaos audit; the off-by-one had been in place since day one.

```yaml
# NetworkPolicy — intra-namespace allow
- from:
    - podSelector: {}
  ports:
    - protocol: TCP
      port: 31766   # HTTP metrics
    - protocol: TCP
      port: 31767   # gRPC injection (REQUIRED)
```

### mTLS certificate errors after chart upgrade

If controller-manager logs show:

```
tls: failed to verify certificate: x509: certificate signed by unknown authority "chaos-mesh-ca"
```

The chaos-daemon pods have stale certs from before a chart upgrade regenerated the CA. Chart lifecycle rotates the CA in Secrets (`chaos-mesh-daemon-certs`, `chaos-mesh-daemon-client-certs`, `chaos-mesh-webhook-certs`, `chaos-mesh-chaosd-client-certs`) but does NOT restart chaos-daemon pods to pick them up.

```bash
kubectl rollout restart daemonset -n chaos-mesh chaos-daemon
```

### Experiment shows `Selected: False, records: 0`

The selector matched no pods. Common causes:

- Label typo — verify with `kubectl get pod -n <ns> -l <selector>` before scheduling
- `expressionSelectors NotIn` combined with `nodeSelectors` returns "no pod is selected" (silent chaos-mesh implementation quirk). Use positive `namespaces:` allowlist instead.

### `Schedule.status.lastScheduleTime` is empty (but experiments fired)

Known issue in chaos-mesh 2.8.3 on this cluster — the Schedule controller never populates this status field, even when it's actively firing experiments. Tools that key off it (like an older `verify-chaos-week.sh`) will show "never fired." Use child experiment `creationTimestamp` (via ownerReferences or name prefix) instead.

### Webhook rejected (cert not ready)

The four cert Secrets are populated on first startup. If a webhook call arrives before certs are ready, it will be rejected. Wait for the controller to fully initialize:

```bash
kubectl get secret -n chaos-mesh | grep certs
kubectl wait pod -n chaos-mesh -l app.kubernetes.io/component=controller-manager --for=condition=Ready
```

### chaos-mesh pods running `pause:latest` (self-lockup)

If `kubectl get pod -n chaos-mesh -o wide` shows pods with image `gcr.io/google-containers/pause:latest` — chaos-mesh has pause-swapped its own components (usually via a PodChaos with `mode: all` on a node scope). Recovery:

```bash
# 1. Force-delete the affected pods; Deployment/DaemonSet controllers recreate with correct image
kubectl delete pod -n chaos-mesh <affected-pods> --grace-period=0 --force

# 2. Clean up the stuck parent experiment
kubectl delete <kind>.chaos-mesh.org -n chaos-mesh <name> --grace-period=30 --wait=false
kubectl patch <kind>.chaos-mesh.org -n chaos-mesh <name> --type=merge -p '{"metadata":{"finalizers":null}}'

# 3. Fix the Schedule (add safe namespaces allowlist per "Safe Schedule Configuration" above)
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
