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

### Storage Infrastructure
- **Synology CSI Driver**: Deployed for persistent storage support with iSCSI
- **Persistent Volumes**: Configured retention policies for critical data
- **Storage Classes**: `synology-iscsi-retain` for high-availability storage

### Network Migration to UniFi
- **UniFi Network Stack**: Complete migration from consumer networking
- **Network Monitoring**: UniFi Poller integration with Prometheus
- **Performance Monitoring**: 20-second metrics collection intervals

### Monitoring Stack Enhancements
- **Prometheus Stack**: Updated kube-prometheus-stack configuration
- **Grafana Dashboards**: Enhanced network and storage visibility
- **Alert Management**: Comprehensive alerting for infrastructure health

## 🛠️ Key Features

- **GitOps Workflow**: All configurations managed through Git and ArgoCD
- **High Availability**: Multi-node cluster with persistent storage
- **Comprehensive Monitoring**: Infrastructure, application, and network metrics
- **Professional Networking**: UniFi-based network infrastructure
- **Automated Deployments**: Self-healing applications with ArgoCD
- **Enterprise Storage**: Synology NAS integration for persistent data
