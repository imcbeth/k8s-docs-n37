---
sidebar_position: 3
title: "Prerequisites"
description: "Software and network requirements before starting the installation"
---

# Prerequisites

Before setting up the Kubernetes cluster, ensure you have the following prerequisites in place.

## Hardware Requirements

### Minimum Requirements
- **5x Raspberry Pi 5**: 8GB RAM minimum (16GB recommended)
- **PoE Switch**: 8+ port PoE+ switch with sufficient power budget
- **Storage**: MicroSD cards (32GB minimum) + NVMe SSDs (256GB recommended)
- **Network**: Stable internet connection and local network

### Recommended Hardware
See the [Hardware Setup](./hardware) guide for detailed specifications of the recommended configuration.

## Network Requirements

### IP Address Planning
Plan your network topology:
- **Management Network**: For cluster nodes and infrastructure
- **Service Network**: For Kubernetes services and ingress
- **Storage Network**: For NAS and storage communication

### DNS Configuration
- Access to public DNS for package downloads
- Ability to configure local DNS records (optional but recommended)
- Consider using Pi-hole for network-level DNS management

### Firewall Rules
Ensure the following ports are available:
- **6443**: Kubernetes API server
- **2379-2380**: etcd server communication
- **10250**: Kubelet API
- **10259**: kube-scheduler
- **10257**: kube-controller-manager
- **30000-32767**: NodePort services range

## Software Requirements

### Operating System
- **Raspberry Pi OS Lite**: 64-bit version recommended
- **Alternative**: Ubuntu Server 22.04 LTS for ARM64

### Required Tools
Install these tools on your workstation:
```bash
# kubectl - Kubernetes command-line tool
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl
sudo mv kubectl /usr/local/bin/

# helm - Kubernetes package manager
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# git - Version control
sudo apt update && sudo apt install git -y
```

### Development Environment (Optional)
- **VS Code**: For editing configurations
- **Docker**: For building custom images
- **Lens**: Kubernetes IDE for cluster management

## Storage Requirements

### Local Storage
- **Boot Storage**: MicroSD cards for initial setup
- **Application Storage**: NVMe SSDs for performance
- **Container Images**: Sufficient space for image cache

### Network Storage
- **NAS Device**: Synology or compatible NAS for persistent storage
- **iSCSI Support**: For block storage integration
- **Backup Storage**: Separate storage for backups

## Knowledge Prerequisites

### Required Knowledge
- **Linux Administration**: Basic command line skills
- **Networking**: Understanding of TCP/IP, DNS, and routing
- **Git**: Version control basics
- **YAML**: Configuration file syntax

### Recommended Knowledge
- **Docker/Containers**: Understanding containerization
- **Kubernetes Basics**: Pods, Services, Deployments
- **Infrastructure as Code**: GitOps principles
- **Monitoring**: Metrics and observability concepts

## Account Requirements

### GitHub Account
Required for:
- Storing configuration repositories
- ArgoCD GitOps workflow
- Accessing community charts and tools

### Container Registries
Access to:
- **Docker Hub**: For public container images
- **Quay.io**: For operator and tool images
- **GitHub Container Registry**: For custom images (optional)

## Security Considerations

### SSH Access
- Configure SSH key-based authentication
- Disable password authentication
- Use strong SSH keys (RSA 4096-bit or Ed25519)

### Network Security
- Enable firewall on all nodes
- Implement network segmentation where possible
- Regular security updates for base OS

### Secrets Management
- Plan for secure storage of sensitive data
- Consider external secrets management
- Regular rotation of credentials

## Time and Effort Planning

### Initial Setup Time
- **Pi Preparation**: 2-4 hours for 5 nodes
- **Network Configuration**: 1-2 hours
- **Kubernetes Installation**: 3-5 hours
- **Basic Applications**: 2-3 hours

### Ongoing Maintenance
- **Weekly**: Monitor cluster health and updates
- **Monthly**: Security patches and dependency updates
- **Quarterly**: Major version updates and reviews

## Next Steps

Once you have all prerequisites in place:

1. **[Hardware Setup](./hardware)** - Physical assembly and configuration
2. **[Kubernetes Installation](../kubernetes/installation)** - Cluster setup
3. **Storage Configuration** - Persistent storage setup (coming soon)
4. **Monitoring Setup** - Observability stack (coming soon)

---

**Note**: This setup assumes familiarity with Linux and networking concepts. If you're new to these technologies, consider starting with a single-node setup to gain experience before expanding to a full cluster.