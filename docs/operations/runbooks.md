---
sidebar_position: 1
title: "Operational Runbooks"
description: "Step-by-step procedures for common operational tasks: stuck syncs, pod restarts, rollbacks, PVC recovery, certificate renewal"
---

# Operational Runbooks

Concrete step-by-step procedures for the things that actually break. Each runbook starts with **symptoms** (how you'd notice the problem), then **diagnose**, then **resolve**, then **verify**.

## ArgoCD app stuck in `Progressing` state

**Symptoms.** `ArgoCDAppProgressing` alert firing (default `for: 1h`). App shows `Synced + Progressing` but no rollout is actually happening.

**Diagnose.**

```bash
# Which resources are keeping the app in Progressing?
kubectl get application <app> -n argocd -o json | \
  jq '.status.resources[] | select(.health.status != "Healthy")'

# Non-Running / non-Ready pods in the target namespace
kubectl get pod -n <ns> -o wide | grep -v Running

# What's the operation currently doing?
kubectl get application <app> -n argocd \
  -o jsonpath='{.status.operationState.message}{"\n"}'
```

**Common root causes:**

- **Pod stuck `RunContainerError`** — a chaos-mesh experiment or admission webhook mutation swapped the container image to something the runtime can't exec. Check `kubectl describe pod <pod> -n <ns>` for the actual error. See [chaos-mesh self-lockup recovery](../applications/chaos-mesh.md#chaos-mesh-pods-running-pauselatest-self-lockup) if the image is `pause:latest`.
- **Job stuck (never completing)** — usually a PreSync/PostSync hook waiting on a dependency. Check `kubectl get job -n <ns>` and delete the hook Job if it's genuinely stuck.
- **StatefulSet replica won't come up** — often iSCSI RO cascade. See [PVC mount went read-only](#pvc-mount-went-read-only-erofs) below.

**Resolve.**

1. Fix the underlying resource (delete stuck pod, delete stuck Job, kubectl rollout restart, etc.).
2. Alert clears within ~1 min once `argocd_app_info{health_status="Progressing"}` drops.

**See also.** [ArgoCD alerting section](../applications/argocd.md#alerting) — the alert set and rationale.

---

## ArgoCD application stuck OutOfSync

**Symptoms.** App shows `OutOfSync` for >10 minutes; sync history shows no new attempts; manual sync errors with a permission or hook failure.

**Diagnose.**

```bash
# Status + last operation
kubectl get application <app> -n argocd -o jsonpath='{.status.sync.status}{"\n"}{.status.operationState.message}{"\n"}'

# Recent events
kubectl describe application <app> -n argocd | tail -30

# What's drifting?
kubectl get application <app> -n argocd -o json | \
  jq '.status.resources[] | select(.status != "Synced")'
```

**Resolve.**

Pick the option that matches the diagnosis:

```bash
# 1. Soft refresh — pick up new git revisions
kubectl annotate application <app> -n argocd \
  argocd.argoproj.io/refresh=normal --overwrite

# 2. Hard refresh — force re-resolve of Helm values / multi-source
kubectl annotate application <app> -n argocd \
  argocd.argoproj.io/refresh=hard --overwrite

# 3. Stuck hook (Job that never completed) — delete it
kubectl delete job <stuck-hook-job> -n <app-namespace>

# 4. Terminate a hung sync operation
argocd app terminate-op <app>   # via CLI
# OR via the UI: App → Sync Status → Terminate
```

**Verify.** App returns to `Synced` + `Healthy` within ~2 minutes:

```bash
watch -n5 'kubectl get application <app> -n argocd -o jsonpath="{.status.sync.status}/{.status.health.status}{\"\n\"}"'
```

**When to escalate.** If hard refresh + hook cleanup don't resolve in 10 minutes, the underlying resource may have a finalizer holding it. Check `kubectl get <resource> -o yaml | grep finalizer`.

---

## Pod restart needed (not auto-fixed by a redeploy)

**Symptoms.** Pod is alive but misbehaving — leaked memory, stale config that didn't reload, sidecar can't talk to a peer.

**Resolve.**

```bash
# Single Deployment / StatefulSet: rolling restart
kubectl rollout restart deployment/<name> -n <ns>
kubectl rollout restart statefulset/<name> -n <ns>

# DaemonSet (cycles all node pods)
kubectl rollout restart daemonset/<name> -n <ns>

# One specific pod (controller recreates it)
kubectl delete pod <pod-name> -n <ns>

# Watch the rollout
kubectl rollout status deployment/<name> -n <ns>
```

For Helm-managed workloads owned by ArgoCD, the rollout restart annotation is preserved by ArgoCD's SSA — no drift will reset it.

**Verify.** `kubectl get pods -n <ns>` shows new pod ages; logs from the new pod show the expected startup sequence.

---

## Roll back an ArgoCD application to a previous git revision

**Symptoms.** Recently merged change broke something; need to revert quickly while the bad commit is reverted in git.

**Resolve.**

```bash
# 1. List recent sync history (git revisions, deploy timestamps)
kubectl get application <app> -n argocd -o json | \
  jq '.status.history[] | {id, revision, deployedAt}'

# 2. Sync to a specific revision
argocd app sync <app> --revision <commit-sha>

# 3. Or revert the bad commit in git, push, and let auto-sync pick it up
git revert <bad-sha> && git push
```

Auto-sync (enabled on all our apps) usually makes option 3 the cleanest path — the rollback lives in git history.

**Verify.** App returns to Healthy on the target revision:

```bash
kubectl get application <app> -n argocd -o jsonpath='{.status.sync.revision}{"\n"}'
```

**Pitfall.** Don't use `argocd app sync --revision` for long — auto-sync will pull `HEAD` again on the next reconcile and you're back to the bad state. Always combine with a `git revert`.

---

## PVC stuck in `Terminating`

**Symptoms.** PVC won't delete; `kubectl delete pvc` hangs; `kubectl get pvc` shows `Terminating` for 5+ minutes.

**Diagnose.**

```bash
# What's holding the finalizer?
kubectl get pvc <pvc> -n <ns> -o yaml | grep -A5 finalizers

# Is any pod still mounting it?
kubectl get pods -n <ns> -o json | \
  jq '.items[] | select(.spec.volumes[]?.persistentVolumeClaim.claimName == "<pvc>") | .metadata.name'

# Is the underlying PV stuck?
kubectl get pv $(kubectl get pvc <pvc> -n <ns> -o jsonpath='{.spec.volumeName}') -o yaml | \
  grep -A5 finalizers
```

**Resolve (PVC).**

```bash
# Confirm no pods using it; then patch off the finalizer
kubectl patch pvc <pvc> -n <ns> -p '{"metadata":{"finalizers":null}}' --type=merge
```

**Resolve (PV).** Synology CSI PVs sometimes need the iSCSI session cleaned up first:

```bash
# Check session on the node
ssh imcbeth@10.0.10.214 sudo iscsiadm -m session

# Force-detach if needed (very rare — confirm no other workloads share the LUN first)
kubectl patch pv <pv> -p '{"metadata":{"finalizers":null}}' --type=merge
```

**Verify.** `kubectl get pvc` shows the PVC is gone; iSCSI session no longer references the deleted target.

**Pitfall.** A PVC stuck Terminating with no pods mounting it usually means a controller is still referencing it (a `VolumeSnapshot` mid-snapshot, a Velero restore in progress). Check `kubectl get events -n <ns>` for the actual blocker before patching off finalizers.

---

## PVC mount went read-only (EROFS)

**Symptoms.** A pod is `Running` but the application inside is failing writes with `Read-only file system` / `EROFS` / `Input/output error`. Loki, Uptime Kuma, Falco-Redis, Prometheus, Grafana are the historical victims because they hold the largest PVCs.

Signs to look for in pod logs:

- Loki: `error running loki: ... read-only file system` then crashloop
- Uptime Kuma: `chown: changing ownership of '/app/data/...': Read-only file system`
- Redis: `Failed opening the temp RDB file ...: Input/output error`
- Prometheus / Grafana: tsdb / sqlite write errors, then crashloop

**Diagnose.**

```bash
# Confirm the underlying mount is RO
LOKI_NODE=$(kubectl get pod -n loki loki-0 -o jsonpath='{.spec.nodeName}')
MON=$(kubectl get pod -n synology-csi -l app.kubernetes.io/name=pvc-mount-monitor \
  --field-selector=spec.nodeName=$LOKI_NODE \
  -o jsonpath='{.items[0].metadata.name}')

kubectl exec -n synology-csi $MON -- /bin/sh -c \
  "awk '\$2 ~ /kubernetes.io~csi.*\\/mount/ && \$4 ~ /^ro,/' /host/proc/1/mounts"
# Any output = pod's CSI mount is RO

# Also check the globalmount (the underlying iSCSI device)
kubectl exec -n synology-csi $MON -- /bin/sh -c \
  "grep -E 'kubernetes.io/csi.*synology.*globalmount' /host/proc/1/mounts"
# Look for `ro,` in column 4 of the matching line
```

**Resolve (automation should handle this; manual is the fallback).**

The [PVC RO Mount Auto-Remediation](../storage/pvc-ro-automation.md) pipeline catches this automatically within ~4 minutes. Verify it ran:

```bash
# Latest remediator pod logs (should show 'no RO mounts detected' OR 'ACTION pvc=... pod=...')
kubectl get pod -n synology-csi -l app.kubernetes.io/name=pvc-ro-remediator \
  --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}{"\n"}' \
  | xargs -I{} kubectl logs -n synology-csi {}
```

If the automation didn't act (e.g., the affected pod is in a [protected namespace](../storage/pvc-ro-automation.md#why-a-protected-namespace-allowlist) like `kube-system`, or the automation itself is broken), the manual fix matches what the automation does:

```bash
# Simple case: pod bind-mount is RO but the underlying iSCSI device is RW
kubectl delete pod -n <ns> <affected-pod>
# Wait for pod to come back Running; verify writes work
```

**Hard case — iSCSI globalmount itself is RO.** Pod delete is insufficient because the fresh pod bind-mounts the same RO device. Cross-node reschedule forces the CSI driver to do a fresh attach on a different node:

```bash
# Cordon the affected node
kubectl cordon <node>

# Delete the affected pods (they'll reschedule elsewhere)
kubectl delete pod -n <ns> <pod>

# Wait for fresh pod to be Running on a new node
kubectl get pod -n <ns> <pod> -o wide

# Uncordon — the RO globalmount on the original node is now detached and clean
kubectl uncordon <node>
```

**Verify.**

```bash
# Mount state across all CSI mounts
PROM=prometheus-kube-prometheus-stack-prometheus-0
kubectl -n default exec $PROM -c prometheus -- \
  wget -qO- "http://localhost:9090/api/v1/query?query=count(pvc_mount_readonly==1)" \
  | python3 -c "import json,sys;r=json.load(sys.stdin)['data']['result'];print('RO mounts:',r[0]['value'][1] if r else 0)"
# Expect: RO mounts: 0
```

**Pitfall.** If multiple pods on the same node are affected, they likely share the same root cause (often the iSCSI session itself went unhealthy). Doing the cross-node reschedule for one pod doesn't fix the others. Cordon + delete the entire affected workload set in one pass.

**See also.** [PVC RO Mount Auto-Remediation](../storage/pvc-ro-automation.md) — the full automation guide, including the lessons from a 16-day silent outage that motivated the monitor-direct architecture.

---

## Certificate renewal — manual trigger

**Symptoms.** `SSLCertificateExpiresIn30Days` warning fired; cert-manager hasn't renewed automatically.

**Diagnose.**

```bash
# Find the cert and its order
kubectl get certificate -A | grep <hostname>
kubectl describe certificate <name> -n <ns> | tail -30

# Look at the order/challenge state
kubectl get challenges,orders -A | head
```

**Resolve.**

```bash
# 1. Force re-issuance by deleting the Certificate's secret
kubectl delete secret <cert-secret-name> -n <ns>
# cert-manager will create a new Order automatically

# 2. Or annotate to trigger renewal
kubectl annotate certificate <name> -n <ns> \
  cert-manager.io/issue-temporary-certificate-now=true --overwrite

# 3. Watch progress
kubectl get challenges -n <ns> -w
```

**Verify.**

```bash
kubectl get certificate <name> -n <ns> -o jsonpath='{.status.notAfter}{"\n"}'
# Should show a date 60-90 days out
```

**Pitfall.** Let's Encrypt rate limits to 5 failed validations/account/hostname/hour. Don't force renewal in a loop while debugging — fix the underlying issue (often DNS-01 split-horizon, see [external-dns docs](../applications/external-dns.md)) and try once.

---

## Application manifest changes not applying

**Symptoms.** Merged a PR touching `manifests/applications/<app>.yaml` (an ArgoCD `Application` CRD); changes don't appear in cluster.

**Cause.** ArgoCD does **not** self-manage `Application` CRs by default. The repo's CLAUDE.md documents this; the fix is one command.

**Resolve.**

```bash
kubectl apply -f manifests/applications/<app>.yaml
```

**Verify.** Spec change visible:

```bash
kubectl get application <app> -n argocd -o jsonpath='{.spec}{"\n"}'
```

---

## Falco WebUI not showing events

**Symptoms.** Falco DaemonSet is generating events (per `kubectl logs`) but the WebUI at `falco.k8s.n37.ca` is silent.

**Cause.** Falco's WebUI builds its RediSearch index on startup. If Falco's Redis pod restarted independently after the WebUI started, the index was wiped and the WebUI logs `exceeding post rate limit (500)` on every POST to `/events`.

**Resolve.**

```bash
kubectl rollout restart deployment/falco-falcosidekick-ui -n falco
```

The WebUI logs "Index does not exist → Create Index" on startup and resumes accepting events.

**Verify.** New events appear within ~30s. WebUI logs show `WebUI - POST OK (200)`.

---

## Stuck Renovate PR / dependency dashboard

**Symptoms.** Renovate's dependency dashboard issue is stale, or PRs are stuck in `awaiting-schedule` past the weekend.

**Resolve.**

```bash
# Comment on the Dependency Dashboard issue to force a re-run
gh issue comment <dashboard-issue> --body "@renovate-bot rebase"

# For an individual PR
gh pr comment <pr> --body "@renovate-bot rebase"
```

Renovate runs on a webhook + cron schedule; force-rebase typically triggers within 5 minutes.

Use the `/renovate-apply` skill for the full triage workflow.

---

## Cluster shutdown / startup

Use the `/cluster-shutdown` skill — it handles the safe sequence (drain → stop workloads → power off nodes → power off NAS). Reverse for startup.

The order matters: Synology NAS must be **up** before nodes boot, otherwise iSCSI sessions don't come back cleanly and Loki/Prometheus/Grafana PVCs need a manual `kubectl delete pod` to remount RW.

## Related

- **[Disaster Recovery](./disaster-recovery.md)** — when a runbook isn't enough (node loss, control plane failure, full restore)
- **[ArgoCD](../applications/argocd.md)** — multi-source patterns, sync waves
- **[Velero](../applications/velero.md)** — backup schedules + restore command reference
- **[Network Policies](../security/network-policies.md)** — when NetPol is the actual blocker
