---
title: "Zot OCI Registry"
description: "CNCF OCI-compliant container registry with pull-through caching and CVE scanning"
---

# Zot OCI Registry

Zot is a CNCF incubating, OCI-native container registry. It serves as the cluster's private image registry and pull-through cache for all major upstream registries.

## Overview

| Property | Value |
|----------|-------|
| **Namespace** | `zot` |
| **Chart** | `zot/zot` v0.1.106 |
| **Image** | `ghcr.io/project-zot/zot:v2.1.16` (linux/arm64/v8) |
| **ArgoCD App** | `zot` (project: `infrastructure`, wave: `-2`) |
| **UI / API URL** | `https://registry.k8s.n37.ca` |
| **Storage** | 50Gi iSCSI PVC (`synology-iscsi-delete`) |
| **Auth** | htpasswd via SealedSecret (`zot-htpasswd`) — anonymous reads enabled (PR #595) |

## Purpose

Zot provides two primary capabilities:

1. **Pull-through cache** — On first `docker pull`, Zot fetches the image from the upstream registry (Docker Hub, GHCR, quay.io, registry.k8s.io) and caches it locally. Subsequent pulls are served directly from Zot, reducing external bandwidth and improving reliability.

2. **Private registry** — Store and serve your own images (`docker push registry.k8s.n37.ca/myapp:v1.0`).

Additional features enabled in this cluster:

- **CVE scanning** — Built-in Trivy integration, DB updated every 2 hours
- **Web UI** — Browse repositories and vulnerability reports at `https://registry.k8s.n37.ca`
- **Prometheus metrics** — Scraped via ServiceMonitor at `/metrics`
- **Storage scrub** — Integrity check runs every 24 hours

:::warning No platform filtering in v2.1.16
Zot v2.1.16 does **not** support platform/architecture filtering in the sync `Content` struct. The `platforms` key does not exist in this version — using it causes Zot to exit at startup with `"invalid keys: platforms"` → CrashLoopBackOff.

All multi-arch variants of an image are downloaded on first pull (~41 seconds for `nginx:latest` = 12+ platforms). This is a known limitation. Accept the first-pull latency or increase upstream proxy timeouts. Platform filtering is expected to be added in a future Zot release.
:::

## Upstream Registries (Pull-Through)

| Upstream | Pull prefix |
|----------|-------------|
| Docker Hub | `registry.k8s.n37.ca/library/<image>` |
| GitHub Container Registry | `registry.k8s.n37.ca/<owner>/<image>` |
| Quay.io | `registry.k8s.n37.ca/<owner>/<image>` |
| registry.k8s.io | `registry.k8s.n37.ca/<path>` |

Pull-through is **on-demand** — Zot only fetches an image when a client requests it for the first time.

## Quick Start

### Login

Login is only required for **push** operations. Anonymous pulls are enabled cluster-wide (no credentials needed for image pulls).

```bash
# Only needed to push images:
docker login registry.k8s.n37.ca
# Username: admin
# Password: (from zot-htpasswd SealedSecret)
```

### Pull an Image via Pull-Through Cache

```bash
# Docker Hub image (nginx)
docker pull registry.k8s.n37.ca/library/nginx:latest

# GHCR image
docker pull registry.k8s.n37.ca/project-zot/zot:v2.1.16

# Kubernetes registry
docker pull registry.k8s.n37.ca/pause:3.10
```

:::tip First Pull
The first pull of any image triggers an on-demand sync from the upstream registry. Since platform filtering is not available in v2.1.16, all platform variants are downloaded (~41 seconds for multi-arch images like `nginx:latest`). Every subsequent pull is instant from the local cache.
:::

### Push a Private Image

```bash
# Tag your local image
docker tag myapp:latest registry.k8s.n37.ca/myapp:latest

# Push to Zot
docker push registry.k8s.n37.ca/myapp:latest
```

### Pull a Private Image in Kubernetes

Add the registry to your Pod spec:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: myapp
spec:
  containers:
    - name: myapp
      image: registry.k8s.n37.ca/myapp:latest
```

:::tip No imagePullSecret required for pulls
As of PR #595, Zot has anonymous read access enabled (`accessControl.repositories["**"].anonymousPolicy: ["read"]`). Cluster pods can pull any image from `registry.k8s.n37.ca` without credentials. Just reference the image directly:

```yaml
spec:
  containers:
    - name: myapp
      image: registry.k8s.n37.ca/myapp:latest
```

`imagePullSecrets` are only needed for **push** operations (private image uploads). Gatekeeper's `allowed-repos` constraint already includes `registry.k8s.n37.ca`.
:::

### Use as a Pull-Through Cache in Kubernetes Deployments

Replace upstream image references with the Zot prefix:

```yaml
# Before (pulls from Docker Hub directly)
image: nginx:1.27

# After (pulls from Zot cache → Docker Hub on first miss)
image: registry.k8s.n37.ca/library/nginx:1.27
```

This is particularly useful for:

- **Air-gap resilience** — If Docker Hub is temporarily unavailable, cached images still serve
- **Pull rate limits** — Docker Hub enforces pull limits for anonymous/free accounts. Zot's cache avoids repeated upstream pulls
- **Speed** — LAN-speed pulls from the Pi cluster's local NAS vs internet downloads

## Cluster Workloads Using Zot

As of PR #595 (2026-04-25), the following directly-managed workloads pull images through Zot:

| Workload | Original Registry | Zot Path |
|----------|------------------|----------|
| `cluster-healthcheck` CronWorkflow | `docker.io/bitnami/kubectl:latest` | `registry.k8s.n37.ca/bitnami/kubectl:latest` |
| `velero-backup-validation` CronWorkflow | `docker.io/bitnami/kubectl:latest` | `registry.k8s.n37.ca/bitnami/kubectl:latest` |
| `compliance-reporter` CronJob (trivy) | `docker.io/bitnami/kubectl:latest` | `registry.k8s.n37.ca/bitnami/kubectl:latest` |
| `external-dns-cloudflare` Deployment | `registry.k8s.io/external-dns/external-dns:v0.21.0` | `registry.k8s.n37.ca/external-dns/external-dns:v0.21.0` |
| `external-dns-unifi` Deployment | `registry.k8s.io/external-dns/external-dns:v0.21.0` | `registry.k8s.n37.ca/external-dns/external-dns:v0.21.0` |
| `external-dns-unifi-webhook` Deployment | `ghcr.io/kashalls/external-dns-unifi-webhook:v0.8.2` | `registry.k8s.n37.ca/kashalls/external-dns-unifi-webhook:v0.8.2` |

:::note Image path format
Zot's on-demand sync uses a flat path — drop the upstream registry hostname. Zot checks all configured upstreams (Docker Hub, GHCR, quay.io, registry.k8s.io) in order when the image isn't cached locally. In practice, each path is unique to one upstream so there is no ambiguity.

Helm chart-managed images (argocd, loki, grafana, etc.) pull directly from their upstreams. Routing Helm chart images through Zot requires per-chart registry override values — a separate effort.
:::

## Web UI

Browse available images and CVE scan results at `https://registry.k8s.n37.ca`:

- **Home** — Lists all cached repositories
- **Repository view** — Tags, manifest digests, layer sizes
- **CVE tab** — Trivy vulnerability report per tag (refreshes every 2h)

## CVE Scanning

Zot downloads the Trivy CVE database on startup (~850 MB) and refreshes it every 2 hours. Any image stored in Zot is automatically scanned.

Query scan results via the Zot API:

```bash
# List CVEs for an image
curl -u admin:<password> \
  "https://registry.k8s.n37.ca/v2/_zot/ext/search?query={CVEListForImage(image:\"library/nginx:latest\"){Tag,CVEList{Id,Severity,Title}}}" \
  | jq .
```

Or use the web UI's CVE tab for a human-readable view.

## Configuration

**Manifests location:** `manifests/base/zot/`

Key files:

| File | Purpose |
|------|---------|
| `values.yaml` | Helm values (image, storage, config.json, ingress) |
| `zot-htpasswd-sealed.yaml` | SealedSecret for htpasswd auth |
| `kustomization.yaml` | Kustomize entry point for SealedSecret |

The full Zot `config.json` is embedded in `values.yaml` under `configFiles`. Key sections:

```json
{
  "storage": {
    "rootDirectory": "/var/lib/registry",
    "gc": true,
    "gcDelay": "1h",
    "gcInterval": "24h"
  },
  "extensions": {
    "sync": {
      "enable": true,
      "registries": [
        {
          "urls": ["https://registry-1.docker.io"],
          "onDemand": true,
          "content": [{"prefix": "**"}]
        }
      ]
    }
  }
  // Note: "platforms" key is NOT supported in v2.1.16 and causes startup failure.
}
```

## Resource Usage

| Component | CPU Request | CPU Limit | Memory Request | Memory Limit |
|-----------|-------------|-----------|----------------|--------------|
| zot | 50m | 1000m | 256Mi | 2Gi |

Memory limit is set to 2Gi (Gatekeeper's maximum) to accommodate the Trivy CVE database (~1.5Gi on first load).

## Troubleshooting

### First Pull Is Slow

Expected — Zot downloads all platform variants of the image on first pull (v2.1.16 has no platform filtering). For `nginx:latest` this is ~41 seconds. Subsequent pulls are instant from the local cache.

### 504 Gateway Timeout on Pull

Check that the ingress-nginx NetworkPolicy allows egress to the `zot` namespace on port 5000:

```bash
kubectl get networkpolicy ingress-nginx-network-policy -n ingress-nginx -o yaml | grep -A5 "zot"
```

### Check Sync Status

```bash
# Watch Zot logs during a pull
kubectl logs -f zot-0 -n zot | grep -E "sync|Copy|HTTP API"
```

### Registry API Health

```bash
# Unauthenticated health check
curl https://registry.k8s.n37.ca/v2/

# Authenticated catalog (lists all repos)
curl -u admin:<password> https://registry.k8s.n37.ca/v2/_catalog | jq .
```

### Storage Usage

```bash
# Check PVC usage
kubectl exec -n zot zot-0 -- df -h /var/lib/registry
```

### Pod Restart After Config Change

Zot is a StatefulSet with a RWO iSCSI PVC (`synology-iscsi-delete`). Only one node can mount it at a time. If the pod is rescheduled to a different node, it may take 30–60s for the iSCSI session to transfer. Use `Recreate` strategy (already configured) — never `RollingUpdate` with RWO volumes.

## References

- [Zot Documentation](https://zotregistry.dev/v2.1.16/)
- [Zot GitHub](https://github.com/project-zot/zot)
- [CNCF Project Page](https://www.cncf.io/projects/zot/)

---

**Last Updated:** 2026-04-23
