# Trivy Operator

## Production Status

**Status:** ✅ **OPERATIONAL** (Deployed: 2026-01-05)

**Current Metrics** (as of 2026-01-06):

| Metric | Count |
|--------|-------|
| Vulnerability Reports | 77 |
| Images Scanned | 77 |
| **CRITICAL** Vulnerabilities | **43** |
| **HIGH** Vulnerabilities | **606** |
| **MEDIUM** Vulnerabilities | **1,499** |
| **Total** Vulnerabilities | **2,148** |

**Operational Highlights:**

- ✅ Trivy Operator running stable (14h uptime)
- ✅ Vulnerability reports generating successfully
- ✅ Prometheus metrics being scraped (60s interval)
- ✅ Grafana dashboard displaying real-time data
- ✅ AlertManager receiving and routing alerts
- ✅ Daily vulnerability database updates active
- ✅ Scan jobs completing within timeout limits

**Alert Status:**

- No exposed secrets detected (ExposedSecretsDetected: inactive)
- Multiple critical vulnerability alerts firing (expected during initial remediation)
- Monitoring integration confirmed working

## Overview

Trivy Operator is a Kubernetes-native security scanning solution that continuously monitors container images, Kubernetes configurations, and cluster compliance. It provides automated vulnerability detection, configuration auditing, and security posture management for the homelab cluster.

## Key Features

- **Container Vulnerability Scanning**: Detects CVEs in container images across all namespaces
- **Configuration Auditing**: Identifies Kubernetes misconfigurations and security issues
- **RBAC Assessment**: Analyzes role permissions for excessive privileges
- **Exposed Secrets Detection**: Scans for leaked credentials in container images
- **Compliance Reporting**: CIS Kubernetes Benchmark and NSA Hardening Guidance compliance

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Trivy Operator (1 pod)                                  │
│ - Watches Kubernetes resources                         │
│ - Triggers scans for new/updated workloads             │
│ - Stores scan results as CRDs                          │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Trivy Server (StatefulSet)                             │
│ - Vulnerability database (5Gi PVC on Synology)         │
│ - Performs actual scanning operations                   │
│ - Updated daily with latest CVE data                    │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Custom Resource Definitions (CRDs)                      │
│ - VulnerabilityReports: CVE findings per image         │
│ - ConfigAuditReports: K8s misconfigurations            │
│ - RBACAssessmentReports: Permission analysis           │
│ - ExposedSecretReports: Leaked credentials             │
│ - ClusterComplianceReports: CIS/NSA compliance         │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Monitoring & Alerting                                   │
│ - Prometheus metrics (scraped every 60s)               │
│ - Grafana dashboard (Trivy Security Scanning)          │
│ - PrometheusRule alerts (Critical/High CVEs)           │
└─────────────────────────────────────────────────────────┘
```

## Deployment

Trivy Operator is deployed via ArgoCD using the official Aqua Security Helm chart.

**ArgoCD Application:** `manifests/applications/trivy-operator.yaml`

**Configuration:** `manifests/base/trivy-operator/values.yaml`

**Version:** Helm chart 0.31.0 (App version 0.29.0)

### Resource Configuration

Optimized for Raspberry Pi 5 cluster:

- **Operator Pod**: 50m CPU request, 300m limit / 100Mi-300Mi memory
- **Trivy Server**: 100m-500m CPU / 256Mi-512Mi memory
- **Scan Jobs**: 50m-500m CPU / 100Mi-500Mi memory per job
- **Concurrent Scans**: Limited to 3 jobs at a time
- **Scan Timeout**: 10 minutes (increased for ARM64 architecture)

## Security Scanners

### Vulnerability Scanner

Scans container images for CVEs using the Trivy vulnerability database.

- **Severities Reported**: CRITICAL, HIGH, MEDIUM
- **Ignore Unfixed**: True (reduces noise from vulnerabilities without patches)
- **Scan Frequency**: On deployment + daily rescans
- **Scan Mode**: ClientServer (built-in Trivy server)

**View vulnerability reports:**

```bash
# List all vulnerability reports
kubectl get vulnerabilityreports -A

# Get detailed report for a specific workload
kubectl get vulnerabilityreport -n <namespace> <report-name> -o yaml

# Filter for CRITICAL vulnerabilities only
kubectl get vulnerabilityreports -A -o json | \
  jq '.items[] | select(.report.summary.criticalCount > 0)'
```

### Configuration Audit Scanner

Scans Kubernetes resources for misconfigurations and security best practices violations.

**Checks include:**

- Missing security contexts
- Privileged containers
- Host network/PID/IPC usage
- Insecure capabilities
- Missing resource limits
- Writable root filesystems

```bash
# List configuration audit reports
kubectl get configauditreports -A

# View specific report
kubectl get configauditreport -n <namespace> <name> -o yaml
```

### RBAC Assessment Scanner

Analyzes ClusterRoles and Roles for overly permissive configurations.

**Identifies:**

- Wildcard permissions (`*` verbs or resources)
- Cluster-admin equivalent permissions
- Dangerous permissions (create pods, exec, proxy)
- Service account token access

```bash
# List RBAC assessment reports
kubectl get rbacassessmentreports -A
kubectl get clusterrbacassessmentreports
```

### Exposed Secrets Scanner

Detects accidentally embedded secrets in container image layers.

**Scans for:**

- AWS credentials
- API keys
- Private keys
- Passwords
- OAuth tokens

```bash
# Check for exposed secrets (CRITICAL findings)
kubectl get exposedsecretreports -A
```

### Compliance Scanner

Generates compliance reports against industry standards.

**Supported frameworks:**

- CIS Kubernetes Benchmark v1.23
- NSA/CISA Kubernetes Hardening Guidance v1.0
- Kubernetes Pod Security Standards (Baseline, Restricted)

```bash
# View compliance reports
kubectl get clustercompliancereport

# Detailed CIS Kubernetes Benchmark results
kubectl get clustercompliancereport k8s-cis-1.23 -o yaml

# NSA Hardening Guidance results
kubectl get clustercompliancereport k8s-nsa-1.0 -o yaml
```

## Monitoring and Alerts

### Grafana Dashboard

Access at: `https://grafana.k8s.n37.ca`

**Dashboard: "Trivy Security Scanning"**

Panels include:

- Total vulnerability counts by severity
- Images scanned
- Vulnerabilities by image (sortable table)
- Severity distribution pie chart
- Namespace vulnerability breakdown

### Prometheus Alerts

PrometheusRule: `trivy-operator-alerts`

**Critical Alerts:**

- `CriticalVulnerabilitiesDetected`: Any image with CRITICAL CVEs
- `ExposedSecretsDetected`: Secrets found in images (immediate action required)

**Warning Alerts:**

- `HighVulnerabilityCount`: Image has >20 HIGH vulnerabilities
- `ClusterCriticalVulnerabilityThresholdExceeded`: >100 CRITICAL CVEs cluster-wide
- `HighRiskRBACPermissions`: Dangerous cluster role permissions

**Info Alerts:**

- `CISKubernetesBenchmarkFailures`: CIS compliance failures
- `NSAKubernetesHardeningFailures`: NSA hardening failures

### Metrics

Trivy Operator exports Prometheus metrics at: `http://trivy-operator.trivy-system.svc:8080/metrics`

**Key metrics:**

- `trivy_image_vulnerabilities{severity="Critical|High|Medium"}`: Vulnerability counts per image
- `trivy_cluster_compliance{title, status}`: Compliance check pass/fail
- `trivy_image_exposedsecrets`: Exposed secret findings

## Vulnerability Remediation

For detailed vulnerability response procedures, see: [Trivy Vulnerability Remediation Guide](./trivy-vulnerability-remediation.md)

**Quick remediation workflow:**

1. **Alert Triage**: Review alert, identify affected workload
2. **Assessment**: Check CVE exploitability and impact
3. **Remediation**: Update image, rebuild, or accept risk with mitigation
4. **Verification**: Rescan and confirm vulnerability resolved

## Operational Notes

### First 24 Hours (2026-01-05 to 2026-01-06)

**Deployment Success:**

- Initial deployment via ArgoCD completed successfully
- All CRDs installed without issues
- Trivy vulnerability database downloaded (ARM64 compatible)
- ServiceMonitor discovered by Prometheus
- Grafana dashboard loaded and displaying metrics

**Scanning Performance:**

- Initial cluster scan: ~2 hours to complete all 77 images
- Average scan job duration: 3-5 minutes per image
- No scan timeouts encountered (10-minute limit configured)
- Resource usage within limits (no OOM kills, CPU throttling minimal)

**Metrics Observations:**

- Vulnerability counts decreased slightly overnight (53→43 CRITICAL, 754→606 HIGH)
- Likely due to some images being rescanned with updated vulnerability database
- 77 vulnerability reports active (covering all workloads across cluster)
- Scan jobs run on-demand for new deployments and every 24h for existing images

**Alert Behavior:**

- CriticalVulnerabilitiesDetected alert firing as expected (multiple images affected)
- HighVulnerabilityCount alert firing for images with >20 HIGH CVEs
- No false positives detected in first 24 hours
- Email notifications confirmed working via AlertManager

**Recommendations from First Day:**

1. Priority remediation targets identified: Promtail, Synology CSI, ArgoCD Redis
2. No immediate critical exposures (no exposed secrets, no internet-facing critical CVEs)
3. Consider scheduling remediation work during next maintenance window
4. Monitor resource usage trends over next week

## Current Security Posture

**Latest Scan Results** (2026-01-06 morning):

| Metric | Count | Change from Initial |
|--------|-------|---------------------|
| Total Images Scanned | 77 | +25 images |
| CRITICAL Vulnerabilities | 43 | -10 (improved) |
| HIGH Vulnerabilities | 606 | -148 (improved) |
| MEDIUM Vulnerabilities | 1,499 | +4 |

**Vulnerability Trend:** ⬇️ **Improving** (likely due to automated database updates catching fixed CVEs)

**Top vulnerable components:**

- Promtail (Loki): 7 CRITICAL, 34 HIGH
- Synology CSI components: 3-5 CRITICAL each
- ArgoCD Redis: 3 CRITICAL, 34 HIGH

**Note:** Vulnerability counts may fluctuate as Trivy's database updates daily with new CVE data and vendor fixes.

## Configuration Files

| File | Purpose |
|------|---------|
| `manifests/applications/trivy-operator.yaml` | ArgoCD Application definition |
| `manifests/base/trivy-operator/values.yaml` | Helm values (scanners, resource limits) |
| `manifests/base/trivy-operator/namespace.yaml` | trivy-system namespace |
| `manifests/base/trivy-operator/trivy-alerts.yaml` | PrometheusRule for vulnerability alerts |
| `manifests/base/grafana/dashboards/trivy-security-dashboard.yaml` | Grafana dashboard JSON |

## Maintenance

### Update Trivy Operator

```bash
# Check for new Helm chart versions
helm search repo aquasecurity/trivy-operator --versions

# Update ArgoCD Application
vim manifests/applications/trivy-operator.yaml
# Update targetRevision

# Commit and deploy
git commit -am "chore: Update Trivy Operator to vX.Y.Z"
git push
```

### Update Vulnerability Database

Trivy automatically updates the vulnerability database daily. To force an update:

```bash
# Restart Trivy server to trigger database update
kubectl rollout restart statefulset/trivy-server -n trivy-system
```

### Adjust Scan Configuration

Edit `manifests/base/trivy-operator/values.yaml`:

```yaml
operator:
  # Increase concurrent scans (default: 3)
  scanJobsConcurrentLimit: 5

  # Adjust scan timeout
  scanJobTimeout: 15m

trivy:
  # Change severity filter
  severity: "CRITICAL,HIGH"  # Remove MEDIUM

  # Include unfixed vulnerabilities
  ignoreUnfixed: false
```

## Troubleshooting

### Scan Jobs Failing

```bash
# Check scan job logs
kubectl get pods -n trivy-system -l app=trivy-operator

# View logs from failed scan
kubectl logs -n trivy-system <scan-job-pod>

# Common issues:
# - Timeout: Increase scanJobTimeout
# - Memory: Increase scan job memory limits
# - Network: Check Trivy server connectivity
```

### High Resource Usage

```bash
# Check current resource consumption
kubectl top pods -n trivy-system

# Reduce concurrent scans
# Edit values.yaml: scanJobsConcurrentLimit: 2

# Increase scan report TTL to reduce rescans
# Edit values.yaml: scannerReportTTL: "48h"
```

### Missing Reports

```bash
# Verify Trivy Operator is running
kubectl get pods -n trivy-system

# Check operator logs
kubectl logs -n trivy-system deployment/trivy-operator

# Manually trigger scan by deleting report
kubectl delete vulnerabilityreport -n <namespace> <report>
```

## Security Considerations

- **PVC Encryption**: Vulnerability database stored on Synology NAS (encrypted at rest)
- **RBAC**: Trivy Operator has cluster-wide read permissions to scan all resources
- **Network Access**: Trivy server needs internet access to download vulnerability database
- **Secret Scanning**: Only scans image layers, does not access Kubernetes Secrets

## Resources

- **Official Documentation**: [aquasecurity.github.io/trivy-operator/](https://aquasecurity.github.io/trivy-operator/)
- **Helm Chart**: [github.com/aquasecurity/trivy-operator/tree/main/deploy/helm](https://github.com/aquasecurity/trivy-operator/tree/main/deploy/helm)
- **Trivy Documentation**: [aquasecurity.github.io/trivy/](https://aquasecurity.github.io/trivy/)
- **CRD Reference**: [aquasecurity.github.io/trivy-operator/latest/docs/crds/](https://aquasecurity.github.io/trivy-operator/latest/docs/crds/)
