---
title: "oauth2-proxy"
description: "GitHub SSO authentication proxy protecting cluster web UIs"
---

# oauth2-proxy

oauth2-proxy is a reverse proxy that enforces GitHub OAuth authentication before allowing access to cluster web UIs. It protects services that lack built-in authentication without modifying the services themselves.

## Overview

| Property | Value |
|----------|-------|
| **Namespace** | `oauth2-proxy` |
| **Chart** | `oauth2-proxy/oauth2-proxy` v10.4.3 |
| **App Version** | `v7.15.2` |
| **ArgoCD App** | `oauth2-proxy` (project: `infrastructure`, wave: `0`) |
| **Auth Endpoint** | `https://oauth.k8s.n37.ca` |
| **Provider** | GitHub OAuth App |
| **Mode** | Validate-only (`upstream: static://202`) |

## Purpose

oauth2-proxy acts as an authentication gate in front of cluster services. Rather than proxying traffic, it validates GitHub session cookies and returns `202 Accepted` for authorized users. nginx's `auth_request` directive handles the gate:

```
Browser → ingress-nginx → auth_request → oauth2-proxy (validates cookie)
              │                                  │
              │         ← 202 OK ────────────────┘
              │
              └──────────────────────────────────► Backend service
```

If the cookie is missing or invalid, oauth2-proxy returns `401` and nginx redirects the browser to `https://oauth.k8s.n37.ca/oauth2/start`, which initiates the GitHub OAuth flow.

## Protected Services

| Service | URL | Auth annotations |
|---------|-----|-----------------|
| Uptime Kuma | `https://status.k8s.n37.ca` | ✅ |
| Falco UI | `https://falco.k8s.n37.ca` | ✅ |
| Argo Workflows | `https://workflows.k8s.n37.ca` | ✅ |

**Not protected by oauth2-proxy:**

| Service | Reason |
|---------|--------|
| ArgoCD | Has native GitHub OIDC via Dex |
| Grafana | Has own authentication |
| Zot registry | docker CLI cannot handle OAuth redirects |
| LocalStack | AWS CLI/SDK cannot handle OAuth browser redirects |

## Architecture

```
Browser
   │
   ▼
ingress-nginx
   │
   ├── auth_request ──► oauth2-proxy (oauth2-proxy ns, port 4180)
   │                          │
   │         ┌── 202 OK ──────┘
   │         │
   │         └── 401 → redirect to https://oauth.k8s.n37.ca/oauth2/start
   │                                           │
   │                                    GitHub OAuth flow
   │                                           │
   │                                    Set cookie + redirect back
   │
   └──────────────────────────────────► Backend Service (direct, not proxied)
```

## Deployment Configuration

### ArgoCD Application

oauth2-proxy uses **directory mode** (no `kustomization.yaml`) so ArgoCD does not attempt to parse the SealedSecret through kustomize. The SealedSecret must be applied manually.

**Apply SealedSecret after first deploy or after secret rotation:**

```bash
kubectl apply -f manifests/base/oauth2-proxy/oauth2-proxy-cookie-sealed.yaml
```

### Key Helm Values

**Location:** `manifests/base/oauth2-proxy/values.yaml`

```yaml
config:
  clientID: "<github-oauth-client-id>"
  configFile: |-
    provider = "github"
    github_users = ["imcbeth"]
    upstreams = ["static://202"]
    cookie_domains = [".k8s.n37.ca"]
    whitelist_domains = [".k8s.n37.ca"]
    email_domains = ["*"]
    cookie_secure = true
    skip_provider_button = true

ingress:
  enabled: true
  hosts:
    - oauth.k8s.n37.ca

image:
  registry: quay.io
  repository: oauth2-proxy/oauth2-proxy  # No registry prefix — chart prepends quay.io automatically
```

:::warning Double registry prefix
The oauth2-proxy Helm chart prepends `image.registry` to `image.repository`. Setting `repository: quay.io/oauth2-proxy/oauth2-proxy` results in `quay.io/quay.io/oauth2-proxy/oauth2-proxy` (pull failure). Keep `repository: oauth2-proxy/oauth2-proxy` and let the chart handle the registry prefix.
:::

## Protecting a New Service

Add three annotations to the service's Ingress:

```yaml
nginx.ingress.kubernetes.io/auth-url: "http://oauth2-proxy.oauth2-proxy.svc.cluster.local:4180/oauth2/auth"
nginx.ingress.kubernetes.io/auth-signin: "https://oauth.k8s.n37.ca/oauth2/start?rd=$scheme://$host$uri"
nginx.ingress.kubernetes.io/auth-response-headers: "X-Auth-Request-User,X-Auth-Request-Email"
```

:::warning Use `$uri` not `$escaped_request_uri` in auth-signin
ingress-nginx v1.14.x validates nginx variables in the `auth-signin` annotation against a strict allowlist. `$escaped_request_uri` is **not** on that list — the annotation is silently rejected and nginx never generates a login redirect, resulting in a blank 401 on every unauthenticated request.

Use `$scheme://$host$uri` instead:

- `$uri` (path only, no query string) is on the allowlist
- Avoids a second issue with `$request_uri`: raw `&` characters in query strings would be parsed as extra `/oauth2/start` parameters, truncating the redirect URL
- Acceptable for SPA dashboards (argo-workflows, falco, uptime-kuma) where query params are not needed for the initial auth redirect
:::

:::tip Use ClusterIP for auth-url
`auth-url` uses the internal ClusterIP address (`oauth2-proxy.oauth2-proxy.svc.cluster.local`), not the external hostname. This avoids hairpin NAT issues where the ingress controller loops back through itself.
:::

## GitHub OAuth App

oauth2-proxy uses a dedicated GitHub OAuth App (`homelab-oauth`):

- **Authorization callback URL:** `https://oauth.k8s.n37.ca/oauth2/callback`
- **Scope:** `user:email`

:::warning One callback URL per OAuth App
GitHub OAuth Apps only support a single authorization callback URL. oauth2-proxy and ArgoCD Dex each need their own separate OAuth App — they cannot share one.
:::

## Access Control

Access is restricted to specific GitHub users via the `github_users` config option. The current configuration allows only `imcbeth`. To add additional users, update `values.yaml`.

## Secrets

| Secret | Namespace | Contents | How Managed |
|--------|-----------|----------|-------------|
| `oauth2-proxy-cookie-secret` | `oauth2-proxy` | Random cookie signing key | SealedSecret (apply manually) |
| `oauth2-proxy` | `oauth2-proxy` | Client secret from GitHub | Helm values (config.clientSecret) |

## Resource Usage

| Component | CPU Request | CPU Limit | Memory Request | Memory Limit |
|-----------|-------------|-----------|----------------|--------------|
| oauth2-proxy | 25m | 100m | 64Mi | 128Mi |

## Troubleshooting

### Blank 401 on every request (no redirect to GitHub login)

The most common cause is an invalid `auth-signin` annotation. ingress-nginx v1.14.x rejects `$escaped_request_uri` (not in the nginx variable allowlist) — when this happens, no `error_page 401` redirect is generated. Check the controller logs:

```bash
kubectl logs -n ingress-nginx deployment/ingress-nginx-controller | grep "auth-signin contains invalid"
```

If you see `annotation auth-signin contains invalid value`, fix the annotation to use `$uri`:

```yaml
nginx.ingress.kubernetes.io/auth-signin: "https://oauth.k8s.n37.ca/oauth2/start?rd=$scheme://$host$uri"
```

### Auth loop (redirecting indefinitely)

Check that the `auth-signin` URL includes scheme and host:

```bash
kubectl get ingress -n <namespace> -o yaml | grep auth-signin
# Should contain: $scheme://$host$uri
```

### 401 on every request (cookie not accepted)

Verify the cookie secret SealedSecret is applied and unsealed:

```bash
kubectl get secret oauth2-proxy-cookie-secret -n oauth2-proxy
```

If missing:

```bash
kubectl apply -f manifests/base/oauth2-proxy/oauth2-proxy-cookie-sealed.yaml
```

### oauth2-proxy pod CrashLoopBackOff

Check for image pull errors caused by double registry prefix:

```bash
kubectl describe pod -n oauth2-proxy -l app.kubernetes.io/name=oauth2-proxy | grep "image"
# Should show: quay.io/oauth2-proxy/oauth2-proxy:v7.15.2
# NOT: quay.io/quay.io/oauth2-proxy/...
```

### Service returns 403 instead of redirecting to GitHub

The `auth-url` must be reachable from within the ingress-nginx pod. Verify the oauth2-proxy service is up:

```bash
kubectl get svc -n oauth2-proxy
kubectl get endpoints -n oauth2-proxy
```

## References

- [oauth2-proxy Documentation](https://oauth2-proxy.github.io/oauth2-proxy/)
- [GitHub OAuth2 Provider](https://oauth2-proxy.github.io/oauth2-proxy/configuration/providers/github)
- [nginx auth_request module](https://nginx.org/en/docs/http/ngx_http_auth_request_module.html)

---

**Last Updated:** 2026-05-03
