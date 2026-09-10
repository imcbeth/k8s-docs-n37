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
| **Chart Version** | **2.0.4** (as of 2026-09-07, via Renovate PR #885 — major bump; appVersion v4.1.2) |
| **App Version** | v4.1.2 |
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
    targetRevision: 1.0.14
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

## lifeonabike Build Pipeline

A `WorkflowTemplate` named `lifeonabike-build` provides automated CI/CD for `lifeonabike.ca`. It is submitted by Argo Events when a push lands on the `main` branch of `github.com/imcbeth/lifeonabike.ca`.

### Pipeline Diagram

```mermaid
sequenceDiagram
    autonumber
    participant Dev as 👨‍💻 Developer
    participant GH as GitHub<br/>imcbeth/lifeonabike.ca
    participant CF as ☁️ Cloudflare Edge
    participant CFD as cloudflared pods<br/>(×2, ns: lifeonabike)
    participant AE as Argo Events<br/>EventSource :12000
    participant Sensor as Argo Events<br/>Sensor
    participant AW as Argo Workflows
    participant Git as alpine/git:v2.52.0<br/>(clone step)
    participant Kaniko as kaniko:v1.24.0<br/>(build step)
    participant Zot as Zot Registry<br/>zot.zot.svc.cluster.local:5000
    participant K8s as Kubernetes<br/>deploy/web (lifeonabike ns)

    Dev->>GH: git push main
    GH->>CF: Webhook POST /push<br/>HMAC-SHA256 signed
    CF->>CFD: Tunnel → HTTP
    CFD->>AE: Forward POST :12000/push
    AE->>AE: Verify HMAC signature<br/>Filter: body.ref == refs/heads/main
    AE->>Sensor: Fire lifeonabike-push event
    Sensor->>AW: Submit WorkflowTemplate<br/>lifeonabike-build (revision=main)
    Note over AW: Workspace PVC provisioned<br/>synology-iscsi-delete-ssd · 2Gi
    AW->>Git: Step 1 — clone<br/>shallow clone → capture git SHA
    AW->>Kaniko: Step 2 — build<br/>Dockerfile → image layers
    Kaniko->>Zot: Push :&lt;sha&gt; + :latest tags<br/>HTTP (insecure, in-cluster only)
    AW->>K8s: Step 3 — deploy<br/>kubectl rollout restart deployment/web
    K8s->>Zot: Pull new image<br/>via registry.k8s.n37.ca (HTTPS)
    Note over AW: Workspace PVC auto-deleted<br/>(Delete reclaim policy)
```

### Steps

| Step | Image | Action |
|------|-------|--------|
| `clone` | `alpine/git:v2.52.0` | Shallow-clones the app repo, captures git SHA |
| `build` | `gcr.io/kaniko-project/executor:v1.24.0` | Builds the Docker image, pushes `<sha>` + `latest` tags to Zot |
| `deploy` | `alpine/k8s:1.31.0` | Runs `kubectl rollout restart deployment/web -n lifeonabike` |

### Key Configuration

```yaml
# Kaniko pushes to in-cluster Zot over HTTP (pod-to-MetalLB HTTPS is broken in-cluster)
- --destination=zot.zot.svc.cluster.local:5000/lifeonabike/lifeonabike.ca:{{inputs.parameters.image-tag}}
- --insecure

# Workflow pods bypass ztunnel — Kaniko and kubectl reach non-mesh endpoints
podMetadata:
  annotations:
    ambient.istio.io/redirection: disabled
```

### Manual Trigger

```bash
argo submit --from workflowtemplate/lifeonabike-build \
  -n argo-workflows \
  -p revision=main
```

See the [lifeonabike guide](./lifeonabike.md) for full pipeline details, RBAC setup, and secrets.

## Artifact Storage

Argo Workflows uses **LocalStack S3** as the default artifact store.

:::danger The bucket does not survive a LocalStack restart
An earlier version of this page said a `PreSync` Job (`localstack-argo-workflows-setup`) *"ensures the bucket exists before each sync"*. It did not. It was a plain Job that ran **once** at install time, and LocalStack loses all buckets whenever it restarts — `PERSISTENCE=1` is set but is a no-op on the community edition ([details](./localstack.md#persistence-is-a-licensed-feature)).

The result on 2026-09-09 was that **every build failed**:

```
lifeonabike-build-zmgqg  Failed
wait: Error (exit code 64): failed to put file: The specified bucket does not exist
```

Bucket creation now lives in a LocalStack **init hook** that runs on every start, and the one-shot Job has been removed. If artifact uploads start failing, check the bucket exists before anything else:

```bash
kubectl -n localstack exec deploy/localstack -- \
  curl -s -o /dev/null -w '%{http_code}\n' http://localhost:4566/argo-workflows
```

:::

```yaml
# Artifact repository config points at LocalStack
endpoint: localstack.localstack.svc.cluster.local:4566
bucket: argo-workflows
```

The CronWorkflows (cluster-healthcheck, velero-backup-validation) also use LocalStack for their intermediate artifacts.

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

## templateDefaults merges by template TYPE

:::danger `templateDefaults.container` does nothing for `script:` templates
Cost two wrong diagnoses on 2026-09-10. `templateDefaults` merges into the **matching field only**. A workflow whose templates are all `script:` gets nothing from a `templateDefaults.container` block — it merges into nothing, silently, and every step falls back to the workflow-controller ConfigMap's `mainContainer` defaults (here 100m / 128Mi).

`cluster-healthcheck` had exactly that shape. Its `check-pods` step was OOMKilled (exit 137) **every day**, so the daily health check had never once completed.

```yaml
# WRONG for a workflow of script: templates — merges into nothing
templateDefaults:
  container:
    resources: {...}

# RIGHT
templateDefaults:
  script:
    resources: {...}
```

:::

### It is not a precedence problem

The tempting conclusion — that the controller's `mainContainer` overrides `templateDefaults` — is wrong, and I published it before checking. The disproof is in the same cluster:

| Workflow | Templates | Defaults apply? | Measured on the pod |
|---|---|---|---|
| `backup-validation` | 9× `container:` | yes | **256Mi** |
| `cluster-healthcheck` | 6× `script:` | no | **128Mi** |

Same controller, same `mainContainer` config, different outcome. The variable is template type, not precedence.

### Verify what a step actually got

Don't infer the limit from the manifest — read it off a running pod:

```bash
kubectl -n argo-workflows get pod <step-pod> \
  -o jsonpath='{.spec.containers[?(@.name=="main")].resources.limits.memory}'
```

### Sizing a step: measure the peak

`check-pods` needed more than the others because it runs **two full-cluster queries back to back in one container**. Measured individually via `/sys/fs/cgroup/memory.peak` in a probe pod:

| Command | Peak |
|---|---|
| `get pods -A --field-selector=... -o json \| jq` | 51 MiB |
| `get pods -A -o jsonpath=...` (153 pods, ~2.9 MiB JSON) | 83 MiB |

Both are under 128Mi individually — which is exactly why the OOMKill looked impossible. **Go does not return freed heap to the OS**, so cumulative RSS across the pair exceeds the limit. Set to 384Mi at template level, since this step legitimately needs more than the workflow default.

```bash
# The two-minute measurement that should have come first
kubectl -n <ns> exec <probe-pod> -- cat /sys/fs/cgroup/memory.peak
```

## Alerting — a label bug made four alerts inert

Found 2026-09-09. Four of the eight Argo alerts selected `argo_workflows_gauge{status="..."}`, but the metric's label is **`phase`**, not `status`. That selector matches **zero series**, so these could never fire:

- `ArgoWorkflowFailed`
- `ArgoWorkflowError`
- `ArgoWorkflowStuck`
- `ArgoWorkflowHighFailureRate`

Proven rather than inferred: two real workflow failures that day produced no alert at all, and `increase(argo_workflows_gauge{status="Failed"}[6h])` returned empty.

Three of them also applied `increase()` — a **counter** function — to a gauge.

### `ArgoWorkflowHighFailureRate` was rewritten, not patched

It derived a 24-hour failure *ratio* from `increase()` over the gauge. That is unsound regardless of the label: the gauge counts workflows **currently present**, and completed workflows are TTL'd away within hours, so there is no 24h history in it to rate.

```promql
# now — what a gauge can honestly answer
sum(argo_workflows_gauge{phase=~"Failed|Error"}) > 3
```

Several failed at once means something systemic; a single bad run is covered by `ArgoWorkflowFailed`.

:::tip Verify a selector matches before trusting an alert
A rule with a wrong label name is `health: ok` and permanently `inactive` — indistinguishable from "nothing is wrong". Check it matches real series:

```bash
kubectl -n default exec prometheus-kube-prometheus-stack-prometheus-0 -c prometheus -- \
  wget -qO- --post-data='query=<your selector>' http://localhost:9090/api/v1/query
```

Zero results for a metric that exists means the selector, not the cluster, is wrong.
:::

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

If visiting `https://workflows.k8s.n37.ca` shows a blank 401 instead of redirecting to GitHub login, the `auth-signin` ingress annotation may be invalid. See the [oauth2-proxy troubleshooting guide](./oauth2-proxy.md#blank-401-on-every-request-no-redirect-to-github-login).

### Permission Denied Errors in Workflows

```bash
kubectl get rolebindings,clusterrolebindings -A | grep argo
```

## References

- [Argo Workflows Documentation](https://argoproj.github.io/argo-workflows/)
- [Workflow Examples](https://github.com/argoproj/argo-workflows/tree/master/examples)
- [CronWorkflow Reference](https://argoproj.github.io/argo-workflows/cron-workflows/)

---

**Last Updated:** 2026-06-01
