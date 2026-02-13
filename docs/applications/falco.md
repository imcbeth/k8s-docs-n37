# Falco Runtime Security

## Production Status

**Status:** ✅ **OPERATIONAL** (Deployed: 2026-01-29, PR #336)

| Component | Status | Resources |
|-----------|--------|-----------|
| Falco DaemonSet | Running on all 5 nodes | 50m/128Mi → 500m/512Mi |
| Falcosidekick | Running | 10m/32Mi → 100m/64Mi |
| Falcosidekick WebUI | Running | 10m/32Mi → 100m/128Mi |
| Redis (redis-stack) | Running | 50m/512Mi → 200m/1Gi |

**Operational Highlights:**

- ✅ Falco monitoring syscalls on all nodes
- ✅ Modern eBPF driver (efficient on ARM64)
- ✅ Prometheus metrics being scraped (30s interval)
- ✅ Grafana dashboard displaying real-time events
- ✅ AlertManager receiving critical/warning alerts
- ✅ Loki receiving all security events
- ✅ Custom rules for homelab environment

## Overview

Falco is a cloud-native runtime security tool that detects unexpected application behavior and alerts on threats at runtime. It uses eBPF to monitor system calls and can detect:

- Container escape attempts
- Privilege escalation
- Reverse shell connections
- Cryptocurrency mining
- Sensitive file access
- Anomalous network activity

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FALCO ARCHITECTURE                                  │
└─────────────────────────────────────────────────────────────────────────────┘

  NODE 1              NODE 2              NODE 3              NODE 4              NODE 5
┌──────────┐       ┌──────────┐       ┌──────────┐       ┌──────────┐       ┌──────────┐
│  Falco   │       │  Falco   │       │  Falco   │       │  Falco   │       │  Falco   │
│ DaemonSet│       │ DaemonSet│       │ DaemonSet│       │ DaemonSet│       │ DaemonSet│
│  (eBPF)  │       │  (eBPF)  │       │  (eBPF)  │       │  (eBPF)  │       │  (eBPF)  │
└────┬─────┘       └────┬─────┘       └────┬─────┘       └────┬─────┘       └────┬─────┘
     │                  │                  │                  │                  │
     │                  │    gRPC :5060    │                  │                  │
     └──────────────────┴──────────────────┴──────────────────┴──────────────────┘
                                           │
                                    ┌──────▼──────┐
                                    │ Falcosidekick│
                                    │  (router)    │
                                    └──────┬──────┘
                                           │
              ┌────────────────────────────┼────────────────────────────┐
              │                            │                            │
       ┌──────▼──────┐              ┌──────▼──────┐              ┌──────▼──────┐
       │ Alertmanager │              │    Loki     │              │  WebUI      │
       │  :9093       │              │   :3100     │              │  :2802      │
       │ (critical)   │              │  (all logs) │              │ (visual)    │
       └─────────────┘              └─────────────┘              └─────────────┘
```

## Deployment

Falco is deployed via ArgoCD using the official Falcosecurity Helm chart.

**ArgoCD Application:** `manifests/applications/falco.yaml`

**Configuration:** `manifests/base/falco/values.yaml`

**Version:** Helm chart 4.20.1 (App version 0.40.0) — note: upstream Falco Helm chart migrated from the `falcosecurity/falco` chart (v8.x) to `falcosecurity/charts` (v4.x), so 4.20.1 is newer than the previously documented 8.0.0.

**Sync Wave:** -5 (after monitoring stack for Prometheus/Loki integration)

### Resource Configuration

Optimized for Raspberry Pi 5 cluster:

| Component | CPU Request | CPU Limit | Memory Request | Memory Limit |
|-----------|-------------|-----------|----------------|--------------|
| Falco | 50m | 500m | 128Mi | 512Mi |
| Falcosidekick | 10m | 100m | 32Mi | 64Mi |
| Falcosidekick WebUI | 10m | 100m | 32Mi | 128Mi |
| Redis (redis-stack) | 50m | 200m | 512Mi | 1Gi |
| WebUI init container | 10m | 50m | 32Mi | 64Mi |

:::note Redis Memory Sizing (2026-02-07)
The redis-stack server (with RediSearch, TimeSeries, JSON, Bloom, Gears modules) requires significantly more memory than plain redis. The RDB file can reach 500MB+. Use `maxmemory` config to cap Redis data below the container limit:

```yaml
falcosidekick-ui:
  redis:
    config:
      maxmemory: "800mb"
      maxmemory-policy: "allkeys-lru"
```

:::

## Security Detection

### Built-in Rules

Falco comes with extensive default rules covering:

- **Container Threats**: Privileged containers, namespace escapes
- **File Access**: Sensitive files (/etc/shadow, /etc/passwd)
- **Process Activity**: Unexpected shell spawns, package managers
- **Network**: Outbound connections, suspicious DNS queries
- **System**: Kernel module loading, ptrace usage

### Custom Homelab Rules

Custom rules tuned for the homelab environment:

```yaml
# Cryptocurrency mining detection
- rule: Detect Cryptocurrency Mining
  desc: Detect cryptocurrency mining processes
  condition: spawned_process and proc.name in (xmrig, minerd, minergate)
  priority: CRITICAL
  tags: [cryptomining, mitre_execution]

# Reverse shell detection
- rule: Reverse Shell Detected
  desc: Detect reverse shell connections
  condition: spawned_process and proc.cmdline contains "/dev/tcp"
  priority: CRITICAL
  tags: [shell, mitre_execution]
```

### Disabled Rules (Noise Reduction)

The following rules are disabled to reduce noise in a development/homelab environment:

- `Terminal shell in container` - Common for debugging
- `Attach/Exec Pod` - Common kubectl usage

## Monitoring and Alerts

### Grafana Dashboard

Access at: `https://grafana.k8s.n37.ca`

**Dashboard: "Falco Runtime Security"**

Panels include:

- **Overview**: Critical/Error/Warning event counts (24h)
- **Event Timeline**: Security events by priority over time
- **Event Analysis**: Events by rule, namespace, and top pods
- **System Performance**: Syscall event rate and memory usage
- **Drop Rate**: Event processing efficiency

### Prometheus Alerts

PrometheusRule: `falco-security-alerts`

**Critical Alerts:**

| Alert | Description | Action Required |
|-------|-------------|-----------------|
| `FalcoCriticalSecurityEvent` | Any critical security event detected | Immediate investigation |
| `FalcoReverseShellDetected` | Reverse shell attempt | Isolate affected pod |
| `FalcoCryptominingDetected` | Cryptocurrency mining detected | Terminate and investigate |

**Warning Alerts:**

| Alert | Description | Action Required |
|-------|-------------|-----------------|
| `FalcoErrorSecurityEvent` | Error-level security events | Review within 24h |
| `FalcoHighEventRate` | >10 events/sec sustained | Investigate source |
| `FalcoDown` | Falco instance not running | Restore monitoring |
| `FalcoHighDropRate` | >1% event drop rate | Check resources |

**Info Alerts:**

| Alert | Description | Action Required |
|-------|-------------|-----------------|
| `FalcoNoEvents` | No events for 15 minutes | Verify Falco health |

### Integration Points

| System | Purpose | Port |
|--------|---------|------|
| Alertmanager | Critical/warning alerts | 9093 |
| Loki | All security events | 3100 |
| Prometheus | Metrics scraping | 8765 |
| WebUI | Visual event browser | 2802 |

## Access WebUI

The Falcosidekick WebUI provides a visual interface for browsing security events.

```bash
# Port forward to access locally
kubectl port-forward -n falco svc/falco-falcosidekick-ui 2802:2802

# Open in browser
open http://localhost:2802
```

## Common Operations

### View Recent Events

```bash
# Check Falcosidekick logs for recent events
kubectl logs -n falco deployment/falco-falcosidekick --tail=50

# Query Loki for Falco events
# In Grafana Explore, use LogQL:
{namespace="falco"} |= "priority"
```

### Test Falco Detection

```bash
# Trigger a test rule (read sensitive file)
kubectl exec -it -n default <any-pod> -- cat /etc/shadow

# Check for the event
kubectl logs -n falco daemonset/falco --tail=20 | grep shadow
```

### Check Falco Health

```bash
# Verify all Falco pods are running
kubectl get pods -n falco -o wide

# Check Falco driver status
kubectl logs -n falco daemonset/falco | grep -i driver

# View syscall processing rate
kubectl exec -n falco daemonset/falco -- cat /proc/falco/stats
```

### Update Falco Rules

```bash
# Falco rules are automatically updated via falcoctl
# To force an update:
kubectl rollout restart daemonset/falco -n falco
```

## Troubleshooting

### Falco Pods Failing to Start

**Symptom:** Falco pods in CrashLoopBackOff

**Common Causes:**

1. **Kernel headers missing**: eBPF driver needs kernel headers

   ```bash
   # Check driver logs
   kubectl logs -n falco daemonset/falco -c falco-driver-loader
   ```

2. **Insufficient privileges**: Falco needs privileged mode

   ```bash
   # Verify securityContext
   kubectl get daemonset -n falco falco -o yaml | grep -A5 securityContext
   ```

### High Event Drop Rate

**Symptom:** `FalcoHighDropRate` alert firing

**Solution:**

1. Increase buffer size in values.yaml:

   ```yaml
   driver:
     modernEbpf:
       bufSizePreset: 8  # Increase from 4
   ```

2. Or reduce event volume with rule tuning

### No Events Being Generated

**Symptom:** Falco running but no events in logs

**Check:**

1. Verify driver is loaded:

   ```bash
   kubectl exec -n falco daemonset/falco -- cat /proc/falco/loaded
   ```

2. Check if rules are loaded:

   ```bash
   kubectl exec -n falco daemonset/falco -- falcoctl artifact list
   ```

### Alertmanager Not Receiving Alerts

**Check Falcosidekick configuration:**

```bash
kubectl logs -n falco deployment/falco-falcosidekick | grep -i alertmanager
```

**Verify network connectivity:**

```bash
kubectl exec -n falco deployment/falco-falcosidekick -- \
  wget -qO- --timeout=5 http://alertmanager-operated.monitoring:9093/-/healthy
```

## Network Policy

Falco namespace has a NetworkPolicy restricting traffic:

**Allowed Ingress:**

- Prometheus (metrics scraping on 8765, 2801)
- Internal namespace communication (gRPC 5060, HTTP 2801, WebUI 2802)

**Allowed Egress:**

- DNS (kube-system:53)
- Kubernetes API (6443)
- Alertmanager (monitoring:9093)
- Loki (loki:3100)
- HTTPS for rule downloads (443)

## Configuration Files

| File | Purpose |
|------|---------|
| `manifests/applications/falco.yaml` | ArgoCD Application definition |
| `manifests/base/falco/values.yaml` | Helm values (driver, resources, rules) |
| `manifests/base/falco/falco-alerts.yaml` | PrometheusRule for security alerts |
| `manifests/base/grafana/dashboards/falco-security-dashboard.yaml` | Grafana dashboard |
| `manifests/base/network-policies/falco/network-policy.yaml` | Network isolation |

## Security Considerations

- **Privileged Mode**: Falco requires privileged containers to access syscalls
- **Host PID Namespace**: Required for process monitoring
- **eBPF**: Uses kernel-level tracing (requires compatible kernel)
- **gRPC**: Events sent to Falcosidekick over unencrypted gRPC (internal only)
- **Rule Updates**: Automatic updates may introduce new detection rules

## Resources

- **Official Documentation**: [falco.org/docs](https://falco.org/docs/)
- **Helm Chart**: [github.com/falcosecurity/charts](https://github.com/falcosecurity/charts)
- **Rules Reference**: [falco.org/docs/rules](https://falco.org/docs/rules/)
- **Falcosidekick**: [github.com/falcosecurity/falcosidekick](https://github.com/falcosecurity/falcosidekick)

## Related Documentation

- [Trivy Operator](./trivy-operator.md) - Container vulnerability scanning
- [Network Policies](../security/network-policies.md) - Falco namespace isolation
- [Grafana Dashboards](../monitoring/grafana-dashboards.md) - Security dashboards
