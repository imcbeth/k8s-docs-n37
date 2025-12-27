---
sidebar_position: 3
title: "MetalLB"
description: "Layer 2 load balancer for bare-metal Kubernetes clusters"
---

# MetalLB - Load Balancer for Bare Metal

## Overview

MetalLB is a load-balancer implementation for bare-metal Kubernetes clusters. It provides LoadBalancer-type Services, which are typically only available in cloud environments. For this homelab cluster, MetalLB runs in Layer 2 mode to assign external IP addresses to Services.

### Key Features

- **LoadBalancer Services:** Enables LoadBalancer type on bare-metal
- **Layer 2 Mode:** Uses ARP to announce IPs on the local network
- **IP Address Management:** Assigns IPs from configured pools
- **Automatic Failover:** Moves IPs between nodes if pods are rescheduled

---

## Deployment Details

### ArgoCD Application

- **Name:** metal-lb
- **Namespace:** metallb-system
- **Project:** infrastructure
- **Sync Wave:** -35
- **Helm Chart:** metallb/metallb v0.14.9
- **Auto-Sync:** Enabled (prune, selfHeal)

### Components

1. **Controller:** Watches Services and assigns IPs
2. **Speaker DaemonSet:** Announces IPs using ARP (Layer 2)

### Resources

```yaml
# Controller resources
controller:
  requests:
    cpu: 100m
    memory: 100Mi

# Speaker (per node - 5 total)
speaker:
  requests:
    cpu: 100m
    memory: 100Mi
```

**Total Resource Usage:**
- CPU Requests: 600m (3% of 20 cores)
- Memory Requests: 600Mi (0.7% of 80GB)

---

## Configuration

### IP Address Pool

MetalLB manages a pool of IP addresses on the Kubernetes VLAN:

```yaml
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: first-pool
  namespace: metallb-system
spec:
  addresses:
  - 10.0.10.10-10.0.10.99  # 90 available IPs
  autoAssign: true
  avoidBuggyIPs: false
```

**Pool Status:**
- **Total IPs:** 90 (10.0.10.10 - 10.0.10.99)
- **Assigned IPv4:** 1
- **Available IPv4:** 89
- **Subnet:** 10.0.10.0/24 (Kubernetes VLAN)

### Layer 2 Advertisement

```yaml
apiVersion: metallb.io/v1beta1
kind: L2Advertisement
metadata:
  name: first-pool
  namespace: metallb-system
spec:
  ipAddressPools:
  - first-pool
```

**How it Works:**
- Speaker pods use ARP to advertise IPs on the local network
- UniFi switch learns MAC addresses and routes traffic
- If a node fails, another speaker takes over the IP

---

## Allocated IP Addresses

| Service | Namespace | IP Address | Ports | Purpose |
|---------|-----------|------------|-------|---------|
| ingress-nginx-controller | ingress-nginx | 10.0.10.10 | 80, 443 | Main ingress controller |
| pi-hole (planned) | pihole | 10.0.0.200 | 53, 80, 443 | DNS/DHCP server |

---

## Operations

### Verify MetalLB Status

```bash
# Check MetalLB pods
kubectl get pods -n metallb-system

# Expected output:
# NAME                          READY   STATUS
# controller-xxxxxxxxxx-xxxxx   1/1     Running
# speaker-xxxxx                 1/1     Running  (x5 nodes)
```

### Check IP Pools

```bash
# List IP address pools
kubectl get ipaddresspool -n metallb-system

# View pool status
kubectl get ipaddresspool first-pool -n metallb-system -o yaml

# Check available IPs
kubectl get ipaddresspool first-pool -n metallb-system -o jsonpath='{.status}'
```

### List LoadBalancer Services

```bash
# All LoadBalancer services across cluster
kubectl get svc -A --field-selector spec.type=LoadBalancer

# Check specific service
kubectl describe svc ingress-nginx-controller -n ingress-nginx
```

### Check Layer 2 Advertisements

```bash
# List L2 advertisements
kubectl get l2advertisement -n metallb-system

# View advertisement details
kubectl describe l2advertisement first-pool -n metallb-system
```

---

## Creating LoadBalancer Services

### Example Service

```yaml
apiVersion: v1
kind: Service
metadata:
  name: my-app-loadbalancer
  namespace: my-app
spec:
  type: LoadBalancer
  ports:
  - port: 80
    targetPort: 8080
    protocol: TCP
    name: http
  selector:
    app: my-app
```

**Process:**
1. Service created with `type: LoadBalancer`
2. MetalLB controller assigns next available IP from pool
3. Speaker pods announce IP via ARP
4. Service accessible at assigned external IP

### Request Specific IP

```yaml
spec:
  type: LoadBalancer
  loadBalancerIP: 10.0.10.50  # Request specific IP
```

**Note:** IP must be within configured pool range.

---

## Troubleshooting

### Service Stuck in "Pending"

**Symptoms:**
```bash
kubectl get svc -n my-namespace
# EXTERNAL-IP shows <pending>
```

**Causes & Solutions:**

1. **No available IPs in pool:**
   ```bash
   kubectl get ipaddresspool first-pool -n metallb-system -o yaml
   # Check: status.availableIPv4
   ```
   **Solution:** Expand IP pool range or release unused IPs

2. **MetalLB controller not running:**
   ```bash
   kubectl get pods -n metallb-system
   ```
   **Solution:** Check controller logs, ensure ArgoCD sync is healthy

3. **Service in different namespace than pool:**
   - MetalLB pools are cluster-wide, this shouldn't be an issue
   - Check for namespace selectors in IPAddressPool if configured

### IP Not Reachable from Outside Cluster

**Symptoms:** LoadBalancer IP assigned but not pingable

**Causes & Solutions:**

1. **Speaker pods not running:**
   ```bash
   kubectl get pods -n metallb-system -l component=speaker
   # Should show 5/5 running (one per node)
   ```

2. **ARP not propagating:**
   ```bash
   # From a client on same network:
   arp -a | grep 10.0.10.10
   ```
   **Solution:** Check network switch configuration, VLAN settings

3. **Firewall blocking traffic:**
   - Verify no iptables rules blocking the IP
   - Check UniFi firewall rules for VLAN 10

### Multiple Services Getting Same IP

**Cause:** Services with `spec.loadBalancerIP` set to same IP

**Solution:** Remove `loadBalancerIP` and let MetalLB auto-assign

---

## Layer 2 Mode Limitations

### Known Constraints

1. **Single Node Handling Traffic:**
   - Only one node announces the IP at a time
   - All traffic flows through that node
   - Not true load balancing across nodes

2. **Failover Time:**
   - 10-15 seconds for IP to fail over to another node
   - Requires pod rescheduling and ARP cache updates

3. **Network Requirements:**
   - All nodes must be on same Layer 2 network
   - Switch must support ARP
   - Broadcast domain required

### When This Works Well

- **Homelab/bare-metal environments** ✅
- **Small to medium clusters** ✅
- **Services with multiple pods on single node** ✅

### When to Consider BGP Mode

- **Large clusters** with > 10 nodes
- **Multi-subnet** environments
- **True multi-path load balancing** requirements
- **Faster failover** requirements (sub-second)

---

## Monitoring

### Metrics

MetalLB exposes Prometheus metrics:

```promql
# IP allocation status
metallb_allocator_addresses_in_use_total
metallb_allocator_addresses_total

# Speaker announcements
metallb_speaker_announced
metallb_speaker_layer2_requests_received

# Controller assignments
metallb_k8s_client_update_errors_total
```

### Recommended Alerts

- **IP Pool Exhaustion:** Alert when available IPs < 10
- **Speaker Pod Down:** Alert if speaker count < 5
- **Controller Errors:** Alert on assignment errors

---

## Expanding IP Pool

To add more IPs to the pool:

1. **Edit IP Pool in homelab repo:**
   ```yaml
   # manifests/base/metal-lb/ipaddresspool.yaml
   spec:
     addresses:
     - 10.0.10.10-10.0.10.150  # Expand from .99 to .150
   ```

2. **Commit and create PR**

3. **ArgoCD syncs automatically** after merge

4. **Verify:**
   ```bash
   kubectl get ipaddresspool first-pool -n metallb-system -o yaml
   # Check: spec.addresses and status.availableIPv4
   ```

---

## Best Practices

1. **Reserve Static IPs:** Don't overlap with DHCP range
2. **Monitor IP Usage:** Set alerts before pool exhaustion
3. **Consistent Naming:** Use descriptive service names
4. **Avoid Manual IP Assignment:** Let MetalLB auto-assign when possible
5. **Plan for Growth:** Leave room in IP pool for future services

---

## Security Considerations

- **Network Isolation:** LoadBalancer IPs are on Kubernetes VLAN (10.0.10.0/24)
- **Firewall Rules:** Control access via UniFi firewall (VLAN-level)
- **Speaker Permissions:** Requires hostNetwork for ARP announcements
- **IP Spoofing:** Layer 2 mode has no authentication (inherent limitation)

---

## Upgrade Procedure

MetalLB is managed by ArgoCD using Helm:

1. **Update Chart Version:** Edit `manifests/applications/metal-lb.yaml`
2. **Check Release Notes:** Review breaking changes at https://metallb.universe.tf/release-notes/
3. **Create PR** and merge
4. **ArgoCD Syncs** automatically
5. **Verify:** Check pods and service IPs

**Note:** IP assignments persist across upgrades.

---

## Useful Commands

```bash
# MetalLB status
kubectl get pods -n metallb-system
kubectl get ipaddresspool -n metallb-system
kubectl get l2advertisement -n metallb-system

# Services using LoadBalancer
kubectl get svc -A --field-selector spec.type=LoadBalancer

# Controller logs
kubectl logs -n metallb-system deployment/controller -f

# Speaker logs (specific node)
kubectl logs -n metallb-system daemonset/speaker -f

# Pool status
kubectl get ipaddresspool first-pool -n metallb-system -o jsonpath='{.status}' | jq
```

---

## Resources

- **Official Documentation:** https://metallb.universe.tf/
- **Configuration:** https://metallb.universe.tf/configuration/
- **Concepts:** https://metallb.universe.tf/concepts/
- **Troubleshooting:** https://metallb.universe.tf/troubleshooting/

---

## Related Documentation

- [ingress-nginx](./ingress-nginx.md) - Primary consumer of MetalLB LoadBalancer
- [ArgoCD](./argocd.md) - GitOps deployment of MetalLB

**Note:** For comprehensive network configuration details, see `network-info.md` in the [homelab repository](https://github.com/imcbeth/homelab).

---

**Last Updated:** 2025-12-27
**Status:** Production, Healthy
**Managed By:** ArgoCD (`manifests/applications/metal-lb.yaml`)
