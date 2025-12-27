---
title: "Monitoring Troubleshooting"
description: "Common monitoring stack issues and solutions"
---

# Monitoring Troubleshooting

This guide covers common issues with the monitoring stack (Prometheus, Grafana, AlertManager, UniFi Poller) and their solutions.

## Prometheus Issues

### Prometheus Pod Stuck in Pending

**Symptoms:**
- Prometheus pod shows `Pending` status
- No metrics being collected

**Diagnosis:**
```bash
kubectl describe pod prometheus-kube-prometheus-stack-prometheus-0 -n default
```

**Common Causes:**

1. **PVC Not Bound:**
   ```bash
   kubectl get pvc -n default | grep prometheus
   ```
   - Check if PVC is in `Pending` state
   - Verify Synology CSI driver is running: `kubectl get pods -n synology-csi`
   - Ensure storage class exists: `kubectl get storageclass`
   - Check Synology NAS storage capacity

2. **Insufficient Node Resources:**
   - Check node capacity: `kubectl describe nodes`
   - Prometheus requests 2Gi memory - ensure nodes have available capacity
   - Review resource requests vs limits

**Solution:**
```bash
# If CSI driver issue
kubectl rollout restart deployment/synology-csi-controller -n synology-csi

# If resource issue, check pod distribution
kubectl get pods -o wide -A | grep prometheus
```

### Prometheus High Memory Usage

**Symptoms:**
- Prometheus pod using excessive memory
- Pod getting OOMKilled
- Slow query performance

**Diagnosis:**
```bash
# Check current memory usage
kubectl top pod prometheus-kube-prometheus-stack-prometheus-0 -n default

# Check cardinality
kubectl exec -n default prometheus-kube-prometheus-stack-prometheus-0 -c prometheus -- \
  wget -qO- http://localhost:9090/api/v1/status/tsdb | grep numSeries
```

**Common Causes:**
- High-cardinality metrics
- Too many active series
- Aggressive scrape intervals
- Long retention period

**Solution:**

1. **Review Scrape Intervals:**
   ```bash
   # Check prometheus configuration
   kubectl get prometheus -n default -o yaml | grep interval
   ```

2. **Reduce Cardinality:**
   - Identify high-cardinality metrics
   - Use recording rules for expensive queries
   - Drop unnecessary labels

3. **Adjust Resource Limits:**
   Edit `manifests/base/kube-prometheus-stack/values.yaml`:
   ```yaml
   prometheus:
     prometheusSpec:
       resources:
         limits:
           memory: 6Gi  # Increase from 4Gi
   ```

4. **Reduce Retention:**
   ```yaml
   prometheus:
     prometheusSpec:
       retention: 15d  # Reduce from 30d
   ```

### No Metrics from Specific Target

**Symptoms:**
- Missing metrics in Prometheus
- Scrape target showing as down

**Diagnosis:**
```bash
# Port-forward to Prometheus UI
kubectl port-forward -n default svc/kube-prometheus-stack-prometheus 9090:9090

# Open http://localhost:9090/targets
# Check target status
```

**Common Targets and Checks:**

**UniFi Poller:**
```bash
# Check pod running
kubectl get pods -n unipoller

# Test metrics endpoint
kubectl exec -n default prometheus-kube-prometheus-stack-prometheus-0 -c prometheus -- \
  wget -qO- http://unifi-poller.unipoller:9130/metrics | head -20

# Check UniFi Poller logs
kubectl logs -n unipoller deployment/unifi-poller
```

**Node Exporter:**
```bash
# Check DaemonSet (should have 5 pods for 5 nodes)
kubectl get ds -n default | grep node-exporter

# Verify all pods running
kubectl get pods -n default -l app.kubernetes.io/name=prometheus-node-exporter
```

**Solution:**
- Verify ServiceMonitor exists: `kubectl get servicemonitor -A`
- Check service endpoints: `kubectl get endpoints <service-name>`
- Review Prometheus logs: `kubectl logs -n default prometheus-kube-prometheus-stack-prometheus-0 -c prometheus`

### Prometheus Disk Full

**Symptoms:**
- Prometheus logs show disk space errors
- Metrics collection stops
- Write failures

**Diagnosis:**
```bash
# Check PVC size
kubectl get pvc -n default | grep prometheus

# Check actual usage (if metrics available)
kubectl exec -n default prometheus-kube-prometheus-stack-prometheus-0 -c prometheus -- \
  df -h /prometheus
```

**Solution:**

1. **Expand PVC:**
   ```bash
   kubectl edit pvc prometheus-kube-prometheus-stack-prometheus-db-prometheus-kube-prometheus-stack-prometheus-0 -n default

   # Change:
   spec:
     resources:
       requests:
         storage: 100Gi  # Increase from 50Gi
   ```

2. **Reduce Retention:**
   Edit values to reduce data retention period

3. **Clean Old Data (Emergency):**
   ```bash
   # Delete old time series (use with caution)
   kubectl exec -n default prometheus-kube-prometheus-stack-prometheus-0 -c prometheus -- \
     rm -rf /prometheus/chunks_head/*

   # Restart Prometheus
   kubectl delete pod prometheus-kube-prometheus-stack-prometheus-0 -n default
   ```

## Grafana Issues

### Cannot Access Grafana UI

**Symptoms:**
- Cannot connect to Grafana via port-forward
- Grafana dashboard not loading

**Diagnosis:**
```bash
# Check Grafana pod status
kubectl get pods -n default | grep grafana

# Check pod logs
kubectl logs -n default deployment/kube-prometheus-stack-grafana

# Verify service
kubectl get svc -n default | grep grafana
```

**Solution:**
```bash
# Port-forward to Grafana
kubectl port-forward -n default svc/kube-prometheus-stack-grafana 3000:80

# Open http://localhost:3000

# If pod crashed, check logs and restart
kubectl rollout restart deployment/kube-prometheus-stack-grafana -n default
```

### Forgot Grafana Admin Password

**Solution:**
```bash
# Retrieve password from secret
kubectl get secret kube-prometheus-stack-grafana -n default \
  -o jsonpath="{.data.admin-password}" | base64 -d

echo  # Add newline after password
```

### Grafana Shows "No Data" or "N/A"

**Symptoms:**
- Dashboards show no data
- Queries return empty results
- All panels show "N/A"

**Diagnosis:**

1. **Check Prometheus Datasource:**
   - Go to Configuration > Data Sources in Grafana
   - Click on Prometheus datasource
   - Click "Test" button

2. **Verify Prometheus Running:**
   ```bash
   kubectl get pods -n default | grep prometheus
   ```

3. **Check Time Range:**
   - Ensure selected time range has data
   - Try "Last 5 minutes" for recent data

**Solution:**

1. **Fix Datasource URL:**
   Should be: `http://kube-prometheus-stack-prometheus.default:9090`

2. **Restart Grafana:**
   ```bash
   kubectl rollout restart deployment/kube-prometheus-stack-grafana -n default
   ```

3. **Verify Metrics Exist:**
   Query Prometheus directly:
   ```bash
   kubectl port-forward -n default svc/kube-prometheus-stack-prometheus 9090:9090
   # Open http://localhost:9090
   # Run query: up
   ```

### Dashboard Import Fails

**Symptoms:**
- Cannot import dashboard JSON
- Dashboard shows errors after import

**Common Causes:**
- Incompatible Grafana version
- Missing data sources
- Incorrect variable definitions

**Solution:**
1. Verify Grafana version compatibility
2. Check datasource name matches
3. Review dashboard variables
4. Import dashboards from [grafana.com](https://grafana.com/grafana/dashboards/)

## AlertManager Issues

### Alerts Not Firing

**Symptoms:**
- Expected alerts not appearing
- No notifications received

**Diagnosis:**
```bash
# Check AlertManager pod
kubectl get pods -n default | grep alertmanager

# View firing alerts
kubectl port-forward -n default svc/kube-prometheus-stack-alertmanager 9093:9093
# Open http://localhost:9093

# Check PrometheusRules
kubectl get prometheusrule -A
```

**Solution:**

1. **Verify Alert Rules:**
   ```bash
   # Check rules loaded in Prometheus
   # Port-forward to Prometheus: http://localhost:9090/rules
   ```

2. **Check Alert State:**
   - Pending: Alert condition met but not for long enough
   - Firing: Alert actively firing
   - Review `for` duration in alert rules

3. **Review AlertManager Config:**
   ```bash
   kubectl get secret alertmanager-kube-prometheus-stack-alertmanager -n default -o yaml
   ```

### Notification Not Sent

**Symptoms:**
- Alerts firing but no notifications
- Slack/email not received

**Diagnosis:**
```bash
# Check AlertManager logs
kubectl logs -n default alertmanager-kube-prometheus-stack-alertmanager-0

# View AlertManager config
kubectl port-forward -n default svc/kube-prometheus-stack-alertmanager 9093:9093
# Open http://localhost:9093/#/status
```

**Solution:**

1. **Configure Notification Channel:**
   Edit `manifests/base/kube-prometheus-stack/values.yaml`:
   ```yaml
   alertmanager:
     config:
       receivers:
       - name: 'slack'
         slack_configs:
         - api_url: 'YOUR_SLACK_WEBHOOK'
           channel: '#alerts'
       route:
         receiver: 'slack'
   ```

2. **Test Configuration:**
   - Send test alert
   - Check webhook/SMTP settings
   - Verify network connectivity

## UniFi Poller Issues

### UniFi Poller Not Collecting Metrics

**Symptoms:**
- No UniFi metrics in Prometheus
- UniFi dashboards empty

**Diagnosis:**
```bash
# Check UniFi Poller pod
kubectl get pods -n unipoller

# View logs
kubectl logs -n unipoller deployment/unifi-poller

# Test metrics endpoint
kubectl exec -n unipoller deployment/unifi-poller -- \
  wget -qO- http://localhost:9130/metrics | grep unifi
```

**Common Causes:**

1. **UniFi Controller Connection Failed:**
   - Verify controller URL: `https://10.0.1.1`
   - Check credentials in secret
   - Verify SSL verification disabled (controller has self-signed cert)

2. **Wrong Site Name:**
   - Verify site name in config (should be `n37-gw`)

**Solution:**

1. **Check Configuration:**
   ```bash
   kubectl get configmap -n unipoller unifi-poller-config -o yaml
   ```

2. **Verify Secret:**
   ```bash
   kubectl get secret -n unipoller unifi-poller-secret -o yaml
   ```

3. **Test Controller Connection:**
   ```bash
   kubectl exec -n unipoller deployment/unifi-poller -- \
     curl -k https://10.0.1.1
   ```

4. **Restart UniFi Poller:**
   ```bash
   kubectl rollout restart deployment/unifi-poller -n unipoller
   ```

### UniFi Poller High Error Rate

**Symptoms:**
- Logs show connection errors
- Intermittent metric collection

**Diagnosis:**
```bash
kubectl logs -n unipoller deployment/unifi-poller | grep -i error
```

**Common Issues:**
- Network connectivity to controller
- Invalid credentials
- Controller API changes after upgrade

**Solution:**
- Verify network path to 10.0.1.1
- Update UniFi Poller to latest version
- Check UniFi Controller version compatibility

## Node Exporter Issues

### Missing Node Metrics

**Symptoms:**
- Some nodes missing from metrics
- Incomplete node exporter data

**Diagnosis:**
```bash
# Check DaemonSet status (should show 5/5 for 5 nodes)
kubectl get daemonset -n default prometheus-node-exporter

# Check pods
kubectl get pods -n default -l app.kubernetes.io/name=prometheus-node-exporter -o wide

# Verify ServiceMonitor
kubectl get servicemonitor -n default | grep node-exporter
```

**Solution:**

1. **Check Pod Status:**
   ```bash
   kubectl describe pod -n default -l app.kubernetes.io/name=prometheus-node-exporter
   ```

2. **Node Taint Issues:**
   ```bash
   # Check node taints
   kubectl describe nodes | grep -i taint

   # DaemonSet might need tolerations
   ```

3. **Restart DaemonSet:**
   ```bash
   kubectl rollout restart daemonset/prometheus-node-exporter -n default
   ```

### Temperature Metrics Missing

**Symptoms:**
- No `node_hwmon_temp_celsius` metrics
- Cannot monitor Pi temperature

**Diagnosis:**
```bash
# Check if hwmon is exposed on nodes
kubectl exec -n default <node-exporter-pod> -- ls -la /host/sys/class/hwmon
```

**Solution:**
- Raspberry Pi temperature sensors should be auto-detected
- Verify node-exporter has access to host filesystem
- Check hostPath mounts in DaemonSet spec

## Control Plane Component Monitoring Issues

### Control Plane Targets Showing Down

**Symptoms:**
- kube-controller-manager, etcd, kube-scheduler, or kube-proxy showing as DOWN in Prometheus
- Missing control plane metrics
- Scrape errors in Prometheus logs

**Diagnosis:**
```bash
# Check Prometheus targets
kubectl port-forward -n default svc/kube-prometheus-stack-prometheus 9090:9090
# Open http://localhost:9090/targets

# Check ServiceMonitor status
kubectl get servicemonitor -n default | grep -E "controller|etcd|scheduler|proxy"

# Verify control plane component endpoints
kubectl get endpoints -n kube-system kube-controller-manager
kubectl get endpoints -n kube-system kube-scheduler
```

**Common Causes:**

1. **Components Binding to Localhost:**
   - **Problem:** Default kubeadm configuration binds components to 127.0.0.1
   - **Symptom:** Connection refused errors when Prometheus tries to scrape
   - **Solution:** Update kubeadm configuration to bind to 0.0.0.0

2. **Certificate/TLS Issues:**
   - **Problem:** Self-signed certificates or TLS verification failures
   - **Symptom:** TLS handshake errors in Prometheus logs
   - **Solution:** Configure `insecureSkipVerify` in ServiceMonitor (use cautiously)

3. **Firewall/Network Policies:**
   - **Problem:** Network policies blocking scrape traffic
   - **Symptom:** Timeouts or connection refused
   - **Solution:** Verify network policies allow Prometheus → control plane traffic

**Solution - Verify Bind Addresses:**

Check kubeadm configuration for control plane components:

```bash
# Controller Manager
sudo cat /etc/kubernetes/manifests/kube-controller-manager.yaml | grep bind-address

# Scheduler
sudo cat /etc/kubernetes/manifests/kube-scheduler.yaml | grep bind-address

# Expected output: --bind-address=0.0.0.0
```

**Solution - Update kubeadm Config (if binding to localhost):**

1. **Edit Controller Manager:**
   ```bash
   sudo vim /etc/kubernetes/manifests/kube-controller-manager.yaml

   # Change:
   - --bind-address=127.0.0.1
   # To:
   - --bind-address=0.0.0.0
   ```

2. **Edit Scheduler:**
   ```bash
   sudo vim /etc/kubernetes/manifests/kube-scheduler.yaml

   # Change:
   - --bind-address=127.0.0.1
   # To:
   - --bind-address=0.0.0.0
   ```

3. **Edit kube-proxy ConfigMap:**
   ```bash
   kubectl edit configmap kube-proxy -n kube-system

   # In the config.conf section, change:
   metricsBindAddress: "127.0.0.1:10249"
   # To:
   metricsBindAddress: "0.0.0.0:10249"

   # Then restart kube-proxy DaemonSet
   kubectl rollout restart daemonset kube-proxy -n kube-system
   ```

4. **etcd Configuration:**
   ```bash
   sudo vim /etc/kubernetes/manifests/etcd.yaml

   # Verify:
   - --listen-metrics-urls=http://0.0.0.0:2381
   ```

**After Configuration Changes:**

Wait for kubelet to automatically restart the static pods (~30-60 seconds), then verify targets:

```bash
# Check if targets are UP
kubectl port-forward -n default svc/kube-prometheus-stack-prometheus 9090:9090
# Open http://localhost:9090/targets
# Look for: kube-controller-manager, etcd, kube-scheduler, kube-proxy
```

### Missing etcd Metrics

**Symptoms:**
- etcd target DOWN or missing
- No etcd performance metrics

**Diagnosis:**
```bash
# Check etcd endpoint
kubectl get endpoints -n kube-system kube-etcd

# Verify etcd is exposing metrics
curl -k http://<node-ip>:2381/metrics
```

**Solution:**
1. Verify etcd is configured to expose metrics on port 2381
2. Check ServiceMonitor configuration in values.yaml
3. Ensure network connectivity from Prometheus pod to etcd

### Controller Manager Metrics Missing

**Diagnosis:**
```bash
# Test endpoint directly
curl -k https://<node-ip>:10257/metrics

# Check for certificate issues
kubectl logs -n default prometheus-kube-prometheus-stack-prometheus-0 -c prometheus | grep controller-manager
```

**Solution:**
- Verify port 10257 is accessible
- Check TLS configuration in ServiceMonitor
- Ensure `insecureSkipVerify: true` if using self-signed certs

### Scheduler Metrics Missing

**Diagnosis:**
```bash
# Test endpoint
curl -k https://<node-ip>:10259/metrics

# Check ServiceMonitor
kubectl get servicemonitor -n default kube-prometheus-stack-kube-scheduler -o yaml
```

**Solution:**
- Verify scheduler is running: `kubectl get pods -n kube-system | grep scheduler`
- Check bind address in scheduler manifest
- Verify port 10259 is accessible

### kube-proxy Metrics Missing

**Diagnosis:**
```bash
# kube-proxy runs on all nodes
kubectl get pods -n kube-system -l k8s-app=kube-proxy -o wide

# Test metrics endpoint (use any node IP)
curl http://<node-ip>:10249/metrics
```

**Solution:**
- Verify metricsBindAddress in kube-proxy ConfigMap
- Restart kube-proxy after config changes
- Check that port 10249 is accessible from Prometheus

## General Troubleshooting Steps

### Check All Monitoring Pods

```bash
# Check all monitoring components
kubectl get pods -n default | grep -E "prometheus|grafana|alertmanager|node-exporter"
kubectl get pods -n unipoller
```

### View Component Logs

```bash
# Prometheus
kubectl logs -n default prometheus-kube-prometheus-stack-prometheus-0 -c prometheus

# Grafana
kubectl logs -n default deployment/kube-prometheus-stack-grafana

# AlertManager
kubectl logs -n default alertmanager-kube-prometheus-stack-alertmanager-0

# Node Exporter
kubectl logs -n default daemonset/prometheus-node-exporter

# UniFi Poller
kubectl logs -n unipoller deployment/unifi-poller
```

### Restart Monitoring Stack

**Individual Components:**
```bash
# Restart Grafana
kubectl rollout restart deployment/kube-prometheus-stack-grafana -n default

# Restart Node Exporter
kubectl rollout restart daemonset/prometheus-node-exporter -n default

# Restart UniFi Poller
kubectl rollout restart deployment/unifi-poller -n unipoller

# Restart Prometheus (StatefulSet - delete pod)
kubectl delete pod prometheus-kube-prometheus-stack-prometheus-0 -n default
```

**Full Stack Restart:**
```bash
# Sync ArgoCD application
argocd app sync kube-prometheus-stack --grpc-web
argocd app sync unipoller --grpc-web
```

### Verify ArgoCD Sync Status

```bash
# Check if monitoring apps are in sync
kubectl get application -n argocd | grep -E "prometheus|unipoller"

# Get detailed status
argocd app get kube-prometheus-stack --grpc-web
argocd app get unipoller --grpc-web
```

## Performance Issues

### Slow Dashboard Load Times

**Causes:**
- Expensive PromQL queries
- Large time ranges
- High cardinality metrics

**Solutions:**
1. Use recording rules for expensive queries
2. Limit dashboard time range
3. Optimize PromQL queries
4. Increase Prometheus resources

### High CPU Usage on Prometheus

**Diagnosis:**
```bash
kubectl top pod prometheus-kube-prometheus-stack-prometheus-0 -n default
```

**Solutions:**
1. Reduce scrape frequency
2. Use recording rules
3. Reduce retention period
4. Optimize alert rule evaluation

## Raspberry Pi Specific Issues

### CPU Throttling Affecting Monitoring

**Symptoms:**
- Monitoring gaps during high load
- Inconsistent metric collection

**Solution:**
- Monitor Pi temperature: `node_hwmon_temp_celsius`
- Improve cooling if temps > 70°C
- Adjust resource limits on monitoring pods
- Distribute workload across nodes

### Network Bandwidth Saturation

**Symptoms:**
- Delayed metric collection
- iSCSI performance issues affecting Prometheus storage

**Solution:**
- Check network utilization metrics
- Reduce scrape intervals if needed
- Monitor Synology NAS network traffic
- Consider metric retention policies

## Recovery Procedures

### Complete Monitoring Stack Failure

1. **Check ArgoCD:**
   ```bash
   kubectl get application kube-prometheus-stack -n argocd
   ```

2. **Force Sync:**
   ```bash
   argocd app sync kube-prometheus-stack --force --grpc-web
   ```

3. **Check PVCs:**
   ```bash
   kubectl get pvc -n default | grep prometheus
   ```

4. **Verify Storage:**
   ```bash
   kubectl get pods -n synology-csi
   ```

### Data Loss Prevention

**Critical PVC:**
- `prometheus-kube-prometheus-stack-prometheus-db-prometheus-kube-prometheus-stack-prometheus-0`
- Uses `synology-iscsi-retain` storage class
- PV retained even if PVC deleted

**Backup Recommendations:**
- Synology snapshot schedule for Prometheus volume
- Regular testing of restore procedures
- Document alert rules and dashboard configs in git

## Getting Help

### Collect Diagnostic Information

```bash
# Create diagnostic bundle
kubectl describe pods -n default > monitoring-pods.txt
kubectl logs -n default prometheus-kube-prometheus-stack-prometheus-0 -c prometheus > prometheus.log
kubectl logs -n default deployment/kube-prometheus-stack-grafana > grafana.log
kubectl get events -n default --sort-by='.lastTimestamp' > events.txt
```

### Useful Commands Reference

```bash
# Port-forward to UIs
kubectl port-forward -n default svc/kube-prometheus-stack-prometheus 9090:9090
kubectl port-forward -n default svc/kube-prometheus-stack-grafana 3000:80
kubectl port-forward -n default svc/kube-prometheus-stack-alertmanager 9093:9093

# Check resource usage
kubectl top pods -n default | grep prometheus
kubectl top pods -n unipoller

# View CRDs
kubectl get prometheus -A
kubectl get servicemonitor -A
kubectl get prometheusrule -A
```

## Related Documentation

- [Monitoring Overview](../monitoring/overview.md)
- [kube-prometheus-stack Guide](../applications/kube-prometheus-stack.md)
- [UniFi Poller Guide](../applications/unipoller.md)
- [Storage Troubleshooting](../storage/synology-csi.md)
