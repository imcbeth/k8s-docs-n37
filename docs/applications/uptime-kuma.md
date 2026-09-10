---
title: "Uptime Kuma"
description: "Self-hosted uptime monitoring and status page for cluster services"
---

# Uptime Kuma

Uptime Kuma is a self-hosted uptime monitoring tool that provides a real-time status page for all cluster services. It integrates with Prometheus for metrics and AlertManager for alerting.

## Overview

| Property | Value |
|----------|-------|
| **Namespace** | `uptime-kuma` |
| **Chart** | `helm-charts/uptime-kuma` v4.2.0 |
| **App Version** | **`2.5.3`** — migrated from `1.23.17-debian` on 2026-09-07 (PR #908). See [The 1.x → 2.x migration](#the-1x--2x-migration-2026-09-07). |
| **ArgoCD App** | `uptime-kuma` (project: `infrastructure`, wave: `0`) |
| **Status Page URL** | `https://status.k8s.n37.ca` |
| **Storage** | 5Gi iSCSI PVC (`synology-iscsi-delete`) |
| **Auth** | GitHub SSO via oauth2-proxy |

## Purpose

Uptime Kuma provides two capabilities:

1. **Status page** — Public-facing dashboard at `https://status.k8s.n37.ca` showing real-time health of all cluster services (HTTP, HTTPS, TCP, DNS checks).
2. **Prometheus metrics** — Exports `monitor_status`, `monitor_cert_days_remaining`, and related metrics, enabling AlertManager to fire alerts when monitors go down or TLS certificates are about to expire.

## Architecture

```
External users
     │
     ▼
ingress-nginx ──► oauth2-proxy (GitHub SSO) ──► Uptime Kuma UI
                                                      │
                                               Prometheus ◄── ServiceMonitor
                                                      │           (default namespace,
                                               AlertManager     namespaceSelector: uptime-kuma)
                                                      │
                                               Email alerts
```

## Prometheus Integration

:::danger /metrics uses HTTP Basic auth, not Bearer
Uptime Kuma's `/metrics` endpoint expects **HTTP Basic** with an *empty username* and the API key as the *password*. A ServiceMonitor using `authorization.credentials` sends `Authorization: Bearer <key>` and gets **HTTP 401**.

This cost 38 days of a dark scrape target (2026-07-30 → 2026-09-06). The API key was valid the whole time; only the scheme was wrong. Verified from the Prometheus pod:

| Auth sent | Result |
|---|---|
| none | 401 |
| `Authorization: Bearer <key>` | 401 |
| `Authorization: Basic base64(":" + <key>)` | **200 + metrics** |

Correct ServiceMonitor shape — note the secret needs **both** a `username` and a `password` key (username is an empty string):

```yaml
endpoints:
  - port: http
    path: /metrics
    interval: 60s
    basicAuth:
      username:
        name: uptime-kuma-metrics-token
        key: username        # empty string
      password:
        name: uptime-kuma-metrics-token
        key: password        # the uk1_... API key
```

Reproduce the check by hand:

```bash
KEY=$(kubectl get secret -n default uptime-kuma-metrics-token -o jsonpath='{.data.password}' | base64 -d)
IP=$(kubectl get endpoints -n uptime-kuma uptime-kuma -o jsonpath='{.subsets[0].addresses[0].ip}')
kubectl -n default exec prometheus-kube-prometheus-stack-prometheus-0 -c prometheus -- \
  wget -S -qO- --header="Authorization: Basic $(printf ':%s' "$KEY" | base64)" \
  "http://$IP:3001/metrics" 2>&1 | head -3
```

:::

### ServiceMonitor

The ServiceMonitor lives in the **`default` namespace** (alongside Prometheus), not in `uptime-kuma`. This is required because Prometheus Operator RBAC only permits reading bearer token secrets from the namespace where Prometheus runs.

**Location:** `manifests/base/kube-prometheus-stack/uptime-kuma-servicemonitor.yaml`

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: uptime-kuma
  namespace: default
  labels:
    release: kube-prometheus-stack
spec:
  namespaceSelector:
    matchNames:
      - uptime-kuma
  selector:
    matchLabels:
      app.kubernetes.io/name: uptime-kuma
  endpoints:
    - port: http
      path: /metrics
      interval: 60s
      authorization:
        credentials:
          name: uptime-kuma-metrics-token
          key: token
```

### API Token

Uptime Kuma requires an API token for Prometheus to access the `/metrics` endpoint. The token is stored as a SealedSecret in the `default` namespace:

**Location:** `manifests/base/kube-prometheus-stack/uptime-kuma-metrics-token-sealed.yaml`

To generate a new API token:

1. Log in to Uptime Kuma UI
2. Go to **Settings → API Keys**
3. Create a new key with read access
4. Re-seal it: `echo -n '<token>' | kubectl create secret generic uptime-kuma-metrics-token --from-file=token=/dev/stdin -n default --dry-run=client -o json | kubeseal --controller-name sealed-secrets-controller --controller-namespace kube-system --format yaml`
5. Apply immediately: `kubectl apply -f manifests/base/kube-prometheus-stack/uptime-kuma-metrics-token-sealed.yaml`

:::warning Cross-namespace secret references fail silently
If the token secret is placed in the `uptime-kuma` namespace while the ServiceMonitor is in `default`, Prometheus sends requests with no bearer token and receives `401 Unauthorized`. The scrape target appears down with no obvious error. Always keep the secret in the same namespace as Prometheus.
:::

## Alerting Rules

**Location:** `manifests/base/uptime-kuma/prometheusrule.yaml`

| Alert | Condition | Severity | For |
|-------|-----------|----------|-----|
| `UptimeKumaMonitorDown` | `monitor_status == 0` | critical | 2m |
| `UptimeKumaMonitorCertExpirySoon` | `monitor_cert_days_remaining < 14` | warning | 1h |

The PrometheusRule is deployed in the `uptime-kuma` namespace with label `release: kube-prometheus-stack` so the Prometheus Operator discovers it across namespaces.

## Deployment Configuration

### Application Manifest

**Location:** `manifests/applications/uptime-kuma.yaml`

The ArgoCD Application uses three sources:

1. **Helm chart** — `helm-charts/uptime-kuma` chart with `values.yaml`
2. **Values ref** — homelab repo as ref source for value files
3. **Kustomize manifests** — `manifests/base/uptime-kuma/` for PrometheusRule

:::warning Application manifests require manual apply
`manifests/applications/uptime-kuma.yaml` is not auto-deployed by ArgoCD self-management. After changes, run:

```bash
kubectl apply -f manifests/applications/uptime-kuma.yaml
```

:::

### Key Helm Values

```yaml
ingress:
  enabled: true
  hosts:
    - host: status.k8s.n37.ca
  annotations:
    # GitHub SSO via oauth2-proxy
    nginx.ingress.kubernetes.io/auth-url: "http://oauth2-proxy.oauth2-proxy.svc.cluster.local/oauth2/auth"
    nginx.ingress.kubernetes.io/auth-signin: "https://oauth.k8s.n37.ca/oauth2/start?rd=$scheme%3A%2F%2F$host$escaped_request_uri"
    nginx.ingress.kubernetes.io/auth-response-headers: "X-Auth-Request-User,X-Auth-Request-Email"
    # WebSocket support (Uptime Kuma uses socket.io)
    nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "3600"

persistence:
  enabled: true
  storageClass: synology-iscsi-delete
  size: 5Gi

strategy:
  type: Recreate  # Required for RWO iSCSI PVC
```

## Resource Usage

| Component | CPU Request | CPU Limit | Memory Request | Memory Limit |
|-----------|-------------|-----------|----------------|--------------|
| uptime-kuma | 50m | 200m | 128Mi | 256Mi |

## Common Operations

:::warning Monitors are the cluster's one significant piece of unmanaged state
Every other piece of cluster configuration is declared in git and reconciled by ArgoCD. **Monitor definitions are not.** They live in Uptime Kuma's SQLite database on its PVC and can only be created, edited or deleted through the web UI. Consequences:

- Monitor changes are **invisible to code review** and leave no audit trail.
- There is no drift detection — a monitor deleted by accident is simply gone.
- **They cannot be fixed by a PR.** During the 2026-09-07 alert triage, a monitor pointing at a Flink batch demo (a Service that only exists while a job runs) had to be handed back for a manual UI click, because no GitOps change could touch it.

Recovery relies on Velero backing up the PVC — which **now** works, as of PR #907; before that this namespace was in no backup schedule at all. Restore granularity is the whole database, not one monitor.

**This gap is NOT closed by the 2.x migration.** An earlier version of this page claimed 2.5.3 added a REST API for monitor CRUD. Probing the running instance on 2026-09-09 disproved it:

| Endpoint | Content-Type | Verdict |
|---|---|---|
| `/api/monitors` | `text/html` | SPA fallback |
| `/api/v1/monitors` | `text/html` | SPA fallback |
| `/api/entry-page` | `application/json` | real |
| `/api/totally-made-up-xyz` | `text/html` | **control** |

All four returned **HTTP 200** — unknown routes fall through to `index.html`, so a 200 proves nothing without a known-negative control.

Uptime Kuma's programmatic interface remains **socket.io**. Declarative management would mean implementing an unofficial protocol and maintaining it across upgrades.

The cheaper option is **drift detection** rather than reconciliation: export monitors from the SQLite DB on a schedule, diff against a committed list, and alert on divergence. That buys visibility and change detection without the protocol risk — but not declarative management.
:::

### Adding a Monitor

1. Log in to `https://status.k8s.n37.ca`
2. Click **Add New Monitor**
3. Select monitor type (HTTP/HTTPS, TCP, DNS, etc.)
4. Configure check interval and alert thresholds
5. Assign to a status page group

:::tip Only monitor things that are meant to be up
A monitor pointing at a batch job's Service reports `DOWN` for the entire time no job is running — which is most of the time, and is correct behaviour rather than a fault. `UptimeKumaMonitorDown` then fires forever and the whole monitor set gets ignored. Monitor **services**; use workflow/job alerting for batch work.
:::

## Monitor drift detection (2026-09-10)

Since monitors cannot be managed declaratively, they are at least **watched**. A daily CronJob diffs the live monitor set against a baseline committed to git and fails when they diverge.

```
uptime-kuma-monitor-drift (CronJob, 06:40 daily)
  → kubectl exec into the app pod, read the SQLite monitor table
  → normalise to  name|type|target|active=N|interval=N
  → diff against the uptime-kuma-monitor-baseline ConfigMap
  → exit non-zero on divergence  →  UptimeKumaMonitorDrift alert
```

### It detects; it cannot repair

There is no monitor API to reconcile against, so a human applies the change in the UI and then refreshes the baseline **via a PR**. That is deliberate: the PR diff is the audit trail these monitors otherwise do not have. Editing the ConfigMap in place defeats the point.

### Design choices worth knowing

**Five fields, not 120.** The `monitor` table has ~120 columns. The comparison uses `name`, `type`, target, `active` and `interval` — what a human would notice changing. Diffing every column would alert on things like retry counters.

**An edited monitor appears in BOTH lists** — once as the old definition removed, once as the new one added. That is one change, not two faults, and the job output says so.

**Zero-monitor guard.** Reading 0 monitors while 14 are declared almost certainly means the query or schema changed, not that everything was deleted. It reports that rather than 14 spurious deletions.

**It execs**, because the PVC is RWO and already mounted by the app — a second pod cannot read the database. The Role is scoped to the one namespace and grants `pods/exec` create plus `pods` get/list, nothing that can write.

### Two traps hit while building it

:::warning ArgoCD selfHeal defeats in-cluster test perturbation
The first negative test patched the baseline ConfigMap directly to inject drift. **ArgoCD reverted it before the job ran**, so the check reported OK — a false pass that looked exactly like a working detector.

The same mechanism defeated a `kubectl scale --replicas=0` on LocalStack the day before. To test against a GitOps-managed object, use a throwaway object ArgoCD does not manage — here, a separate ConfigMap the one-off Job mounts instead.
:::

:::warning The namespace NetworkPolicy blocks the Kubernetes API
`uptime-kuma`'s NetworkPolicy uses `podSelector: {}` — it covers every pod — and allows DNS plus the HTTP ports the app probes. It does **not** allow 6443, which is correct for Uptime Kuma itself; a monitoring app has no business talking to the API.

A job that must exec does need it. Policies are additive, so the fix is a second policy scoped by `podSelector` to the drift pods, **not** widening the namespace-wide one.

This first surfaced as `no Running uptime-kuma pod found` while the app had been up 20 hours, because the lookup was written `2>/dev/null || echo ""` — a 2.5-minute connection timeout and an empty result are indistinguishable when you discard stderr.
:::

## The 1.x → 2.x migration (2026-09-07)

Migrated `1.23.17-debian` → `2.5.3`. Completed in ~58 minutes with **zero restarts** and no data loss.

### Two things that would have broken it

**1. The tag suffix silently disappeared.** 1.x published `-debian` variants; **2.x dropped the suffix entirely.** The unsuffixed tag *is* the Debian build, and `-slim` is the smaller one. Writing `2.5.3-debian` by analogy yields an `ImagePullBackOff`, not a useful error.

The `-rootless` variants are a separate trap: they run as uid 1000 and **cannot write this PVC**, whose files are `root:root 755`. Switching to rootless requires a `chown` first. The unsuffixed image runs as root, matching 1.x, which is why the migration needed no ownership work.

**2. The liveness probe would have killed the migration mid-write.** This is the one that mattered.

Uptime Kuma rewrites its schema on first start, and here also re-aggregated **1.95M heartbeat rows** off an iSCSI PVC. The existing probe was `initialDelaySeconds: 180` with `failureThreshold: 3` at `periodSeconds: 30` — so the kubelet would have killed the container roughly **270 seconds in**, on a half-rewritten SQLite database, and then done it again on every restart.

Measured rate was **~2%/minute**, i.e. ~58 minutes. The migration was never going to finish inside 270s.

```yaml
# Raised for the migration, reverted afterwards (PR #909)
livenessProbe:
  initialDelaySeconds: 900   # was 180
```

:::caution Raise this before any future major upgrade of this app
900s is correct for a migration and wrong for steady state — a wedged pod goes uncaught for 15 minutes. It was returned to 180 once the migration finished and the pod had rolled cleanly. Any future major version bump needs the same temporary raise.
:::

### What the logs look like

The schema conversion — the irreversible part — finishes in the first ~90 seconds and the pod goes `Ready`. A **second, much longer pass** then runs in the background while the app serves normally:

```
[DB] INFO: Migrating Aggregate Table
[DB] INFO: [DON'T STOP] Migrating monitor '...' (1 of 14 total) - total migration progress 0.07%
...
[DB] INFO: Aggregate Table Migration Completed
```

`[DON'T STOP]` is literal. A `Ready` pod does **not** mean the migration is done. Do not restart the pod, sync the app, or drain its node until `Aggregate Table Migration Completed` appears.

### Heartbeat counts drop, and that is correct

| Table | Before | After |
|---|---|---|
| `heartbeat` (raw) | 1,950,590 | **31,957** |
| `stat_daily` | — | 1,400 |
| `stat_hourly` | — | 10,094 |
| `stat_minutely` | — | 20,172 |

2.x rolls history into aggregate tables and keeps raw rows only for a recent window. `stat_daily` reaches back to **2026-06-02**, the original earliest data — uptime percentages and graphs are intact. Only raw per-check detail beyond the retention window is pruned. A 97% drop in `heartbeat` rows is the expected outcome, not data loss.

### Rollback

The migration is **one-way** — a 2.x database cannot be opened by 1.x. Rollback is restore-from-backup only. Three artifacts were taken first, each verified `pragma integrity_check: ok` with 14 monitors / 1,950,531 heartbeats:

1. `/app/data/pre2x.db` on the PVC (via sqlite3 `.backup`, so the 138MB WAL is folded in — a plain `cp` would have silently lost it)
2. An off-cluster gzip of the same file
3. The nightly Velero schedule, which covers this namespace as of PR #907

:::danger This PVC had never been backed up
Preparing this migration is what surfaced it: `uptime-kuma` held a 135-day-old 5Gi PVC that **no Velero schedule covered**, on a `synology-iscsi-delete` StorageClass with no reclaim-policy safety net. Backups had been reporting `Completed` the entire time — the namespace was simply outside their scope. See [Velero → backup coverage](./velero.md#backup-coverage-is-not-backup-success-2026-09-07).
:::

### Checking Prometheus Metrics

```bash
# Verify scrape target is up
kubectl port-forward svc/kube-prometheus-stack-prometheus -n default 9090:9090
# Open http://localhost:9090/targets → search "uptime-kuma"

# Query monitor status directly
curl -s http://localhost:9090/api/v1/query?query=monitor_status | jq .
```

### Verifying API Token

```bash
# Check secret exists in default namespace
kubectl get secret uptime-kuma-metrics-token -n default

# Verify token value (first 20 chars)
kubectl get secret uptime-kuma-metrics-token -n default \
  -o jsonpath='{.data.token}' | base64 -d | head -c 20
```

## Troubleshooting

### 401 Unauthorized on Prometheus Scrape

The token secret must be in the `default` namespace, not `uptime-kuma`. See [Prometheus Integration](#prometheus-integration) above.

```bash
kubectl get secret uptime-kuma-metrics-token -n default
```

If missing, re-apply the SealedSecret:

```bash
kubectl apply -f manifests/base/kube-prometheus-stack/uptime-kuma-metrics-token-sealed.yaml
```

### WebSocket Connection Lost

Uptime Kuma uses socket.io for real-time updates. If the UI shows "disconnected" after a few seconds, verify the proxy timeouts:

```bash
kubectl get ingress -n uptime-kuma -o yaml | grep -E "timeout|websocket"
```

Both `proxy-read-timeout` and `proxy-send-timeout` must be `3600` (seconds).

### Pod Won't Start (iSCSI)

Uptime Kuma uses a RWO iSCSI PVC. Only one node can mount it at a time. If the pod is rescheduled:

```bash
# Check pod events
kubectl describe pod -n uptime-kuma -l app.kubernetes.io/name=uptime-kuma

# If VolumeAttachment is stuck on old node, delete the pod to reschedule
kubectl delete pod -n uptime-kuma -l app.kubernetes.io/name=uptime-kuma
```

## References

- [Uptime Kuma GitHub](https://github.com/louislam/uptime-kuma)
- [Helm Chart](https://helm.sh/docs/helm/helm_install/)
- [oauth2-proxy Integration](./oauth2-proxy.md)

---

**Last Updated:** 2026-06-01
