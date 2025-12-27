---
title: "External-DNS"
description: "Automatic DNS record management for Kubernetes with dual provider support"
---

# External-DNS

External-DNS automatically synchronizes Kubernetes Ingress and Service resources with DNS providers, eliminating manual DNS record management.

## Overview

- **Namespace:** `external-dns`
- **Image:** `registry.k8s.io/external-dns/external-dns:v0.15.0`
- **Deployment:** Managed by ArgoCD (dual deployments)
- **Sync Wave:** `-10` (deploys with cert-manager)

## Purpose

External-DNS provides automatic DNS management by:

- Creating DNS records for new Ingress resources
- Creating DNS records for LoadBalancer Services
- Updating DNS when resources change
- Removing DNS records when resources are deleted (with policy controls)
- Supporting split-horizon DNS (public + internal)

## Dual Provider Architecture

This deployment runs **two separate external-dns instances** for split-horizon DNS:

### 1. Cloudflare Provider (Public DNS)

**Purpose:** Manages public DNS records for external access

- **Target:** Cloudflare DNS for `k8s.n37.ca` zone
- **Authentication:** Reuses cert-manager Cloudflare API token
- **Deployment:** `external-dns-cloudflare`
- **ServiceAccount:** `external-dns-cloudflare`

**Configuration:**

```yaml
provider: cloudflare
domain-filter: k8s.n37.ca
cloudflare-proxied: false  # Direct to MetalLB IPs
```

### 2. UniFi Webhook Provider (Internal DNS)

**Purpose:** Manages internal DNS records for local network access

- **Target:** UniFi UDR7 controller at 10.0.1.1
- **Protocol:** UniFi API via webhook provider
- **Authentication:** UniFi API key
- **Webhook:** `lexfrei/external-dns-unifios-webhook` v0.2.0
- **Deployment:** `external-dns-unifi`
- **ServiceAccount:** `external-dns-unifi`

**Why Webhook Instead of RFC2136:**
UniFi OS does not support RFC2136 TSIG configuration, making dynamic DNS updates via RFC2136 impossible. The webhook provider uses the UniFi API directly to create and manage DNS records.

**Architecture:**

```
External-DNS → Webhook Provider → UniFi API → DNS Records
               (ghcr.io/lexfrei/external-dns-unifios-webhook)
```

**Configuration:**

```yaml
provider: webhook
webhook-provider-url: http://external-dns-unifi-webhook:8080
domain-filter: k8s.n37.ca
```

**Supported Record Types:**

- A (IPv4)
- AAAA (IPv6)
- CNAME (canonical name)
- TXT (ownership tracking)

**Requirements:**

- UniFi OS ≥ 4.3.9
- UniFi Network ≥ 9.4.19
- UniFi API key with DNS management permissions

## How It Works

### Watched Resources

External-DNS monitors these Kubernetes resources:

**1. Ingress Resources:**

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: my-app
spec:
  rules:
  - host: myapp.k8s.n37.ca  # Automatically creates DNS record
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: my-app
            port:
              number: 80
```

**2. LoadBalancer Services:**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: my-service
  annotations:
    external-dns.alpha.kubernetes.io/hostname: service.k8s.n37.ca
spec:
  type: LoadBalancer  # Gets MetalLB IP
  selector:
    app: my-app
  ports:
  - port: 80
```

### DNS Record Creation Flow

1. **Resource Created:** User creates Ingress or LoadBalancer Service
2. **Detection:** External-DNS watches API server and detects new resource
3. **Record Creation:**
   - **Cloudflare:** Creates `myapp.k8s.n37.ca` → MetalLB IP (public DNS)
   - **UniFi:** Creates `myapp.k8s.n37.ca` → MetalLB IP (internal DNS)
4. **Ownership Tracking:** TXT record created: `external-dns-myapp.k8s.n37.ca`
5. **Split-Horizon DNS:**
   - External clients → Cloudflare DNS → MetalLB IP
   - Internal clients → UniFi DNS → MetalLB IP (faster, no internet roundtrip)

## Configuration

### DNS Policy

**Mode:** `upsert-only` (safe mode)

- ✅ **Creates** new DNS records
- ✅ **Updates** existing DNS records
- ❌ **Does NOT delete** DNS records automatically

This prevents accidental deletion of manually-created records.

### Domain Filtering

**Domain:** `k8s.n37.ca`

Only resources with hostnames under `k8s.n37.ca` are processed:

- ✅ `app.k8s.n37.ca` - Managed
- ✅ `*.k8s.n37.ca` - Managed
- ❌ `example.com` - Ignored
- ❌ `other.domain.com` - Ignored

### TXT Registry

External-DNS creates TXT records to track ownership:

**Purpose:**

- Prevents conflicts with manually-created records
- Enables safe multi-provider setups
- Tracks which external-dns instance owns each record

**Format:**

- DNS A record: `app.k8s.n37.ca → 10.0.10.50`
- TXT record: `external-dns-app.k8s.n37.ca → "heritage=external-dns,external-dns/owner=external-dns-cloudflare"`

### Sync Interval

**Interval:** 1 minute

External-DNS checks for changes every 60 seconds:

- Polls Kubernetes API for resource changes
- Compares current state with DNS provider state
- Creates/updates records as needed

## Deployment Configuration

### RBAC Permissions

**ClusterRole:** `external-dns`

Permissions (read-only):

```yaml
- services, endpoints, pods (get, watch, list)
- ingresses (get, watch, list)
- nodes (get, watch, list)
```

**No write permissions** to Kubernetes resources - only reads and updates DNS.

### Resource Limits

**Per Deployment:**

```yaml
resources:
  requests:
    cpu: 50m
    memory: 64Mi
  limits:
    cpu: 100m
    memory: 128Mi
```

**Total:** ~100m CPU, ~128Mi memory for both deployments

Minimal resource usage appropriate for Raspberry Pi cluster.

### Security Context

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 65534
  readOnlyRootFilesystem: true
  capabilities:
    drop: [ALL]
```

Runs with minimal privileges and no root access.

## Secrets Management

### Cloudflare Secret

**Secret:** `cloudflare-api-token` (in `external-dns` namespace)

**Reuses cert-manager token:**

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: cloudflare-api-token
  namespace: external-dns
stringData:
  api-token: <same-token-as-cert-manager>
```

**Required Permissions:** DNS:Edit for `k8s.n37.ca` zone

### UniFi RFC2136 Secret

**Secret:** `rfc2136-credentials` (in `external-dns` namespace)

**TSIG Authentication:**

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: rfc2136-credentials
  namespace: external-dns
stringData:
  tsig-keyname: external-dns
  tsig-secret: <base64-encoded-key>
  tsig-algorithm: hmac-sha256
```

## UniFi Webhook Setup

### Prerequisites

- UniFi OS ≥ 4.3.9
- UniFi Network ≥ 9.4.19
- UniFi UDR7 (or compatible controller) at 10.0.1.1
- Access to UniFi Console

### Configuration Steps

**1. Generate UniFi API Key:**

Log into UniFi Console at `https://10.0.1.1`:

- Navigate to: **Settings → System → Advanced → API Access** (path may vary slightly by UniFi OS version)
- Click **Create API Key**
- **Name:** `external-dns-k8s`
- **Permissions:** Select the **Network** application with **Read/Write** access (required to create, update, and delete DNS records). Do not grant access to other applications unless explicitly needed.
- **Copy the API key** and securely store it immediately — it will only be displayed once and cannot be retrieved later. If you lose it, you must generate a new API key.

**2. Update Kubernetes Secret:**

Edit the UniFi credentials secret:

Edit the secret file (git-crypt encrypted) using your preferred editor:

```bash
# Example editors: vim, nano, code, or any text editor
$EDITOR manifests/base/external-dns/secret-unifi.yaml
```

Update the following values in the secret:

```yaml
# UNIFI_HOST: "https://10.0.1.1"
# UNIFI_API_KEY: "YOUR_ACTUAL_API_KEY_HERE"  # Long alphanumeric API key from UniFi Console (e.g., "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4")
# UNIFI_SITE_NAME: "default"  # Commonly "default", but verify in your UniFi Console URL:
#                              # if the URL contains /site/mysite, the site name is "mysite".
#                              # You can also confirm the site name via the UniFi API if needed.
# UNIFI_TLS_INSECURE: "false"  # Recommended: use a valid or trusted cert; only set to "true" temporarily in non-production if you must skip TLS verification
```

Apply the updated secret:

```bash
kubectl apply -f manifests/base/external-dns/secret-unifi.yaml
```

**3. Deploy via ArgoCD:**

ArgoCD will automatically sync the deployment. To manually sync:

```bash
# Sync external-dns application
argocd app sync external-dns

# Or use kubectl
kubectl apply -k manifests/base/external-dns/
```

**4. Verify Deployment:**

```bash
# Check webhook provider
kubectl get deployment -n external-dns external-dns-unifi-webhook

# Check external-dns deployment
kubectl get deployment -n external-dns external-dns-unifi

# View webhook logs
kubectl logs -n external-dns deployment/external-dns-unifi-webhook

# View external-dns logs
kubectl logs -n external-dns deployment/external-dns-unifi
```

### Webhook Architecture Details

The UniFi webhook provider consists of two components:

1. **Webhook Provider** (`external-dns-unifi-webhook`)
   - Runs `ghcr.io/lexfrei/external-dns-unifios-webhook`
   - Exposes HTTP API on port 8080
   - Health checks on port 8888
   - Prometheus metrics on `/metrics`

2. **External-DNS** (`external-dns-unifi`)
   - Connects to webhook via `http://external-dns-unifi-webhook:8080`
   - Watches Kubernetes Ingress and Service resources
   - Sends DNS record changes to webhook

For complete setup documentation, see the `manifests/base/external-dns/UNIFI-WEBHOOK-SETUP.md` document in your homelab Kubernetes manifests repository.

## Monitoring

### Check Deployment Status

```bash
# Check both deployments
kubectl get deployments -n external-dns

# Check pods
kubectl get pods -n external-dns
```

### View Logs

**Cloudflare Provider:**

```bash
kubectl logs -n external-dns deployment/external-dns-cloudflare -f
```

**UniFi Webhook Provider:**

```bash
# External-DNS logs
kubectl logs -n external-dns deployment/external-dns-unifi -f

# Webhook provider logs
kubectl logs -n external-dns deployment/external-dns-unifi-webhook -f
```

### Verify DNS Records

**Check managed resources:**

```bash
# List ingresses
kubectl get ingress -A

# List LoadBalancer services
kubectl get svc -A --field-selector spec.type=LoadBalancer
```

**Test DNS resolution:**

```bash
# External (Cloudflare)
dig myapp.k8s.n37.ca

# Internal (UniFi)
dig @10.0.1.1 myapp.k8s.n37.ca

# Check TXT ownership record
dig TXT external-dns-myapp.k8s.n37.ca
```

## Usage Examples

### Example 1: Ingress with Automatic DNS

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: grafana
  namespace: default
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  ingressClassName: nginx
  tls:
  - hosts:
    - grafana.k8s.n37.ca
    secretName: grafana-tls
  rules:
  - host: grafana.k8s.n37.ca
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: kube-prometheus-stack-grafana
            port:
              number: 80
```

**Result:**

- External-DNS creates DNS records (Cloudflare + UniFi)
- Cert-manager obtains Let's Encrypt certificate
- Grafana accessible at `https://grafana.k8s.n37.ca`

### Example 2: LoadBalancer with Custom Hostname

```yaml
apiVersion: v1
kind: Service
metadata:
  name: custom-service
  annotations:
    external-dns.alpha.kubernetes.io/hostname: custom.k8s.n37.ca
    external-dns.alpha.kubernetes.io/ttl: "300"
spec:
  type: LoadBalancer
  selector:
    app: custom-app
  ports:
  - port: 8080
    targetPort: 8080
```

**Result:**

- MetalLB assigns IP from pool
- External-DNS creates `custom.k8s.n37.ca` pointing to MetalLB IP
- Custom TTL of 300 seconds

### Example 3: Multiple Hostnames

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: multi-host-app
  annotations:
    external-dns.alpha.kubernetes.io/hostname: app.k8s.n37.ca,www.k8s.n37.ca
spec:
  rules:
  - host: app.k8s.n37.ca
    # ...
  - host: www.k8s.n37.ca
    # ...
```

**Result:**

- Both `app.k8s.n37.ca` and `www.k8s.n37.ca` DNS records created

## Troubleshooting

### Cloudflare Records Not Created

**Symptoms:**

- Ingress created but no Cloudflare DNS record
- external-dns-cloudflare logs show errors

**Diagnosis:**

```bash
kubectl logs -n external-dns deployment/external-dns-cloudflare
```

**Common Causes:**

1. **Invalid API token**

   ```bash
   kubectl get secret cloudflare-api-token -n external-dns -o yaml
   ```

2. **Insufficient API token permissions**
   - Verify token has DNS:Edit for `k8s.n37.ca`
3. **Domain filter mismatch**
   - Ensure hostname is under `k8s.n37.ca`

### UniFi Records Not Created

**Symptoms:**

- Cloudflare works but UniFi DNS not updated
- Webhook deployment logs show connection/authentication errors

**Diagnosis:**

```bash
# Check external-dns logs
kubectl logs -n external-dns deployment/external-dns-unifi

# Check webhook provider logs
kubectl logs -n external-dns deployment/external-dns-unifi-webhook
```

**Common Causes:**

1. **Invalid UniFi API key**
   - Verify API key has DNS management permissions
   - Check key hasn't expired or been revoked

   ```bash
   # Inspect the UniFi credentials secret created by secret-unifi.yaml
   kubectl get secret unifi-credentials -n external-dns -o yaml
   ```

2. **Webhook provider cannot reach UniFi controller**
   - Test connectivity from cluster:

   ```bash
   kubectl run -it --rm debug --image=curlimages/curl --restart=Never -- \
     curl -k https://10.0.1.1
   ```

3. **TLS certificate issues**
   - For self-signed certs, ensure `UNIFI_TLS_INSECURE: "true"`

4. **Incorrect site name**
   - Verify `UNIFI_SITE_NAME` matches your UniFi site (usually "default")

5. **Webhook service not reachable**
   - Ensure webhook service is running:

   ```bash
   kubectl get svc -n external-dns external-dns-unifi-webhook
   kubectl get endpoints -n external-dns external-dns-unifi-webhook
   ```

### DNS Records Not Updating

**Symptoms:**

- DNS record exists but points to old IP
- Changes not reflected after sync interval

**Solutions:**

1. **Force sync:**

   ```bash
   kubectl rollout restart deployment/external-dns-cloudflare -n external-dns
   kubectl rollout restart deployment/external-dns-rfc2136 -n external-dns
   ```

2. **Check TXT ownership:**

   ```bash
   dig TXT external-dns-myapp.k8s.n37.ca
   ```

   - If owned by different instance, may not update

3. **Verify resource hostname:**

   ```bash
   kubectl get ingress myapp -o yaml | grep host
   ```

### Split-Brain DNS Issues

**Symptoms:**

- External clients can't reach service
- Internal clients work fine (or vice versa)

**Diagnosis:**

```bash
# Test external DNS (Cloudflare)
dig @1.1.1.1 myapp.k8s.n37.ca

# Test internal DNS (UniFi)
dig @10.0.1.1 myapp.k8s.n37.ca
```

**Solutions:**

- Verify both providers are running
- Check logs for both deployments
- Ensure both point to same MetalLB IP

## Performance Considerations

### Sync Efficiency

**1-minute sync interval** balances:

- ✅ Timely DNS updates for new resources
- ✅ Low API call volume
- ✅ Minimal resource usage

**For faster updates:** Reduce interval to 30s (increases API calls)

### Resource Usage

**Typical Usage:**

- CPU: 20-30m per deployment
- Memory: 40-50Mi per deployment
- Network: Minimal (API polls + DNS updates)

**Scaling:**

- Single replica per deployment is sufficient
- External-DNS is not compute-intensive

## Security Best Practices

### API Token Security

**Cloudflare:**

- Use scoped API tokens (not Global API Key)
- Limit to DNS:Edit for specific zone
- Rotate tokens periodically
- Store in Kubernetes secrets (git-crypt encrypted in repo)

**UniFi Webhook:**

- Use dedicated API key with minimal permissions (DNS management only)
  - Note: Ensure only DNS-related permissions are enabled when creating the API key in the UniFi Console. Select the **Network** application with **Read/Write** access (required to create, update, and delete DNS records). Do not grant access to other applications unless explicitly needed.
- Store API key in encrypted Kubernetes secrets (git-crypt)
- Rotate API keys periodically
- Configure the UniFi controller with a trusted certificate/CA so TLS verification remains enabled (avoid `UNIFI_TLS_INSECURE: "true"`, especially in production)
- Monitor webhook logs for unauthorized access attempts

### Network Security

**Cloudflare:**

- HTTPS API calls to Cloudflare
- Token transmitted securely

**RFC2136:**

- DNS protocol to UniFi (10.0.1.1:53)
- TSIG authentication prevents spoofing
- Consider VPN/firewall rules for additional security

## Related Documentation

- [ArgoCD Application Management](./argocd.md)
- [Monitoring Overview](../monitoring/overview.md)
- [SNMP Exporter](./snmp-exporter.md)

## References

- [External-DNS Documentation](https://kubernetes-sigs.github.io/external-dns/)
- [Cloudflare Provider Guide](https://kubernetes-sigs.github.io/external-dns/v0.15.0/tutorials/cloudflare/)
- [Webhook Provider Guide](https://kubernetes-sigs.github.io/external-dns/latest/docs/tutorials/webhook-provider/)
- [UniFi Webhook Provider (lexfrei)](https://github.com/lexfrei/external-dns-unifios-webhook)
- [Alternative UniFi Webhook (kashalls)](https://github.com/kashalls/external-dns-unifi-webhook)
- [UniFi API (community-maintained, unofficial, may be outdated)](https://ubntwiki.com/products/software/unifi-controller/api)
- [Official Ubiquiti Developer Resources](https://developer.ui.com)
