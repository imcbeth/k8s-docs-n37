---
title: "Network Policies"
description: "Kubernetes NetworkPolicies for namespace isolation and traffic control"
---

# Network Policies

NetworkPolicies provide namespace isolation and traffic control for the Raspberry Pi 5 Kubernetes homelab cluster, restricting pod-to-pod communication to only what's necessary.

## Overview

- **CNI:** Calico v3.31.3 (native NetworkPolicy support)
- **Service Mesh:** Istio Ambient (mTLS via HBONE tunneling)
- **Deployment:** Managed by ArgoCD at sync-wave `-40`
- **Approach:** Zero-trust (default-deny with explicit allow rules)
- **Namespaces Protected:** 13 (added ingress-nginx, istio-system, gatekeeper-system 2026-02-14)

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        NETWORK SEGMENTATION OVERVIEW                         │
└─────────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────────┐
                              │   EXTERNAL      │
                              │   TRAFFIC       │
                              └────────┬────────┘
                                       │
                              ┌────────▼────────┐
                              │  ingress-nginx  │
                              │  (policy ✅)    │
                              └────────┬────────┘
                                       │
       ┌───────────────────────────────┼───────────────────────────────┐
       │                               │                               │
┌──────▼──────┐               ┌────────▼────────┐              ┌───────▼───────┐
│  localstack │               │  argo-workflows │              │    ArgoCD     │
│   (S3 API)  │               │   (CI/CD UI)    │              │  (planned)    │
└──────┬──────┘               └────────┬────────┘              └───────────────┘
       │                               │
       │ S3                            │ artifacts
       │                               │
┌──────▼──────┐               ┌────────▼────────┐
│   velero    │               │  Backblaze B2   │
│  (backups)  │               │   (external)    │
└─────────────┘               └─────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                           MONITORING FLOW                                    │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────┐     metrics     ┌─────────────┐     metrics     ┌─────────────┐
│  PROMETHEUS │────────────────▶│ ALL SYSTEMS │◀────────────────│  GRAFANA    │
│  (default)  │                 │  (port 80xx)│                 │  (default)  │
└─────────────┘                 └─────────────┘                 └─────────────┘

┌─────────────┐     logs        ┌─────────────┐     alerts      ┌─────────────┐
│  PROMTAIL   │────────────────▶│    LOKI     │────────────────▶│ALERTMANAGER │
│   (loki)    │     :3100       │   (loki)    │     :9093       │  (default)  │
└─────────────┘                 └─────────────┘                 └─────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                        ISTIO AMBIENT MESH (mTLS)                            │
└─────────────────────────────────────────────────────────────────────────────┘

  Meshed Namespaces: default, loki, argo-workflows, localstack, unipoller, trivy-system

  Pod ──────▶ ztunnel ══════════════════════▶ ztunnel ──────▶ Pod
       local   (HBONE tunnel on port 15008)    remote
       proxy    encrypted mTLS traffic         proxy
```

## Protected Namespaces

| Namespace | Purpose | Mesh Status | Key Ports |
|-----------|---------|-------------|-----------|
| ingress-nginx | HTTP/HTTPS ingress controller | No | 80, 443, 10254 |
| istio-system | Service mesh control plane | N/A | 15008, 15010, 15012, 15014, 15017 |
| gatekeeper-system | Admission control | No | 8443, 8888 |
| localstack | S3 emulator for Velero | Ambient | 4566 |
| unipoller | UniFi metrics | Ambient | 9130 |
| loki | Log aggregation | Ambient | 3100, 9095, 7946 |
| trivy-system | Vulnerability scanning | Ambient | 4954, 8080 |
| velero | Backup/restore | No | 8085 |
| argo-workflows | CI/CD pipelines | Ambient | 2746, 9090 |
| cert-manager | TLS certificates | No | 9402, 10250 |
| external-dns | DNS management | No | 7979, 8080, 8888 |
| metallb-system | Load balancer | No | 7472, 7473, 7946 |
| falco | Runtime security | No | 8765, 2801, 5060 |

## Universal Patterns

### DNS Resolution

All namespaces require DNS egress to CoreDNS in kube-system:

```yaml
egress:
  - to:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: kube-system
        podSelector:
          matchLabels:
            k8s-app: kube-dns
    ports:
      - protocol: UDP
        port: 53
      - protocol: TCP
        port: 53
```

:::warning AND vs OR Semantics
`namespaceSelector` and `podSelector` must be in the **same** list item (AND logic). If they are **separate** list items, it becomes OR logic -- allowing all pods in kube-system, not just kube-dns.
:::

### Kubernetes API Access

Applications needing cluster interaction require both ClusterIP and control plane access:

```yaml
egress:
  # Kubernetes API ClusterIP (service proxy)
  - to:
      - ipBlock:
          cidr: 10.96.0.1/32
    ports:
      - protocol: TCP
        port: 443
  # Control plane nodes (direct API server)
  - to:
      - ipBlock:
          cidr: 10.0.10.0/24
    ports:
      - protocol: TCP
        port: 6443
```

**Why both?** With Calico CNI, some K8s API calls route through the ClusterIP (10.96.0.1:443) while others connect directly to the control plane network (10.0.10.0/24:6443). Both must be allowed for reliable API access.

### Prometheus Metrics Scraping

All monitored namespaces allow ingress from the default namespace where Prometheus runs:

```yaml
ingress:
  - from:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: default
    ports:
      - protocol: TCP
        port: <metrics-port>
```

### External HTTPS Access

For namespaces requiring internet access (registries, APIs):

```yaml
egress:
  - to:
      - ipBlock:
          cidr: 0.0.0.0/0
          except:
            - 10.0.0.0/8       # Block private ranges
            - 172.16.0.0/12
            - 192.168.0.0/16
    ports:
      - protocol: TCP
        port: 443
```

## Istio Ambient Mesh Patterns

Istio Ambient uses transparent proxy (TPROXY) which **preserves source IPs**. This has critical implications for NetworkPolicies:

### Key Concepts

1. **HBONE Tunnel (Port 15008):** All mesh traffic is tunneled over mTLS on port 15008
2. **Source IP Preserved:** NetworkPolicies see the original source namespace, not istio-system
3. **Dual Rules Required:** Allow both HBONE (15008) and application ports from source namespaces

### Pattern for Meshed Namespaces

```yaml
ingress:
  # Allow ztunnel to terminate HBONE and originate app connections
  - from:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: istio-system
    ports:
      - protocol: TCP
        port: 15008  # HBONE mTLS tunnel
      - protocol: TCP
        port: <app-port>  # Application port (ztunnel originates connection)

  # Allow from actual source namespace (transparent proxy preserves source IP)
  - from:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: <source-namespace>
    ports:
      - protocol: TCP
        port: 15008
      - protocol: TCP
        port: <app-port>

egress:
  # Allow mesh communication to Istio control plane
  - to:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: istio-system
    ports:
      - protocol: TCP
        port: 15008  # ztunnel HBONE
      - protocol: TCP
        port: 15012  # istiod gRPC
      - protocol: TCP
        port: 15017  # istiod webhook
```

### Example: Meshed Namespace (localstack)

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: localstack-network-policy
  namespace: localstack
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
  ingress:
    # Istio ztunnel (HBONE termination + app port origin)
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: istio-system
      ports:
        - protocol: TCP
          port: 15008
        - protocol: TCP
          port: 4566
    # Velero direct access (transparent proxy preserves source)
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: velero
      ports:
        - protocol: TCP
          port: 4566
    # Argo Workflows via mesh
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: argo-workflows
      ports:
        - protocol: TCP
          port: 15008
        - protocol: TCP
          port: 4566
    # Prometheus from default namespace
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: default
      ports:
        - protocol: TCP
          port: 15008
        - protocol: TCP
          port: 4566
  egress:
    # DNS (AND semantics: kube-system namespace AND kube-dns pods)
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
    # Istio mesh
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: istio-system
      ports:
        - protocol: TCP
          port: 15008
        - protocol: TCP
          port: 15012
        - protocol: TCP
          port: 15017
```

## Namespace Policy Details

### trivy-system

Vulnerability scanner with intra-namespace communication for scan jobs.

**Critical:** Scan jobs must connect to trivy-server (port 4954) within the namespace.

```yaml
ingress:
  # Intra-namespace: scan jobs -> trivy-server
  - from:
      - podSelector: {}
    ports:
      - protocol: TCP
        port: 4954
      - protocol: TCP
        port: 8080
  # Istio mesh + Prometheus
  - from:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: istio-system
    ports:
      - protocol: TCP
        port: 15008
      - protocol: TCP
        port: 8080
  - from:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: default
    ports:
      - protocol: TCP
        port: 15008
        port: 8080

egress:
  # Intra-namespace: scan jobs -> trivy-server
  - to:
      - podSelector: {}
    ports:
      - protocol: TCP
        port: 4954
  # DNS, K8s API, external registries, Istio mesh
  # ... (standard patterns)
```

### cert-manager

TLS certificate management with webhook access from control plane.

```yaml
ingress:
  # Webhook from control plane nodes
  - from:
      - ipBlock:
          cidr: 10.0.10.0/24
    ports:
      - protocol: TCP
        port: 10250
  # Prometheus metrics
  - from:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: default
    ports:
      - protocol: TCP
        port: 9402
  # Intra-namespace communication
  - from:
      - podSelector: {}
    ports:
      - protocol: TCP
        port: 9402

egress:
  # DNS, K8s API
  # External HTTPS (Let's Encrypt, Cloudflare API)
  # Intra-namespace
```

### external-dns

DNS record management with UniFi controller access.

```yaml
ingress:
  # Prometheus (external-dns + unifi-webhook metrics)
  - from:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: default
    ports:
      - protocol: TCP
        port: 7979   # external-dns metrics
      - protocol: TCP
        port: 8080   # unifi-webhook metrics
  # Intra-namespace (unifi-webhook internal)
  - from:
      - podSelector: {}
    ports:
      - protocol: TCP
        port: 8888   # webhook API

egress:
  # DNS, K8s API
  # Cloudflare API (external HTTPS)
  # UniFi controller (specific external IPs)
  - to:
      - ipBlock:
          cidr: 10.0.1.1/32
    ports:
      - protocol: TCP
        port: 443
      - protocol: TCP
        port: 8443
```

### metallb-system

Load balancer with memberlist clustering.

**Note:** Layer 2 ARP/GARP announcements bypass NetworkPolicy (Layer 2 vs Layer 3/4).

```yaml
ingress:
  # Prometheus metrics
  - from:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: default
    ports:
      - protocol: TCP
        port: 7472   # controller metrics
      - protocol: TCP
        port: 7473   # speaker metrics
  # Intra-namespace memberlist
  - from:
      - podSelector: {}
    ports:
      - protocol: TCP
        port: 7946
      - protocol: UDP
        port: 7946
  # Webhook from control plane
  - from:
      - ipBlock:
          cidr: 10.0.10.0/24
    ports:
      - protocol: TCP
        port: 9443

egress:
  # DNS, K8s API
  # Intra-namespace memberlist
```

## ArgoCD Deployment

NetworkPolicies are deployed via ArgoCD using Kustomize at sync-wave `-40` (early in deployment order).

**Application:** `manifests/applications/network-policies.yaml`

**Directory Structure:**

```
manifests/base/network-policies/
├── kustomization.yaml
├── ingress-nginx/
│   └── network-policy.yaml
├── istio-system/
│   └── network-policy.yaml
├── gatekeeper-system/
│   └── network-policy.yaml
├── localstack/
│   └── network-policy.yaml
├── unipoller/
│   └── network-policy.yaml
├── loki/
│   └── network-policy.yaml
├── trivy-system/
│   └── network-policy.yaml
├── velero/
│   └── network-policy.yaml
├── argo-workflows/
│   └── network-policy.yaml
├── cert-manager/
│   └── network-policy.yaml
├── external-dns/
│   └── network-policy.yaml
├── metallb-system/
│   └── network-policy.yaml
└── falco/
    └── network-policy.yaml
```

## Adding New Policies

### Step 1: Create Policy File

```bash
mkdir -p manifests/base/network-policies/<namespace>/
```

### Step 2: Define NetworkPolicy

Use the universal patterns above as a starting point. Key decisions:

1. **Is namespace on Istio mesh?** Add HBONE port 15008 rules
2. **Does it need K8s API?** Add both ClusterIP and control plane egress
3. **Does it need external access?** Add HTTPS egress with private range exclusions
4. **Does it have intra-namespace communication?** Add podSelector: {} rules

### Step 3: Update Kustomization

```yaml
# manifests/base/network-policies/kustomization.yaml
resources:
  # ... existing policies
  - <namespace>/network-policy.yaml
```

### Step 4: Test

```bash
# Dry-run validation
kubectl apply --dry-run=client -f manifests/base/network-policies/<namespace>/

# Apply manually to test
kubectl apply -f manifests/base/network-policies/<namespace>/

# Verify functionality
kubectl exec -n <namespace> <pod> -- wget -qO- --timeout=5 http://<target>
```

### Step 5: Commit

```bash
git add manifests/base/network-policies/
git commit -m "feat: Add NetworkPolicy for <namespace>"
git push
```

## Troubleshooting

### Traffic Unexpectedly Blocked

1. **Check namespace labels:**

   ```bash
   kubectl get namespace <ns> --show-labels
   ```

   Ensure `kubernetes.io/metadata.name` label exists.

2. **For meshed namespaces, verify HBONE rules:**

   ```bash
   kubectl describe networkpolicy -n <ns> | grep 15008
   ```

3. **Check if source namespace is allowed:**

   ```bash
   kubectl get networkpolicy -n <target-ns> -o yaml | grep -A5 namespaceSelector
   ```

### K8s API Timeout

Ensure BOTH API egress rules are present:

- `10.96.0.1/32:443` (ClusterIP)
- `10.0.10.0/24:6443` (control plane)

### Prometheus Scraping Failing

1. Verify ingress allows from `default` namespace
2. Check correct metrics port is allowed
3. For meshed namespaces, ensure port 15008 is also allowed

### Istio Mesh Traffic Blocked

1. Add HBONE port 15008 to both ingress AND egress
2. Allow from `istio-system` namespace for ztunnel
3. Allow from actual source namespace (transparent proxy preserves source IP)

## Rollback

### Delete Single Policy

```bash
kubectl delete networkpolicy -n <namespace> <policy-name>
```

### GitOps Rollback

```bash
git revert HEAD
git push
```

### Emergency: Delete All Policies

```bash
kubectl delete networkpolicy -A --all
```

## Related Documentation

- [Secrets Management](./secrets-management.md) - SealedSecrets for credentials
- [Velero](../applications/velero.md) - Backup solution with NetworkPolicy
- [Loki](../applications/loki.md) - Log aggregation with NetworkPolicy
- [Trivy Operator](../applications/trivy-operator.md) - Security scanning

## References

- [Kubernetes Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [Calico Network Policy](https://docs.tigera.io/calico/latest/network-policy/)
- [Istio Ambient NetworkPolicy](https://istio.io/latest/docs/ambient/usage/networkpolicy/)
- [Network Policy Editor](https://editor.networkpolicy.io/) - Visual policy builder
