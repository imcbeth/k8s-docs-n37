---
sidebar_position: 1
---

# Homelab Infrastructure Documentation

Welcome to the comprehensive documentation for my Kubernetes-based homelab infrastructure. This documentation covers everything from initial setup to advanced monitoring and troubleshooting.

## 🏠 What is this Homelab?

This homelab is built around a **5-node Raspberry Pi 5 cluster** running Kubernetes, complete with:

- **High-performance hardware**: Pi 5s with 16GB RAM and NVMe SSDs
- **Enterprise-grade storage**: Synology NAS with iSCSI integration
- **Professional monitoring**: Prometheus, Grafana, and UniFi network monitoring
- **GitOps workflow**: ArgoCD for declarative application management
- **Network infrastructure**: UniFi networking with comprehensive monitoring

## 🎓 Prerequisites & Recommended Skills

### Essential Skills

Before diving into this homelab setup, these foundational skills will be invaluable:

#### 🐧 **Linux System Administration**

- Command line proficiency (bash, file permissions, process management)
- Package management and service configuration
- SSH and remote system management
- Basic troubleshooting and log analysis

#### 🐳 **Containerization & Orchestration**

- **Docker**: Container concepts, Dockerfile creation, image management
- **Kubernetes**: Pods, Services, Deployments, ConfigMaps, Secrets
- **YAML**: Configuration file syntax and structure
- **Container registries**: Image versioning and management

#### 🌐 **Networking Fundamentals**

- TCP/IP, DNS, DHCP concepts
- VLANs and network segmentation
- Port forwarding and firewall rules
- Load balancing and ingress concepts

### Intermediate Skills

#### 🔄 **GitOps & Infrastructure as Code**

- **Git**: Version control, branching, pull requests
- **ArgoCD**: Application deployment and synchronization
- **Terraform**: Infrastructure automation and state management
- **Helm**: Kubernetes package management

#### 📊 **Monitoring & Observability**

- **Prometheus**: Metrics collection and PromQL queries
- **Grafana**: Dashboard creation and data visualization
- **Alert management**: Notification rules and escalation policies
- **Log aggregation**: Centralized logging concepts

#### 💾 **Storage & Data Management**

- **Persistent Volumes**: Kubernetes storage concepts
- **iSCSI**: Network storage protocols
- **Backup strategies**: Data protection and recovery
- **Database administration**: Basic SQL and NoSQL concepts

### 🚀 Getting Started Path

#### **Beginner Track** (2-4 weeks)

1. **Linux Basics**: Set up a virtual machine, practice command line
2. **Docker Fundamentals**: Run containers, build simple images
3. **Git Basics**: Create repositories, make commits, understand workflows
4. **YAML Syntax**: Practice writing configuration files

#### **Intermediate Track** (1-2 months)

1. **Kubernetes Basics**: Deploy applications, understand core concepts
2. **Network Setup**: Configure home networking, understand VLANs
3. **Monitoring Setup**: Install Prometheus and Grafana locally
4. **GitOps Workflow**: Set up ArgoCD, deploy from Git

#### **Advanced Track** (Ongoing)

1. **Production Practices**: Security, backup strategies, high availability
2. **Custom Applications**: Deploy your own services and databases
3. **Advanced Networking**: Complex routing, security policies
4. **Automation**: Infrastructure as Code, CI/CD pipelines

## 📚 Learning Resources

### 🎯 **Recommended Starting Points**

- **Kubernetes**: [Official Kubernetes Tutorial](https://kubernetes.io/docs/tutorials/)
- **Docker**: [Docker Get Started Guide](https://docs.docker.com/get-started/)
- **Prometheus**: [Prometheus Getting Started](https://prometheus.io/docs/prometheus/latest/getting_started/)
- **ArgoCD**: [ArgoCD Getting Started Guide](https://argo-cd.readthedocs.io/en/stable/getting_started/)

### 🏠 **Homelab-Specific Resources**

- **Raspberry Pi Clusters**: Hardware setup and clustering guides
- **UniFi Networking**: Network design and monitoring setup
- **Synology NAS**: iSCSI configuration and integration
- **GitOps Practices**: Repository structure and workflow design

## 📁 Project Structure

This homelab infrastructure is organized across multiple repositories:

### 🏠 [homelab](https://github.com/imcbeth/homelab)

The main repository containing:

- **Kubernetes Manifests**: All application deployments and configurations
- **ArgoCD Applications**: GitOps workflow definitions
- **Secrets Management**: SealedSecrets for GitOps-compatible encrypted secrets
- **Scripts**: Validation and maintenance utilities
- **Hardware Documentation**: Network topology and hardware specifications

### 📚 [k8s-docs-n37](https://github.com/imcbeth/k8s-docs-n37)

This documentation site built with Docusaurus:

- **Comprehensive Guides**: Step-by-step setup and configuration instructions
- **Troubleshooting**: Common issues and solutions
- **Architecture Documentation**: System design and component relationships
- **Best Practices**: Lessons learned and recommended approaches

### 🌐 [unifi-tf-generator](https://github.com/imcbeth/unifi-tf-generator)

Terraform automation for UniFi network management:

- **Infrastructure as Code**: Network configuration through Terraform
- **Automated Imports**: Scripts to import existing UniFi configurations
- **Resource Management**: Networks, firewall rules, port forwarding, and more
- **Version Control**: Track and manage network infrastructure changes

## 🚀 Quick Start

If you're new to this setup, start here:

1. **[Hardware Overview](getting-started/hardware)** - Learn about the physical infrastructure
2. **[Prerequisites](getting-started/prerequisites)** - Software and network requirements
3. **[Kubernetes Installation](kubernetes/installation)** - Step-by-step cluster setup

## 📊 Recent Infrastructure Updates

*Checked against the running cluster on 2026-11-22. Newest first.*

### NAS Patch and Node OS Updates (November 2026)

- **Full shutdown for the Synology DSM update**, using the documented [shutdown and startup procedure](kubernetes/cluster-maintenance)
- **Node OS**: Ubuntu packages applied on all five nodes during the window; every node now runs kernel `6.8.0-1068-raspi`, with the Kubernetes packages held
- **Back to baseline**: 38/38 applications Synced and Healthy, 108/108 Prometheus targets up

### Images Scanned Before They Ship (November 2026)

- **Image gate**: in-cluster builds (Kaniko in [Argo Workflows](applications/argo-workflows)) push only the commit tag; a Trivy scan against the in-cluster Trivy server must pass (no fixable CRITICAL) before `:latest` moves and the deploy runs
- **Covers**: the lifeonabike.ca site, its publishing agent, and the flink-demo image
- **Alerting**: the CVE-increase alerts now count each running image once, so one image reported by several pods no longer inflates the total

### Flink 2.2 and Kafka 4.2.2 (November 2026)

- **[Flink](applications/flink)**: flink-demo moved from Flink 1.20 to **2.2.1** on Java 17.0.21, because PyFlink 1.20 pinned a vulnerable pyarrow; verified end to end (CSV → Kafka → S3)
- **[Kafka](applications/kafka)**: Strimzi-managed cluster upgraded to **4.2.2** (broker Java 21.0.13.1)

### LAN Gateway Replaces ingress-nginx (November 2026)

- **ingress-nginx retired upstream and removed** on 2026-11-15
- **[LAN gateway](applications/lan-gateway)**: an Istio Gateway API gateway on `10.0.10.11` serves ten LAN hosts (Argo CD, Grafana, Argo Workflows, Falco, Flink, LocalStack, the registry, status, oauth and lifeonabike.ca), plus an HTTP → HTTPS redirect
- **Sign-in**: GitHub sign-in through [oauth2-proxy](applications/oauth2-proxy) as Istio forward-auth

### Mesh Traffic Allow-Lists (November 2026)

- **HBONE restricted**: each namespace's NetworkPolicy used to admit Istio's HBONE port (15008) from anywhere, which let any meshed pod reach any port; each now lists the namespaces that may connect
- **AuthorizationPolicies** narrow it further to service accounts and ports where needed (for example, build pods → Trivy server)

### lifeonabike.ca Publishing Agent (November 2026)

- **[lifeonabike](applications/lifeonabike)**: a Go agent watches Strava for new rides, collects photos from an inbox share on the NAS, and opens pull requests on the site's repository
- **SRE checks**: it also watches the public site and posts alerts straight to Alertmanager

### Kubernetes 1.36 (July 2026)

- **Upgraded 1.35.0 → 1.36.3** across all five nodes with kubeadm
- **Next**: Istio 1.31.4 and Calico 3.33.1 (weekend of 2026-11-28), then Kubernetes 1.37.1 (weekend of 2026-12-05)

### Platform Additions (March–June 2026)

- **Logs and traces**: Grafana Alloy replaced Promtail; [Tempo](applications/tempo) for tracing
- **Registry**: [Zot](applications/zot) OCI registry and pull-through cache (`registry.k8s.n37.ca`)
- **Event-driven builds**: [Argo Events](applications/argo-events) and [Argo Workflows](applications/argo-workflows) build and deploy on push
- **Streaming**: Strimzi [Kafka](applications/kafka), the Flink Kubernetes Operator and [LocalStack](applications/localstack) (S3)
- **Status and resilience**: [Uptime Kuma](applications/uptime-kuma) and [Chaos Mesh](applications/chaos-mesh)

### CNI Migration to Tigera Operator (January 2026)

- **Tigera Operator**: Migrated Calico CNI from manifest-based to operator-managed
- **Namespace**: `calico-system` (previously `kube-system`)
- **Version**: Calico v3.31.7 via Tigera Operator (tigera/operator v1.40.15)
- **Typha**: Deployed with topology spread constraints across all nodes
- **ArgoCD Managed**: Sync-wave -100 for foundational infrastructure

### Service Mesh (since January 2026)

- **Istio Ambient Mode**: Sidecar-less service mesh for zero-trust networking
- **Version**: Istio 1.30.8 (1.31.4 planned for 2026-11-28; 1.30 reaches end of life on 2026-12-16)
- **Components**: istiod, ztunnel (DaemonSet), istio-cni
- **mTLS**: Automatic L4 encryption between services
- **11 Namespaces in Mesh**: argo-events, argo-workflows, default, flink-demo, flink-operator, kafka, localstack, loki, strimzi-system, trivy-system, unipoller
- **Resource Savings**: ~90% reduction vs traditional sidecar injection

### Runtime Security (since January 2026)

- **Falco 0.45.2**: eBPF-based runtime threat detection on all nodes
- **Custom Rules**: Tuned for homelab to reduce false positives
- **Falcosidekick UI**: Web interface for alert visualization
- **Integration**: Prometheus metrics and alerting

### Backup Strategy (since January 2026)

- **Velero with Backblaze B2**: Production backup storage with 11 nines durability
- **Daily ArgoCD Backup**: 1:30 AM, 30-day retention
- **Daily Critical PVC Backup**: 2:00 AM, 30-day retention (default, loki, trivy-system, uptime-kuma, zot, lifeonabike)
- **Weekly Cluster Backup**: 3:00 AM Sunday, 90-day retention
- **CSI Snapshots**: Native Synology NAS snapshots via snapshot-controller (the NFS photo inbox cannot be CSI-snapshotted; see [Velero](applications/velero))
- **Verified**: 72/72 retained backups Completed, and a restore validator tests restores on a schedule

### Security Scanning (since January 2026)

- **Trivy Operator**: Continuous container vulnerability scanning (113 VulnerabilityReports)
- **Vulnerability Reduction**: 81% reduction in CRITICAL (53 → 10) in the January remediation
- **Compliance Reports**: CIS Kubernetes Benchmark, NSA Hardening Guidance, Pod Security Standards (baseline and restricted), summarised weekly to Alertmanager
- **PrometheusRule Alerts**: Critical vulnerability notifications via AlertManager

### Secrets Management (since January 2026)

- **Sealed Secrets**: Migrated from git-crypt to Bitnami Sealed Secrets
- **GitOps-Compatible**: All secrets stored as encrypted SealedSecrets in Git
- **Automatic Decryption**: Sealed Secrets controller decrypts at runtime
- **21 SealedSecrets** across 12 namespaces
- **Full GitOps**: No manual `kubectl apply` for secrets (except bootstrap)

### GitOps Migration (December 2025)

- **ArgoCD Management**: Migrated UniFi Poller and kube-prometheus-stack to GitOps
- **Automated Deployments**: All applications self-heal and auto-sync from git
- **Resource Optimization**: Added CPU/memory limits for Pi cluster stability
- **Container Pinning**: Images pinned to specific versions, with a few exceptions still on `latest` (such as `bitnami/kubectl` in maintenance jobs)
- **Namespace Organization**: Dedicated namespaces for better isolation

### Storage Infrastructure

- **Synology CSI Driver**: Persistent storage over iSCSI (10 PVCs), plus one static NFS volume for the lifeonabike photo inbox
- **Storage Classes**: `synology-iscsi-retain` for critical data, `synology-iscsi-delete` for rebuildable data
- **Prometheus Persistence**: 50Gi volume preserving months of metrics history

### Network Migration to UniFi

- **UniFi Network Stack**: Complete migration from consumer networking
- **Network Monitoring**: UniFi Poller v2.38.0 with dedicated namespace
- **Performance Monitoring**: 20-second metrics collection intervals
- **Comprehensive Metrics**: Device health, client connections, bandwidth tracking

### Automated Dependency Updates (since January 2026)

- **Renovate GitHub App**: Automated Helm chart and Docker image updates
- **Grouped Updates**: ArgoCD, monitoring, networking, security, backup tools
- **Weekend Schedule**: Sat/Sun 6am-9pm to minimize disruption
- **PR Workflow**: All updates go through PR review before merging

### Ingress Hardening (February 2026, since retired)

- **Helm Migration**: ingress-nginx moved to an ArgoCD-managed Helm chart, with security headers, TLSv1.2+ and HSTS
- **Retired**: replaced by the Istio LAN gateway on 2026-11-15 (see above)

### Admission Control (since February 2026)

- **OPA Gatekeeper**: Kubernetes admission control policy engine (v3.23.1)
- **5 Policies in Deny Mode**: Resource limits, allowed repos, required labels, block NodePort, container limits
- **Exclusions per Policy**: Each constraint excludes only the namespaces it must (for example, system and operator namespaces whose pods it cannot change)
- **0 Violations**: Across all five constraints and 38 ArgoCD applications
- **Monitoring**: PodMonitor + Grafana dashboard for constraint violations

### Network Policies (since January 2026)

- **Namespace Isolation**: 29 of 34 namespaces have Kubernetes NetworkPolicies (the rest are `kube-node-lease`, `kube-public` and three test or staging namespaces)
- **Allow-List Approach**: Default-deny with explicit allow rules, ingress and egress
- **Monitoring Preserved**: Prometheus metrics scraping allowed across all policies
- **GitOps Managed**: ArgoCD Application at sync-wave -40

### Monitoring Stack

- **kube-prometheus-stack 93.6.1**: Fully GitOps-managed via ArgoCD
- **Grafana Dashboards**: 53 dashboard ConfigMaps provisioned from git
- **Alert Management**: 54 PrometheusRule resources for infrastructure and application alerts
- **Multi-Source Deployment**: Helm chart + custom values managed in git
- **38 ArgoCD Applications**: All Synced & Healthy

## 🛠️ Key Features

- **GitOps Workflow**: All configurations managed through Git and ArgoCD
- **High Availability**: Multi-node cluster with persistent storage
- **Comprehensive Monitoring**: Infrastructure, application, and network metrics
- **Professional Networking**: UniFi-based network infrastructure
- **Automated Deployments**: Self-healing applications with ArgoCD
- **Enterprise Storage**: Synology NAS integration for persistent data

## 🤝 Getting Involved

### Exploring the Codebase

- Browse the [homelab repository](https://github.com/imcbeth/homelab) for Kubernetes manifests and configurations
- Check out the [unifi-tf-generator](https://github.com/imcbeth/unifi-tf-generator) for network automation examples
- Contribute to this documentation by submitting PRs to [k8s-docs-n37](https://github.com/imcbeth/k8s-docs-n37)

### Local Development

- **Documentation**: Clone this repository and run `npm start` for local development
- **Manifests**: Use the validation scripts in the homelab repo to test changes
- **Network Config**: Use the Terraform generator to manage UniFi infrastructure

### 📋 What's Next?

Ready to dive deeper? Here are some recommended paths:

- **Infrastructure Admins**: Start with [Kubernetes Installation](kubernetes/installation) and [ArgoCD Setup](applications/argocd)
- **Monitoring Enthusiasts**: Jump to [Monitoring Overview](monitoring/overview) and explore [Grafana Dashboards](monitoring/grafana-dashboards)
- **Network Engineers**: Explore [Networking Overview](networking/overview) and [Terraform Automation](networking/terraform)
- **Storage Administrators**: Learn about [Synology CSI](storage/synology-csi) and persistent volume management
