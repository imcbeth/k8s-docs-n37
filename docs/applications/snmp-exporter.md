---
title: "SNMP Exporter"
description: "SNMP monitoring for Synology NAS with Prometheus integration"
---

# SNMP Exporter

The SNMP Exporter enables Prometheus to collect metrics from SNMP-enabled devices, specifically monitoring the Synology DS925+ NAS that provides storage for the cluster.

## Overview

- **Namespace:** `default`
- **Image:** `prom/snmp-exporter:v0.26.0`
- **Deployment:** Managed by ArgoCD as part of kube-prometheus-stack
- **Target Device:** Synology DS925+ NAS (10.0.1.204)

## Purpose

The SNMP Exporter provides comprehensive NAS monitoring by collecting:

- Disk health and temperature
- Volume capacity and usage
- RAID status and health
- System resource utilization
- Network interface statistics
- iSCSI target statistics
- Fan speeds and system temperatures

## Architecture

### Components

**Init Container (config-processor):**

- Processes SNMP configuration template
- Injects credentials from Kubernetes secrets
- Generates final configuration file
- Uses busybox:1.36

**Main Container (snmp-exporter):**

- Prometheus SNMP Exporter
- Exposes HTTP endpoint for metric scraping
- Queries NAS via SNMPv3
- Translates SNMP OIDs to Prometheus metrics

## SNMPv3 Configuration

### Authentication

The exporter uses **SNMPv3 with authentication and privacy** for secure monitoring:

**Security Level:** `authPriv`

**Authentication:**

- Protocol: SHA (configurable)
- Username: Stored in secret
- Password: Stored in secret

**Privacy (Encryption):**

- Protocol: AES (configurable)
- Password: Stored in secret

**Why SNMPv3?**

- Encrypted communication with NAS
- Authentication prevents unauthorized access
- Privacy ensures data confidentiality
- Industry best practice for SNMP monitoring

### Credentials Management

**Secret:** `snmp-exporter-credentials`

**Location:** `manifests/base/kube-prometheus-stack/snmp-exporter-secret.yaml` (git-crypt encrypted)

**Fields:**

```yaml
snmp-username: <username>
snmp-auth-password: <authentication password>
snmp-priv-password: <privacy password>
snmp-auth-protocol: SHA  # or MD5
snmp-priv-protocol: AES  # or DES
```

**Apply Secret:**

```bash
kubectl apply -f manifests/base/kube-prometheus-stack/snmp-exporter-secret.yaml
```

## Deployment Configuration

### Deployment Manifest

**Location:** `manifests/base/kube-prometheus-stack/snmp-exporter-deployment.yaml`

**Key Features:**

- Init container for credential injection
- Environment variable substitution
- Health checks (liveness and readiness probes)
- Resource limits appropriate for Pi cluster

**Resource Limits:**

```yaml
resources:
  requests:
    cpu: 50m
    memory: 64Mi
  limits:
    cpu: 100m
    memory: 128Mi
```

### Service Configuration

**Endpoint:** `snmp-exporter.default:9116`

```yaml
apiVersion: v1
kind: Service
metadata:
  name: snmp-exporter
  namespace: default
spec:
  type: ClusterIP
  ports:
  - port: 9116
    targetPort: 9116
```

### ConfigMap

**Location:** `manifests/base/kube-prometheus-stack/snmp-exporter-configmap.yaml`

Contains SNMP module configuration including:

- OID mappings
- Metric translations
- Walk configurations
- Synology-specific MIBs

## Prometheus Integration

### Scrape Configuration

Prometheus scrapes SNMP metrics via the exporter:

```yaml
scrape_configs:
- job_name: 'snmp-nas'
  static_configs:
    - targets:
      - 10.0.1.204  # Synology NAS
  metrics_path: /snmp
  params:
    module: [synology]  # Use synology SNMP module
  relabel_configs:
    - source_labels: [__address__]
      target_label: __param_target
    - source_labels: [__param_target]
      target_label: instance
    - target_label: __address__
      replacement: snmp-exporter.default:9116
```

**How It Works:**

1. Prometheus sends scrape request to snmp-exporter
2. snmp-exporter queries NAS via SNMP
3. snmp-exporter translates SNMP data to Prometheus metrics
4. Prometheus stores the metrics

### Collected Metrics

#### Storage Metrics

**Disk Health:**

- `diskTable` - Disk status and health
- `diskTemperature` - Drive temperatures
- `diskModel` - Drive model information

**Volume Metrics:**

- `volumeTable` - Volume status
- `volumeSize` - Total capacity
- `volumeFreeSize` - Available space
- `volumePercentUsed` - Usage percentage

**RAID Status:**

- `raidTable` - RAID array status
- `raidFreeSize` - Available RAID capacity
- `raidStatus` - Health status

#### System Metrics

**CPU and Memory:**

- `systemCPU` - CPU utilization
- `memorySize` - Total memory
- `memoryAvailable` - Free memory

**Temperature:**

- `systemTemperature` - System temperature
- `cpuFanStatus` - Fan status and speed
- `systemFanStatus` - Chassis fan status

#### Network Metrics

**Interface Statistics:**

- `ifInOctets` - Incoming bytes
- `ifOutOctets` - Outgoing bytes
- `ifInErrors` - Receive errors
- `ifOutErrors` - Transmit errors
- `ifSpeed` - Link speed

#### iSCSI Metrics

**Target Statistics:**

- `iscsiTargetTable` - iSCSI target status
- `iscsiLUNTable` - LUN status and usage
- `iscsiSessionTable` - Active sessions

## Grafana Dashboards

### Synology NAS Dashboard

**Location:** `Synology_Dashboard2.json`

**Panels Include:**

- Storage capacity overview
- Disk health and temperature
- RAID status
- Network throughput
- System resource usage
- iSCSI performance
- Temperature trends

**Import Dashboard:**

1. Access Grafana UI
2. Navigate to Dashboards → Import
3. Upload `Synology_Dashboard2.json`
4. Select Prometheus datasource
5. Import

### Common Queries

**Volume Usage:**

```promql
(volumeSize - volumeFreeSize) / volumeSize * 100
```

**Disk Temperature:**

```promql
diskTemperature{disk="Disk 1"}
```

**Network Throughput:**

```promql
rate(ifInOctets{ifDescr="eth0"}[5m]) * 8
```

**iSCSI LUN Usage:**

```promql
iscsiLUNUsed / iscsiLUNSize * 100
```

## Accessing the Exporter

### Metrics Endpoint

**Port Forward:**

```bash
kubectl port-forward -n default svc/snmp-exporter 9116:9116
```

**Query Metrics Directly:**

```bash
curl http://localhost:9116/snmp?target=10.0.1.204&module=synology
```

**Health Check:**

```bash
curl http://localhost:9116/health
```

### Testing SNMP Connectivity

**From within cluster:**

```bash
kubectl exec -n default deployment/snmp-exporter -- \
  wget -qO- http://localhost:9116/snmp?target=10.0.1.204&module=synology | head -50
```

## Troubleshooting

### Check Pod Status

```bash
# View pod
kubectl get pods -n default | grep snmp-exporter

# Check logs (init container)
kubectl logs -n default deployment/snmp-exporter -c config-processor

# Check logs (main container)
kubectl logs -n default deployment/snmp-exporter -c snmp-exporter
```

### Common Issues

#### No Metrics Returned

**Symptoms:**

- Empty metrics output
- SNMP exporter returns errors

**Diagnosis:**

```bash
# Check exporter logs
kubectl logs -n default deployment/snmp-exporter

# Test SNMP connection from pod
kubectl exec -n default deployment/snmp-exporter -- \
  snmpwalk -v3 -l authPriv -u <username> -a SHA -A <auth-pass> \
  -x AES -X <priv-pass> 10.0.1.204 system
```

**Common Causes:**

- SNMP not enabled on Synology NAS
- Incorrect credentials
- Firewall blocking SNMP (UDP 161)
- Wrong security level configuration

**Solution:**

1. Verify SNMP enabled in DSM (Control Panel → Terminal & SNMP → SNMP)
2. Check SNMPv3 user configured in DSM
3. Verify credentials in secret match DSM
4. Test network connectivity to NAS

#### Authentication Failures

**Symptoms:**

- Logs show "authentication failure"
- "Unknown user name" errors

**Solution:**

1. Verify SNMPv3 user exists in Synology DSM
2. Check username in secret: `kubectl get secret snmp-exporter-credentials -o yaml`
3. Ensure auth/priv protocols match DSM configuration
4. Recreate secret if credentials changed

#### Missing Specific Metrics

**Symptoms:**

- Some metrics present, others missing
- Incomplete disk or volume data

**Common Causes:**

- OID not in walk configuration
- Synology model differences
- Firmware version changes

**Solution:**

1. Check ConfigMap for OID definitions
2. Use `snmpwalk` to discover available OIDs
3. Update ConfigMap with new OIDs if needed
4. Restart deployment after ConfigMap changes

### Configuration Changes

**Update SNMP Module:**

1. Edit `manifests/base/kube-prometheus-stack/snmp-exporter-configmap.yaml`
2. Commit and push changes
3. ArgoCD will sync automatically
4. Pod will restart with new configuration

**Update Credentials:**

1. Edit secret file (git-crypt encrypted)
2. Apply updated secret: `kubectl apply -f snmp-exporter-secret.yaml`
3. Restart deployment: `kubectl rollout restart deployment/snmp-exporter -n default`

## Synology NAS Configuration

### Enable SNMP on Synology DSM

1. Log in to DSM ([https://10.0.1.204:5001](https://10.0.1.204:5001))
2. Go to Control Panel → Terminal & SNMP
3. Click SNMP tab
4. Enable SNMPv3 service
5. Create SNMPv3 user:
   - Username: (configure as needed)
   - Auth protocol: SHA
   - Auth password: (set strong password)
   - Priv protocol: AES
   - Priv password: (set strong password)
6. Apply settings

### Firewall Configuration

Ensure Synology firewall allows SNMP from Kubernetes nodes:

1. Control Panel → Security → Firewall
2. Edit rules to allow UDP port 161 from cluster network
3. Recommended: Restrict to cluster subnet (10.0.10.0/24)

## Alerting

### Recommended Alerts

**Disk Temperature:**

```yaml
- alert: DiskHighTemperature
  expr: diskTemperature > 50
  for: 10m
  annotations:
    summary: "Disk {{ $labels.disk }} temperature high"
```

**Volume Nearly Full:**

```yaml
- alert: VolumeHighUsage
  expr: (volumeSize - volumeFreeSize) / volumeSize * 100 > 85
  for: 5m
  annotations:
    summary: "Volume {{ $labels.volumeDescr }} is {{ $value }}% full"
```

**RAID Degraded:**

```yaml
- alert: RAIDDegraded
  expr: raidStatus != 1
  for: 1m
  annotations:
    summary: "RAID array {{ $labels.raidName }} is degraded"
```

## Updates and Maintenance

### Updating SNMP Exporter

To update to a newer version:

1. Update image version in deployment manifest
2. Check [release notes](https://github.com/prometheus/snmp_exporter/releases)
3. Test in non-production environment
4. Commit and push
5. ArgoCD deploys automatically

**Example:**

```yaml
image: prom/snmp-exporter:v0.27.0  # Update from v0.26.0
```

### MIB Updates

If Synology releases firmware updates with new MIBs:

1. Download updated MIB files from Synology
2. Generate new SNMP exporter configuration
3. Update ConfigMap with new OIDs
4. Test metrics collection
5. Commit changes

## Performance Considerations

### Scrape Interval

**Current:** 30s (standard Prometheus default)

**Considerations:**

- SNMP queries are lightweight
- 30s provides good resolution for storage metrics
- Can be reduced to 15s for more frequent updates
- Increase if NAS load becomes a concern

### Resource Usage

**Typical:**

- CPU: ~20-30m
- Memory: ~40-50Mi
- Network: Minimal (SNMP queries are small)

**Limits:**

- Set conservatively for Pi cluster
- Monitor actual usage and adjust if needed

## Migration History

**Date:** December 2025

SNMP exporter was added to provide comprehensive NAS monitoring:

**Changes:**

- Deployed SNMP exporter for Synology DS925+
- Configured SNMPv3 with authentication and privacy
- Added comprehensive OID mappings for storage, system, network, and iSCSI metrics
- Created Grafana dashboard for NAS visualization
- Integrated with existing Prometheus stack
- Implemented secure credential management

## Related Documentation

- [Monitoring Overview](../monitoring/overview.md)
- [kube-prometheus-stack](./kube-prometheus-stack.md)
- [Synology CSI Storage](../storage/synology-csi.md)
- [Troubleshooting Monitoring](../troubleshooting/monitoring.md)

## References

- [Prometheus SNMP Exporter](https://github.com/prometheus/snmp_exporter)
- [Synology SNMP MIB Guide](https://global.download.synology.com/download/Document/Software/DeveloperGuide/Firmware/DSM/All/enu/Synology_MIB_Guide.pdf)
- [SNMPv3 Security](https://www.rfc-editor.org/rfc/rfc3414)
