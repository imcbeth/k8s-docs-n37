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

## 📂 Project Repositories

This homelab project is organized across multiple repositories:

- **[homelab](https://github.com/imcbeth/homelab)** - Main repository containing Kubernetes manifests, ArgoCD applications, and infrastructure configurations
- **[k8s-docs-n37](https://github.com/imcbeth/k8s-docs-n37)** - This documentation site built with Docusaurus
- **[unifi-tf-generator](https://github.com/imcbeth/unifi-tf-generator)** - Terraform automation for UniFi network infrastructure management

## 💡 Skills Useful for Similar Setups

If you're interested in building something similar, these skills would be helpful:

**Core Infrastructure:**

- **Linux basics** - Command line, SSH, file management
- **Docker & Kubernetes** - Container concepts and orchestration
- **Git** - Version control and collaboration workflows

**Homelab Specific:**

- **Hardware setup** - Raspberry Pi, networking equipment, storage devices
- **Networking** - VLANs, DNS, DHCP configuration
- **Monitoring tools** - Prometheus, Grafana for observability

**Advanced (Optional):**

- **GitOps** - ArgoCD for automated deployments
- **Terraform** - Infrastructure as code for network management
- **Storage systems** - NAS configuration and iSCSI

Start with the core skills and gradually work your way up as you expand your homelab!

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
- **Secrets Management**: Encrypted secrets for services (external-dns, cert-manager, etc.)
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

### Monitoring Stack Enhancements

- **Prometheus Stack v80.6.0**: Fully GitOps-managed via ArgoCD
- **Grafana Dashboards**: 20+ pre-loaded dashboards for comprehensive visibility
- **Alert Management**: PrometheusRule CRDs for infrastructure health alerts
- **Multi-Source Deployment**: Helm chart + custom values managed in git

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
