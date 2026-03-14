#!/bin/bash
# Script to update Fumadocs documentation website on AWS (ECS + CloudFront)
#
# Docs are built into the Docker image and served by the ECS task on port 8082.
# This script rebuilds the Docker image and forces an ECS redeployment.
#
# Usage:
#   ./update_docs.sh           # Build image, deploy, and invalidate cache
#   ./update_docs.sh --build   # Only build Docker image locally (no deploy)
#   ./update_docs.sh --deploy  # Only deploy (skip build, use existing image)
#
# Prerequisites:
#   - AWS CLI configured with appropriate credentials
#   - Docker Desktop running
#   - ECR repository already set up
#   - ECS service already running
#
# Reference: docs/aws-ecs-deployment.md

set -e

# Configuration
AWS_REGION="${AWS_REGION:-us-west-2}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text 2>/dev/null)}"
APP_NAME="${APP_NAME:-agenticmem}"
ECR_REPO_NAME="${ECR_REPO_NAME:-agenticmem}"
ECR_URI="${ECR_URI:-$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME}"
CF_DISTRIBUTION_ID="${CF_DISTRIBUTION_ID:-E15WBN9QYYCSND}"

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

show_help() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS]

Update Fumadocs documentation website on AWS (ECS + CloudFront).
Docs are built into the Docker image and served by the ECS task on port 8082.

Options:
    --build     Only build Docker image locally (no deploy)
    --deploy    Only deploy existing image (skip build)
    --help      Show this help message

Examples:
    $(basename "$0")           # Build, deploy, and invalidate cache
    $(basename "$0") --build   # Only build Docker image
    $(basename "$0") --deploy  # Deploy existing image and invalidate cache

Configuration (via environment variables):
    AWS_REGION          AWS region (default: us-west-2)
    AWS_ACCOUNT_ID      AWS account ID (auto-detected)
    APP_NAME            Application name (default: agenticmem)
    ECR_REPO_NAME       ECR repository name (default: agenticmem)
    CF_DISTRIBUTION_ID  CloudFront distribution ID (default: E15WBN9QYYCSND)
EOF
}

check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI is not installed. Please install it first."
        exit 1
    fi

    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS credentials not configured. Run 'aws configure' first."
        exit 1
    fi

    # Check Docker (only needed for build)
    if [[ "$DEPLOY_ONLY" != true ]]; then
        if ! command -v docker &> /dev/null; then
            log_error "Docker is not installed. Please install Docker Desktop first."
            exit 1
        fi

        if ! docker info &> /dev/null; then
            log_error "Docker is not running. Please start Docker Desktop first."
            exit 1
        fi
    fi

    log_success "All prerequisites met."
}

build_image() {
    log_info "Building Docker image with updated docs..."

    cd "$PROJECT_ROOT"

    # Login to ECR
    log_info "Logging in to ECR..."
    aws ecr get-login-password --region "$AWS_REGION" | \
        docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

    # Build image
    log_info "Building image (this includes Fumadocs build)..."
    docker build --platform linux/amd64 -f docker/Dockerfile.base -t "${ECR_REPO_NAME}:latest" .

    # Tag and push
    docker tag "${ECR_REPO_NAME}:latest" "${ECR_URI}:latest"
    log_info "Pushing image to ECR..."
    docker push "${ECR_URI}:latest"

    log_success "Docker image built and pushed to ECR."
}

deploy_to_ecs() {
    log_info "Forcing new ECS deployment..."

    aws ecs update-service \
        --cluster "$APP_NAME-cluster" \
        --service "$APP_NAME-service" \
        --force-new-deployment \
        --region "$AWS_REGION" > /dev/null

    log_info "Waiting for ECS service to stabilize..."
    aws ecs wait services-stable \
        --cluster "$APP_NAME-cluster" \
        --services "$APP_NAME-service" \
        --region "$AWS_REGION"

    log_success "ECS deployment complete."
}

invalidate_cloudfront() {
    log_info "Invalidating CloudFront cache for /docs/*..."

    local invalidation_id=$(aws cloudfront create-invalidation \
        --distribution-id "$CF_DISTRIBUTION_ID" \
        --paths "/docs" "/docs/*" \
        --query 'Invalidation.Id' \
        --output text)

    log_success "CloudFront invalidation created: $invalidation_id"
    log_info "Cache invalidation typically takes 1-5 minutes to complete."
}

print_summary() {
    echo ""
    echo "=========================================="
    log_success "Documentation update complete!"
    echo "=========================================="
    echo ""
    echo "URLs:"
    echo "  - Production: https://reflexio.ai/docs/"
    echo ""
    echo "CloudFront Distribution: $CF_DISTRIBUTION_ID"
    echo ""
}

# Parse arguments
BUILD_ONLY=false
DEPLOY_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --build)
            BUILD_ONLY=true
            shift
            ;;
        --deploy)
            DEPLOY_ONLY=true
            shift
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Validate mutually exclusive options
if [[ "$BUILD_ONLY" == true && "$DEPLOY_ONLY" == true ]]; then
    log_error "--build and --deploy are mutually exclusive"
    exit 1
fi

# Main execution
echo ""
echo "=========================================="
echo "  Fumadocs Documentation Update Script"
echo "=========================================="
echo ""
log_info "AWS Region: $AWS_REGION"
log_info "ECR URI: $ECR_URI"
log_info "ECS Cluster: $APP_NAME-cluster"
log_info "CloudFront Distribution: $CF_DISTRIBUTION_ID"
echo ""

if [[ "$BUILD_ONLY" == true ]]; then
    check_prerequisites
    build_image
    log_success "Build complete. Run with --deploy to deploy."
elif [[ "$DEPLOY_ONLY" == true ]]; then
    check_prerequisites
    deploy_to_ecs
    invalidate_cloudfront
    print_summary
else
    # Full build and deploy
    check_prerequisites
    build_image
    deploy_to_ecs
    invalidate_cloudfront
    print_summary
fi
