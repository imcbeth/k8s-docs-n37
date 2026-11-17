---
title: "LAN Gateway (Istio)"
description: "Istio Gateway API gateway that serves every LAN hostname, replacing ingress-nginx"
---

# LAN Gateway (Istio Gateway API)

## Overview

`lan-gateway` is the cluster's only L7 entry point from the LAN. It is a Kubernetes
Gateway API `Gateway` with class `istio`: istiod (already running for the ambient mesh)
generates an Envoy Deployment and a LoadBalancer Service for it, so it added no new
controller to the cluster.

It replaced [ingress-nginx](./ingress-nginx.md), which upstream retired (v1.15.1 was the
final release). The migration ran on 2026-11-15:

| Phase | What | Result |
|-------|------|--------|
| 0 | Prototype on falco.k8s.n37.ca: forward-auth through Envoy ext_authz | 302 to GitHub with the right return URL |
| 1 | Move hosts one at a time, each with its own listener and certificate | All 11 hostnames moved |
| 2 | Remove ingress-nginx, its NetworkPolicy rules, alerts and dashboard | 10.0.10.10 freed |

| Item | Value |
|------|-------|
| Gateway | `istio-system/lan-gateway` |
| Generated Deployment / Service | `lan-gateway-istio` (Envoy, `registry.istio.io` proxy image) |
| LoadBalancer IP | **10.0.10.11** (MetalLB, `metallb.io/loadBalancerIPs` annotation) |
| ArgoCD Application | `istio-gateway`, sync wave -4 (after istiod and falco) |
| Manifests | `manifests/base/istio-gateway/` (plain YAML, no kustomization) |
| Replicas | 2, on different nodes, PDB `minAvailable: 1` |

:::info Why istio-system
The proxy image comes from `registry.istio.io`, which the Gatekeeper allowed-repos
constraint rejects everywhere except the namespaces excluded from it. The gateway lives
in `istio-system` for that reason.
:::

---

## Hosts

Each host has its own HTTPS listener, certificate and `HTTPRoute`, so one host can move
or change alone. Listeners admit routes only from the backend's namespace.

| Host | Namespace | Backend | Forward-auth | Notes |
|------|-----------|---------|--------------|-------|
| argocd.k8s.n37.ca | argocd | argocd-server :80 / :8080 | — (Argo CD SSO) | gRPC to the h2c port, see below |
| grafana.k8s.n37.ca | default | kube-prometheus-stack-grafana :80 | — (Grafana login) | |
| workflows.k8s.n37.ca | argo-workflows | argo-workflows-server :2746 | ✅ | |
| falco.k8s.n37.ca | falco | falco-falcosidekick-ui :2802 | ✅ | |
| status.k8s.n37.ca | uptime-kuma | uptime-kuma :3001 | ✅ | WebSockets |
| flink.k8s.n37.ca | flink-demo | kafka-to-s3-rest :8081 | ✅ | |
| localstack.k8s.n37.ca | localstack | localstack :4566 | — (API endpoint) | |
| registry.k8s.n37.ca | zot | zot :5000 | — (zot htpasswd) | large pushes |
| oauth.k8s.n37.ca | oauth2-proxy | oauth2-proxy :4180 | — (is the auth) | |
| lifeonabike.ca, www | lifeonabike | web :80 | — (public site) | LAN path only |

`lifeonabike.ca` from the internet goes through the Cloudflare tunnel straight to the
`web` Service. Only LAN clients, whose DNS answers with the gateway address, use this path.

Plain HTTP on port 80 is answered for every host by one `HTTPRoute`
(`http-redirect`) with a 301 to HTTPS. ingress-nginx did this by default; without it,
`http://<host>` was connection refused.

### Argo CD and gRPC

argocd-server runs with `server.insecure: true` (since 2026-11-15), so the gateway talks
plain HTTP to it, with no TLS origination and no DestinationRule.

:::warning This hop is not encrypted
The `argocd` namespace is not in the ambient mesh, so gateway → argocd-server is
plaintext HTTP on the pod network. Under ingress-nginx it was HTTPS
(`backend-protocol: HTTPS`). Open in the homelab TODO; the fix is either to mesh the
`argocd` namespace or to go back to TLS to the backend.
:::
The `argocd` CLI's native gRPC needs HTTP/2 to the backend, so the route sends
`content-type: application/grpc*` to the chart's h2c port `http2` (8080). The UI, REST
API and grpc-web go to port 80. Both CLI modes work.

### Timeouts and body size

Istio route timeouts are off by default and Envoy does not limit streamed request
bodies. That covers what nginx needed annotations for: registry's
`proxy-body-size: 0` and 600 s timeouts, and Uptime Kuma's 3600 s WebSocket timeouts.
WebSocket upgrades work without configuration.

---

## TLS

Certificates are `Certificate` objects in `istio-system` (`certificates.yaml`), one per
host, issued by the `lets-encrypt-k8s-n37-ca-prod` ClusterIssuer (DNS-01 through
Cloudflare). Secrets are named `<host>-gw-tls`. The listener terminates TLS; Let's
Encrypt never needs to reach the gateway.

---

## Hardening

Carried over from ingress-nginx's controller-wide config:

| Setting | How |
|---------|-----|
| TLS 1.2+ only | Envoy's default for listeners; TLS 1.0/1.1 handshakes fail |
| `Strict-Transport-Security: max-age=31536000; includeSubDomains` | `ResponseHeaderModifier` on every route rule |
| `X-Frame-Options: DENY` | same |
| `X-Content-Type-Options: nosniff` | same |
| `Referrer-Policy: strict-origin-when-cross-origin` | same |
| `Permissions-Policy: camera=(), microphone=(), …` | same |
| `X-Powered-By` removed | same (`remove`) |
| No server version | Envoy sends `server: istio-envoy` |

Gateway API has no gateway-wide header setting, so **a new route must copy the
filter** from an existing `*-route.yaml`. The filter uses `set`, not `add`, so a
backend's own value is replaced instead of sent twice.

Per-host rate limits (50–100 RPS on nginx) were **dropped on purpose**: Istio can only
do them with an EnvoyFilter, and every rate-limited host is LAN-only (`*.k8s.n37.ca` has
no public DNS). Revisit if a host is ever exposed publicly.

---

## Forward-auth (oauth2-proxy)

Hosts that used nginx's `auth-url`/`auth-signin` annotations now use Envoy ext_authz:

1. istiod's `meshConfig.extensionProviders` defines an `envoyExtAuthzHttp` provider
   named `oauth2-proxy` (`oauth2-proxy.oauth2-proxy.svc.cluster.local:4180`).
2. A `CUSTOM` AuthorizationPolicy, `istio-system/lan-gateway-oauth2` (`authz.yaml`),
   targets the Gateway and lists the protected **hosts**. A host not in the list gets no
   forward-auth, so add a host there in the same PR that adds its route.

The provider sends `cookie` and `authorization` to oauth2-proxy, plus an
`x-auth-request-redirect: https://<host><path>` header so the user returns to the
protected host after sign-in. An ext_authz check carries only the path, so without this
header the user landed on `oauth.k8s.n37.ca/<path>`. On allow it passes
`x-auth-request-user`/`-email` upstream. On deny it passes `location` and `set-cookie`
back, so the browser gets the 302 to GitHub. See [oauth2-proxy](./oauth2-proxy.md).

---

## NetworkPolicy and the mesh

- `istio-system/lan-gateway-ingress` admits 443 and 80 from anywhere to the gateway pods
  only. It is additive to the namespace's own policy.
- The gateway pod itself is not captured by ztunnel (`dataplane-mode: none`), but Envoy
  speaks HBONE natively: to **ambient** backends (default, argo-workflows, flink-demo,
  localstack) it opens HBONE mTLS on 15008 with its own identity, and those namespaces'
  L4 `AuthorizationPolicy` allows the principal
  `cluster.local/ns/istio-system/sa/lan-gateway-istio` on the app port.
- To **non-ambient** backends (argocd, falco, uptime-kuma, zot, oauth2-proxy,
  lifeonabike) it connects directly to the pod port, in plain HTTP, and their
  NetworkPolicy admits `istio-system` on that port.
  See [Network Policies](../security/network-policies.md).

---

## Monitoring

**Scrape:** PodMonitor `lan-gateway` (`podmonitor.yaml`), port `metrics` (15020,
`/stats/prometheus`), every 30 s. Gateway traffic is
`istio_requests_total{source_workload="lan-gateway-istio", reporter="source"}`.

**Dashboard:** "LAN Gateway (Istio)", uid `lan-gateway-overview`, folder *network*.
Rows: overview stats (up, requests/s, 5xx %, p95, sign-in redirects, uptime),
traffic by backend and status class, latency percentiles and per-backend p95, errors
and auth (5xx by backend, Envoy response flags, sign-in redirects by backend), and
listener certificate expiry plus gateway memory. The `$backend` variable filters it.

**Alerts:** PrometheusRule `lan-gateway-alerts`:

| Alert | Condition | Severity |
|-------|-----------|----------|
| LanGatewayDown | gateway not scrapeable for 5m | critical |
| LanGatewayConfigRejected | Envoy rejected an LDS/CDS update from istiod | critical |
| LanGatewayHighServerErrorRate | 5xx > 5% and ≥ 5 errors, 5m | warning |
| LanGatewayBackendHighErrorRate | per-backend 5xx > 10% and ≥ 3 errors, 5m | warning |
| LanGatewayHighClientErrorRate | 4xx > 30% and ≥ 20 errors, 10m | warning |
| LanGatewayHighLatencyP95 | p95 > 5 s and ≥ 10 requests, 10m | warning |
| LanGatewayBackendHighLatencyP95 | per-backend p95 > 10 s and ≥ 5 requests, 10m | warning |

Traffic is low (often under 0.1 req/s), so each rate alert also needs a minimum count;
otherwise a single 503 at night is a 100% error rate. The latency alerts exclude
response codes `101` (WebSockets, which stay open for hours) and `0` (aborted streams).
Sign-in redirects show the response flag `UAEX` and are 302s, not errors.

**Blackbox probes** of grafana and argocd resolve those hosts to the gateway's
ClusterIP through `hostAliases` on the blackbox-exporter Deployment, which avoids
pod-to-VIP hairpin NAT. The ClusterIP changes only if the Gateway is recreated:

```bash
kubectl get svc -n istio-system lan-gateway-istio -o jsonpath='{.spec.clusterIP}'
```

---

## Operations

```bash
# Gateway status: PROGRAMMED True, ADDRESS 10.0.10.11
kubectl get gateway -n istio-system lan-gateway

# Routes and the listener each one attached to
kubectl get httproute -A
kubectl describe httproute -n <ns> <name>   # Accepted / ResolvedRefs conditions

# Gateway pods and PDB
kubectl get pods,pdb -n istio-system -l gateway.networking.k8s.io/gateway-name=lan-gateway

# Access logs (one line per request)
kubectl logs -n istio-system deploy/lan-gateway-istio -f

# Envoy's view of routes and clusters
istioctl proxy-config routes deploy/lan-gateway-istio -n istio-system
istioctl proxy-config clusters deploy/lan-gateway-istio -n istio-system

# Test a host before its DNS record exists
curl --resolve <host>:443:10.0.10.11 https://<host>/
```

### Adding a host

1. A listener in `gateway.yaml`: `https-<name>`, the hostname, `tls.certificateRefs`
   to `<host>-gw-tls`, `allowedRoutes` selecting the backend namespace.
2. A `Certificate` in `certificates.yaml`.
3. `<name>-route.yaml`: `parentRefs` with `sectionName: https-<name>`, the hostname,
   the **security-header filter**, and the backend.
4. Forward-auth: add the host to `authz.yaml`.
5. The backend namespace's NetworkPolicy: `istio-system` on 15008 if it is ambient
   (plus `sa/lan-gateway-istio` in its AuthorizationPolicy), otherwise on the pod port.
6. DNS: `external-dns-unifi` watches `gateway-httproute`, so the LAN record follows
   the route.

---

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| `connection refused` on 443 for one host | Listener missing, or its certificate secret not issued yet (`kubectl get certificate -n istio-system`) |
| 404 from `istio-envoy` | No route attached: check the `HTTPRoute` `Accepted` condition and `sectionName` |
| 503 with flag `UF`/`URX` | Backend unreachable: AuthorizationPolicy or NetworkPolicy, or no ready endpoints |
| Sign-in loop / lands on `oauth.k8s.n37.ca/<path>` | Host missing from `authz.yaml`, or the `x-auth-request-redirect` provider header was removed |
| `LanGatewayConfigRejected` | A route or filter Envoy cannot load; `istioctl proxy-status` shows which xDS type is stale |

---

## Related Documentation

- [Istio](./istio.md) — the mesh and istiod
- [MetalLB](./metallb.md) — LoadBalancer address
- [cert-manager](./cert-manager.md) — certificates
- [oauth2-proxy](./oauth2-proxy.md) — forward-auth
- [ingress-nginx](./ingress-nginx.md) — the controller this replaced (retired)

---

**Last Updated:** 2026-11-16
**Managed By:** ArgoCD (`manifests/applications/istio-gateway.yaml`)
