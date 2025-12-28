---
title: "Metrics Server"
description: "Kubernetes resource metrics API for kubectl top and Horizontal Pod Autoscaling"
---

# Metrics Server

Metrics Server provides container resource metrics (CPU, memory) for Kubernetes monitoring and autoscaling capabilities.

## Overview

- **Namespace:** `kube-system`
- **Chart:** `metrics-server` v3.13.0
- **App Version:** v0.8.0
- **Repository:** [kubernetes-sigs/metrics-server](https://kubernetes-sigs.github.io/metrics-server/)
- **Deployment:** Managed by ArgoCD
- **Sync Wave:** `-10` (deploys with cert-manager, external-dns)

## Purpose

Metrics Server is a cluster-wide aggregator of resource usage data that:

- Provides the Metrics API (`metrics.k8s.io`) for Kubernetes
- Enables `kubectl top nodes` and `kubectl top pods` commands
- Powers Horizontal Pod Autoscaler (HPA) for automatic scaling
- Collects resource metrics from Kubelets on each node
- Stores metrics in-memory (not for long-term monitoring)

**Key Capabilities:**

- Real-time CPU and memory usage per node
- Real-time CPU and memory usage per pod/container
- Foundation for autoscaling decisions
- Lightweight (minimal resource overhead)

## Architecture

### How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                        │
│                                                               │
│  ┌──────────────┐      ┌──────────────┐      ┌────────────┐ │
│  │   Node 1     │      │   Node 2     │      │   Node N   │ │
│  │              │      │              │      │            │ │
│  │  ┌────────┐  │      │  ┌────────┐  │      │ ┌────────┐ │ │
│  │  │ Kubelet│◄─┼──────┼──│ Kubelet│◄─┼──────┼─│ Kubelet│ │ │
│  │  │ (cAdv.)│  │      │  │ (cAdv.)│  │      │ │ (cAdv.)│ │ │
│  │  └────────┘  │      │  └────────┘  │      │ └────────┘ │ │
│  └──────────────┘      └──────────────┘      └────────────┘ │
│         ▲                     ▲                     ▲        │
│         │                     │                     │        │
│         │   HTTPS scrape      │                     │        │
│         │   (10250/metrics)   │                     │        │
│         │                     │                     │        │
│         └─────────────────────┴─────────────────────┘        │
│                               │                              │
│                   ┌───────────▼──────────┐                   │
│                   │   Metrics Server     │                   │
│                   │   (kube-system)      │                   │
│                   │                      │                   │
│                   │  - Aggregates data   │                   │
│                   │  - In-memory storage │                   │
│                   │  - 60s collection    │                   │
│                   └───────────┬──────────┘                   │
│                               │                              │
│                               │ Metrics API                  │
│                               │ (metrics.k8s.io/v1beta1)     │
│                               │                              │
│         ┌─────────────────────┴──────────────────┐           │
│         ▼                     ▼                  ▼           │
│  ┌────────────┐      ┌──────────────┐    ┌────────────┐     │
│  │  kubectl   │      │     HPA      │    │ Prometheus │     │
│  │  top       │      │  (autoscale) │    │ (monitor)  │     │
│  └────────────┘      └──────────────┘    └────────────┘     │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

**Data Flow:**

1. **Collection:** Metrics Server scrapes Kubelet `/metrics/resource` endpoint every 60s
2. **Aggregation:** Combines metrics from all nodes in-memory
3. **API:** Exposes aggregated metrics via `metrics.k8s.io` API
4. **Consumption:** kubectl, HPA, and monitoring tools query the API

**Kubelet Integration:**

Metrics Server connects to Kubelet's metrics endpoint (port 10250) using the internal node IP. The Kubelet collects container metrics from cAdvisor (Container Advisor), which is built into the Kubelet.

## Pi Cluster Configuration

### Resource Allocation

Optimized for Raspberry Pi 5 cluster constraints:

```yaml
resources:
  requests:
    cpu: 50m       # 0.25% of 20-core cluster
    memory: 100Mi  # 0.125% of 80GB RAM
  limits:
    cpu: 200m      # Burst capacity
    memory: 256Mi  # Maximum memory usage
```

**Impact:**

- Total overhead: **~50m CPU, ~100Mi RAM**
- Acceptable for 20-core ARM64 cluster with 80GB RAM
- Single replica deployment (HA not required for homelab)

### Required Arguments

```yaml
args:
  - --kubelet-insecure-tls
  # Required for clusters with self-signed kubelet certificates
  # Allows metrics-server to scrape metrics without TLS verification
  # Common in homelab/kubeadm deployments

  - --kubelet-preferred-address-types=InternalIP,ExternalIP,Hostname
  # Prefer internal IP for kubelet communication
  # Ensures metrics-server can reach kubelets on the Pi cluster network
```

**Why These Arguments Are Needed:**

- **`--kubelet-insecure-tls`:** The Pi cluster uses kubeadm with default self-signed Kubelet certificates. Without this flag, metrics-server cannot verify the Kubelet TLS certificates and fails to scrape metrics.

- **`--kubelet-preferred-address-types`:** Ensures metrics-server uses the node's internal IP (e.g., 10.0.50.101-105) to reach Kubelets rather than attempting external IPs or unresolvable hostnames.

### Security Context

```yaml
securityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  runAsNonRoot: true
  runAsUser: 1000
  seccompProfile:
    type: RuntimeDefault
  capabilities:
    drop:
      - ALL
```

**Priority Class:** `system-cluster-critical`

Ensures metrics-server pods are not evicted under resource pressure.

## Monitoring Integration

### Prometheus ServiceMonitor

Metrics Server exports its own metrics for monitoring:

```yaml
serviceMonitor:
  enabled: true
  additionalLabels:
    release: kube-prometheus-stack
  interval: 1m
  scrapeTimeout: 10s
```

**Exposed Metrics:**

- `metrics_server_manager_tick_duration_seconds` - Collection duration
- `metrics_server_storage_points` - Number of stored metrics
- `metrics_server_api_metric_freshness_seconds` - Metric age
- `rest_client_requests_total` - Kubelet scrape count/errors

**Grafana Dashboards:**

View metrics-server performance in Grafana:

- Kubernetes / API Server dashboard
- Custom metrics-server dashboard (TODO)

## Usage

### kubectl top Commands

Once deployed, the following commands become available:

**View node resource usage:**

```bash
kubectl top nodes
```

**Output:**

```
NAME      CPU(cores)   CPU%   MEMORY(bytes)   MEMORY%
node-01   850m         21%    12Gi            15%
node-02   720m         18%    10Gi            12%
node-03   680m         17%    9Gi             11%
node-04   910m         22%    14Gi            17%
node-05   760m         19%    11Gi            13%
```

**View pod resource usage (all namespaces):**

```bash
kubectl top pods -A
```

**View pod resource usage (specific namespace):**

```bash
kubectl top pods -n default
```

**View pod resource usage with containers:**

```bash
kubectl top pods -n default --containers
```

**Sort by CPU or memory:**

```bash
kubectl top pods -A --sort-by=cpu
kubectl top pods -A --sort-by=memory
```

### Horizontal Pod Autoscaler (HPA)

Metrics Server enables HPA for automatic pod scaling:

**Create HPA based on CPU:**

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: example-hpa
  namespace: default
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: example-app
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

**Create HPA with kubectl:**

```bash
kubectl autoscale deployment example-app \
  --cpu-percent=70 \
  --min=2 \
  --max=10
```

**View HPA status:**

```bash
kubectl get hpa -A
kubectl describe hpa example-hpa -n default
```

## Deployment

### ArgoCD Application

**File:** `manifests/applications/metrics-server.yaml`

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: metrics-server
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "-10"
spec:
  project: infrastructure
  sources:
    - repoURL: https://kubernetes-sigs.github.io/metrics-server/
      chart: metrics-server
      targetRevision: 3.13.0
      helm:
        releaseName: metrics-server
        valueFiles:
          - $values/manifests/base/metrics-server/values.yaml
    - repoURL: git@github.com:imcbeth/homelab.git
      path: manifests/base/metrics-server
      targetRevision: HEAD
      ref: values
  destination:
    server: https://kubernetes.default.svc
    namespace: kube-system
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=false  # kube-system already exists
      - ServerSideApply=false
    retry:
      limit: 3
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
```

### Sync Wave Explanation

**Sync Wave:** `-10` (same tier as cert-manager, external-dns)

**Dependency Chain:**

```
Wave -30: synology-csi (storage driver)
         ↓
Wave -15: kube-prometheus-stack (monitoring)
         ↓
Wave -10: metrics-server, cert-manager, external-dns
         ↓
Wave  -5: velero (backups)
         ↓
Wave   0: applications
```

Metrics Server has no dependencies on other applications, so wave `-10` provides early deployment while ensuring storage and monitoring infrastructure is available.

### Manual Sync

```bash
# Sync via ArgoCD CLI
argocd app sync metrics-server

# Watch sync progress
argocd app get metrics-server --watch

# Check sync status
argocd app get metrics-server
```

## Validation

### Verify Deployment

**Check pod status:**

```bash
kubectl get pods -n kube-system -l app.kubernetes.io/name=metrics-server
```

**Expected output:**

```
NAME                              READY   STATUS    RESTARTS   AGE
metrics-server-5d4f8c5b9c-7x2kg   1/1     Running   0          2m
```

**Check API service:**

```bash
kubectl get apiservice v1beta1.metrics.k8s.io
```

**Expected output:**

```
NAME                     SERVICE                      AVAILABLE   AGE
v1beta1.metrics.k8s.io   kube-system/metrics-server   True        2m
```

**Test metrics availability:**

```bash
# Should return node metrics
kubectl top nodes

# Should return pod metrics
kubectl top pods -A

# Query raw API
kubectl get --raw /apis/metrics.k8s.io/v1beta1/nodes
kubectl get --raw /apis/metrics.k8s.io/v1beta1/pods
```

### Check Logs

```bash
kubectl logs -n kube-system -l app.kubernetes.io/name=metrics-server --tail=50
```

**Healthy logs:**

```
I1228 08:00:00.123456       1 serving.go:342] Generated self-signed cert (apiserver.local.config/certificates::"metrics-server-cert" ...)
I1228 08:00:00.234567       1 secure_serving.go:266] Serving securely on [::]:10250
I1228 08:00:00.345678       1 requestheader_controller.go:169] Starting RequestHeaderAuthRequestController
I1228 08:00:00.456789       1 shared_informer.go:311] Waiting for caches to sync for RequestHeaderAuthRequestController
I1228 08:00:00.567890       1 shared_informer.go:318] Caches are synced for RequestHeaderAuthRequestController
```

### Verify Prometheus Monitoring

```bash
# Check ServiceMonitor
kubectl get servicemonitor -n kube-system metrics-server

# Port-forward to Prometheus
kubectl port-forward -n default svc/kube-prometheus-stack-prometheus 9090:9090

# Query metrics in Prometheus UI (http://localhost:9090)
# - up{job="metrics-server"}
# - metrics_server_manager_tick_duration_seconds
```

## Troubleshooting

### Issue: kubectl top fails with "Metrics API not available"

**Symptoms:**

```
error: Metrics API not available
```

**Diagnosis:**

```bash
# Check API service status
kubectl get apiservice v1beta1.metrics.k8s.io

# Check pod status
kubectl get pods -n kube-system -l app.kubernetes.io/name=metrics-server

# Check logs
kubectl logs -n kube-system -l app.kubernetes.io/name=metrics-server
```

**Common Causes:**

1. **Metrics Server pod not running:**

   ```bash
   kubectl describe pod -n kube-system -l app.kubernetes.io/name=metrics-server
   ```

2. **API service not registered:**

   ```bash
   kubectl describe apiservice v1beta1.metrics.k8s.io
   ```

3. **Certificate errors:**
   - Check logs for TLS errors
   - Verify `--kubelet-insecure-tls` flag is set

### Issue: "unable to fetch metrics from Kubelet"

**Symptoms in logs:**

```
unable to fetch metrics from node node-01: Get "https://10.0.50.101:10250/metrics/resource": x509: certificate signed by unknown authority
```

**Solution:**

Add `--kubelet-insecure-tls` flag to `args` in values.yaml:

```yaml
args:
  - --kubelet-insecure-tls
```

### Issue: "no metrics known for pod"

**Symptoms:**

```
error: metrics not available yet
```

**Explanation:**

Metrics Server collects metrics every 60 seconds. Wait 1-2 minutes after pod creation for metrics to become available.

**Verify metrics are being collected:**

```bash
# Check scrape count
kubectl logs -n kube-system -l app.kubernetes.io/name=metrics-server | grep -i scrape

# Query raw API
kubectl get --raw /apis/metrics.k8s.io/v1beta1/pods
```

### Issue: High memory usage

**Diagnosis:**

```bash
kubectl top pods -n kube-system -l app.kubernetes.io/name=metrics-server
```

**Explanation:**

Metrics Server stores metrics in-memory for all pods/nodes in the cluster. Memory usage scales with cluster size:

- Small cluster (fewer than 50 pods): ~100-150Mi
- Medium cluster (50-200 pods): ~150-300Mi
- Large cluster (200+ pods): ~300-500Mi

**Solution:**

Adjust memory limits in `values.yaml` if needed:

```yaml
resources:
  limits:
    memory: 512Mi  # Increase if needed
```

### Issue: Metrics Server pod evicted under load

**Symptoms:**

```
Status: Failed
Reason: Evicted
```

**Solution:**

Metrics Server is configured with `priorityClassName: system-cluster-critical` to prevent eviction. If evictions occur, check:

1. **Node resource pressure:**

   ```bash
   kubectl describe node <node-name> | grep -A 10 "Conditions:"
   ```

2. **Pod priority:**

   ```bash
   kubectl get pod -n kube-system <metrics-server-pod> -o yaml | grep priority
   ```

3. **Resource requests too low:**
   - Increase CPU/memory requests in values.yaml

## Performance & Scalability

### Resource Usage

**Baseline (5-node cluster, ~30 pods):**

- CPU: ~30-50m average, bursts to 100m during scrapes
- Memory: ~80-120Mi
- Network: Minimal (~1-2 KB/s per node)

**Scaling Characteristics:**

| Cluster Size | Pods | CPU Usage | Memory Usage |
|--------------|------|-----------|--------------|
| 5 nodes      | 30   | 50m       | 100Mi        |
| 10 nodes     | 100  | 100m      | 200Mi        |
| 20 nodes     | 300  | 200m      | 400Mi        |

### Collection Interval

**Default:** 60 seconds (not configurable via flags)

Metrics Server scrapes Kubelets every 60 seconds. This interval is hardcoded and cannot be changed without modifying the source code.

**Metric Freshness:**

Metrics are considered fresh for 90 seconds after collection. Older metrics are discarded.

### High Availability

**Current Deployment:** Single replica

**HA Considerations:**

For production clusters, consider multiple replicas:

```yaml
replicas: 2

affinity:
  podAntiAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
    - weight: 100
      podAffinityTerm:
        labelSelector:
          matchLabels:
            app.kubernetes.io/name: metrics-server
        topologyKey: kubernetes.io/hostname
```

**Not required for homelab:** Single replica is sufficient. If the pod fails, it restarts quickly and metrics resume within 60 seconds.

## Comparison: Metrics Server vs Prometheus

| Feature | Metrics Server | Prometheus |
|---------|----------------|------------|
| **Purpose** | Real-time resource metrics | Long-term monitoring & alerting |
| **Storage** | In-memory (60s retention) | On-disk (configurable retention) |
| **Collection** | Every 60s | Configurable (1s - 5m) |
| **Metrics** | CPU, memory only | All Prometheus metrics |
| **HPA Support** | ✅ Yes (primary use) | ❌ No (custom metrics adapter needed) |
| **kubectl top** | ✅ Yes | ❌ No |
| **Alerting** | ❌ No | ✅ Yes |
| **Grafana** | Limited | Full support |
| **Resource Usage** | Low (~50m CPU, ~100Mi RAM) | High (~500m CPU, ~2Gi RAM base) |

**Use Both:**

- **Metrics Server:** For kubectl top, HPA, real-time resource monitoring
- **Prometheus:** For long-term trends, alerting, comprehensive metrics

## Integration Examples

### Example: CPU-based HPA for NGINX Ingress

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: nginx-ingress-hpa
  namespace: ingress-nginx
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: ingress-nginx-controller
  minReplicas: 2
  maxReplicas: 5
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 75
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 50
        periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
      - type: Percent
        value: 100
        periodSeconds: 30
```

### Example: Memory-based HPA

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: example-memory-hpa
  namespace: default
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: memory-intensive-app
  minReplicas: 2
  maxReplicas: 8
  metrics:
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

### Example: Combined CPU + Memory HPA

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: example-combined-hpa
  namespace: default
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: web-app
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
      - type: Pods
        value: 2
        periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Pods
        value: 1
        periodSeconds: 120
```

## References

- **Official Documentation:** [kubernetes-sigs/metrics-server](https://github.com/kubernetes-sigs/metrics-server)
- **Helm Chart:** [metrics-server on ArtifactHub](https://artifacthub.io/packages/helm/metrics-server/metrics-server)
- **Kubernetes Metrics API:** [Resource Metrics Pipeline](https://kubernetes.io/docs/tasks/debug/debug-cluster/resource-metrics-pipeline/)
- **HPA Documentation:** [Horizontal Pod Autoscaler](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/)

## Related Documentation

- [kube-prometheus-stack](./kube-prometheus-stack.md) - Long-term metrics storage and alerting
- [ArgoCD](./argocd.md) - GitOps deployment management
- [Velero](./velero.md) - Backup strategy (metrics-server config backed up)
