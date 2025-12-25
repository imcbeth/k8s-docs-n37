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
