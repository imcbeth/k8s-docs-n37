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
| **Flink version** | 1.20 |
| **Operator chart** | flink-operator (community) |
| **ArgoCD Apps** | `flink-operator`, `flink-demo` |
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

## Custom Docker Image

The demo uses a custom image built on `apache/flink:1.20-scala_2.12` with PyFlink and the Kafka connector:

**Location:** `manifests/base/flink-demo/docker/`
**Image:** `registry.k8s.n37.ca/flink-demo:1.0.0`

Key additions over the base image:

- `apache-flink[cython]` (PyFlink) — requires `openjdk-17-jdk-headless`, `build-essential`, `python3-dev` to compile `pemja` C extension
- `flink-sql-connector-kafka-3.3.0-1.20.jar` at `/opt/flink/lib/`
- `boto3` for S3 writes
- `sales-data.csv` baked into the image at `/opt/flink/data/`

### Building and pushing

```bash
# Start colima (ARM64 Docker daemon on macOS)
colima start --arch aarch64

# Build and push
cd manifests/base/flink-demo/docker/
DOCKER_HOST=unix://$HOME/.colima/default/docker.sock \
  bash build-and-push.sh

colima stop
```

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

## Gotchas

- **flink-webhook needs ≥256Mi**: TLS crypto during webhook calls is memory-intensive. 128Mi causes OOMKill → EOF → FlinkDeployments fail to create.
- **PyFlink `from_collection()` type safety**: Always pass `type_info=Types.STRING()` (or the appropriate type). Without it, Kryo serialization converts Python strings to Java `[B` byte arrays, breaking any Java-side String sink.
- **FAILED FlinkDeployment is terminal**: The operator will not restart a FAILED job on ConfigMap change. Delete the JobManager pod to force a fresh start.
- **Application mode entrypoint**: `env.execute()` in Application mode returns immediately after job submission (detached). Log messages after `execute()` fire before job completion — Kafka may still be empty at that point.
- **pemja C extension build**: `apache-flink[cython]` requires `openjdk-17-jdk-headless`, `build-essential`, `python3-dev`, and a symlink from `/usr/lib/jvm/java-17-openjdk-arm64/include/linux/jni_md.h` → `/usr/lib/jvm/java-17-openjdk-arm64/include/jni_md.h` for the C extension to compile.

## References

- [Apache Flink Documentation](https://flink.apache.org/docs/)
- [Flink Kubernetes Operator](https://nightlies.apache.org/flink/flink-kubernetes-operator-docs-main/)
- [PyFlink API](https://nightlies.apache.org/flink/flink-docs-master/api/python/)

---

**Last Updated:** 2026-05-31
