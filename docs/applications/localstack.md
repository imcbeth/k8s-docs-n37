---
sidebar_position: 18
title: "LocalStack"
description: "Local AWS cloud stack for development and testing"
---

# LocalStack

LocalStack provides a local AWS cloud stack for development and testing purposes.

## Overview

| Property | Value |
|----------|-------|
| **Namespace** | `localstack` |
| **Source** | Git repository (custom manifests) |
| **ArgoCD App** | `localstack` |
| **UI URL** | `https://localstack.k8s.n37.ca` |
| **Istio Mesh** | Enabled (Ambient mode) |

## Purpose

LocalStack is used in the homelab for:

1. **Velero Testing** - Test backup/restore workflows with S3-compatible storage before production
2. **AWS SDK Development** - Develop and test AWS SDK integrations locally
3. **CI/CD Testing** - Validate infrastructure-as-code without cloud costs

## Available Services

LocalStack Community Edition provides:

- **S3** - Object storage (primary use case for Velero testing)
- **SQS** - Message queues
- **SNS** - Pub/sub notifications
- **Lambda** - Serverless functions
- **DynamoDB** - NoSQL database
- **CloudWatch** - Monitoring (logs)

## Configuration

**Manifests Location:** `manifests/base/localstack/`

```yaml
# Key configuration
apiVersion: v1
kind: Service
metadata:
  name: localstack
  namespace: localstack
spec:
  ports:
    - port: 4566
      name: edge
      targetPort: 4566
    - port: 4510
      name: external-services
      targetPort: 4510
```

## Accessing LocalStack

### From Within Cluster

```bash
# S3 endpoint
http://localstack.localstack.svc.cluster.local:4566

# Example: List S3 buckets
aws --endpoint-url=http://localstack.localstack:4566 s3 ls
```

### From Outside Cluster

```bash
# Via ingress
https://localstack.k8s.n37.ca

# Example with AWS CLI
aws --endpoint-url=https://localstack.k8s.n37.ca s3 ls
```

## Integration with Velero

LocalStack was used during Velero development for testing backup workflows:

```yaml
# Velero BackupStorageLocation for LocalStack testing
apiVersion: velero.io/v1
kind: BackupStorageLocation
metadata:
  name: localstack
  namespace: velero
spec:
  provider: aws
  bucket: velero-backups
  config:
    region: us-east-1
    s3ForcePathStyle: "true"
    s3Url: http://localstack.localstack:4566
```

:::note Production Migration
Velero has been migrated to Backblaze B2 for production backups. LocalStack remains available for testing and development workflows.
:::

## Resource Usage

| Component | CPU Request | CPU Limit | Memory Request | Memory Limit |
|-----------|-------------|-----------|----------------|--------------|
| localstack | 100m | 500m | 256Mi | 1Gi |

## Troubleshooting

### Service Not Responding

```bash
# Check pod status
kubectl get pods -n localstack

# Check logs
kubectl logs -n localstack -l app=localstack

# Test connectivity
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -- \
  curl -s http://localstack.localstack:4566/_localstack/health
```

### S3 Operations Failing

```bash
# Verify S3 is enabled
curl http://localstack.localstack:4566/_localstack/health | jq '.services.s3'

# Create test bucket
aws --endpoint-url=http://localstack.localstack:4566 s3 mb s3://test-bucket
```

## References

- [LocalStack Documentation](https://docs.localstack.cloud/)
- [AWS CLI with LocalStack](https://docs.localstack.cloud/user-guide/integrations/aws-cli/)

---

**Last Updated:** 2026-01-30
