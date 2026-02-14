---
sidebar_position: 1
title: "Network Overview"
description: "Comprehensive network architecture documentation for the Raspberry Pi Kubernetes homelab cluster"
---

# Network Overview

This document describes the complete network architecture for the Raspberry Pi Kubernetes homelab cluster.

## VLAN Configuration

| Name | VLAN ID | Subnet | Gateway | Purpose |
|------|---------|---------|---------|---------|
| Home | 1 | 10.0.1.0/24 | 10.0.1.1 | Primary home network, NAS, gateway |
| IoT | 2 | 10.0.2.0/24 | 10.0.2.1 | Internet of Things devices |
| Kubernetes | 10 | 10.0.10.0/24 | 10.0.10.1 | Kubernetes cluster nodes and services |
| Work | 100 | 10.0.100.0/24 | 10.0.100.1 | Work devices and VPN |
| Guest | 99 | 10.0.99.0/24 | 10.0.99.1 | Guest network |

## Wireless Networks

| SSID | VLAN ID | Subnet | Security | Notes |
|------|---------|---------|----------|-------|
| micro-net | 1 | 10.0.1.0/24 | WPA3 | Primary home network |
| micro-iot | 2 | 10.0.2.0/24 | WPA2 | IoT devices (legacy compatibility) |
| micro-guest | 99 | 10.0.99.0/24 | WPA3 | Guest access, isolated |

## Network Infrastructure

### Gateway/Router

- **Device:** UniFi Dream Router (UDR7)
- **IP Address:** 10.0.1.1
- **Management:** UniFi Network Application
- **Features:**
  - VLAN routing between subnets
  - DNS forwarding to Cloudflare (1.1.1.1, 1.0.0.1)
  - CyberSecure Enhanced by Proofpoint (IDS, ad-blocking, threat prevention)
  - RFC2136 support for dynamic DNS (to be configured)
  - DHCP server for all VLANs

### Switch

- **Device:** UniFi USW-Pro-24-PoE
- **Management IP:** 10.0.1.x (managed via UniFi Controller)
- **Power:** Powers all 5 Raspberry Pi nodes via PoE
- **Previous:** TP-Link TL-SG1008MP (replaced December 2025)

### DNS & Security

**Infrastructure as Code Management:**

- **[UniFi Terraform Configuration](terraform.md)** - Automated network infrastructure management
- Complete Terraform generation toolkit for UniFi components
- Version-controlled network policies and VLAN configurations
- Automated import and management of existing infrastructure

- **Primary DNS:** Cloudflare (1.1.1.1, 1.0.0.1)
- **Security Services:** UniFi CyberSecure Enhanced by Proofpoint
  - Intrusion Detection System (IDS)
  - Ad-blocking and malware prevention
  - Threat intelligence and reputation filtering
  - Content filtering
- **Status:** Integrated into UniFi OS, active across all VLANs
- **Previous Solution:** Pi-hole (deprecated and not deployed - migrated to CyberSecure Enhanced)
  - **Note:** Pi-hole manifests remain in the homelab repository for historical reference but are not deployed to the cluster

## Kubernetes Cluster Network (VLAN 10)

### Node IP Addresses

| Hostname | IP Address | MAC Address | Role | PoE Port |
|----------|------------|-------------|------|----------|
| control-plane | 10.0.10.214 | - | Control Plane | - |
| node01 | 10.0.10.235 | - | Worker | - |
| node02 | 10.0.10.211 | - | Worker | - |
| node03 | 10.0.10.244 | - | Worker | - |
| node04 | 10.0.10.220 | - | Worker | - |

:::info
All nodes are Raspberry Pi 5 (16GB) running Ubuntu 24.04.3 LTS with Kubernetes v1.35.0.
MAC addresses and PoE port mappings will be documented once collected.
:::

### Kubernetes Networking

#### CNI (Container Network Interface)

- **Plugin:** Calico v3.31.3 (via Tigera Operator)
- **Namespace:** `calico-system` (operator-managed)
- **Operator Namespace:** `tigera-operator`
- **Pod CIDR:** 192.168.0.0/16
- **Block Size:** /26 (64 IPs per node)
- **Encapsulation:** IP-in-IP
- **BGP:** Enabled
- **Network Policy:** Enabled and actively configured
- **Typha:** Deployed with topology spread constraints across all nodes (port 5473/tcp)

:::info Migration Note
Migrated from manifest-based Calico (kube-system) to Tigera Operator-managed (calico-system) in January 2026. The operator provides better lifecycle management and configuration via the Installation CR.
:::

**ArgoCD Application:** `tigera-operator` (sync-wave: -100)

```yaml
# Key Installation CR settings
spec:
  variant: Calico
  calicoNetwork:
    bgp: Enabled
    ipPools:
      - cidr: 192.168.0.0/16
        encapsulation: IPIP
        natOutgoing: Enabled
        blockSize: 26
    nodeAddressAutodetectionV4:
      kubernetes: NodeInternalIP
  typhaDeployment:
    spec:
      template:
        spec:
          topologySpreadConstraints:
            - maxSkew: 1
              topologyKey: kubernetes.io/hostname
              whenUnsatisfiable: ScheduleAnyway
```

#### Service Network

- **Service CIDR:** 10.96.0.0/12 (Kubernetes default)
- **DNS Service:** CoreDNS at 10.96.0.10
- **Cluster Domain:** cluster.local

### MetalLB Load Balancer

- **Mode:** Layer 2
- **IP Pool:** 10.0.10.10 - 10.0.10.99 (90 available IPs)
- **IP Pool Name:** first-pool
- **Auto-assign:** Enabled
- **Status:**
  - Assigned IPv4: 1 (ingress-nginx-controller)
  - Available IPv4: 89

See the [MetalLB guide](../applications/metallb.md) for detailed configuration.

#### Allocated LoadBalancer IPs

| Service | Namespace | IP Address | Ports | Purpose |
|---------|-----------|------------|-------|---------|
| ingress-nginx-controller | ingress-nginx | 10.0.10.10 | 80, 443 | Main ingress controller |

### Ingress Configuration

- **Controller:** ingress-nginx v1.14.3 (Helm chart v4.14.3, ArgoCD-managed)
- **External IP:** 10.0.10.10 (via MetalLB)
- **TLS:** Let's Encrypt via cert-manager (Cloudflare DNS-01 challenge)
- **Security Headers:** X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy
- **TLS Hardening:** TLSv1.2+, HSTS, server-preferred ciphers
- **Public Domain:** k8s.n37.ca
- **IngressClass:** nginx (default)

See the [Ingress NGINX guide](../applications/ingress-nginx.md) for detailed configuration.

#### Active Ingresses

| Host | Namespace | Service | TLS | Status |
|------|-----------|---------|-----|--------|
| argocd.k8s.n37.ca | argocd | argocd-server | ✅ | Active |
| grafana.k8s.n37.ca | default | kube-prometheus-stack-grafana | ✅ | Active |
| localstack.k8s.n37.ca | localstack | localstack | ✅ | Active |

## External Services (VLAN 1 - Home Network)

| Service | IP Address | Purpose | Access |
|---------|------------|---------|--------|
| UniFi Gateway (UDR7) | 10.0.1.1 | Router, DHCP, DNS forwarder | HTTPS |
| Synology NAS (DS925+) | 10.0.1.204 | iSCSI storage, NFS, SMB | HTTPS, iSCSI |
| UniFi Controller | 10.0.1.1 | Network management | Built into UDR7 |

### Synology NAS Network Configuration

- **Hostname:** synology-nas (local DNS)
- **Management:** HTTPS on port 5001
- **iSCSI Target:** 10.0.1.204:3260
- **Services:**
  - iSCSI: Provides storage to Kubernetes via Synology CSI
  - SMB/NFS: File sharing
  - SNMP: Monitored by SNMP exporter (SNMPv3, port 161)
  - Docker: Container services (not used by K8s)

## DNS Configuration

### Internal DNS (Kubernetes)

- **Service:** CoreDNS
- **ClusterIP:** 10.96.0.10
- **Zone:** cluster.local
- **Upstream:** Host DNS (10.0.1.1 → Cloudflare)

### External DNS (Planned)

- **Provider 1:** Cloudflare DNS
  - **Zone:** k8s.n37.ca
  - **API:** Uses cert-manager API token
  - **Purpose:** Public DNS records for external access

- **Provider 2:** UniFi UDR7 (RFC2136)
  - **Zone:** k8s.n37.ca (internal)
  - **Purpose:** Split-horizon DNS for internal access
  - **Status:** Pending RFC2136 TSIG key configuration

### DNS Flow

```
Client Query → UniFi Gateway (10.0.1.1) →
  ├─ CyberSecure Enhanced: Filters threats/ads
  ├─ Internal: Local DNS overrides
  └─ Upstream: Cloudflare 1.1.1.1/1.0.0.1
```

## TLS/SSL Certificates

- **Provider:** Let's Encrypt
- **ACME Challenge:** DNS-01 (via Cloudflare API)
- **Issuer:** ClusterIssuer (cert-manager)
- **Renewal:** Automatic (60 days before expiry)
- **Storage:** Kubernetes Secrets

See the [cert-manager guide](../applications/cert-manager.md) for detailed configuration.

### Certificate List

| Domain | Type | Issuer | Valid Until | Used By |
|--------|------|--------|-------------|---------|
| argocd.k8s.n37.ca | TLS | Let's Encrypt | Auto-renew | ArgoCD |
| grafana.k8s.n37.ca | TLS | Let's Encrypt | Auto-renew | Grafana |
| localstack.k8s.n37.ca | TLS | Let's Encrypt | Auto-renew | LocalStack |

## Firewall & Security

### Inter-VLAN Routing

- **Default:** VLANs are isolated
- **Allowed Routes:**
  - Kubernetes VLAN (10) → Home VLAN (1): For NAS access
  - All VLANs → Internet via gateway
  - Guest VLAN (99): Isolated, internet-only

### Port Forwarding

- **Status:** Not configured (no public-facing services)
- **Cloudflare Tunnel:** Potential future use for secure public access

### Network Policies (Kubernetes)

- **Status:** Active and enforced
- **CNI:** Calico (via Tigera Operator)
- **Policy Types:** Ingress and Egress
- **ArgoCD Application:** `network-policies`

**Default Policies:**

- Namespace isolation (deny-all by default)
- Allow DNS egress (UDP 53, TCP 53) to kube-system
- Allow Kubernetes API access
- Allow Prometheus scraping from monitoring namespace
- Allow istio-system control plane communication

**Namespace-specific Policies (13 namespaces):**

- `ingress-nginx` - Allow external traffic, backend routing, Prometheus scraping
- `istio-system` - Allow HBONE tunnel, istiod xDS, Prometheus scraping
- `gatekeeper-system` - Allow webhook calls, Prometheus scraping
- `localstack`, `unipoller`, `loki`, `trivy-system`, `velero`, `argo-workflows` - Application-specific rules
- `cert-manager`, `external-dns`, `metallb-system`, `falco` - Infrastructure rules

See [Network Policies](../security/network-policies.md) for detailed configuration.

## Monitoring & Observability

### Network Monitoring

- **UniFi Metrics:** Collected by UniFi Poller → Prometheus
  - Client connections
  - Bandwidth usage per device
  - PoE power consumption
  - Uplink statistics

- **SNMP Monitoring:**
  - Synology NAS via SNMP exporter
  - Network interface statistics on all nodes via node-exporter

- **Ingress Metrics:**
  - ingress-nginx controller metrics → Prometheus
  - Request rates, latencies, error rates per Ingress

### Service Mesh (Istio Ambient)

- **Status:** Deployed and active
- **Mode:** Ambient (sidecar-less architecture)
- **Version:** 1.28.3
- **Components:**
  - `istiod` - Control plane (1 replica)
  - `ztunnel` - Per-node DaemonSet for L4 mTLS
  - `istio-cni` - CNI plugin for traffic redirection
- **Namespace:** `istio-system`
- **Purpose:** Zero-trust networking, mTLS between services, traffic observability

**ArgoCD Applications:**

- `istio-base` (sync-wave: -46) - CRDs and base resources
- `istiod` (sync-wave: -44) - Control plane
- `istio-cni` (sync-wave: -45) - CNI plugin
- `istio-ztunnel` (sync-wave: -42) - ztunnel DaemonSet

:::tip Ambient Mode Benefits
Ambient mode eliminates per-pod sidecars, reducing resource overhead by ~90% compared to traditional sidecar injection. The ztunnel DaemonSet handles L4 mTLS transparently.
:::

## Network Performance

### Bandwidth

- **Internet Uplink:** Depends on ISP (document actual speed)
- **Internal Network:** 1 Gbps (switch ports)
- **Pi NIC:** 1 Gbps Ethernet (Raspberry Pi 5)
- **iSCSI Storage:** 1 Gbps (Synology to cluster)

### Latency

- **Pod-to-Pod (same node):** < 1ms (local)
- **Pod-to-Pod (cross-node):** 1-2ms (via Calico overlay)
- **Pod-to-External:** Depends on service location

## Troubleshooting

### Common Network Issues

#### Pod cannot reach external internet

**Symptoms:** Pods fail to connect to external services or download images.

**Diagnostic Steps:**

1. Check CoreDNS is running:

   ```bash
   kubectl get pods -n kube-system -l k8s-app=kube-dns
   ```

2. Check Calico pods running:

   ```bash
   kubectl get pods -n calico-system
   ```

3. Check node has default route:

   ```bash
   kubectl get nodes -o wide
   ```

#### LoadBalancer IP not assigned

**Symptoms:** Service stuck in `<pending>` state for external IP.

**Diagnostic Steps:**

1. Check MetalLB pods:

   ```bash
   kubectl get pods -n metallb-system
   ```

2. Check IP pool has available IPs:

   ```bash
   kubectl get ipaddresspool -n metallb-system
   ```

3. Verify Service type is LoadBalancer:

   ```bash
   kubectl get svc <service-name> -n <namespace>
   ```

#### Ingress not accessible

**Symptoms:** Cannot access ingress hostname from browser.

**Diagnostic Steps:**

1. Check ingress-nginx controller running:

   ```bash
   kubectl get pods -n ingress-nginx
   kubectl get svc -n ingress-nginx
   ```

2. Check Ingress resource:

   ```bash
   kubectl get ingress -n <namespace>
   kubectl describe ingress <ingress-name> -n <namespace>
   ```

3. Check DNS resolves to MetalLB IP:

   ```bash
   nslookup <hostname>
   ```

4. Check TLS certificate:

   ```bash
   kubectl get certificate -n <namespace>
   ```

#### Cannot ping hostNetwork pods on other nodes

**Symptoms:** Pods with `hostNetwork: true` cannot communicate across nodes.

**Root Cause:** This is a known Calico limitation with IP-in-IP encapsulation.

**Workaround:** Use pod network IPs instead of node IPs for inter-pod communication.

### Diagnostic Commands

```bash
# Check node network status
kubectl get nodes -o wide

# Check pod network (Calico via Tigera Operator)
kubectl get pods -n calico-system
kubectl get pods -n tigera-operator

# Check MetalLB status
kubectl get pods -n metallb-system
kubectl get ipaddresspool -n metallb-system

# Check ingress controller
kubectl get pods -n ingress-nginx
kubectl get svc -n ingress-nginx

# Test DNS resolution from pod
kubectl run -it --rm debug --image=busybox --restart=Never -- nslookup kubernetes.default

# Check service endpoints
kubectl get endpoints <service-name> -n <namespace>

# View Calico configuration
kubectl get felixconfiguration -o yaml

# Check MetalLB configuration
kubectl get l2advertisement -n metallb-system -o yaml
```

## Future Enhancements

- [x] ~~Configure External-DNS for automatic DNS record creation~~ ✅ Deployed
- [x] ~~Implement NetworkPolicies for namespace isolation~~ ✅ Active
- [x] ~~Deploy Service Mesh~~ ✅ Istio Ambient deployed
- [ ] Set up VPN for secure remote cluster access (Tailscale or WireGuard)
- [ ] Document actual ISP bandwidth and latency baselines
- [ ] Create network topology diagram
- [ ] Implement egress traffic monitoring
- [ ] Consider IPv6 enablement
- [ ] Waypoint proxies for L7 policies (Istio Ambient)

## References

- **Calico Documentation:** [Calico Docs](https://docs.tigera.io/calico/latest)
- **MetalLB Documentation:** [MetalLB](https://metallb.universe.tf/)
- **ingress-nginx:** [ingress-nginx](https://kubernetes.github.io/ingress-nginx/)
- **UniFi Network:** [UniFi](https://ui.com/)
- **Synology NAS:** 10.0.1.204 (DSM interface)

---

**Last Updated:** 2026-02-14
