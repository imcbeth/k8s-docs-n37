---
title: "ingress-nginx (retired)"
description: "Former NGINX ingress controller, replaced by the Istio LAN gateway on 2026-11-15"
---

# ingress-nginx (retired)

:::warning Removed 2026-11-15
ingress-nginx is no longer deployed. Every LAN hostname is served by the
[LAN Gateway (Istio)](./lan-gateway.md) on **10.0.10.11**. The old address
10.0.10.10 is free, and the cluster has no `Ingress` objects or `IngressClass` left.
:::

## Why it was replaced

Upstream retired ingress-nginx (v1.15.1 was the final release), so it would stop
getting security fixes. Istio's Gateway API implementation was chosen over Envoy
Gateway and Traefik because istiod was already running for the ambient mesh, so the
replacement added no new controller (`runbooks/ingress-nginx-replacement.md` in the
homelab repo).

## What it did, and where that lives now

| ingress-nginx | LAN gateway |
|---------------|-------------|
| LoadBalancer 10.0.10.10, 2 replicas + PDB | LoadBalancer 10.0.10.11, 2 replicas + PDB |
| `Ingress` per app, `ingressClassName: nginx` | `HTTPRoute` per host + one listener and `Certificate` per host |
| `cert-manager.io/cluster-issuer` annotation | `Certificate` objects in `istio-system` |
| `auth-url` / `auth-signin` annotations (oauth2-proxy) | Envoy ext_authz provider + `CUSTOM` AuthorizationPolicy by host |
| `force-ssl-redirect` | `http-redirect` HTTPRoute (301) |
| `addHeaders` + `hsts` (controller-wide) | `ResponseHeaderModifier` filter on every route rule |
| `ssl-protocols: TLSv1.2 TLSv1.3` | Envoy default |
| `limit-rps` / `limit-connections` | dropped (LAN-only hosts) |
| `backend-protocol: HTTPS` (argocd) | argocd-server in insecure mode, gRPC to its h2c port |
| `proxy-body-size: 0`, long timeouts (registry, status) | Envoy defaults (no body limit, route timeouts off) |
| ServiceMonitor :10254, `ingress-nginx-alerts`, "Ingress NGINX Overview" | PodMonitor :15020, `lan-gateway-alerts`, "LAN Gateway (Istio)" |

## Removal record

- Phase 2 (homelab #1213) removed the Helm values, the Application, the namespace
  NetworkPolicy, the alerts, the ResourceQuota and the `ingress-nginx` rule from 12
  namespaces' policies. The `ingress-nginx-config` Application and namespace were
  then deleted by hand.
- #1214 removed the default egress port 10254 that only nginx's metrics used.
- #1215 replaced the Grafana dashboard.

---

**Last Updated:** 2026-11-16
