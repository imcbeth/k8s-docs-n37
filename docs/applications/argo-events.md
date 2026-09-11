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
| **Chart Version** | 2.4.26 (as of 2026-09-06, via Renovate PR #850) |
| **App Version** | v1.9.10 |
| **ArgoCD App** | `argo-events` |
| **Sync Wave** | -8 |
| **EventBus** | JetStream (NATS 2.10.10) |

## Vulnerability status (reviewed 2026-09-11)

`v1.9.11` carries **4 unique CRITICAL CVEs**, all in vendored Go dependencies:

| CVE | Component | Fixed in |
|---|---|---|
| CVE-2025-68121 | Go `stdlib v1.25.6` | 1.25.7 |
| CVE-2026-33186 | `grpc v1.72.2` | 1.79.3 |
| CVE-2026-33815 | `pgx/v5 v5.7.5` | 5.9.0 |
| CVE-2026-33816 | `pgx/v5 v5.7.5` | 5.9.0 |

:::tip Trivy reports 16, not 4
Four workloads run the identical image — `controller-manager`, `events-webhook`, the sensor and the eventsource — so each CVE is counted four times. **Fixing one image clears all sixteen.** The same per-workload multiplication is why `CriticalVulnerabilitiesDetected` was replaced with delta and outlier rules.
:::

**Two of the four are not reachable here.** `pgx` is a PostgreSQL driver, linked only for the Postgres persistence backend. This cluster's EventBus is **JetStream/NATS**, so those code paths are never exercised.

### There is nothing to upgrade to

`v1.9.11` is the latest release (2026-07-13) and **its image has never been rebuilt** — the registry digest still carries the original build date. All four CVEs need an upstream rebuild.

### The `latest` tag does not help — measured

A `latest` tag exists, rebuilt 2026-08-31 with a genuinely different digest, which looks tempting. Scanned with the same scanner, flags and server:

| | v1.9.11 | latest |
|---|---:|---:|
| unique CRITICAL | **4** | **5** |
| unique HIGH | 54 | 53 |

**Fixed by `latest`: none.** The dependency versions are byte-identical; the rebuild bumped nothing.

**Added by `latest`: CVE-2025-32445**, reported against a pseudo-version (`v0.0.0-20260831051828-…`) that trivy cannot compare to the 1.9.6 which fixed it — noise inherent to unpinned builds.

:::warning Do not swap a pinned version for `latest` to chase CVEs
It trades a known exposure for an unknown one, and here it demonstrably buys nothing. This repository has already lost 16 days of backups to an unpinned dependency moving underneath it.
:::

### Renovate surfaces this immediately

`argo-events` has a dedicated rule with `schedule: ["at any time"]`, so a fixed release appears the day it ships rather than waiting for the weekend batch. The rule sits **after** the ArgoCD ecosystem grouping (so it is not held behind argo-cd) and **before** the major-update rule (so major bumps are still held for review).

`vulnerabilityAlerts` does not cover this case — it keys off GitHub advisories for the *chart*, not CVEs vendored inside the container image.

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
