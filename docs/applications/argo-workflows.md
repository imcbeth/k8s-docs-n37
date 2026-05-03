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
| **Chart Version** | 1.0.13 |
| **App Version** | v4.x |
| **ArgoCD App** | `argo-workflows` |
| **UI URL** | `https://workflows.k8s.n37.ca` |
| **Auth** | GitHub SSO via oauth2-proxy |

:::info v4 API Change (2026-05-03)
Argo Workflows v4.0 renamed `CronWorkflow.spec.schedule` (string) to `spec.schedules` (array). CronWorkflows using the old singular `schedule:` field silently fail with "must have at least one schedule" in the controller logs and never fire. See [CronWorkflow API Change](#cronworkflow-v4-api-change) below.
:::

## Components

- **Workflow Controller** — Watches for Workflow CRs and orchestrates execution
- **Argo Server** — UI and API server at `https://workflows.k8s.n37.ca`
- **Executor** — Runs workflow steps in containers

## Architecture

### Multi-Source ArgoCD Application

The ArgoCD Application uses three sources to avoid duplicate manifest rendering:

```yaml
sources:
  # 1. Helm chart
  - repoURL: https://argoproj.github.io/argo-helm
    chart: argo-workflows
    targetRevision: 1.0.13
    helm:
      releaseName: argo-workflows
      valueFiles:
        - $values/manifests/base/argo-workflows/values.yaml
  # 2. Values ref ONLY — no path (adding path here renders manifests twice)
  - repoURL: git@github.com:imcbeth/homelab.git
    targetRevision: HEAD
    ref: values
  # 3. Additional resources (CronWorkflows, RBAC, SealedSecret)
  - repoURL: git@github.com:imcbeth/homelab.git
    path: manifests/base/argo-workflows
    targetRevision: HEAD
```

:::warning Do not add `path:` to the ref source
A source with both `ref:` and `path:` renders manifests AND serves as a Helm values reference, causing every custom resource to appear twice (`RepeatedResourceWarning`). Keep source 2 as `ref:` only and use source 3 for actual manifest paths.
:::

### Authentication

The Argo Workflows UI uses oauth2-proxy for GitHub SSO. The Helm chart is configured with `--auth-mode=server` (bypasses Argo's own auth, relies on the oauth2-proxy cookie set by nginx).

The ingress uses these annotations:

```yaml
nginx.ingress.kubernetes.io/auth-url: "http://oauth2-proxy.oauth2-proxy.svc.cluster.local:4180/oauth2/auth"
nginx.ingress.kubernetes.io/auth-signin: "https://oauth.k8s.n37.ca/oauth2/start?rd=$scheme://$host$uri"
nginx.ingress.kubernetes.io/auth-response-headers: "X-Auth-Request-User,X-Auth-Request-Email"
```

## CronWorkflows

Two CronWorkflows are deployed for automated cluster operations:

### cluster-healthcheck

**Schedule:** Daily at 06:00 MT (`0 6 * * *`)

Runs 5 checks in parallel, then fires an AlertManager alert (`ClusterHealthDegraded`) if any issues are found:

| Check | What it detects |
|-------|----------------|
| `check-argocd` | Apps not Synced or not Healthy |
| `check-pods` | Pods in Failed/Unknown phase, or CrashLoopBackOff |
| `check-pvs` | PersistentVolumes in Released or Failed state |
| `check-velero` | Last backup for each schedule not Completed |
| `check-gatekeeper` | Total violation count > 0 |

**RBAC:** `cluster-healthcheck` ServiceAccount with ClusterRole granting read access to applications, pods, PVs, backups, and Gatekeeper constraints.

### velero-backup-validation

**Schedule:** 1st of each month at 06:00 MT (`0 6 1 * *`)

Exercises the full DR cycle:

1. Verify Velero BSL is Available
2. Create test namespace + marker ConfigMap
3. Take a Velero backup of the namespace
4. Delete the namespace (simulating a disaster)
5. Restore from the backup
6. Verify the marker ConfigMap exists with correct data
7. Cleanup (runs on exit regardless of success/failure)

**RBAC:** `velero-validator` ServiceAccount with permissions to manage namespaces, ConfigMaps, Velero Backups/Restores, and BSL reads.

## CronWorkflow v4 API Change

Argo Workflows v4.0 changed the CronWorkflow schedule field:

```yaml
# v3 (broken in v4 — silently fails)
spec:
  schedule: "0 6 * * *"

# v4 (correct)
spec:
  schedules:
    - "0 6 * * *"
```

**Symptom:** CronWorkflows never fire. Controller logs show:

```
cron workflow must have at least one schedule
```

**Fix:** Update all CronWorkflow manifests to use `schedules:` (array).

## Resource Usage

| Component | CPU Request | CPU Limit | Memory Request | Memory Limit |
|-----------|-------------|-----------|----------------|--------------|
| workflow-controller | 50m | 200m | 128Mi | 256Mi |
| server | 50m | 200m | 128Mi | 256Mi |

## Configuration

**Helm values:** `manifests/base/argo-workflows/values.yaml`

```yaml
server:
  extraArgs:
    - --auth-mode=server
```

## Usage Examples

### Submit a Workflow

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

### Simple Workflow Example

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

## Troubleshooting

### CronWorkflow never fires

Check the workflow controller logs for schedule validation errors:

```bash
kubectl logs -n argo-workflows -l app.kubernetes.io/name=argo-workflows-workflow-controller | grep -i "schedule\|cron"
```

If you see `must have at least one schedule`, the CronWorkflow is using the v3 `schedule:` (singular) field. Update to v4 `schedules:` (array).

### Workflow Stuck in Pending

```bash
kubectl logs -n argo-workflows -l app.kubernetes.io/name=argo-workflows-workflow-controller
kubectl get events -n argo-workflows --sort-by='.lastTimestamp'
```

### UI returns 401 (no redirect to GitHub login)

If visiting `https://workflows.k8s.n37.ca` shows a blank 401 instead of redirecting to GitHub login, the `auth-signin` ingress annotation may be invalid. See the [oauth2-proxy troubleshooting guide](./oauth2-proxy#blank-401-on-every-request-no-redirect-to-github-login).

### Permission Denied Errors in Workflows

```bash
kubectl get rolebindings,clusterrolebindings -A | grep argo
```

## References

- [Argo Workflows Documentation](https://argoproj.github.io/argo-workflows/)
- [Workflow Examples](https://github.com/argoproj/argo-workflows/tree/master/examples)
- [CronWorkflow Reference](https://argoproj.github.io/argo-workflows/cron-workflows/)

---

**Last Updated:** 2026-05-03
