---
sidebar_position: 3
title: "SLOs and Error Budgets"
description: "Multi-window multi-burn-rate Service Level Objective monitoring for critical cluster services — recording rules, alerting strategy, and runbook"
---

# SLOs and Error Budgets

Service Level Objectives (SLOs) are quantitative reliability targets for the cluster's critical services. The homelab's SLO framework lives in Prometheus and follows the [Google SRE Workbook multi-window multi-burn-rate](https://sre.google/workbook/alerting-on-slos/) pattern.

## Goals

- **Detect real degradation fast** without flapping on transient blips.
- **Track error budget** over a rolling 30-day window so the cluster has a defensible reliability number, not just "feels slow today."
- **Keep probe semantics honest** — don't conflate connectivity with cert validity, don't measure things blocked by NetworkPolicy.

## Targets

| Service | Path | Probe URL | SLO |
|---------|------|-----------|------|
| ArgoCD | ingress | `https://argocd.k8s.n37.ca` | 99.5% / 30d |
| Grafana | ingress | `https://grafana.k8s.n37.ca` | 99.5% / 30d |
| Argo Workflows | backend | `http://argo-workflows-server.argo-workflows:2746/` | 99.5% / 30d |
| Zot Registry | backend | `http://zot.zot:5000/v2/` | 99.5% / 30d |
| Lifeonabike | backend | `http://web.lifeonabike:80/` | 99.5% / 30d |

**Error budget at 99.5% / 30d**: 3h 36m of downtime allowed per month.

### Two probe jobs

Probes are split into two Prometheus scrape jobs so the SLI signal is honest:

| Job | Module | What it measures |
|---|---|---|
| `blackbox-availability` | `https_2xx` | End-to-end via ingress-nginx (DNS → MetalLB → ingress → backend). `slo_path: "ingress"` |
| `blackbox-availability-internal` | `http_2xx` | Backend Service ClusterIP only (no ingress). `slo_path: "backend"` |

Both set `slo_target: "0.995"`. The SLI recording rule selects on `slo_target!=""` so new targets join the SLO automatically when labelled.

#### Why two jobs?

Some services can't be probed end-to-end:

- **Argo Workflows** sits behind oauth2-proxy. A `https_2xx` probe follows the 302 redirect to `oauth.k8s.n37.ca`, which resolves to MetalLB VIP `10.0.10.10`, which fails because kube-proxy's `KUBE-EXT` chain only DNATs LoadBalancer VIPs for `src-type LOCAL` traffic (see [pod-to-MetalLB hairpin](../networking/coredns.md#public-service-through-split-horizon-argocdk8sn37ca)).
- **Zot Registry** has L7 routing quirks for `/v2/` from the cluster side.
- **Lifeonabike** resolves internally via split-horizon DNS to the same MetalLB VIP — same hairpin.

For these, the backend Service ClusterIP probe is the next best thing. Combined with the external ingress probes for ArgoCD and Grafana, the two-job set still gives meaningful availability data — and the [Uptime Kuma](../applications/uptime-kuma.md) status page covers the true end-to-end external view.

## Recording rules

The SLI is `probe_success` (0 or 1 gauge from blackbox-exporter) averaged over a rolling window. The PrometheusRule lives at `manifests/base/kube-prometheus-stack/slo-alerts.yaml`.

```yaml
- record: sli:probe_success:ratio_rate_5m
  expr: avg_over_time(probe_success{slo_target!=""}[5m])
- record: sli:probe_success:ratio_rate_30m
  expr: avg_over_time(probe_success{slo_target!=""}[30m])
- record: sli:probe_success:ratio_rate_1h
  expr: avg_over_time(probe_success{slo_target!=""}[1h])
- record: sli:probe_success:ratio_rate_6h
  expr: avg_over_time(probe_success{slo_target!=""}[6h])
- record: sli:probe_success:ratio_rate_30d
  expr: avg_over_time(probe_success{slo_target!=""}[30d])

- record: slo:error_budget_consumed:ratio_30d
  expr: clamp_max((1 - sli:probe_success:ratio_rate_30d) / 0.005, 1)
```

The five windows are inputs to multi-window burn alerts. The budget recording rule is for dashboards — values close to 1 mean "budget about to run out."

## Burn-rate alerts

A burn rate is "how many times faster than sustainable are we eating budget?" Burn rate of 1x = exhausting the entire 30d budget exactly at day 30. 14.4x = exhausting it in ~2 days.

Three alert tiers, all at `warning` severity for now (promote to `critical` after the thresholds settle):

### Fast burn (page-grade signal)

- **Trigger**: 14.4x burn rate sustained on BOTH the 1h AND 5m windows for 2 minutes.
- **Threshold for 99.5% SLO**: `(1 - 0.995) * 14.4 = 0.072` — 7.2% of probes failing.
- **Why two windows**: the long window confirms it's real; the short window confirms it's still happening NOW. AND'ing both kills false positives from a transient 5-minute outage.

```yaml
- alert: SLOFastBurnRate
  expr: |
    (1 - sli:probe_success:ratio_rate_1h) > (14.4 * 0.005)
    and
    (1 - sli:probe_success:ratio_rate_5m) > (14.4 * 0.005)
  for: 2m
  labels:
    severity: warning
    slo_burn: fast
```

### Slow burn (ticket-grade signal)

- **Trigger**: 6x burn rate sustained on BOTH the 6h AND 30m windows for 15 minutes.
- **Threshold for 99.5% SLO**: `(1 - 0.995) * 6 = 0.03` — 3% of probes failing.
- **Use case**: catches a slow, persistent leak (sporadic 500s, degraded backend, slow upstream).

```yaml
- alert: SLOSlowBurnRate
  expr: |
    (1 - sli:probe_success:ratio_rate_6h) > (6 * 0.005)
    and
    (1 - sli:probe_success:ratio_rate_30m) > (6 * 0.005)
  for: 15m
```

### Budget exhausted

- **Trigger**: 30d availability has already dropped below 99.5%.
- **Action**: no new risky changes until the SLI recovers. Stabilize first.

```yaml
- alert: SLOErrorBudgetExhausted
  expr: sli:probe_success:ratio_rate_30d < 0.995
  for: 30m
```

## Operational queries

```promql
# Current state of all SLO probes
probe_success{slo_target!=""}

# Per-service availability over the last 30 days
sli:probe_success:ratio_rate_30d

# How much of the monthly error budget is consumed?
slo:error_budget_consumed:ratio_30d

# Current burn rate (multiples of sustainable)
(1 - sli:probe_success:ratio_rate_1h) / 0.005

# Only backend (ClusterIP) probes
probe_success{slo_path="backend"}

# Only ingress (end-to-end) probes
probe_success{slo_path="ingress"}
```

## Adding a new SLO target

1. Pick a probe URL the blackbox-exporter pod can actually reach. From `default` namespace:
   - **Internal HTTP** (preferred): ClusterIP Service URL like `http://<svc>.<ns>:<port>/`. Works for any service in any namespace, subject to NetworkPolicy.
   - **External HTTPS via ingress**: works only if (a) the ingress is TLS-passthrough OR (b) the backend ingress returns 2xx without a redirect chain that crosses a non-meshed pod hop.

2. Decide on the right module:
   - `https_2xx` for external HTTPS (rejects non-2xx, validates cert).
   - `http_2xx` for internal HTTP via ClusterIP.

3. Add the target to `manifests/base/kube-prometheus-stack/values.yaml`:

   ```yaml
   - job_name: 'blackbox-availability-internal'
     ...
     static_configs:
       - targets:
           - http://<svc>.<ns>:<port>/
         labels:
           slo_target: "0.995"
           slo_path: "backend"
   ```

4. Check NetworkPolicies — both directions:
   - **Destination ns**: must allow inbound from `app=blackbox-exporter` in `default` ns on the application port. If both source and destination namespaces are ambient-meshed, the bare HBONE rule on port 15008 handles this (zot is NOT meshed and needed an explicit rule; argo-workflows IS meshed and didn't).
   - **Source ns (default)**: must allow outbound to the destination port. The default-ns egress only allows specific ports — port 5000 needed an explicit add for Zot.

5. After merge, hard-refresh ArgoCD on `kube-prometheus-stack` if the new scrape job doesn't show up within a few minutes:

   ```bash
   kubectl annotate application kube-prometheus-stack -n argocd \
     argocd.argoproj.io/refresh=hard --overwrite
   ```

## Troubleshooting

### Probe reports `probe_http_status_code=0`

The probe never got a response. Almost always one of:

- **Connection timeout (5s default)**. Check NetworkPolicy on both source AND destination. Run `wget --timeout=8 -qO- <url>` from inside the blackbox-exporter pod to compare.
- **Redirect chain hits the MetalLB VIP hairpin**. The probe followed a 302 to an internal hostname that resolves to `10.0.10.10`, which is unreachable from non-mesh-meshed pods. Switch to a direct ClusterIP probe target.

### Probe reports `probe_success=0` with a real status code

Module mismatch:

- `https_2xx` requires a 2xx. A 302/401/redirect returns the actual status but `probe_success=0`. Either switch the module (e.g., `http_2xx` accepts any 2xx; you can extend `valid_status_codes` to include 302) or probe a path that doesn't require auth.

### Fast burn alert fires repeatedly with no actual outage

Probe is flaky. Check:

- Probe duration consistently near the 5s timeout? Backend is slow but technically up. Tune the module timeout or pick a faster endpoint.
- Probe alternates 0/1? Network jitter — but verify with `probe_dns_lookup_time_seconds` and `probe_duration_seconds{phase="connect"}`.

### `sli:probe_success:ratio_rate_30d` is `NaN`

The recording rule needs at least 30 days of data. For new targets, expect `NaN` or partial values for the first month.

## Related

- **[Blackbox Exporter](../applications/blackbox-exporter.md)** — the prober itself, probe modules, target list
- **[Kube Prometheus Stack](../applications/kube-prometheus-stack.md)** — where the recording rules and alerts live
- **[Uptime Kuma](../applications/uptime-kuma.md)** — true end-to-end status page (independent of Prometheus)
- **[Network Policies](../security/network-policies.md)** — NetworkPolicy is the most common cause of broken probes
