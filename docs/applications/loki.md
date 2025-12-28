---
title: "Loki + Promtail"
description: "Centralized log aggregation with Grafana Loki and Promtail"
---

# Loki + Promtail

Grafana Loki with Promtail provides centralized log aggregation and querying for all Kubernetes pods across the 5-node Raspberry Pi cluster.

## Overview

**Loki:**

- **Namespace:** `loki`
- **Helm Chart:** `grafana/loki`
- **Chart Version:** `6.49.0`
- **Deployment Mode:** SingleBinary (monolithic)
- **Deployment:** Managed by ArgoCD
- **Sync Wave:** `-12` (after kube-prometheus-stack -15, before cert-manager -10)

**Promtail:**

- **Namespace:** `loki`
- **Helm Chart:** `grafana/promtail`
- **Chart Version:** `6.16.6`
- **Deployment:** DaemonSet (one pod per node)
- **Sync Wave:** `-11` (after Loki -12)

## Architecture

```
┌─────────────────────────────────────────┐
│  Promtail DaemonSet (5 pods)            │
│  - One pod per Pi node                  │
│  - Collects logs from /var/log/pods/    │
│  - 50m/100m CPU, 64Mi/128Mi memory each │
└────────────────┬────────────────────────┘
                 ↓
┌─────────────────────────────────────────┐
│  Loki SingleBinary (1 pod)              │
│  - Storage: 20Gi PVC on Synology        │
│  - Retention: 7 days (168h)             │
│  - 200m/500m CPU, 384Mi/768Mi memory    │
└────────────────┬────────────────────────┘
                 ↓
┌─────────────────────────────────────────┐
│  Grafana (auto-discovered datasource)   │
│  - Query logs via LogQL                 │
│  - Dashboards and exploration           │
└─────────────────────────────────────────┘
```

## Components

### Loki SingleBinary

**Purpose:** Centralized log storage, querying, and compaction

- **Replicas:** 1
- **Storage:** 20Gi PVC on `synology-iscsi-retain`
- **Retention:** 7 days (168h) with automatic compaction
- **Schema:** v13 (TSDB store with filesystem backend)
- **Resources:**
  - Requests: 200m CPU, 384Mi memory
  - Limits: 500m CPU, 768Mi memory

**Service Endpoints:**

- Internal: `loki.loki.svc.cluster.local:3100`
- Push API: `http://loki.loki.svc.cluster.local:3100/loki/api/v1/push`
- Query API: `http://loki.loki.svc.cluster.local:3100/loki/api/v1/query`

**Key Features:**

- **TSDB Index:** Modern time-series database index for efficient queries
- **Compaction:** Runs every 10 minutes to reduce storage usage
- **Retention:** Automatically deletes logs older than 7 days
- **Filesystem Storage:** Uses PVC (no object storage required)

### Promtail DaemonSet

**Purpose:** Log collection agent running on all nodes

- **Replicas:** 5 (one DaemonSet pod per node, including control-plane)
- **Host Access:** `hostPID: true`, `hostNetwork: false`
- **Log Sources:** `/var/log/pods/`, `/var/log/containers/`
- **Tolerations:** Configured to run on control-plane node
- **Resources per pod:**
  - Requests: 50m CPU, 64Mi memory
  - Limits: 100m CPU, 128Mi memory
- **Metrics:** ServiceMonitor enabled for Prometheus scraping

**Total Resource Impact:**

- CPU Requests: 450m total (Loki 200m + 5 × Promtail 50m)
- Memory Requests: 704Mi total (Loki 384Mi + 5 × Promtail 64Mi)
- CPU Limits: 1000m total (Loki 500m + 5 × Promtail 100m)
- Memory Limits: 1.6Gi total (Loki 768Mi + 5 × Promtail 128Mi)

**Log Labeling:**
Promtail automatically adds these labels to all logs:

- `namespace` - Kubernetes namespace
- `pod` - Pod name
- `container` - Container name
- `node` - Node name (useful for Pi cluster debugging)

**Control-Plane Scheduling:**
Promtail includes a toleration to run on the control-plane node:

```yaml
tolerations:
  - key: node-role.kubernetes.io/control-plane
    operator: Exists
    effect: NoSchedule
```

This enables log collection from critical control plane components:

- kube-apiserver
- kube-controller-manager
- kube-scheduler
- etcd
- CoreDNS

**Important Notes:**

- Uses `hostNetwork: false` to avoid Calico CNI routing issues
- Learned from control plane monitoring troubleshooting
- Runs on ALL 5 nodes (4 workers + 1 control-plane)

## Storage

### PVC Configuration

- **Size:** 20Gi
- **Storage Class:** `synology-iscsi-retain`
- **Access Mode:** ReadWriteOnce
- **Backend:** Synology DS925+ NAS via iSCSI

### Storage Calculation

Expected usage for the 5-node cluster:

- ~250 pods total (5 nodes × ~50 pods)
- ~1.8 GB/day compressed logs
- 7-day retention = ~12.6 GB
- 20Gi provides ~50% buffer for growth

### Expanding Storage

If storage fills up, you can expand the PVC online:

```bash
# Edit PVC to increase size
kubectl edit pvc loki-chunks-loki-0 -n loki

# Change spec.resources.requests.storage to new size
# Synology CSI supports online expansion
```

## Retention Configuration

Loki is configured with automatic log retention:

```yaml
loki:
  limits_config:
    retention_period: 168h  # 7 days
  compactor:
    retention_enabled: true
    compaction_interval: 10m
```

**How it works:**

1. Compactor runs every 10 minutes
2. Identifies log chunks older than 7 days
3. Automatically deletes expired chunks
4. Reduces storage usage and improves query performance

**Adjusting Retention:**
To change retention period, edit `manifests/base/loki/values.yaml`:

```yaml
limits_config:
  retention_period: 120h  # 5 days (example)
```

## Grafana Integration

### Datasource Configuration

Loki datasource is automatically discovered by Grafana via ConfigMap:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: loki-grafana-datasource
  namespace: loki
  labels:
    grafana_datasource: "1"  # Auto-discovery label
```

The Grafana sidecar automatically:

1. Watches for ConfigMaps with label `grafana_datasource: "1"`
2. Loads datasource configuration
3. Makes Loki available in Grafana Explore and dashboards

**No manual configuration needed!**

### Accessing Grafana

```bash
# Port-forward to Grafana
kubectl port-forward -n default svc/kube-prometheus-stack-grafana 3000:80

# Open browser
open http://localhost:3000

# Login credentials
username: admin
password: $(kubectl get secret kube-prometheus-stack-grafana -n default \
  -o jsonpath="{.data.admin-password}" | base64 -d)
```

### Using Loki in Grafana

1. Navigate to **Explore** (compass icon)
2. Select **Loki** from datasource dropdown
3. Enter LogQL query
4. Click **Run query**

## LogQL Query Examples

### Basic Queries

```logql
# All logs from default namespace
{namespace="default"}

# All logs from specific pod
{pod="loki-0"}

# All logs from specific node
{node="node04"}

# All logs from Loki namespace
{namespace="loki"}
```

### Filtering Logs

```logql
# Filter for errors in default namespace
{namespace="default"} |= "error"

# Filter for errors OR fatal
{namespace="default"} |= "error" or "fatal"

# Exclude info logs
{namespace="default"} != "info"

# Case-insensitive search
{namespace="default"} |~ "(?i)error"
```

### Pattern Matching

```logql
# All Prometheus pods
{pod=~"prometheus.*"}

# All kube-system errors
{namespace="kube-system"} |= "error"

# Critical system errors
{namespace="kube-system"} |= "error" |= "fatal"

# Application errors (exclude system namespaces)
{namespace!~"kube-.*"} |= "error"
```

### Advanced Queries

```logql
# Count error rate per minute
sum(rate({namespace="default"} |= "error" [1m])) by (pod)

# Top 10 pods by log volume
topk(10, sum(rate({namespace=~".+"} [5m])) by (pod))

# Logs from last hour
{namespace="default"} |= "error" [1h]
```

## Common Use Cases

### Troubleshooting Pod Crashes

```logql
# View logs from crashed pod
{namespace="default", pod="myapp-xyz"}

# Find errors before crash
{namespace="default", pod="myapp-xyz"} |= "error" or "fatal" or "panic"
```

### Monitoring Deployments

```logql
# Watch logs during deployment
{namespace="default", pod=~"myapp-.*"} |= "Started" or "Ready" or "Error"
```

### Debugging Network Issues

```logql
# Find connection errors
{namespace=~".+"} |= "connection refused" or "timeout" or "network"
```

### Checking Control Plane Health

```logql
# API server errors
{namespace="kube-system", pod=~"kube-apiserver.*"} |= "error"

# CoreDNS issues
{namespace="kube-system", pod=~"coredns.*"} |= "error" or "timeout"

# Node-level issues
{namespace="kube-system"} |= "node" |= "not ready" or "evicted"
```

## Grafana Dashboards

### Community Dashboards

Import these dashboards in Grafana (Dashboard → Import):

| Dashboard ID | Name | Description |
|--------------|------|-------------|
| 12611 | Loki Dashboard | Quick search and log volume overview |
| 13639 | Logs / App | Application log analysis |
| 13407 | Kubernetes Logs | Kubernetes-specific log patterns |

### Custom Dashboard Example

Create a custom dashboard to monitor errors across namespaces:

1. Create new dashboard
2. Add panel with query:

   ```logql
   sum(rate({namespace=~".+"} |= "error" [5m])) by (namespace)
   ```

3. Visualization: Time series or Bar chart
4. Set alert threshold for error rate > X/min

## Troubleshooting

### No Logs Appearing

**Check Promtail pods are running:**

```bash
kubectl get pods -n loki -l app.kubernetes.io/name=promtail
# Expect: 5 pods (one per node)
```

**Check Promtail logs:**

```bash
kubectl logs -n loki -l app.kubernetes.io/name=promtail --tail=50
# Look for connection errors or scrape failures
```

**Verify Loki service:**

```bash
kubectl get svc -n loki loki
# Should show ClusterIP on port 3100
```

### Loki Pod Crashes or OOM

**Check memory usage:**

```bash
kubectl top pod -n loki loki-0
```

**Increase memory limits if needed:**
Edit `manifests/base/loki/values.yaml`:

```yaml
singleBinary:
  resources:
    limits:
      memory: 1Gi  # Increase from 768Mi
```

**Check query complexity:**

- Avoid queries with very long time ranges
- Use `max_query_series` limit to prevent expensive queries

### Slow Queries

**Check compaction status:**

```bash
kubectl logs -n loki loki-0 -c loki | grep compaction
```

**Reduce retention if storage is filling:**

```yaml
limits_config:
  retention_period: 120h  # Reduce to 5 days
```

### Storage Full

**Check PVC usage:**

```bash
kubectl exec -n loki loki-0 -c loki -- df -h /var/loki
```

**Expand PVC:**

```bash
kubectl edit pvc loki-chunks-loki-0 -n loki
# Increase spec.resources.requests.storage
```

**Or reduce retention:**

```yaml
limits_config:
  retention_period: 72h  # 3 days
```

## Monitoring Loki

ServiceMonitors are **enabled** for both Loki and Promtail, allowing Prometheus to scrape metrics automatically.

### Prometheus Integration

**ServiceMonitor Configuration:**

```yaml
# Loki
monitoring:
  serviceMonitor:
    enabled: true
    labels:
      release: kube-prometheus-stack

# Promtail
serviceMonitor:
  enabled: true
  labels:
    release: kube-prometheus-stack
```

**Verify ServiceMonitors:**

```bash
kubectl get servicemonitor -n loki
# Expected: loki and promtail ServiceMonitors
```

**Check Prometheus Targets:**

```bash
# Port-forward to Prometheus
kubectl port-forward -n default svc/kube-prometheus-stack-prometheus 9090:9090

# Navigate to: http://localhost:9090/targets
# Look for: serviceMonitor/loki/loki and serviceMonitor/loki/promtail
```

### Key Metrics to Watch

Loki and Promtail metrics are available in Prometheus:

**Loki Metrics:**

```promql
# Ingestion rate (logs/second)
sum(rate(loki_distributor_lines_received_total[1m]))

# Query performance (99th percentile)
histogram_quantile(0.99, rate(loki_request_duration_seconds_bucket[5m]))

# Active log streams
loki_ingester_streams

# Storage usage
loki_store_chunk_entries

# Compaction status
loki_compactor_compaction_interval_seconds
```

**Promtail Metrics (per pod × 5):**

```promql
# Logs sent to Loki (rate)
rate(promtail_sent_entries_total[5m])

# Bytes read from log files
rate(promtail_read_bytes_total[5m])

# Active scrape targets (should show ~250 pods)
promtail_targets_active_total

# Files being watched
promtail_files_active_total
```

### Health Checks

**Check Loki readiness:**

```bash
kubectl exec -n loki loki-0 -c loki -- wget -qO- http://localhost:3100/ready
# Should return: "ready"
```

**Check Loki metrics endpoint:**

```bash
kubectl exec -n loki loki-0 -c loki -- wget -qO- http://localhost:3100/metrics | head
```

## Log-Based Alerting

Loki includes a **Ruler** component that evaluates LogQL expressions and sends alerts to AlertManager, enabling log-based monitoring and proactive incident detection.

### Loki Ruler Overview

**Deployment:**

- **Enabled:** Yes (as of 2025-12-28)
- **Mode:** Deployment (1 replica)
- **Namespace:** `loki`
- **Resources:**
  - Requests: 50m CPU, 128Mi memory
  - Limits: 200m CPU, 256Mi memory
- **Persistence:** 1Gi PVC on `synology-iscsi-retain`

**Purpose:** Evaluates log-based alerting rules and sends alerts to AlertManager for notification routing (email, Slack, etc.)

### AlertManager Integration

The Loki Ruler is configured to send alerts to the kube-prometheus-stack AlertManager:

```yaml
loki:
  rulerConfig:
    alertmanager_url: http://kube-prometheus-stack-alertmanager.default.svc.cluster.local:9093
    enable_api: true
    enable_alertmanager_v2: true
```

**Alert Flow:**

```
Loki Logs → Ruler (LogQL evaluation) → AlertManager → Email/Slack/etc.
```

### Alert Rules Configuration

Alert rules are defined using PrometheusRule CRDs with the following labels for Prometheus Operator discovery:

```yaml
metadata:
  namespace: loki
  labels:
    prometheus: kube-prometheus
    role: alert-rules
    app: loki
```

**Configuration File:** `manifests/base/loki/loki-alerts.yaml` in homelab repository

### Implemented Alert Rules

The following 11 alert rules are deployed across 4 categories:

#### 1. Log Errors (Group: loki.log_errors)

**HighErrorLogRate:**

- **Expression:** Error log rate > 1/sec for 5 minutes
- **Severity:** Warning
- **Pattern:** Matches "error", "err", "fatal", "exception", "panic", "fail" (case-insensitive)
- **Purpose:** Detect elevated error rates across all namespaces

**CriticalErrorLogs:**

- **Expression:** Critical error rate > 0.1/sec for 2 minutes
- **Severity:** Critical
- **Pattern:** Matches "critical", "fatal", "panic", "emergency" (case-insensitive)
- **Purpose:** Immediate notification for severe errors

#### 2. Pod Failures (Group: loki.pod_failures)

**CrashLoopBackOffDetected:**

- **Expression:** CrashLoopBackOff messages detected for 5 minutes
- **Severity:** Critical
- **Pattern:** Matches "back-off restarting failed container", "crashloopbackoff"
- **Purpose:** Alert on pods unable to start successfully

**OOMKilledDetected:**

- **Expression:** Out-of-memory kill events detected for 1 minute
- **Severity:** Critical
- **Pattern:** Matches "oomkilled", "out of memory", "memory cgroup out of memory"
- **Purpose:** Identify pods exceeding memory limits

**PersistentPodRestarts:**

- **Expression:** More than 5 restart messages in 15 minutes
- **Severity:** Warning
- **Pattern:** Matches "restarting container", "restart count"
- **Purpose:** Detect unstable pods with frequent restarts

#### 3. Application Errors (Group: loki.application_errors)

**HighHTTP5xxErrorRate:**

- **Expression:** HTTP 5xx error rate > 1/sec for 5 minutes
- **Severity:** Warning
- **Pattern:** Matches "status[= :]5[0-9]{2}", "http.*5[0-9]{2}"
- **Purpose:** Monitor application-level server errors

**DatabaseConnectionErrors:**

- **Expression:** Database error rate > 0.5/sec for 5 minutes
- **Severity:** Warning
- **Pattern:** Matches "connection.*refused", "connection.*timeout", "database.*error", "sql.*error"
- **Purpose:** Detect database connectivity issues

#### 4. Security Events (Group: loki.security_events)

**AuthenticationFailures:**

- **Expression:** Authentication failure rate > 5/sec for 5 minutes
- **Severity:** Warning
- **Pattern:** Matches "authentication.*failed", "auth.*failed", "unauthorized", "invalid.*credentials"
- **Purpose:** Detect potential brute-force or misconfiguration

**SuspiciousActivity:**

- **Expression:** Any suspicious keywords detected for 2 minutes
- **Severity:** Critical
- **Pattern:** Matches "attack", "intrusion", "exploit", "malicious", "suspicious"
- **Purpose:** Early detection of potential security incidents

### Verifying Alerting Setup

**Check Ruler Pod:**

```bash
kubectl get pods -n loki -l app.kubernetes.io/component=ruler
# Expected: 1 running pod
```

**Check Ruler Logs:**

```bash
kubectl logs -n loki -l app.kubernetes.io/component=ruler --tail=50
# Look for "ruler started" and "evaluating rules"
```

**Verify PrometheusRule Created:**

```bash
kubectl get prometheusrule -n loki loki-log-based-alerts
# Should show the alert rules resource
```

**Check Alert Rules in Prometheus:**

```bash
# Port-forward to Prometheus
kubectl port-forward -n default svc/kube-prometheus-stack-prometheus 9090:9090

# Navigate to: http://localhost:9090/alerts
# Look for alerts with prefix "loki" or check "loki.log_errors" group
```

**Verify AlertManager Integration:**

```bash
# Port-forward to AlertManager
kubectl port-forward -n default svc/kube-prometheus-stack-alertmanager 9093:9093

# Navigate to: http://localhost:9093
# Check for any firing Loki alerts
```

### Testing Alert Rules

**Trigger a Test Alert (HighErrorLogRate):**

```bash
# Generate error logs in a test pod
kubectl run test-error-logs --image=busybox --restart=Never -- \
  sh -c 'for i in $(seq 1 100); do echo "ERROR: Test error message $i"; sleep 1; done'

# Wait 5-6 minutes for alert to fire
# Check AlertManager UI for the alert
```

**Clean Up Test Pod:**

```bash
kubectl delete pod test-error-logs
```

### Tuning Alert Thresholds

Alert thresholds can be adjusted in `manifests/base/loki/loki-alerts.yaml`:

**Example - Reduce HighErrorLogRate sensitivity:**

```yaml
- alert: HighErrorLogRate
  expr: |
    sum by (namespace, pod) (
      rate({namespace=~".+"} |~ "(?i)(error|err|fatal|exception|panic|fail)" [5m])
    ) > 5  # Changed from 1 to 5 errors/sec
  for: 10m  # Changed from 5m to 10m
```

After editing, commit and push changes - ArgoCD will auto-sync the new rules.

### Monitoring Ruler Performance

**Ruler Metrics (via Prometheus):**

```promql
# Rules evaluated per second
rate(loki_prometheus_rule_evaluations_total[5m])

# Rule evaluation duration
histogram_quantile(0.99, rate(loki_prometheus_rule_evaluation_duration_seconds_bucket[5m]))

# Failed rule evaluations
rate(loki_prometheus_rule_evaluation_failures_total[5m])
```

**Resource Usage:**

```bash
kubectl top pod -n loki -l app.kubernetes.io/component=ruler
```

### Alert Notification Channels

Alerts are routed through AlertManager, which supports:

- **Email:** Configured for homelab (Gmail SMTP)
- **Slack:** Can be configured for team notifications
- **Discord:** Alternative messaging platform
- **Webhook:** Custom integrations
- **PagerDuty:** For production on-call rotations

**Email Configuration:** See `manifests/base/kube-prometheus-stack/alertmanager-secret.yaml` in homelab repository

### Troubleshooting Alerts

**Alert Not Firing:**

1. Check if logs match the pattern:

   ```logql
   {namespace=~".+"} |~ "(?i)(error|err|fatal|exception|panic|fail)"
   ```

2. Verify threshold is exceeded:

   ```logql
   sum by (namespace, pod) (
     rate({namespace=~".+"} |~ "(?i)(error|err|fatal|exception|panic|fail)" [5m])
   )
   ```

3. Check Ruler logs for evaluation errors

**Too Many False Positives:**

- Adjust pattern to be more specific
- Increase threshold or evaluation duration
- Add exclusions for known noisy patterns

**Alert Not Reaching Email/Slack:**

- Verify AlertManager configuration
- Check AlertManager logs for routing errors
- Test AlertManager notification channels

### Best Practices

**When Creating Custom Alert Rules:**

1. **Test LogQL queries in Grafana Explore** before creating alert rules
2. **Use appropriate `for` duration** to avoid flapping alerts
3. **Set meaningful annotations** with runbook links
4. **Include helpful context** in alert descriptions (namespace, pod, error rate)
5. **Use label-based routing** in AlertManager for different severities
6. **Monitor alert evaluation performance** to avoid overloading Ruler

**Alert Naming Convention:**

- Use descriptive names: `HighErrorLogRate`, not `Alert1`
- Include severity in name when appropriate: `CriticalErrorLogs`
- Group related alerts with common prefix

### Future Enhancements

Potential improvements for log-based alerting:

- **SLO-Based Alerting:** Define error budget and alert when budget is exhausted
- **Anomaly Detection:** ML-based detection of unusual log patterns
- **Log Correlation:** Combine log patterns with metric thresholds
- **Dynamic Thresholds:** Adjust thresholds based on time of day or traffic volume
- **Custom Runbooks:** Detailed troubleshooting guides for each alert type

## Configuration Files

### ArgoCD Applications

**Loki:**

- Path: `manifests/applications/loki.yaml`
- Sync Wave: `-12`
- Destination: `loki` namespace

**Promtail:**

- Path: `manifests/applications/promtail.yaml`
- Sync Wave: `-11`
- Destination: `loki` namespace

### Helm Values

**Loki Configuration:**

- Path: `manifests/base/loki/values.yaml`
- Key settings: deployment mode, storage, retention

**Promtail Configuration:**

- Path: `manifests/base/promtail/values.yaml`
- Key settings: resources, scrape config, labels

**Grafana Datasource:**

- Path: `manifests/base/loki/loki-datasource.yaml`
- Auto-discovered by Grafana sidecar

## Performance Tuning

### For Raspberry Pi Cluster

**Current settings are optimized for:**

- 5 Raspberry Pi 5 nodes (16GB RAM each)
- ~250 pods total
- Moderate log volume (~1.8GB/day)

**If experiencing performance issues:**

1. **Reduce scrape frequency** (less CPU on nodes):

   ```yaml
   # In promtail values.yaml, not currently set (uses default)
   ```

2. **Reduce query parallelism** (less memory in Loki):

   ```yaml
   limits_config:
     max_query_parallelism: 16  # Default: 32
   ```

3. **Increase Loki memory** (better query performance):

   ```yaml
   singleBinary:
     resources:
       limits:
         memory: 1Gi  # From 768Mi
   ```

## Security Considerations

### Authentication

Loki is configured with `auth_enabled: false` for simplicity in homelab environment.

For multi-tenant or production use, enable authentication:

```yaml
loki:
  auth_enabled: true
```

### Network Policies

Consider adding NetworkPolicy to restrict access:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: loki-allow-promtail
  namespace: loki
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: loki
  ingress:
    - from:
      - podSelector:
          matchLabels:
            app.kubernetes.io/name: promtail
      ports:
        - port: 3100
```

## Upgrading

### Loki Chart Upgrades

```bash
# Update chart version in manifests/applications/loki.yaml
targetRevision: 6.50.0  # Example new version

# Commit and push (ArgoCD will auto-sync)
git commit -am "chore: Upgrade Loki to 6.50.0"
git push
```

**Important:** Check Loki [release notes](https://github.com/grafana/loki/releases) for breaking changes.

### Promtail Chart Upgrades

```bash
# Update chart version in manifests/applications/promtail.yaml
targetRevision: 6.17.0  # Example new version

# Commit and push
git commit -am "chore: Upgrade Promtail to 6.17.0"
git push
```

## Related Documentation

- [Monitoring Overview](../monitoring/overview.md)
- [kube-prometheus-stack](kube-prometheus-stack.md)
- [Storage Configuration](../storage/synology-csi.md)
- [Troubleshooting Monitoring](../troubleshooting/monitoring.md)

## External Resources

- [Grafana Loki Documentation](https://grafana.com/docs/loki/latest/)
- [LogQL Query Language](https://grafana.com/docs/loki/latest/logql/)
- [Promtail Configuration](https://grafana.com/docs/loki/latest/clients/promtail/configuration/)
- [Loki Helm Chart](https://github.com/grafana/loki/tree/main/production/helm/loki)
