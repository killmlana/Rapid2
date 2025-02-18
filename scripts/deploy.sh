#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TOFU_DIR="$PROJECT_ROOT/infra/tofu"
DOCKER_DIR="$PROJECT_ROOT/infra/docker"

AWS_REGION="${AWS_REGION:-us-west-2}"
ENV="${1:-dev}"

echo "=== Deploying Rapid2 ($ENV) ==="

# 1. OpenTofu
echo "--- Running OpenTofu ---"
cd "$TOFU_DIR"
tofu init
tofu plan -var-file="${ENV}.tfvars" -out=plan.tfplan
tofu apply plan.tfplan
rm -f plan.tfplan

GROBID_ECR=$(tofu output -raw ecr_grobid_url)
VILA_ECR=$(tofu output -raw ecr_vila_url)
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# 2. Docker build & push
echo "--- Building and pushing containers ---"
aws ecr get-login-password --region "$AWS_REGION" | \
    docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "Building GROBID..."
docker build -t "${GROBID_ECR}:latest" -f "$DOCKER_DIR/grobid/Dockerfile" "$PROJECT_ROOT"
docker push "${GROBID_ECR}:latest"

echo "Building VILA..."
docker build -t "${VILA_ECR}:latest" -f "$DOCKER_DIR/vila/Dockerfile" "$PROJECT_ROOT"
docker push "${VILA_ECR}:latest"

# 3. Force ECS service update
echo "--- Updating ECS services ---"
CLUSTER=$(tofu output -raw vpc_id | sed 's/vpc-/rapid2-cluster/')
aws ecs update-service --cluster rapid2-cluster --service rapid2-grobid --force-new-deployment --region "$AWS_REGION" > /dev/null
aws ecs update-service --cluster rapid2-cluster --service rapid2-vila --force-new-deployment --region "$AWS_REGION" > /dev/null

# 4. Print endpoints
echo ""
echo "=== Deployment complete ==="
echo "Neptune:    $(tofu output -raw neptune_endpoint)"
echo "OpenSearch: $(tofu output -raw opensearch_papers_endpoint)"
echo "Annas OS:   $(tofu output -raw opensearch_annas_endpoint)"
echo "GROBID:     $(tofu output -raw grobid_service_dns)"
echo "VILA:       $(tofu output -raw vila_service_dns)"
echo "S3 Bucket:  $(tofu output -raw s3_papers_bucket)"
