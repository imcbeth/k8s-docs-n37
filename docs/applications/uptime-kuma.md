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
| **Chart** | `helm-charts/uptime-kuma` v4.0.0 |
| **App Version** | `v1.23.17` |
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

### Adding a Monitor

1. Log in to `https://status.k8s.n37.ca`
2. Click **Add New Monitor**
3. Select monitor type (HTTP/HTTPS, TCP, DNS, etc.)
4. Configure check interval and alert thresholds
5. Assign to a status page group

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

**Last Updated:** 2026-05-03
