---
sidebar_position: 18
title: "Argo Events"
description: "Event-driven workflow automation for Kubernetes"
---

# Argo Events

Argo Events is the event-driven automation layer that bridges external events (GitHub webhooks, Kafka messages, schedules) and Argo Workflows executions.

## Overview

| Property | Value |
|----------|-------|
| **Namespace** | `argo-events` |
| **Helm Chart** | `argo/argo-events` |
| **Chart Version** | 2.4.22 (as of 2026-06-21, via Renovate PR #740) |
| **App Version** | v1.9.10 |
| **ArgoCD App** | `argo-events` |
| **Sync Wave** | -8 |
| **EventBus** | JetStream (NATS 2.10.10) |

## Architecture

Argo Events has three main components:

```
GitHub webhook ──► EventSource ──► EventBus (NATS JetStream) ──► Sensor ──► Workflow submit
```

| Component | Role |
|-----------|------|
| **EventBus** | Message broker (JetStream / NATS). Events are published here and held until a Sensor consumes them. |
| **EventSource** | Receives external events (webhooks, schedules, Kafka, etc.) and publishes them to the EventBus. |
| **Sensor** | Subscribes to EventBus events and triggers actions (submit an Argo Workflow, call a webhook, etc.). |

## Deployment

The ArgoCD Application uses a multi-source pattern:

```yaml
sources:
  # 1. Helm chart
  - repoURL: https://argoproj.github.io/argo-helm
    chart: argo-events
    targetRevision: 2.4.21
    helm:
      releaseName: argo-events
      valueFiles:
        - $values/manifests/base/argo-events/values.yaml
  # 2. Values ref ONLY
  - repoURL: git@github.com:imcbeth/homelab.git
    targetRevision: HEAD
    ref: values
  # 3. Additional resources
  - repoURL: git@github.com:imcbeth/homelab.git
    path: manifests/base/argo-events
    targetRevision: HEAD
```

:::warning kustomization.yaml is required
The directory source (source 3) will apply **every YAML file** in the path as a Kubernetes manifest — including `values.yaml`. Add a `kustomization.yaml` that enumerates only real resources to switch ArgoCD into Kustomize mode and prevent `values.yaml` from being applied.
:::

## EventBus

The JetStream EventBus runs a single NATS instance:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: EventBus
metadata:
  name: default
  namespace: argo-events
spec:
  jetstream:
    version: "2.10.10"
    replicas: 1
```

:::note Single replica
The cluster uses a 1-replica EventBus. Set `replicas: 1` explicitly — NATS will otherwise try to form a cluster quorum and hang if fewer peers are available.
:::

## lifeonabike CI Pipeline

The primary use case is a GitHub push → Docker build → deploy pipeline for `lifeonabike.ca`.

### EventSource

`lifeonabike-github` listens for push events on `imcbeth/lifeonabike.ca`:

```yaml
spec:
  github:
    lifeonabike-push:
      repositories:
        - owner: imcbeth
          names: [lifeonabike.ca]
      webhook:
        endpoint: /push
        port: "12000"
        method: POST
        url: https://build-webhook.n37.ca
      events: [push]
      apiToken:
        name: github-access-token
        key: token
      webhookSecret:
        name: github-lifeonabike-webhook-secret
        key: secret
      filter:
        expression: "body.ref == 'refs/heads/main'"
```

The webhook is exposed at `https://build-webhook.n37.ca` via the **Cloudflare Tunnel** running in the `lifeonabike` namespace — no ingress-nginx rule or public IP required.

### Sensor

`lifeonabike-build` submits the Argo Workflows `WorkflowTemplate` when a push event arrives:

```yaml
spec:
  dependencies:
    - name: push-event
      eventSourceName: lifeonabike-github
      eventName: lifeonabike-push
  triggers:
    - template:
        name: build-trigger
        argoWorkflow:
          operation: submit
          source:
            resource:
              apiVersion: argoproj.io/v1alpha1
              kind: Workflow
              spec:
                workflowTemplateRef:
                  name: lifeonabike-build
```

The Sensor uses the `lifeonabike-sensor-sa` ServiceAccount, which is bound (via `lifeonabike-workflow-submitter` RoleBinding in the `argo-workflows` namespace) to a Role that allows workflow submission.

### Prerequisites (one-time cluster setup)

```bash
# GitHub PAT with repo scope + admin:repo_hook for auto-registration
kubectl create secret generic github-access-token \
  --from-literal=token=<your-pat> -n argo-events

# HMAC secret — paste the same value into GitHub webhook settings
# (must NOT be named with "secret" in the filename — use *-sealed.yaml naming)
kubectl create secret generic github-lifeonabike-webhook-secret \
  --from-literal=secret=$(openssl rand -hex 32) -n argo-events
```

## Monitoring

Argo Events controller metrics are scraped by kube-prometheus-stack:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  namespace: default   # kube-prometheus-stack is deployed in default
spec:
  namespaceSelector:
    matchNames: [argo-events]
  endpoints:
    - port: metrics
      path: /metrics
```

:::warning Prometheus namespace
`kube-prometheus-stack` is deployed in the **`default`** namespace, not `monitoring`. The ServiceMonitor `namespace:` field and NetworkPolicy scrape rules must use `default`.
:::

Metrics port: **7777** (both controller-manager and EventBus NATS exporter).

## Networking

### NetworkPolicy

The `argo-events` NetworkPolicy allows:

| Direction | Target | Port | Purpose |
|-----------|--------|------|---------|
| Ingress | any (bare) | 15008 | ztunnel HBONE |
| Ingress | `default` ns | 7777 | Prometheus scrape |
| Ingress | intra-pod | 4222/6222/8222 | NATS cluster |
| Ingress | `ingress-nginx` or `lifeonabike` | 12000 | Webhook events |
| Egress | any (bare) | 15008 | ztunnel HBONE |
| Egress | `kube-system` kube-dns | 53 | DNS |
| Egress | K8s API (10.96.0.1, 10.0.10.0/24) | 443/6443 | API server |
| Egress | `istio-system` | 15012/15017 | istiod xDS/webhook |
| Egress | `argo-workflows` | 2746 | Sensor → Workflow submit |
| Egress | `kafka` | 9092 | Kafka EventSource |
| Egress | 0.0.0.0/0 (no RFC1918) | 443 | GitHub API/webhooks |

### Cloudflare Tunnel for Webhook

The EventSource webhook at port 12000 is exposed externally via Cloudflare Tunnel (running in `lifeonabike` namespace), not ingress-nginx. The tunnel routes `build-webhook.n37.ca` → `lifeonabike-github-eventsource-svc.argo-events.svc.cluster.local:12000`.

This means:

- No public IP exposure
- No ingress-nginx Ingress rule for webhooks
- Traffic enters via the `lifeonabike` namespace → therefore `lifeonabike` is in the NetworkPolicy ingress allow list

## Troubleshooting

### EventSource not receiving events

```bash
# Check EventSource pod logs
kubectl logs -n argo-events -l eventsource-name=lifeonabike-github

# Verify webhook is registered in GitHub
# Go to https://github.com/imcbeth/lifeonabike.ca/settings/hooks
```

### Sensor not triggering

```bash
# Check Sensor pod logs
kubectl logs -n argo-events -l sensor-name=lifeonabike-build

# Check EventBus health
kubectl get eventbus -n argo-events
```

### EventBus pods stuck

```bash
# Check JetStream pod status
kubectl get pods -n argo-events -l app=eventbus-default-js
kubectl describe pod -n argo-events eventbus-default-js-0
```

If the NATS container is hanging waiting for cluster quorum, verify `replicas: 1` in the EventBus spec.

### NetworkPolicy blocking webhook

Verify the Cloudflare Tunnel pod in `lifeonabike` can reach `argo-events:12000`:

```bash
kubectl exec -n lifeonabike deploy/cloudflared -- \
  wget -q -O- http://lifeonabike-github-eventsource-svc.argo-events.svc.cluster.local:12000
```

## References

- [Argo Events Documentation](https://argoproj.github.io/argo-events/)
- [EventSource Reference](https://argoproj.github.io/argo-events/eventsources/setup/github/)
- [Sensor Reference](https://argoproj.github.io/argo-events/sensors/triggers/argo-workflow/)

---

**Last Updated:** 2026-06-01
