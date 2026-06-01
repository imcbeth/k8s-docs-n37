---
title: "Tempo"
description: "Distributed tracing backend for the observability stack"
---

# Tempo

Grafana Tempo is the distributed tracing backend for the homelab cluster. It receives traces via OTLP from instrumented applications (primarily Alloy), stores them on a local iSCSI volume, and exposes them through a Grafana datasource for trace visualization.

## Overview

| Property | Value |
|----------|-------|
| **Namespace** | `tempo` |
| **Chart** | `grafana/tempo` v1.24.4 |
| **App Version** | `v2.9.0` |
| **ArgoCD App** | `tempo` (project: `infrastructure`, wave: `-11`) |
| **Mode** | Monolithic |
| **Storage** | 10Gi iSCSI PVC (`synology-iscsi-delete`) |
| **Trace Retention** | 30 days |

## Architecture

```
Instrumented apps (Alloy OTLP exporter)
        │
        ▼ OTLP gRPC :4317 / HTTP :4318
┌───────────────────────────────┐
│  Tempo (monolithic mode)      │
│  - Receiver: OTLP             │
│  - Backend: local filesystem  │
│  - WAL: /var/tempo/wal        │
│  - Traces: /var/tempo/traces  │
└───────────────────────────────┘
        │
        ▼ :3100 (Tempo query API)
Grafana (tempo datasource)
        │
        ├── Trace → Logs correlation (Loki, by trace ID)
        └── Trace → Metrics correlation (Prometheus, by service.name)
```

## Deployment Configuration

### ArgoCD Application

**Location:** `manifests/applications/tempo.yaml`

The application uses three sources:

1. **Helm chart** — `grafana/tempo` v1.24.4 with `values.yaml`
2. **Values ref** — homelab repo as ref source for value files
3. **Additional manifests** — `manifests/base/tempo/` (Grafana datasource ConfigMap)

```yaml
ignoreDifferences:
  - group: apps
    kind: StatefulSet
    jqPathExpressions:
      - .spec.volumeClaimTemplates
      - .status
```

The `ignoreDifferences` on `volumeClaimTemplates` prevents ArgoCD from trying to update an immutable StatefulSet field, which would otherwise cause a sync error after initial PVC creation.

### Key Helm Values

**Location:** `manifests/base/tempo/values.yaml`

```yaml
tempo:
  reportingEnabled: false
  receivers:
    otlp:
      protocols:
        grpc:
          endpoint: "0.0.0.0:4317"
        http:
          endpoint: "0.0.0.0:4318"
  storage:
    trace:
      backend: local
      local:
        path: /var/tempo/traces
      wal:
        path: /var/tempo/wal
  retention: 720h  # 30 days
  resources:
    requests:
      cpu: 100m
      memory: 256Mi
    limits:
      cpu: 500m
      memory: 1Gi
  extraEnv:
    - name: GOMEMLIMIT
      value: "900MiB"

persistence:
  enabled: true
  storageClassName: synology-iscsi-delete
  size: 10Gi
```

:::warning Resources must be under `tempo:` key
The `grafana/tempo` chart only reads `resources` when nested under `tempo.resources`. A top-level `resources:` block is silently ignored — the pod starts with no requests/limits, gets flagged by Gatekeeper's require-resource-limits policy, and is rejected.

Always scope resource configuration like this:

```yaml
# CORRECT
tempo:
  resources:
    requests:
      cpu: 100m
    limits:
      memory: 1Gi

# WRONG — silently ignored
resources:
  requests:
    cpu: 100m
```

:::

### Grafana Datasource

**Location:** `manifests/base/tempo/tempo-datasource.yaml`

A ConfigMap in the `tempo` namespace with label `grafana_datasource: "1"`. The Grafana sidecar discovers it and provisions the datasource automatically. Configured with:

- **Trace → Logs** correlation via Loki (by `service.name`)
- **Trace → Metrics** correlation via Prometheus (by `service.name`)
- **Service graph** view (Prometheus datasource)
- **Node graph** visualization enabled

## Resource Usage

| Component | CPU Request | CPU Limit | Memory Request | Memory Limit |
|-----------|-------------|-----------|----------------|--------------|
| tempo | 100m | 500m | 256Mi | 1Gi |

`GOMEMLIMIT=900MiB` keeps the Go runtime below the 1Gi container limit.

## Common Operations

### Verify Traces Are Being Received

```bash
# Check Tempo is running
kubectl get pod -n tempo

# Tail Tempo logs for incoming spans
kubectl logs -n tempo statefulset/tempo --tail=50 | grep -i "span\|trace\|otlp"

# Check Prometheus metrics for ingested spans
kubectl port-forward -n default svc/kube-prometheus-stack-prometheus 9090:9090
# Query: tempo_ingester_traces_created_total
```

### Query Traces via Grafana

1. Open Grafana → **Explore**
2. Select **Tempo** datasource
3. Search by service name, trace ID, or duration

### Storage Usage

```bash
kubectl exec -n tempo statefulset/tempo -- du -sh /var/tempo/traces /var/tempo/wal
kubectl get pvc -n tempo
```

## Troubleshooting

### No Traces in Grafana

1. **Check Alloy is exporting to Tempo**: Verify Alloy config points to `tempo.tempo.svc.cluster.local:4317`

2. **Check Tempo pod is healthy**:

   ```bash
   kubectl get pod -n tempo
   kubectl logs -n tempo statefulset/tempo --tail=50
   ```

3. **Verify the datasource is provisioned**:

   ```bash
   # Grafana sidecar should have picked up the ConfigMap
   kubectl get configmap -n tempo tempo-grafana-datasource
   kubectl logs -n default deployment/kube-prometheus-stack-grafana -c grafana-sc-datasources --tail=20
   ```

### Pod Not Scheduling (iSCSI)

Tempo uses a RWO iSCSI PVC — only one node can mount it at a time. If the pod is rescheduled to a different node:

```bash
kubectl describe pod -n tempo -l app.kubernetes.io/name=tempo
# Look for: VolumeAttachment or Multi-Attach error

# Delete pod to force reschedule (ArgoCD will recreate)
kubectl delete pod -n tempo -l app.kubernetes.io/name=tempo
```

### Gatekeeper Admission Denied

If Tempo pod is rejected by Gatekeeper's resource-limits policy, the resource spec is misconfigured. Confirm resources are under `tempo.resources` in values.yaml (see warning above).

## Configuration Files

| File | Purpose |
|------|---------|
| `manifests/applications/tempo.yaml` | ArgoCD Application definition |
| `manifests/base/tempo/values.yaml` | Helm values |
| `manifests/base/tempo/tempo-datasource.yaml` | Grafana datasource ConfigMap |

## References

- [Grafana Tempo Documentation](https://grafana.com/docs/tempo/latest/)
- [Tempo Helm Chart](https://github.com/grafana/helm-charts/tree/main/charts/tempo)
- [OTLP Receiver Configuration](https://grafana.com/docs/tempo/latest/configuration/#otlp-receiver)

---

**Last Updated:** 2026-06-01
