---
sidebar_position: 5
title: "Pod Security Admission"
description: "Namespace-level Pod Security Standards enforcement, and why each namespace sits at the level it does"
---

# Pod Security Admission

Pod Security Admission (PSA) is the in-tree admission controller that enforces the
[Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
per namespace. It is configured entirely with labels on the `Namespace` object —
there is no chart, no CRD and no controller to deploy.

## Why this page exists

Until 2026-10-29 the cluster had **no PSA labels at all on 31 of its 35
namespaces**. That is not a neutral default: a namespace with no
`pod-security.kubernetes.io/enforce` label is admitted at **`privileged`**, the
level that permits host namespaces, privileged containers, and arbitrary host
paths.

So every workload namespace was being admitted at the most permissive level
available, including the one serving a public website.

Fixed in PR #1086, which labelled the 13 namespaces holding our own workloads.

## Current levels

| Level | Namespaces |
|---|---|
| `restricted` | `cert-manager`, `oauth2-proxy`, `strimzi-system`, `flink-demo` |
| `baseline` (with `warn`/`audit` at `restricted`) | `argo-events`, `external-dns`, `lifeonabike`, `flink-operator`, `kafka`, `tempo`, `trivy-system`, `velero` |
| `privileged` (explicit) | `synology-csi` |

Every `baseline` namespace also carries:

```yaml
pod-security.kubernetes.io/enforce: baseline
pod-security.kubernetes.io/enforce-version: latest
pod-security.kubernetes.io/warn: restricted
pod-security.kubernetes.io/audit: restricted
```

The `warn`/`audit` pair at the stricter level is the useful part: the distance
to `restricted` stays visible on every apply, in warnings, without blocking
anything today.

## How the levels were chosen

Not by taste. Each level was dry-run against the pods **actually scheduled** in
that namespace before being committed:

```bash
kubectl label --dry-run=server ns/<name> \
  pod-security.kubernetes.io/enforce=<level>
```

A violating pod makes the server return a warning naming it. All 13 came back
clean, re-verified with `kubectl apply --dry-run=server` against the real
manifests. No pod was evicted and none needed changing.

:::note PSA never evicts
PSA is an *admission* controller. Labelling a namespace does not touch pods that
are already running — a violating pod keeps running until something tries to
recreate it, at which point admission refuses. This is why the dry-run matters:
the failure shows up later, on an unrelated rollout, long after the label was
added.
:::

## `synology-csi` is `privileged` on purpose

The CSI node plugin mounts host paths and needs privileged containers; it cannot
run under `baseline`. The label is set **explicitly** rather than left absent so
it reads as a decision in the manifest, where silence would look like an
oversight — which is exactly what the other 30 unlabelled namespaces looked like.

## `default` is the one that can't move yet

`default` holds the monitoring stack and cannot take `baseline` as-is:

- **blackbox-exporter** needs `NET_RAW` for ICMP probes (see
  [Blackbox Exporter → Calico ICMP egress](../applications/blackbox-exporter.md))
- **node-exporter** needs `hostPID`

Both are legitimate. Moving `default` to `baseline` means splitting those two out
into their own namespace, which is a real change with real blast radius, not a
label edit. Left alone deliberately.

`kube-system`, `kube-public` and `kube-node-lease` are left to the distribution.

## A label file that does nothing

`manifests/base/velero/namespace.yaml` carried the PSA labels from #1086 and
**they had no effect**, because that file was never listed in its kustomization's
`resources`. ArgoCD creates the namespace itself via `CreateNamespace=true`,
which produces a bare namespace with no labels — so the file looked
authoritative while doing nothing, for its `app.kubernetes.io/*` labels too.

Found only because 12 of 13 namespaces picked up their labels and `velero`
reported `enforce=MISSING`. Fixed in PR #1090.

Audit for the same shape anywhere else:

```bash
# For each namespace manifest, is its basename referenced by a kustomization?
for f in $(find manifests/base -name 'namespace.y*ml'); do
  d=$(dirname "$f"); b=$(basename "$f")
  grep -q "$b" "$d/kustomization.yaml" 2>/dev/null \
    || echo "ORPHAN (or parent-referenced): $f"
done
```

The `network-policies/*/namespace.yaml` files are referenced from the **parent**
kustomization, so they show up in that check and are fine. `velero` was the only
genuine orphan.

## Verifying

```bash
# Which namespaces have no enforce label at all?
kubectl get ns -o json | jq -r '
  .items[]
  | select((.metadata.labels // {})["pod-security.kubernetes.io/enforce"] == null)
  | .metadata.name'

# Current level per namespace
kubectl get ns -o custom-columns=\
'NAME:.metadata.name,ENFORCE:.metadata.labels.pod-security\.kubernetes\.io/enforce'

# Did anything get refused or warned recently?
kubectl get events -A --field-selector type=Warning \
  | grep -i 'violate\|PodSecurity'
```

## Related documentation

- [Network Policies](./network-policies.md) — the other half of namespace isolation
- [Runtime Security](./runtime-security.md) — Falco, Trivy and Gatekeeper
- [Resource Quotas](./resource-quotas.md) — object-count caps per namespace
