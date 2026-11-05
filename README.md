# Homelab Documentation Site

[![Built with Docusaurus](https://img.shields.io/badge/Built%20with-Docusaurus-brightgreen.svg)](https://docusaurus.io/)
[![Deployment Status](https://img.shields.io/badge/GitHub%20Pages-Live-brightgreen.svg)](https://imcbeth.github.io/k8s-docs-n37/)

## Overview

This repository contains a comprehensive Docusaurus-based documentation site for a Raspberry Pi Kubernetes homelab cluster. The site provides detailed deployment guides, troubleshooting documentation, and operational runbooks for all infrastructure components.

**Live Documentation:** [https://imcbeth.github.io/k8s-docs-n37/](https://imcbeth.github.io/k8s-docs-n37/)

## Quick Start

### Development Server

```bash
npm install
npm start
```

The development server starts at `http://localhost:3000` with hot reload enabled.

### Production Build

```bash
npm run build
npm run serve
```

## Directory Structure

### Core Documentation

- **[`docs/`](docs/)** - Main documentation content
  - **[`applications/`](docs/applications/)** - Application deployment guides (ArgoCD, Grafana, Loki, etc.)
  - **[`getting-started/`](docs/getting-started/)** - Initial setup and hardware guides
  - **[`kubernetes/`](docs/kubernetes/)** - Core Kubernetes component documentation
  - **[`monitoring/`](docs/monitoring/)** - Prometheus, Grafana, and observability setup
  - **[`networking/`](docs/networking/)** - Network architecture and DNS configuration
  - **[`storage/`](docs/storage/)** - Persistent storage and backup strategies
  - **[`security/`](docs/security/)** - Security policies and configurations
  - **[`troubleshooting/`](docs/troubleshooting/)** - Common issues and solutions

### Site Configuration

- **[`blog/`](blog/)** - Blog posts and announcements
- **[`src/`](src/)** - React components and custom pages
  - **[`components/`](src/components/)** - Reusable React components
  - **[`css/`](src/css/)** - Custom CSS styling
  - **[`pages/`](src/pages/)** - Additional static pages
- **[`static/`](static/)** - Static assets (images, files)
- **[`docusaurus.config.ts`](docusaurus.config.ts)** - Main Docusaurus configuration
- **[`sidebars.ts`](sidebars.ts)** - Documentation sidebar navigation

## Key Documentation Files

### Project Information

- **[README.md](README.md)** - This project overview
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - Contribution guidelines and development setup
- **[CODEOWNERS](CODEOWNERS)** - Code ownership and review assignments
- **[docs/todo.md](docs/todo.md)** - Project roadmap and improvement tracking

### Application Guides

- **[ArgoCD](docs/applications/argocd.md)** - GitOps deployment platform
- **[Grafana Dashboards](docs/monitoring/grafana-dashboards.md)** - Monitoring visualizations
- **[Loki](docs/applications/loki.md)** - Log aggregation and analysis
- **[External-DNS](docs/applications/external-dns.md)** - Automated DNS record management
- **[Blackbox Exporter](docs/applications/blackbox-exporter.md)** - Endpoint monitoring

## Project Completion Status

**Overall Progress: ~90% Complete**

Based on the [TODO roadmap](docs/todo.md):

- **✅ Completed:** 55+ major tasks
- **🔄 In Progress:** 4 ongoing initiatives
- **📋 Planned:** 10 future enhancements

### Recently Completed (January-February 2026)

- ✅ Velero backup strategy with Backblaze B2 and CSI snapshots
- ✅ Falco runtime security with eBPF driver
- ✅ OPA Gatekeeper admission control (5 policies in deny mode)
- ✅ Istio Ambient mesh deployment (sidecar-less mTLS)
- ✅ Sealed Secrets migration from git-crypt
- ✅ Network Policies for 10 namespaces
- ✅ Trivy vulnerability scanning and remediation (81% CRITICAL reduction)
- ✅ Blackbox Exporter endpoint monitoring

### Current Focus

- 🔄 Documentation updates and accuracy
- 🔄 Dependency updates via Renovate
- 🔄 Advanced alerting configuration
- 🔄 Phase 4: Advanced features and automation

## Related Repositories

- **[homelab](https://github.com/imcbeth/homelab)** - Infrastructure manifests and GitOps configuration
- **[unifi-tf-generator](https://github.com/imcbeth/unifi-tf-generator)** - Terraform configuration generator for UniFi networks

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, writing guidelines, and contribution workflow.

## Architecture

**Infrastructure:** 5x Raspberry Pi 5 (16GB each) running Kubernetes v1.36.3
**GitOps:** ArgoCD managing 24 applications (all Synced & Healthy)
**Monitoring:** Prometheus + Grafana + Loki stack
**Storage:** Synology NAS with CSI integration
**Networking:** UniFi with VLAN segmentation
