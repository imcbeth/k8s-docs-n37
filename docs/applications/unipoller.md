---
title: "UniFi Poller"
description: "UniFi network monitoring with Prometheus integration"
---

# UniFi Poller

UniFi Poller collects metrics from UniFi network controllers and exposes them in Prometheus format for monitoring and visualization.

## Overview

- **Namespace:** `unipoller`
- **Image:** `ghcr.io/unpoller/unpoller:v2.33.0`
- **Deployment:** Managed by ArgoCD
- **Sync Wave:** `-20` (deploys after storage, before monitoring stack)

## Purpose

UniFi Poller provides comprehensive network monitoring by:

- Collecting device metrics from UniFi controller
- Exposing metrics in Prometheus format
- Tracking network performance, client connections, and device health
- Providing visibility into UniFi infrastructure

## Configuration

### UniFi Controller Connection

- **Controller URL:** `https://10.0.1.1`
- **Site:** `n37-gw`
- **Authentication:** API Key (stored in Secret)
- **TLS Verification:** Disabled (controller has self-signed certificate)
- **Scrape Interval:** 20 seconds (configured in Prometheus)

### Resource Limits

```yaml
resources:
  requests:
    cpu: 100m
    memory: 256Mi
  limits:
    cpu: 200m
    memory: 512Mi
```

These limits are appropriate for the Raspberry Pi cluster while ensuring reliable operation.

## Metrics Endpoint

- **Service:** `unifi-poller.unipoller:9130`
- **Path:** `/metrics`
- **Protocol:** HTTP

## Prometheus Integration

UniFi Poller is automatically scraped by Prometheus via the following job configuration:

```yaml
- job_name: 'unpoller'
  static_configs:
    - targets: ['unifi-poller.unipoller:9130']
  scrape_interval: 20s
  scrape_timeout: 10s
```

## Collected Metrics

UniFi Poller exposes a wide range of metrics including:

### Device Metrics

- Device uptime and status
- CPU and memory utilization
- Temperature readings
- Firmware versions

### Network Metrics

- Port statistics (bytes in/out, packets)
- Error rates
- Link speed and duplex
- PoE power consumption

### Client Metrics

- Connected clients count
- Client signal strength
- Bandwidth usage per client
- Connection duration

### Wireless Metrics

- SSID statistics
- Channel utilization
- Interference levels
- Roaming events

## Deployment via ArgoCD

UniFi Poller is deployed using GitOps through ArgoCD:

**Application Manifest:** `manifests/applications/unipoller.yaml`

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: unipoller
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "-20"
spec:
  project: infrastructure
  source:
    path: manifests/base/unipoller
    repoURL: git@github.com:imcbeth/homelab.git
    targetRevision: HEAD
  destination:
    server: https://kubernetes.default.svc
    namespace: unipoller
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

## Deployed Resources

The application creates the following Kubernetes resources:

1. **Deployment:** Single replica of UniFi Poller
2. **Service:** ClusterIP service exposing port 9130
3. **ConfigMap:** Configuration for UniFi controller connection
4. **Secret:** UniFi controller API key credentials

## Authentication

UniFi Poller uses **API key authentication** to connect to the UniFi controller. This is more secure than username/password authentication and supports better access control.

### Creating a UniFi API Key

1. Log into your UniFi Console at `https://10.0.1.1`
2. Navigate to **Settings** → **Integrations** → **API**
3. Click **Create API Key**
4. **Name:** `unipoller-k8s`
5. **Permissions:** Grant network monitoring permissions
6. Copy the API key (you won't be able to see it again)

### Configuring the Secret

The API key is managed via **SealedSecret** for GitOps compatibility:

- **SealedSecret:** `manifests/base/unipoller/unipoller-sealed.yaml`
- **Decrypted Secret:** `unipoller-secret` in `unipoller` namespace

To update the API key, create a new SealedSecret:

```bash
# 1. Create temporary secret YAML (DO NOT commit)
cat > /tmp/unipoller-secret.yaml <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: unipoller-secret
  namespace: unipoller
type: Opaque
stringData:
  api-key: "YOUR_NEW_API_KEY_HERE"
EOF

# 2. Seal the secret
kubeseal --cert <(kubectl get secret -n kube-system \
  -l sealedsecrets.bitnami.com/sealed-secrets-key=active \
  -o jsonpath='{.items[0].data.tls\.crt}' | base64 -d) \
  --format yaml < /tmp/unipoller-secret.yaml > manifests/base/unipoller/unipoller-sealed.yaml

# 3. Delete temporary file and commit
rm /tmp/unipoller-secret.yaml
git add manifests/base/unipoller/unipoller-sealed.yaml
git commit -m "feat: Update unipoller API key"
git push
```

The deployment references this secret via environment variable:

```yaml
env:
- name: UP_UNIFI_CONTROLLER_0_API_KEY
  valueFrom:
    secretKeyRef:
      name: unipoller-secret
      key: api-key
```

See [Secrets Management](../security/secrets-management.md) for details on SealedSecrets.

## Monitoring and Dashboards

### Grafana Dashboards

UniFi Poller metrics can be visualized in Grafana. Common dashboard panels include:

- Network throughput over time
- Connected clients by device
- Device health and uptime
- Wireless performance metrics
- PoE power consumption

### Common Queries

**Total connected clients:**

```promql
sum(unifi_device_client_count)
```

**Network throughput:**

```promql
rate(unifi_device_bytes_total[5m])
```

**Device uptime:**

```promql
unifi_device_uptime_seconds
```

## Troubleshooting

### Check Pod Status

```bash
kubectl get pods -n unipoller
```

### View Logs

```bash
kubectl logs -n unipoller deployment/unifi-poller
```

### Verify Metrics Endpoint

```bash
kubectl exec -n default prometheus-kube-prometheus-stack-prometheus-0 -c prometheus -- \
  wget -qO- http://unifi-poller.unipoller:9130/metrics | head -20
```

### Common Issues

**Connection to UniFi Controller Failed:**

- Verify controller URL is accessible: `https://10.0.1.1`
- Check API key in the secret (`unipoller-secret`)
- Ensure UniFi API key has appropriate permissions for network monitoring

**No Metrics in Prometheus:**

- Verify Prometheus scrape configuration
- Check UniFi Poller pod is running
- Confirm service endpoint is accessible

## Updates and Maintenance

### Updating UniFi Poller

To update to a newer version:

1. Update image version in `manifests/base/unipoller/deployment.yaml`
2. Commit and push changes
3. ArgoCD will automatically deploy the update

### Configuration Changes

To modify UniFi controller settings:

1. Edit `manifests/base/unipoller/configmap.yaml`
2. Commit and push changes
3. ArgoCD will sync and restart the pod automatically

## Migration History

**Date:** 2025-12-25

UniFi Poller was migrated from manual deployment to ArgoCD GitOps management:

- Moved from `default` namespace to dedicated `unipoller` namespace
- Pinned image version from `latest` to `v2.11.2`
- Added resource limits for cluster stability
- Organized manifests under `manifests/base/unipoller/`
- Updated Prometheus scrape target to use namespace-qualified service name

## Related Documentation

- [Monitoring Overview](../monitoring/overview.md)
- [kube-prometheus-stack](./kube-prometheus-stack.md)
- [ArgoCD](./argocd.md)
