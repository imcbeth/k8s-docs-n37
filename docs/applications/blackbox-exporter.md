---
sidebar_position: 10
title: "Blackbox Exporter"
description: "Endpoint monitoring, SSL certificate expiry tracking, and service availability monitoring with Blackbox Exporter"
---

# Blackbox Exporter

## Overview

**Blackbox Exporter** is a Prometheus exporter that allows blackbox probing of endpoints over HTTP, HTTPS, DNS, TCP, and ICMP protocols. It's used for monitoring external service availability, SSL certificate expiry, network latency, and overall connectivity.

### Key Features

- **Multi-Protocol Probing**: HTTP, HTTPS, DNS, TCP, and ICMP
- **SSL/TLS Monitoring**: Certificate expiry tracking and TLS version validation
- **Response Time Metrics**: Latency and performance monitoring
- **Flexible Configuration**: Customizable probe modules for different use cases
- **Comprehensive Alerts**: Automatic alerting for service downtime, certificate expiry, and degraded performance

### Use Cases in This Cluster

1. **Internal Service Monitoring**: HTTP/HTTPS probes for Pi-hole, ArgoCD, and Grafana
2. **External Connectivity**: Monitoring internet connectivity via Google and Cloudflare
3. **DNS Health**: Query monitoring for Pi-hole, Cloudflare, and Google DNS servers
4. **Certificate Expiry**: SSL certificate monitoring for all external HTTPS endpoints
5. **Infrastructure Availability**: ICMP ping monitoring for NAS, gateway, and critical infrastructure

## Architecture

```
┌─────────────────┐
│   Prometheus    │
│                 │
│  (Scrapes       │
│   Blackbox      │
│   Exporter)     │
└────────┬────────┘
         │
         │ HTTP GET /probe?target=X&module=Y
         │
         ▼
┌─────────────────────────────┐
│    Blackbox Exporter        │
│                             │
│  - HTTP/HTTPS Prober        │
│  - DNS Prober               │
│  - ICMP Prober              │
│  - TCP Prober               │
└──────────┬──────────────────┘
           │
           │ Probe Target
           │
           ▼
     ┌──────────┐
     │  Target  │
     │ Endpoint │
     └──────────┘
```

## Deployment Details

### Container Image

- **Image**: `prom/blackbox-exporter:v0.28.0`
- **Port**: 9115 (HTTP metrics and probes)
- **Probes**: Liveness and readiness checks on `/health`

:::info Version Update (2026-01-11)
Upgraded from v0.25.0 to v0.28.0 to address 2 CRITICAL and 7 HIGH vulnerabilities. Now has 0 vulnerabilities.
:::

### Resource Allocation

```yaml
resources:
  requests:
    cpu: 50m
    memory: 64Mi
  limits:
    cpu: 200m
    memory: 128Mi
```

### Security Context

- **RunAsNonRoot**: `true`
- **RunAsUser**: `65534` (nobody)
- **ReadOnlyRootFilesystem**: `true`
- **Capabilities**: `NET_RAW` (required for ICMP probes)

## Configuration

### Probe Modules

The Blackbox Exporter is configured with multiple probe modules for different monitoring scenarios:

#### HTTP/HTTPS Probes

**http_2xx** - Basic HTTP probe

```yaml
prober: http
timeout: 5s
http:
  valid_status_codes: []  # 2xx
  method: GET
  follow_redirects: true
```

**https_cert_expiry** - HTTPS with certificate validation

```yaml
prober: http
timeout: 5s
http:
  method: GET
  fail_if_not_ssl: true
  tls_config:
    insecure_skip_verify: false
```

#### DNS Probe

**dns_query** - DNS resolution monitoring

```yaml
prober: dns
timeout: 5s
dns:
  query_name: "kubernetes.default.svc.cluster.local"
  query_type: "A"
```

#### ICMP Probe

**icmp_ping** - Network connectivity via ping

```yaml
prober: icmp
timeout: 5s
icmp:
  preferred_ip_protocol: "ip4"
```

#### TCP Probe

**tcp_connect** - TCP port connectivity

```yaml
prober: tcp
timeout: 5s
```

### Monitored Targets

#### Internal Services (HTTP)

- `http://pihole.pihole:80` - Pi-hole web interface
- `http://argocd-server.argocd:80` - ArgoCD server

#### External Services (HTTPS)

- `https://argocd.k8s.n37.ca` - ArgoCD external access
- `https://grafana.k8s.n37.ca` - Grafana dashboards
- `https://pihole.k8s.n37.ca` - Pi-hole external access
- `https://google.com` - External connectivity test
- `https://cloudflare.com` - External connectivity test

#### DNS Servers

- `10.0.0.200:53` - Pi-hole DNS
- `1.1.1.1:53` - Cloudflare DNS
- `8.8.8.8:53` - Google DNS

#### ICMP Targets

- `10.0.1.204` - Synology NAS
- `10.0.1.1` - Network gateway
- `8.8.8.8` - Google DNS (connectivity test)

## Prometheus Integration

### Scrape Configuration

The Blackbox Exporter is configured in Prometheus via `additionalScrapeConfigs` with four separate jobs:

1. **blackbox-http**: HTTP endpoint monitoring (30s interval)
2. **blackbox-https**: HTTPS with cert expiry (60s interval)
3. **blackbox-dns**: DNS query monitoring (30s interval)
4. **blackbox-icmp**: ICMP ping monitoring (30s interval)

### Relabeling Configuration

Each scrape job uses relabeling to properly set target labels:

```yaml
relabel_configs:
  - source_labels: [__address__]
    target_label: __param_target
  - source_labels: [__param_target]
    target_label: instance
  - target_label: __address__
    replacement: blackbox-exporter:9115
```

This configuration:

1. Moves the target address to a query parameter
2. Sets the instance label to the target
3. Directs Prometheus to scrape the Blackbox Exporter

## Alerting

### Alert Rules

Comprehensive alerting is configured via PrometheusRule:

#### Service Availability

| Alert Name | Condition | Duration | Severity |
|-----------|-----------|----------|----------|
| `EndpointDown` | `probe_success == 0` | 5 minutes | Critical |
| `EndpointDegraded` | `probe_success == 0` | 1 minute | Warning |

#### SSL Certificates

| Alert Name | Condition | Duration | Severity |
|-----------|-----------|----------|----------|
| `SSLCertificateExpiresIn30Days` | Expires in < 30 days | 1 hour | Warning |
| `SSLCertificateExpiresIn7Days` | Expires in < 7 days | 1 hour | Critical |
| `SSLCertificateExpired` | Expired certificate | 5 minutes | Critical |
| `TLSVersionTooOld` | TLS 1.0 or 1.1 | 1 hour | Warning |

#### Performance

| Alert Name | Condition | Duration | Severity |
|-----------|-----------|----------|----------|
| `HighHTTPResponseTime` | Response time > 5s | 5 minutes | Warning |
| `VeryHighHTTPResponseTime` | Response time > 10s | 2 minutes | Critical |
| `HighDNSResponseTime` | DNS lookup > 1s | 5 minutes | Warning |
| `HighICMPLatency` | Ping latency > 100ms | 5 minutes | Warning |

#### DNS & Network

| Alert Name | Condition | Duration | Severity |
|-----------|-----------|----------|----------|
| `DNSQueryFailed` | DNS probe fails | 5 minutes | Critical |
| `HostUnreachable` | ICMP probe fails | 5 minutes | Critical |

## Key Metrics

### Probe Success

- **probe_success**: `1` if probe succeeded, `0` if failed
- **probe_duration_seconds**: Total probe duration

### HTTP Metrics

- **probe_http_status_code**: HTTP status code returned
- **probe_http_duration_seconds**: HTTP request duration by phase
- **probe_http_redirects**: Number of redirects followed
- **probe_http_ssl**: `1` if SSL was used

### SSL/TLS Metrics

- **probe_ssl_earliest_cert_expiry**: Unix timestamp of certificate expiry
- **probe_tls_version_info**: TLS version used (1.0, 1.1, 1.2, 1.3)

### DNS Metrics

- **probe_dns_lookup_time_seconds**: DNS query duration
- **probe_dns_answer_rrs**: Number of DNS answer records

### ICMP Metrics

- **probe_icmp_duration_seconds**: ICMP round-trip time
- **probe_icmp_reply_hop_limit**: TTL of ICMP reply

## Useful Queries

### Service Availability

```promql
# Current status of all probes
probe_success

# Failed probes
probe_success == 0

# Uptime percentage (last 24h)
avg_over_time(probe_success[24h]) * 100
```

### SSL Certificate Expiry

```promql
# Days until certificate expires
(probe_ssl_earliest_cert_expiry - time()) / 86400

# Certificates expiring in < 30 days
(probe_ssl_earliest_cert_expiry - time()) / 86400 < 30
```

### Response Times

```promql
# HTTP response times
probe_http_duration_seconds

# DNS query times
probe_dns_lookup_time_seconds

# ICMP ping latency
probe_icmp_duration_seconds

# 95th percentile response time (last 5m)
histogram_quantile(0.95, rate(probe_http_duration_seconds_bucket[5m]))
```

### Connectivity Health

```promql
# ICMP packet loss rate
1 - avg_over_time(probe_success{job="blackbox-icmp"}[5m])

# DNS failure rate
1 - avg_over_time(probe_success{job="blackbox-dns"}[5m])
```

## Grafana Dashboards

### Recommended Dashboards

1. **Prometheus Blackbox Exporter** (ID: 7587)
   - Overview of all probes
   - Success rates and response times
   - SSL certificate status

2. **Blackbox Exporter SSL/TLS** (ID: 13659)
   - Certificate expiry tracking
   - TLS version distribution
   - Certificate chain details

### Custom Dashboard Panels

**Service Availability Timeline**

```promql
probe_success{job=~"blackbox.*"}
```

**Certificate Expiry (Days)**

```promql
(probe_ssl_earliest_cert_expiry - time()) / 86400
```

**Response Time Heatmap**

```promql
probe_http_duration_seconds
```

## Troubleshooting

### Common Issues

#### Probes Failing

**Problem**: `probe_success == 0` for a target

**Solutions**:

1. Check target is reachable from the cluster:

   ```bash
   kubectl exec -it deployment/blackbox-exporter -- wget -O- http://target
   ```

2. Verify DNS resolution:

   ```bash
   kubectl exec -it deployment/blackbox-exporter -- nslookup target
   ```

3. Check probe configuration:

   ```bash
   kubectl logs deployment/blackbox-exporter
   ```

#### ICMP Probes Not Working

**Problem**: ICMP probes fail with permission errors

**Solution**: Verify the deployment has `NET_RAW` capability:

```bash
kubectl get deployment blackbox-exporter -o yaml | grep -A5 capabilities
```

#### SSL Certificate Warnings

**Problem**: SSL certificate metrics not appearing

**Solution**: Ensure `https_cert_expiry` module is used for HTTPS targets, not `http_2xx`

#### High Memory Usage

**Problem**: Blackbox exporter consuming excessive memory

**Solutions**:

1. Reduce probe frequency in `additionalScrapeConfigs`
2. Limit number of targets
3. Increase memory limits if justified

### Debug Commands

```bash
# Check deployment status
kubectl get deployment blackbox-exporter

# View logs
kubectl logs deployment/blackbox-exporter

# Test a probe manually
kubectl exec -it deployment/blackbox-exporter -- wget -O- \
  'http://localhost:9115/probe?target=https://google.com&module=https_cert_expiry'

# View current configuration
kubectl get configmap blackbox-exporter-config -o yaml

# Check Prometheus targets
kubectl port-forward -n default svc/kube-prometheus-stack-prometheus 9090:9090
# Navigate to: http://localhost:9090/targets
```

## Maintenance

### Adding New Targets

1. Edit `manifests/base/kube-prometheus-stack/values.yaml`
2. Add target to appropriate `additionalScrapeConfigs` job:

   ```yaml
   - job_name: 'blackbox-https'
     static_configs:
       - targets:
           - https://new-service.k8s.n37.ca
   ```

3. Commit and let ArgoCD sync

### Updating Probe Modules

1. Edit `manifests/base/kube-prometheus-stack/blackbox-exporter-configmap.yaml`
2. Modify or add probe modules as needed
3. Restart the deployment:

   ```bash
   kubectl rollout restart deployment/blackbox-exporter
   ```

### Certificate Monitoring Best Practices

1. Monitor certificates at least 30 days before expiry
2. Set up critical alerts for 7-day threshold
3. Verify cert-manager is renewing certificates automatically
4. Test alert notifications regularly

## References

- **Official Documentation**: [Blackbox Exporter GitHub](https://github.com/prometheus/blackbox_exporter)
- **Probe Configuration**: [Configuration Guide](https://github.com/prometheus/blackbox_exporter/blob/master/CONFIGURATION.md)
- **Example Configurations**: [Examples](https://github.com/prometheus/blackbox_exporter/tree/master/example)
- **Grafana Dashboards**: [Dashboard Gallery](https://grafana.com/grafana/dashboards/?search=blackbox)

## Related Documentation

- [Kube Prometheus Stack](./kube-prometheus-stack.md) - Core monitoring stack
- [SNMP Exporter](./snmp-exporter.md) - Synology NAS monitoring
- [Cert Manager](./cert-manager.md) - Automatic certificate management
- [Monitoring Overview](../monitoring/overview.md) - Complete monitoring architecture
