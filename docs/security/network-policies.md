---
title: "Network Policies"
description: "Kubernetes NetworkPolicies for namespace isolation and traffic control"
---

# Network Policies

NetworkPolicies provide namespace isolation and traffic control for the Raspberry Pi 5 Kubernetes homelab cluster, restricting pod-to-pod communication to only what's necessary.

## Overview

- **CNI:** Calico v3.31.3 (native NetworkPolicy support)
- **Deployment:** Managed by ArgoCD at sync-wave `-40`
- **Approach:** Allow-list (default-deny ingress with explicit allow rules)
- **Namespaces Protected:** 5 (localstack, unipoller, loki, trivy-system, velero)

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     NETWORK POLICY FLOW                         │
└─────────────────────────────────────────────────────────────────┘

┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  PROMETHEUS │────▶│  ALL NAMESPACES    │◀────│  GRAFANA    │
│  (default)  │     │  (metrics scraping)│     │  (default)  │
└─────────────┘     └─────────────┘     └─────────────┘

┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  PROMTAIL   │────▶│    LOKI     │────▶│ ALERTMANAGER│
│  (loki)     │logs │   (loki)    │alerts│  (default)  │
└─────────────┘     └─────────────┘     └─────────────┘

┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   VELERO    │────▶│  LOCALSTACK │     │ BACKBLAZE B2│
│  (velero)   │ S3  │ (localstack)│     │  (external) │
└─────────────┘     └─────────────┘     └─────────────┘
```

## Deployed Policies

### Policy Summary

| Namespace | Ingress Allowed From | Egress Allowed To |
|-----------|---------------------|-------------------|
| localstack | velero, ingress-nginx, prometheus (default) | DNS only |
| unipoller | prometheus (default) | DNS, UniFi controller (10.0.1.1) |
| loki | promtail, prometheus, grafana (default) | DNS, alertmanager (default) |
| trivy-system | prometheus (default) | DNS, K8s API, container registries |
| velero | prometheus (default) | DNS, localstack, Backblaze B2, K8s API |

### localstack

Provides S3-compatible storage for Velero testing.

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
    # Allow Velero S3 access
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: velero
      ports:
        - protocol: TCP
          port: 4566
    # Allow ingress-nginx for UI
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: ingress-nginx
      ports:
        - protocol: TCP
          port: 4566
    # Allow Prometheus metrics scraping
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: default
      ports:
        - protocol: TCP
          port: 4566
  egress:
    # DNS only
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
        - podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
```

### unipoller

Collects UniFi network metrics for Prometheus.

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: unipoller-network-policy
  namespace: unipoller
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
  ingress:
    # Allow Prometheus metrics scraping
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: default
      ports:
        - protocol: TCP
          port: 9130
  egress:
    # DNS
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
        - podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
    # UniFi controller
    - to:
        - ipBlock:
            cidr: 10.0.1.1/32
      ports:
        - protocol: TCP
          port: 443
        - protocol: TCP
          port: 8443
```

### loki

Log aggregation system receiving logs from Promtail.

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: loki-network-policy
  namespace: loki
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
  ingress:
    # Allow Promtail log ingestion
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: loki
      ports:
        - protocol: TCP
          port: 3100
    # Allow Prometheus and Grafana
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: default
      ports:
        - protocol: TCP
          port: 3100
  egress:
    # DNS
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
        - podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
    # AlertManager for log-based alerts
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: default
      ports:
        - protocol: TCP
          port: 9093
    # Internal Loki communication
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: loki
      ports:
        - protocol: TCP
          port: 3100
        - protocol: TCP
          port: 9095
        - protocol: TCP
          port: 7946
```

### trivy-system

Container vulnerability scanning operator.

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: trivy-operator-network-policy
  namespace: trivy-system
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
  ingress:
    # Allow Prometheus metrics scraping
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: default
      ports:
        - protocol: TCP
          port: 8080
  egress:
    # DNS
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
        - podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
    # Kubernetes API
    - to:
        - ipBlock:
            cidr: 10.96.0.1/32
      ports:
        - protocol: TCP
          port: 443
    # Container registries (external HTTPS)
    - to:
        - ipBlock:
            cidr: 0.0.0.0/0
            except:
              - 10.0.0.0/8
              - 172.16.0.0/12
              - 192.168.0.0/16
      ports:
        - protocol: TCP
          port: 443
```

### velero

Backup and disaster recovery solution.

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: velero-network-policy
  namespace: velero
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
  ingress:
    # Allow Prometheus metrics scraping
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: default
      ports:
        - protocol: TCP
          port: 8085
  egress:
    # DNS
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
        - podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
    # LocalStack S3
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: localstack
      ports:
        - protocol: TCP
          port: 4566
    # Kubernetes API
    - to:
        - ipBlock:
            cidr: 10.96.0.1/32
      ports:
        - protocol: TCP
          port: 443
    # Backblaze B2 (external HTTPS)
    - to:
        - ipBlock:
            cidr: 0.0.0.0/0
            except:
              - 10.0.0.0/8
              - 172.16.0.0/12
              - 192.168.0.0/16
      ports:
        - protocol: TCP
          port: 443
```

## ArgoCD Deployment

NetworkPolicies are deployed via ArgoCD using Kustomize:

**Application Manifest:** `manifests/applications/network-policies.yaml`

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: network-policies
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "-40"
spec:
  project: infrastructure
  source:
    repoURL: git@github.com:imcbeth/homelab.git
    path: manifests/base/network-policies
    targetRevision: HEAD
  destination:
    server: https://kubernetes.default.svc
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

**File Structure:**

```
manifests/base/network-policies/
├── kustomization.yaml
├── localstack/
│   └── network-policy.yaml
├── unipoller/
│   └── network-policy.yaml
├── loki/
│   └── network-policy.yaml
├── trivy-system/
│   └── network-policy.yaml
└── velero/
    └── network-policy.yaml
```

## Adding New Policies

### Step 1: Create Policy Directory

```bash
mkdir -p manifests/base/network-policies/<namespace>/
```

### Step 2: Create NetworkPolicy

```yaml
# manifests/base/network-policies/<namespace>/network-policy.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: <namespace>-network-policy
  namespace: <namespace>
  labels:
    app.kubernetes.io/name: <app-name>
    app.kubernetes.io/component: network-policy
spec:
  podSelector: {}  # Apply to all pods
  policyTypes:
    - Ingress
    - Egress
  ingress:
    # Add ingress rules
  egress:
    # Always include DNS
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
        - podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
    # Add other egress rules
```

### Step 3: Update Kustomization

```yaml
# manifests/base/network-policies/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - localstack/network-policy.yaml
  - unipoller/network-policy.yaml
  - loki/network-policy.yaml
  - trivy-system/network-policy.yaml
  - velero/network-policy.yaml
  - <namespace>/network-policy.yaml  # Add new policy
```

### Step 4: Test Before Committing

```bash
# Validate YAML
kubectl apply --dry-run=client -f manifests/base/network-policies/<namespace>/network-policy.yaml

# Apply manually first to test
kubectl apply -f manifests/base/network-policies/<namespace>/network-policy.yaml

# Verify policy
kubectl get networkpolicy -n <namespace>

# Test connectivity (see Testing section)
```

### Step 5: Commit and Deploy

```bash
git add manifests/base/network-policies/
git commit -m "feat: Add NetworkPolicy for <namespace>"
git push
```

ArgoCD will automatically sync the new policy.

## Testing Network Policies

### Verify Policies Applied

```bash
# List all NetworkPolicies
kubectl get networkpolicy -A

# Describe specific policy
kubectl describe networkpolicy -n velero velero-network-policy
```

### Test Allowed Traffic

```bash
# Test Prometheus -> namespace metrics (should succeed)
kubectl exec -n default prometheus-kube-prometheus-stack-prometheus-0 \
  -c prometheus -- wget -qO- --timeout=5 \
  http://<service>.<namespace>.svc:<port>/metrics | head -5
```

### Test Blocked Traffic

```bash
# Test from unauthorized namespace (should timeout)
kubectl run test-pod --rm -it --image=busybox -n default -- \
  wget -qO- --timeout=5 http://localstack.localstack.svc:4566
```

### Verify Application Functionality

| Application | Test Command | Expected Result |
|-------------|--------------|-----------------|
| Velero | `velero backup-location get` | Status: Available |
| Loki | Check Grafana Explore | Recent logs visible |
| Prometheus | Check targets page | All targets UP |
| UniPoller | Check UniFi dashboard | Metrics populated |

## Troubleshooting

### Policy Not Applied

```bash
# Check if policy exists
kubectl get networkpolicy -n <namespace>

# Check ArgoCD sync status
kubectl get application network-policies -n argocd

# Force sync
kubectl annotate application network-policies -n argocd \
  argocd.argoproj.io/refresh=hard --overwrite
```

### Traffic Unexpectedly Blocked

1. **Check namespace labels:**

   ```bash
   kubectl get namespace <namespace> --show-labels
   ```

   Ensure `kubernetes.io/metadata.name` label exists.

2. **Check pod labels:**

   ```bash
   kubectl get pods -n <namespace> --show-labels
   ```

   Verify podSelector matches.

3. **Check policy rules:**

   ```bash
   kubectl describe networkpolicy -n <namespace> <policy-name>
   ```

4. **Test with temporary policy removal:**

   ```bash
   kubectl delete networkpolicy -n <namespace> <policy-name>
   # Test connectivity
   # Re-apply policy
   kubectl apply -f manifests/base/network-policies/<namespace>/network-policy.yaml
   ```

### DNS Resolution Failing

All policies must allow DNS egress to kube-system:

```yaml
egress:
  - to:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: kube-system
      - podSelector:
          matchLabels:
            k8s-app: kube-dns
    ports:
      - protocol: UDP
        port: 53
      - protocol: TCP
        port: 53
```

### Prometheus Scraping Failing

Ensure ingress allows traffic from the `default` namespace (where Prometheus runs):

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

## Rollback

### Quick Rollback (Delete Policy)

```bash
kubectl delete networkpolicy -n <namespace> <policy-name>
```

### GitOps Rollback

```bash
git revert HEAD
git push
# ArgoCD will sync the revert
```

### Emergency: Delete All Policies

```bash
kubectl delete networkpolicy -A --all
```

## Future Enhancements

- [ ] Expand to remaining namespaces (cert-manager, external-dns, metallb-system)
- [ ] Implement default-deny policies for all namespaces
- [ ] Add Calico GlobalNetworkPolicy for cluster-wide rules
- [ ] Create Grafana dashboard for network policy monitoring
- [ ] Automated policy testing in CI/CD

## Related Documentation

- [Secrets Management](./secrets-management.md) - SealedSecrets for credentials
- [Velero](../applications/velero.md) - Backup solution
- [Loki](../applications/loki.md) - Log aggregation
- [Trivy Operator](../applications/trivy-operator.md) - Security scanning

## References

- [Kubernetes Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [Calico Network Policy](https://docs.tigera.io/calico/latest/network-policy/)
- [Network Policy Editor](https://editor.networkpolicy.io/) - Visual policy builder
