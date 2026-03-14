# AWS ECS Fargate Self-Host Deployment Guide

Deploy Reflexio (FastAPI + Next.js) to your own AWS account using ECS Fargate with Application Load Balancer.

## Self-Host Mode Overview

Self-host mode enables Reflexio to run in your own AWS account without requiring external authentication services. Key characteristics:

- **No authentication required**: Default org is `self-host-org`
- **S3-based config storage**: Configuration stored in your S3 bucket
- **User-provided Supabase**: You provide your own Supabase instance for profile/memory storage (configured via UI)

### Required Environment Variables

| Variable | Description |
|----------|-------------|
| `SELF_HOST` | Set to `true` to enable self-host mode (backend) |
| `NEXT_PUBLIC_SELF_HOST` | Set to `true` to enable self-host mode (frontend) |
| `CONFIG_S3_ACCESS_KEY` | AWS access key for S3 config storage |
| `CONFIG_S3_SECRET_KEY` | AWS secret key for S3 config storage |
| `CONFIG_S3_REGION` | AWS region for S3 bucket (e.g., `us-west-2`) |
| `CONFIG_S3_PATH` | S3 bucket name for config storage |
| `OPENAI_API_KEY` | OpenAI API key for LLM operations |

## Cost Estimate

| Resource | Estimated Cost |
|----------|---------------|
| ECS Fargate Spot (1 task, 512 CPU, 2GB) | ~$8-12/month |
| ALB | ~$18-22/month |
| CloudWatch Logs | ~$2-5/month |
| ECR Storage | ~$1-2/month |
| S3 Config Storage | ~$0.50/month |
| **Total** | **~$30-45/month** |

## Architecture

```
                    ┌─────────────────────────────────────────────────────────┐
                    │                     Your AWS Account                    │
                    │                                                         │
   Users ──────────►│  ALB ──► ECS Fargate Spot (1 Task)                      │
                    │          │   ├── FastAPI :8081                          │
                    │          │   └── Next.js :8080                          │
                    │          │                                              │
                    │          ├── Target Group :8080 (frontend)              │
                    │          └── Target Group :8081 (api)                   │
                    │                                                         │
                    │  S3 (Config Storage)                                    │
                    │  ECR (Container Registry)                               │
                    │  Secrets Manager (API keys)                             │
                    │  CloudWatch (Logs)                                      │
                    └─────────────────────────────────────────────────────────┘
```

---

## Prerequisites

### 1. Install Required Tools

```bash
# Install AWS CLI v2 (macOS)
curl "https://awscli.amazonaws.com/AWSCLIV2.pkg" -o "AWSCLIV2.pkg"
sudo installer -pkg AWSCLIV2.pkg -target /

# Verify
aws --version

# Docker Desktop required - download from https://www.docker.com/products/docker-desktop/
```

### 2. Configure AWS CLI

```bash
aws configure
# Enter: AWS Access Key ID, Secret Access Key, Region (e.g., us-west-2), Output format: json

# Verify
aws sts get-caller-identity
```

### 3. Set Environment Variables

```bash
# Set these variables (used throughout the guide)
export AWS_REGION=us-west-2
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export APP_NAME=reflexio
export ECR_REPO_NAME=reflexio
export ECR_URI=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME
export CONFIG_BUCKET_NAME=reflexio-config-$AWS_ACCOUNT_ID

echo "Account: $AWS_ACCOUNT_ID"
echo "Region: $AWS_REGION"
echo "ECR URI: $ECR_URI"
echo "Config Bucket: $CONFIG_BUCKET_NAME"
```

---

## Step 1: Create S3 Bucket for Config Storage

```bash
# Create S3 bucket for configuration storage
aws s3api create-bucket \
    --bucket $CONFIG_BUCKET_NAME \
    --region $AWS_REGION \
    --create-bucket-configuration LocationConstraint=$AWS_REGION

# Enable versioning for config safety
aws s3api put-bucket-versioning \
    --bucket $CONFIG_BUCKET_NAME \
    --versioning-configuration Status=Enabled

# Block public access
aws s3api put-public-access-block \
    --bucket $CONFIG_BUCKET_NAME \
    --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

echo "Config bucket created: $CONFIG_BUCKET_NAME"
```

---

## Step 2: Create ECR Repository

```bash
aws ecr create-repository \
    --repository-name $ECR_REPO_NAME \
    --region $AWS_REGION \
    --image-scanning-configuration scanOnPush=true
```

---

## Step 3: Build and Push Docker Image

```bash
# Navigate to project root
cd /path/to/user_profiler

# Login to ECR
aws ecr get-login-password --region $AWS_REGION | \
    docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# Build image
docker build --platform linux/amd64 -f docker/Dockerfile.base -t ${ECR_REPO_NAME}:latest .

# Tag and push
docker tag ${ECR_REPO_NAME}:latest ${ECR_URI}:latest
docker push ${ECR_URI}:latest

# Verify
aws ecr describe-images --repository-name $ECR_REPO_NAME --region $AWS_REGION
```

---

## Step 4: Store Secrets in AWS Secrets Manager

```bash
# Create secrets JSON (DO NOT commit this)
cat > /tmp/secrets.json << 'EOF'
{
    "OPENAI_API_KEY": "sk-proj-YOUR_OPENAI_KEY",
    "CONFIG_S3_ACCESS_KEY": "YOUR_AWS_ACCESS_KEY",
    "CONFIG_S3_SECRET_KEY": "YOUR_AWS_SECRET_KEY"
}
EOF

# Create secret in AWS
aws secretsmanager create-secret \
    --name $APP_NAME/selfhost/env \
    --secret-string file:///tmp/secrets.json \
    --region $AWS_REGION

# Clean up local file
rm /tmp/secrets.json

# Get secret ARN
export SECRET_ARN=$(aws secretsmanager describe-secret \
    --secret-id $APP_NAME/selfhost/env \
    --query ARN --output text --region $AWS_REGION)
echo "Secret ARN: $SECRET_ARN"
```

---

## Step 5: Create IAM Roles

### 5.1 ECS Task Execution Role

```bash
# Create trust policy
cat > /tmp/ecs-trust-policy.json << 'EOF'
{
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "ecs-tasks.amazonaws.com"},
        "Action": "sts:AssumeRole"
    }]
}
EOF

# Create execution role
aws iam create-role \
    --role-name ecsTaskExecutionRole-$APP_NAME \
    --assume-role-policy-document file:///tmp/ecs-trust-policy.json

# Attach managed policy
aws iam attach-role-policy \
    --role-name ecsTaskExecutionRole-$APP_NAME \
    --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

# Add Secrets Manager access
cat > /tmp/secrets-policy.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Action": ["secretsmanager:GetSecretValue"],
        "Resource": "$SECRET_ARN"
    }]
}
EOF

aws iam put-role-policy \
    --role-name ecsTaskExecutionRole-$APP_NAME \
    --policy-name SecretsManagerAccess \
    --policy-document file:///tmp/secrets-policy.json

# Get ARN
export EXECUTION_ROLE_ARN=$(aws iam get-role \
    --role-name ecsTaskExecutionRole-$APP_NAME \
    --query Role.Arn --output text)
echo "Execution Role ARN: $EXECUTION_ROLE_ARN"
```

### 5.2 ECS Task Role (with S3 Access)

```bash
# Create task role
aws iam create-role \
    --role-name ecsTaskRole-$APP_NAME \
    --assume-role-policy-document file:///tmp/ecs-trust-policy.json

# Add S3 access for config storage
cat > /tmp/s3-policy.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Action": [
            "s3:GetObject",
            "s3:PutObject",
            "s3:DeleteObject",
            "s3:ListBucket"
        ],
        "Resource": [
            "arn:aws:s3:::$CONFIG_BUCKET_NAME",
            "arn:aws:s3:::$CONFIG_BUCKET_NAME/*"
        ]
    }]
}
EOF

aws iam put-role-policy \
    --role-name ecsTaskRole-$APP_NAME \
    --policy-name S3ConfigAccess \
    --policy-document file:///tmp/s3-policy.json

export TASK_ROLE_ARN=$(aws iam get-role \
    --role-name ecsTaskRole-$APP_NAME \
    --query Role.Arn --output text)
echo "Task Role ARN: $TASK_ROLE_ARN"
```

---

## Step 6: Create VPC and Networking

```bash
# Create VPC
export VPC_ID=$(aws ec2 create-vpc \
    --cidr-block 10.0.0.0/16 \
    --query Vpc.VpcId --output text)

aws ec2 modify-vpc-attribute --vpc-id $VPC_ID --enable-dns-hostnames
aws ec2 modify-vpc-attribute --vpc-id $VPC_ID --enable-dns-support
aws ec2 create-tags --resources $VPC_ID --tags Key=Name,Value=$APP_NAME-vpc

# Create Internet Gateway
export IGW_ID=$(aws ec2 create-internet-gateway \
    --query InternetGateway.InternetGatewayId --output text)
aws ec2 attach-internet-gateway --vpc-id $VPC_ID --internet-gateway-id $IGW_ID

# Create public subnets (2 required for ALB)
export SUBNET_1=$(aws ec2 create-subnet \
    --vpc-id $VPC_ID \
    --cidr-block 10.0.1.0/24 \
    --availability-zone ${AWS_REGION}a \
    --query Subnet.SubnetId --output text)

export SUBNET_2=$(aws ec2 create-subnet \
    --vpc-id $VPC_ID \
    --cidr-block 10.0.2.0/24 \
    --availability-zone ${AWS_REGION}b \
    --query Subnet.SubnetId --output text)

# Enable auto-assign public IP
aws ec2 modify-subnet-attribute --subnet-id $SUBNET_1 --map-public-ip-on-launch
aws ec2 modify-subnet-attribute --subnet-id $SUBNET_2 --map-public-ip-on-launch

# Create and configure route table
export RTB_ID=$(aws ec2 create-route-table \
    --vpc-id $VPC_ID \
    --query RouteTable.RouteTableId --output text)

aws ec2 create-route --route-table-id $RTB_ID --destination-cidr-block 0.0.0.0/0 --gateway-id $IGW_ID
aws ec2 associate-route-table --subnet-id $SUBNET_1 --route-table-id $RTB_ID
aws ec2 associate-route-table --subnet-id $SUBNET_2 --route-table-id $RTB_ID

echo "VPC: $VPC_ID"
echo "Subnets: $SUBNET_1, $SUBNET_2"
```

---

## Step 7: Create Security Groups

```bash
# ALB Security Group
export ALB_SG=$(aws ec2 create-security-group \
    --group-name $APP_NAME-alb-sg \
    --description "ALB security group" \
    --vpc-id $VPC_ID \
    --query GroupId --output text)

aws ec2 authorize-security-group-ingress --group-id $ALB_SG --protocol tcp --port 80 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id $ALB_SG --protocol tcp --port 443 --cidr 0.0.0.0/0

# ECS Task Security Group (only allows traffic from ALB)
export ECS_SG=$(aws ec2 create-security-group \
    --group-name $APP_NAME-ecs-sg \
    --description "ECS tasks security group" \
    --vpc-id $VPC_ID \
    --query GroupId --output text)

aws ec2 authorize-security-group-ingress --group-id $ECS_SG --protocol tcp --port 8080 --source-group $ALB_SG
aws ec2 authorize-security-group-ingress --group-id $ECS_SG --protocol tcp --port 8081 --source-group $ALB_SG

echo "ALB SG: $ALB_SG"
echo "ECS SG: $ECS_SG"
```

---

## Step 8: Create Application Load Balancer

```bash
# Create ALB
export ALB_ARN=$(aws elbv2 create-load-balancer \
    --name $APP_NAME-alb \
    --subnets $SUBNET_1 $SUBNET_2 \
    --security-groups $ALB_SG \
    --scheme internet-facing \
    --type application \
    --query LoadBalancers[0].LoadBalancerArn --output text)

export ALB_DNS=$(aws elbv2 describe-load-balancers \
    --load-balancer-arns $ALB_ARN \
    --query 'LoadBalancers[0].DNSName' --output text)

echo "ALB DNS: $ALB_DNS"

# Create Target Groups
export TG_FRONTEND_ARN=$(aws elbv2 create-target-group \
    --name $APP_NAME-frontend-tg \
    --protocol HTTP \
    --port 8080 \
    --vpc-id $VPC_ID \
    --target-type ip \
    --health-check-path "/" \
    --health-check-interval-seconds 30 \
    --query TargetGroups[0].TargetGroupArn --output text)

export TG_API_ARN=$(aws elbv2 create-target-group \
    --name $APP_NAME-api-tg \
    --protocol HTTP \
    --port 8081 \
    --vpc-id $VPC_ID \
    --target-type ip \
    --health-check-path "/health" \
    --health-check-interval-seconds 30 \
    --query TargetGroups[0].TargetGroupArn --output text)

# Create HTTP Listener (default to frontend)
export LISTENER_ARN=$(aws elbv2 create-listener \
    --load-balancer-arn $ALB_ARN \
    --protocol HTTP \
    --port 80 \
    --default-actions Type=forward,TargetGroupArn=$TG_FRONTEND_ARN \
    --query Listeners[0].ListenerArn --output text)

# Route /health to API target group
aws elbv2 create-rule \
    --listener-arn $LISTENER_ARN \
    --priority 5 \
    --conditions Field=path-pattern,Values='/health' \
    --actions Type=forward,TargetGroupArn=$TG_API_ARN

# Route /token to API target group
aws elbv2 create-rule \
    --listener-arn $LISTENER_ARN \
    --priority 6 \
    --conditions Field=path-pattern,Values='/token' \
    --actions Type=forward,TargetGroupArn=$TG_API_ARN

# Route /api/* to API target group
aws elbv2 create-rule \
    --listener-arn $LISTENER_ARN \
    --priority 10 \
    --conditions Field=path-pattern,Values='/api/*' \
    --actions Type=forward,TargetGroupArn=$TG_API_ARN

echo "Frontend TG: $TG_FRONTEND_ARN"
echo "API TG: $TG_API_ARN"
```

---

## Step 9: Create ECS Cluster

```bash
# First-time setup: Create ECS service-linked role (one-time per AWS account)
# This may fail if role already exists - that's OK
aws iam create-service-linked-role --aws-service-name ecs.amazonaws.com 2>/dev/null || true

# Create cluster
aws ecs create-cluster \
    --cluster-name $APP_NAME-cluster \
    --capacity-providers FARGATE_SPOT FARGATE \
    --default-capacity-provider-strategy capacityProvider=FARGATE_SPOT,weight=1 \
    --region $AWS_REGION

echo "ECS Cluster created: $APP_NAME-cluster"
```

---

## Step 10: Create CloudWatch Log Group

```bash
aws logs create-log-group \
    --log-group-name /ecs/$APP_NAME \
    --region $AWS_REGION

# Set 7-day retention (saves costs)
aws logs put-retention-policy \
    --log-group-name /ecs/$APP_NAME \
    --retention-in-days 7 \
    --region $AWS_REGION
```

---

## Step 11: Create ECS Task Definition

This task definition includes all self-host environment variables:

```bash
cat > /tmp/task-definition.json << EOF
{
    "family": "${APP_NAME}-task",
    "networkMode": "awsvpc",
    "requiresCompatibilities": ["FARGATE"],
    "cpu": "512",
    "memory": "2048",
    "executionRoleArn": "${EXECUTION_ROLE_ARN}",
    "taskRoleArn": "${TASK_ROLE_ARN}",
    "containerDefinitions": [
        {
            "name": "${APP_NAME}",
            "image": "${ECR_URI}:latest",
            "essential": true,
            "portMappings": [
                {"containerPort": 8080, "protocol": "tcp", "name": "frontend"},
                {"containerPort": 8081, "protocol": "tcp", "name": "api"}
            ],
            "environment": [
                {"name": "NODE_ENV", "value": "production"},
                {"name": "ENVIRONMENT", "value": "production"},
                {"name": "SELF_HOST", "value": "true"},
                {"name": "NEXT_PUBLIC_SELF_HOST", "value": "true"},
                {"name": "CONFIG_S3_REGION", "value": "${AWS_REGION}"},
                {"name": "CONFIG_S3_PATH", "value": "${CONFIG_BUCKET_NAME}"}
            ],
            "secrets": [
                {"name": "OPENAI_API_KEY", "valueFrom": "${SECRET_ARN}:OPENAI_API_KEY::"},
                {"name": "CONFIG_S3_ACCESS_KEY", "valueFrom": "${SECRET_ARN}:CONFIG_S3_ACCESS_KEY::"},
                {"name": "CONFIG_S3_SECRET_KEY", "valueFrom": "${SECRET_ARN}:CONFIG_S3_SECRET_KEY::"}
            ],
            "logConfiguration": {
                "logDriver": "awslogs",
                "options": {
                    "awslogs-group": "/ecs/${APP_NAME}",
                    "awslogs-region": "${AWS_REGION}",
                    "awslogs-stream-prefix": "ecs"
                }
            },
            "healthCheck": {
                "command": ["CMD-SHELL", "curl -f http://localhost:8081/health || exit 1"],
                "interval": 30,
                "timeout": 5,
                "retries": 3,
                "startPeriod": 60
            }
        }
    ]
}
EOF

aws ecs register-task-definition \
    --cli-input-json file:///tmp/task-definition.json \
    --region $AWS_REGION

echo "Task definition registered"
```

---

## Step 12: Create ECS Service

```bash
aws ecs create-service \
    --cluster $APP_NAME-cluster \
    --service-name $APP_NAME-service \
    --task-definition $APP_NAME-task \
    --desired-count 1 \
    --capacity-provider-strategy "capacityProvider=FARGATE_SPOT,weight=1" \
    --platform-version LATEST \
    --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_1,$SUBNET_2],securityGroups=[$ECS_SG],assignPublicIp=ENABLED}" \
    --load-balancers "targetGroupArn=$TG_FRONTEND_ARN,containerName=$APP_NAME,containerPort=8080" "targetGroupArn=$TG_API_ARN,containerName=$APP_NAME,containerPort=8081" \
    --deployment-configuration "minimumHealthyPercent=0,maximumPercent=100" \
    --enable-execute-command \
    --region $AWS_REGION

echo "ECS Service created with Fargate Spot"
```

> **Note**: `minimumHealthyPercent=0` allows rolling deployments with a single task. This means brief downtime during deployments, which is acceptable for cost savings.

---

## Step 13: Verify Deployment

### Check Service Status

```bash
# Check service status
aws ecs describe-services \
    --cluster $APP_NAME-cluster \
    --services $APP_NAME-service \
    --query 'services[0].{Status:status,Running:runningCount,Desired:desiredCount}'
```

### Wait for Service to Stabilize

```bash
aws ecs wait services-stable \
    --cluster $APP_NAME-cluster \
    --services $APP_NAME-service

echo "Service is stable!"
```

### Test Endpoints

```bash
echo "Frontend: http://$ALB_DNS/"
echo "API Health: http://$ALB_DNS/health"

curl -I http://$ALB_DNS/
curl http://$ALB_DNS/health
```

---

## Step 14: Configure Supabase Storage (Post-Deployment)

After deployment, access the Reflexio UI to configure your Supabase storage:

1. Navigate to `http://$ALB_DNS/`
2. Go to **Settings** → **Storage Configuration**
3. Enter your Supabase credentials:
   - Supabase URL
   - Supabase Key
   - Database URL (for vector search)
4. Test the connection and save

---

## Updating the Application

```bash
# Build and push new image
cd /path/to/user_profiler
docker build --platform linux/amd64 -f docker/Dockerfile.base -t ${ECR_REPO_NAME}:latest .
docker tag ${ECR_REPO_NAME}:latest ${ECR_URI}:latest

aws ecr get-login-password --region $AWS_REGION | \
    docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

docker push ${ECR_URI}:latest

# Force new deployment
aws ecs update-service \
    --cluster $APP_NAME-cluster \
    --service $APP_NAME-service \
    --force-new-deployment

# Watch deployment
aws ecs wait services-stable \
    --cluster $APP_NAME-cluster \
    --services $APP_NAME-service

echo "Deployment complete!"
```

---

## Viewing Logs

```bash
# Tail logs
aws logs tail /ecs/$APP_NAME --follow

# View recent logs
aws logs tail /ecs/$APP_NAME --since 1h
```

---

## SSH into Container (Troubleshooting)

```bash
TASK_ARN=$(aws ecs list-tasks \
    --cluster $APP_NAME-cluster \
    --service-name $APP_NAME-service \
    --query taskArns[0] --output text)

aws ecs execute-command \
    --cluster $APP_NAME-cluster \
    --task $TASK_ARN \
    --container $APP_NAME \
    --interactive \
    --command "/bin/bash"
```

---

## Optional: Add HTTPS with ACM Certificate

```bash
# Request certificate
export CERT_ARN=$(aws acm request-certificate \
    --domain-name yourdomain.com \
    --validation-method DNS \
    --query CertificateArn --output text)

echo "Complete DNS validation in AWS Console > ACM"

# After validation, add HTTPS listener
aws elbv2 create-listener \
    --load-balancer-arn $ALB_ARN \
    --protocol HTTPS \
    --port 443 \
    --certificates CertificateArn=$CERT_ARN \
    --default-actions Type=forward,TargetGroupArn=$TG_FRONTEND_ARN

# Add API routing rules to HTTPS listener
export HTTPS_LISTENER_ARN=$(aws elbv2 describe-listeners \
    --load-balancer-arn $ALB_ARN \
    --query "Listeners[?Protocol=='HTTPS'].ListenerArn" --output text)

# Route /health to API target group
aws elbv2 create-rule \
    --listener-arn $HTTPS_LISTENER_ARN \
    --priority 5 \
    --conditions Field=path-pattern,Values='/health' \
    --actions Type=forward,TargetGroupArn=$TG_API_ARN

# Route /token to API target group
aws elbv2 create-rule \
    --listener-arn $HTTPS_LISTENER_ARN \
    --priority 6 \
    --conditions Field=path-pattern,Values='/token' \
    --actions Type=forward,TargetGroupArn=$TG_API_ARN

# Route /api/* to API target group
aws elbv2 create-rule \
    --listener-arn $HTTPS_LISTENER_ARN \
    --priority 10 \
    --conditions Field=path-pattern,Values='/api/*' \
    --actions Type=forward,TargetGroupArn=$TG_API_ARN

# Redirect HTTP to HTTPS
aws elbv2 modify-listener \
    --listener-arn $LISTENER_ARN \
    --default-actions Type=redirect,RedirectConfig='{Protocol=HTTPS,Port=443,StatusCode=HTTP_301}'
```

---

## Cleanup (Delete Everything)

```bash
# Delete ECS service
aws ecs update-service --cluster $APP_NAME-cluster --service $APP_NAME-service --desired-count 0
aws ecs delete-service --cluster $APP_NAME-cluster --service $APP_NAME-service --force

# Delete ECS cluster
aws ecs delete-cluster --cluster $APP_NAME-cluster

# Delete ALB resources
aws elbv2 delete-listener --listener-arn $LISTENER_ARN
aws elbv2 delete-target-group --target-group-arn $TG_FRONTEND_ARN
aws elbv2 delete-target-group --target-group-arn $TG_API_ARN
aws elbv2 delete-load-balancer --load-balancer-arn $ALB_ARN

# Wait for ALB to delete
sleep 60

# Delete security groups
aws ec2 delete-security-group --group-id $ECS_SG
aws ec2 delete-security-group --group-id $ALB_SG

# Delete VPC resources
aws ec2 delete-subnet --subnet-id $SUBNET_1
aws ec2 delete-subnet --subnet-id $SUBNET_2
aws ec2 delete-route-table --route-table-id $RTB_ID
aws ec2 detach-internet-gateway --internet-gateway-id $IGW_ID --vpc-id $VPC_ID
aws ec2 delete-internet-gateway --internet-gateway-id $IGW_ID
aws ec2 delete-vpc --vpc-id $VPC_ID

# Delete ECR repository
aws ecr delete-repository --repository-name $ECR_REPO_NAME --force

# Delete secrets
aws secretsmanager delete-secret --secret-id $APP_NAME/selfhost/env --force-delete-without-recovery

# Delete S3 config bucket (must be empty first)
aws s3 rm s3://$CONFIG_BUCKET_NAME --recursive
aws s3api delete-bucket --bucket $CONFIG_BUCKET_NAME

# Delete IAM roles
aws iam delete-role-policy --role-name ecsTaskRole-$APP_NAME --policy-name S3ConfigAccess
aws iam delete-role --role-name ecsTaskRole-$APP_NAME
aws iam delete-role-policy --role-name ecsTaskExecutionRole-$APP_NAME --policy-name SecretsManagerAccess
aws iam detach-role-policy --role-name ecsTaskExecutionRole-$APP_NAME --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
aws iam delete-role --role-name ecsTaskExecutionRole-$APP_NAME

# Delete log group
aws logs delete-log-group --log-group-name /ecs/$APP_NAME

echo "Cleanup complete"
```

---

## Quick Reference: Environment Variables

Save these after setup for future deployments:

```bash
# Save to ~/.bashrc or run before deployments
export AWS_REGION=us-west-2
export AWS_ACCOUNT_ID=<your-account-id>
export APP_NAME=reflexio
export ECR_URI=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$APP_NAME
export CONFIG_BUCKET_NAME=reflexio-config-$AWS_ACCOUNT_ID
```

---

## Troubleshooting

### Task failing to start
```bash
# Check task stopped reason
aws ecs describe-tasks \
    --cluster $APP_NAME-cluster \
    --tasks $(aws ecs list-tasks --cluster $APP_NAME-cluster --query taskArns[0] --output text) \
    --query 'tasks[0].stoppedReason'
```

### Target unhealthy
```bash
aws elbv2 describe-target-health --target-group-arn $TG_FRONTEND_ARN
aws elbv2 describe-target-health --target-group-arn $TG_API_ARN
```

### Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `SELF_HOST=true requires S3 config storage` | Missing CONFIG_S3_* vars | Verify all 4 CONFIG_S3_* env vars are set |
| Login page shown instead of dashboard | Missing NEXT_PUBLIC_SELF_HOST | Add `NEXT_PUBLIC_SELF_HOST=true` to environment |
| `unable to retrieve secret...did not contain json key X` | Secret missing required key | Update secret with missing key |
| `CannotPullContainerError` | ECR image not found | Verify image exists: `aws ecr describe-images --repository-name $ECR_REPO_NAME` |
| `Capacity is unavailable` | Fargate Spot unavailable | Wait and retry, or switch to regular Fargate |
| `ResourceInitializationError` | Secrets/IAM permission issue | Check execution role has Secrets Manager access |
| `Access Denied` on S3 | Task role missing S3 permissions | Verify ecsTaskRole-$APP_NAME has S3ConfigAccess policy |

### Fargate Spot interruption

Fargate Spot tasks can be interrupted with 2-minute warning. The service will automatically launch a new task. For critical production workloads, consider using regular Fargate by changing `FARGATE_SPOT` to `FARGATE` in the service creation command.
