# Custom Grafana Dashboards

This guide documents the custom Grafana dashboards deployed for comprehensive Pi cluster monitoring.

## Overview

Four custom dashboards provide visibility into cluster health, node resources, temperatures, and log analytics:

1. **Pi Cluster Overview** - Unified health dashboard
2. **Node Resource Monitoring** - Detailed per-node metrics
3. **Temperature Monitoring** - Thermal analysis and monitoring
4. **Loki Log Analytics** - Log aggregation and error tracking

All dashboards are deployed via ConfigMap sidecar provisioning and auto-discovered by Grafana.

## Access

**URL:** [https://grafana.k8s.n37.ca](https://grafana.k8s.n37.ca)
**Credentials:** `<grafana-username>` / `<grafana-password>` (example only — set your own secure credentials in Grafana or your secret management system)

## Dashboard Deployment

### Architecture

Dashboards are deployed as Kubernetes ConfigMaps with the label `grafana_dashboard: "1"`, which triggers auto-discovery by the Grafana sidecar container.

**Deployment Pattern:**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-dashboard-<name>
  namespace: default
  labels:
    grafana_dashboard: "1"  # Auto-discovery label
    app: grafana
data:
  <name>.json: |
    { "dashboard": {...} }
```

**Kustomization Structure:**

```
manifests/base/
├── grafana/
│   └── dashboards/
│       ├── kustomization.yaml  # Includes all dashboards
│       ├── pi-cluster-overview.yaml
│       ├── node-resource-monitoring.yaml
│       ├── temperature-monitoring.yaml
│       └── loki-log-analytics.yaml
└── kube-prometheus-stack/
    └── kustomization.yaml  # References dashboards via bases
```

### Sidecar Auto-Discovery

The Grafana deployment includes a sidecar container (`grafana-sc-dashboard`) that:

1. Watches for ConfigMaps with label `grafana_dashboard: "1"`
2. Extracts dashboard JSON from ConfigMap data
3. Writes dashboard files to `/tmp/dashboards/`
4. Grafana automatically loads dashboards from this directory

**Discovery is automatic** - no manual dashboard import required.

### Dashboard Provisioning

Dashboards are **read-only in the Grafana UI** (`editable: false`) because they're provisioned via ConfigMaps, but they remain configurable via the ConfigMap definitions. To modify:

1. Edit the dashboard ConfigMap YAML file
2. Commit and push changes
3. ArgoCD syncs automatically
4. Grafana sidecar reloads dashboard (~30s)

## Pi Cluster Overview Dashboard

**UID:** `pi-cluster-overview`
**Refresh Rate:** 30 seconds
**Default Time Range:** Last 6 hours

### Purpose

Unified cluster health dashboard combining key metrics across all nodes.

### Panels (7 Total)

#### 1. Total Nodes (Stat)

- **Query:** `count(kube_node_info)`
- **Shows:** Number of Kubernetes nodes in the cluster
- **Expected:** 5 (control-plane + 4 worker nodes)

#### 2. Total Pods (Stat)

- **Query:** `count(kube_pod_info)`
- **Shows:** Total running pods across all namespaces
- **Typical Range:** 40-60 pods

#### 3. Cluster CPU Usage (Stat)

- **Query:** `(1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m]))) * 100`
- **Shows:** Average CPU usage across all nodes
- **Thresholds:**
  - Green: < 70%
  - Yellow: 70-90%
  - Red: > 90%

#### 4. Cluster Memory Usage (Stat)

- **Query:** `(1 - sum(node_memory_MemAvailable_bytes) / sum(node_memory_MemTotal_bytes)) * 100`
- **Shows:** Total memory usage across cluster
- **Cluster Total:** ~80GB (5 nodes × 16GB)
- **Thresholds:** Same as CPU

#### 5. CPU Usage Per Node (Time Series)

- **Query:** `(1 - avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m]))) * 100`
- **Shows:** Individual CPU usage trends for each node
- **Legend:** Last, Max values displayed

#### 6. Memory Usage Per Node (Time Series)

- **Query:** `(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100`
- **Shows:** Individual memory usage trends for each node

#### 7. CPU Temperature Per Node (Time Series)

- **Query:** `node_hwmon_temp_celsius{chip="thermal_thermal_zone0",sensor="temp1"}`
- **Shows:** Real-time CPU temperatures for all Pi 5 nodes
- **Thresholds:**
  - Green: < 70°C
  - Yellow: 70-85°C
  - Red: > 85°C
- **Normal Range:** 45-60°C (idle to moderate load)

### Use Cases

- **Quick health check** - Glance at cluster status
- **Capacity planning** - Monitor resource utilization trends
- **Thermal monitoring** - Ensure nodes aren't overheating
- **Incident response** - Identify which nodes are under stress

## Node Resource Monitoring Dashboard

**UID:** `node-resource-monitoring`
**Refresh Rate:** 30 seconds
**Default Time Range:** Last 6 hours

### Purpose

Detailed per-node resource analysis for troubleshooting and capacity planning.

### Panels (13 Total)

#### CPU Metrics

**1. CPU Usage Per Node (Time Series)**

- **Query:** `(1 - avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m]))) * 100`
- **Shows:** Individual node CPU % over time
- **5 series** - One per node

**2. CPU Load Average (Time Series)**

- **Queries:**
  - `node_load1` - 1-minute load average
  - `node_load5` - 5-minute load average
  - `node_load15` - 15-minute load average
- **Interpretation:**
  - Load < 4.0 (# of cores) = healthy
  - Load > 4.0 = CPU saturation

#### Memory Metrics

**3. Memory Usage Per Node (Time Series)**

- **Query:** `(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100`
- **Shows:** Per-node memory % over time

**4. Available Memory Per Node (Time Series)**

- **Query:** `node_memory_MemAvailable_bytes`
- **Shows:** Free memory in bytes per node
- **16GB per node** = 17,179,869,184 bytes total

#### Disk Metrics

**5. Disk I/O Per Node (Time Series)**

- **Queries:**
  - Read: `rate(node_disk_read_bytes_total[5m])`
  - Write: `rate(node_disk_written_bytes_total[5m])`
- **Shows:** Bytes/sec read and written per disk
- **Includes:** MicroSD and NVMe devices

**6. Disk IOPS Per Node (Time Series)**

- **Queries:**
  - Read: `rate(node_disk_reads_completed_total[5m])`
  - Write: `rate(node_disk_writes_completed_total[5m])`
- **Shows:** I/O operations per second

#### Network Metrics

**7. Network Receive (RX) Per Node (Time Series)**

- **Query:** `rate(node_network_receive_bytes_total{device!~"lo|veth.*|docker.*|flannel.*|cali.*|cbr.*"}[5m])`
- **Shows:** Inbound network traffic (bytes/sec)
- **Excludes:** Loopback and virtual interfaces

**8. Network Transmit (TX) Per Node (Time Series)**

- **Query:** `rate(node_network_transmit_bytes_total{device!~"lo|veth.*|docker.*|flannel.*|cali.*|cbr.*"}[5m])`
- **Shows:** Outbound network traffic (bytes/sec)

#### Filesystem Metrics

**9. Filesystem Usage (Table)**

- **Queries:**
  - Size: `node_filesystem_size_bytes`
  - Available: `node_filesystem_avail_bytes`
  - Used %: `(1 - (node_filesystem_avail_bytes / node_filesystem_size_bytes)) * 100`
- **Shows:** Per-mountpoint disk usage
- **Excludes:** tmpfs, fuse, NFS mounts

#### Node Details

**10. Node Boot Time (Stat)**

- **Query:** `node_boot_time_seconds`
- **Shows:** Timestamp when each node last booted

**11. Node Uptime (Stat)**

- **Query:** `time() - node_boot_time_seconds`
- **Shows:** Seconds since boot per node

**12. Kernel Version (Table)**

- **Query:** `node_uname_info`
- **Shows:** Linux kernel version per node
- **Expected:** Debian/Raspberry Pi OS kernel

**13. OS Information (Table)**

- **Query:** `node_os_info`
- **Shows:** Operating system distribution per node
- **Expected:** Debian GNU/Linux 12 (bookworm)

### Use Cases

- **Performance troubleshooting** - Identify bottlenecks (CPU, memory, disk, network)
- **Capacity planning** - Track resource trends over time
- **Disk space monitoring** - Prevent out-of-space conditions
- **Network diagnostics** - Measure bandwidth utilization

## Temperature Monitoring Dashboard

**UID:** `temperature-monitoring`
**Refresh Rate:** 30 seconds
**Default Time Range:** Last 24 hours

### Purpose

Raspberry Pi CPU thermal monitoring and cooling efficiency analysis.

### Panels (8 Total)

#### 1. CPU Temperature Per Node (24h) (Time Series)

- **Query:** `node_hwmon_temp_celsius{chip="thermal_thermal_zone0",sensor="temp1"}`
- **Shows:** Real-time CPU temperature trends for all 5 nodes
- **Visualization:**
  - Smooth line interpolation
  - Threshold lines at 70°C (yellow) and 85°C (red)
  - Legend shows: Last, Max, Mean, Min values

**Raspberry Pi 5 Thermal Characteristics:**

- **Idle:** 40-50°C
- **Moderate Load:** 50-65°C
- **Heavy Load:** 65-75°C
- **Throttle Point:** 85°C (CPU will reduce frequency)
- **Critical:** 90°C (system protection kicks in)

#### Temperature Statistics

**2. Current Max Temperature (Stat)**

- **Query:** `max(node_hwmon_temp_celsius{chip="thermal_thermal_zone0",sensor="temp1"})`
- **Shows:** Hottest node right now

**3. Current Avg Temperature (Stat)**

- **Query:** `avg(node_hwmon_temp_celsius{chip="thermal_thermal_zone0",sensor="temp1"})`
- **Shows:** Average CPU temp across cluster

**4. Max Temperature (24h) (Stat)**

- **Query:** `max_over_time(node_hwmon_temp_celsius{chip="thermal_thermal_zone0",sensor="temp1"}[24h])`
- **Shows:** Peak temperature in last 24 hours
- **Use:** Identify thermal spikes during heavy workloads

**5. Current Min Temperature (Stat)**

- **Query:** `min(node_hwmon_temp_celsius{chip="thermal_thermal_zone0",sensor="temp1"})`
- **Shows:** Coolest node right now

#### Advanced Visualizations

**6. Temperature Distribution Heatmap**

- **Query:** `node_hwmon_temp_celsius{chip="thermal_thermal_zone0",sensor="temp1"}`
- **Visualization:** Heatmap showing temperature distribution over time
- **Color Scheme:** Oranges (cooler = lighter, hotter = darker)
- **Use:** Identify thermal patterns and daily cycles

**7. Temperature Delta (Cooling Efficiency) (Gauge)**

- **Query:** `max(node_hwmon_temp_celsius{...}) - min(node_hwmon_temp_celsius{...})`
- **Shows:** Temperature difference between hottest and coolest nodes
- **Thresholds:**
  - Green: < 5°C (excellent cooling uniformity)
  - Yellow: 5-10°C (acceptable variation)
  - Red: > 10°C (poor cooling efficiency)
- **Ideal:** < 5°C delta indicates well-balanced cooling

**8. Temperature Summary by Node (Table)**

- **Columns:**
  - Instance (node IP)
  - Current Temp
  - Max (24h)
  - Avg (24h)
- **Sorted by:** Current temperature (descending)
- **Use:** Identify which nodes run hotter consistently

### Temperature Sensor Details

**Metric:** `node_hwmon_temp_celsius`

**Available Chips:**

- `thermal_thermal_zone0` - **CPU thermal zone** (used in dashboard)
- `1000120000_pcie_1f000c8000_adc` - PCIe/RP1 chip sensor
- `nvme_nvme0` - NVMe SSD temperature

**Why thermal_thermal_zone0?**
This is the kernel's thermal zone for the Broadcom BCM2712 SoC (Raspberry Pi 5 CPU), which represents the actual CPU die temperature.

### Cooling Recommendations

**If temperatures consistently exceed 75°C:**

1. Verify active cooling (fans) are operational
2. Check for dust accumulation on heatsinks
3. Ensure adequate airflow in rack/case
4. Consider upgrading to Active Cooler or heatsink with larger surface area
5. Review pod scheduling - redistribute CPU-heavy workloads

**Normal Operation:**

- Passive cooling: 55-70°C under load
- Active cooling (fan): 45-55°C under load
- Idle: 40-50°C

### Use Cases

- **Thermal management** - Ensure nodes stay within safe operating temperatures
- **Cooling validation** - Verify active cooling is effective
- **Workload optimization** - Identify temperature spikes during specific workloads
- **Preventive maintenance** - Detect thermal degradation over time

## Loki Log Analytics Dashboard

**UID:** `loki-log-analytics`
**Refresh Rate:** 30 seconds
**Default Time Range:** Last 1 hour

### Purpose

Log aggregation monitoring and analysis for cluster-wide log insights.

### Panels (10 Total)

#### Ingestion Metrics

**1. Log Ingestion Rate (Lines/sec) (Time Series)**

- **Query:** `sum(rate(loki_distributor_lines_received_total[5m]))`
- **Shows:** Total log lines ingested per second
- **Unit:** cps (counts per second)
- **Typical Range:** 10-100 lines/sec (depends on verbosity)

**2. Log Ingestion Rate (Bytes/sec) (Time Series)**

- **Query:** `sum(rate(loki_distributor_bytes_received_total[5m]))`
- **Shows:** Total log data ingested per second
- **Unit:** Bytes/sec
- **Typical Range:** 1-10 KB/sec

#### Loki Internals

**3. Active Streams (Stat)**

- **Query:** `sum(loki_ingester_streams)`
- **Shows:** Number of active log streams in ingester
- **Stream:** Unique combination of labels (namespace, pod, container)

**4. Chunks Flushed/sec (Stat)**

- **Query:** `sum(rate(loki_ingester_chunks_flushed_total[5m]))`
- **Shows:** Rate of chunk flushes to storage
- **High rate:** May indicate high log volume or short retention

**5. Ingester Memory Usage (Stat)**

- **Query:** `sum(loki_ingester_memory_chunks_bytes)`
- **Shows:** Memory used by in-memory log chunks
- **Thresholds:**
  - Green: < 256MB
  - Yellow: 256-512MB
  - Red: > 512MB
- **Tuned for:** Pi cluster with limited RAM

#### Log Volume Analysis

**6. Log Volume by Namespace (Time Series)**

- **Query:** `sum by (namespace) (count_over_time({namespace!=""}[5m]))`
- **Shows:** Log lines per namespace over time
- **Visualization:** Stacked bars
- **Use:** Identify which namespaces are most verbose

**7. Error Log Volume by Pod (Time Series)**

- **Query:** `sum by (pod) (count_over_time({namespace!=""} |~ "(?i)(error|err|failed|fatal)" [5m]))`
- **Shows:** Error-level logs per pod
- **Pattern:** Case-insensitive match for error keywords
- **Use:** Quickly identify pods with errors

#### Query Performance

**8. Query Performance (Latency) (Time Series)**

- **Queries:**
  - p95: `histogram_quantile(0.95, sum(rate(loki_request_duration_seconds_bucket[5m])) by (le))`
  - p99: `histogram_quantile(0.99, sum(rate(loki_request_duration_seconds_bucket[5m])) by (le))`
- **Shows:** Query latency at 95th and 99th percentiles
- **Healthy:** p95 < 1s, p99 < 2s
- **Degraded:** p95 > 2s indicates query performance issues

#### Log Inspection

**9. Recent Error Logs (Logs Panel)**

- **Query:** `{cluster="$cluster", namespace=~"$namespace"} |~ "(?i)(error|err|failed|fatal)"`
- **Shows:** Live stream of error-level logs from all namespaces
- **Features:**
  - Filterable by namespace/pod
  - Time-ordered (newest first)
  - Syntax highlighting
- **Pattern Matching:** Case-insensitive regex for common error keywords

**10. Top 20 Pods by Log Volume (Time Series)**

- **Query:** `topk(20, sum by (pod) (count_over_time({namespace!=""}[5m])))`
- **Shows:** Pods generating the most log lines
- **Use:** Identify chatty applications or potential logging issues

### LogQL Query Optimization

**Performance Best Practices:**

1. **Use specific namespace selectors:**

   ```logql
   # Good
   {namespace!=""}  # Excludes empty namespace

   # Avoid
   {namespace=~".+"}  # permissive regex (slower)
   ```

2. **Limit time ranges for expensive queries:**
   - Large scans: Use 5m-15m ranges
   - Error searches: Use 1h-6h ranges
   - Full-text searches: Avoid > 24h ranges

3. **Case-insensitive pattern matching:**

   ```logql
   # Efficient
   |~ "(?i)(error|err|failed|fatal)"

   # Redundant
   |~ "(?i)(error|ERROR|err|ERR|failed|FAILED)"
   ```

### Loki Configuration

**Retention:** 7 days (configured in Loki values.yaml)
**Storage:** Local filesystem (PVC-backed)
**Limits:**

- Max query size: 5000 lines
- Max streams per user: 10000

### Use Cases

- **Troubleshooting** - Search for errors across all pods
- **Performance monitoring** - Track query latency and ingestion rate
- **Capacity planning** - Monitor log volume growth
- **Incident investigation** - Filter logs by time range and keywords

## Dashboard Audit (2025-12-28)

### Current State

**Total Dashboards:** 30 (all provisioned via ConfigMap)
**Custom Dashboards:** 4
**Kube-Prometheus-Stack Dashboards:** 26
**Uncommitted Dashboards:** 0 ✅

All dashboards are managed as code - there are **no manually created or uncommitted dashboards** in the Grafana UI.

### Audit Process

The following audit was performed to verify all dashboards are in GitOps:

1. **Verified Dashboard Provisioning Configuration:**

   ```bash
   # Check sidecar provisioning config
   kubectl exec -n default deployment/kube-prometheus-stack-grafana \
     -c grafana -- cat /etc/grafana/provisioning/dashboards/sc-dashboardproviders.yaml
   ```

   **Key Settings:**
   - `allowUiUpdates: false` - **UI modifications are disabled**
   - `disableDeletion: false` - Dashboards can be deleted but will be recreated by sidecar
   - `path: /tmp/dashboards` - All dashboards loaded from this directory

2. **Listed All Provisioned Dashboards:**

   ```bash
   # List all dashboard files
   kubectl exec -n default deployment/kube-prometheus-stack-grafana \
     -c grafana -- ls -1 /tmp/dashboards/ | sort
   ```

   **Custom Dashboards (4):**
   - `loki-log-analytics.json`
   - `node-resource-monitoring.json`
   - `pi-cluster-overview.json`
   - `temperature-monitoring.json`

   **Kube-Prometheus-Stack Dashboards (26):**
   - `alertmanager-overview.json`
   - `apiserver.json`
   - `cluster-total.json`
   - `controller-manager.json`
   - `grafana-overview.json`
   - `k8s-coredns.json`
   - `k8s-resources-cluster.json`
   - `k8s-resources-multicluster.json`
   - `k8s-resources-namespace.json`
   - `k8s-resources-node.json`
   - `k8s-resources-pod.json`
   - `k8s-resources-workload.json`
   - `k8s-resources-workloads-namespace.json`
   - `kubelet.json`
   - `namespace-by-pod.json`
   - `namespace-by-workload.json`
   - `node-cluster-rsrc-use.json`
   - `node-rsrc-use.json`
   - `nodes-aix.json`
   - `nodes-darwin.json`
   - `nodes.json`
   - `persistentvolumesusage.json`
   - `pod-total.json`
   - `prometheus.json`
   - `scheduler.json`
   - `workload-total.json`

3. **Verified All Dashboards Have ConfigMap Sources:**

   ```bash
   # Count dashboard ConfigMaps
   kubectl get configmap -n default -l grafana_dashboard=1 | wc -l
   ```

   **Result:** 30 ConfigMaps (matches 30 dashboard files)

### Audit Conclusion

✅ **All dashboards are managed as code via GitOps**
✅ **UI dashboard creation is disabled** (`allowUiUpdates: false`)
✅ **No manual migrations needed** - all existing dashboards already have ConfigMap sources
✅ **Sidecar auto-discovery is working** - all ConfigMaps are loaded automatically

**Recommendation:** Maintain this GitOps-only workflow for all future dashboard changes.

## Common Tasks

### Adding a New Dashboard

**Note:** Dashboard creation through the Grafana UI is **disabled** (`allowUiUpdates: false`). All dashboards must be created as ConfigMaps.

**Workflow:**

1. **Option A: Create JSON manually** or **Option B: Create locally and export**

   If using Option B:
   - Temporarily enable `allowUiUpdates: true` in values.yaml
   - Create dashboard in Grafana UI
   - Export JSON (Settings → JSON Model)
   - Disable `allowUiUpdates: false` again

2. Create ConfigMap YAML:

   ```yaml
   apiVersion: v1
   kind: ConfigMap
   metadata:
     name: grafana-dashboard-<name>
     namespace: default
     labels:
       grafana_dashboard: "1"  # Required for sidecar discovery
       app: grafana
   data:
     <name>.json: |
       {
         "editable": false,
         "title": "Dashboard Title",
         "uid": "unique-dashboard-id",
         ...
       }
   ```

3. Add to `manifests/base/grafana/dashboards/kustomization.yaml`:

   ```yaml
   resources:
     - pi-cluster-overview.yaml
     - node-resource-monitoring.yaml
     - temperature-monitoring.yaml
     - loki-log-analytics.yaml
     - <your-new-dashboard>.yaml  # Add here
   ```

4. Commit and push changes
5. ArgoCD syncs automatically (~3 minutes)
6. Grafana sidecar discovers and loads dashboard (~30 seconds)

### Modifying an Existing Dashboard

**Option 1: Edit YAML directly (recommended)**

1. Edit the dashboard ConfigMap YAML
2. Commit and push changes
3. ArgoCD syncs automatically
4. Grafana reloads dashboard (~30s)

**Option 2: Export from UI**

1. Make changes in Grafana UI
2. Export JSON (Settings → JSON Model)
3. Copy JSON into ConfigMap YAML
4. Ensure `editable: false` is set
5. Commit and push

**Note:** UI edits are **temporary** - they will be overwritten on next sync.

### Troubleshooting Dashboard Issues

**Dashboard not appearing:**

```bash
# 1. Verify ConfigMap exists
kubectl get configmap -n default -l grafana_dashboard=1

# 2. Check sidecar logs
kubectl logs -n default deployment/kube-prometheus-stack-grafana \
  -c grafana-sc-dashboard --tail=50

# 3. Verify dashboard was written
kubectl logs -n default deployment/kube-prometheus-stack-grafana \
  -c grafana-sc-dashboard | grep "Writing.*<dashboard-name>"
```

**Query not returning data:**

```bash
# Test query in Prometheus
kubectl port-forward -n default prometheus-kube-prometheus-stack-prometheus-0 9090:9090

# Open http://localhost:9090 and test PromQL query
```

**Temperature metrics missing:**

```bash
# With the port-forward from above still running, check available hwmon chips
curl -s 'http://localhost:9090/api/v1/label/chip/values' | jq

# Query all temperature sensors
curl -s 'http://localhost:9090/api/v1/query?query=node_hwmon_temp_celsius' | jq
```

## Dashboard Configuration

### Datasource References

All dashboards use structured datasource format:

**Prometheus:**

```json
"datasource": {
  "type": "prometheus",
  "uid": "prometheus"
}
```

**Loki:**

```json
"datasource": {
  "type": "loki",
  "uid": "loki"
}
```

### Common Thresholds

**Resource Usage (CPU/Memory):**

- Green: < 70%
- Yellow: 70-90%
- Red: > 90%

**Temperature:**

- Green: < 70°C
- Yellow: 70-85°C
- Red: > 85°C

**Loki Ingester Memory:**

- Green: < 256MB
- Yellow: 256-512MB
- Red: > 512MB

## References

- [Grafana Dashboard Documentation](https://grafana.com/docs/grafana/latest/dashboards/)
- [PromQL Query Examples](https://prometheus.io/docs/prometheus/latest/querying/examples/)
- [LogQL Documentation](https://grafana.com/docs/loki/latest/logql/)
- [node_exporter Metrics](https://github.com/prometheus/node_exporter#enabled-by-default)
- [Raspberry Pi 5 Thermal Specifications](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#raspberry-pi-5)
