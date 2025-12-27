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
- **Deployment Strategy:** Recreate (prevents Multi-Attach errors with ReadWriteOnce PVC)
- **Storage:** 5Gi persistent volume (Synology iSCSI)

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
- **Network Mode:** `hostNetwork: false`, `hostPID: true`
  - Uses pod network for connectivity (avoids Calico CNI routing issues)
  - Retains host PID namespace for process metrics

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
- coredns
# Note: kube-controller-manager, kube-etcd, kube-proxy, kube-scheduler disabled
# These components bind to localhost in kubeadm and are unreachable

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

## Known Issues and Solutions

This section documents common issues encountered with kube-prometheus-stack on Raspberry Pi clusters with Calico CNI, and their solutions.

### Issue 1: Node-Exporter Scraping Failures

**Date Resolved:** 2025-12-26
**Severity:** High (affects all node monitoring)

**Symptoms:**

- Prometheus can only scrape 1 out of 5 node-exporter instances
- Error: `Get "http://10.0.10.x:9100/metrics": context deadline exceeded`
- Targets show "down" status for most nodes
- Fresh curl pods CAN reach node-exporters, but Prometheus pod CANNOT

**Root Cause:**
Node-exporter was configured with `hostNetwork: true`, which binds it to the node's IP address (10.0.10.x). When Prometheus (a regular pod in the Calico pod network) tries to connect to these node IPs, Calico's CNI routing fails due to:

- Reverse path filtering on host network interfaces
- CNI limitations when pods connect to hostNetwork pods via node IPs
- Routing asymmetry between pod network and host network

**Solution:**
Changed node-exporter configuration to use pod network instead of host network:

```yaml
prometheus-node-exporter:
  hostNetwork: false  # Changed from true
  hostPID: true       # Kept true for process metrics
```

**Why This Works:**

- node-exporter doesn't actually need `hostNetwork` for most metrics
- `hostPID: true` provides access to host process information
- Using pod network (Calico) allows Prometheus to reach all node-exporters via pod IPs (192.168.x.x)
- Maintains full metrics collection capability

**Result:**

- All 5 node-exporters now show "UP" status in Prometheus
- Complete metrics collection from all nodes
- No performance impact

**Related PRs:**

- homelab#72: Disable hostNetwork for node-exporter to fix Prometheus scraping

---

### Issue 2: Grafana Multi-Attach PVC Errors

**Date Resolved:** 2025-12-26
**Severity:** Medium (prevents ArgoCD updates)

**Symptoms:**

- ArgoCD sync fails when updating Grafana
- Error: `Multi-Attach error for volume "pvc-xxx" Volume is already used by pod(s) kube-prometheus-stack-grafana-xxx`
- Grafana pod stuck in Pending state during updates
- Old pod still running, new pod can't start

**Root Cause:**
Grafana uses a ReadWriteOnce (RWO) PVC for dashboard storage. The default RollingUpdate deployment strategy tries to:

1. Create new pod BEFORE terminating old pod
2. New pod attempts to mount the RWO PVC
3. PVC is still attached to old pod
4. Kubernetes rejects the mount → Multi-Attach error

This is a fundamental incompatibility: RWO PVCs can only attach to one pod at a time, but RollingUpdate requires two pods momentarily.

**Solution:**
Changed Grafana deployment strategy to Recreate:

```yaml
grafana:
  deploymentStrategy:
    type: Recreate
    rollingUpdate: null  # Must be null when using Recreate
```

**Why This Works:**

- `Recreate` strategy terminates old pod first
- Waits for PVC to fully detach
- Then creates new pod
- New pod successfully mounts the PVC

**Trade-off:**

- Small downtime during updates (~10-30 seconds)
- Acceptable for Grafana (not a critical real-time service)
- Better than deployment failures requiring manual intervention

**Result:**

- ArgoCD syncs complete successfully
- Clean pod replacements
- No manual intervention required

**Applies To:**
Any deployment using:

- Single replica (replicas: 1)
- ReadWriteOnce PVC
- Examples: LocalStack, future stateful apps

**Related PRs:**

- homelab#73: Set Grafana deployment strategy to Recreate for RWO PVC
- homelab#74: Explicitly set rollingUpdate to null for Grafana Recreate strategy

---

### Issue 3: Control Plane Component Scraping Failures

**Date Resolved:** 2025-12-26
**Severity:** Low (cosmetic errors in Prometheus)

**Symptoms:**

- Prometheus shows scraping errors for:
  - kube-controller-manager: `connection refused on https://10.0.10.214:10257`
  - kube-etcd: `context deadline exceeded on http://10.0.10.214:2381`
  - kube-proxy: `connection refused on http://10.0.10.x:10249`
  - kube-scheduler: `connection refused on https://10.0.10.214:10259`
- Targets permanently show "down" status
- No actual monitoring impact (cluster works fine)

**Root Cause:**
In kubeadm-based Kubernetes clusters, control plane components bind to localhost (127.0.0.1) for security:

- **Security Practice:** Prevents external access to sensitive components
- **Standard kubeadm:** Default configuration for all kubeadm clusters
- **Unreachable:** ServiceMonitors try to scrape via node IPs, but components only listen on localhost

Even if they listened on node IPs, the Calico CNI routing issue (same as node-exporter) would still prevent access.

**Solution:**
Disabled ServiceMonitors for unreachable control plane components:

```yaml
kubeControllerManager:
  enabled: false  # Disabled: binds to localhost in kubeadm

kubeEtcd:
  enabled: false  # Disabled: binds to localhost in kubeadm

kubeProxy:
  enabled: false  # Disabled: binds to localhost in kubeadm

kubeScheduler:
  enabled: false  # Disabled: binds to localhost in kubeadm
```

**Why This Is Correct:**

- **Not losing monitoring:** Cluster health still monitored via:
  - kubelet (monitors node and pod health)
  - kube-apiserver (monitors API server health)
  - kube-state-metrics (monitors all Kubernetes resource states)
- **Standard practice:** Common for homelab kubeadm clusters
- **Alternative is complex:** Would require:
  - Modifying kubeadm configuration to bind to node IPs
  - Opening firewall ports for these services
  - Potentially weakening security posture
  - Risk of breaking cluster during kubeadm upgrades

**Result:**

- Clean Prometheus targets page (no error noise)
- Still have comprehensive cluster monitoring
- Follows best practices for kubeadm homelab clusters

**Related PRs:**

- homelab#75: Disable unreachable control plane ServiceMonitors (controller-manager, etcd, proxy)
- homelab#77: Disable kube-scheduler ServiceMonitor

---

### Configuration Best Practices

Based on the above issues, follow these practices for Raspberry Pi clusters with Calico CNI:

**1. Avoid hostNetwork for exporters:**

- Use `hostNetwork: false` with `hostPID: true` or `hostIPC: true` as needed
- Allows pod network connectivity while accessing host resources
- Prevents Calico routing issues

**2. Use Recreate strategy for stateful apps with RWO PVCs:**

- Any app with single replica + ReadWriteOnce PVC
- Set `deploymentStrategy.type: Recreate`
- Set `deploymentStrategy.rollingUpdate: null`
- Accept brief downtime over deployment failures

**3. Disable unreachable kubeadm control plane monitoring:**

- Standard for homelab kubeadm clusters
- Focus monitoring on kubelet, API server, kube-state-metrics
- Don't try to modify kubeadm config for metric access

**4. Test connectivity from Prometheus pod:**

```bash
# Test if Prometheus can reach a target
kubectl exec -n default prometheus-kube-prometheus-stack-prometheus-0 -c prometheus -- \
  wget -q -O - --timeout=5 http://<target-ip>:<target-port>/metrics | head -5
```

---

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
