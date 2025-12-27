---
title: "ArgoCD"
description: "GitOps continuous delivery tool for Kubernetes"
---

# ArgoCD

ArgoCD is a declarative, GitOps continuous delivery tool for Kubernetes that automates application deployment and lifecycle management.

## Overview

- **Namespace:** `argocd`
- **Helm Chart:** `argoproj/argo-cd`
- **Chart Version:** `9.0.5`
- **Deployment:** Self-managed via ArgoCD
- **Sync Wave:** `-50` (first application to deploy)
- **URL:** `https://argocd.k8s.n37.ca`

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
      targetRevision: 9.0.5
      helm:
        valueFiles:
          - $argocd/manifests/base/argocd/argocd-config.yaml
    - repoURL: git@github.com:imcbeth/homelab.git
      path: manifests/base/argocd
      targetRevision: HEAD
      ref: argocd
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
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
- pi-hole

### Applications Project

**Name:** `applications` (default)

**Purpose:** User-facing applications and services

**Applications:**

- localstack
- (future applications)

## Sync Waves

ArgoCD uses sync waves to control deployment order. Applications are deployed in ascending order by sync wave annotation.

**Current Sync Wave Configuration:**

```
-50: ArgoCD (must be first)
-35: MetalLB, Pi-hole (networking layer)
-30: Synology CSI (storage layer)
-20: UniFi Poller (metrics collection)
-15: kube-prometheus-stack (monitoring)
-10: cert-manager (TLS management)
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
targetRevision: 9.1.0  # Update from 9.0.5
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
