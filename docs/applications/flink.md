---
sidebar_position: 25
title: "Apache Flink"
description: "Stateful stream processing with the Flink operator and a file→Kafka→S3 demo pipeline"
---

# Apache Flink

Apache Flink stateful stream processing platform, managed by the Flink Kubernetes Operator, with a complete end-to-end demo pipeline: CSV file → Kafka → LocalStack S3.

## Overview

| Property | Value |
|----------|-------|
| **Operator namespace** | `flink-operator` |
| **Jobs namespace** | `flink-demo` |
| **Operator version** | 1.16.1 (image, pinned in `values.yaml`; Helm chart 1.15.0). Accepts `flinkVersion` up to `v2_2` |
| **Flink runtime** | **2.2.1** (image `flink-demo:2.0.0`, `flinkVersion: v2_2`, since 2026-11-21); Java: Temurin 17.0.21 |
| **ArgoCD Apps** | `flink-operator`, `flink-demo` |
| **Flink UI** | [https://flink.k8s.n37.ca](https://flink.k8s.n37.ca) (GitHub SSO; routes to the kafka-to-s3 JobManager, the long-running job) |
| **Istio Mesh** | Enabled (Ambient mode) |

## Architecture

```
flink-operator/
  flink-kubernetes-operator  → watches FlinkDeployment CRDs
  flink-webhook              → admission webhook (needs ≥256Mi — TLS crypto is memory-intensive)

flink-demo/
  file-to-kafka              → batch job: reads CSV, publishes to Kafka (FINISHED when done)
  kafka-to-s3                → streaming job: consumes Kafka, writes to LocalStack S3 (RUNNING)
  localstack-flink-setup     → PreSync hook: creates s3://flink-output bucket
```

Jobs run in **Application mode** (kubernetes-application): each `FlinkDeployment` spins up a dedicated JobManager + TaskManager pod. The Python script is the entrypoint; it calls `env.execute()` to submit the job graph.

## Demo Pipeline

### file-to-kafka (batch)

Reads `sales-data.csv` (15 records) from a ConfigMap-mounted file and publishes each row as a JSON event to Kafka topic `flink-events`.

**Script:** `manifests/base/flink-demo/docker/pipeline_file_to_kafka.py`
**ConfigMap:** `manifests/base/flink-demo/pipeline-file-to-kafka-configmap.yaml`

```python
# Critical: always pass type_info=Types.STRING() to from_collection().
# Without it, PyFlink uses Kryo serialization which converts Python strings
# to Java byte arrays ([B). SimpleStringSchema then throws ClassCastException.
stream = env.from_collection(records, type_info=Types.STRING())
```

### kafka-to-s3 (streaming)

Consumes from `flink-events` topic and writes each message as an individual JSON file to `s3://flink-output/events/{YYYY}/{MM}/{DD}/{HH}/{uuid}.json` via boto3 + LocalStack.

**Script:** `manifests/base/flink-demo/docker/pipeline_kafka_to_s3.py`

The S3 write uses a `MapFunction` wrapping `boto3.client("s3").put_object()`, not a native Flink connector. Output stream is printed to stdout (Flink labels the task "Sink: Print to Std. Out").

### Data flow

```
sales-data.csv (ConfigMap)
  → file-to-kafka (PyFlink batch)
    → Kafka topic: flink-events
      → kafka-to-s3 (PyFlink streaming)
        → LocalStack S3: s3://flink-output/events/YYYY/MM/DD/HH/uuid.json
```

## Flink UI

The Flink web UI for the `file-to-kafka` JobManager is accessible at:

**[https://flink.k8s.n37.ca](https://flink.k8s.n37.ca)** — protected by GitHub SSO (oauth2-proxy)

The UI shows job graphs, task metrics, checkpoints, and logs for the `file-to-kafka` deployment. Since `file-to-kafka` is a batch job it will show `FINISHED` — this is the expected terminal state.

To access the `kafka-to-s3` UI (streaming job), use a port-forward:

```bash
kubectl port-forward svc/kafka-to-s3-rest -n flink-demo 8082:8081
# Then open http://localhost:8082
```

## Submitting a Job

### GitOps way (recommended) — new FlinkDeployment

Add a new `FlinkDeployment` manifest under `manifests/base/flink-demo/` and reference it in `kustomization.yaml`. The operator picks it up automatically when ArgoCD syncs.

Minimal example:

```yaml
apiVersion: flink.apache.org/v1beta1
kind: FlinkDeployment
metadata:
  name: my-job
  namespace: flink-demo
spec:
  image: registry.k8s.n37.ca/flink-demo:2.0.0
  flinkVersion: v2_2
  flinkConfiguration:
    taskmanager.numberOfTaskSlots: "1"
  serviceAccount: flink
  jobManager:
    resource:
      memory: "1Gi"
      cpu: 0.5
  taskManager:
    resource:
      memory: "1Gi"
      cpu: 0.5
  job:
    jarURI: local:///opt/flink/usrlib/my_job.py
    entryClass: ""        # leave blank for Python jobs
    parallelism: 1
    upgradeMode: stateless
```

Key settings for Python jobs:

- `jarURI` uses `local://` (file already in the Docker image) or a remote URI
- `flinkVersion` must match the image runtime — `v2_2` for the current `flink-demo:2.0.0` image. Change both in the same commit
- `memory: "1Gi"` minimum — see Memory Configuration below

### Replaying the batch job (file-to-kafka)

`file-to-kafka` is a batch job that finishes (`FINISHED/STABLE`) after publishing the 15 CSV records. To replay it:

```bash
# Delete the JobManager pod — the Deployment controller recreates it
# and the job runs again from scratch
kubectl delete pod -n flink-demo -l component=jobmanager,app=file-to-kafka
```

The job will re-publish all 15 records to Kafka. `kafka-to-s3` will pick them up and write new S3 files (the existing files are not deduplicated).

### Via the REST API

The Flink REST API is available on port 8081 of each JobManager's service. Use it to inspect or cancel jobs without touching git.

```bash
# List jobs on file-to-kafka
kubectl exec -n flink-demo deploy/file-to-kafka -- \
  curl -s http://localhost:8081/jobs | python3 -m json.tool

# Or via port-forward
kubectl port-forward svc/file-to-kafka-rest -n flink-demo 8081:8081
curl http://localhost:8081/jobs
curl http://localhost:8081/jobs/overview

# Cancel a running job (kafka-to-s3 example)
kubectl port-forward svc/kafka-to-s3-rest -n flink-demo 8082:8081
JOB_ID=$(curl -s http://localhost:8082/jobs | python3 -c \
  "import json,sys; print(json.load(sys.stdin)['jobs'][0]['id'])")
curl -X PATCH http://localhost:8082/jobs/$JOB_ID?mode=cancel
```

:::note Application mode and job submission
In Application mode each `FlinkDeployment` runs exactly one job — the one baked into the image or referenced by `jarURI`. The REST API and UI are for monitoring and cancellation, not for submitting additional jobs to an existing deployment. To run a new job, create a new `FlinkDeployment`.
:::

## Custom Docker Image

**Location:** `manifests/base/flink-demo/docker/Dockerfile` (homelab repo)
**Image:** `registry.k8s.n37.ca/flink-demo:2.0.0`

| Layer | Version |
|---|---|
| Base | `apache/flink:2.2.1-java17` (Ubuntu 24.04) |
| JDK | Temurin 17.0.21 (`eclipse-temurin:17.0.21_9-jdk-noble`, copied over `/opt/java/openjdk`; the base image ships 17.0.19) |
| PyFlink | `apache-flink==2.2.1`, built from source (no linux/aarch64 wheel); `pyarrow` pinned `>=14.0.1,<17` (resolves 16.1.0) |
| Kafka connector | `flink-sql-connector-kafka-5.0.0-2.2.jar` in `/opt/flink/lib/` |
| Other | `boto3` for the S3 writes |

The pipeline scripts and `sales-data.csv` are **not** in the image: they are mounted from ConfigMaps
(`flink-pipeline-*`, `flink-test-data`). The `docker/*.py` copies in the repo are not what runs.

### Building: in the cluster, scanned before it is tagged

The image is built by the Argo Workflows template **`flink-demo-build`** (Kaniko on the arm64 nodes),
which replaced the laptop `build-and-push.sh` on 2026-11-21:

```bash
argo submit --from workflowtemplate/flink-demo-build -n argo-workflows -p version=<new-version> --watch
```

Steps: clone the homelab repo → Kaniko pushes `flink-demo:<git-sha>` → the shared **image-gate** scan
(trivy against the in-cluster trivy-server; fails on any CRITICAL that has a fixed version) → `promote`
tags it `<new-version>`. Nothing restarts: deploying is a PR that changes `image:` (and `flinkVersion`
if the minor changed) in both FlinkDeployments. Pick a new version; promoting onto a tag that is
already deployed would change a running image underneath it.

Kaniko peaks around 1.3 GiB of its 2 GiB limit for this image (about 10 minutes).

:::note Why Flink 2.2 (2026-11-21)
The gate blocked a Flink 1.20 rebuild on **pyarrow 11.0.0** (CVE-2023-47248, critical, fixed in
14.0.1). PyFlink 1.20 pins `apache-beam<2.49`, which pins `pyarrow<12`, so 1.20 cannot carry the fix.
PyFlink 2.2 allows Beam up to 2.61 and so pyarrow up to 16.x. 2.2 rather than 2.3 because the
operator accepts `flinkVersion` up to `v2_2`; Renovate caps `apache/flink` below 2.3 and the JDK
below 18 for the same reason. Image findings went from 17 critical / 452 high (1.20) to
3 critical (none fixable) / 98 high.
:::

### Dockerfile gotchas

- **Flink 2.x images build as `USER flink`** (1.20 images built as root): install as `USER root`, end with `USER flink` (uid 9999, as the podTemplates run).
- **apt over HTTPS:** argo-workflows may reach the internet on 443 only, and Ubuntu's sources use `http://` (port 80). The Dockerfile rewrites `ubuntu.sources` to `https://`.
- **PEP 668:** Ubuntu 24.04's system Python is "externally managed", so pip needs `--break-system-packages`.
- **pip timeouts:** the PyFlink download is large; `--default-timeout=120 --retries 5`.

## Memory Configuration

Flink memory model minimum for `resource.memory: "1Gi"`:

| Component | Size |
|-----------|------|
| JVM Overhead (min) | 192 MB |
| JVM Metaspace | 256 MB |
| JVM Heap | 448 MB |
| Off-heap (Flink default) | 128 MB |
| **Total** | **1024 MB** |

:::warning 512m is too small
With `memory: "512m"`, JVM overhead + Metaspace consume 448 MB, leaving only 64 MB for Total Flink Memory — below the 128 MB off-heap default. The job fails with:

```
Total Flink Memory (64mb) < Off-heap Memory (128mb)
```

Minimum viable: **1Gi**.
:::

## FlinkDeployment Status

```bash
# Check job status
kubectl get flinkdeployment -n flink-demo

# Detailed status
kubectl describe flinkdeployment file-to-kafka -n flink-demo

# Job logs
kubectl logs -n flink-demo -l component=jobmanager -c flink-main-container --tail=50
```

Expected output:

```
NAME            JOB STATUS   LIFECYCLE STATE
file-to-kafka   FINISHED     STABLE
kafka-to-s3     RUNNING      STABLE
```

`FINISHED` is the correct terminal state for `file-to-kafka` (batch job). It will replay if the pod is restarted.

## Verify End-to-End Pipeline

```bash
# Check Kafka topic has records
kubectl exec -n kafka kafka-cluster-combined-0 -- \
  bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --all-groups

# Check LocalStack S3 output
kubectl exec -n localstack deploy/localstack -- \
  awslocal s3 ls s3://flink-output/events/ --recursive
```

## Troubleshooting

### FAILED job doesn't restart after ConfigMap change

The Flink operator treats `FAILED` as a terminal state — it will not restart on ConfigMap updates. To force a restart:

```bash
# Delete the JobManager pod; the Deployment controller recreates it
# with the updated ConfigMap
kubectl delete pod -n flink-demo -l component=jobmanager,app=file-to-kafka
```

### Missing operator-created ConfigMaps during startup

ConfigMaps like `flink-config-*` and `pod-template-*` are created by the operator during reconciliation, not from git. They appear within ~73 seconds of pod creation. `FailedMount` events during this window are non-fatal.

### flink-webhook OOMKill

The webhook JVM is memory-intensive during TLS operations. 128 Mi causes OOMKill → EOF on all webhook calls → FlinkDeployments cannot be created.

Minimum: `webhook.resources.limits.memory: 256Mi`

```bash
# Check webhook is running
kubectl get pods -n flink-operator

# Check for OOMKill
kubectl describe pod -n flink-operator -l app.kubernetes.io/component=webhook
```

### ClassCastException in Kafka sink

```
ClassCastException: class [B cannot be cast to class java.lang.String
```

Root cause: `env.from_collection(records)` without `type_info` → Kryo serializes Python strings as Java byte arrays → `SimpleStringSchema.serialize()` receives `[B` instead of `String`.

Fix: always pass `type_info=Types.STRING()`.

### flink.k8s.n37.ca returns 403 or 503

The host is on the [LAN gateway](./lan-gateway.md) with forward-auth. A 403 means the ext_authz check could not reach oauth2-proxy (see [oauth2-proxy troubleshooting](./oauth2-proxy.md#service-returns-403-instead-of-redirecting-to-github)). A 503 means the gateway could not reach `kafka-to-s3-rest:8081`: check the JobManager pod is running, and that flink-demo's AuthorizationPolicy still allows `sa/lan-gateway-istio` on 8081.

## Gotchas

- **PodSecurity `restricted`**: `flink-demo` enforces it (since 2026-10-29). Both podTemplates need the pod `securityContext` (runAsNonRoot, uid/gid 9999, seccomp RuntimeDefault) and the container one (no privilege escalation, drop ALL). file-to-kafka lacked them until 2026-11-21 and was refused when it was redeployed.

- **flink-webhook needs ≥256Mi**: TLS crypto during webhook calls is memory-intensive. 128Mi causes OOMKill → EOF → FlinkDeployments fail to create.
- **PyFlink `from_collection()` type safety**: Always pass `type_info=Types.STRING()` (or the appropriate type). Without it, Kryo serialization converts Python strings to Java `[B` byte arrays, breaking any Java-side String sink.
- **FAILED FlinkDeployment is terminal**: The operator will not restart a FAILED job on ConfigMap change. Delete the JobManager pod to force a fresh start.
- **Application mode entrypoint**: `env.execute()` in Application mode returns immediately after job submission (detached). Log messages after `execute()` fire before job completion — Kafka may still be empty at that point.
- **pemja C extension build**: PyFlink and pemja have no linux/aarch64 wheels and compile from source. That needs `build-essential`, `python3-dev` and a JDK's `include/` headers, which the Temurin JDK copied into `/opt/java/openjdk` provides (until 2026-11-21 this used Ubuntu's `openjdk-17-jdk-headless` plus a symlink).
- **The UI route shows kafka-to-s3 only**: `https://flink.k8s.n37.ca` (an HTTPRoute on the LAN gateway) routes to the `kafka-to-s3-rest` service, the streaming job that stays up. The batch `file-to-kafka` JobManager exits when the job finishes; while it runs, use `kubectl port-forward svc/file-to-kafka-rest -n flink-demo 8082:8081`.
- **Wrong ClusterIssuer name**: The cert-manager ClusterIssuer is `lets-encrypt-k8s-n37-ca-prod` (not `letsencrypt-prod`). Using the wrong name silently fails — Certificate stays `Ready: False` for hours.

## References

- [Apache Flink Documentation](https://flink.apache.org/docs/)
- [Flink Kubernetes Operator](https://nightlies.apache.org/flink/flink-kubernetes-operator-docs-main/)
- [PyFlink API](https://nightlies.apache.org/flink/flink-docs-master/api/python/)

---

**Last Updated:** 2026-11-16
