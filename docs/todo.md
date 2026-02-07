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

### 4. **Backup Strategy** ✅ COMPLETED (2026-01-14)

- [x] **Velero** - Deployed with CSI snapshot support and Backblaze B2 storage
- [x] **Daily ArgoCD backup** - Automated at 1:30 AM, 30-day retention
- [x] **Daily critical PVC backup** - Automated at 2:00 AM (Prometheus, Loki, Grafana, Pi-hole)
- [x] **Weekly cluster resource backup** - Automated at 3:00 AM Sunday, 90-day retention
- [x] Backup testing and restore procedures verified with B2
- [x] Velero documentation complete with monitoring alerts

**Documentation:** See [Velero Application Guide](./applications/velero.md) for complete deployment details and disaster recovery procedures.

### 5. **Security Scanning & Runtime Protection** ✅ COMPLETED (2026-01-05)

- [x] **Trivy Operator** - Container vulnerability scanning deployed
- [x] Vulnerability reports generating for all workloads (95 images)
- [x] Grafana dashboard for security metrics
- [x] PrometheusRule alerts for critical vulnerabilities
- [x] Compliance reporting (CIS Kubernetes Benchmark, NSA Hardening)
- [x] **Falco** - Runtime security monitoring (eBPF driver, all 5 nodes, chart v8.0.0)
- [x] **OPA Gatekeeper** - Policy enforcement (5 policies, deny mode since 2026-02-07)

**Documentation:** See [Trivy Operator Guide](./applications/trivy-operator.md) and [Vulnerability Remediation Guide](./applications/trivy-vulnerability-remediation.md) for details.

### 5b. **Network Policies** ✅ COMPLETED (2026-01-29)

- [x] **Kubernetes NetworkPolicies** - Namespace isolation deployed via ArgoCD
- [x] 10 namespaces protected: localstack, unipoller, loki, trivy-system, velero, argo-workflows, cert-manager, external-dns, metallb-system, falco
- [x] Allow-list approach: Default-deny ingress with explicit allow rules
- [x] Prometheus metrics scraping preserved across all policies
- [x] DNS egress allowed for all namespaces
- [x] Documentation complete with testing procedures
- [ ] Implement Calico GlobalNetworkPolicy for cluster-wide rules
- [ ] Network policy monitoring dashboard in Grafana

**Documentation:** See [Network Policies Guide](./security/network-policies.md) for complete policy definitions and management procedures.

## 🚀 **Platform Enhancements**

### 6. **Service Mesh** ✅ COMPLETED (2026-01-28)

- [x] Evaluated **Istio Ambient** vs **Linkerd** for the Pi cluster (chose Istio Ambient)
- [x] Deployed Istio Ambient mesh v1.28.3 (sidecarless architecture)
- [x] mTLS encryption between services via ztunnel
- [x] 6 namespaces in mesh: default, loki, localstack, argo-workflows, unipoller, trivy-system
- [ ] L7 authorization policies (future enhancement)
- [ ] Circuit breaker and retry policies (future enhancement)

### 7. **Log Aggregation** ✅ COMPLETED (2025-12-28)

- [x] Deploy **Loki + Promtail** stack for centralized logging
- [x] Integrate with existing Grafana instance (auto-discovered datasource)
- [x] Configure log retention policies (7 days, 20Gi PVC)
- [x] Promtail DaemonSet on all 5 nodes (including control-plane)
- [x] Set up log-based alerting via Loki ruler (11 alert rules)
- [x] Loki log analytics dashboard deployed

**Documentation:** See [Loki Application Guide](./applications/loki.md) for complete deployment details including log-based alerting.

### 8. **Secrets Management** ✅ COMPLETED (2026-01-14)

- [x] **Sealed Secrets** - GitOps-friendly encrypted secrets (chosen over ESO)
- [x] Migrate existing secrets to managed solution (8 SealedSecrets deployed)
- [x] Document secrets management procedures
- [x] Sealing key backup procedures documented
- [ ] Set up automated secret rotation reminders (future enhancement)

**Note:** Evaluated both External Secrets Operator and Sealed Secrets. Chose Sealed Secrets for homelab due to 7x less memory usage and simpler architecture.

**Documentation:** See [Secrets Management Guide](./security/secrets-management.md) for complete procedures including rotation and disaster recovery.

## 📊 **Advanced Monitoring & Dashboards**

### 9. **Custom Dashboards** ✅ COMPLETED (2025-12-28)

- [x] Pi cluster temperature monitoring dashboard
- [x] Node resource monitoring dashboard (CPU, memory, disk I/O, network)
- [x] Loki log analytics dashboard
- [x] Trivy security scanning dashboard
- [x] 43 total Grafana dashboards deployed via GitOps
- [ ] Power consumption tracking (if UPS available)
- [ ] Network utilization by VLAN/segment (advanced)

**Documentation:** See [Grafana Dashboards Guide](./monitoring/grafana-dashboards.md) for dashboard details.

### 10. **Alerting Improvements** ✅ PARTIALLY COMPLETED (2026-01-12)

- [x] Configure **AlertManager** email notifications (Gmail SMTP)
- [x] Implement tiered alerting (warning → critical severity levels)
- [x] Set up predictive alerts for disk space (`predict_linear()`)
- [x] Synology NAS health alerts (disk failures, RAID, temperature)
- [x] Velero backup monitoring alerts (7 alert rules)
- [x] Log-based alerting via Loki ruler (11 alert rules)
- [ ] Configure webhook to Discord/Slack (future enhancement)
- [ ] Create runbooks for common alert scenarios (future enhancement)

**Note:** 121 emails delivered successfully as of 2026-01-14. AlertManager fully operational.

## 🏗️ **Infrastructure & DevOps**

### 11. **GitOps Enhancements** ✅ PARTIALLY COMPLETED (2026-01-23)

- [x] **Renovate** - Automated dependency updates for manifests (GitHub App deployed)
  - [x] ArgoCD Application manifest scanning (Helm charts)
  - [x] Docker image tag updates in Kubernetes manifests
  - [x] Grouped updates (ArgoCD, monitoring, networking, security, backup)
  - [x] Weekend schedule (Sat/Sun 6am-9pm) to minimize disruption
- [ ] Evaluate **Flux** as ArgoCD complement for specific workflows
- [ ] Pre-commit hooks for Kubernetes manifest validation
- [ ] Automated testing pipeline for infrastructure changes
- [ ] GitOps workflow documentation

**Configuration:** See `renovate.json` in homelab repository for full configuration.

### 12. **Development & CI/CD Tools**

- [ ] **Gitea** or **GitLab** - Self-hosted git repository
- [ ] **Harbor** - Container registry with vulnerability scanning
- [x] **Argo Workflows** - CI/CD pipeline automation (deployed, chart v0.47.3)
- [ ] Build and deployment automation for custom containers
- [ ] Integration with existing ArgoCD setup

## 🌐 **Network & Access Management**

### 13. **DNS & Service Discovery** ✅ COMPLETED (2025-12-27)

- [x] **External-DNS** - Automatic DNS record creation with dual provider support
  - [x] Deployed Cloudflare provider for public DNS
  - [x] Deployed UniFi webhook provider (kashalls v0.7.0) for internal DNS
  - [x] Split-horizon DNS configuration (k8s.n37.ca)
  - [x] TXT registry for ownership tracking
  - [x] Configured ingress annotations for ArgoCD, Grafana, Localstack
  - [x] Verified DNS record creation in both providers
- [ ] **CoreDNS** customization for internal service discovery
- [ ] DNS-based load balancing configuration
- [ ] DNS monitoring and troubleshooting tools

**Note:** External-DNS is fully operational with dual providers (Cloudflare + kashalls UniFi webhook). All ingress resources have external-dns annotations for automatic DNS management. See [External-DNS documentation](./applications/external-dns.md) for complete details.

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

### **Phase 1: Foundation & Reliability** ✅ COMPLETED

1. ✅ External-DNS deployment (dual provider: Cloudflare + UniFi)
2. ✅ Backup strategy (Velero + critical PVC backups + B2 storage)
3. ✅ Enhanced alerting (AlertManager email notifications)
4. ✅ Metrics server deployment

### **Phase 2: Security & Observability** ✅ COMPLETED

1. ✅ Security scanning (Trivy Operator)
2. ✅ Secrets management migration (Sealed Secrets)
3. ✅ Blackbox exporter for endpoint monitoring
4. ✅ Custom Grafana dashboards (43 total)
5. ✅ Log-based alerting (Loki ruler)

### **Phase 3: Advanced Features** ✅ COMPLETED

1. ✅ Network policies implementation (10 namespaces isolated 2026-01-29)
2. ✅ GitOps enhancements (Renovate deployed - automated dependency updates)
3. ✅ Argo Workflows for pipeline automation (chart v0.47.3)
4. ✅ Service mesh deployed (Istio Ambient v1.28.3)
5. ✅ Runtime security (Falco v8.0.0 + OPA Gatekeeper v3.21.1 in deny mode)

### **Phase 4: Optimization & Expansion** 🚧 IN PROGRESS

1. ✅ Storage performance dashboard (PR #383)
2. ✅ Network utilization dashboard (PR #385)
3. ✅ SealedSecrets key rotation (30-day rotation enabled)
4. Resource optimization and VPA
5. Chaos engineering and resilience testing
6. Advanced networking and VPN (Tailscale/WireGuard)
7. Development tools (Gitea/GitLab, Harbor)

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

- **homelab/.claude/notes/** - Session notes and context (CURRENT.md, REFERENCE.md, sessions/)
- **homelab/TODO.md** - Infrastructure repository TODO list (should sync with this)
- **homelab/Hardware.md** - Cluster hardware specifications
- **homelab/network-info.md** - Comprehensive network configuration
