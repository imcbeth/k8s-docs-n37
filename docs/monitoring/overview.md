---
title: "Monitoring Overview"
description: "Overview of monitoring and observability stack"
---

# Monitoring and Observability

Comprehensive monitoring setup providing complete visibility into infrastructure, applications, and network performance.

## Architecture Overview

The monitoring stack is built around the **kube-prometheus-stack**, which provides a complete observability solution for the Kubernetes cluster.

```
┌─────────────────────────────────────────────────────────┐
│              Metrics Collection Layer                    │
├─────────────────────────────────────────────────────────┤
│  • Node Exporter (all 5 Pi nodes)                       │
│  • kube-state-metrics (K8s objects)                     │
│  • UniFi Poller (network metrics)                       │
│  • Kubelet (container metrics)                          │
│  • API Server, etcd, CoreDNS                            │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│              Prometheus (Time-Series DB)                 │
├─────────────────────────────────────────────────────────┤
│  • 50Gi persistent storage (Synology iSCSI)             │
│  • 20-30s scrape intervals                              │
│  • Long-term retention                                  │
│  • Recording rules for efficiency                       │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│          Visualization & Alerting Layer                 │
├─────────────────────────────────────────────────────────┤
│  • Grafana (dashboards and visualization)               │
│  • AlertManager (alert routing)                         │
└─────────────────────────────────────────────────────────┘
```

## Current Monitoring Stack

### Core Components

#### Prometheus

**Purpose:** Central metrics collection and storage

- **Version:** v3.7.3
- **Storage:** 50Gi PVC on Synology NAS
- **Deployment:** ArgoCD-managed (sync-wave: -15)
- **Namespace:** `default`

**Capabilities:**
- Time-series metric storage
- Powerful query language (PromQL)
- Service discovery
- Alert rule evaluation

**Documentation:** [kube-prometheus-stack Guide](../applications/kube-prometheus-stack.md)

#### Grafana

**Purpose:** Metrics visualization and dashboarding

- **Pre-loaded Dashboards:** 20+ Kubernetes monitoring dashboards
- **Custom Dashboards:** Support for user-created visualizations
- **Datasources:** Pre-configured Prometheus connection
- **Authentication:** Secure admin access

**Access:**
```bash
kubectl port-forward -n default svc/kube-prometheus-stack-grafana 3000:80
```

#### AlertManager

**Purpose:** Alert aggregation and routing

- **Integration:** Prometheus alert rules
- **Routing:** Configurable notification channels
- **Deduplication:** Intelligent alert grouping
- **Silencing:** Temporary alert suppression

### Metric Exporters

#### Node Exporter

**Deployment:** DaemonSet on all 5 Raspberry Pi nodes

**Metrics Collected:**
- CPU usage and temperature
- Memory utilization
- Disk I/O and space
- Network interface statistics
- System load
- Hardware sensors

**Why It Matters:** Critical for monitoring Pi cluster health, especially temperature and throttling.

#### kube-state-metrics

**Purpose:** Kubernetes object state metrics

**Metrics Collected:**
- Pod status and resource usage
- Deployment health and replicas
- Node conditions and capacity
- PersistentVolume status
- ConfigMap and Secret counts

#### UniFi Poller

**Purpose:** Network infrastructure monitoring

- **Version:** v2.11.2
- **Deployment:** ArgoCD-managed (sync-wave: -20)
- **Namespace:** `unipoller`
- **Controller:** 10.0.1.1

**Network Metrics:**
- Device status and uptime
- Port statistics and errors
- Wireless client connections
- Bandwidth utilization
- PoE power consumption
- Signal strength and interference

**Documentation:** [UniFi Poller Guide](../applications/unipoller.md)

#### SNMP Exporter

**Purpose:** Synology NAS monitoring

- **Version:** v0.26.0
- **Deployment:** ArgoCD-managed (part of kube-prometheus-stack)
- **Namespace:** `default`
- **Target:** Synology DS925+ at 10.0.1.204

**Storage Metrics:**
- Disk health and temperature
- Volume capacity and usage
- RAID status
- iSCSI target statistics
- Network interface statistics
- System resource utilization

**Documentation:** [SNMP Exporter Guide](../applications/snmp-exporter.md)

## Metrics Collection

### Scrape Configuration

Prometheus is configured to scrape metrics from multiple sources:

| Target | Interval | Purpose |
|--------|----------|---------|
| UniFi Poller | 20s | Network metrics |
| SNMP Exporter | 30s | NAS storage metrics |
| Node Exporter | 30s | Hardware metrics |
| kubelet | 30s | Container metrics |
| API Server | 30s | Control plane |
| kube-state-metrics | 30s | K8s objects |
| CoreDNS | 30s | DNS metrics |

### Storage and Retention

**Prometheus Storage:**
- **Size:** 50Gi
- **Backend:** Synology NAS via iSCSI
- **Storage Class:** `synology-iscsi-retain`
- **Retention Policy:** Configured for long-term storage

**PVC Details:**
```bash
kubectl get pvc -n default | grep prometheus
```

## Dashboards

### Pre-Installed Grafana Dashboards

The kube-prometheus-stack includes comprehensive dashboards:

**Cluster-Level:**
- Kubernetes Cluster Overview
- Cluster Resource Usage
- Namespace Resource Usage
- Persistent Volumes

**Node-Level:**
- Node Exporter Full
- Node Resource Usage per Namespace
- Nodes Dashboard
- Node Temperature (critical for Pis!)

**Application-Level:**
- Deployment Status
- StatefulSet Status
- Pod Resource Usage
- Container Resource Usage

**Infrastructure:**
- API Server Performance
- etcd Metrics
- CoreDNS Metrics
- Scheduler Metrics

**Network:**
- Network I/O Pressure
- UniFi Network Performance (custom)

### Creating Custom Dashboards

1. Access Grafana UI
2. Create new dashboard
3. Add panels with PromQL queries
4. Save dashboard
5. Export as JSON
6. Commit to git for version control

## Alerting

### Prometheus Alert Rules

Alert rules are defined using PrometheusRule CRDs:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: example-alert
spec:
  groups:
  - name: example
    rules:
    - alert: HighPodMemory
      expr: container_memory_usage_bytes > 1e9
      for: 5m
```

### Common Alerts

**Node Alerts:**
- Node down or unreachable
- High CPU usage (&gt;80%)
- High memory usage (&gt;90%)
- Disk space low (&lt;10%)
- Node temperature critical (&gt;75°C for Pi)

**Pod Alerts:**
- Pod crash looping
- Pod restart count high
- Container OOM killed
- Pod pending too long

**Cluster Alerts:**
- API server errors
- etcd performance degradation
- Persistent volume filling up
- Excessive pod evictions

### AlertManager Configuration

**Notification Channels:**
- Slack (recommended for homelab)
- Email
- Discord
- Webhook
- PagerDuty

**Configuration:**
Edit AlertManager config in `values.yaml` and apply via ArgoCD.

## Key Metrics for Raspberry Pi Cluster

### Critical Metrics to Monitor

#### Temperature

**Why:** Raspberry Pis throttle at high temperatures

```promql
node_hwmon_temp_celsius
```

**Alert Threshold:** &gt; 70°C (warning), &gt; 75°C (critical)

#### CPU Throttling

**Why:** Indicates thermal or power issues

```promql
node_cpu_frequency_hertz / node_cpu_scaling_frequency_max_hertz < 0.9
```

#### Memory Pressure

**Why:** 16GB RAM per node can fill up quickly

```promql
(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100
```

**Alert Threshold:** &gt; 85% (warning), &gt; 90% (critical)

#### NVMe Health

**Why:** Monitor SSD wear and health

```promql
node_disk_io_time_seconds_total
node_disk_read_bytes_total
node_disk_write_bytes_total
```

#### Network Performance

**Why:** Ensure cluster communication is healthy

```promql
rate(node_network_receive_bytes_total[5m])
rate(node_network_transmit_bytes_total[5m])
```

### Cluster-Wide Metrics

#### Pod Distribution

```promql
count by (node) (kube_pod_info)
```

**Purpose:** Ensure even workload distribution

#### Resource Requests vs Limits

```promql
sum(kube_pod_container_resource_requests_cpu_cores) / sum(kube_node_status_allocatable_cpu_cores) * 100
```

**Purpose:** Monitor cluster capacity utilization

#### Storage Usage

```promql
kubelet_volume_stats_used_bytes / kubelet_volume_stats_capacity_bytes * 100
```

**Purpose:** Prevent PVC from filling up

## Access Methods

### Prometheus UI

**Port Forward:**
```bash
kubectl port-forward -n default svc/kube-prometheus-stack-prometheus 9090:9090
```

**URL:** `http://localhost:9090`

**Features:**
- PromQL query interface
- Target status page
- Alert rules viewer
- Configuration viewer

### Grafana UI

**Port Forward:**
```bash
kubectl port-forward -n default svc/kube-prometheus-stack-grafana 3000:80
```

**URL:** `http://localhost:3000`

**Login:**
```bash
# Get admin password
kubectl get secret kube-prometheus-stack-grafana -n default \
  -o jsonpath="{.data.admin-password}" | base64 -d
```

### AlertManager UI

**Port Forward:**
```bash
kubectl port-forward -n default svc/kube-prometheus-stack-alertmanager 9093:9093
```

**URL:** `http://localhost:9093`

## GitOps Management

All monitoring components are managed via ArgoCD:

**Sync Waves:**
```
-20: UniFi Poller (metrics collection)
-15: kube-prometheus-stack (monitoring stack)
```

**Auto-Sync:** Enabled with prune and self-heal

**Configuration Changes:**
1. Edit values in `homelab/manifests/base/kube-prometheus-stack/values.yaml`
2. Commit and push
3. ArgoCD automatically syncs within ~3 minutes

## Performance Tuning

### For Raspberry Pi Cluster

**Scrape Intervals:**
- Balance between metric resolution and resource usage
- 20-30s intervals are appropriate for homelab

**Retention:**
- 50Gi provides months of retention
- Adjust based on growth rate

**Cardinality:**
- Be mindful of high-cardinality metrics
- Use recording rules for expensive queries
- Regularly review series count

**Resource Limits:**
- Set appropriate limits for 16GB node memory
- Monitor Prometheus memory usage
- Adjust if OOM occurs

## Implemented Enhancements

### Recently Added

- ✅ **SNMP Monitoring for Synology NAS** (December 2025)
  - Disk health and temperature monitoring
  - Volume capacity and usage tracking
  - RAID status monitoring
  - iSCSI target statistics
  - Network interface statistics
  - Comprehensive Grafana dashboard

## Planned Enhancements

### Coming Soon

- **Blackbox Exporter**
  - HTTP/HTTPS endpoint monitoring
  - SSL certificate expiration tracking
  - Response time monitoring

- **Additional Custom Dashboards**
  - Enhanced Raspberry Pi thermal dashboard
  - Storage performance correlation dashboard

- **Alert Notification Setup**
  - Slack integration for critical alerts
  - Daily health report summaries
  - PagerDuty integration for production alerts

## Troubleshooting

### Common Issues

**Prometheus High Memory:**
- Check cardinality: `curl localhost:9090/api/v1/status/tsdb`
- Review scrape configuration
- Adjust retention settings

**Missing Metrics:**
- Verify ServiceMonitor exists
- Check Prometheus targets page
- Review pod logs

**Grafana Connection Issues:**
- Verify datasource configuration
- Check Prometheus service endpoint
- Review Grafana logs

### Useful Commands

```bash
# Check monitoring pods
kubectl get pods -n default | grep prometheus

# View Prometheus config
kubectl get prometheus -o yaml

# List all ServiceMonitors
kubectl get servicemonitor -A

# Check PrometheusRules
kubectl get prometheusrule -A

# Verify metrics endpoint
kubectl exec -n default prometheus-kube-prometheus-stack-prometheus-0 -c prometheus -- \
  wget -qO- http://TARGET:PORT/metrics | head -20
```

## Related Documentation

- [kube-prometheus-stack Application Guide](../applications/kube-prometheus-stack.md)
- [UniFi Poller Application Guide](../applications/unipoller.md)
- [Storage Configuration](../storage/synology-csi.md)
- [Troubleshooting Guide](../troubleshooting/monitoring.md)
