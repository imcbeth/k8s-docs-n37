---
sidebar_position: 3
title: "Runtime Security"
description: "Runtime security monitoring with Trivy Operator, Falco, and OPA Gatekeeper"
---

# Runtime Security

This document covers runtime security monitoring deployed in the Kubernetes homelab cluster.

## Overview

The cluster uses a defense-in-depth approach with three complementary security tools:

| Tool | Purpose | Namespace | ArgoCD App |
|------|---------|-----------|------------|
| Trivy Operator | Vulnerability scanning, SBOM, compliance | `trivy-system` | `trivy-operator` |
| Falco | Runtime threat detection, syscall monitoring | `falco` | `falco` |
| OPA Gatekeeper | Admission control, policy enforcement | `gatekeeper-system` | `gatekeeper`, `gatekeeper-policies` |

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

**Helm Chart:** `falcosecurity/falco` v8.0.0

```yaml
# Key configuration from values.yaml
driver:
  kind: modern_ebpf
  modernEbpf:
    bufSizePreset: 4

falco:
  jsonOutput: true
  jsonIncludeOutputProperty: true
  jsonIncludeTagsProperty: true
  logLevel: info
  priority: notice

# Resource limits for ARM64 Raspberry Pi
resources:
  requests:
    cpu: 50m
    memory: 128Mi
  limits:
    cpu: 500m
    memory: 512Mi

# Falcosidekick WebUI Redis (redis-stack)
falcosidekick:
  webui:
    redis:
      resources:
        requests:
          memory: 512Mi
        limits:
          memory: 1Gi
      config:
        maxmemory: "800mb"
        maxmemory-policy: "allkeys-lru"

# Tolerations for all nodes
tolerations:
  - effect: NoSchedule
    key: node-role.kubernetes.io/control-plane
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

## OPA Gatekeeper

### Description

OPA Gatekeeper operates as a ValidatingAdmissionWebhook to enforce policies on resources before they are created or modified. This provides the admission control layer that complements Trivy (scanning) and Falco (runtime).

### Configuration

**Helm Chart:** `open-policy-agent/gatekeeper` v3.21.1

```yaml
# Key configuration from values.yaml
replicas: 1                    # 1 replica (default 3 is excessive for homelab)
auditInterval: 300             # 5-minute audit interval
constraintViolationsLimit: 20  # Max violations per constraint

controllerManager:
  exemptNamespaces:            # System namespaces exempt from policies
    - kube-system
    - argocd
    - gatekeeper-system
  resources:
    requests:
      cpu: 100m
      memory: 256Mi
    limits:
      cpu: 500m
      memory: 512Mi
```

### Active Policies

All policies deployed in **deny** mode (actively blocking non-compliant resources since 2026-02-07):

| Policy | Purpose |
|--------|---------|
| K8sRequireResourceLimits | Require CPU/memory limits on all containers |
| K8sAllowedRepos | Restrict images to approved registries |
| K8sRequireLabels | Require `app.kubernetes.io/name` label |
| K8sBlockNodePort | Prevent NodePort services (use LoadBalancer) |
| K8sContainerLimits | Max 2 CPU / 2Gi RAM per container |

### Viewing Violations

```bash
# Check all constraints and their violation counts
kubectl get constraints

# View detailed violations for a specific constraint
kubectl get k8srequireresourcelimits require-resource-limits -o yaml
```

### Prometheus Metrics

Gatekeeper exposes metrics on port 8888:

- `gatekeeper_violations` - Constraint violations by type
- `gatekeeper_audit_duration_seconds` - Audit cycle duration
- `gatekeeper_request_count` - Webhook request count

**Full documentation:** [OPA Gatekeeper](../applications/gatekeeper.md)

## Integration with Monitoring

All three tools integrate with the monitoring stack:

```
┌─────────────────┐     ┌─────────────────┐
│  Trivy Operator │────▶│   Prometheus    │
└─────────────────┘     │                 │
                        │   (scrapes)     │
┌─────────────────┐     │                 │
│     Falco       │────▶│                 │
│  (sidekick)     │     │                 │
└─────────────────┘     │                 │
                        │                 │
┌─────────────────┐     │                 │
│   Gatekeeper    │────▶│                 │
│  (audit+webhook)│     └────────┬────────┘
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
| trivy-operator | 50m | 300m | 100Mi | 300Mi |
| falco | 50m | 500m | 128Mi | 512Mi |
| falcosidekick | 10m | 100m | 32Mi | 64Mi |
| falcosidekick-ui | 10m | 100m | 32Mi | 128Mi |
| falcosidekick redis | 50m | 200m | 512Mi | 1Gi |
| gatekeeper-controller | 100m | 500m | 256Mi | 512Mi |
| gatekeeper-audit | 100m | 500m | 256Mi | 512Mi |

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
- [OPA Gatekeeper Documentation](https://open-policy-agent.github.io/gatekeeper/website/docs/)
- [Gatekeeper Policy Library](https://github.com/open-policy-agent/gatekeeper-library)

---

**Last Updated:** 2026-02-07
