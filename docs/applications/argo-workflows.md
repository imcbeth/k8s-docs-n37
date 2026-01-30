---
sidebar_position: 17
title: "Argo Workflows"
description: "Kubernetes-native workflow engine for orchestrating parallel jobs"
---

# Argo Workflows

Argo Workflows is the workflow engine for orchestrating parallel jobs on Kubernetes.

## Overview

| Property | Value |
|----------|-------|
| **Namespace** | `argo-workflows` |
| **Helm Chart** | `argo/argo-workflows` |
| **Version** | 0.47.1 |
| **ArgoCD App** | `argo-workflows` |
| **UI URL** | `https://argo-workflows.k8s.n37.ca` |

## Components

- **Workflow Controller** - Watches for Workflow CRs and orchestrates execution
- **Argo Server** - UI and API server for workflow management
- **Executor** - Runs workflow steps in containers

## Configuration

**ArgoCD Application:** `manifests/applications/argo-workflows.yaml`

```yaml
# Key Helm values
server:
  extraArgs:
    - --auth-mode=server
  ingress:
    enabled: true
    ingressClassName: nginx
    hosts:
      - argo-workflows.k8s.n37.ca
    tls:
      - secretName: argo-workflows-tls
        hosts:
          - argo-workflows.k8s.n37.ca

controller:
  workflowNamespaces:
    - argo-workflows
    - default
```

## Resource Usage

| Component | CPU Request | CPU Limit | Memory Request | Memory Limit |
|-----------|-------------|-----------|----------------|--------------|
| workflow-controller | 50m | 200m | 128Mi | 256Mi |
| server | 50m | 200m | 128Mi | 256Mi |

## Usage Examples

### Simple Workflow

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Workflow
metadata:
  generateName: hello-world-
  namespace: argo-workflows
spec:
  entrypoint: whalesay
  templates:
    - name: whalesay
      container:
        image: docker/whalesay
        command: [cowsay]
        args: ["hello world"]
```

### Submit Workflow

```bash
# Submit a workflow
argo submit -n argo-workflows workflow.yaml

# List workflows
argo list -n argo-workflows

# Watch workflow progress
argo watch -n argo-workflows <workflow-name>

# Get workflow logs
argo logs -n argo-workflows <workflow-name>
```

## Integration with CI/CD

Argo Workflows can be triggered by:

- GitHub webhooks
- ArgoCD post-sync hooks
- Kubernetes CronWorkflows
- Manual submission via CLI or UI

## Troubleshooting

### Workflow Stuck in Pending

```bash
# Check controller logs
kubectl logs -n argo-workflows -l app.kubernetes.io/name=argo-workflows-workflow-controller

# Check pod events
kubectl get events -n argo-workflows --sort-by='.lastTimestamp'
```

### Permission Denied Errors

```bash
# Verify service account permissions
kubectl get rolebindings,clusterrolebindings -A | grep argo
```

## References

- [Argo Workflows Documentation](https://argoproj.github.io/argo-workflows/)
- [Workflow Examples](https://github.com/argoproj/argo-workflows/tree/master/examples)

---

**Last Updated:** 2026-01-30
