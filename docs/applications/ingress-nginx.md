---
title: "ingress-nginx"
description: "NGINX Ingress Controller for HTTP/HTTPS traffic routing"
---

# ingress-nginx - HTTP/HTTPS Ingress Controller

## Overview

The NGINX Ingress Controller is a Kubernetes controller that manages external access to HTTP/HTTPS services in the cluster. It uses NGINX as a reverse proxy to route traffic based on hostnames and paths defined in Ingress resources.

### Key Features

- **HTTP/HTTPS Routing:** Route traffic based on host headers and URL paths
- **TLS Termination:** Decrypt HTTPS traffic using cert-manager certificates
- **Security Headers:** X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy
- **TLS Hardening:** TLSv1.2+ only, server-preferred ciphers, HSTS
- **Rate Limiting:** Global rate limiting via ConfigMap
- **Load Balancing:** Distribute traffic across multiple backend pods
- **Path-Based Routing:** Route different URLs to different services
- **WebSocket Support:** Proxy WebSocket connections
- **Custom Annotations:** Fine-tune behavior per-Ingress

---

## Deployment Details

### Installation

- **Namespace:** ingress-nginx
- **Type:** Deployment (single replica)
- **Helm Chart:** ingress-nginx v4.14.3
- **Controller Version:** v1.14.3
- **LoadBalancer IP:** 10.0.10.10 (via MetalLB)
- **Deployment Method:** ArgoCD with Helm chart (ServerSideApply)
- **Sync Wave:** -30 (after sealed-secrets, alongside cert-manager)

:::info Helm Migration (2026-02-14)
Migrated from manual `kubectl apply` to ArgoCD-managed Helm chart (PR #441). ServerSideApply adopted existing resources seamlessly without requiring Helm ownership labels. Security headers, resource limits, and ServiceMonitor are now all managed via Helm values.
:::

### Components

1. **Controller Pods:** Run NGINX and watch Ingress resources
2. **LoadBalancer Service:** Exposes controller on 10.0.10.10 (externalTrafficPolicy: Local)
3. **Admission Webhook:** Validates Ingress configurations
4. **ServiceMonitor:** Prometheus metrics scraping on port 10254

---

## Configuration

### LoadBalancer Service

```yaml
apiVersion: v1
kind: Service
metadata:
  name: ingress-nginx-controller
  namespace: ingress-nginx
spec:
  type: LoadBalancer
  loadBalancerIP: 10.0.10.10  # MetalLB assigned IP
  ports:
  - name: http
    port: 80
    targetPort: http
    protocol: TCP
  - name: https
    port: 443
    targetPort: https
    protocol: TCP
  selector:
    app.kubernetes.io/component: controller
```

**Access Points:**

- **HTTP:** [http://10.0.10.10](http://10.0.10.10) (redirects to HTTPS)
- **HTTPS:** [https://10.0.10.10](https://10.0.10.10) (requires valid host header)

### IngressClass

```yaml
apiVersion: networking.k8s.io/v1
kind: IngressClass
metadata:
  name: nginx
spec:
  controller: k8s.io/ingress-nginx
```

**Default IngressClass:** nginx

### ArgoCD Application

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: ingress-nginx-config
  namespace: argocd
spec:
  project: infrastructure
  sources:
    - repoURL: https://kubernetes.github.io/ingress-nginx
      chart: ingress-nginx
      targetRevision: 4.14.3
      helm:
        releaseName: ingress-nginx
        valueFiles:
          - $values/manifests/base/ingress-nginx/values.yaml
    - repoURL: git@github.com:imcbeth/homelab.git
      targetRevision: HEAD
      ref: values
  destination:
    server: https://kubernetes.default.svc
    namespace: ingress-nginx
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=false
      - ServerSideApply=true
```

### Security Hardening

All security settings are configured globally via Helm values (`controller.config` and `controller.addHeaders`):

**TLS Configuration:**

- TLSv1.2 and TLSv1.3 only (older protocols disabled)
- Server-preferred cipher suites
- HSTS with 1-year max-age and includeSubDomains
- Forced SSL redirect for all HTTP requests

**Security Headers (applied to all responses):**

| Header | Value | Purpose |
|--------|-------|---------|
| X-Frame-Options | DENY | Prevents clickjacking |
| X-Content-Type-Options | nosniff | Prevents MIME-type sniffing |
| Referrer-Policy | strict-origin-when-cross-origin | Controls referrer info |
| Permissions-Policy | camera=(), microphone=(), geolocation=(), payment=(), usb=(), bluetooth=(), serial=() | Disables browser APIs |

**Other Settings:**

- `server-tokens: "false"` - Hide NGINX version
- `hide-headers: "X-Powered-By"` - Remove backend info
- `client-max-body-size: "20m"` - Request body limit

### Resource Limits

```yaml
controller:
  resources:
    requests:
      cpu: 100m
      memory: 90Mi
    limits:
      cpu: 500m
      memory: 256Mi

  admissionWebhooks:
    createSecretJob:
      resources:
        requests:
          cpu: 10m
          memory: 32Mi
        limits:
          cpu: 50m
          memory: 64Mi
    patchWebhookJob:
      resources:
        requests:
          cpu: 10m
          memory: 32Mi
        limits:
          cpu: 50m
          memory: 64Mi
```

:::warning Webhook Job Resource Keys
The Helm chart has two separate job types for webhook certificate management: `createSecretJob` and `patchWebhookJob`. Both need resource limits for Gatekeeper compliance. The `patch.resources` key controls image/pod config, NOT the container resources.
:::

---

## Active Ingresses

| Host | Namespace | Service | Backend | TLS |
|------|-----------|---------|---------|-----|
| argocd.k8s.n37.ca | argocd | argocd-server | 443 | ✅ Let's Encrypt |
| grafana.k8s.n37.ca | default | kube-prometheus-stack-grafana | 80 | ✅ Let's Encrypt |
| localstack.k8s.n37.ca | localstack | localstack | 4566 | ✅ Let's Encrypt |

All ingresses use TLS certificates automatically issued by cert-manager.

---

## Creating an Ingress

### Basic HTTP Ingress

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: my-app-ingress
  namespace: my-app
spec:
  ingressClassName: nginx
  rules:
  - host: myapp.k8s.n37.ca
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: my-app-service
            port:
              number: 80
```

### HTTPS Ingress with cert-manager

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: my-app-ingress
  namespace: my-app
  annotations:
    cert-manager.io/cluster-issuer: "lets-encrypt-k8s-n37-ca-prod"
spec:
  ingressClassName: nginx
  tls:
  - hosts:
    - myapp.k8s.n37.ca
    secretName: myapp-k8s-n37-ca-nginx-tls
  rules:
  - host: myapp.k8s.n37.ca
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: my-app-service
            port:
              number: 80
```

**What Happens:**

1. Ingress created with cert-manager annotation
2. cert-manager requests TLS certificate from Let's Encrypt
3. Certificate stored in secret `myapp-k8s-n37-ca-nginx-tls`
4. ingress-nginx uses certificate for HTTPS termination
5. Traffic routed to backend service

---

## Common Annotations

### SSL/TLS Configuration

```yaml
metadata:
  annotations:
    # Force HTTPS redirect
    nginx.ingress.kubernetes.io/force-ssl-redirect: "true"

    # Custom SSL protocols
    nginx.ingress.kubernetes.io/ssl-protocols: "TLSv1.2 TLSv1.3"
```

### Proxy and Backend Settings

```yaml
metadata:
  annotations:
    # Increase timeout for long-running requests
    nginx.ingress.kubernetes.io/proxy-read-timeout: "600"

    # WebSocket support
    nginx.ingress.kubernetes.io/proxy-send-timeout: "600"
    nginx.ingress.kubernetes.io/websocket-services: "my-websocket-service"

    # Custom backend protocol
    nginx.ingress.kubernetes.io/backend-protocol: "HTTPS"
```

### Request Limits

```yaml
metadata:
  annotations:
    # Rate limiting
    nginx.ingress.kubernetes.io/limit-rps: "100"

    # Max body size
    nginx.ingress.kubernetes.io/proxy-body-size: "50m"
```

### Custom Headers

```yaml
metadata:
  annotations:
    # CORS headers
    nginx.ingress.kubernetes.io/enable-cors: "true"
    nginx.ingress.kubernetes.io/cors-allow-origin: "https://example.com"
```

---

## Operations

### Verify Controller Status

```bash
# Check controller pods
kubectl get pods -n ingress-nginx

# Expected output:
# NAME                                        READY   STATUS
# ingress-nginx-controller-xxxxxxxxxx-xxxxx   1/1     Running

# Check LoadBalancer service
kubectl get svc -n ingress-nginx
# Should show EXTERNAL-IP: 10.0.10.10
```

### List All Ingresses

```bash
# All ingresses in cluster
kubectl get ingress -A

# Specific namespace
kubectl get ingress -n my-app

# Detailed view
kubectl describe ingress my-app-ingress -n my-app
```

### Test Ingress Routing

```bash
# From outside cluster (DNS configured):
curl https://grafana.k8s.n37.ca

# From inside cluster or without DNS:
curl -H "Host: grafana.k8s.n37.ca" https://10.0.10.10

# Test specific path:
curl https://grafana.k8s.n37.ca/api/health
```

### View Controller Logs

```bash
# Stream logs
kubectl logs -n ingress-nginx deployment/ingress-nginx-controller -f

# Search for errors
kubectl logs -n ingress-nginx deployment/ingress-nginx-controller | grep error

# Filter by host
kubectl logs -n ingress-nginx deployment/ingress-nginx-controller | grep grafana
```

### Reload Configuration

```bash
# Force reload (usually not needed - automatic)
kubectl delete pod -n ingress-nginx -l app.kubernetes.io/component=controller
```

---

## Path Types

### Prefix (Most Common)

```yaml
pathType: Prefix
path: /app
```

Matches: `/app`, `/app/`, `/app/anything`

### Exact

```yaml
pathType: Exact
path: /app
```

Matches: `/app` only (not `/app/` or `/app/subpath`)

### ImplementationSpecific

```yaml
pathType: ImplementationSpecific
path: /app
```

Behavior depends on ingress controller (NGINX uses regex matching)

---

## Advanced Routing

### Multiple Paths per Host

```yaml
spec:
  rules:
  - host: example.k8s.n37.ca
    http:
      paths:
      - path: /api
        pathType: Prefix
        backend:
          service:
            name: api-service
            port:
              number: 8080
      - path: /web
        pathType: Prefix
        backend:
          service:
            name: web-service
            port:
              number: 80
```

### Default Backend (Catch-All)

```yaml
spec:
  defaultBackend:
    service:
      name: default-service
      port:
        number: 80
  rules:
  - host: example.k8s.n37.ca
    # ... specific rules
```

---

## Troubleshooting

### Ingress Shows No Address

**Symptoms:**

```bash
kubectl get ingress -n my-app
# ADDRESS field is empty
```

**Causes & Solutions:**

1. **Controller not running:**

   ```bash
   kubectl get pods -n ingress-nginx
   ```

2. **IngressClass mismatch:**

   ```yaml
   spec:
     ingressClassName: nginx  # Must match
   ```

3. **LoadBalancer service pending:**

   ```bash
   kubectl get svc -n ingress-nginx
   # Check if EXTERNAL-IP is assigned
   ```

### 404 Not Found

**Symptoms:** Ingress address shows but returns 404

**Causes & Solutions:**

1. **Service not found:**

   ```bash
   kubectl get svc my-app-service -n my-app
   ```

2. **Service port mismatch:**

   ```yaml
   backend:
     service:
       port:
         number: 80  # Must match Service port
   ```

3. **Path mismatch:**
   - Check `pathType` (Prefix vs Exact)
   - Verify path in request matches Ingress rule

4. **Host header missing:**

   ```bash
   curl -H "Host: myapp.k8s.n37.ca" https://10.0.10.10
   ```

### TLS Certificate Issues

**Symptoms:** Certificate warnings, "NET::ERR_CERT_AUTHORITY_INVALID"

**Causes & Solutions:**

1. **Certificate not ready:**

   ```bash
   kubectl get certificate -n my-app
   kubectl describe certificate myapp-k8s-n37-ca-nginx-tls -n my-app
   ```

2. **Wrong issuer (staging vs production):**
   - Check: `cert-manager.io/cluster-issuer` annotation
   - Staging certs are not trusted by browsers

3. **Secret not found:**

   ```bash
   kubectl get secret myapp-k8s-n37-ca-nginx-tls -n my-app
   ```

### Backend Service Unreachable

**Symptoms:** 502 Bad Gateway or 503 Service Unavailable

**Causes & Solutions:**

1. **No healthy pods:**

   ```bash
   kubectl get endpoints my-app-service -n my-app
   # Should show pod IPs
   ```

2. **Pod not ready:**

   ```bash
   kubectl get pods -n my-app
   # Check READY column
   ```

3. **Service selector mismatch:**

   ```bash
   kubectl describe svc my-app-service -n my-app
   # Check Selector and Endpoints
   ```

---

## Monitoring

### ServiceMonitor

A Prometheus ServiceMonitor is deployed via the Helm chart to scrape controller metrics on port 10254:

```yaml
controller:
  metrics:
    enabled: true
    serviceMonitor:
      enabled: true
      additionalLabels:
        release: kube-prometheus-stack
```

The `release: kube-prometheus-stack` label ensures Prometheus discovers the ServiceMonitor.

### Metrics

ingress-nginx exposes Prometheus metrics:

```promql
# Request rate by ingress
rate(nginx_ingress_controller_requests[5m])

# Request duration (latency)
histogram_quantile(0.95, rate(nginx_ingress_controller_request_duration_seconds_bucket[5m]))

# Error rate (4xx, 5xx)
rate(nginx_ingress_controller_requests{status=~"5.*"}[5m])

# Bytes in/out
rate(nginx_ingress_controller_bytes_sent_total[5m])

# SSL certificate expiry
nginx_ingress_controller_ssl_certificate_expiry_seconds
```

### Grafana Dashboards

Recommended community dashboards:

- **Dashboard ID 9614:** NGINX Ingress Controller
- **Dashboard ID 11875:** Kubernetes Ingress

---

## Security Best Practices

1. **Always Use TLS:** Force HTTPS redirect

   ```yaml
   annotations:
     nginx.ingress.kubernetes.io/force-ssl-redirect: "true"
   ```

2. **Rate Limiting:** Protect against DDoS

   ```yaml
   annotations:
     nginx.ingress.kubernetes.io/limit-rps: "100"
   ```

3. **IP Whitelisting:** Restrict access by IP

   ```yaml
   annotations:
     nginx.ingress.kubernetes.io/whitelist-source-range: "10.0.0.0/8,192.168.0.0/16"
   ```

4. **Modern TLS Only:**

   ```yaml
   annotations:
     nginx.ingress.kubernetes.io/ssl-protocols: "TLSv1.2 TLSv1.3"
   ```

5. **Request Size Limits:**

   ```yaml
   annotations:
     nginx.ingress.kubernetes.io/proxy-body-size: "10m"
   ```

---

## Useful Commands

```bash
# Ingress status
kubectl get ingress -A
kubectl describe ingress <name> -n <namespace>

# Controller logs
kubectl logs -n ingress-nginx deployment/ingress-nginx-controller -f

# Validate configuration
kubectl exec -n ingress-nginx deployment/ingress-nginx-controller -- nginx -T

# Reload controller
kubectl delete pod -n ingress-nginx -l app.kubernetes.io/component=controller

# Check endpoints
kubectl get endpoints <service-name> -n <namespace>

# Test routing
curl -H "Host: example.k8s.n37.ca" https://10.0.10.10
```

---

## Resources

- **Official Documentation:** [ingress-nginx Documentation](https://kubernetes.github.io/ingress-nginx/)
- **Annotations Reference:** [Annotations Guide](https://kubernetes.github.io/ingress-nginx/user-guide/nginx-configuration/annotations/)
- **Examples:** [ingress-nginx Examples](https://kubernetes.github.io/ingress-nginx/examples/)
- **Troubleshooting:** [Troubleshooting Guide](https://kubernetes.github.io/ingress-nginx/troubleshooting/)

---

## Related Documentation

- [cert-manager](./cert-manager.md) - TLS certificate automation
- [metallb](./metallb.md) - LoadBalancer IP provider
- [external-dns](./external-dns.md) - DNS automation (planned)

**Note:** For comprehensive network configuration details, see `network-info.md` in the [homelab repository](https://github.com/imcbeth/homelab).

---

### NetworkPolicy

ingress-nginx namespace has a NetworkPolicy restricting traffic:

**Allowed Ingress:**

- External traffic on ports 80, 443 (LoadBalancer)
- Prometheus metrics scraping on port 10254 from default namespace
- HBONE port 15008 (Istio Ambient mesh)

**Allowed Egress:**

- DNS (kube-system:53)
- Kubernetes API (ClusterIP + control plane)
- Backend services in all namespaces on ports 80, 443, 8080, 8443
- cert-manager webhook (port 10250)
- Istio control plane (ports 15008, 15012, 15017)

---

**Last Updated:** 2026-02-14
**Status:** Production, Healthy
**Managed By:** ArgoCD (`manifests/applications/ingress-nginx-config.yaml`)
**LoadBalancer IP:** 10.0.10.10
