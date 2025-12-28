---
sidebar_position: 2
title: "UniFi Terraform Management"
description: "Infrastructure as Code for UniFi network components using Terraform"
---

# UniFi Terraform Infrastructure as Code

## Overview

This guide covers managing UniFi network infrastructure using Terraform with the automated configuration generator. The [unifi-tf-generator](https://github.com/imcbeth/unifi-tf-generator) repository provides tools to extract existing UniFi configurations and generate corresponding Terraform code.

## Architecture

### UniFi Infrastructure Components

Our homelab network infrastructure is managed through Terraform, covering:

- **Network Devices** - Access points, switches, and gateways
- **VLANs and Networks** - Segmented network topology
- **Firewall Rules** - Security policies and traffic control
- **Port Forwarding** - NAT configuration for services
- **User Management** - Authentication and authorization
- **Wireless Networks** - WiFi SSIDs and access controls

### Current Network Topology

| Component | Model | Purpose | IP Address |
|-----------|--------|---------|------------|
| Gateway | UDR7 | Primary router and controller | 10.0.1.1 |
| Switch | USW-Pro-24-POE | Core network switching | 10.0.1.x |
| Access Points | U6 Extender | Wireless coverage | 10.0.1.159 |

## Terraform Generator

### Repository Structure

The `unifi-tf-generator` repository contains:

```
unifi-tf-generator/
├── scripts/                    # Generation and utility scripts
│   ├── all.sh                 # Main generation orchestrator
│   ├── get_*.sh               # API data extraction scripts
│   ├── generate_*.sh          # Terraform generation scripts
│   └── test_connectivity.sh   # Network validation
├── json/                      # Extracted API data
├── tests/                     # Mock server for testing
├── *.tf                       # Generated Terraform files
├── *_import.tf               # Terraform import commands
└── *_map.tf                  # Data mapping configurations
```

### Generated Resources

The generator creates Terraform configurations for:

| Resource Type | File | Purpose |
|---------------|------|---------|
| **Accounts** | `unifi_accounts.tf` | User authentication |
| **Devices** | `unifi_devices.tf` | Physical network devices |
| **Networks** | `unifi_networks.tf` | VLANs and subnets |
| **Firewall Rules** | `unifi_firewall_rules.tf` | Security policies |
| **Firewall Groups** | `unifi_firewall_groups.tf` | Address/port groups |
| **Port Forwarding** | `unifi_port_forward.tf` | NAT rules |
| **Port Profiles** | `unifi_port_profiles.tf` | Switch configurations |
| **Wireless Networks** | `unifi_wlans.tf` | WiFi SSIDs |
| **User Groups** | `unifi_user_groups.tf` | Access control |

## Usage

### Prerequisites

- **UniFi Controller** with admin access
- **Terraform** v1.6.3+ (recommended v1.7.0 or later)
- **Bash 4.0+** with associative arrays
- **curl** and **jq** for API communication

### Quick Start

```bash
# Clone the generator repository
git clone https://github.com/imcbeth/unifi-tf-generator.git
cd unifi-tf-generator

# Test connectivity to UniFi controller
make test

# Prompt for UniFi controller password (input will be hidden)
read -s -p "Enter UniFi controller password: " UNIFI_PASSWORD
echo

# Generate complete Terraform configuration without exposing the password on the command line
UNIFI_PASSWORD="$UNIFI_PASSWORD" ./scripts/all.sh -i <CONTROLLER_IP> -u <USERNAME>

# Initialize and import existing infrastructure
terraform init
# Use the generated `*_import.tf` files for terraform import commands
# (see the unifi-tf-generator README for detailed import instructions)

# Plan and apply changes
terraform plan
terraform apply
```

### Configuration Workflow

1. **Extract Configuration** - Scripts connect to UniFi controller API
2. **Generate Terraform** - Create `.tf` files from extracted data
3. **Import Existing** - Use `terraform import` for current resources
4. **Plan Changes** - Review proposed modifications
5. **Apply Updates** - Deploy infrastructure changes

## Network Configuration

### VLAN Structure

Our network uses VLAN segmentation for security and organization:

```hcl
# Example VLAN configuration
resource "unifi_network" "kubernetes_vlan" {
  name          = "Kubernetes"
  purpose       = "corporate"
  subnet        = "10.0.10.0/24"
  vlan_id       = 10
  dhcp_start    = "10.0.10.10"
  dhcp_stop     = "10.0.10.250"
  dhcp_enabled  = true
}

resource "unifi_network" "iot_vlan" {
  name          = "IoT"
  purpose       = "vlan-only"
  subnet        = "10.0.2.0/24"
  vlan_id       = 2
  dhcp_start    = "10.0.2.10"
  dhcp_stop     = "10.0.2.250"
  dhcp_enabled  = true
}
```

### Firewall Rules

Security policies are enforced through firewall rules:

```hcl
# Example firewall rule
resource "unifi_firewall_rule" "block_iot_to_internal" {
  name        = "Block IoT to Internal"
  action      = "drop"
  ruleset     = "LAN_IN"
  rule_index  = 2000
  protocol    = "all"

  src_address_group = "IoT_Devices"
  dst_address_group = "Internal_Networks"

  logging = true
}
```

### Device Management

Network devices are managed with lifecycle protection:

```hcl
resource "unifi_device" "main_switch" {
  name          = "USW Pro 24 PoE"
  mac           = "58:d6:1f:1f:cd:02"
  site          = data.unifi_site.default.name

  allow_adoption    = false
  forget_on_destroy = false

  lifecycle {
    prevent_destroy = true
  }
}
```

## Best Practices

### Security Considerations

- **Admin Access Required** - Generator needs admin-level UniFi account
- **API Token Management** - Secure storage of authentication credentials
- **Network Isolation** - Generator should run from trusted network segment
- **Backup Before Changes** - Always backup controller before Terraform apply

### Terraform State Management

- **Remote State** - Use Terraform Cloud or S3 backend for state storage
- **State Locking** - Prevent concurrent modifications
- **Import Strategy** - Import existing resources before making changes
- **Lifecycle Rules** - Protect critical infrastructure with `prevent_destroy`

### Development Workflow

1. **Test Locally** - Validate connectivity and generation
2. **Plan Carefully** - Review all changes before applying
3. **Incremental Updates** - Apply changes in small batches
4. **Monitor Results** - Verify network functionality after changes

## Integration with Homelab

### Relationship to Kubernetes Cluster

The UniFi Terraform configuration manages the network foundation for our Kubernetes homelab:

- **Kubernetes VLAN** (10.0.10.0/24) - Dedicated network for cluster nodes
- **Port Forwarding** - External access to services (ArgoCD, Grafana)
- **Firewall Rules** - Security policies for cluster traffic
- **DNS Integration** - Works with External-DNS for automatic record management

### Monitoring Integration

Network metrics from UniFi devices are collected via:

- **UniFi Poller** - Prometheus exporter for device metrics
- **SNMP Monitoring** - Additional device health monitoring
- **Custom Dashboards** - Grafana visualization of network performance

## Troubleshooting

### Common Issues

**Connection Failures**

```bash
# Test controller connectivity (requires valid/trusted certificate)
curl https://<CONTROLLER_IP>/api/auth/login

# Check network accessibility
./scripts/test_connectivity.sh -i <CONTROLLER_IP>
```

**Authentication Problems**

- Verify admin-level access on UniFi account
- Check username/password credentials
- Ensure 2FA is disabled for API account

**Generation Errors**

- Review `log.txt` for detailed error messages
- Verify bash version 4.0+ with associative arrays
- Check jq installation and JSON parsing

**Terraform Issues**

- Validate generated `.tf` files syntax
- Check provider version compatibility
- Verify import commands match existing resources

### Logs and Debugging

```bash
# Enable debug logging
export DEBUG=1
./scripts/all.sh

# Check generation logs
tail -f log.txt

# Validate Terraform syntax
terraform validate
terraform plan
```

## Related Documentation

- **[Network Overview](overview.md)** - High-level network architecture
- **[External-DNS](../applications/external-dns.md)** - Automated DNS management
- **[UniFi Poller](../applications/unipoller.md)** - Network monitoring
- **[Getting Started - Hardware](../getting-started/hardware.md)** - Physical infrastructure

## Repository Links

- **[unifi-tf-generator](https://github.com/imcbeth/unifi-tf-generator)** - Terraform generation toolkit
- **[homelab](https://github.com/imcbeth/homelab)** - Kubernetes infrastructure manifests
