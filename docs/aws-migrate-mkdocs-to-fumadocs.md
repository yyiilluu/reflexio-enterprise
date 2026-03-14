# Migrating Docs from MkDocs (S3) to Fumadocs (ECS)

Migration steps for moving documentation hosting from MkDocs static files on S3 to Fumadocs (Next.js) running inside the ECS Fargate task.

## Before vs After

| | Before (MkDocs) | After (Fumadocs) |
|---|---|---|
| **Framework** | MkDocs + mkdocs-material | Fumadocs (Next.js) |
| **Hosting** | S3 static website | ECS Fargate (port 8082) |
| **Routing** | CloudFront → S3 origin for `/docs/*` | CloudFront → ALB → ECS for `/docs/*` |
| **Deploy flow** | `mkdocs build` → `aws s3 sync` | Docker image rebuild → ECS redeploy |
| **Content format** | Markdown + mkdocs.yml | MDX + source.config.ts |
| **Search** | MkDocs built-in | Fumadocs search API |

## Prerequisites

Ensure you have the existing deployment environment variables set:

```bash
export AWS_REGION=us-west-2
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export APP_NAME=agenticmem
export ECR_REPO_NAME=agenticmem
export ECR_URI=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME
export CF_DISTRIBUTION_ID=E15WBN9QYYCSND
export S3_BUCKET_NAME=agenticmem  # needed for cleanup
```

### Look Up Existing Infrastructure Variables

If you don't have the infra variables saved from the initial deployment, retrieve them from AWS:

```bash
# VPC
export VPC_ID=$(aws ec2 describe-vpcs \
    --filters "Name=tag:Name,Values=$APP_NAME-vpc" \
    --query 'Vpcs[0].VpcId' --output text)

# Subnets
export SUBNET_1=$(aws ec2 describe-subnets \
    --filters "Name=vpc-id,Values=$VPC_ID" "Name=availability-zone,Values=${AWS_REGION}a" \
    --query 'Subnets[0].SubnetId' --output text)

export SUBNET_2=$(aws ec2 describe-subnets \
    --filters "Name=vpc-id,Values=$VPC_ID" "Name=availability-zone,Values=${AWS_REGION}b" \
    --query 'Subnets[0].SubnetId' --output text)

# Security groups
export ALB_SG=$(aws ec2 describe-security-groups \
    --filters "Name=group-name,Values=$APP_NAME-alb-sg" "Name=vpc-id,Values=$VPC_ID" \
    --query 'SecurityGroups[0].GroupId' --output text)

export ECS_SG=$(aws ec2 describe-security-groups \
    --filters "Name=group-name,Values=$APP_NAME-ecs-sg" "Name=vpc-id,Values=$VPC_ID" \
    --query 'SecurityGroups[0].GroupId' --output text)

# ALB
export ALB_ARN=$(aws elbv2 describe-load-balancers \
    --names $APP_NAME-alb \
    --query 'LoadBalancers[0].LoadBalancerArn' --output text)

# Listeners (HTTP on port 80, HTTPS on port 443)
export LISTENER_ARN=$(aws elbv2 describe-listeners \
    --load-balancer-arn $ALB_ARN \
    --query 'Listeners[?Port==`80`].ListenerArn' --output text)

export HTTPS_LISTENER_ARN=$(aws elbv2 describe-listeners \
    --load-balancer-arn $ALB_ARN \
    --query 'Listeners[?Port==`443`].ListenerArn' --output text)

# Target groups
export TG_FRONTEND_ARN=$(aws elbv2 describe-target-groups \
    --names $APP_NAME-frontend-tg \
    --query 'TargetGroups[0].TargetGroupArn' --output text)

export TG_API_ARN=$(aws elbv2 describe-target-groups \
    --names $APP_NAME-api-tg \
    --query 'TargetGroups[0].TargetGroupArn' --output text)

# Verify all variables are set
echo "VPC:          $VPC_ID"
echo "Subnets:      $SUBNET_1, $SUBNET_2"
echo "ALB SG:       $ALB_SG"
echo "ECS SG:       $ECS_SG"
echo "ALB ARN:      $ALB_ARN"
echo "HTTP Listener:  $LISTENER_ARN"
echo "HTTPS Listener: $HTTPS_LISTENER_ARN"
echo "Frontend TG:  $TG_FRONTEND_ARN"
echo "API TG:       $TG_API_ARN"
```

> If any variable shows `None`, the resource name may differ from the defaults. Check the AWS console or use `aws ec2 describe-security-groups --filters "Name=vpc-id,Values=$VPC_ID"` to list all resources.

---

## Step 1: Add ECS Security Group Rule for Port 8082

Allow ALB to reach the new docs service on port 8082:

```bash
aws ec2 authorize-security-group-ingress \
    --group-id $ECS_SG \
    --protocol tcp \
    --port 8082 \
    --source-group $ALB_SG

echo "Added port 8082 ingress rule to ECS security group"
```

---

## Step 2: Create Docs Target Group

```bash
export TG_DOCS_ARN=$(aws elbv2 create-target-group \
    --name $APP_NAME-docs-tg \
    --protocol HTTP \
    --port 8082 \
    --vpc-id $VPC_ID \
    --target-type ip \
    --health-check-path "/docs" \
    --health-check-interval-seconds 30 \
    --query 'TargetGroups[0].TargetGroupArn' --output text)

echo "Docs TG: $TG_DOCS_ARN"
```

---

## Step 3: Add ALB Listener Rules for /docs

Add routing rules to **both** HTTP and HTTPS listeners. These rules must have **higher priority (lower number) than the default** to take precedence.

### HTTP listener

```bash
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
```

### HTTPS listener

```bash
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
```

---

## Step 4: Update ECS Task Definition

Register a new task definition revision that exposes port 8082:

```bash
# Get current task definition
aws ecs describe-task-definition \
    --task-definition $APP_NAME-task \
    --query 'taskDefinition' > /tmp/current-task-def.json

# The key change: add port 8082 to portMappings.
# Update the containerDefinitions[0].portMappings to include:
#   {"containerPort": 8082, "hostPort": 8082, "protocol": "tcp", "name": "docs"}
#
# You can edit /tmp/current-task-def.json manually or use jq:

cat /tmp/current-task-def.json | \
    jq '.containerDefinitions[0].portMappings += [{"containerPort": 8082, "hostPort": 8082, "protocol": "tcp", "name": "docs"}]' | \
    jq '{family, networkMode, requiresCompatibilities, cpu, memory, executionRoleArn, taskRoleArn, containerDefinitions}' \
    > /tmp/updated-task-def.json

aws ecs register-task-definition \
    --cli-input-json file:///tmp/updated-task-def.json \
    --region $AWS_REGION

echo "Task definition updated with port 8082"
```

---

## Step 5: Build and Push Updated Docker Image

The updated `docker/Dockerfile.base` now includes a `docs-builder` stage that builds the Fumadocs site, and `docker/supervisord.conf` includes a `[program:docs]` section that runs it on port 8082.

```bash
cd /Users/yilu/repos/reflexio

# Login to ECR
aws ecr get-login-password --region $AWS_REGION | \
    docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# Build image (includes Fumadocs build in docs-builder stage)
docker build --platform linux/amd64 -f docker/Dockerfile.base -t ${ECR_REPO_NAME}:latest .

# Tag and push
docker tag ${ECR_REPO_NAME}:latest ${ECR_URI}:latest
docker push ${ECR_URI}:latest

echo "Image pushed with Fumadocs support"
```

---

## Step 6: Update ECS Service with Docs Target Group

The ECS service needs to register the new docs target group. Unfortunately, `update-service` cannot add new load balancer target groups to an existing service — you must **delete and recreate** the service.

```bash
# Scale down
aws ecs update-service \
    --cluster $APP_NAME-cluster \
    --service $APP_NAME-service \
    --desired-count 0

# Wait for tasks to drain
aws ecs wait services-stable \
    --cluster $APP_NAME-cluster \
    --services $APP_NAME-service

# Delete the service
aws ecs delete-service \
    --cluster $APP_NAME-cluster \
    --service $APP_NAME-service

# Recreate with all three target groups
aws ecs create-service \
    --cluster $APP_NAME-cluster \
    --service-name $APP_NAME-service \
    --task-definition $APP_NAME-task \
    --desired-count 1 \
    --capacity-provider-strategy "capacityProvider=FARGATE_SPOT,weight=1" \
    --platform-version LATEST \
    --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_1,$SUBNET_2],securityGroups=[$ECS_SG],assignPublicIp=ENABLED}" \
    --load-balancers \
        "targetGroupArn=$TG_FRONTEND_ARN,containerName=$APP_NAME,containerPort=8080" \
        "targetGroupArn=$TG_API_ARN,containerName=$APP_NAME,containerPort=8081" \
        "targetGroupArn=$TG_DOCS_ARN,containerName=$APP_NAME,containerPort=8082" \
    --deployment-configuration "minimumHealthyPercent=0,maximumPercent=100" \
    --enable-execute-command \
    --region $AWS_REGION

echo "ECS Service recreated with docs target group"

# Wait for stabilization
aws ecs wait services-stable \
    --cluster $APP_NAME-cluster \
    --services $APP_NAME-service
```

> **Downtime note**: This causes a brief service interruption while the service is deleted and recreated. Plan for ~2-5 minutes of downtime.

---

## Step 7: Update CloudFront Distribution

Remove the S3 docs origin and its cache behaviors. All `/docs/*` traffic now goes through the ALB origin.

```bash
# Get current config
aws cloudfront get-distribution-config --id $CF_DISTRIBUTION_ID > /tmp/cf-config.json
ETAG=$(jq -r '.ETag' /tmp/cf-config.json)

# Update: remove S3 origin and /docs cache behaviors
# The ALB origin already handles /docs/* via the ALB listener rules
jq '.DistributionConfig' /tmp/cf-config.json | \
    jq '.Origins.Items = [.Origins.Items[] | select(.Id != "s3-docs-origin")]' | \
    jq '.Origins.Quantity = (.Origins.Items | length)' | \
    jq '.CacheBehaviors.Items = [.CacheBehaviors.Items[] | select(.PathPattern | startswith("/docs") | not)]' | \
    jq '.CacheBehaviors.Quantity = (.CacheBehaviors.Items | length)' \
    > /tmp/cf-updated.json

aws cloudfront update-distribution \
    --id $CF_DISTRIBUTION_ID \
    --if-match $ETAG \
    --distribution-config file:///tmp/cf-updated.json

echo "CloudFront updated — S3 docs origin removed"

# Wait for deployment
aws cloudfront wait distribution-deployed --id $CF_DISTRIBUTION_ID
echo "CloudFront deployment complete"
```

---

## Step 8: Verify

```bash
echo "=== Target Group Health ==="
echo "Frontend:"
aws elbv2 describe-target-health --target-group-arn $TG_FRONTEND_ARN \
    --query 'TargetHealthDescriptions[*].TargetHealth.State' --output text

echo "API:"
aws elbv2 describe-target-health --target-group-arn $TG_API_ARN \
    --query 'TargetHealthDescriptions[*].TargetHealth.State' --output text

echo "Docs:"
aws elbv2 describe-target-health --target-group-arn $TG_DOCS_ARN \
    --query 'TargetHealthDescriptions[*].TargetHealth.State' --output text

echo ""
echo "=== Endpoint Tests ==="
echo "Docs homepage:"
curl -s -o /dev/null -w "%{http_code}" https://reflexio.ai/docs

echo ""
echo "Docs subpage:"
curl -s -o /dev/null -w "%{http_code}" https://reflexio.ai/docs/getting-started/quickstart

echo ""
echo "Frontend (should still work):"
curl -s -o /dev/null -w "%{http_code}" https://reflexio.ai/

echo ""
echo "API health (should still work):"
curl -s https://reflexio.ai/health
```

All endpoints should return 200.

---

## Step 9: Clean Up Old S3 MkDocs Resources

Once you've confirmed Fumadocs is serving correctly, remove the old S3 bucket:

```bash
# Delete all objects in the bucket
aws s3 rm s3://$S3_BUCKET_NAME --recursive

# Delete the bucket
aws s3 rb s3://$S3_BUCKET_NAME

echo "S3 bucket $S3_BUCKET_NAME deleted"
```

> If the S3 bucket is used for other assets besides docs, only delete the `/docs/` prefix:
> ```bash
> aws s3 rm s3://$S3_BUCKET_NAME/docs/ --recursive
> ```

---

## Rollback Plan

If something goes wrong, you can revert to MkDocs:

1. **Re-add S3 origin to CloudFront** — restore the S3 docs origin and `/docs*` cache behaviors
2. **Remove ALB `/docs` listener rules** — delete the priority 15/16 rules from both listeners
3. **Re-upload MkDocs to S3** — `mkdocs build && aws s3 sync site/ s3://$S3_BUCKET_NAME/docs/ --delete`
4. **Invalidate CloudFront** — `aws cloudfront create-invalidation --distribution-id $CF_DISTRIBUTION_ID --paths "/docs" "/docs/*"`

The ECS service changes (port 8082, docs target group) are harmless to keep even if you rollback — the port just won't receive traffic.

---

## Files Changed in This Migration

| File | Change |
|------|--------|
| `docker/Dockerfile.base` | Added `docs-builder` stage; copies built docs into image; exposes port 8082 |
| `docker/Dockerfile.update` | Removed `public_docs` copy to preserve pre-built docs from base |
| `docker/supervisord.conf` | Added `[program:docs]` running Fumadocs on port 8082 (256MB memory) |
| `reflexio/scripts/update_docs.sh` | Rewritten: now rebuilds Docker image and redeploys ECS |
| `docs/aws-ecs-deployment.md` | Updated architecture, removed S3 steps, added docs target group/routing |

---

## Save Updated Environment Variables

After migration, save the new variable:

```bash
echo "export TG_DOCS_ARN=$TG_DOCS_ARN"
```

Add this alongside your other saved environment variables from the initial deployment.
