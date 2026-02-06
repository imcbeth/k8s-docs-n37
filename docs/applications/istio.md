# Istio Ambient Service Mesh

## Overview

Istio Ambient mode provides a sidecarless service mesh architecture for the homelab cluster. It handles mTLS encryption, L4 authorization, and telemetry without injecting sidecar proxies into application pods.

**Version:** 1.28.3 (Helm charts)
**Last Updated:** 2026-02-05

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

- `default` - Prometheus, Grafana, AlertManager
- `loki` - Loki, Promtail, loki-canary
- `localstack` - LocalStack S3 emulator
- `argo-workflows` - Argo Workflows server and controller
- `unipoller` - UniFi metrics exporter
- `trivy-system` - Trivy vulnerability scanner

### NetworkPolicy Requirements

**IMPORTANT**: Istio ambient uses transparent proxy - source IPs are preserved. NetworkPolicies must allow HBONE port 15008 from all communicating namespaces, not just istio-system.

#### Egress Rules (required for meshed pods to communicate out)

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

#### Ingress Rules (required for meshed pods to receive traffic)

```yaml
ingress:
  # Allow HBONE from istio-system (ztunnel terminates tunnel)
  - from:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: istio-system
    ports:
      - protocol: TCP
        port: 15008  # HBONE mTLS
      - protocol: TCP
        port: <app-port>  # Application port (ztunnel originates connection)

  # Allow HBONE from source namespace (transparent proxy preserves source IP)
  - from:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: <source-namespace>
    ports:
      - protocol: TCP
        port: 15008  # HBONE mTLS (transparent proxy)
      - protocol: TCP
        port: <app-port>  # Application port
```

#### Intra-namespace Communication

For pods within the same meshed namespace to communicate:

```yaml
ingress:
  - from:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: <same-namespace>
    ports:
      - protocol: TCP
        port: 15008  # HBONE mTLS (transparent proxy)
      - protocol: TCP
        port: <app-port>
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

**Current measurements (6 namespaces, 29 pods in mesh):**

| Component | Instances | CPU | Memory |
|-----------|-----------|-----|--------|
| istiod | 1 | ~3m | ~39Mi |
| istio-cni-node | 5 | ~5m | ~68Mi |
| ztunnel | 5 | ~30m | ~38Mi |
| **Total** | - | **~38m** | **~145Mi** |

Note: ztunnel CPU varies with traffic volume.

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

### HBONE connection timeout

If ztunnel logs show errors like:

```
error="connection timed out, maybe a NetworkPolicy is blocking HBONE port 15008"
```

This indicates NetworkPolicy is blocking HBONE traffic. Check:

1. **Ingress on destination**: Must allow port 15008 from source namespace
2. **Egress on source**: Must allow port 15008 to destination namespace
3. **Transparent proxy**: Source IP is preserved, so allow from the actual source namespace (not just istio-system)

Example fix:

```yaml
# On destination namespace NetworkPolicy
ingress:
  - from:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: <source-namespace>
    ports:
      - protocol: TCP
        port: 15008  # HBONE
      - protocol: TCP
        port: <app-port>
```

### ArgoCD shows OutOfSync

:::info Resolved (2026-02-05)
All Istio ArgoCD applications are now fully Synced and Healthy after comprehensive `ignoreDifferences` were added in PRs #379, #380, and #381.
:::

OutOfSync can occur due to:

1. **Webhook caBundle drift**: Kubernetes auto-populates `caBundle` fields in webhook configurations
2. **Helm operator labels**: The Helm chart adds `app.kubernetes.io/managed-by: Helm` and `meta.helm.sh/release-*` labels at runtime
3. **ServerSideApply K8s defaults**: With `ServerSideApply=true`, Kubernetes populates default values (imagePullPolicy, revisionHistoryLimit, readinessProbe defaults, dnsPolicy, restartPolicy, schedulerName, etc.) not present in Helm templates

**Solution - Use ignoreDifferences with jqPathExpressions:**

Configure `ignoreDifferences` in ArgoCD Application specs. For DaemonSets with ServerSideApply, you must enumerate ALL Kubernetes-defaulted fields:

```yaml
spec:
  ignoreDifferences:
    # Webhook caBundle
    - group: admissionregistration.k8s.io
      kind: ValidatingWebhookConfiguration
      jqPathExpressions:
        - .webhooks[]?.clientConfig.caBundle
    # Helm operator labels
    - group: "*"
      kind: "*"
      jqPathExpressions:
        - .metadata.labels["app.kubernetes.io/managed-by"]
        - .metadata.labels["meta.helm.sh/release-name"]
        - .metadata.labels["meta.helm.sh/release-namespace"]
    # K8s-defaulted fields (required for ServerSideApply)
    - group: apps
      kind: DaemonSet
      jqPathExpressions:
        - .metadata.labels
        - .metadata.annotations
        - .spec.revisionHistoryLimit
        - .spec.template.spec.containers[].imagePullPolicy
        - .spec.template.spec.containers[].terminationMessagePath
        - .spec.template.spec.containers[].terminationMessagePolicy
        - .spec.template.spec.dnsPolicy
        - .spec.template.spec.restartPolicy
        - .spec.template.spec.schedulerName
        - .spec.template.spec.securityContext
        # ... plus env fieldRef, readinessProbe defaults, volume defaults
  syncPolicy:
    syncOptions:
      - ServerSideApply=true
      - RespectIgnoreDifferences=true
```

:::warning Application Manifest Updates
After merging `ignoreDifferences` changes, you must `kubectl apply -f manifests/applications/<app>.yaml` to update the Application spec in-cluster. ArgoCD self-management does NOT auto-deploy Application manifest changes.
:::

**To force full sync (causes brief disruption):**

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
