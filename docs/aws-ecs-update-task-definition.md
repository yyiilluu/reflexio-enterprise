# Updating ECS Task Definition

Step-by-step guide for updating the ECS Fargate task definition (CPU, memory, environment variables, secrets, health checks, etc.).

## Prerequisites

Set your environment variables:

```bash
export AWS_REGION=us-west-2
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export APP_NAME=agenticmem
export ECR_REPO_NAME=agenticmem
export ECR_URI=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME
```

---

## Step 1: View Current Task Definition

```bash
# Get the latest task definition revision
aws ecs describe-task-definition \
    --task-definition $APP_NAME-task \
    --region $AWS_REGION \
    --query 'taskDefinition.{cpu:cpu,memory:memory,revision:revision}' \
    --output table
```

To see the full JSON (useful as a starting point for edits):

```bash
aws ecs describe-task-definition \
    --task-definition $APP_NAME-task \
    --region $AWS_REGION \
    --query 'taskDefinition' \
    --output json > /tmp/current-task-def.json

cat /tmp/current-task-def.json
```

---

## Step 2: Get Role ARNs

```bash
export EXECUTION_ROLE_ARN=$(aws iam get-role \
    --role-name ecsTaskExecutionRole-$APP_NAME \
    --query Role.Arn --output text)

export TASK_ROLE_ARN=$(aws iam get-role \
    --role-name ecsTaskRole-$APP_NAME \
    --query Role.Arn --output text)

export SECRET_ARN=$(aws secretsmanager describe-secret \
    --secret-id $APP_NAME/prod/env \
    --query ARN --output text --region $AWS_REGION)

echo "Execution Role: $EXECUTION_ROLE_ARN"
echo "Task Role: $TASK_ROLE_ARN"
echo "Secret ARN: $SECRET_ARN"
```

---

## Step 3: Register New Task Definition

Edit the values below as needed (cpu, memory, environment, secrets, etc.), then register:

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
                {"name": "ENVIRONMENT", "value": "production"},
                {"name": "RUN_MIGRATION", "value": "true"}
            ],
            "secrets": [
                {"name": "OPENAI_API_KEY", "valueFrom": "${SECRET_ARN}:OPENAI_API_KEY::"},
                {"name": "ANTHROPIC_API_KEY", "valueFrom": "${SECRET_ARN}:ANTHROPIC_API_KEY::"},
                {"name": "LOGIN_SUPABASE_URL", "valueFrom": "${SECRET_ARN}:LOGIN_SUPABASE_URL::"},
                {"name": "LOGIN_SUPABASE_KEY", "valueFrom": "${SECRET_ARN}:LOGIN_SUPABASE_KEY::"},
                {"name": "OPENROUTER_API_KEY", "valueFrom": "${SECRET_ARN}:OPENROUTER_API_KEY::"},
                {"name": "MINIMAX_API_KEY", "valueFrom": "${SECRET_ARN}:MINIMAX_API_KEY::"}
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

### Fargate CPU/Memory Valid Combinations

| CPU (units) | Memory (MiB) options |
|-------------|---------------------|
| 256 (0.25 vCPU) | 512, 1024, 2048 |
| 512 (0.5 vCPU) | 1024, 2048, 3072, 4096 |
| 1024 (1 vCPU) | 2048, 3072, 4096, 5120, 6144, 7168, 8192 |
| 2048 (2 vCPU) | 4096 – 16384 (in 1024 increments) |
| 4096 (4 vCPU) | 8192 – 30720 (in 1024 increments) |

---

## Step 4: Update ECS Service to Use New Task Definition

```bash
aws ecs update-service \
    --cluster $APP_NAME-cluster \
    --service $APP_NAME-service \
    --task-definition $APP_NAME-task \
    --force-new-deployment \
    --region $AWS_REGION

echo "Service update initiated"
```

---

## Step 5: Wait for Deployment

```bash
echo "Waiting for service to stabilize..."

aws ecs wait services-stable \
    --cluster $APP_NAME-cluster \
    --services $APP_NAME-service \
    --region $AWS_REGION

echo "Deployment complete!"
```

---

## Step 6: Verify

```bash
# Check the running task is using the new revision
aws ecs describe-services \
    --cluster $APP_NAME-cluster \
    --services $APP_NAME-service \
    --region $AWS_REGION \
    --query 'services[0].{taskDef:taskDefinition,runningCount:runningCount,desiredCount:desiredCount,status:status}' \
    --output table

# Check target group health
export TG_API_ARN=$(aws elbv2 describe-target-groups \
    --names $APP_NAME-api-tg \
    --query 'TargetGroups[0].TargetGroupArn' --output text 2>/dev/null)

aws elbv2 describe-target-health --target-group-arn $TG_API_ARN

# Tail recent logs
aws logs tail /ecs/$APP_NAME --since 5m --region $AWS_REGION
```

---

## Troubleshooting

### Deployment stuck or failing

```bash
# Check service events for errors
aws ecs describe-services \
    --cluster $APP_NAME-cluster \
    --services $APP_NAME-service \
    --query 'services[0].events[0:5]' \
    --region $AWS_REGION

# Check stopped task reason
TASK_ARN=$(aws ecs list-tasks \
    --cluster $APP_NAME-cluster \
    --service-name $APP_NAME-service \
    --desired-status STOPPED \
    --query 'taskArns[0]' --output text \
    --region $AWS_REGION)

aws ecs describe-tasks \
    --cluster $APP_NAME-cluster \
    --tasks $TASK_ARN \
    --query 'tasks[0].{stoppedReason:stoppedReason,stopCode:stopCode}' \
    --region $AWS_REGION
```

### Rollback to previous revision

```bash
# List recent revisions
aws ecs list-task-definitions \
    --family-prefix $APP_NAME-task \
    --sort DESC \
    --query 'taskDefinitionArns[0:5]' \
    --region $AWS_REGION

# Rollback to a specific revision (replace N with revision number)
aws ecs update-service \
    --cluster $APP_NAME-cluster \
    --service $APP_NAME-service \
    --task-definition $APP_NAME-task:N \
    --force-new-deployment \
    --region $AWS_REGION
```

### Clean up old task definition revisions

```bash
# Deregister a specific old revision (replace N)
aws ecs deregister-task-definition \
    --task-definition $APP_NAME-task:N \
    --region $AWS_REGION
```
