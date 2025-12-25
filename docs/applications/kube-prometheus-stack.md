---
title: "kube-prometheus-stack"
description: "Complete monitoring stack with Prometheus, Grafana, and AlertManager"
---

# kube-prometheus-stack

The kube-prometheus-stack is a comprehensive monitoring solution that includes Prometheus, Grafana, AlertManager, and various exporters for Kubernetes cluster monitoring.

## Overview

- **Namespace:** `default`
- **Helm Chart:** `prometheus-community/kube-prometheus-stack`
- **Chart Version:** `80.6.0`
- **App Version:** `v0.87.1`
- **Deployment:** Managed by ArgoCD
- **Sync Wave:** `-15` (deploys after UniFi Poller, before cert-manager)

## Components

### Prometheus

**Purpose:** Time-series database for metrics collection and storage

- **Version:** v3.7.3
- **Replicas:** 1
- **Storage:** 50Gi persistent volume (Synology iSCSI)
- **Retention:** Configured for long-term metrics storage
- **Scrape Interval:** Varies by target (default 30s)

**Service Endpoints:**
- Internal: `kube-prometheus-stack-prometheus.default:9090`
- Prometheus UI: `http://kube-prometheus-stack-prometheus.default:9090`

### Grafana

**Purpose:** Metrics visualization and dashboarding

- **Replicas:** 1
- **Authentication:** Admin credentials stored in secret
- **Datasource:** Pre-configured Prometheus datasource
- **Dashboards:** Comprehensive Kubernetes monitoring dashboards included

**Service Endpoint:**
- Internal: `kube-prometheus-stack-grafana.default:80`

### AlertManager

**Purpose:** Alert routing and notification management

- **Version:** Included with Prometheus Operator
- **Replicas:** 1
- **Configuration:** Managed via PrometheusRule CRDs

**Service Endpoint:**
- Internal: `kube-prometheus-stack-alertmanager.default:9093`

### Additional Components

**Prometheus Operator:**
- Manages Prometheus, AlertManager, and related resources
- Handles PrometheusRule and ServiceMonitor CRDs

**kube-state-metrics:**
- Exposes Kubernetes object state as Prometheus metrics
- Monitors deployments, pods, nodes, and other K8s resources

**Node Exporter (DaemonSet):**
- Runs on all 5 Raspberry Pi nodes
- Collects hardware and OS metrics
- CPU, memory, disk, network statistics

## Storage Configuration

### Prometheus Data

**Persistent Volume:**
```yaml
storageSpec:
  volumeClaimTemplate:
    spec:
      storageClassName: synology-iscsi-retain
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 50Gi
```

**PVC Name:** `prometheus-kube-prometheus-stack-prometheus-db-prometheus-kube-prometheus-stack-prometheus-0`

**Status:** Bound to Synology NAS via iSCSI
**Retention Policy:** Retained on deletion (critical metrics data)

## Prometheus Scrape Targets

### Infrastructure Targets

```yaml
# UniFi Network Monitoring
- job_name: 'unpoller'
  targets: ['unifi-poller.unipoller:9130']
  scrape_interval: 20s

# Kubernetes Metrics
- kubelet (all nodes)
- kube-apiserver
- kube-controller-manager
- kube-scheduler
- etcd
- coredns

# Node Metrics
- node-exporter (DaemonSet on all 5 Pi nodes)

# Application Metrics
- kube-state-metrics
```

### Custom Scrape Configurations

Additional scrape configs can be added via `additionalScrapeConfigs` in the values file.

## Resource Allocation

### Prometheus

```yaml
resources:
  requests:
    cpu: 500m
    memory: 2Gi
  limits:
    cpu: 1000m
    memory: 4Gi
```

### Grafana

```yaml
resources:
  requests:
    cpu: 100m
    memory: 128Mi
  limits:
    cpu: 200m
    memory: 256Mi
```

### Node Exporter (per node)

```yaml
resources:
  requests:
    cpu: 100m
    memory: 64Mi
  limits:
    cpu: 200m
    memory: 128Mi
```

## Deployment via ArgoCD

The stack is deployed using GitOps through ArgoCD with a multi-source configuration:

**Application Manifest:** `manifests/applications/kube-prometheus-stack.yaml`

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: kube-prometheus-stack
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "-15"
spec:
  project: infrastructure
  sources:
    - repoURL: https://prometheus-community.github.io/helm-charts
      chart: kube-prometheus-stack
      targetRevision: 80.6.0
      helm:
        valueFiles:
          - $values/manifests/base/kube-prometheus-stack/values.yaml
    - repoURL: git@github.com:imcbeth/homelab.git
      path: manifests/base/kube-prometheus-stack
      targetRevision: HEAD
      ref: values
  destination:
    server: https://kubernetes.default.svc
    namespace: default
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

**Key Features:**
- **Multi-source:** Combines Helm chart from upstream with local values
- **ServerSideApply:** Required for large CRD-heavy charts
- **Auto-sync:** Automatically deploys configuration changes from git

## Grafana Dashboards

### Pre-installed Dashboards

The stack includes numerous dashboards for comprehensive monitoring:

**Cluster Monitoring:**
- Kubernetes Cluster Overview
- Node Resource Usage
- Namespace Resource Usage
- Pod Resource Usage

**Component Monitoring:**
- etcd Metrics
- API Server Performance
- Controller Manager Metrics
- Scheduler Metrics
- CoreDNS Metrics

**Infrastructure:**
- Node Exporter Full
- Persistent Volumes Usage
- Network I/O Pressure

**Application:**
- Deployment Status
- StatefulSet Status
- DaemonSet Status

### Custom Dashboards

Additional dashboards can be added via:
1. Grafana UI (exported as JSON)
2. ConfigMaps with dashboard JSON
3. Grafana dashboard provisioning

## AlertManager Configuration

### Alert Rules

PrometheusRule CRDs define alerting rules:

**Default Rule Groups:**
- Node health alerts
- Pod crash alerts
- Resource utilization warnings
- Persistent volume alerts
- API server alerts

### Notification Channels

Configure notification channels in AlertManager config:
- Slack
- Email
- PagerDuty
- Discord
- Webhook

## Monitoring the Raspberry Pi Cluster

### Node-Specific Metrics

With 5 Raspberry Pi 5 nodes, monitor:

**Hardware:**
- CPU temperature (important for Pi thermal management)
- CPU throttling events
- Memory pressure
- NVMe SSD health and I/O
- Network interface statistics

**Resource Usage:**
- Per-node CPU utilization
- Memory usage across nodes
- Disk space on NVMe drives
- Pod distribution across nodes

### Example Queries

**Node CPU Usage:**
```promql
100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)
```

**Node Memory Usage:**
```promql
(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100
```

**Node Temperature:**
```promql
node_hwmon_temp_celsius
```

**Pod Count per Node:**
```promql
count by (node) (kube_pod_info)
```

## Accessing Services

### Prometheus UI

**Internal Access:**
```bash
kubectl port-forward -n default svc/kube-prometheus-stack-prometheus 9090:9090
```
Then open: `http://localhost:9090`

### Grafana UI

**Internal Access:**
```bash
kubectl port-forward -n default svc/kube-prometheus-stack-grafana 3000:80
```
Then open: `http://localhost:3000`

**Default Credentials:**
- Username: `admin`
- Password: Stored in secret `kube-prometheus-stack-grafana`

**Retrieve Password:**
```bash
kubectl get secret kube-prometheus-stack-grafana -n default \
  -o jsonpath="{.data.admin-password}" | base64 -d
```

### AlertManager UI

**Internal Access:**
```bash
kubectl port-forward -n default svc/kube-prometheus-stack-alertmanager 9093:9093
```
Then open: `http://localhost:9093`

## Troubleshooting

### Check Component Status

```bash
# All monitoring pods
kubectl get pods -n default | grep prometheus

# Prometheus status
kubectl get prometheus -n default

# ServiceMonitors
kubectl get servicemonitor -n default

# PrometheusRules
kubectl get prometheusrule -n default
```

### View Prometheus Logs

```bash
kubectl logs -n default prometheus-kube-prometheus-stack-prometheus-0 -c prometheus
```

### View Grafana Logs

```bash
kubectl logs -n default deployment/kube-prometheus-stack-grafana
```

### Common Issues

**Prometheus Pod Pending:**
- Check PVC status: `kubectl get pvc -n default`
- Verify Synology CSI driver is running
- Ensure storage class exists

**Grafana Can't Connect to Prometheus:**
- Verify Prometheus service is running
- Check datasource configuration in Grafana

**No Metrics from Node Exporter:**
- Verify DaemonSet is running on all nodes
- Check ServiceMonitor configuration
- Review Prometheus targets page

**High Memory Usage:**
- Review retention settings
- Check scrape interval configuration
- Consider reducing metric cardinality

## Updating the Stack

### Helm Chart Updates

To update to a newer version:

1. Update `targetRevision` in `manifests/applications/kube-prometheus-stack.yaml`
2. Review upstream CHANGELOG for breaking changes
3. Test in a non-production environment if possible
4. Commit and push changes
5. ArgoCD will automatically deploy

### Configuration Changes

To modify stack configuration:

1. Edit `manifests/base/kube-prometheus-stack/values.yaml`
2. Commit and push changes
3. ArgoCD will sync and apply changes

**Note:** Some changes may require pod restarts.

## Migration History

**Date:** 2025-12-25

kube-prometheus-stack was migrated from Helm to ArgoCD GitOps management:

**Changes:**
- Migrated from manual Helm install to ArgoCD-managed
- Preserved existing 50Gi Prometheus PVC (data retained)
- Added ServerSideApply for better CRD handling
- Values file now managed in git
- Auto-sync enabled for automatic updates
- Multi-source configuration for flexibility

**Migration Steps:**
1. Backed up Helm values
2. Uninstalled Helm release (preserved PVCs)
3. Created ArgoCD Application manifest
4. Deployed via ArgoCD
5. Verified all components and data intact

## Performance Considerations

### Raspberry Pi Cluster Optimization

**Resource Limits:**
- Set appropriate CPU/memory limits for Pi constraints
- Monitor for resource contention
- Adjust scrape intervals if needed

**Storage:**
- 50Gi provides adequate retention for homelab
- Monitor disk usage growth
- Consider compression and retention policies

**Cardinality:**
- Be mindful of high-cardinality metrics
- Use recording rules for expensive queries
- Regularly review active series count

## Related Documentation

- [UniFi Poller](./unipoller.md)
- [Monitoring Overview](../monitoring/overview.md)
- [ArgoCD](./argocd.md)
- [Storage Configuration](../storage/synology-csi.md)
