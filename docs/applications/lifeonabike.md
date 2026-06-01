---
sidebar_position: 25
title: "lifeonabike.ca"
description: "Web application deployment with automated CI/CD build pipeline"
---

# lifeonabike.ca

The `lifeonabike` namespace hosts the web application at `lifeonabike.ca`, a Cloudflare Tunnel for external access, and integrates with the Argo Events + Argo Workflows CI/CD pipeline for automated builds on GitHub push.

## Overview

| Property | Value |
|----------|-------|
| **Namespace** | `lifeonabike` |
| **ArgoCD App** | `lifeonabike` |
| **Sync Wave** | 5 |
| **Public URL** | `https://lifeonabike.ca`, `https://www.lifeonabike.ca` |
| **Build Webhook** | `https://build-webhook.n37.ca` |
| **Source Repo** | `github.com/imcbeth/lifeonabike.ca` (private) |
| **Registry** | `registry.k8s.n37.ca/lifeonabike/lifeonabike.ca` (Zot) |

## Components

| Resource | Kind | Description |
|----------|------|-------------|
| `web` | Deployment | Web application (image from Zot registry) |
| `web` | Service | ClusterIP port 80 → pod port 8080 (nginx non-root) |
| `web` / `www` | Ingress | nginx ingress routing (TLS via cert-manager) |
| `cloudflared` | Deployment | Cloudflare Tunnel (2 replicas) |
| `cloudflared-config` | ConfigMap | Tunnel routing rules |
| `tunnel-credentials` | SealedSecret | Tunnel auth credentials |
| `lifeonabike-registry-creds` | SealedSecret | Zot pull credentials for web Deployment |
| `lifeonabike-ca-tls` | Certificate | Let's Encrypt cert (apex + www SAN) |

## Cloudflare Tunnel

The Cloudflare Tunnel replaces a public LoadBalancer for external traffic. Two `cloudflared` pods run in the namespace and maintain outbound connections to Cloudflare's edge network.

### Routing

| Hostname | Destination |
|----------|-------------|
| `lifeonabike.ca` | `web.lifeonabike.svc.cluster.local:80` |
| `www.lifeonabike.ca` | `web.lifeonabike.svc.cluster.local:80` |
| `build-webhook.n37.ca` | `lifeonabike-github-eventsource-svc.argo-events.svc.cluster.local:12000` |

The tunnel routes `build-webhook.n37.ca` to the Argo Events webhook port — this is how GitHub push events from `imcbeth/lifeonabike.ca` reach the cluster without any public IP or ingress-nginx rule.

### Credentials

The tunnel credentials JSON is stored as a SealedSecret named `tunnel-credentials`. To rotate:

```bash
# Seal new credentials (obtain JSON from Cloudflare dashboard)
kubectl create secret generic tunnel-credentials \
  --from-file=credentials.json=<path-to-json> \
  -n lifeonabike --dry-run=client -o yaml | \
  kubeseal --cert <(kubectl get secret -n kube-system \
    -l sealedsecrets.bitnami.com/sealed-secrets-key=active \
    -o jsonpath='{.items[0].data.tls\.crt}' | base64 -d) \
  --format yaml > manifests/base/lifeonabike/tunnel-credentials-sealed.yaml
```

## CI/CD Build Pipeline

Every push to the `main` branch of `github.com/imcbeth/lifeonabike.ca` triggers an automated build:

```
GitHub push (main) ──► build-webhook.n37.ca (Cloudflare Tunnel)
  ──► Argo Events EventSource (port 12000)
    ──► EventBus (NATS JetStream)
      ──► Sensor (lifeonabike-build)
        ──► WorkflowTemplate (lifeonabike-build) in argo-workflows ns
          ├── Step 1: git-clone  (alpine/git, captures SHA)
          ├── Step 2: kaniko-build  (builds + pushes to Zot)
          └── Step 3: rollout-restart  (kubectl, triggers new pod pull)
```

### WorkflowTemplate

**Namespace:** `argo-workflows`
**Name:** `lifeonabike-build`

#### Step 1: git-clone

Uses `alpine/git:2.43.0` to shallow-clone `imcbeth/lifeonabike.ca` using a GitHub PAT (`github-clone-token` SealedSecret). Writes the short git SHA to `/tmp/sha` for downstream tagging.

#### Step 2: kaniko-build

Builds the Docker image and pushes two tags:

```
zot.zot.svc.cluster.local:5000/lifeonabike/lifeonabike.ca:<git-sha>
zot.zot.svc.cluster.local:5000/lifeonabike/lifeonabike.ca:latest
```

Uses `--insecure` because Kaniko pushes to the **in-cluster Zot ClusterIP** over HTTP (port 5000). See [in-cluster registry gotcha](#in-cluster-zot-push-over-http) below.

#### Step 3: rollout-restart

Uses `alpine/k8s:1.31.0` to run:

```bash
kubectl rollout restart deployment/web -n lifeonabike
```

This causes the `web` Deployment to pull the new `:latest` image.

### Manual Trigger

```bash
argo submit --from workflowtemplate/lifeonabike-build \
  -n argo-workflows \
  -p revision=main
```

### Required Secrets (one-time setup)

```bash
# GitHub PAT for cloning the private repo
kubectl create secret generic github-clone-token \
  --from-literal=token=<github-pat> \
  -n argo-workflows

# Zot registry credentials for Kaniko push
kubectl create secret docker-registry lifeonabike-registry-creds \
  --docker-server=zot.zot.svc.cluster.local:5000 \
  --docker-username=admin \
  --docker-password='<password>' \
  -n argo-workflows

# Same credentials needed in lifeonabike ns for web Deployment pull
kubectl create secret docker-registry lifeonabike-registry-creds \
  --docker-server=registry.k8s.n37.ca \
  --docker-username=admin \
  --docker-password='<password>' \
  -n lifeonabike
```

Both are managed as SealedSecrets in GitOps (`manifests/base/argo-workflows/` and `manifests/base/lifeonabike/`).

### RBAC

| Role | Namespace | Binding | Purpose |
|------|-----------|---------|---------|
| `lifeonabike-workflow-submitter` | `argo-workflows` | `lifeonabike-sensor-sa` (argo-events ns) | Sensor submits workflows |
| `lifeonabike-deployer` | `lifeonabike` | `argo-workflow` SA (argo-workflows ns) | rollout-restart step |

## Gotchas

### In-Cluster Zot Push Over HTTP

**Problem:** Kaniko cannot push to `registry.k8s.n37.ca` (the MetalLB LoadBalancer IP) via HTTPS from within the cluster. Pod-level routing to MetalLB VIPs is broken in-cluster on this setup.

**Symptom:** Kaniko push fails with TLS handshake errors or connection refused.

**Fix:** Use the Zot ClusterIP service directly:

```
zot.zot.svc.cluster.local:5000
```

Pass `--insecure` and `--insecure-pull` to Kaniko. Kubelet image pulls happen at the **node level** (not inside pods), so they still use `registry.k8s.n37.ca` over HTTPS and are unaffected.

### Istio Ambient Bypass for Workflow Pods

**Problem:** Workflow pods that push to Zot (HTTP) or run `kubectl` have ztunnel intercept their outbound connections. ztunnel resets connections to non-mesh destinations (Zot in-cluster HTTP, Kubernetes API server) because it can't establish HBONE with them.

**Fix:** Add this annotation to all workflow pod metadata:

```yaml
ambient.istio.io/redirection: disabled
```

This is set in the `WorkflowTemplate.spec.podMetadata.annotations`.

### git-crypt Filename Rule

Git-crypt is configured to encrypt any file matching `*secret*`. SealedSecret files must use the `*-sealed.yaml` naming convention to avoid being double-encrypted (git-crypt + SealedSecrets) and to avoid yamllint failures (base64 values in git-crypt-encrypted files fail linting).

## Networking

The `lifeonabike` namespace has no dedicated NetworkPolicy — the Cloudflare Tunnel pods only need:

- **Outbound HTTPS (443)** to Cloudflare's edge network
- **Outbound HTTP to argo-events:12000** (for the build webhook routing)
- **Outbound HTTP to web Service:80** (served locally within the namespace via the ClusterIP Service)

:::note Port mapping
The `web` container runs nginx as a non-root user and binds to **port 8080** (non-privileged). The `web` Service maps **port 80 → targetPort 8080**. The Cloudflare Tunnel connects to the Service at port 80 (`web.lifeonabike.svc.cluster.local:80`), which kube-proxy translates to pod port 8080. The ingress-nginx NetworkPolicy egress rule allows port **8080** because ingress-nginx resolves backend Services to their pod endpoints (bypassing the Service ClusterIP) and connects directly to the pod on port 8080.
:::

The ingress-nginx NetworkPolicy allows egress to `lifeonabike:8080` for web traffic (pod endpoint port, not Service port).

## TLS Certificate

A `Certificate` resource requests a Let's Encrypt cert covering both apex and www:

| Field | Value |
|-------|-------|
| Secret | `lifeonabike-ca-tls` |
| DNS Names | `lifeonabike.ca`, `www.lifeonabike.ca` |
| Issuer | `letsencrypt-prod` (ClusterIssuer, DNS-01 via Cloudflare) |
| Valid | Apr 18 – Jul 17 2026 |

## Troubleshooting

### Build workflow not triggering on push

1. Check the GitHub webhook delivery log: `https://github.com/imcbeth/lifeonabike.ca/settings/hooks`
2. Verify `build-webhook.n37.ca` resolves and the Cloudflare Tunnel is healthy:

   ```bash
   kubectl get pods -n lifeonabike -l app=cloudflared
   ```

3. Check the EventSource logs:

   ```bash
   kubectl logs -n argo-events -l eventsource-name=lifeonabike-github
   ```

### Kaniko push fails

```bash
# Check workflow logs for the kaniko step
argo logs -n argo-workflows <workflow-name> -c main

# Verify Zot ClusterIP
kubectl get svc -n zot zot
```

### New image not pulled after rollout

The `web` Deployment uses `imagePullPolicy: Always` (or `:latest` tag forces a pull check). If pods are stuck on the old image:

```bash
kubectl rollout status deployment/web -n lifeonabike
kubectl describe pod -n lifeonabike -l app=web | grep -A5 "Events:"
```

## References

- [Cloudflare Tunnel Documentation](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
- [Argo Events lifeonabike EventSource](../applications/argo-events.md)
- [Argo Workflows lifeonabike WorkflowTemplate](../applications/argo-workflows.md#lifeonabike-build-pipeline)
- [Zot OCI Registry](../applications/zot.md)

---

**Last Updated:** 2026-06-01
