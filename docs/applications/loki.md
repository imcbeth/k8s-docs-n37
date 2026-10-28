---
title: "Loki + Alloy"
description: "Centralized log aggregation with Grafana Loki and Grafana Alloy"
---

# Loki + Alloy

Grafana Loki with Grafana Alloy provides centralized log aggregation and querying for all Kubernetes pods across the 5-node Raspberry Pi cluster. Alloy also carries the OpenTelemetry trace pipeline into Tempo.

## Overview

**Loki:**

- **Namespace:** `loki`
- **Helm Chart:** `grafana/loki`
- **Chart Version:** `7.5.0` (as of 2026-10-24, via Renovate PR #1069). Chart appVersion declares 3.6.16 but the chart renders image `grafana/loki:3.6.11` — compare `helm template` against the running image rather than assuming appVersion.
- **Deployment Mode:** SingleBinary (monolithic, explicit — Loki v7 default is SimpleScalable)
- **Deployment:** Managed by ArgoCD
- **Sync Wave:** `-12` (after kube-prometheus-stack -15, before cert-manager -10)

**Log Collector: Grafana Alloy** *(replaced Promtail 2026-03-01)*

- **Namespace:** `loki`
- **Helm Chart:** `grafana/alloy`
- **Chart Version:** `1.14.3` (as of 2026-10-24 via Renovate PR #1058); running image `grafana/alloy:v1.21.2`
- **Deployment:** DaemonSet, 5/5 (one pod per node, control-plane included) + OTLP → Tempo forwarding
- **Sync Wave:** `-11` (after Loki -12)

Promtail reached end-of-life in March 2026 and was replaced by Grafana Alloy. Alloy uses `loki.source.kubernetes` for pod log collection and a selective `labelmap` stage to stay within Loki's 15-label limit. It also forwards OpenTelemetry traces to Grafana Tempo via `otelcol.receiver.otlp` + `otelcol.exporter.otlp`.

:::note Promtail (historical)
Promtail chart 6.17.1 (app v3.5.1) was deployed until 2026-03-01. Replaced due to EOL. See archived session notes for migration details.
:::

## Architecture

```
┌─────────────────────────────────────────┐
│  Alloy DaemonSet (5 pods)               │
│  - One pod per Pi node                  │
│  - discovery.kubernetes -> loki.source  │
│  - 50m/200m CPU, 128Mi/512Mi each       │
│  - also OTLP :4317/:4318 -> Tempo       │
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
  - Requests: 200m CPU, 512Mi memory
  - Limits: 500m CPU, 768Mi memory
- **Memory Management:**
  - `GOMEMLIMIT: 700MiB` (Go runtime memory cap)
  - Ingestion rate limits: 10MB/sec, 20MB burst
  - Internal caching only (no external memcached)
- **Sidecar (k8s-sidecar):** 10m/64Mi request, 100m/256Mi limit
- **Loki Canary:** 10m/32Mi request, 50m/64Mi limit

**Note:** Memory configuration optimized on 2026-01-05 for singleBinary mode stability. Uses internal caching instead of external memcached to prevent distributed mode activation conflicts.

:::note Sidecar Memory (2026-02-07)
The k8s-sidecar container (loki-sc-rules) watches ConfigMaps across many namespaces and needs 256Mi+ memory. The original 64Mi limit caused OOMKills. Loki canary resources are set via the top-level `lokiCanary.resources` key (not under `monitoring.selfMonitoring.lokiCanary`).
:::

**Service Endpoints:**

- Internal: `loki.loki.svc.cluster.local:3100`
- Push API: `http://loki.loki.svc.cluster.local:3100/loki/api/v1/push`
- Query API: `http://loki.loki.svc.cluster.local:3100/loki/api/v1/query`

**Key Features:**

- **TSDB Index:** Modern time-series database index for efficient queries
- **Compaction:** Runs every 10 minutes to reduce storage usage
- **Retention:** Automatically deletes logs older than 7 days
- **Filesystem Storage:** Uses PVC (no object storage required)

### Alloy DaemonSet

**Purpose:** log collection agent on every node, plus the OTLP trace receiver.

- **Pods:** 5/5 (one per node, control-plane included via toleration)
- **Image:** `grafana/alloy:v1.21.2`
- **Config:** `/etc/alloy/config.alloy`, served by a `config-reloader` sidecar that POSTs
  `http://localhost:12345/-/reload` when the ConfigMap changes
- **Ports:** `12345` (http-metrics / UI), `4317` (otlp-grpc), `4318` (otlp-http)
- **Containers per pod:**

| Container | CPU req/limit | Memory req/limit |
|---|---|---|
| `alloy` | 50m / 200m | 128Mi / 512Mi |
| `config-reloader` | 10m / 50m | 50Mi / 64Mi |

**Pipeline components** (Alloy is component-based, not a `scrape_configs` list):

```
discovery.kubernetes "pods"   ->  discovery.relabel "pods"
                              ->  loki.source.kubernetes "pods"
                              ->  loki.process "pods"
                              ->  loki.write "default"   (http://loki.loki.svc.cluster.local:3100)

otelcol.receiver.otlp "default" -> otelcol.exporter.otlp "tempo"
```

:::info Alloy reads the Kubernetes API, not host log files
`loki.source.kubernetes` streams logs through the API server rather than tailing
`/var/log/pods`. There is no `hostPID` and no host log mount — a meaningful difference from
Promtail when reasoning about NetworkPolicy and node access.
:::

**Total Resource Impact** (recomputed from the live cluster, 2026-10-26):

| | CPU requests | Memory requests | CPU limits | Memory limits |
|---|---|---|---|---|
| Loki StatefulSet ×1 (`loki` + `loki-sc-rules`) | 210m | 640Mi | 600m | 1024Mi |
| Alloy DaemonSet ×5 (`alloy` + `config-reloader`) | 300m | 890Mi | 1250m | 2880Mi |
| loki-canary DaemonSet ×4 (workers only) | 40m | 128Mi | 200m | 256Mi |
| **Total** | **550m** | **1658Mi (1.62Gi)** | **2050m** | **4160Mi (4.06Gi)** |

**Log Labeling:**
Alloy's `discovery.relabel "pods"` stage adds these labels to all logs:

- `namespace` - Kubernetes namespace
- `pod` - Pod name
- `container` - Container name
- `node` - Node name (useful for Pi cluster debugging)

#### Loki Label Limit (15 Labels Maximum)

:::warning Important
Loki has a default limit of 15 labels per log stream. Kubernetes pods with many labels (especially Istio, Helm-deployed apps) can exceed this limit.
:::

**Symptoms:**

```
entry for stream '{...17 labels...}' has 17 label names; limit 15
```

**Common high-label-count sources:**

- Istio pods (ztunnel, istio-cni-node): 17+ labels
- Helm-deployed StatefulSets: 16+ labels
- Apps with many `app.kubernetes.io/*` labels

**Solution - Selective labelmap:**

Don't use `labeldrop` after `labelmap` - it doesn't work because `relabel_configs` process against the original label set, not transformed labels.

Instead, use a selective `labelmap` regex to only capture essential labels:

Alloy expresses this in its own configuration language, inside
`discovery.relabel "pods"` (`manifests/base/alloy/values.yaml`):

```river
discovery.relabel "pods" {
  targets = discovery.kubernetes.pods.targets

  // Only scrape running pods
  rule {
    source_labels = ["__meta_kubernetes_pod_phase"]
    regex         = "Running"
    action        = "keep"
  }

  // Fixed labels
  rule {
    source_labels = ["__meta_kubernetes_namespace"]
    target_label  = "namespace"
  }
  rule {
    source_labels = ["__meta_kubernetes_pod_name"]
    target_label  = "pod"
  }
  rule {
    source_labels = ["__meta_kubernetes_pod_container_name"]
    target_label  = "container"
  }
  rule {
    source_labels = ["__meta_kubernetes_pod_node_name"]
    target_label  = "node"
  }

  // Selective labelmap — stay under Loki's 15-label limit
  rule {
    action = "labelmap"
    regex  = "__meta_kubernetes_pod_label_(app|app_kubernetes_io_name|app_kubernetes_io_instance|app_kubernetes_io_component|app_kubernetes_io_part_of|k8s_app|service_name)"
  }
}
```

The rule semantics are identical to Prometheus relabelling — only the syntax differs, so the
`labeldrop`-after-`labelmap` caveat above still applies.

**Label count after fix:**

- Fixed: namespace, pod, container, node (4)
- Mapped: up to 7 essential labels (only if present)
- Auto: filename, stream (2)
- **Total: max 13 labels** (under 15 limit)

:::note Added 2026-01-28
This fix was implemented after adding Istio Ambient mesh, which added many labels to pods.
:::

**Control-Plane Scheduling:**
Alloy carries a toleration so it runs on the control-plane node too:

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

- `hostNetwork: false`, which avoids the Calico CNI routing issues that affected the
  host-network approach
- Because `loki.source.kubernetes` reads through the API server, control-plane component logs
  arrive without any host path mount
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

## The Chart Default That Deletes the PVC

`manifests/base/loki/values.yaml` sets:

```yaml
singleBinary:
  persistence:
    enableStatefulSetAutoDeletePVC: false
```

**This is load-bearing.** The chart defaults it to `true` for `singleBinary` — and *only*
for `singleBinary`; `write`, `ingester`, `compactor`, `indexGateway` and both bloom
components all default to `false`. With it true, the StatefulSet renders:

```yaml
persistentVolumeClaimRetentionPolicy:
  whenDeleted: Delete
  whenScaled: Delete
```

Which means `kubectl scale statefulset loki --replicas=0` **deletes `storage-loki-0`**. That
is step 2 of our own documented [graceful shutdown](../kubernetes/cluster-maintenance.md), so
every planned shutdown was destroying Loki's claim.

### Why it is dangerous rather than merely annoying

The failure is silent and self-concealing. On restart the StatefulSet recreates
`storage-loki-0` from its `volumeClaimTemplate`, dynamically provisions a **brand new empty
20Gi LUN**, binds successfully, and Loki comes up **`Healthy` with no log history**. The old
LUN is orphaned on the NAS. Nothing alerts and ArgoCD reports `Synced`.

What an operator sees is a green cluster with empty logs — which reads as a retention setting,
not data loss.

Discovered 2026-10-24 during a shutdown for NAS patching, caught only because the cluster-wide
PVC count dropped from 8 to 7 mid-procedure. Nothing was lost, but **only** because
`synology-iscsi-retain` carries `reclaimPolicy: Retain`: the PV went `Released` instead of
being deleted, the LUN stayed on the NAS, and the claim could be re-bound by hand. On a
`-delete` StorageClass, 30 days of logs would have been gone.

### Auditing for it

Re-run this after **any** chart bump — a new chart version or a newly deployed stateful app
can reintroduce it:

```bash
kubectl get sts -A -o json | python3 -c "
import json,sys
for s in json.load(sys.stdin)['items']:
    pol = s['spec'].get('persistentVolumeClaimRetentionPolicy') or {}
    if pol.get('whenScaled') == 'Delete':
        print('HAZARD:', s['metadata']['namespace'] + '/' + s['metadata']['name'], pol)"
```

Verified still correct under chart 7.5.0 (2026-10-26). The other four PVC-owning StatefulSets
— Prometheus, Tempo, Zot, trivy-server — were already `Retain`/`Retain`.

### Recovering a deleted claim

Only possible while the PV is still `Released`, which requires a `*-retain` StorageClass:

```bash
PV=$(kubectl get pv --no-headers | awk '$5=="Released" {print $1}')
kubectl patch pv $PV --type=json -p '[{"op":"remove","path":"/spec/claimRef"}]'   # -> Available
```

Then recreate the PVC with an explicit `volumeName: $PV`, matching the
`volumeClaimTemplate`'s size, `storageClassName` and `accessModes` exactly. It binds to the
existing volume instead of provisioning a new one.

Confirm the data actually survived by querying how far back Loki can serve, rather than
trusting that the pod started:

```bash
kubectl port-forward -n loki svc/loki 3100:3100 &
START=$(python3 -c "import time; print(int((time.time()-30*86400)*1e9))")
curl -s -G http://127.0.0.1:3100/loki/api/v1/query_range \
  --data-urlencode 'query={namespace="kube-system"}' \
  --data-urlencode "start=$START" --data-urlencode 'limit=1' \
  --data-urlencode 'direction=forward'
```

An oldest entry near the retention window means the volume is intact; only today's logs means
it came back empty.

:::note Loki's image tag lags the chart appVersion
Chart 7.5.0 declares `appVersion: 3.6.16` but renders `grafana/loki:3.6.11`. That is the
chart's own default, not drift — compare `helm template` output against the running image
before concluding a bump did not apply.
:::

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

## Ingestion Limits — and the Mismatch That Dropped 0.5% of Logs

`reject_old_samples_max_age` **must match `retention_period`**. Loki's default is 168h
(7 days); this cluster retains for 720h (30 days). Until 2026-09-21 only the retention side
was set, so log data well inside the retention window could not be written at all.

```yaml
limits_config:
  retention_period: 720h
  reject_old_samples_max_age: 720h   # keep these equal
```

### Why the cost is far higher than the stale lines

**Loki rejects an entire batch with HTTP 400 when one entry is too old**, and alloy then
drops the whole batch — so current log lines are lost alongside the stale one.

The two counters disagree by a factor of forty, and reading the wrong one understates the
damage badly:

| Counter | 24h | What it means |
|---|---|---|
| `loki_discarded_samples_total` | 1,852 | entries Loki *examined* and rejected |
| `loki_write_dropped_entries_total` | **72,008** | entries **alloy actually lost** |
| `loki_distributor_lines_received_total` | 14,293,553 | successfully ingested |

:::danger Use the alloy counter, not the Loki one
An initial assessment called this "0.006%, no action needed" based on
`loki_discarded_samples_total`. That counter only counts entries Loki got far enough to
examine — not the batches it threw away whole. The real figure was **~0.5%**.
:::

### Why it never self-resolves

Every stale entry dated to a single moment: `2026-09-13T06:40`, when `loki-0` restarted.
Long-lived DaemonSet pods (`synology-csi-node`, `csi-node-driver`, `calico-typha`) still held
those lines in their container log files, and alloy retried them indefinitely — **failing
harder each day** as the 168h window slid forward and the entries aged further out of range.
Raising the limit let the backlog drain; drops went to zero within minutes.

Loki 3.6.11 accepts out-of-order writes, so late arrivals are safe.

## The Ruler Alerts On Its Own Logs

:::danger Any LogQL rule matching log TEXT must exclude `namespace="loki"`
Loki's ruler **logs the full text of every query it evaluates**:

```
caller=metrics.go component=ruler ... query="(sum by (namespace,pod)
  (rate({namespace=~\".+\"} |~ \"(?i)(attack|intrusion|exploit|malicious|suspicious)\"...
```

Alloy ships those lines straight back into Loki. The next evaluation matches **its own logged
query string**, so the alert fires forever and can never clear.
:::

Confirmed 2026-09-19: `OOMKilledDetected`, `CrashLoopBackOffDetected` and `SuspiciousActivity`
each matched **exactly one series — `loki/loki-0`** — and nothing else in the cluster. Three of
them were `critical`. With `namespace!="loki"` added, all three return zero series.

Every rule in `loki-alerting-rules.yaml` now carries the guard:

```logql
{namespace=~".+", namespace!="loki"} |~ "(?i)(oomkilled|out of memory)"
```

### These rules are coarse by nature

They detect a pod that **logs** a phrase, not a pod the phrase is **about**. A container that
gets OOM-killed does not log "oomkilled" — the kernel kills it and the kubelet records the
reason. Treat them as a wide net; metric-based alerts are authoritative. See
[`KubeContainerOOMKilled`](../monitoring/overview.md#oom-detection) for the metric-based
equivalent added afterwards.

:::danger A bare word is not a severity

On 2026-10-16 `CriticalErrorLogs` fired at 02:02 claiming *"critical/fatal errors at
263.3m/s"* against `snapshot-controller`. There were none. Every matching line was **INFO**:

```text
I1016 02:02:40 ... setAnnVolumeSnapshotBeingDeleted: volume snapshot content
  &{... Labels:map[velero.io/backup-name:velero-daily-critical-pvcs-20261016020049] ...}
```

The pattern was `|~ "(?i)(critical|fatal|panic|emergency)"`. The word **critical** came from
the nightly backup schedule name `velero-daily-critical-pvcs`, embedded in a label on the
VolumeSnapshotContent object the controller dumps in full at info level. The alert had been
firing **every night at ~02:00** for as long as that schedule has existed.

**Word boundaries do not fix this.** `\bcritical\b` still matches inside
`velero-daily-critical-pvcs`, because a hyphen *is* a word boundary. Severity has to be
matched structurally, in the forms the cluster actually emits:

```text
^F[0-9]{4}                        klog fatal
level=(fatal|critical|emerg)      logfmt
"level":"(fatal|critical|emerg)"  json
[FATAL] / [CRITICAL]              bracketed
panic:                            go runtime
```

When changing one of these patterns, test it **in both directions against real log lines
pulled from Loki** — true positives that must still match, and the false positives you are
removing. Then test it again *after* the YAML round-trip, by reading the regex back out of
the parsed ConfigMap: escaping through YAML is exactly where a pattern silently changes.
:::

:::warning The rules live inside a ConfigMap `data:` key
`yamllint` and `kubeconform` validate the *outer* document and never parse that string. On
2026-09-19 a comment at the wrong indentation left the rules unparseable and **the ruler ran
with zero rules loaded** while every check passed. A pre-commit hook now parses embedded
blobs — see [Pre-commit & CI](../development/pre-commit-ci.md).

Verify what the ruler actually holds, rather than trusting a successful sync:

```bash
kubectl -n loki port-forward sts/loki 3100:3100
curl -s localhost:3100/loki/api/v1/rules | head
```

A parse failure is reported there and nowhere else.
:::

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

**Check Alloy pods are running:**

```bash
kubectl get pods -n loki -l app.kubernetes.io/name=alloy
# Expect: 5 pods (one per node, control-plane included)
```

**Check Alloy logs:**

```bash
kubectl logs -n loki -l app.kubernetes.io/name=alloy -c alloy --tail=50
# Look for component errors, or loki.write push failures
```

:::tip Inspect the live pipeline instead of guessing
Alloy serves a UI on port 12345 that shows every component's health and its current
evaluation — far faster than reading logs when a stage is misconfigured:

```bash
kubectl port-forward -n loki ds/alloy 12345:12345
# then open http://localhost:12345
```

:::

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

ServiceMonitors are **enabled** for both Loki and Alloy, allowing Prometheus to scrape metrics automatically.

### Prometheus Integration

**ServiceMonitor Configuration:**

```yaml
# Loki
monitoring:
  serviceMonitor:
    enabled: true
    labels:
      release: kube-prometheus-stack

# Alloy
serviceMonitor:
  enabled: true
  labels:
    release: kube-prometheus-stack
```

**Verify ServiceMonitors:**

```bash
kubectl get servicemonitor -n loki
# Expected: loki and alloy ServiceMonitors
```

**Check Prometheus Targets:**

```bash
# Port-forward to Prometheus
kubectl port-forward -n default svc/kube-prometheus-stack-prometheus 9090:9090

# Navigate to: http://localhost:9090/targets
# Look for: serviceMonitor/loki/loki and serviceMonitor/loki/alloy
```

### Key Metrics to Watch

Loki and Alloy metrics are available in Prometheus:

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

**Alloy Metrics (per pod × 5):**

:::warning `promtail_*` metrics no longer exist
Alloy exports under `alloy_*` and, for the Loki pipeline components, `loki_write_*`. Verified
2026-10-26: `promtail_sent_entries_total` returns **0 series**, so any dashboard or alert still
referencing the old names is silently broken rather than erroring.
:::

```promql
# Entries successfully pushed to Loki (rate)
sum(rate(loki_write_sent_entries_total[5m]))

# Entries DROPPED — the one to alert on. A sustained non-zero rate means
# Loki is rejecting writes (see the reject_old_samples section above).
sum(rate(loki_write_dropped_entries_total[5m])) by (reason)

# Bytes dropped
sum(rate(loki_write_dropped_bytes_total[5m]))

# Push retries — climbing means Loki is backpressuring
sum(rate(loki_write_batch_retries_total[5m]))

# End-to-end push latency
histogram_quantile(0.99, sum(rate(loki_write_entry_propagation_latency_seconds_bucket[5m])) by (le))

# Alloy health: components running vs failing to evaluate
alloy_component_controller_running_components
alloy_build_info
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

The following 9 alert rules are deployed across 4 groups:

#### 1. Log Errors (Group: `log_errors`)

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

#### 2. Pod Failures (Group: `pod_failures`)

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

#### 3. Application Errors (Group: `application_errors`)

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

#### 4. Security Events (Group: `security_events`)

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

**Check the ruler is running.** There is no separate ruler pod — `ruler.enabled` is
`false` and the ruler runs *embedded in the singleBinary pod*, reading rules from `/rules`:

```bash
kubectl logs -n loki loki-0 -c loki --tail=50 | grep -i ruler
# Look for the ruler starting and evaluating groups
```

**Check Ruler Logs:**

```bash
kubectl logs -n loki -l app.kubernetes.io/component=ruler --tail=50
# Look for "ruler started" and "evaluating rules"
```

**Verify the rules are mounted.** These are **LogQL** rules served by Loki's own ruler, so
they live in a ConfigMap — not a PrometheusRule:

```bash
kubectl get cm -n loki loki-alerting-rules
kubectl get cm -n loki loki-alerting-rules -o jsonpath='{.data}' | head -c 400
```

**Check Alert Rules in Prometheus:**

```bash
# Port-forward to Prometheus
kubectl port-forward -n default svc/kube-prometheus-stack-prometheus 9090:9090

# Navigate to: http://localhost:9090/alerts
# Look for alerts with prefix "loki" or check the "log_errors" group
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

**Alloy:**

- Path: `manifests/applications/alloy.yaml`
- Sync Wave: `-11`
- Destination: `loki` namespace

### Helm Values

**Loki Configuration:**

- Path: `manifests/base/loki/values.yaml`
- Key settings: deployment mode, storage, retention

**Alloy Configuration:**

- Path: `manifests/base/alloy/values.yaml`
- Key settings: resources, the `config.alloy` pipeline (discovery, relabel, source, process,
  write), the selective `labelmap`, the `stage.drop` age guard, and the OTLP → Tempo exporter

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

   ```river
   // In manifests/base/alloy/values.yaml, inside loki.source.kubernetes.
   // Not currently tuned — Alloy streams from the API server rather than
   // polling files, so there is no scrape-interval knob to reduce.
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
  name: loki-allow-alloy
  namespace: loki
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: loki
  ingress:
    - from:
      - podSelector:
          matchLabels:
            app.kubernetes.io/name: alloy
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

### Alloy Chart Upgrades

```bash
# Update chart version in manifests/applications/alloy.yaml
targetRevision: 1.14.3  # current

# Commit and push
git commit -am "chore: Upgrade Alloy to 1.14.3"
git push
```

:::warning Re-verify the `stage.drop` age guard after an Alloy bump
`manifests/base/alloy/values.yaml` carries a `stage.drop { older_than = "696h" }` that keeps
stale entries from poisoning whole batches against Loki's reject window. It survived the
1.14.3 bump, but confirm it still renders after any chart change — losing it silently
reintroduces whole-batch rejection.
:::

## Related Documentation

- [Monitoring Overview](../monitoring/overview.md)
- [kube-prometheus-stack](kube-prometheus-stack.md)
- [Storage Configuration](../storage/synology-csi.md)
- [Troubleshooting Monitoring](../troubleshooting/monitoring.md)

## External Resources

- [Grafana Loki Documentation](https://grafana.com/docs/loki/latest/)
- [LogQL Query Language](https://grafana.com/docs/loki/latest/logql/)
- [Grafana Alloy Documentation](https://grafana.com/docs/alloy/latest/)
- [`loki.source.kubernetes` reference](https://grafana.com/docs/alloy/latest/reference/components/loki/loki.source.kubernetes/)
- [Loki Helm Chart](https://github.com/grafana/loki/tree/main/production/helm/loki)
