# Istio Ambient Service Mesh

## Overview

Istio Ambient mode provides a sidecarless service mesh architecture for the homelab cluster. It handles mTLS encryption, L4 authorization, and telemetry without injecting sidecar proxies into application pods.

**Evaluation Date:** 2026-01-25

## Architecture

### Components

| Component | Type | Purpose | Resource Usage |
|-----------|------|---------|----------------|
| istiod | Deployment | Control plane, certificate management | ~6m CPU, ~35Mi |
| istio-cni-node | DaemonSet | CNI plugin for traffic redirection | ~1m CPU, ~12-15Mi per node |
| ztunnel | DaemonSet | L4 proxy, mTLS termination | ~1-2m CPU, ~1-2Mi per node |

### Why Ambient Mode?

Compared to traditional sidecar mode:

- **90% less overhead**: No per-pod sidecar proxies
- **Scales with nodes, not pods**: DaemonSets instead of sidecars
- **Simpler operations**: No sidecar injection/restart cycles

### Comparison with Linkerd

| Metric | Linkerd | Istio Ambient | Winner |
|--------|---------|---------------|--------|
| Control plane memory | 66-73Mi | ~110Mi | Linkerd |
| Per-pod overhead | ~10-15Mi (sidecar) | 0 | Istio Ambient |
| Scales with | Pods | Nodes | Istio Ambient |
| Crossover point | - | ~5-6 pods | - |

**Decision:** Istio Ambient chosen for better scalability with many pods.

## Installation

### ArgoCD Applications

Istio is managed via ArgoCD with the following sync wave order:

| Application | Sync Wave | Chart |
|-------------|-----------|-------|
| istio-base | -45 | CRDs and base resources |
| istiod | -44 | Control plane |
| istio-cni | -43 | CNI plugin |
| istio-ztunnel | -42 | Data plane proxy |

### Files

```
manifests/
├── applications/
│   ├── istio-base.yaml
│   ├── istiod.yaml
│   └── istio-cni.yaml      # includes ztunnel
└── base/
    ├── istio/
    │   ├── istiod-values.yaml
    │   ├── ztunnel-values.yaml
    │   └── cni-values.yaml
    └── network-policies/
        └── istio-system/
            └── network-policy.yaml
```

## Adding Namespaces to the Mesh

To add a namespace to the ambient mesh:

```bash
kubectl label namespace <namespace> istio.io/dataplane-mode=ambient
```

### Currently Meshed Namespaces

- `localstack` - Test namespace for mesh evaluation

### NetworkPolicy Requirements

Namespaces with restrictive NetworkPolicies need egress rules for Istio. Example for a meshed namespace:

```yaml
egress:
  # Allow ztunnel communication
  - to:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: istio-system
    ports:
      - protocol: TCP
        port: 15008  # HBONE
      - protocol: TCP
        port: 15012  # istiod gRPC
      - protocol: TCP
        port: 15017  # istiod webhook
```

## Verification

### Check mesh status

```bash
# Verify ztunnel sees workloads
istioctl ztunnel-config workloads

# Check for HBONE protocol (indicates mTLS active)
istioctl ztunnel-config workloads | grep localstack
# Should show: HBONE (not TCP)
```

### Check ArgoCD status

```bash
kubectl get applications -n argocd | grep istio
```

### Resource usage

```bash
kubectl top pods -n istio-system
```

## Troubleshooting

### Pod not joining mesh

1. Verify namespace label:

   ```bash
   kubectl get namespace <ns> -o jsonpath='{.metadata.labels}'
   ```

2. Check ztunnel logs:

   ```bash
   kubectl logs -n istio-system -l app=ztunnel --tail=50
   ```

3. Verify NetworkPolicy allows egress to istio-system

### ArgoCD shows OutOfSync

The istio-base, istiod, and istio-cni apps may show "OutOfSync" due to metadata differences from the initial CLI installation. This is cosmetic if Health is "Healthy".

To force full sync (causes brief disruption):

```bash
# Delete and let ArgoCD recreate
kubectl delete application istio-base istiod istio-cni istio-ztunnel -n argocd
kubectl apply -f manifests/applications/istio-base.yaml
kubectl apply -f manifests/applications/istiod.yaml
kubectl apply -f manifests/applications/istio-cni.yaml
```

## Removal

To remove a namespace from the mesh:

```bash
kubectl label namespace <namespace> istio.io/dataplane-mode-
kubectl rollout restart deployment -n <namespace>
```

To completely remove Istio:

```bash
kubectl delete application istio-ztunnel istio-cni istiod istio-base -n argocd
kubectl delete namespace istio-system
```

## References

- [Istio Ambient Mode Documentation](https://istio.io/latest/docs/ambient/)
- [Istio Helm Charts](https://istio-release.storage.googleapis.com/charts)
- [Ambient Mode Getting Started](https://istio.io/latest/docs/ambient/getting-started/)
