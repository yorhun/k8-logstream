# Log Stream Analyzer Demo

A log stream pipeline on Kubernetes. A generator pod publishes a mock log stream via Redis Streams; horizontally autoscaling pods index the data into OpenSearch for visualization in OpenSearch Dashboards.

<video src="https://github.com/user-attachments/assets/dc24b21a-51f5-489c-82f4-fae3dfd2c3f5"></video>

## Prerequisites

| Tool | Purpose |
|------|---------|
| [OrbStack](https://orbstack.dev) with K8s enabled | Local cluster |
| `helm` v3+ | Bitnami + OpenSearch charts |
| `docker` | Build service images |
| `kubectl` | Apply manifests |

## Quickstart

### Setup

```bash
# 1. Enable OrbStack Kubernetes (OrbStack app → Settings → Kubernetes → Enable)
#    Then confirm:
kubectl config current-context   # should print: orbstack

# 2. Add Helm repos (one-time)
make helm-repos

# 3. Deploy Redis
make deploy-infra

# 4. Build the Python service images locally
#    (OrbStack shares Docker daemon — no registry push needed)
make build
```

### Configuration

Before deploying, set a password for the local OpenSearch admin account.
Replace `CHANGE_ME` in these three files with the same password value:

| File | Key |
|------|-----|
| `k8s/monitoring/opensearch-values.yaml` | `OPENSEARCH_INITIAL_ADMIN_PASSWORD` |
| `k8s/monitoring/opensearch-dashboards-values.yaml` | `opensearch.password` |
| `k8s/log-processor/secret.yaml.example` | `OPENSEARCH_URL` (embedded in the URL) -> Rename as `secret.yaml` |

### Deploy

```bash
# 1. Deploy K8s manifests for generator + processor
make deploy-services

# 2. Deploy OpenSearch + OpenSearch Dashboards
#    OpenSearch takes ~60s to become healthy on first start
make deploy-monitoring

# 3. Port-forward Dashboards to localhost
make port-forward
# OpenSearch Dashboards → http://localhost:5601
```



## Verification

```bash
# All pods Running?
kubectl get pods -n logstream

# Messages accumulating in the stream?
kubectl exec -n logstream redis-master-0 -- redis-cli XLEN logs:raw

# Dedup set growing?
kubectl exec -n logstream redis-master-0 -- redis-cli SCARD logs:processed

# HPA status
kubectl get hpa -n logstream -w
```

## Importing the Dashboard

Once `http://localhost:5601` is open:

   **Import saved objects** — Stack Management → Saved Objects → Import  
   File: `k8s/monitoring/dashboards/logstream-opensearch.ndjson`  
   Choose *Automatically overwrite conflicts* if re-importing.

The **Logstream** dashboard then appears under Dashboards with these panels:

| Panel | What it shows |
|-------|--------------|
| Log Explorer | Full-text search across `message`, `trace_id`, any field |
| Log Volume over Time | Documents/min — traffic spikes visible instantly |
| Level Distribution | DEBUG/INFO/WARNING/ERROR/CRITICAL pie |
| Top Services by Volume | Which `service` values generate the most logs |
| Top Error Messages | Recurring ERROR/CRITICAL messages ranked by frequency |
| Active Processor Pod Count | Number of Pods (Autoscaling Processor Pods) |
| Processed Messages | Count of processed messages |

## Improvement Ideas

- Add TTL to processed logs set
- Use event-driven autoscaling instead of CPU-based
- Add a dead-letter queue for messages that fail to index
