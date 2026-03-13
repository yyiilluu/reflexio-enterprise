#!/bin/bash
# =============================================================================
# ECS Deployment Script
# Rebuilds Docker image and deploys to AWS ECS Fargate
# =============================================================================
#
# Usage:
#   ./deploy_ecs.sh              # Build and deploy
#   ./deploy_ecs.sh --skip-build # Deploy without rebuilding
#   ./deploy_ecs.sh --help       # Show help
#
# Prerequisites:
#   - AWS CLI configured with appropriate credentials
#   - Docker running
#   - ECR repository and ECS service already created
# =============================================================================

set -e

# Configuration (modify these or set as environment variables)
AWS_REGION="${AWS_REGION:-us-west-2}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text 2>/dev/null)}"
APP_NAME="${APP_NAME:-agenticmem}"
ECR_REPO_NAME="${ECR_REPO_NAME:-agenticmem}"
ECR_URI="${ECR_URI:-$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME}"
CLUSTER_NAME="${CLUSTER_NAME:-$APP_NAME-cluster}"
SERVICE_NAME="${SERVICE_NAME:-$APP_NAME-service}"

# Script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

show_help() {
    cat << EOF
ECS Deployment Script

Usage: ./deploy_ecs.sh [OPTIONS]

Options:
    --skip-build Skip Docker build, only deploy existing image
    --help       Show this help message

Examples:
    ./deploy_ecs.sh              # Build and deploy
    ./deploy_ecs.sh --skip-build # Deploy without rebuilding

Environment Variables:
    AWS_REGION      AWS region (default: us-west-2)
    AWS_ACCOUNT_ID  AWS account ID (auto-detected)
    APP_NAME        Application name (default: agenticmem)
    ECR_REPO_NAME   ECR repository name (default: agenticmem)
    CLUSTER_NAME    ECS cluster name (default: agenticmem-cluster)
    SERVICE_NAME    ECS service name (default: agenticmem-service)
EOF
}

check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI not found. Please install it first."
        exit 1
    fi

    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker not found. Please install it first."
        exit 1
    fi

    # Check Docker is running
    if ! docker info &> /dev/null; then
        log_error "Docker is not running. Please start Docker Desktop."
        exit 1
    fi

    # Check uv
    if ! command -v uv &> /dev/null; then
        log_error "uv not found. Please install it first: https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    fi

    # Check AWS credentials
    if [ -z "$AWS_ACCOUNT_ID" ]; then
        log_error "Could not determine AWS Account ID. Please configure AWS CLI."
        exit 1
    fi

    log_success "Prerequisites check passed"
    echo "  AWS Account: $AWS_ACCOUNT_ID"
    echo "  AWS Region: $AWS_REGION"
    echo "  ECR URI: $ECR_URI"
}

login_ecr() {
    log_info "Logging into ECR..."
    aws ecr get-login-password --region "$AWS_REGION" | \
        docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
    log_success "ECR login successful"
}

generate_requirements() {
    log_info "Generating requirements.txt from uv (runtime deps only)..."
    cd "$PROJECT_ROOT"

    uv export --no-dev --no-hashes -o requirements.txt

    # Replace local path dependency with PyPI package
    sed -i '' '/-e file:\/\/.*reflexio_commons/d' requirements.txt
    echo "reflexio-commons" >> requirements.txt

    log_success "requirements.txt generated"
}

build_image() {
    log_info "Building Docker image using Dockerfile.base..."
    cd "$PROJECT_ROOT"

    docker build --platform linux/amd64 -f Dockerfile.base -t "${ECR_REPO_NAME}:latest" .

    log_success "Docker image built successfully"
}

push_image() {
    log_info "Tagging and pushing image to ECR..."

    docker tag "${ECR_REPO_NAME}:latest" "${ECR_URI}:latest"
    docker push "${ECR_URI}:latest"

    log_success "Image pushed to ECR"
}

deploy_service() {
    log_info "Deploying to ECS..."

    aws ecs update-service \
        --cluster "$CLUSTER_NAME" \
        --service "$SERVICE_NAME" \
        --force-new-deployment \
        --region "$AWS_REGION" \
        > /dev/null

    log_success "Deployment initiated"
}

# Main script
main() {
    local skip_build=false

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --skip-build)
                skip_build=true
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

    echo "=============================================="
    echo "  ECS Deployment Script"
    echo "=============================================="
    echo ""

    check_prerequisites

    if [ "$skip_build" = false ]; then
        generate_requirements
        login_ecr
        build_image
        push_image
    else
        log_info "Skipping build, deploying existing image"
    fi

    deploy_service

    log_success "Deployment complete!"
}

main "$@"
