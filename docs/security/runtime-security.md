---
sidebar_position: 3
title: "Runtime Security"
description: "Runtime security monitoring with Trivy Operator and Falco"
---

# Runtime Security

This document covers runtime security monitoring deployed in the Kubernetes homelab cluster.

## Overview

The cluster uses a defense-in-depth approach with two complementary security tools:

| Tool | Purpose | Namespace | ArgoCD App |
|------|---------|-----------|------------|
| Trivy Operator | Vulnerability scanning, SBOM, compliance | `trivy-system` | `trivy-operator` |
| Falco | Runtime threat detection, syscall monitoring | `falco` | `falco` |

## Trivy Operator

### Description

Trivy Operator continuously scans workloads for:

- Container image vulnerabilities (CVEs)
- Kubernetes misconfigurations
- Software Bill of Materials (SBOM)
- Secret exposure in images

### Configuration

**Helm Chart:** `aquasecurity/trivy-operator` v0.31.0

```yaml
# Key configuration from values.yaml
trivy:
  # Use internal registry mirror
  registry: docker.io

operator:
  # Scan all namespaces
  scanJobsInSameNamespace: false

  # Resource limits for scanner pods
  resources:
    requests:
      cpu: 10m
      memory: 64Mi
    limits:
      cpu: 500m
      memory: 512Mi

# Tolerate control-plane taint for node scanning
nodeCollector:
  tolerations:
    - key: node-role.kubernetes.io/control-plane
      operator: Exists
      effect: NoSchedule
```

### Viewing Scan Results

```bash
# List vulnerability reports
kubectl get vulnerabilityreports -A

# View specific report
kubectl get vulnerabilityreport -n <namespace> <report-name> -o yaml

# List exposed secrets
kubectl get exposedsecretreports -A

# View SBOM reports
kubectl get sbomreports -A
```

### Prometheus Metrics

Trivy Operator exposes metrics at `/metrics`:

- `trivy_image_vulnerabilities` - CVEs by severity
- `trivy_resource_configauditreport_info` - Config audit results
- `trivy_vulnerability_id` - Individual CVE details

**Grafana Dashboard:** Trivy Operator Dashboard (ID: 17813)

## Falco

### Description

Falco monitors system calls in real-time to detect:

- Suspicious process execution
- File access violations
- Network anomalies
- Container escapes
- Privilege escalation

### Configuration

**Helm Chart:** `falcosecurity/falco` v4.20.1

```yaml
# Key configuration from values.yaml
falco:
  # Use eBPF driver (no kernel module needed)
  driver:
    kind: modern_ebpf

  # Output to stdout for log aggregation
  json_output: true
  json_include_output_property: true

  # Rules configuration
  rules_files:
    - /etc/falco/falco_rules.yaml
    - /etc/falco/falco_rules.local.yaml
    - /etc/falco/rules.d

# Resource limits for ARM64 Raspberry Pi
resources:
  requests:
    cpu: 100m
    memory: 256Mi
  limits:
    cpu: 500m
    memory: 512Mi

# Tolerations for all nodes
tolerations:
  - effect: NoSchedule
    operator: Exists
```

### Custom Rules

Custom rules are defined in the homelab repository to reduce false positives:

```yaml
# Example: Allow systemd to read PAM files (false positive)
- rule: Read sensitive file untrusted
  append: true
  condition: >
    and not (proc.pname = "systemd" and fd.name startswith "/etc/pam.d/")
```

### Viewing Alerts

```bash
# View Falco logs
kubectl logs -n falco -l app.kubernetes.io/name=falco -f

# Filter for warnings and above
kubectl logs -n falco -l app.kubernetes.io/name=falco | jq 'select(.priority == "Warning" or .priority == "Error" or .priority == "Critical")'
```

### Falco UI

- **URL:** `https://falco-ui.k8s.n37.ca` (if ingress configured)
- **Namespace:** `falco`
- **Service:** `falco-falcosidekick-ui`

### Prometheus Metrics

Falco exposes metrics via falcosidekick:

- `falco_events` - Total events by rule and priority
- `falcosidekick_outputs_sent` - Events sent to outputs

## Integration with Monitoring

Both tools integrate with the monitoring stack:

```
┌─────────────────┐     ┌─────────────────┐
│  Trivy Operator │────▶│   Prometheus    │
└─────────────────┘     │                 │
                        │   (scrapes)     │
┌─────────────────┐     │                 │
│     Falco       │────▶│                 │
│  (sidekick)     │     └────────┬────────┘
└─────────────────┘              │
                                 ▼
                        ┌─────────────────┐
                        │    Grafana      │
                        │  (dashboards)   │
                        └─────────────────┘
```

### Alerting

PrometheusRules are configured for critical security events:

```yaml
# Example alert for critical vulnerabilities
- alert: CriticalVulnerabilityDetected
  expr: sum(trivy_image_vulnerabilities{severity="Critical"}) > 0
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: Critical vulnerability detected in cluster

# Example alert for Falco threats
- alert: FalcoThreatDetected
  expr: increase(falco_events{priority=~"Critical|Error"}[5m]) > 0
  for: 0m
  labels:
    severity: critical
  annotations:
    summary: Falco detected a security threat
```

## Resource Usage

| Component | CPU Request | CPU Limit | Memory Request | Memory Limit |
|-----------|-------------|-----------|----------------|--------------|
| trivy-operator | 10m | 500m | 64Mi | 512Mi |
| falco | 100m | 500m | 256Mi | 512Mi |
| falcosidekick | 20m | 100m | 64Mi | 128Mi |
| falcosidekick-ui | 20m | 100m | 64Mi | 128Mi |

## Troubleshooting

### Trivy Scanner Pods Failing

```bash
# Check scanner pod status
kubectl get pods -n trivy-system -l trivy-operator.resource.kind=ReplicaSet

# View scanner logs
kubectl logs -n trivy-system <scanner-pod-name>

# Common issues:
# - Image pull failures (check registry access)
# - OOM kills (increase memory limits)
# - Missing tolerations for control-plane scanning
```

### Falco Not Detecting Events

```bash
# Check Falco pod status
kubectl get pods -n falco

# Verify eBPF driver loaded
kubectl logs -n falco -l app.kubernetes.io/name=falco | grep "driver"

# Test with manual event
kubectl exec -it <any-pod> -- cat /etc/shadow
# Should trigger "Read sensitive file" alert
```

## References

- [Trivy Operator Documentation](https://aquasecurity.github.io/trivy-operator/)
- [Falco Documentation](https://falco.org/docs/)
- [Falco Rules Reference](https://falco.org/docs/reference/rules/)

---

**Last Updated:** 2026-01-30
