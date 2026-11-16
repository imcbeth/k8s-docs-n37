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
| **Chart** | `oauth2-proxy/oauth2-proxy` v10.7.1 (appVersion 7.15.5) |
| **App Version** | `v7.15.2` |
| **ArgoCD App** | `oauth2-proxy` (project: `infrastructure`, wave: `0`) |
| **Auth Endpoint** | `https://oauth.k8s.n37.ca` |
| **Provider** | GitHub OAuth App |
| **Mode** | Validate-only (`upstream: static://200`), called by the LAN gateway's Envoy ext_authz |

## Purpose

oauth2-proxy acts as an authentication gate in front of cluster services. Rather than proxying traffic, it validates GitHub session cookies and returns `200` for authorized users. Since 2026-11-15 the [LAN gateway](./lan-gateway.md) asks it through **Envoy ext_authz** (it was nginx's `auth_request` before):

```
Browser → lan-gateway (Envoy) → ext_authz check → oauth2-proxy (validates cookie)
               │                                       │
               │          ← 200 OK ────────────────────┘
               │
               └───────────────────────────────────────► Backend service
```

If the cookie is missing or invalid, oauth2-proxy answers the check itself with a `302` to GitHub (`skip-provider-button`), and Envoy returns that redirect to the browser. After sign-in, GitHub calls back to `https://oauth.k8s.n37.ca/oauth2/callback`, oauth2-proxy sets the `.k8s.n37.ca` cookie, and the browser goes back to the original URL.

:::warning Envoy ext_authz allows only 200
Any other status from the check, 202 included, is a denial that Envoy returns to the client. With the old `static://202` upstream, a signed-in user got an empty 202 page instead of the app. That's why the upstream is `static://200` (homelab #1183).
:::

## Protected Services

| Service | URL |
|---------|-----|
| Uptime Kuma | `https://status.k8s.n37.ca` |
| Falco UI | `https://falco.k8s.n37.ca` |
| Argo Workflows | `https://workflows.k8s.n37.ca` |
| Flink (kafka-to-s3) | `https://flink.k8s.n37.ca` |

The list is the `hosts` of the `CUSTOM` AuthorizationPolicy `istio-system/lan-gateway-oauth2` (`manifests/base/istio-gateway/authz.yaml`).

**Not protected by oauth2-proxy:**

| Service | Reason |
|---------|--------|
| ArgoCD | Has native GitHub OIDC via Dex |
| Grafana | Has own authentication |
| Zot registry | docker CLI cannot handle OAuth redirects; zot does htpasswd auth |
| LocalStack | AWS CLI/SDK cannot handle OAuth browser redirects |
| lifeonabike.ca | Public site |

## Architecture

The ext_authz provider is defined once in istiod's mesh config (`manifests/base/istio/istiod-values.yaml`):

```yaml
meshConfig:
  extensionProviders:
    - name: oauth2-proxy
      envoyExtAuthzHttp:
        service: oauth2-proxy.oauth2-proxy.svc.cluster.local
        port: 4180
        includeRequestHeadersInCheck: [authorization, cookie]
        includeAdditionalHeadersInCheck:
          x-auth-request-redirect: "https://%REQ(:authority)%%REQ(:path)%"
        headersToUpstreamOnAllow: [authorization, x-auth-request-user, x-auth-request-email]
        headersToDownstreamOnDeny: [content-type, set-cookie, location]
        headersToDownstreamOnAllow: [set-cookie]
```

- **`x-auth-request-redirect`**: an ext_authz check carries only the request path, so oauth2-proxy would otherwise send the user back to `oauth.k8s.n37.ca/<path>` after sign-in. This header gives it the full original URL, and oauth2-proxy still checks it against `whitelist-domain`.
- **`headersToDownstreamOnDeny`**: passes `location` and `set-cookie`, so the browser sees the 302 to GitHub.
- The service is the ClusterIP name, and the gateway reaches it over HBONE (mTLS) like any backend.

`oauth.k8s.n37.ca` itself (sign-in start and callback) is an ordinary route on the gateway, with no forward-auth.

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
image:
  repository: oauth2-proxy/oauth2-proxy  # No registry prefix — chart prepends quay.io automatically
config:
  existingSecret: oauth2-proxy-secret
extraArgs:
  provider: github
  github-user: imcbeth
  email-domain: "*"
  upstream: static://200          # ext_authz allows only 200
  redirect-url: https://oauth.k8s.n37.ca/oauth2/callback
  cookie-domain: .k8s.n37.ca
  whitelist-domain: .k8s.n37.ca
  cookie-secure: "true"
  cookie-name: _oauth2_proxy_k8s
  skip-provider-button: "true"
  set-xauthrequest: "true"
ingress:
  enabled: false                  # oauth.k8s.n37.ca is an HTTPRoute on the LAN gateway
```

:::warning Double registry prefix
The oauth2-proxy Helm chart prepends `image.registry` to `image.repository`. Setting `repository: quay.io/oauth2-proxy/oauth2-proxy` results in `quay.io/quay.io/oauth2-proxy/oauth2-proxy` (pull failure). Keep `repository: oauth2-proxy/oauth2-proxy` and let the chart handle the registry prefix.
:::

## Protecting a New Service

Add the host to the `hosts` list in `manifests/base/istio-gateway/authz.yaml`, in the same PR that adds its route to the gateway (see [Adding a host](./lan-gateway.md#adding-a-host)). Nothing changes on the backend.

A CUSTOM policy applies to every request it matches, which is why it is scoped by host: argocd and grafana have their own login, registry and localstack are used by non-browser clients, and oauth.k8s.n37.ca is oauth2-proxy itself.

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
| oauth2-proxy | 20m | 100m | 64Mi | 128Mi |

## Troubleshooting

### Signed-in user lands on `oauth.k8s.n37.ca/<path>`

The `x-auth-request-redirect` header is missing from the provider's `includeAdditionalHeadersInCheck` in istiod's mesh config, so oauth2-proxy only knows the path. Check:

```bash
kubectl get cm istio -n istio-system -o yaml | grep -A2 includeAdditionalHeadersInCheck
```

### Empty page with status 202 after sign-in

The upstream is `static://202`. Envoy treats any non-200 check result as a denial. Set `upstream: static://200`.

### No sign-in redirect at all (host loads without auth)

The host isn't in `authz.yaml`:

```bash
kubectl get authorizationpolicy -n istio-system lan-gateway-oauth2 -o jsonpath='{.spec.rules[0].to[0].operation.hosts}'
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
# Should show: quay.io/oauth2-proxy/oauth2-proxy:v7.15.5
# NOT: quay.io/quay.io/oauth2-proxy/...
```

### Service returns 403 instead of redirecting to GitHub

Envoy could not reach oauth2-proxy for the check (ext_authz fails closed with 403). Check that oauth2-proxy is up and the gateway's access log shows the `UAEX` response flag:

```bash
kubectl get pods,endpoints -n oauth2-proxy
kubectl logs -n istio-system deploy/lan-gateway-istio | grep UAEX | tail
```

## References

- [oauth2-proxy Documentation](https://oauth2-proxy.github.io/oauth2-proxy/)
- [GitHub OAuth2 Provider](https://oauth2-proxy.github.io/oauth2-proxy/configuration/providers/github)
- [Istio external authorization](https://istio.io/latest/docs/tasks/security/authorization/authz-custom/)

---

**Last Updated:** 2026-11-16
