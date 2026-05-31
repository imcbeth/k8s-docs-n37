---
sidebar_position: 24
title: "Kafka (Strimzi)"
description: "Apache Kafka cluster managed by the Strimzi operator"
---

# Kafka (Strimzi)

Apache Kafka message broker deployed on Kubernetes via the Strimzi operator, used as the streaming backbone for the Flink demo pipeline.

## Overview

| Property | Value |
|----------|-------|
| **Namespace** | `kafka` |
| **Operator namespace** | `strimzi-system` |
| **Kafka version** | 4.1.2 (KRaft mode, no ZooKeeper) |
| **Strimzi chart** | 1.0.0 |
| **ArgoCD App** | `kafka` (project: `infrastructure`) |
| **Istio Mesh** | Enabled (Ambient mode) |

## Architecture

Strimzi manages the full Kafka lifecycle via Kubernetes CRDs. This cluster runs in **KRaft mode** (Kafka Raft metadata), eliminating the ZooKeeper dependency introduced in older Kafka versions.

```
strimzi-system/
  strimzi-cluster-operator  → watches Kafka, KafkaTopic, KafkaUser CRDs
kafka/
  kafka-cluster-combined-0  → KRaft combined (broker + controller) node
  kafka-cluster-entity-operator → topic-operator only
```

The `combined` node type runs broker and controller roles in a single pod — appropriate for a single-node homelab cluster.

## Configuration

**Manifests location:** `manifests/base/kafka/`

Key Kafka CR settings:

```yaml
apiVersion: kafka.strimzi.io/v1beta2
kind: Kafka
metadata:
  name: kafka-cluster
  namespace: kafka
spec:
  kafka:
    version: 4.1.2
    replicas: 1
    listeners:
      - name: plain
        port: 9092
        type: internal
        tls: false
    config:
      offsets.topic.replication.factor: 1
      transaction.state.log.replication.factor: 1
      transaction.state.log.min.isr: 1
      default.replication.factor: 1
      min.insync.replicas: 1
  entityOperator:
    topicOperator: {}
    # userOperator omitted — ARM64 JVM takes ~35s to init, liveness probe kills it
    # at ~30s (initialDelaySeconds=10, failureThreshold=3). Not needed for demo.
```

## Topics

The demo pipeline uses one topic, created via a `KafkaTopic` CR:

```yaml
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: flink-events
  namespace: kafka
  labels:
    strimzi.io/cluster: kafka-cluster
spec:
  partitions: 1
  replicas: 1
```

## Connecting to Kafka

### Bootstrap address (in-cluster)

```
kafka-cluster-kafka-bootstrap.kafka.svc.cluster.local:9092
```

### Inspect topics

```bash
# List topics
kubectl exec -n kafka kafka-cluster-combined-0 -- \
  bin/kafka-topics.sh --bootstrap-server localhost:9092 --list

# Describe a topic
kubectl exec -n kafka kafka-cluster-combined-0 -- \
  bin/kafka-topics.sh --bootstrap-server localhost:9092 \
  --describe --topic flink-events

# Consume from beginning
kubectl exec -n kafka kafka-cluster-combined-0 -- \
  bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic flink-events --from-beginning --max-messages 5
```

### Check consumer group lag

```bash
kubectl exec -n kafka kafka-cluster-combined-0 -- \
  bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --all-groups
```

## Network Policy

Four port ranges need to be open between namespaces:

| Port | Protocol | Purpose |
|------|----------|---------|
| 9092 | PLAINTEXT | Client connections |
| 9091 | REPLICATION | Internal Strimzi AdminClient (entity-operator → broker) |
| 9090 | CONTROLPLANE | KRaft controller discovery (`CONTROLPLANE-9090://...` metadata) |
| 15008 | HBONE | Istio Ambient mesh tunnel (bare egress, no `to` selector) |

:::note KRaft CONTROLPLANE port
Strimzi's AdminClient calls `describeMetadataQuorum` which connects to the bootstrap port (9092), discovers the KRaft controller endpoint (`CONTROLPLANE-9090://...`) from the metadata response, then opens a second connection to port 9090. Both ports must be open from `strimzi-system` → `kafka`.
:::

## Troubleshooting

### Cluster not READY

```bash
# Check Kafka CR status
kubectl get kafka -n kafka kafka-cluster -o jsonpath='{.status.conditions}' | jq .

# Check operator logs
kubectl logs -n strimzi-system -l name=strimzi-cluster-operator --tail=50
```

### entity-operator crashing

```bash
kubectl logs -n kafka -l app.kubernetes.io/name=entity-operator -c topic-operator --tail=50
```

The user-operator is intentionally omitted — on ARM64, the JVM startup takes ~35 seconds but the liveness probe kills the container at ~30 seconds (`initialDelaySeconds=10`, `failureThreshold=3`, `periodSeconds=10`). There is no `startupProbe` field available in `spec.entityOperator.template.userOperatorContainer` in Strimzi 1.0.0.

### Topic not appearing

```bash
kubectl get kafkatopic -n kafka
kubectl describe kafkatopic flink-events -n kafka
```

The topic-operator watches for `KafkaTopic` CRDs with label `strimzi.io/cluster: kafka-cluster`. Without that label, the topic is ignored.

## Gotchas

- **Strimzi 1.0.0 requires Kafka 4.x**: Earlier versions (3.x) are not supported. KRaft mode is mandatory.
- **entity-operator bootstrap uses port 9091**: The internal `REPLICATION` listener, not port 9092. NetworkPolicies from `strimzi-system` must allow egress to `kafka` on 9091 in addition to 9092.
- **KRaft CONTROLPLANE port 9090**: The `describeMetadataQuorum` call follows the controller endpoint from Kafka metadata. This second connection goes to port 9090 — must be open from `strimzi-system` → `kafka`.
- **user-operator liveness probe kills ARM64 JVM**: JVM on ARM64 needs ~35s to start; probe fires at 30s. Remove `userOperator` from `entityOperator` unless KafkaUser CRDs are actually needed.

## References

- [Strimzi Documentation](https://strimzi.io/docs/)
- [Kafka KRaft Mode](https://kafka.apache.org/documentation/#kraft)

---

**Last Updated:** 2026-05-31
