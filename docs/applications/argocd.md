---
title: "ArgoCD"
description: "GitOps continuous delivery tool for Kubernetes"
---

# ArgoCD

ArgoCD is a declarative, GitOps continuous delivery tool for Kubernetes that automates application deployment and lifecycle management.

## Overview

- **Namespace:** `argocd`
- **Helm Chart:** `argoproj/argo-cd`
- **Chart Version:** `9.4.1`
- **App Version:** `v3.3.0`
- **Deployment:** Self-managed via ArgoCD
- **Sync Wave:** `-50` (first application to deploy)
- **Sync Options:** `ServerSideApply=true`
- **URL:** `https://argocd.k8s.n37.ca`

:::info Version Update (2026-02-05)
Upgraded from chart 9.2.4 to 9.4.1. Server-Side Apply enabled (PR #376) for better handling of large CRDs and reduced sync conflicts.
:::

## Purpose

ArgoCD serves as the foundation of the GitOps workflow by:

- Monitoring git repositories for configuration changes
- Automatically syncing desired state to the cluster
- Providing visualization of application health
- Managing application lifecycle and rollbacks
- Enforcing declarative infrastructure as code

## Architecture

### Self-Management

ArgoCD manages its own deployment through a bootstrap Application manifest. This creates a self-healing, self-upgrading system where ArgoCD's configuration is version-controlled in git.

### Components

**Application Controller:**

- Monitors git repositories
- Compares desired state (git) vs actual state (cluster)
- Synchronizes resources
- Replicas: 2 (for high availability)

**Repo Server:**

- Clones git repositories
- Renders Helm charts and Kustomize configurations
- Caches rendered manifests

**API Server:**

- Provides web UI and API
- Handles authentication and authorization
- Service Type: ClusterIP

**Dex (Optional):**

- OAuth2/OIDC authentication provider
- Supports GitHub, Google, LDAP integration
- Currently disabled (can be enabled for SSO)

## Deployment Configuration

### Application Manifest

**Location:** `manifests/applications/argocd.yaml`

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: argocd
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "-50"
spec:
  project: infrastructure
  sources:
    - chart: argo-cd
      repoURL: https://argoproj.github.io/argo-helm
      targetRevision: 9.4.1
      helm:
        releaseName: argocd
        valueFiles:
          - $argocd/manifests/base/argocd/argocd-config.yaml
    - path: manifests/base/argocd
      repoURL: git@github.com:imcbeth/homelab.git
      targetRevision: HEAD
      ref: argocd
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

### Configuration Values

**Location:** `manifests/base/argocd/argocd-config.yaml`

```yaml
server:
  service:
    type: ClusterIP
configs:
  cm:
    url: https://argocd.k8s.n37.ca
controller:
  replicas: 2
```

## Access and Authentication

### Web UI Access

**External URL:** `https://argocd.k8s.n37.ca`

**Port Forward (for local access):**

```bash
kubectl port-forward svc/argocd-server -n argocd 8080:443
```

Then open: `https://localhost:8080`

### CLI Access

**Login:**

```bash
argocd login argocd.k8s.n37.ca --grpc-web
```

**Get Initial Admin Password:**

```bash
kubectl get secret argocd-initial-admin-secret -n argocd \
  -o jsonpath="{.data.password}" | base64 -d
```

**Change Admin Password:**

```bash
argocd account update-password --grpc-web
```

## Projects

ArgoCD organizes applications into projects for access control and resource management.

### Infrastructure Project

**Name:** `infrastructure`

**Purpose:** Core cluster infrastructure and platform services

**Applications:**

- argocd (self-management)
- metal-lb
- synology-csi
- cert-manager
- kube-prometheus-stack
- unipoller
- gatekeeper, gatekeeper-policies
- istio-base, istiod, istio-cni, istio-ztunnel
- tigera-operator
- sealed-secrets
- external-dns
- loki, promtail
- argo-workflows
- velero
- falco
- trivy-operator
- metrics-server
- network-policies

### Applications Project

**Name:** `applications` (default)

**Purpose:** User-facing applications and services

**Applications:**

- localstack

## Sync Waves

ArgoCD uses sync waves to control deployment order. Applications are deployed in ascending order by sync wave annotation.

**Current Sync Wave Configuration:**

```
-50: ArgoCD (must be first)
-45: istio-base (mesh CRDs)
-44: istiod (mesh control plane)
-43: istio-cni (mesh CNI plugin)
-42: istio-ztunnel (mesh data plane)
-40: network-policies (must be in place before workloads)
-35: MetalLB (networking layer)
-30: Sealed Secrets (must decrypt before other apps), Synology CSI (storage layer)
-20: UniFi Poller (metrics collection)
-15: kube-prometheus-stack (monitoring)
-12: Loki (log aggregation)
-11: Promtail (log collection)
-10: cert-manager, external-dns (TLS and DNS management)
 -8: Argo Workflows (CI/CD automation)
 -5: Falco (runtime security), Synology CSI (storage layer)
  0: Applications (localstack, etc.)
```

**Why This Matters:**

- Storage must be ready before applications request PVCs
- Load balancer must be ready before services request LoadBalancer IPs
- Monitoring should deploy early to track other applications

## Automated Sync Policies

All applications have automated sync enabled with these policies:

**prune: true**

- Automatically removes resources deleted from git
- Keeps cluster in sync with repository

**selfHeal: true**

- Automatically reverts manual changes to resources
- Enforces git as the single source of truth

**CreateNamespace: true**

- Automatically creates target namespace if it doesn't exist

## Common Operations

### List All Applications

```bash
# CLI
argocd app list --grpc-web

# kubectl
kubectl get applications -n argocd
```

### Get Application Status

```bash
# Detailed status
argocd app get <app-name> --grpc-web

# YAML manifest
kubectl get application <app-name> -n argocd -o yaml
```

### Manually Sync Application

```bash
# Sync specific application
argocd app sync <app-name> --grpc-web

# Force sync (bypass sync policies)
argocd app sync <app-name> --force --grpc-web

# Sync with prune
argocd app sync <app-name> --prune --grpc-web
```

### Refresh Application

```bash
# Refresh (re-compare git vs cluster)
argocd app get <app-name> --refresh --grpc-web

# Hard refresh (clear cache)
argocd app get <app-name> --hard-refresh --grpc-web
```

### View Application Logs

```bash
# Sync logs
argocd app logs <app-name> --grpc-web

# Follow logs
argocd app logs <app-name> --follow --grpc-web
```

## Git Repository Configuration

### Repository Secret

**Location:** `secrets/argocd-git-access.yaml` (git-crypt encrypted)

Contains SSH private key for accessing the private homelab repository.

**Apply Secret:**

```bash
kubectl apply -f secrets/argocd-git-access.yaml
```

### Repository Connection

```bash
# List connected repositories
argocd repo list --grpc-web

# Add new repository (if needed)
argocd repo add git@github.com:imcbeth/homelab.git \
  --ssh-private-key-path ~/.ssh/id_rsa --grpc-web
```

## Troubleshooting

### Application Won't Sync

**Check sync status:**

```bash
kubectl get application <name> -n argocd -o yaml | grep -A 20 "status:"
```

**Common issues:**

- Invalid YAML syntax in manifests
- Missing dependencies (e.g., storage class doesn't exist)
- Resource conflicts
- CRD not installed

**Force refresh and sync:**

```bash
argocd app get <name> --refresh --grpc-web
argocd app sync <name> --force --grpc-web
```

### Out of Sync Resources

**View diff:**

```bash
argocd app diff <name> --grpc-web
```

**Manual kubectl apply:**

```bash
kubectl apply -f manifests/applications/<app-name>.yaml
```

:::warning Application Manifest Updates
Files in `manifests/applications/` are NOT auto-deployed by ArgoCD self-management. After merging changes to Application manifests, you must run `kubectl apply -f manifests/applications/<app>.yaml` to update the Application spec in-cluster.
:::

### ServerSideApply Drift (ignoreDifferences)

When `ServerSideApply=true` is enabled, Kubernetes populates default values on resources that aren't in the Helm chart template (e.g., `imagePullPolicy`, `revisionHistoryLimit`, readiness probe defaults, `dnsPolicy`, `restartPolicy`, `schedulerName`, etc.). This causes perpetual OutOfSync in ArgoCD.

**Solution:** Add comprehensive `ignoreDifferences` with `jqPathExpressions` and enable `RespectIgnoreDifferences=true`:

```yaml
spec:
  ignoreDifferences:
    - group: apps
      kind: DaemonSet
      jqPathExpressions:
        - .metadata.labels
        - .metadata.annotations
        - .spec.revisionHistoryLimit
        - .spec.template.spec.containers[].imagePullPolicy
        # ... all K8s-defaulted fields
  syncPolicy:
    syncOptions:
      - ServerSideApply=true
      - RespectIgnoreDifferences=true
```

**Affected applications (as of 2026-02-05):**

- `istio-ztunnel` - DaemonSet K8s-defaulted fields (PR #379, #380)
- `tigera-operator` - Installation CR operator-populated defaults (PR #381)
- `kube-prometheus-stack` - Grafana secret checksum drift

### ArgoCD Pods Not Running

**Check pod status:**

```bash
kubectl get pods -n argocd
```

**View logs:**

```bash
kubectl logs -n argocd deployment/argocd-server
kubectl logs -n argocd deployment/argocd-application-controller
kubectl logs -n argocd deployment/argocd-repo-server
```

### Git Repository Connection Issues

**Test SSH key:**

```bash
ssh -T git@github.com
```

**Verify repository secret:**

```bash
kubectl get secret -n argocd | grep repo
```

### Self-Healing Not Working

**Check sync policy:**

```bash
kubectl get application <name> -n argocd -o yaml | grep -A 5 "syncPolicy:"
```

**Ensure selfHeal is enabled:**

```yaml
syncPolicy:
  automated:
    selfHeal: true
```

## Updating ArgoCD

### Helm Chart Updates

To update to a newer ArgoCD version:

1. Check [ArgoCD releases](https://github.com/argoproj/argo-cd/releases) for changes
2. Update `targetRevision` in `manifests/applications/argocd.yaml`
3. Review CHANGELOG for breaking changes
4. Commit and push changes
5. ArgoCD will self-upgrade automatically

**Example:**

```yaml
targetRevision: 9.5.0  # Update from 9.4.1
```

### Configuration Changes

To modify ArgoCD settings:

1. Edit `manifests/base/argocd/argocd-config.yaml`
2. Commit and push
3. ArgoCD syncs and applies changes automatically

## Best Practices

### Application Organization

- Use descriptive application names
- Set appropriate sync waves
- Use projects for access control
- Document sync dependencies

### Git Workflow

- Always use pull requests for main branch
- Test changes in feature branches
- Use meaningful commit messages
- Tag releases for rollback capability

### Sync Policies

- Enable automated sync for stable applications
- Use manual sync for critical changes
- Enable prune for complete state management
- Use selfHeal for production stability

### Monitoring

- Watch ArgoCD UI for sync failures
- Set up alerts for out-of-sync applications
- Monitor ArgoCD resource usage
- Review sync history regularly

## Resource Usage

**Application Controller:**

- CPU: ~100-200m under normal load
- Memory: ~256-512Mi

**Repo Server:**

- CPU: ~50-100m
- Memory: ~128-256Mi

**API Server:**

- CPU: ~50-100m
- Memory: ~128-256Mi

**Total:** Minimal overhead for powerful automation capabilities on the Raspberry Pi cluster.

## Related Documentation

- [Monitoring Overview](../monitoring/overview.md)
- [kube-prometheus-stack](./kube-prometheus-stack.md)
- [Synology CSI Storage](../storage/synology-csi.md)
- [GitOps Workflow Guide](../kubernetes/cluster-configuration.md)

## References

- [ArgoCD Official Documentation](https://argo-cd.readthedocs.io/)
- [ArgoCD GitHub Repository](https://github.com/argoproj/argo-cd)
- [Helm Chart Repository](https://github.com/argoproj/argo-helm)
