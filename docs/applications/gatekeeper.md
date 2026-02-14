# OPA Gatekeeper

## Production Status

**Status:** ✅ **OPERATIONAL** (Deployed: 2026-02-06, PRs #389-392)

| Component | Status | Resources |
|-----------|--------|-----------|
| Controller Manager | Running (1 replica) | 100m/256Mi → 500m/512Mi |
| Audit Controller | Running (1 replica) | 100m/256Mi → 500m/512Mi |

**Operational Highlights:**

- ✅ 5 ConstraintTemplates installed
- ✅ 5 Constraints active (**deny** mode since 2026-02-07)
- ✅ 0 violations (resolved 2026-02-07 PRs #404-408, exclusion audit 2026-02-14 PRs #451-452)
- ✅ Audit scanning all namespaces every 5 minutes
- ✅ Prometheus metrics via PodMonitor on port 8888
- ✅ Grafana dashboard for constraint violations
- ✅ NetworkPolicy configured
- ✅ System namespaces exempted from admission control

## Overview

OPA Gatekeeper is a Kubernetes-native policy engine based on the Open Policy Agent (OPA). It operates as a ValidatingAdmissionWebhook to enforce policies on resources before they are created or modified. This fills the **admission control** gap in the security stack:

| Tool | Layer | Purpose |
|------|-------|---------|
| Trivy Operator | Scanning | Container image vulnerability detection |
| Falco | Runtime | Syscall monitoring and threat detection |
| **Gatekeeper** | **Admission** | **Prevent bad resources from being created** |

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    GATEKEEPER ARCHITECTURE                          │
└─────────────────────────────────────────────────────────────────────┘

  kubectl apply / ArgoCD sync
          │
          ▼
  ┌───────────────────┐        ┌───────────────────────────────────┐
  │  Kubernetes API   │───────▶│  Gatekeeper Webhook (port 8443)   │
  │  Server           │◀───────│  ValidatingAdmissionWebhook       │
  │                   │ admit/ │                                   │
  │                   │ deny   │  ┌─────────────────────────────┐  │
  └───────────────────┘        │  │  ConstraintTemplates (Rego) │  │
                               │  │  ┌───────────────────────┐  │  │
                               │  │  │ K8sRequireResLimits   │  │  │
                               │  │  │ K8sAllowedRepos       │  │  │
                               │  │  │ K8sRequireLabels      │  │  │
                               │  │  │ K8sBlockNodePort      │  │  │
                               │  │  │ K8sContainerLimits    │  │  │
                               │  │  └───────────────────────┘  │  │
                               │  └─────────────────────────────┘  │
                               └───────────────────────────────────┘
                                          │
                               ┌──────────▼──────────┐
                               │  Audit Controller   │
                               │  (every 300s)       │
                               │  Scans all existing │
                               │  resources          │
                               └──────────┬──────────┘
                                          │
                               ┌──────────▼──────────┐
                               │  Prometheus :8888   │
                               │  gatekeeper_*       │
                               │  violation metrics  │
                               └─────────────────────┘
```

## Deployment

Gatekeeper is deployed via two ArgoCD Applications:

1. **`gatekeeper`** - Helm chart + ConstraintTemplates
2. **`gatekeeper-policies`** - Constraints (separate app due to CRD ordering)

ConstraintTemplates create custom CRDs that Constraints depend on. Splitting into two Applications ensures the CRDs exist before Constraints are applied.

**ArgoCD Applications:**

- `manifests/applications/gatekeeper.yaml` (sync wave -6)
- `manifests/applications/gatekeeper-policies.yaml` (sync wave -5)

**Configuration:** `manifests/base/gatekeeper/values.yaml`

**Version:** Helm chart 3.21.1 (Gatekeeper v3.21.1)

**Sync Wave:** -6 (after monitoring stack, before Velero/Falco)

### Resource Configuration

Optimized for Raspberry Pi 5 cluster:

| Component | CPU Request | CPU Limit | Memory Request | Memory Limit |
|-----------|-------------|-----------|----------------|--------------|
| Controller Manager | 100m | 500m | 256Mi | 512Mi |
| Audit Controller | 100m | 500m | 256Mi | 512Mi |

**Total footprint:** ~200m CPU / 512Mi RAM

## Policies

### Enforcement Mode

All constraints were initially deployed in **dryrun** mode for auditing. After resolving all violations (PRs #404-408), they were switched to **deny** mode on 2026-02-07, which actively blocks non-compliant resources.

**Rollout process used:**

1. Deploy in `dryrun` mode - audit existing violations
2. Fix all violations across the cluster (12 violations resolved)
3. Switch to `deny` mode to enforce policies

### Active Policies

#### K8sRequireResourceLimits

**Purpose:** Ensures all containers have CPU and memory limits set.

**Why:** Critical for the Pi cluster - prevents any single pod from consuming all resources on a node.

**Scope:** All Pods (excluding system namespaces)

```yaml
# This would be flagged:
containers:
  - name: nginx
    image: nginx  # No resources.limits!

# This passes:
containers:
  - name: nginx
    image: nginx
    resources:
      limits:
        cpu: 200m
        memory: 256Mi
```

#### K8sAllowedRepos

**Purpose:** Restricts container images to approved registries.

**Allowed registries:**

- `docker.io`
- `ghcr.io`
- `quay.io`
- `registry.k8s.io`
- `gcr.io`

**Scope:** All Pods (excluding system namespaces)

#### K8sRequireLabels

**Purpose:** Requires `app.kubernetes.io/name` label on all Pods.

**Why:** Enables consistent monitoring, network policies, and service discovery.

**Scope:** All Pods (excluding system namespaces)

#### K8sBlockNodePort

**Purpose:** Prevents creation of NodePort services.

**Why:** The cluster uses MetalLB for LoadBalancer services. NodePort is unnecessary and exposes ports directly on node IPs.

**Scope:** All Services (cluster-wide)

#### K8sContainerLimits

**Purpose:** Enforces maximum resource limits per container.

**Limits:** 2 CPU cores, 2Gi RAM per container

**Why:** Prevents any single container from monopolizing a Raspberry Pi 5 node (4 cores, 16GB RAM).

**Scope:** All Pods (excluding system namespaces)

### Exempted Namespaces

:::info Exclusion Audit (2026-02-14)
Reduced `excludedNamespaces` in `require-resource-limits` from 10 to 2 (PRs #451, #452). Resource limits were added to all containers in previously-excluded namespaces: argocd (dex, redis-secret-init), cert-manager, calico-system (typha, apiserver, csi-node-driver), synology-csi, istio-system, metallb-system, gatekeeper-system, localstack.
:::

The following namespaces are still exempt from the `require-resource-limits` constraint:

- `kube-system` - Core Kubernetes components (kubeadm-managed, cannot add limits via GitOps)
- `tigera-operator` - Calico operator (upstream release manifest, would require patching)

All other namespaces (including `argocd`, `calico-system`, `istio-system`, `cert-manager`, `gatekeeper-system`, `metallb-system`, `synology-csi`, `localstack`) now have resource limits on all containers and are subject to Gatekeeper admission control.

The `gatekeeper-system` namespace remains exempt from Gatekeeper's own webhook (self-referential exemption) but is no longer exempt from the resource limits constraint.

## Common Operations

### View Audit Violations

```bash
# Check total violations per constraint
kubectl get constraints

# View detailed violations for resource limits
kubectl get k8srequireresourcelimits require-resource-limits -o yaml | \
  grep -A 20 'violations:'

# View all constraint violations
kubectl get k8sallowedrepos allowed-repos -o yaml
kubectl get k8srequirelabels require-labels -o yaml
kubectl get k8sblocknodeport block-nodeport -o yaml
kubectl get k8scontainerlimits container-limits -o yaml
```

### Test Policy Detection

```bash
# This should log a dryrun violation (no resource limits):
kubectl run test-no-limits --image=nginx --restart=Never -n default

# Check the violation was recorded:
kubectl get k8srequireresourcelimits require-resource-limits \
  -o jsonpath='{.status.totalViolations}'

# Clean up:
kubectl delete pod test-no-limits -n default
```

### Check Gatekeeper Health

```bash
# Verify pods are running
kubectl get pods -n gatekeeper-system

# Check controller logs
kubectl logs -n gatekeeper-system deployment/gatekeeper-controller-manager

# Check audit logs
kubectl logs -n gatekeeper-system deployment/gatekeeper-audit

# Verify webhook is registered
kubectl get validatingwebhookconfigurations | grep gatekeeper
```

### Switch Constraint to Deny Mode

To switch a constraint from `dryrun` to `deny` (blocks violating resources):

```bash
# Edit the constraint
kubectl edit k8srequireresourcelimits require-resource-limits

# Change:
#   enforcementAction: dryrun
# To:
#   enforcementAction: deny
```

Or update the YAML in the repository and let ArgoCD sync.

### Add a New Policy

1. Create a ConstraintTemplate in `manifests/base/gatekeeper/constraint-templates/`
2. Create a matching Constraint in `manifests/base/gatekeeper/constraints/`
3. Add both to the respective `kustomization.yaml` files
4. Commit, push, and let ArgoCD sync

## Monitoring

### Prometheus Metrics

Gatekeeper exposes metrics on port 8888:

- `gatekeeper_violations` - Total constraint violations by constraint
- `gatekeeper_audit_duration_seconds` - Time taken for audit runs
- `gatekeeper_constraint_templates` - Number of constraint templates
- `gatekeeper_constraints` - Number of constraints
- `gatekeeper_request_count` - Webhook request count
- `gatekeeper_request_duration_seconds` - Webhook request latency

### Grafana Dashboard

A custom Grafana dashboard monitors constraint violations, audit cycle health, and webhook latency. Deployed via ConfigMap with label `grafana_dashboard: "1"`.

### Integration Points

| System | Purpose | Port |
|--------|---------|------|
| Prometheus | Metrics via PodMonitor | 8888 |
| Kubernetes API | Webhook calls | 8443 |

:::note PodMonitor not ServiceMonitor
Gatekeeper's Helm chart does not create a metrics Service, so a **PodMonitor** (not ServiceMonitor) is used for Prometheus scraping on port `metrics` (8888).
:::

## Troubleshooting

### Gatekeeper Pods Not Starting

**Symptom:** Pods in CrashLoopBackOff

**Check:**

```bash
# View controller logs
kubectl logs -n gatekeeper-system deployment/gatekeeper-controller-manager

# Check events
kubectl get events -n gatekeeper-system --sort-by='.lastTimestamp'
```

**Common causes:**

- Insufficient resources (increase limits in values.yaml)
- Certificate rotation issues (check `gatekeeper-webhook-server-cert` secret)

### ConstraintTemplates Not Creating CRDs

**Symptom:** `kubectl get <constraint-kind>` returns "the server doesn't have a resource type"

**Check:**

```bash
# Verify template status
kubectl get constrainttemplate <name> -o yaml | grep -A 10 'status:'

# Look for Rego compilation errors
kubectl describe constrainttemplate <name>
```

### Webhook Blocking Requests (After Switching to Deny)

**Symptom:** `kubectl apply` returns admission webhook error

**Quick fix (emergency):**

```bash
# Set constraint back to dryrun
kubectl patch k8srequireresourcelimits require-resource-limits \
  --type merge -p '{"spec":{"enforcementAction":"dryrun"}}'
```

**Note:** The webhook `failurePolicy` is set to `Ignore`, so if Gatekeeper is down, requests are allowed through.

### ArgoCD Sync Issues

**Symptom:** `gatekeeper-policies` app stuck in OutOfSync

**Cause:** ConstraintTemplate CRDs may not be established yet

**Solution:** Wait for Gatekeeper retries (up to 10 attempts with 30s backoff). Check:

```bash
kubectl get crd | grep constraints.gatekeeper.sh
```

## Network Policy

Gatekeeper namespace has a NetworkPolicy restricting traffic:

**Allowed Ingress:**

- Kubernetes API server (webhook calls on 8443)
- Prometheus (metrics scraping on 8888)
- Internal namespace communication

**Allowed Egress:**

- DNS (kube-system:53)
- Kubernetes API (6443, for audit controller)
- Internal namespace communication

## Configuration Files

| File | Purpose |
|------|---------|
| `manifests/applications/gatekeeper.yaml` | ArgoCD Application (Helm + ConstraintTemplates) |
| `manifests/applications/gatekeeper-policies.yaml` | ArgoCD Application (Constraints) |
| `manifests/base/gatekeeper/values.yaml` | Helm values (replicas, resources, audit) |
| `manifests/base/gatekeeper/kustomization.yaml` | Kustomize overlay for ConstraintTemplates |
| `manifests/base/gatekeeper/constraint-templates/` | Rego policy definitions (5 templates) |
| `manifests/base/gatekeeper/constraints/` | Policy bindings (5 constraints, deny mode) |
| `manifests/base/network-policies/gatekeeper-system/` | Network isolation |

## Security Considerations

- **Webhook TLS**: Gatekeeper manages its own TLS certificates for the webhook
- **Failure Policy**: Set to `Ignore` - if Gatekeeper is unavailable, requests are allowed through (safe for homelab)
- **Deny Mode**: All constraints enforce policies (switched from dryrun on 2026-02-07 after resolving all violations)
- **Exempt Namespaces**: System namespaces are exempt to prevent infrastructure issues
- **Rego Policies**: Policy logic is defined in Rego (OPA's policy language), reviewed via GitOps

## Resources

- **Official Documentation**: [open-policy-agent.github.io/gatekeeper](https://open-policy-agent.github.io/gatekeeper/website/docs/)
- **Helm Chart**: [github.com/open-policy-agent/gatekeeper](https://github.com/open-policy-agent/gatekeeper/tree/master/charts/gatekeeper)
- **Rego Language**: [openpolicyagent.org/docs/latest/policy-language](https://www.openpolicyagent.org/docs/latest/policy-language/)
- **Gatekeeper Library**: [github.com/open-policy-agent/gatekeeper-library](https://github.com/open-policy-agent/gatekeeper-library)

## Related Documentation

- [Trivy Operator](./trivy-operator.md) - Container vulnerability scanning
- [Falco](./falco.md) - Runtime security monitoring
- [Network Policies](../security/network-policies.md) - Gatekeeper namespace isolation
