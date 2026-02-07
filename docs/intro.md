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

### 🏠 [homelab](https://github.com/your-username/homelab)

The main repository containing:

- **Kubernetes Manifests**: All application deployments and configurations
- **ArgoCD Applications**: GitOps workflow definitions
- **Secrets Management**: SealedSecrets for GitOps-compatible encrypted secrets
- **Scripts**: Validation and maintenance utilities
- **Hardware Documentation**: Network topology and hardware specifications

### 📚 [k8s-docs-n37](https://github.com/your-username/k8s-docs-n37)

This documentation site built with Docusaurus:

- **Comprehensive Guides**: Step-by-step setup and configuration instructions
- **Troubleshooting**: Common issues and solutions
- **Architecture Documentation**: System design and component relationships
- **Best Practices**: Lessons learned and recommended approaches

### 🌐 [unifi-tf-generator](https://github.com/your-username/unifi-tf-generator)

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

### CNI Migration to Tigera Operator (January 2026)

- **Tigera Operator**: Migrated Calico CNI from manifest-based to operator-managed
- **Namespace**: `calico-system` (previously `kube-system`)
- **Version**: Calico v3.31.3 via Tigera Operator
- **Typha**: Deployed with topology spread constraints across all nodes
- **ArgoCD Managed**: Sync-wave -100 for foundational infrastructure

### Service Mesh Deployment (January 2026)

- **Istio Ambient Mode**: Sidecar-less service mesh for zero-trust networking
- **Version**: Istio 1.28.3
- **Components**: istiod, ztunnel (DaemonSet), istio-cni
- **mTLS**: Automatic L4 encryption between services
- **6 Namespaces in Mesh**: default, loki, localstack, argo-workflows, unipoller, trivy-system
- **Resource Savings**: ~90% reduction vs traditional sidecar injection

### Runtime Security (January 2026)

- **Falco**: eBPF-based runtime threat detection on all nodes
- **Custom Rules**: Tuned for homelab to reduce false positives
- **Falcosidekick UI**: Web interface for alert visualization
- **Integration**: Prometheus metrics and alerting

### Backup Strategy Complete (January 2026)

- **Velero with Backblaze B2**: Production backup storage with 11 nines durability
- **Daily ArgoCD Backup**: 1:30 AM, 30-day retention
- **Daily Critical PVC Backup**: 2:00 AM (Prometheus, Loki, Grafana)
- **Weekly Cluster Backup**: 3:00 AM Sunday, 90-day retention
- **CSI Snapshots**: Native Synology NAS snapshots via snapshot-controller
- **Tested & Verified**: Full backup/restore cycle validated with B2

### Security Scanning Active (January 2026)

- **Trivy Operator**: Continuous container vulnerability scanning
- **95 Images Scanned**: All cluster workloads monitored
- **Vulnerability Reduction**: 81% reduction in CRITICAL (53 → 10)
- **Compliance Reports**: CIS Kubernetes Benchmark, NSA Hardening Guidance
- **PrometheusRule Alerts**: Critical vulnerability notifications via AlertManager

### Secrets Management Migration (January 2026)

- **Sealed Secrets**: Migrated from git-crypt to Bitnami Sealed Secrets
- **GitOps-Compatible**: All secrets now stored as encrypted SealedSecrets in Git
- **Automatic Decryption**: Sealed Secrets controller decrypts at runtime
- **8 Secrets Migrated**: unipoller, external-dns, cert-manager, alertmanager, snmp-exporter, synology-csi, pihole
- **Full GitOps**: No more manual `kubectl apply` for secrets (except bootstrap)

### GitOps Migration (December 2025)

- **ArgoCD Management**: Migrated UniFi Poller and kube-prometheus-stack to GitOps
- **Automated Deployments**: All applications now self-heal and auto-sync from git
- **Resource Optimization**: Added CPU/memory limits for Pi cluster stability
- **Container Pinning**: Locked all images to specific versions (no more `latest`)
- **Namespace Organization**: Dedicated namespaces for better isolation

### Storage Infrastructure

- **Synology CSI Driver**: Deployed for persistent storage support with iSCSI
- **Persistent Volumes**: Configured retention policies for critical data
- **Storage Classes**: `synology-iscsi-retain` for high-availability storage
- **Prometheus Persistence**: 50Gi volume preserving months of metrics history

### Network Migration to UniFi

- **UniFi Network Stack**: Complete migration from consumer networking
- **Network Monitoring**: UniFi Poller v2.11.2 with dedicated namespace
- **Performance Monitoring**: 20-second metrics collection intervals
- **Comprehensive Metrics**: Device health, client connections, bandwidth tracking

### Automated Dependency Updates (January 2026)

- **Renovate GitHub App**: Automated Helm chart and Docker image updates
- **Grouped Updates**: ArgoCD, monitoring, networking, security, backup tools
- **Weekend Schedule**: Sat/Sun 6am-9pm to minimize disruption
- **PR Workflow**: All updates go through PR review before merging

### Admission Control (February 2026)

- **OPA Gatekeeper**: Kubernetes admission control policy engine (v3.21.1)
- **5 Policies in Deny Mode**: Resource limits, allowed repos, required labels, block NodePort, container limits
- **0 Violations**: All violations resolved across 24 ArgoCD applications
- **Monitoring**: PodMonitor + Grafana dashboard for constraint violations

### Network Policies Implementation (January 2026)

- **Namespace Isolation**: 10 namespaces protected with Kubernetes NetworkPolicies
- **Allow-List Approach**: Default-deny ingress with explicit allow rules
- **Namespaces Protected**: localstack, unipoller, loki, trivy-system, velero, argo-workflows, cert-manager, external-dns, metallb-system, falco
- **Monitoring Preserved**: Prometheus metrics scraping allowed across all policies
- **GitOps Managed**: ArgoCD Application at sync-wave -40

### Monitoring Stack Enhancements

- **Prometheus Stack v81.5.0**: Fully GitOps-managed via ArgoCD
- **Grafana Dashboards**: 46 dashboards (4 custom, 13 community, 26 from prometheus-stack)
- **Alert Management**: PrometheusRule CRDs for infrastructure health alerts
- **Multi-Source Deployment**: Helm chart + custom values managed in git
- **24 ArgoCD Applications**: All Synced & Healthy

## 🛠️ Key Features

- **GitOps Workflow**: All configurations managed through Git and ArgoCD
- **High Availability**: Multi-node cluster with persistent storage
- **Comprehensive Monitoring**: Infrastructure, application, and network metrics
- **Professional Networking**: UniFi-based network infrastructure
- **Automated Deployments**: Self-healing applications with ArgoCD
- **Enterprise Storage**: Synology NAS integration for persistent data

## 🤝 Getting Involved

### Exploring the Codebase

- Browse the [homelab repository](https://github.com/your-username/homelab) for Kubernetes manifests and configurations
- Check out the [unifi-tf-generator](https://github.com/your-username/unifi-tf-generator) for network automation examples
- Contribute to this documentation by submitting PRs to [k8s-docs-n37](https://github.com/your-username/k8s-docs-n37)

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
