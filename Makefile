NAMESPACE := logstream # immediate/simple assignment

.PHONY: helm-repos deploy-infra build deploy-services deploy-monitoring port-forward teardown

## Add Bitnami and opensearch Helm repos then update
helm-repos:
	helm repo add bitnami https://charts.bitnami.com/bitnami
	helm repo add opensearch https://opensearch-project.github.io/helm-charts/
	helm repo update

## Deploy Redis into the logstream namespace via Helm
deploy-infra:
	kubectl apply -f k8s/namespace.yaml
	helm upgrade --install redis bitnami/redis \
		-n $(NAMESPACE) -f k8s/redis/values.yaml

## Build Docker images locally (OrbStack shares daemon — no push needed)
build:
	docker build -t log-generator:latest services/log-generator/
	docker build -t log-processor:latest services/log-processor/

## Apply namespace + generator/processor K8s manifests
deploy-services:
	kubectl apply -f k8s/namespace.yaml
	kubectl apply -f k8s/log-generator/
	kubectl apply -f k8s/log-processor/

## Deploy OpenSearch and OpenSearch Dashboards via Helm
deploy-monitoring:
	helm upgrade --install opensearch opensearch/opensearch \
		-n $(NAMESPACE) -f k8s/monitoring/opensearch-values.yaml
	helm upgrade --install opensearch-dashboards opensearch/opensearch-dashboards \
		-n $(NAMESPACE) -f k8s/monitoring/opensearch-dashboards-values.yaml

## Port-forward OpenSearch Dashboards to localhost:5601
port-forward:
	kubectl port-forward -n $(NAMESPACE) svc/opensearch-dashboards 5601:5601 &

## Tear down everything: Helm releases + K8s resources + namespace
teardown:
	helm uninstall redis -n $(NAMESPACE) || true
	helm uninstall opensearch -n $(NAMESPACE) || true
	helm uninstall opensearch-dashboards -n $(NAMESPACE) || true
	kubectl delete -f k8s/log-processor/ || true
	kubectl delete -f k8s/log-generator/ || true
	kubectl delete -f k8s/namespace.yaml || true
