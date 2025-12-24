# Homelab Documentation Site

This repository contains a [Docusaurus](https://docusaurus.io/) documentation site for homelab Kubernetes infrastructure.

🚀 **Live Site**: [https://imcbeth.github.io/k8s-docs-n37/](https://imcbeth.github.io/k8s-docs-n37/)

## 🏗️ Infrastructure Covered

- **Raspberry Pi 5 Cluster** - 5-node Kubernetes cluster setup
- **Synology NAS Integration** - iSCSI storage with CSI driver
- **UniFi Network Monitoring** - Network observability stack
- **Prometheus & Grafana** - Comprehensive monitoring setup
- **GitOps with ArgoCD** - Application deployment automation

## 🚀 Quick Start

```bash
# Clone the repository
git clone https://github.com/imcbeth/k8s-docs-n37.git
cd k8s-docs-n37

# Install dependencies
npm install

# Start development server
npm start

# Build for production
npm run build

# Serve built site locally
npm run serve
```

## 📁 Structure

- `/docs` - Main documentation content
- `/blog` - Blog posts for updates and changes
- `/src` - Custom React components and pages
- `/static` - Static assets (images, files, etc.)

## 📝 Contributing

The documentation is automatically deployed to GitHub Pages when changes are pushed to the `main` branch.

### Adding New Documentation

1. Create markdown files in the appropriate `/docs` subdirectory
2. Add frontmatter with title and description
3. Update `sidebars.ts` to include the new pages
4. Test locally with `npm run build`
5. Commit and push to trigger automatic deployment

## 🔧 Development

The site runs locally at `http://localhost:3000` with hot reloading enabled for instant content updates.

### Documentation Organization

- **Getting Started** - Hardware setup, prerequisites, overview
- **Kubernetes** - Installation and cluster management guides
- **Monitoring** - Prometheus, Grafana, and observability stack
- **TODO** - Planned improvements and roadmap

## ✨ Features

- **Search**: Built-in search functionality
- **Dark Mode**: Automatic dark/light theme switching
- **Responsive**: Mobile-friendly responsive design
- **Mermaid**: Diagram support for architecture diagrams
- **Code Highlighting**: Syntax highlighting for YAML, bash, etc.
- **GitHub Integration**: Edit links and automated deployment

## 🚀 Deployment

The site is automatically deployed to GitHub Pages via GitHub Actions when changes are pushed to the main branch. No manual deployment required!

The deployment workflow:
1. Checkout code
2. Install dependencies
3. Build static site
4. Deploy to GitHub Pages

---

**Note**: This documentation site provides comprehensive guides for setting up and managing a production-ready Kubernetes homelab on Raspberry Pi hardware.
