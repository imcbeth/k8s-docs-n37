---
sidebar_position: 2
title: "cert-manager"
description: "Automated TLS certificate management with Let's Encrypt"
---

# cert-manager - TLS Certificate Management

## Overview

cert-manager is a Kubernetes controller that automates the management and issuance of TLS certificates from various sources, including Let's Encrypt. It ensures certificates are valid and up-to-date, automatically renewing them before expiry.

### Key Features

- **Automated Certificate Issuance:** Automatically requests and installs TLS certificates
- **Multiple Issuers:** Supports Let's Encrypt, private CA, and other ACME providers
- **DNS-01 Challenge:** Uses Cloudflare DNS for wildcard certificate support
- **Auto-Renewal:** Certificates automatically renewed 60 days before expiry
- **Kubernetes Native:** Managed via Custom Resource Definitions (CRDs)

---

## Deployment Details

### ArgoCD Application

- **Name:** cert-manager
- **Namespace:** cert-manager
- **Project:** infrastructure
- **Sync Wave:** -10
- **Helm Chart:** jetstack/cert-manager v1.16.3
- **Auto-Sync:** Enabled (prune, selfHeal)

### Resources

```yaml
# Controller resources
controller:
  requests:
    cpu: 10m
    memory: 32Mi
  limits:
    cpu: 100m
    memory: 128Mi

# Webhook resources
webhook:
  requests:
    cpu: 10m
    memory: 32Mi
  limits:
    cpu: 50m
    memory: 64Mi

# CA Injector resources
cainjector:
  requests:
    cpu: 10m
    memory: 32Mi
  limits:
    cpu: 100m
    memory: 128Mi
```

**Total Resource Usage:**

- CPU Requests: 30m (0.15% of 20 cores)
- Memory Requests: 96Mi (0.12% of 80GB)

---

## Configuration

### ClusterIssuers

Two ClusterIssuers are configured for Let's Encrypt:

#### 1. Production Issuer

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: lets-encrypt-k8s-n37-ca-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: imcbeth1980@gmail.com
    privateKeySecretRef:
      name: lets-encrypt-k8s-n37-ca-key-prod
    solvers:
    - dns01:
        cloudflare:
          email: imcbeth1980@gmail.com
          apiTokenSecretRef:
            name: cloudflare-api-token-secret
            key: api-token
```

**When to use:** Production ingresses with public-facing domains

#### 2. Staging Issuer

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: lets-encrypt-k8s-n37-ca-staging
spec:
  acme:
    server: https://acme-staging-v02.api.letsencrypt.org/directory
    email: imcbeth1980@gmail.com
    privateKeySecretRef:
      name: lets-encrypt-k8s-n37-ca-key-staging
    solvers:
    - dns01:
        cloudflare:
          email: imcbeth1980@gmail.com
          apiTokenSecretRef:
            name: cloudflare-api-token-secret
            key: api-token
```

**When to use:** Testing certificate issuance without rate limits

---

## DNS-01 Challenge with Cloudflare

### Why DNS-01?

- **Wildcard Certificates:** Supports `*.k8s.n37.ca` certificates
- **Internal Services:** Works for services not publicly accessible
- **Firewall Friendly:** No need to expose port 80 publicly
- **Shared Secret:** Reuses Cloudflare API token from cert-manager configuration

### Cloudflare API Token

The API token is stored in a Kubernetes secret:

```bash
# View secret (base64 encoded)
kubectl get secret cloudflare-api-token-secret -n cert-manager -o yaml
```

**Permissions Required:**

- Zone: DNS: Edit
- Zone: Zone: Read

**Token Scope:** k8s.n37.ca zone only

---

## Certificate Management

### Automatic Certificate Creation

Certificates are automatically created when an Ingress resource includes cert-manager annotations:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: example-ingress
  annotations:
    cert-manager.io/cluster-issuer: "lets-encrypt-k8s-n37-ca-prod"
spec:
  tls:
  - hosts:
    - example.k8s.n37.ca
    secretName: example-k8s-n37-ca-nginx-tls
  rules:
  - host: example.k8s.n37.ca
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: example-service
            port:
              number: 80
```

### Currently Managed Certificates

| Domain | Namespace | Secret Name | Status | Age |
|--------|-----------|-------------|--------|-----|
| argocd.k8s.n37.ca | argocd | argocd-k8s-n37-ca-nginx-tls | Ready | 4d6h |
| grafana.k8s.n37.ca | default | grafana-k8s-n37-ca-nginx-tls | Ready | 31h |
| localstack.k8s.n37.ca | localstack | localstack-k8s-n37-ca-nginx-tls | Ready | 4d5h |

### Certificate Lifecycle

1. **Ingress Created:** With cert-manager.io/cluster-issuer annotation
2. **Certificate Resource Created:** Automatically by cert-manager
3. **ACME Challenge:** DNS-01 challenge initiated with Cloudflare
4. **TXT Record Created:** `_acme-challenge.example.k8s.n37.ca`
5. **Verification:** Let's Encrypt verifies domain ownership
6. **Certificate Issued:** Stored as Kubernetes Secret
7. **Ingress Updated:** Uses the secret for TLS termination
8. **Auto-Renewal:** 60 days before expiry

### Certificate Renewal

- **Renewal Window:** 30 days before expiry
- **Process:** Fully automated, no intervention required
- **Monitoring:** Check certificate expiry in Grafana (future: Blackbox Exporter)

---

## Operations

### Verify cert-manager Status

```bash
# Check all cert-manager pods
kubectl get pods -n cert-manager

# Expected output:
# NAME                                       READY   STATUS
# cert-manager-xxxxxxxxxx-xxxxx              1/1     Running
# cert-manager-cainjector-xxxxxxxxxx-xxxxx   1/1     Running
# cert-manager-webhook-xxxxxxxxxx-xxxxx      1/1     Running
```

### Check ClusterIssuers

```bash
# List all ClusterIssuers
kubectl get clusterissuer

# Expected output:
# NAME                                READY   AGE
# lets-encrypt-k8s-n37-ca-prod        True    4d
# lets-encrypt-k8s-n37-ca-staging     True    4d

# Check issuer status
kubectl describe clusterissuer lets-encrypt-k8s-n37-ca-prod
```

### List All Certificates

```bash
# List certificates in all namespaces
kubectl get certificates -A

# Check specific certificate details
kubectl describe certificate grafana-k8s-n37-ca-nginx-tls -n default
```

### View Certificate Details

```bash
# Get certificate information
kubectl get certificate grafana-k8s-n37-ca-nginx-tls -n default -o yaml

# Check TLS secret
kubectl get secret grafana-k8s-n37-ca-nginx-tls -n default -o yaml

# Decode certificate
kubectl get secret grafana-k8s-n37-ca-nginx-tls -n default -o jsonpath='{.data.tls\.crt}' | base64 -d | openssl x509 -text -noout
```

### Manually Trigger Certificate Renewal

```bash
# Delete certificate to force renewal (it will be recreated)
kubectl delete certificate grafana-k8s-n37-ca-nginx-tls -n default

# Or annotate certificate to force renewal
kubectl annotate certificate grafana-k8s-n37-ca-nginx-tls -n default cert-manager.io/issue-temporary-certificate="true" --overwrite
```

---

## Troubleshooting

### Certificate Not Issuing

1. **Check Certificate Status:**

   ```bash
   kubectl describe certificate <cert-name> -n <namespace>
   ```

   Look for events describing the issue.

2. **Check CertificateRequest:**

   ```bash
   kubectl get certificaterequest -n <namespace>
   kubectl describe certificaterequest <request-name> -n <namespace>
   ```

3. **Check Challenge:**

   ```bash
   kubectl get challenge -n <namespace>
   kubectl describe challenge <challenge-name> -n <namespace>
   ```

4. **Check Order:**

   ```bash
   kubectl get order -n <namespace>
   kubectl describe order <order-name> -n <namespace>
   ```

### Common Issues

#### Issue: "Waiting for DNS propagation"

**Cause:** DNS TXT record not yet visible to Let's Encrypt servers

**Solution:**

- Wait 2-5 minutes for DNS propagation
- Check Cloudflare DNS records for `_acme-challenge` entries
- Verify Cloudflare API token has correct permissions

**Verify DNS:**

```bash
# Check DNS TXT record
dig _acme-challenge.grafana.k8s.n37.ca TXT +short
```

#### Issue: "Secret cloudflare-api-token-secret not found"

**Cause:** Cloudflare API token secret missing or in wrong namespace

**Solution:**

```bash
# Verify secret exists
kubectl get secret cloudflare-api-token-secret -n cert-manager

# If missing, apply from homelab repo
kubectl apply -f manifests/base/cert-manager/cloudflare-api-token-secret.yaml
```

#### Issue: "Rate limit exceeded"

**Cause:** Too many certificate requests to Let's Encrypt production

**Solution:**

- Use staging issuer for testing: `lets-encrypt-k8s-n37-ca-staging`
- Wait for rate limit reset (limits are per domain, per week)
- See: [Let's Encrypt Rate Limits](https://letsencrypt.org/docs/rate-limits/)

#### Issue: Certificate shows as "False" or "Unknown"

**Cause:** Various - check logs

**Solution:**

```bash
# Check cert-manager controller logs
kubectl logs -n cert-manager deployment/cert-manager -f

# Look for errors related to your certificate
kubectl logs -n cert-manager deployment/cert-manager | grep <cert-name>
```

---

## Monitoring

### Metrics

cert-manager exposes Prometheus metrics on port 9402:

```promql
# Certificate expiry time
certmanager_certificate_expiration_timestamp_seconds

# Certificate renewal success/failure
certmanager_certificate_renewal_count

# ACME client requests
certmanager_http_acme_client_request_count
```

### Alerts (Future)

Recommended alerts to configure:

- **Certificate Expiring Soon:** Alert if certificate expires in < 14 days
- **Certificate Renewal Failed:** Alert on renewal failures
- **ClusterIssuer Not Ready:** Alert if issuer status is not Ready

---

## Adding New Certificates

### For a New Ingress

Simply add the cert-manager annotation to your Ingress:

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

**Process:**

1. Apply Ingress manifest
2. cert-manager detects annotation
3. Creates Certificate resource automatically
4. Initiates ACME challenge
5. Certificate issued and stored in secret
6. Ingress uses secret for TLS

### For Testing (Use Staging)

Replace the issuer annotation:

```yaml
annotations:
  cert-manager.io/cluster-issuer: "lets-encrypt-k8s-n37-ca-staging"
```

---

## Integration with external-dns (Planned)

When external-dns is deployed, it will work alongside cert-manager:

- **external-dns:** Creates DNS A/CNAME records pointing to ingress
- **cert-manager:** Creates DNS TXT records for ACME challenges

Both use the same Cloudflare API token, no conflict.

---

## Best Practices

1. **Use Staging First:** Test new certificates with staging issuer
2. **Monitor Expiry:** Set up alerts for expiring certificates
3. **Secret Management:** Keep cloudflare-api-token-secret secure and backed up
4. **Rate Limits:** Be aware of Let's Encrypt rate limits
5. **Consistent Naming:** Use pattern: `<app>-k8s-n37-ca-nginx-tls` for secrets
6. **Namespace Isolation:** Certificates are namespace-scoped, plan accordingly

---

## Security Considerations

- **API Token Security:** Cloudflare token stored as Kubernetes secret (encrypted at rest)
- **Least Privilege:** Token has minimal required permissions (DNS edit only)
- **Token Rotation:** Consider rotating Cloudflare API token periodically
- **ACME Account:** Private key stored securely in cert-manager namespace
- **Certificate Secrets:** Contain private keys, protect namespace access

---

## Backup and Disaster Recovery

### Critical Resources to Backup

1. **ClusterIssuers:**

   ```bash
   kubectl get clusterissuer -o yaml > clusterissuers-backup.yaml
   ```

2. **Cloudflare API Token Secret:**

   ```bash
   kubectl get secret cloudflare-api-token-secret -n cert-manager -o yaml > cloudflare-secret-backup.yaml
   ```

3. **ACME Account Keys:**

   ```bash
   kubectl get secret lets-encrypt-k8s-n37-ca-key-prod -n cert-manager -o yaml > acme-key-prod-backup.yaml
   kubectl get secret lets-encrypt-k8s-n37-ca-key-staging -n cert-manager -o yaml > acme-key-staging-backup.yaml
   ```

### Recovery Process

1. Restore cert-manager via ArgoCD (from Git repository)
2. Restore secrets: `kubectl apply -f <backup-file>.yaml`
3. Verify ClusterIssuers are Ready: `kubectl get clusterissuer`
4. Certificates will automatically regenerate from Ingresses

---

## Upgrade Procedure

cert-manager is managed by ArgoCD using Helm. To upgrade:

1. **Update Chart Version:** Edit `manifests/applications/cert-manager.yaml` in homelab repo
2. **Check Release Notes:** Review breaking changes at [cert-manager Releases](https://cert-manager.io/docs/releases/)
3. **Create PR:** Follow GitOps workflow
4. **ArgoCD Sync:** Automatic after merge
5. **Verify:** Check pods and certificate renewal

**Note:** Always test in staging environment first if available.

---

## Useful Commands Reference

```bash
# cert-manager status
kubectl get pods -n cert-manager
kubectl get clusterissuer

# Certificates
kubectl get certificates -A
kubectl describe certificate <name> -n <namespace>

# Certificate chain (request → order → challenge)
kubectl get certificaterequest -n <namespace>
kubectl get order -n <namespace>
kubectl get challenge -n <namespace>

# Logs
kubectl logs -n cert-manager deployment/cert-manager -f

# Force certificate renewal
kubectl delete certificate <name> -n <namespace>

# Check certificate expiry
kubectl get secret <cert-secret> -n <namespace> -o jsonpath='{.data.tls\.crt}' | base64 -d | openssl x509 -enddate -noout
```

---

## Resources

- **Official Documentation:** [cert-manager.io](https://cert-manager.io/docs/)
- **Let's Encrypt:** [letsencrypt.org](https://letsencrypt.org/)
- **Cloudflare API Tokens:** [Cloudflare API Tokens Guide](https://developers.cloudflare.com/fundamentals/api/get-started/create-token/)
- **ACME Challenge Types:** [Let's Encrypt Challenge Types](https://letsencrypt.org/docs/challenge-types/)
- **Rate Limits:** [Let's Encrypt Rate Limits](https://letsencrypt.org/docs/rate-limits/)

---

## Related Documentation

- [nginx-ingress](./ingress-nginx.md) - Ingress controller using these certificates
- [ArgoCD](./argocd.md) - GitOps deployment of cert-manager
- [external-dns](./external-dns.md) - Complementary DNS automation (planned)

---

**Last Updated:** 2025-12-27
**Status:** Production, Healthy
**Managed By:** ArgoCD (`manifests/applications/cert-manager.yaml`)
