---
sidebar_position: 100
title: "TODO & Roadmap"
description: "Planned improvements and ongoing projects for the homelab infrastructure"
---

# Homelab TODO & Improvements

## 🔍 **Monitoring & Observability Enhancements**

### 0. **Prometheus Monitoring Stack Fixes** ✅ COMPLETED (2025-12-26)

- [x] Fixed node-exporter scraping issues (changed to hostNetwork: false)
- [x] Resolved Grafana Multi-Attach PVC errors (Recreate deployment strategy)
- [x] Disabled unreachable control plane monitoring (controller-manager, etcd, proxy, scheduler)
- [x] All 5 Raspberry Pi nodes now fully monitored
- [x] Clean Prometheus targets page (no scraping errors)

**Documentation:** See [kube-prometheus-stack Known Issues](./applications/kube-prometheus-stack.md#known-issues-and-solutions) for detailed troubleshooting guides.

### 1. **SNMP Monitoring for Synology** ✅ COMPLETED

- [x] Deploy SNMP exporter for Synology NAS monitoring
- [x] Configure Prometheus scrape config for SNMP metrics
- [x] Add Grafana dashboards for NAS performance, disk health, temperature
- [ ] Set up alerts for disk failures, high temperature, storage capacity (pending)

```yaml
# Add to prometheus scrape configs
- job_name: 'synology-snmp'
  static_configs:
    - targets: ['10.0.1.204']
  metrics_path: /snmp
  params:
    module: [synology]
  relabel_configs:
    - source_labels: [__address__]
      target_label: __param_target
    - source_labels: [__param_target]
      target_label: instance
    - target_label: __address__
      replacement: snmp-exporter:9116
```

### 2. **Node Exporter for Pi Cluster** ✅ COMPLETED

- [x] Deploy node-exporter on all 5x Pi 5 nodes
- [x] Monitor CPU temperature and throttling
- [x] Track NVMe SSD health and performance metrics
- [x] Memory usage and available capacity monitoring
- [x] Network interface statistics

### 3. **Blackbox Exporter** ✅ COMPLETED (2025-12-27)

- [x] Deploy blackbox exporter for endpoint monitoring
- [x] Monitor external services availability (DNS, HTTP/HTTPS)
- [x] SSL certificate expiry monitoring
- [x] Network latency and response time tracking
- [x] Add alerts for service downtime

**Documentation:** See [Blackbox Exporter Application Guide](./applications/blackbox-exporter.md) for complete deployment details.

## 🛡️ **Security & Backup**

### 4. **Backup Strategy**

- [ ] **Velero** - Deploy for Kubernetes cluster backup
- [ ] **Restic** - Set up application data backup to Synology NAS
- [ ] **ArgoCD backup** - Automate app-of-apps configuration backup
- [ ] Schedule regular backup testing and restore procedures
- [ ] Document backup and restore processes

### 5. **Security Scanning & Runtime Protection**

- [ ] **Trivy Operator** - Container vulnerability scanning
- [ ] **Falco** - Runtime security monitoring and threat detection
- [ ] **OPA Gatekeeper** - Policy enforcement and admission control
- [ ] Security policy definitions for workloads
- [ ] Compliance reporting and alerting

## 🚀 **Platform Enhancements**

### 6. **Service Mesh**

- [ ] Evaluate **Istio** vs **Linkerd** for the Pi cluster
- [ ] Implement traffic management and load balancing
- [ ] Add observability for service-to-service communication
- [ ] Implement security policies and mTLS
- [ ] Circuit breaker and retry policies

### 7. **Log Aggregation** ✅ COMPLETED (2025-12-27)

- [x] Deploy **Loki + Promtail** stack for centralized logging
- [x] Integrate with existing Grafana instance (auto-discovered datasource)
- [x] Configure log retention policies (7 days, 20Gi PVC)
- [x] Promtail DaemonSet on all 5 nodes (including control-plane)
- [ ] Set up log-based alerting for errors and anomalies (pending)
- [ ] Create custom log dashboards for application troubleshooting (pending)

**Documentation:** See [Loki Application Guide](./applications/loki.md) for complete deployment details.

### 8. **Secrets Management**

- [ ] **External Secrets Operator** - Use Synology as secrets backend
- [ ] **Sealed Secrets** - GitOps-friendly encrypted secrets
- [ ] Migrate existing secrets to managed solution
- [ ] Set up secret rotation automation
- [ ] Document secrets management procedures

## 📊 **Advanced Monitoring & Dashboards**

### 9. **Custom Dashboards**

- [ ] Pi cluster temperature monitoring dashboard
- [ ] Power consumption tracking (if UPS available)
- [ ] Network utilization by VLAN/segment
- [ ] Storage performance metrics (iSCSI latency, IOPS)
- [ ] Application performance monitoring (APM)

### 10. **Alerting Improvements**

- [ ] Configure **AlertManager** webhook to Discord/Slack
- [ ] Implement tiered alerting (warning → critical → page)
- [ ] Set up predictive alerts for disk space and temperature
- [ ] Create runbooks for common alert scenarios
- [ ] Test alert routing and escalation

## 🏗️ **Infrastructure & DevOps**

### 11. **GitOps Enhancements**

- [ ] **Renovate** - Automated dependency updates for manifests
- [ ] Evaluate **Flux** as ArgoCD complement for specific workflows
- [ ] Pre-commit hooks for Kubernetes manifest validation
- [ ] Automated testing pipeline for infrastructure changes
- [ ] GitOps workflow documentation

### 12. **Development & CI/CD Tools**

- [ ] **Gitea** or **GitLab** - Self-hosted git repository
- [ ] **Harbor** - Container registry with vulnerability scanning
- [ ] **Tekton** or **Argo Workflows** - CI/CD pipeline automation
- [ ] Build and deployment automation for custom containers
- [ ] Integration with existing ArgoCD setup

## 🌐 **Network & Access Management**

### 13. **DNS & Service Discovery**

- [ ] **CoreDNS** customization for internal service discovery
- [ ] **External-DNS** - Automatic DNS record creation (manifest exists, needs UniFi RFC2136 configuration)
  - [ ] Complete UniFi UDR7 RFC2136 setup (TSIG key generation)
  - [ ] Apply external-dns ArgoCD Application
  - [ ] Configure Cloudflare provider for public DNS
  - [ ] Configure UniFi RFC2136 provider for internal DNS
- [ ] Internal domain setup (k8s.n37.ca for split-horizon DNS)
- [ ] DNS-based load balancing configuration
- [ ] DNS monitoring and troubleshooting tools

**Note:** External-DNS manifest is ready but not deployed. See homelab CLAUDE_NOTES.md 2025-12-26 Afternoon session.

### 14. **VPN & Remote Access**

- [ ] **Tailscale** or **WireGuard** - Secure remote access to cluster
- [ ] **oauth2-proxy** - Single Sign-On (SSO) integration
- [ ] Multi-factor authentication setup
- [ ] Remote access policies and user management
- [ ] VPN performance monitoring

## 🔧 **Operational Improvements**

### 15. **Documentation & Knowledge Management**

- [ ] Create operational runbooks for common tasks
- [ ] Document disaster recovery procedures
- [ ] Capacity planning documentation
- [ ] Update network topology diagrams
- [ ] Performance baseline documentation

### 16. **Testing & Validation**

- [ ] Chaos engineering with **Chaos Monkey** or **Litmus**
- [ ] Load testing framework for applications
- [ ] Backup and restore testing automation
- [ ] Network failure simulation and recovery testing
- [ ] Performance regression testing

### 17. **Capacity Planning & Optimization**

- [ ] Resource utilization analysis and optimization
- [ ] Storage capacity planning and alerting
- [ ] Network bandwidth monitoring and optimization
- [ ] Power consumption analysis
- [ ] Cost tracking and optimization (if applicable)

---

## 📅 **Implementation Priority**

Items are organized by priority. Focus on:

### **Phase 1: Foundation & Reliability**

1. External-DNS deployment (unblock pending work)
2. Backup strategy (Velero + critical PVC backups)
3. Enhanced alerting (AlertManager notifications)
4. Metrics server deployment

### **Phase 2: Security & Observability**

1. Security scanning (Trivy Operator)
2. Secrets management migration
3. Blackbox exporter for endpoint monitoring
4. Custom Grafana dashboards
5. Log-based alerting

### **Phase 3: Advanced Features**

1. Service mesh evaluation and potential deployment
2. GitOps enhancements (Renovate)
3. Network policies implementation
4. Development tools and CI/CD

### **Phase 4: Optimization & Expansion**

1. Resource optimization and VPA
2. Chaos engineering and resilience testing
3. Advanced networking and VPN
4. Additional application deployments

---

## 📋 **Notes**

- **Resource Constraints:** All implementations must consider the Pi 5 cluster constraints (80GB RAM total, 20 ARM cores)
- **Testing Strategy:** Test all implementations in a development namespace before production deployment
- **Documentation First:** Document all configurations and procedures for maintainability in this docs site
- **GitOps Workflow:** All changes must go through PR workflow in homelab repo
- **Regular Reviews:** Review and update this TODO list monthly based on cluster evolution
- **Monitoring First:** Ensure monitoring is in place before deploying new workloads

---

## 🔗 **References**

- **homelab/CLAUDE_NOTES.md** - Detailed session notes and troubleshooting history
- **homelab/TODO.md** - Infrastructure repository TODO list (should sync with this)
- **homelab/Hardware.md** - Cluster hardware specifications
- **homelab/network-info.md** - Comprehensive network configuration
