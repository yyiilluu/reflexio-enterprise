# AWS ECS Fargate Deployment Guide

Complete deployment for Reflexio (FastAPI + Next.js) to AWS ECS Fargate with HTTPS, custom domain, and documentation hosting.

## Architecture Overview

```
                    ┌─────────────────────────────────────────────────────────────┐
                    │                         AWS Cloud                           │
                    │                                                             │
   Users ──────────►│  CloudFront ──► ALB ──► ECS Fargate Spot (1 Task)          │
                    │                            ├── FastAPI    :8081             │
                    │                            ├── Next.js    :8080             │
                    │                            └── Fumadocs   :8082 (/docs/*)  │
                    │                                                             │
                    │  ECR (Container Registry)                                   │
                    │  Secrets Manager (API keys)                                 │
                    │  CloudWatch (Logs)                                          │
                    └─────────────────────────────────────────────────────────────┘
```

## Monthly Cost Estimate

| Resource | Estimated Cost |
|----------|---------------|
| ECS Fargate Spot (1 task, 1 vCPU, 2GB) | ~$8-12 |
| ALB | ~$18-22 |
| CloudFront (low traffic) | ~$1-5 |
| CloudWatch Logs | ~$2-5 |
| ECR Storage | ~$1-2 |
| Route 53 / ACM | ~$0.50 |
| **Total** | **~$30-47/month** |

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
export AWS_REGION=us-west-2
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export APP_NAME=agenticmem
export ECR_REPO_NAME=agenticmem
export ECR_URI=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME
export DOMAIN_NAME=reflexio.ai
export CF_DISTRIBUTION_ID=E15WBN9QYYCSND

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
cd /Users/yilu/repos/user_profiler

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

## Step 3: Store Secrets in AWS Secrets Manager

```bash
# Create secrets JSON (DO NOT commit this)
cat > /tmp/secrets.json << 'EOF'
{
    "OPENAI_API_KEY": "sk-proj-...",
    "ANTHROPIC_API_KEY": "sk-ant-...",
    "LOGIN_SUPABASE_URL": "https://<project-id>.supabase.co",
    "LOGIN_SUPABASE_KEY": "eyJ..."
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

## Step 6: Create Security Groups

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
aws ec2 authorize-security-group-ingress --group-id $ECS_SG --protocol tcp --port 8082 --source-group $ALB_SG

echo "ALB SG: $ALB_SG"
echo "ECS SG: $ECS_SG"
```

---

## Step 7: Create Application Load Balancer

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

echo "ALB ARN: $ALB_ARN"
echo "ALB DNS: $ALB_DNS"
```

---

## Step 8: Create Target Groups

```bash
# Frontend target group (port 8080)
export TG_FRONTEND_ARN=$(aws elbv2 create-target-group \
    --name $APP_NAME-frontend-tg \
    --protocol HTTP \
    --port 8080 \
    --vpc-id $VPC_ID \
    --target-type ip \
    --health-check-path "/" \
    --health-check-interval-seconds 30 \
    --query 'TargetGroups[0].TargetGroupArn' --output text)

# API target group (port 8081)
export TG_API_ARN=$(aws elbv2 create-target-group \
    --name $APP_NAME-api-tg \
    --protocol HTTP \
    --port 8081 \
    --vpc-id $VPC_ID \
    --target-type ip \
    --health-check-path "/health" \
    --health-check-interval-seconds 30 \
    --query 'TargetGroups[0].TargetGroupArn' --output text)

# Docs target group (port 8082)
export TG_DOCS_ARN=$(aws elbv2 create-target-group \
    --name $APP_NAME-docs-tg \
    --protocol HTTP \
    --port 8082 \
    --vpc-id $VPC_ID \
    --target-type ip \
    --health-check-path "/docs" \
    --health-check-interval-seconds 30 \
    --query 'TargetGroups[0].TargetGroupArn' --output text)

echo "Frontend TG: $TG_FRONTEND_ARN"
echo "API TG: $TG_API_ARN"
echo "Docs TG: $TG_DOCS_ARN"
```

---

## Step 9: Create HTTP Listener with Routing Rules

```bash
# Create HTTP listener (default to frontend)
export LISTENER_ARN=$(aws elbv2 create-listener \
    --load-balancer-arn $ALB_ARN \
    --protocol HTTP \
    --port 80 \
    --default-actions Type=forward,TargetGroupArn=$TG_FRONTEND_ARN \
    --query 'Listeners[0].ListenerArn' --output text)

# Route /health to API
aws elbv2 create-rule \
    --listener-arn $LISTENER_ARN \
    --priority 5 \
    --conditions Field=path-pattern,Values='/health' \
    --actions Type=forward,TargetGroupArn=$TG_API_ARN

# Route /token to API
aws elbv2 create-rule \
    --listener-arn $LISTENER_ARN \
    --priority 6 \
    --conditions Field=path-pattern,Values='/token' \
    --actions Type=forward,TargetGroupArn=$TG_API_ARN

# Route /api/* to API
aws elbv2 create-rule \
    --listener-arn $LISTENER_ARN \
    --priority 10 \
    --conditions Field=path-pattern,Values='/api/*' \
    --actions Type=forward,TargetGroupArn=$TG_API_ARN

# Route /docs and /docs/* to Docs (Fumadocs)
aws elbv2 create-rule \
    --listener-arn $LISTENER_ARN \
    --priority 15 \
    --conditions Field=path-pattern,Values='/docs' \
    --actions Type=forward,TargetGroupArn=$TG_DOCS_ARN

aws elbv2 create-rule \
    --listener-arn $LISTENER_ARN \
    --priority 16 \
    --conditions Field=path-pattern,Values='/docs/*' \
    --actions Type=forward,TargetGroupArn=$TG_DOCS_ARN

echo "Listener ARN: $LISTENER_ARN"
```

---

## Step 10: Create ECS Cluster

```bash
# First-time setup: Create ECS service-linked role (one-time per AWS account)
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

## Step 11: Create CloudWatch Log Group

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

## Step 12: Create ECS Task Definition

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
                {"containerPort": 8081, "protocol": "tcp", "name": "api"},
                {"containerPort": 8082, "protocol": "tcp", "name": "docs"}
            ],
            "environment": [
                {"name": "NODE_ENV", "value": "production"},
                {"name": "ENVIRONMENT", "value": "production"},
                {"name": "RUN_MIGRATION", "value": "true"}
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

## Step 13: Create ECS Service

```bash
aws ecs create-service \
    --cluster $APP_NAME-cluster \
    --service-name $APP_NAME-service \
    --task-definition $APP_NAME-task \
    --desired-count 1 \
    --capacity-provider-strategy "capacityProvider=FARGATE_SPOT,weight=1" \
    --platform-version LATEST \
    --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_1,$SUBNET_2],securityGroups=[$ECS_SG],assignPublicIp=ENABLED}" \
    --load-balancers "targetGroupArn=$TG_FRONTEND_ARN,containerName=$APP_NAME,containerPort=8080" "targetGroupArn=$TG_API_ARN,containerName=$APP_NAME,containerPort=8081" "targetGroupArn=$TG_DOCS_ARN,containerName=$APP_NAME,containerPort=8082" \
    --deployment-configuration "minimumHealthyPercent=0,maximumPercent=100" \
    --enable-execute-command \
    --region $AWS_REGION

echo "ECS Service created with Fargate Spot"
```

---

## Step 14: Verify Deployment

```bash
# Wait for service to stabilize
aws ecs wait services-stable \
    --cluster $APP_NAME-cluster \
    --services $APP_NAME-service

# Check target health
echo "Frontend target health:"
aws elbv2 describe-target-health --target-group-arn $TG_FRONTEND_ARN

echo "API target health:"
aws elbv2 describe-target-health --target-group-arn $TG_API_ARN

echo "Docs target health:"
aws elbv2 describe-target-health --target-group-arn $TG_DOCS_ARN

# Test endpoints
echo "Frontend: http://$ALB_DNS/"
curl -I http://$ALB_DNS/

echo "API Health: http://$ALB_DNS/health"
curl http://$ALB_DNS/health
```

---

## Step 15: Request SSL Certificate (ACM)

```bash
# Request certificate for ALB (in your deployment region)
export CERT_ARN=$(aws acm request-certificate \
    --domain-name $DOMAIN_NAME \
    --subject-alternative-names "www.$DOMAIN_NAME" \
    --validation-method DNS \
    --query CertificateArn --output text \
    --region $AWS_REGION)

echo "Certificate ARN: $CERT_ARN"

# Get DNS validation records
aws acm describe-certificate \
    --certificate-arn $CERT_ARN \
    --query 'Certificate.DomainValidationOptions[*].{Domain:DomainName,Name:ResourceRecord.Name,Value:ResourceRecord.Value}' \
    --output table
```

### Add ACM Validation CNAME Records in GoDaddy

1. Log in to [GoDaddy](https://www.godaddy.com/) > **My Products** > **DNS**
2. Add CNAME record for certificate validation:
   - **Type**: CNAME
   - **Name**: The `Name` value, but **remove the domain suffix** (e.g., `_abc123` from `_abc123.reflexio.com.`)
   - **Value**: The `Value` from AWS output
   - **TTL**: 600

```bash
# Wait for validation (5-30 minutes)
aws acm wait certificate-validated --certificate-arn $CERT_ARN
echo "Certificate validated!"
```

---

## Step 16: Add HTTPS Listener

```bash
# Create HTTPS listener
export HTTPS_LISTENER_ARN=$(aws elbv2 create-listener \
    --load-balancer-arn $ALB_ARN \
    --protocol HTTPS \
    --port 443 \
    --certificates CertificateArn=$CERT_ARN \
    --default-actions Type=forward,TargetGroupArn=$TG_FRONTEND_ARN \
    --query 'Listeners[0].ListenerArn' --output text)

# Add routing rules to HTTPS listener
aws elbv2 create-rule \
    --listener-arn $HTTPS_LISTENER_ARN \
    --priority 5 \
    --conditions Field=path-pattern,Values='/health' \
    --actions Type=forward,TargetGroupArn=$TG_API_ARN

aws elbv2 create-rule \
    --listener-arn $HTTPS_LISTENER_ARN \
    --priority 6 \
    --conditions Field=path-pattern,Values='/token' \
    --actions Type=forward,TargetGroupArn=$TG_API_ARN

aws elbv2 create-rule \
    --listener-arn $HTTPS_LISTENER_ARN \
    --priority 10 \
    --conditions Field=path-pattern,Values='/api/*' \
    --actions Type=forward,TargetGroupArn=$TG_API_ARN

# Route /docs and /docs/* to Docs (Fumadocs)
aws elbv2 create-rule \
    --listener-arn $HTTPS_LISTENER_ARN \
    --priority 15 \
    --conditions Field=path-pattern,Values='/docs' \
    --actions Type=forward,TargetGroupArn=$TG_DOCS_ARN

aws elbv2 create-rule \
    --listener-arn $HTTPS_LISTENER_ARN \
    --priority 16 \
    --conditions Field=path-pattern,Values='/docs/*' \
    --actions Type=forward,TargetGroupArn=$TG_DOCS_ARN

echo "HTTPS Listener ARN: $HTTPS_LISTENER_ARN"
```

---

## Step 17: (Removed — docs now served from ECS)

> Documentation has been migrated from MkDocs (S3 static hosting) to Fumadocs (Next.js).
> Docs are now built into the Docker image and served by the ECS task on port 8082.
> The S3 bucket and related steps are no longer needed for docs hosting.
> If you previously set up S3 for MkDocs, you can clean it up (see Cleanup section).

---

## Step 18: Request CloudFront Certificate (us-east-1)

> **Important**: CloudFront requires ACM certificates in **us-east-1** region.

```bash
# Request certificate in us-east-1
export CF_CERT_ARN=$(aws acm request-certificate \
    --domain-name $DOMAIN_NAME \
    --subject-alternative-names "www.$DOMAIN_NAME" \
    --validation-method DNS \
    --query CertificateArn --output text \
    --region us-east-1)

echo "CloudFront Certificate ARN: $CF_CERT_ARN"

# Get DNS validation records (may be same as Step 15 if already added)
aws acm describe-certificate \
    --certificate-arn $CF_CERT_ARN \
    --region us-east-1 \
    --query 'Certificate.DomainValidationOptions[*].{Domain:DomainName,Name:ResourceRecord.Name,Value:ResourceRecord.Value}' \
    --output table

# Wait for validation
aws acm wait certificate-validated --certificate-arn $CF_CERT_ARN --region us-east-1
echo "CloudFront certificate validated!"
```

---

## Step 19: Create CloudFront Distribution

```bash
cat > /tmp/cloudfront-config.json << EOF
{
  "CallerReference": "$APP_NAME-$(date +%s)",
  "Aliases": {
    "Quantity": 2,
    "Items": ["$DOMAIN_NAME", "www.$DOMAIN_NAME"]
  },
  "DefaultRootObject": "",
  "Origins": {
    "Quantity": 1,
    "Items": [
      {
        "Id": "alb-origin",
        "DomainName": "$ALB_DNS",
        "CustomOriginConfig": {
          "HTTPPort": 80,
          "HTTPSPort": 443,
          "OriginProtocolPolicy": "http-only",
          "OriginSslProtocols": {"Quantity": 1, "Items": ["TLSv1.2"]}
        }
      }
    ]
  },
  "DefaultCacheBehavior": {
    "TargetOriginId": "alb-origin",
    "ViewerProtocolPolicy": "redirect-to-https",
    "AllowedMethods": {
      "Quantity": 7,
      "Items": ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"],
      "CachedMethods": {"Quantity": 2, "Items": ["GET", "HEAD"]}
    },
    "CachePolicyId": "4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
    "OriginRequestPolicyId": "216adef6-5c7f-47e4-b989-5492eafa07d3",
    "Compress": true
  },
  "CacheBehaviors": {
    "Quantity": 0
  },
  "Comment": "$APP_NAME with S3 docs",
  "Enabled": true,
  "ViewerCertificate": {
    "ACMCertificateArn": "$CF_CERT_ARN",
    "SSLSupportMethod": "sni-only",
    "MinimumProtocolVersion": "TLSv1.2_2021"
  },
  "HttpVersion": "http2"
}
EOF

export CF_DISTRIBUTION=$(aws cloudfront create-distribution \
    --distribution-config file:///tmp/cloudfront-config.json \
    --query 'Distribution.{Id:Id,DomainName:DomainName}' \
    --output json)

export CF_DISTRIBUTION_ID=$(echo $CF_DISTRIBUTION | jq -r '.Id')
export CF_DOMAIN=$(echo $CF_DISTRIBUTION | jq -r '.DomainName')

echo "CloudFront Distribution ID: $CF_DISTRIBUTION_ID"
echo "CloudFront Domain: $CF_DOMAIN"

# Wait for deployment (5-15 minutes)
echo "Waiting for CloudFront to deploy..."
aws cloudfront wait distribution-deployed --id $CF_DISTRIBUTION_ID
echo "Distribution deployed!"
```

---

## Step 20: Update DNS in GoDaddy

Update your DNS records to point to CloudFront:

1. Log in to [GoDaddy](https://www.godaddy.com/) > **DNS Management**
2. Update/Add **www** CNAME record:
   - **Type**: CNAME
   - **Name**: www
   - **Value**: Your CloudFront domain (e.g., `d1234567890.cloudfront.net`)
   - **TTL**: 600

3. For root domain, use domain forwarding to `www.$DOMAIN_NAME`

---

## Step 21: Restrict ALB to CloudFront Only

```bash
# Remove public access from ALB security group
aws ec2 revoke-security-group-ingress --group-id $ALB_SG --protocol tcp --port 80 --cidr 0.0.0.0/0
aws ec2 revoke-security-group-ingress --group-id $ALB_SG --protocol tcp --port 443 --cidr 0.0.0.0/0

# Add CloudFront managed prefix list
CF_PREFIX_LIST=$(aws ec2 describe-managed-prefix-lists \
    --filters "Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing" \
    --query "PrefixLists[0].PrefixListId" --output text)

aws ec2 authorize-security-group-ingress \
    --group-id $ALB_SG \
    --ip-permissions "IpProtocol=tcp,FromPort=80,ToPort=80,PrefixListIds=[{PrefixListId=$CF_PREFIX_LIST}]"

echo "ALB now only accepts traffic from CloudFront"
```

---

## Step 22: Verify Production Setup

```bash
echo "Testing HTTPS endpoints..."

echo "Frontend: https://$DOMAIN_NAME/"
curl -I https://$DOMAIN_NAME/

echo "API Health: https://$DOMAIN_NAME/health"
curl https://$DOMAIN_NAME/health

echo "Documentation: https://$DOMAIN_NAME/docs"
curl -I https://$DOMAIN_NAME/docs
```

---

## Updating the Application

```bash
cd /Users/yilu/repos/reflexio

# Build and push
aws ecr get-login-password --region $AWS_REGION | \
    docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

docker build --platform linux/amd64 -f docker/Dockerfile.base -t ${ECR_REPO_NAME}:latest .
docker tag ${ECR_REPO_NAME}:latest ${ECR_URI}:latest
docker push ${ECR_URI}:latest

# Force new deployment
aws ecs update-service \
    --cluster $APP_NAME-cluster \
    --service $APP_NAME-service \
    --force-new-deployment

# Wait for deployment
aws ecs wait services-stable \
    --cluster $APP_NAME-cluster \
    --services $APP_NAME-service

echo "Deployment complete!"
```

---

## Updating Documentation

Documentation is now bundled in the Docker image (Fumadocs/Next.js). To update docs, rebuild and redeploy the container:

```bash
cd /Users/yilu/repos/reflexio

# Rebuild and push (docs are built as part of the Docker image)
aws ecr get-login-password --region $AWS_REGION | \
    docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

docker build --platform linux/amd64 -f docker/Dockerfile.base -t ${ECR_REPO_NAME}:latest .
docker tag ${ECR_REPO_NAME}:latest ${ECR_URI}:latest
docker push ${ECR_URI}:latest

# Force new deployment
aws ecs update-service \
    --cluster $APP_NAME-cluster \
    --service $APP_NAME-service \
    --force-new-deployment

aws ecs wait services-stable \
    --cluster $APP_NAME-cluster \
    --services $APP_NAME-service

# Invalidate CloudFront cache for docs
aws cloudfront create-invalidation \
    --distribution-id $CF_DISTRIBUTION_ID \
    --paths "/docs" "/docs/*"

echo "Docs updated!"
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

## SSH into Container

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

## Quick Reference: Environment Variables

Save these after setup for future deployments:

```bash
echo "=== Save these values ==="
echo "export AWS_REGION=$AWS_REGION"
echo "export AWS_ACCOUNT_ID=$AWS_ACCOUNT_ID"
echo "export APP_NAME=$APP_NAME"
echo "export DOMAIN_NAME=$DOMAIN_NAME"
echo "export ECR_URI=$ECR_URI"
echo "export VPC_ID=$VPC_ID"
echo "export SUBNET_1=$SUBNET_1"
echo "export SUBNET_2=$SUBNET_2"
echo "export ALB_SG=$ALB_SG"
echo "export ECS_SG=$ECS_SG"
echo "export ALB_ARN=$ALB_ARN"
echo "export ALB_DNS=$ALB_DNS"
echo "export TG_FRONTEND_ARN=$TG_FRONTEND_ARN"
echo "export TG_API_ARN=$TG_API_ARN"
echo "export TG_DOCS_ARN=$TG_DOCS_ARN"
echo "export LISTENER_ARN=$LISTENER_ARN"
echo "export HTTPS_LISTENER_ARN=$HTTPS_LISTENER_ARN"
echo "export CERT_ARN=$CERT_ARN"
echo "export CF_CERT_ARN=$CF_CERT_ARN"
echo "export CF_DISTRIBUTION_ID=$CF_DISTRIBUTION_ID"
echo "export CF_DOMAIN=$CF_DOMAIN"
echo "export S3_BUCKET_NAME=$S3_BUCKET_NAME"  # Only if S3 still used for other assets
```

---

## Summary of URLs

| Service | URL |
|---------|-----|
| Frontend | https://reflexio.com/ |
| API | https://reflexio.com/api/* |
| API Health | https://reflexio.com/health |
| Documentation | https://reflexio.com/docs |

---

## Troubleshooting

### Task failing to start
```bash
aws ecs describe-tasks \
    --cluster $APP_NAME-cluster \
    --tasks $(aws ecs list-tasks --cluster $APP_NAME-cluster --query 'taskArns[0]' --output text) \
    --query 'tasks[0].stoppedReason'
```

### Target unhealthy
```bash
aws elbv2 describe-target-health --target-group-arn $TG_FRONTEND_ARN
aws elbv2 describe-target-health --target-group-arn $TG_API_ARN
aws elbv2 describe-target-health --target-group-arn $TG_DOCS_ARN
```

### Check service events
```bash
aws ecs describe-services \
    --cluster $APP_NAME-cluster \
    --services $APP_NAME-service \
    --query 'services[0].events[0:5]'
```

---

## Cleanup (Delete Everything)

```bash
# Delete CloudFront distribution
aws cloudfront get-distribution-config --id $CF_DISTRIBUTION_ID > /tmp/cf-config.json
ETAG=$(cat /tmp/cf-config.json | jq -r '.ETag')
cat /tmp/cf-config.json | jq '.DistributionConfig.Enabled = false' | jq '.DistributionConfig' > /tmp/cf-disable.json
aws cloudfront update-distribution --id $CF_DISTRIBUTION_ID --if-match $ETAG --distribution-config file:///tmp/cf-disable.json
aws cloudfront wait distribution-deployed --id $CF_DISTRIBUTION_ID
ETAG=$(aws cloudfront get-distribution-config --id $CF_DISTRIBUTION_ID --query 'ETag' --output text)
aws cloudfront delete-distribution --id $CF_DISTRIBUTION_ID --if-match $ETAG

# Delete CloudFront certificate
aws acm delete-certificate --certificate-arn $CF_CERT_ARN --region us-east-1

# Delete S3 bucket (if previously created for MkDocs)
aws s3 rm s3://$S3_BUCKET_NAME --recursive 2>/dev/null || true
aws s3 rb s3://$S3_BUCKET_NAME 2>/dev/null || true

# Delete ECS service
aws ecs update-service --cluster $APP_NAME-cluster --service $APP_NAME-service --desired-count 0
aws ecs delete-service --cluster $APP_NAME-cluster --service $APP_NAME-service --force

# Delete ECS cluster
aws ecs delete-cluster --cluster $APP_NAME-cluster

# Delete ALB resources
aws elbv2 delete-listener --listener-arn $HTTPS_LISTENER_ARN
aws elbv2 delete-listener --listener-arn $LISTENER_ARN
aws elbv2 delete-target-group --target-group-arn $TG_FRONTEND_ARN
aws elbv2 delete-target-group --target-group-arn $TG_API_ARN
aws elbv2 delete-target-group --target-group-arn $TG_DOCS_ARN
aws elbv2 delete-load-balancer --load-balancer-arn $ALB_ARN
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

# Delete ACM certificate
aws acm delete-certificate --certificate-arn $CERT_ARN

# Manually delete DNS records from GoDaddy

echo "Cleanup complete"
```
