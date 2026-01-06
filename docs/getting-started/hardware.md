---
sidebar_position: 2
title: "Hardware Setup"
description: "Physical infrastructure and hardware specifications for the Pi cluster"
---

# Hardware Setup

Complete hardware specifications and physical infrastructure for the Raspberry Pi 5 Kubernetes homelab cluster.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Internet / ISP                               │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│  UniFi Dream Router (UDR7)                                      │
│  - Gateway/Router (10.0.1.1)                                    │
│  - VLAN routing, DHCP, DNS forwarding                           │
│  - CyberSecure Enhanced (IDS, threat prevention)                │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│  UniFi USW-Pro-24-PoE Switch                                    │
│  - 24-port Gigabit PoE+ switch                                  │
│  - Powers all 5 Pi nodes via PoE                                │
│  - VLAN tagging for network isolation                           │
└─────┬─────┬─────┬─────┬─────┬──────────────┬───────────────────┘
      │     │     │     │     │              │
      ▼     ▼     ▼     ▼     ▼              ▼
    ┌───┐ ┌───┐ ┌───┐ ┌───┐ ┌───┐    ┌─────────────┐
    │CP │ │N1 │ │N2 │ │N3 │ │N4 │    │ Synology    │
    │   │ │   │ │   │ │   │ │   │    │ DS925+      │
    └───┘ └───┘ └───┘ └───┘ └───┘    │ NAS         │
                                      └─────────────┘
    Raspberry Pi 5 Cluster Nodes      iSCSI Storage
    - 16GB RAM each (80GB total)      (VLAN 1)
    - 256GB NVMe per node
    - Active cooling
    - PoE powered (VLAN 10)

Legend:
  CP = control-plane (10.0.10.214)
  N1-N4 = node01-04 (10.0.10.211-213, 220)
```

## Compute Cluster

### Raspberry Pi 5 Nodes

**Quantity:** 5 nodes

**Specifications per node:**

- **Model:** [Raspberry Pi 5](https://www.raspberrypi.com/products/raspberry-pi-5/) (16GB)
- **CPU:** Broadcom BCM2712 (ARM Cortex-A76 @ 2.4GHz, 4 cores)
- **RAM:** 16GB LPDDR4X-4267
- **Storage:** 256GB NVMe SSD via PCIe Gen 2 x1
- **Network:** Gigabit Ethernet (10/100/1000 Mbps)
- **Power:** PoE+ (802.3at, up to 25.5W per device)
- **GPIO:** 40-pin header (not used in cluster)

**Total Cluster Resources:**

- **CPU:** 20 cores (80 vCPUs with hyperthreading)
- **RAM:** 80GB
- **Local Storage:** 1.28TB NVMe (ephemeral)
- **Architecture:** ARM64 (aarch64)

### Node Configuration

| Hostname | IP Address | Role | OS | Kubernetes |
|----------|------------|------|-----|------------|
| control-plane | 10.0.10.214 | Control Plane | Ubuntu 24.04.3 LTS | v1.35.0 |
| node01 | 10.0.10.211 | Worker | Ubuntu 24.04.3 LTS | v1.35.0 |
| node02 | 10.0.10.212 | Worker | Ubuntu 24.04.3 LTS | v1.35.0 |
| node03 | 10.0.10.213 | Worker | Ubuntu 24.04.3 LTS | v1.35.0 |
| node04 | 10.0.10.220 | Worker | Ubuntu 24.04.3 LTS | v1.35.0 |

### Expansion Hardware (per node)

**PoE + PCIe M.2 HAT:**

- **Model:** [Waveshare PoE M.2 HAT+ (B)](https://www.waveshare.com/wiki/PoE_M.2_HAT+_(B))
- **PoE Standard:** IEEE 802.3at (PoE+)
- **Power Input:** 37-57V DC from PoE
- **Power Output:** 5V DC to Raspberry Pi (up to 25W)
- **M.2 Interface:** PCIe Gen 2 x1 (supports NVMe SSDs)
- **Form Factor:** M.2 2280 (22mm x 80mm)
- **Additional Features:**
  - RTC (Real-Time Clock) with CR1220 battery
  - Cooling fan header (4-pin PWM)
  - Status LEDs for power and activity

**Cooling:**

- **Model:** [Raspberry Pi Active Cooler](https://www.raspberrypi.com/products/active-cooler/)
- **Type:** Aluminum heatsink with integrated PWM fan
- **Fan Speed:** Variable (PWM controlled)
- **Noise Level:** < 20 dBA at full speed
- **Thermal Performance:** Maintains < 60°C under load
- **Connector:** 4-pin connector to Waveshare HAT

**NVMe Storage:**

- **Model:** [Raspberry Pi SSD](https://www.raspberrypi.com/products/ssd/) 256GB
- **Interface:** NVMe 1.4 (PCIe Gen 3 x4 capable, limited to Gen 2 x1 by Pi 5)
- **Actual Speed:** ~400 MB/s read/write (PCIe Gen 2 x1 limitation)
- **Form Factor:** M.2 2280 NVMe
- **Usage:** Root filesystem, container image cache, ephemeral storage

## Storage Infrastructure

### Synology NAS

**Model:** [Synology DS925+](https://www.synology.com/en-us/products/DS925+)

**Specifications:**

- **CPU:** AMD Ryzen R1600 (dual-core @ 2.6 GHz, turbo to 3.1 GHz)
- **RAM:** 4GB DDR4 ECC (upgradeable to 32GB)
- **Drive Bays:** 4x 3.5"/2.5" SATA (hot-swappable)
- **Network:** 2x Gigabit Ethernet (link aggregation capable)
- **Expansion:** 2x M.2 NVMe slots for SSD cache (not populated)

**Network Configuration:**

- **IP Address:** 10.0.1.204 (VLAN 1 - Home network)
- **Hostname:** synology-nas.local
- **Management:** DSM 7.x (HTTPS port 5001)
- **Protocols:**
  - iSCSI Target (port 3260) - Primary Kubernetes storage
  - NFS v3/v4
  - SMB/CIFS
  - SNMP v3 (port 161) - Monitoring

**Storage Configuration:**

- **RAID Type:** SHR (Synology Hybrid RAID) or RAID 1
- **Total Capacity:** Varies by drive configuration (document your setup)
- **Kubernetes Usage:**
  - iSCSI LUNs for Persistent Volumes
  - Synology CSI driver provisioning
  - Storage classes: `synology-iscsi-delete`, `synology-iscsi-retain`
  - Snapshot support via CSI VolumeSnapshots

**Kubernetes Integration:**

- **CSI Driver:** Synology CSI v1.x
- **Features:**
  - Dynamic PVC provisioning
  - Volume expansion
  - Volume snapshots (CSI v1 API)
  - Volume cloning
- **Backup:** Velero with CSI snapshots (storage-native)

## Networking

### Switch

**Model:** [UniFi USW-Pro-24-PoE](https://store.ui.com/us/en/products/usw-pro-24-poe)

**Specifications:**

- **Ports:** 24x Gigabit Ethernet (RJ45)
- **PoE Ports:** 16x PoE+ ports (802.3at)
- **PoE Budget:** 400W total
- **Uplink:** 2x 10G SFP+ ports
- **Management:** UniFi Network Application (on UDR7)
- **Features:**
  - VLAN support (802.1Q)
  - Link aggregation (LACP)
  - Port mirroring
  - Spanning Tree Protocol (STP/RSTP)
  - PoE scheduling and power management

**Cluster Usage:**

- **Ports 1-5:** Raspberry Pi cluster nodes (PoE powered)
- **Port Capacity:** Each Pi draws ~15-20W via PoE
- **Total PoE Draw:** ~75-100W for cluster
- **VLAN:** Tagged VLAN 10 (Kubernetes network)

**Previous Hardware:**

- TP-Link TL-SG1008MP (replaced December 2025)
- Migration reason: More ports, better PoE budget, UniFi integration

### Gateway/Router

**Model:** UniFi Dream Router (UDR7)

**Key Features:**

- **WAN/LAN:** Gigabit Ethernet ports
- **WiFi:** WiFi 6 (802.11ax) integrated access point
- **Processor:** Quad-core ARM Cortex-A53
- **Management:** UniFi Network Application (built-in)
- **Security:** CyberSecure Enhanced by Proofpoint
  - IDS/IPS
  - Ad-blocking
  - Threat prevention
  - Content filtering

**Network Isolation:**

- 5 VLANs configured (see [Network Overview](../networking/overview.md))
- Kubernetes cluster on isolated VLAN 10 (10.0.10.0/24)
- Firewall rules allow Kubernetes → NAS (VLAN 1) for storage access

## Power & Cooling

### Power Budget

**Raspberry Pi Cluster (via PoE):**

- Per node idle: ~8-10W
- Per node under load: ~15-20W
- Total cluster idle: ~40-50W
- Total cluster load: ~75-100W

**Active Cooling:**

- Fan power: ~0.5W per node (~2.5W total)
- Controlled by CPU temperature (PWM)
- Typical operating range: 30-50% fan speed
- Full speed only during sustained high load

**UniFi Switch:**

- Base power consumption: ~30W
- PoE power budget: 400W total (cluster uses ~25%)
- Passive cooling (fanless design)

**Synology DS925+:**

- Idle: ~20-25W (HDD spun down)
- Active: ~35-45W (during I/O operations)
- Cooling: 2x 92mm fans (temperature controlled)

**Total Infrastructure Power:**

- **Minimum (idle):** ~90-105W
- **Typical (moderate load):** ~140-180W
- **Maximum (full load):** ~200-250W

**Power Efficiency:**

- **PUE (Power Usage Effectiveness):** ~1.05-1.1 (no additional cooling)
- **Annual Energy Cost:** ~$150-200 USD (at $0.12/kWh, 24/7 operation)

### Thermal Management

**Raspberry Pi Cooling:**

- **Ambient Target:** 20-25°C room temperature
- **CPU Temps (idle):** 40-50°C
- **CPU Temps (load):** 55-70°C
- **Thermal Throttling:** 80°C (CPU scales down)
- **Critical Shutdown:** 85°C (rarely reached with active cooling)
- **Fan Curve:**
  - 0-50°C: 30% speed (quiet)
  - 50-65°C: 50% speed
  - 65-75°C: 80% speed
  - 75°C+: 100% speed

**NAS Cooling:**

- **Drive Temps (normal):** 30-40°C
- **Drive Temps (max):** 50°C (triggers fan ramp-up)
- **System Fan:** Variable speed based on HDD temperature
- **Airflow:** Front-to-back through drive bays

**Switch Cooling:**

- **Passive cooling** (fanless design)
- **Operating Temp:** 0-40°C ambient
- **Heat dissipation:** Aluminum chassis acts as heatsink

**Cluster Rack Environment:**

- **Ventilation:** Open-frame rack (no enclosure)
- **Airflow:** Natural convection + active cooling per node
- **Noise Level:** < 30 dBA (whisper quiet in home office)

## Physical Layout

**Rack Mounting:**

- **Type:** 19" open-frame rack or shelf mount
- **Height:** ~4U total for cluster + switch
- **Cable Management:**
  - Ethernet: Cat 6 patch cables (color-coded per VLAN)
  - Power: PoE eliminates need for individual power supplies

**Workspace Integration:**

- **Location:** Home office / lab space
- **Acoustics:** Quiet enough for shared workspace
- **Accessibility:** Front-panel access for monitoring LEDs
- **Maintenance:** Hot-swappable components (drives, nodes)

## Compute Performance

**CPU Benchmarks (per node):**

- **Single-core:** ~2400 PassMark score
- **Multi-core:** ~8500 PassMark score
- **Cluster Total:** ~42,500 PassMark score

**Memory Performance:**

- **Bandwidth:** ~25 GB/s per node (LPDDR4X-4267)
- **Latency:** ~80ns (ARM typical)

**Storage Performance:**

**Local NVMe (per node):**

- **Sequential Read:** ~400 MB/s
- **Sequential Write:** ~400 MB/s
- **Random IOPS:** ~50K IOPS (limited by PCIe Gen 2 x1)

**Network Storage (iSCSI via Synology):**

- **Sequential Read:** ~110 MB/s (Gigabit network limit)
- **Sequential Write:** ~110 MB/s
- **Latency:** ~1-2ms (over 1GbE)
- **Protocol Overhead:** iSCSI ~5-10% vs raw block

## Resource Allocation

**Current Kubernetes Usage:**

- **Pods Running:** ~60-80 pods cluster-wide
- **CPU Requests:** ~15-20% of total capacity
- **Memory Requests:** ~40-50% of total capacity (32-40GB allocated)
- **Persistent Storage:** ~50-100GB on Synology NAS

**Headroom:**

- **CPU:** ~60-70% available for workload scaling
- **Memory:** ~40-50% available
- **Storage:** Expandable (add drives to NAS or expand RAID)

## Hardware Reliability

**MTBF (Mean Time Between Failures):**

- **Raspberry Pi 5:** ~100,000 hours (theoretical)
- **NVMe SSDs:** ~1.5M hours (per manufacturer specs)
- **Synology NAS:** ~100,000 hours (with redundant drives)
- **Network Equipment:** ~200,000+ hours

**Redundancy:**

- **Compute:** 5 nodes (4 workers + 1 control plane) - can lose 1-2 workers
- **Storage:** RAID on NAS (can lose 1 drive without data loss)
- **Network:** Single switch (planned: add redundant uplink)
- **Power:** Single PoE switch (planned: add UPS)

**Maintenance Schedule:**

- **Firmware Updates:** Quarterly (Raspberry Pi EEPROM)
- **OS Updates:** Monthly (Ubuntu security patches)
- **Kubernetes:** Every 3-6 months (tested in staging first)
- **NAS DSM:** Quarterly or on security advisories
- **Drive Health:** Monthly SMART checks

## Upgrade Path

**Near-term Upgrades:**

- [ ] UPS (Uninterruptible Power Supply) for graceful shutdown
- [ ] Redundant network uplink (second switch or LAG)
- [ ] NAS RAM upgrade (4GB → 16-32GB for better cache)
- [ ] M.2 NVMe cache on NAS for read acceleration

**Future Expansion:**

- [ ] Add 1-2 more Pi 5 nodes (scale to 7 nodes)
- [ ] Upgrade to 10GbE network (switch + NIC for NAS)
- [ ] Larger NAS or secondary NAS for tiered storage
- [ ] GPU-accelerated node (Jetson Orin or similar for ML workloads)

## Bill of Materials (BOM)

| Category | Item | Quantity | Approx. Cost (USD) |
|----------|------|----------|---------------------|
| **Compute** | Raspberry Pi 5 (16GB) | 5 | $500 |
| | Raspberry Pi Active Cooler | 5 | $25 |
| | Waveshare PoE M.2 HAT+ (B) | 5 | $150 |
| | Raspberry Pi NVMe SSD 256GB | 5 | $200 |
| **Storage** | Synology DS925+ | 1 | $550 |
| | HDD/SSD (varies by config) | 4 | $400-800 |
| **Network** | UniFi USW-Pro-24-PoE | 1 | $600 |
| | UniFi Dream Router (UDR7) | 1 | $200 |
| | Cat 6 Ethernet Cables | 10 | $30 |
| **Accessories** | 19" Rack or Shelf | 1 | $50-150 |
| | Cable Management | - | $20 |
| **Total** | | | **~$2,725-3,225** |

*Prices approximate and subject to change. Excludes shipping, taxes, and optional accessories.*

## Comparison to Cloud Costs

**Equivalent Cloud Resources:**

- AWS: 5x t4g.xlarge (ARM, 4 vCPU, 16GB each) = ~$600/month
- GCP: 5x e2-standard-4 = ~$500/month
- Azure: 5x B4ms = ~$450/month

**Break-even Analysis:**

- Hardware cost: ~$3,000
- Monthly power: ~$15-20
- Break-even vs cloud: 6-7 months
- 5-year TCO savings: ~$25,000+

**Advantages over Cloud:**

- ✅ No egress fees
- ✅ Full hardware control
- ✅ Learning opportunity
- ✅ Low latency (local)
- ✅ Privacy (data stays local)

**Cloud Advantages:**

- ✅ No hardware maintenance
- ✅ Instant scaling
- ✅ Geographic distribution
- ✅ Managed services

---

**Last Updated:** 2026-01-05
**Hardware Version:** v2.0 (Post UniFi migration)
