# AWS ECS Fargate Deployment Guide (Cost-Optimized)

Minimal-cost deployment for Reflexio (FastAPI + Next.js) to AWS ECS Fargate.

## Choose Your Setup

This guide offers two deployment options:

| Option | Monthly Cost | Best For |
|--------|-------------|----------|
| **Option A: No ALB (Ultra-Minimal)** | **~$8-15** | Dev/testing, single user, cost-sensitive |
| **Option B: With ALB** | **~$25-40** | Production, stable DNS, path routing |

### Option A: No ALB - Cost Breakdown

| Resource | Estimated Cost |
|----------|---------------|
| ECS Fargate Spot (1 task, 512 CPU, 1GB) | ~$8-12 |
| CloudWatch Logs | ~$2-5 |
| ECR Storage | ~$1-2 |
| **Total** | **~$8-15/month** |

### Option B: With ALB - Cost Breakdown

| Resource | Estimated Cost |
|----------|---------------|
| ECS Fargate Spot (1 task, 512 CPU, 1GB) | ~$8-12 |
| ALB | ~$18-22 |
| CloudWatch Logs | ~$2-5 |
| ECR Storage | ~$1-2 |
| **Total** | **~$25-40/month** |

### Tradeoffs

| Feature | No ALB | With ALB |
|---------|--------|----------|
| Stable DNS | ❌ IP changes on restart | ✅ Stable ALB DNS |
| Path routing (`/api/*`) | ❌ Use different ports | ✅ Single port, path-based |
| HTTPS | ❌ Complex to add | ✅ Easy with ACM |
| Health checks | ❌ Manual monitoring | ✅ Auto-recovery |
| Cost | ✅ ~$8-15/month | ~$25-40/month |

## Architecture Overview

### Option A: No ALB (Direct Public IP)

```
                    ┌─────────────────────────────────────────────────────────┐
                    │                         AWS Cloud                       │
                    │                                                         │
   Users ──────────►│  ECS Fargate Spot (1 Task) ◄── Public IP               │
                    │      ├── FastAPI :8081                                  │
                    │      └── Next.js :8080                                  │
                    │                                                         │
                    │  ECR (Container Registry)                               │
                    │  Secrets Manager (API keys)                             │
                    │  CloudWatch (Logs)                                      │
                    └─────────────────────────────────────────────────────────┘
```

### Option B: With ALB

```
                    ┌─────────────────────────────────────────────────────────┐
                    │                         AWS Cloud                       │
                    │                                                         │
   Users ──────────►│  ALB ──► ECS Fargate Spot (1 Task)                      │
                    │          │   ├── FastAPI :8081                          │
                    │          │   └── Next.js :8080                          │
                    │          │                                              │
                    │          ├── Target Group :8080 (frontend)              │
                    │          └── Target Group :8081 (api)                   │
                    │                                                         │
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

echo "Account: $AWS_ACCOUNT_ID"
echo "Region: $AWS_REGION"
echo "ECR URI: $ECR_URI"
```

---

## Step 1: Create ECR Repository

```bash
aws ecr create-repository \
    --repository-name $ECR_REPO_NAME \
    --region $AWS_REGION \
    --image-scanning-configuration scanOnPush=true
```

---

## Step 2: Build and Push Docker Image

```bash
# Navigate to project root
cd /Users/yilu/repos/user_profiler

# Login to ECR
aws ecr get-login-password --region $AWS_REGION | \
    docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# Option 1: Build base image (when dependencies change - slower)
docker build --platform linux/amd64 -f docker/Dockerfile.base -t ${ECR_REPO_NAME}:latest .

# Option 2: Build update image (when only code changes - faster)
# Requires base image built first with: docker build -f docker/Dockerfile.base -t reflexio-base:latest .
# docker build --platform linux/amd64 -f docker/Dockerfile.update -t ${ECR_REPO_NAME}:latest .

# Tag and push
docker tag ${ECR_REPO_NAME}:latest ${ECR_URI}:latest
docker push ${ECR_URI}:latest

# Verify
aws ecr describe-images --repository-name $ECR_REPO_NAME --region $AWS_REGION
```

---

## Step 3: Store Secrets in AWS Secrets Manager

```bash
# Create secrets JSON (DO NOT commit this)
cat > /tmp/secrets.json << 'EOF'
{
    "OPENAI_API_KEY": "sk-proj-",
    "LOGIN_SUPABASE_URL": "https://<project id>.supabase.co",
    "LOGIN_SUPABASE_KEY": "eyJ.."
}
EOF

# Create secret in AWS
aws secretsmanager create-secret \
    --name $APP_NAME/prod/env \
    --secret-string file:///tmp/secrets.json \
    --region $AWS_REGION

# Clean up local file
rm /tmp/secrets.json

# Get secret ARN
export SECRET_ARN=$(aws secretsmanager describe-secret \
    --secret-id $APP_NAME/prod/env \
    --query ARN --output text --region $AWS_REGION)
echo "Secret ARN: $SECRET_ARN"
```

---

## Step 4: Create IAM Roles

### 4.1 ECS Task Execution Role

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

### 4.2 ECS Task Role

```bash
aws iam create-role \
    --role-name ecsTaskRole-$APP_NAME \
    --assume-role-policy-document file:///tmp/ecs-trust-policy.json

export TASK_ROLE_ARN=$(aws iam get-role \
    --role-name ecsTaskRole-$APP_NAME \
    --query Role.Arn --output text)
echo "Task Role ARN: $TASK_ROLE_ARN"
```

---

## Step 5: Create VPC and Networking

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

# Create public subnet (1 for Option A, 2 for Option B with ALB)
export SUBNET_1=$(aws ec2 create-subnet \
    --vpc-id $VPC_ID \
    --cidr-block 10.0.1.0/24 \
    --availability-zone ${AWS_REGION}a \
    --query Subnet.SubnetId --output text)

# Option B only: Create second subnet (required for ALB)
export SUBNET_2=$(aws ec2 create-subnet \
    --vpc-id $VPC_ID \
    --cidr-block 10.0.2.0/24 \
    --availability-zone ${AWS_REGION}b \
    --query Subnet.SubnetId --output text)

# Enable auto-assign public IP
aws ec2 modify-subnet-attribute --subnet-id $SUBNET_1 --map-public-ip-on-launch
aws ec2 modify-subnet-attribute --subnet-id $SUBNET_2 --map-public-ip-on-launch  # Option B only

# Create and configure route table
export RTB_ID=$(aws ec2 create-route-table \
    --vpc-id $VPC_ID \
    --query RouteTable.RouteTableId --output text)

aws ec2 create-route --route-table-id $RTB_ID --destination-cidr-block 0.0.0.0/0 --gateway-id $IGW_ID
aws ec2 associate-route-table --subnet-id $SUBNET_1 --route-table-id $RTB_ID
aws ec2 associate-route-table --subnet-id $SUBNET_2 --route-table-id $RTB_ID  # Option B only

echo "VPC: $VPC_ID"
echo "Subnets: $SUBNET_1, $SUBNET_2"
```

---

## Step 6: Create Security Groups

### Option A: No ALB (Direct Public Access)

```bash
# ECS Task Security Group (allows direct public access)
export ECS_SG=$(aws ec2 create-security-group \
    --group-name $APP_NAME-ecs-sg \
    --description "ECS tasks security group" \
    --vpc-id $VPC_ID \
    --query GroupId --output text)

# Allow public access to both ports
aws ec2 authorize-security-group-ingress --group-id $ECS_SG --protocol tcp --port 8080 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id $ECS_SG --protocol tcp --port 8081 --cidr 0.0.0.0/0

echo "ECS SG: $ECS_SG"
```

### Option B: With ALB

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

## Step 7: Create Application Load Balancer (Option B Only)

> **Skip this step if using Option A (No ALB)**

```bash
# Create ALB
export ALB_ARN=$(aws elbv2 create-load-balancer \
    --name $APP_NAME-alb \
    --subnets $SUBNET_1 $SUBNET_2 \
    --security-groups $ALB_SG \
    --scheme internet-facing \
    --type application \
    --query 'LoadBalancers[0].LoadBalancerArn' --output text)

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
    --query 'TargetGroups[0].TargetGroupArn' --output text)

export TG_API_ARN=$(aws elbv2 create-target-group \
    --name $APP_NAME-api-tg \
    --protocol HTTP \
    --port 8081 \
    --vpc-id $VPC_ID \
    --target-type ip \
    --health-check-path "/health" \
    --health-check-interval-seconds 30 \
    --query 'TargetGroups[0].TargetGroupArn' --output text)

# Create HTTP Listener (default to frontend)
export LISTENER_ARN=$(aws elbv2 create-listener \
    --load-balancer-arn $ALB_ARN \
    --protocol HTTP \
    --port 80 \
    --default-actions Type=forward,TargetGroupArn=$TG_FRONTEND_ARN \
    --query 'Listeners[0].ListenerArn' --output text)

# Route /health to API target group (needed for ALB health checks)
aws elbv2 create-rule \
    --listener-arn $LISTENER_ARN \
    --priority 5 \
    --conditions Field=path-pattern,Values='/health' \
    --actions Type=forward,TargetGroupArn=$TG_API_ARN

# Route /token to API target group (authentication endpoint)
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

## Step 8: Create ECS Cluster

```bash
# First-time setup: Create ECS service-linked role (one-time per AWS account)
# This may fail if role already exists - that's OK, proceed to cluster creation
aws iam create-service-linked-role --aws-service-name ecs.amazonaws.com

# Create cluster
aws ecs create-cluster \
    --cluster-name $APP_NAME-cluster \
    --capacity-providers FARGATE_SPOT FARGATE \
    --default-capacity-provider-strategy capacityProvider=FARGATE_SPOT,weight=1 \
    --region $AWS_REGION

echo "ECS Cluster created: $APP_NAME-cluster"
```

---

## Step 9: Create CloudWatch Log Group

```bash
aws logs create-log-group \
    --log-group-name /ecs/$APP_NAME \
    --region $AWS_REGION

# Set 14-day retention (saves costs)
aws logs put-retention-policy \
    --log-group-name /ecs/$APP_NAME \
    --retention-in-days 7 \
    --region $AWS_REGION
```

---

## Step 10: Create ECS Task Definition (Cost-Optimized)

```bash
cat > /tmp/task-definition.json << EOF
{
    "family": "${APP_NAME}-task",
    "networkMode": "awsvpc",
    "requiresCompatibilities": ["FARGATE"],
    "cpu": "1024",
    "memory": "4096",
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
                {"name": "ENVIRONMENT", "value": "production"}
            ],
            "secrets": [
                {"name": "OPENAI_API_KEY", "valueFrom": "${SECRET_ARN}:OPENAI_API_KEY::"},
                {"name": "ANTHROPIC_API_KEY", "valueFrom": "${SECRET_ARN}:ANTHROPIC_API_KEY::"},
                {"name": "LOGIN_SUPABASE_URL", "valueFrom": "${SECRET_ARN}:LOGIN_SUPABASE_URL::"},
                {"name": "LOGIN_SUPABASE_KEY", "valueFrom": "${SECRET_ARN}:LOGIN_SUPABASE_KEY::"}
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

## Step 11: Create ECS Service (Using Fargate Spot)

### Option A: No ALB (Direct Public IP)

```bash
aws ecs create-service \
    --cluster $APP_NAME-cluster \
    --service-name $APP_NAME-service \
    --task-definition $APP_NAME-task \
    --desired-count 1 \
    --capacity-provider-strategy "capacityProvider=FARGATE_SPOT,weight=1" \
    --platform-version LATEST \
    --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_1],securityGroups=[$ECS_SG],assignPublicIp=ENABLED}" \
    --deployment-configuration "minimumHealthyPercent=0,maximumPercent=100" \
    --enable-execute-command \
    --region $AWS_REGION

echo "ECS Service created with Fargate Spot (No ALB)"
```

### Option B: With ALB

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

echo "ECS Service created with Fargate Spot (With ALB)"
```

> **Note**: `minimumHealthyPercent=0` allows rolling deployments with a single task. This means brief downtime during deployments, which is acceptable for cost savings.

---

## Step 12: Verify Deployment

### Check Service Status

```bash
# Check service status
aws ecs describe-services \
    --cluster $APP_NAME-cluster \
    --services $APP_NAME-service \
    --query 'services[0].{Status:status,Running:runningCount,Desired:desiredCount}'
```

**Understanding the output:**
- `Running: 1, Desired: 1` - Task is running successfully
- `Running: 0, Desired: 1` - Task is failing to start (see troubleshooting below)

### If Task Fails to Start

```bash
# Check recent service events for errors
aws ecs describe-services \
    --cluster $APP_NAME-cluster \
    --services $APP_NAME-service \
    --query 'services[0].events[0:5]'

# Check stopped task reason
aws ecs list-tasks --cluster $APP_NAME-cluster --desired-status STOPPED --query 'taskArns[0]' --output text | \
    xargs -I{} aws ecs describe-tasks --cluster $APP_NAME-cluster --tasks {} \
    --query 'tasks[0].{stoppedReason:stoppedReason,stopCode:stopCode}'
```

**Common errors:**
| Error | Cause | Fix |
|-------|-------|-----|
| `unable to retrieve secret...did not contain json key X` | Secret missing required key | Update secret with missing key |
| `CannotPullContainerError` | ECR image not found | Verify image exists: `aws ecr describe-images --repository-name $ECR_REPO_NAME` |
| `Capacity is unavailable` | Fargate Spot unavailable | Wait and retry, or switch to regular Fargate |
| `ResourceInitializationError` | Secrets/IAM permission issue | Check execution role has Secrets Manager access |

### Wait for Service to Stabilize

```bash
# This will wait until Running matches Desired (or timeout after 10 min)
aws ecs wait services-stable \
    --cluster $APP_NAME-cluster \
    --services $APP_NAME-service

echo "Service is stable!"
```

### Option A: Get Public IP and Test (No ALB)

```bash
# Get the task's public IP
export TASK_ARN=$(aws ecs list-tasks \
      --cluster $APP_NAME-cluster \
      --service-name $APP_NAME-service \
      --query 'taskArns[0]' --output text)

export ENI_ID=$(aws ecs describe-tasks \
      --cluster $APP_NAME-cluster \
      --tasks "$TASK_ARN" \
      --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' \
      --output text)

export PUBLIC_IP=$(aws ec2 describe-network-interfaces \
      --network-interface-ids "$ENI_ID" \
      --query 'NetworkInterfaces[0].Association.PublicIp' \
      --output text)

echo "Public IP: $PUBLIC_IP"
echo "Frontend: http://$PUBLIC_IP:8080/"
echo "API: http://$PUBLIC_IP:8081/health"

# Test endpoints
curl -I http://$PUBLIC_IP:8080/
curl http://$PUBLIC_IP:8081/health
```

> **Important**: The public IP changes every time the task restarts. You'll need to re-run the above commands to get the new IP.

### Option B: Test via ALB

```bash
# Test endpoints
echo "Frontend: http://$ALB_DNS/"
echo "API: http://$ALB_DNS/api/health"

curl -I http://$ALB_DNS/
curl http://$ALB_DNS/api/health
```

---

## Updating the Application

```bash
# Build and push new image
cd /Users/yilu/repos/user_profiler
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


# Force new deployment with new task definition
aws ecs update-service \
    --cluster $APP_NAME-cluster \
    --service $APP_NAME-service \
    --task-definition ${APP_NAME}-task-<number> \
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
    --query 'taskArns[0]' --output text)

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

### Option A: No ALB Cleanup

```bash
# Delete ECS service
aws ecs update-service --cluster $APP_NAME-cluster --service $APP_NAME-service --desired-count 0
aws ecs delete-service --cluster $APP_NAME-cluster --service $APP_NAME-service --force

# Delete ECS cluster
aws ecs delete-cluster --cluster $APP_NAME-cluster

# Delete security group
aws ec2 delete-security-group --group-id $ECS_SG

# Delete VPC resources
aws ec2 delete-subnet --subnet-id $SUBNET_1
aws ec2 delete-route-table --route-table-id $RTB_ID
aws ec2 detach-internet-gateway --internet-gateway-id $IGW_ID --vpc-id $VPC_ID
aws ec2 delete-internet-gateway --internet-gateway-id $IGW_ID
aws ec2 delete-vpc --vpc-id $VPC_ID

# Delete ECR repository
aws ecr delete-repository --repository-name $ECR_REPO_NAME --force

# Delete secrets
aws secretsmanager delete-secret --secret-id $APP_NAME/prod/env --force-delete-without-recovery

# Delete IAM roles
aws iam delete-role-policy --role-name ecsTaskExecutionRole-$APP_NAME --policy-name SecretsManagerAccess
aws iam detach-role-policy --role-name ecsTaskExecutionRole-$APP_NAME --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
aws iam delete-role --role-name ecsTaskExecutionRole-$APP_NAME
aws iam delete-role --role-name ecsTaskRole-$APP_NAME

# Delete log group
aws logs delete-log-group --log-group-name /ecs/$APP_NAME

echo "Cleanup complete"
```

### Option B: With ALB Cleanup

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
aws secretsmanager delete-secret --secret-id $APP_NAME/prod/env --force-delete-without-recovery

# Delete IAM roles
aws iam delete-role-policy --role-name ecsTaskExecutionRole-$APP_NAME --policy-name SecretsManagerAccess
aws iam detach-role-policy --role-name ecsTaskExecutionRole-$APP_NAME --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
aws iam delete-role --role-name ecsTaskExecutionRole-$APP_NAME
aws iam delete-role --role-name ecsTaskRole-$APP_NAME

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
```

---

## Troubleshooting

### Task failing to start
```bash
# Check task stopped reason
aws ecs describe-tasks \
    --cluster $APP_NAME-cluster \
    --tasks $(aws ecs list-tasks --cluster $APP_NAME-cluster --query 'taskArns[0]' --output text) \
    --query 'tasks[0].stoppedReason'
```

### Target unhealthy (Option B only)
```bash
aws elbv2 describe-target-health --target-group-arn $TG_FRONTEND_ARN
aws elbv2 describe-target-health --target-group-arn $TG_API_ARN
```

### Get current public IP (Option A only)
```bash
# Run this after every task restart to get the new IP
TASK_ARN=$(aws ecs list-tasks --cluster $APP_NAME-cluster --service-name $APP_NAME-service --query 'taskArns[0]' --output text)
ENI_ID=$(aws ecs describe-tasks --cluster $APP_NAME-cluster --tasks $TASK_ARN --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' --output text)
aws ec2 describe-network-interfaces --network-interface-ids $ENI_ID --query 'NetworkInterfaces[0].Association.PublicIp' --output text
```

### Fargate Spot interruption
Fargate Spot tasks can be interrupted with 2-minute warning. The service will automatically launch a new task. For critical production workloads, consider using regular Fargate.

**For Option A (No ALB)**: After a Spot interruption, you'll need to get the new public IP using the command above.
