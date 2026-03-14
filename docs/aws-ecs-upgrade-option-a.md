# Upgrading Option A to Production (HTTPS + Custom Domain)

This guide upgrades your existing Option A (No ALB) deployment to include:
- Application Load Balancer (ALB)
- HTTPS with AWS Certificate Manager (ACM)
- Custom domain via Route 53

## Prerequisites

You must have completed Option A from `aws-ecs-deployment-minimal.md`, meaning you have:
- ECS cluster running
- ECS service with Fargate Spot task
- VPC with public subnet
- Security group for ECS tasks
- ECR repository with your image
- Secrets in Secrets Manager

## Cost Impact

| Resource | Additional Monthly Cost |
|----------|------------------------|
| ALB | ~$18-22 |
| Route 53 Hosted Zone | ~$0.50 |
| ACM Certificate | Free |
| **Total Additional** | **~$18-23/month** |

Your new total: **~$26-38/month** (up from ~$8-15)

---

## Step 0: Set Environment Variables

Run these to restore your environment variables from the original setup:

```bash
export AWS_REGION=us-west-2
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export APP_NAME=reflexio
export ECR_REPO_NAME=reflexio
export ECR_URI=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME

# Get existing resource IDs
export VPC_ID=$(aws ec2 describe-vpcs \
    --filters "Name=tag:Name,Values=$APP_NAME-vpc" \
    --query 'Vpcs[0].VpcId' --output text)

export SUBNET_1=$(aws ec2 describe-subnets \
    --filters "Name=vpc-id,Values=$VPC_ID" "Name=availability-zone,Values=${AWS_REGION}a" \
    --query 'Subnets[0].SubnetId' --output text)

export ECS_SG=$(aws ec2 describe-security-groups \
    --filters "Name=group-name,Values=$APP_NAME-ecs-sg" \
    --query 'SecurityGroups[0].GroupId' --output text)

echo "VPC: $VPC_ID"
echo "Subnet 1: $SUBNET_1"
echo "ECS SG: $ECS_SG"
```

---

## Step 1: Create Second Subnet (Required for ALB)

ALB requires subnets in at least 2 availability zones:

```bash
# Create second subnet
export SUBNET_2=$(aws ec2 create-subnet \
    --vpc-id $VPC_ID \
    --cidr-block 10.0.2.0/24 \
    --availability-zone ${AWS_REGION}b \
    --query Subnet.SubnetId --output text)

# Enable auto-assign public IP
aws ec2 modify-subnet-attribute --subnet-id $SUBNET_2 --map-public-ip-on-launch

# Get route table and associate
export RTB_ID=$(aws ec2 describe-route-tables \
    --filters "Name=vpc-id,Values=$VPC_ID" "Name=route.gateway-id,Values=igw-*" \
    --query 'RouteTables[0].RouteTableId' --output text)

aws ec2 associate-route-table --subnet-id $SUBNET_2 --route-table-id $RTB_ID

aws ec2 create-tags --resources $SUBNET_2 --tags Key=Name,Value=$APP_NAME-subnet-2

echo "Subnet 2: $SUBNET_2"
```
Subnet 2: subnet-0893eea51ab269fdc
---

## Step 2: Create ALB Security Group

```bash
# Create ALB security group
export ALB_SG=$(aws ec2 create-security-group \
    --group-name $APP_NAME-alb-sg \
    --description "ALB security group" \
    --vpc-id $VPC_ID \
    --query GroupId --output text)

# Allow HTTP and HTTPS from internet
aws ec2 authorize-security-group-ingress --group-id $ALB_SG --protocol tcp --port 80 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id $ALB_SG --protocol tcp --port 443 --cidr 0.0.0.0/0

echo "ALB SG: $ALB_SG"
```

---

## Step 3: Update ECS Security Group

Modify the ECS security group to allow traffic from ALB (in addition to existing public access):

```bash
# Add rules to allow traffic from ALB
aws ec2 authorize-security-group-ingress --group-id $ECS_SG --protocol tcp --port 8080 --source-group $ALB_SG
aws ec2 authorize-security-group-ingress --group-id $ECS_SG --protocol tcp --port 8081 --source-group $ALB_SG

echo "ECS SG updated to allow ALB traffic"
```

> **Note**: You can optionally remove the public access rules later once ALB is confirmed working:
> ```bash
> # Optional: Remove direct public access after ALB is working
> # aws ec2 revoke-security-group-ingress --group-id $ECS_SG --protocol tcp --port 8080 --cidr 0.0.0.0/0
> # aws ec2 revoke-security-group-ingress --group-id $ECS_SG --protocol tcp --port 8081 --cidr 0.0.0.0/0
> ```

---

## Step 4: Create Application Load Balancer

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
ALB ARN: arn:aws:elasticloadbalancing:us-west-2:348297466724:loadbalancer/app/reflexio-alb/d3395fec01672eac
ALB DNS: reflexio-alb-90044493.us-west-2.elb.amazonaws.com
---

## Step 5: Create Target Groups

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

echo "Frontend TG: $TG_FRONTEND_ARN"
echo "API TG: $TG_API_ARN"
```
Frontend TG: arn:aws:elasticloadbalancing:us-west-2:348297466724:targetgroup/reflexio-frontend-tg/9695ae6494585a6d
API TG: arn:aws:elasticloadbalancing:us-west-2:348297466724:targetgroup/reflexio-api-tg/c1bd2584f35e4b11
---

## Step 6: Create HTTP Listener with Routing Rules

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

echo "Listener ARN: $LISTENER_ARN"
```
Listener ARN: arn:aws:elasticloadbalancing:us-west-2:348297466724:listener/app/reflexio-alb/d3395fec01672eac/bbd76faf36abcc1e
---

## Step 7: Update ECS Service to Use ALB

Delete the existing service and recreate it with load balancer configuration:

```bash
# Scale down existing service
aws ecs update-service \
    --cluster $APP_NAME-cluster \
    --service $APP_NAME-service \
    --desired-count 0

# Wait for tasks to drain
sleep 30

# Delete existing service
aws ecs delete-service \
    --cluster $APP_NAME-cluster \
    --service $APP_NAME-service \
    --force

# Wait for service deletion
sleep 30

# Create new service with ALB
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

echo "ECS Service recreated with ALB"
```

---

## Step 8: Verify ALB Setup

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

# Test endpoints
echo ""
echo "Testing via ALB..."
echo "Frontend: http://$ALB_DNS/"
curl -I http://$ALB_DNS/

echo ""
echo "API Health: http://$ALB_DNS/health"
curl http://$ALB_DNS/health
```
Frontend: http://reflexio-alb-90044493.us-west-2.elb.amazonaws.com/
---

## Step 9: Request SSL Certificate (ACM)

Replace `yourdomain.com` with your actual domain:

```bash
export DOMAIN_NAME=reflexio.com

# Request certificate
export CERT_ARN=$(aws acm request-certificate \
    --domain-name $DOMAIN_NAME \
    --subject-alternative-names "www.$DOMAIN_NAME" \
    --validation-method DNS \
    --query CertificateArn --output text \
    --region $AWS_REGION)

echo "Certificate ARN: $CERT_ARN"
echo ""
echo ">>> IMPORTANT: Complete DNS validation before proceeding <<<"
echo ">>> Go to AWS Console > ACM > Certificates to see DNS records to add <<<"
```

### Get DNS Validation Records

```bash
# Get the DNS validation records
aws acm describe-certificate \
    --certificate-arn $CERT_ARN \
    --query 'Certificate.DomainValidationOptions[*].{Domain:DomainName,Name:ResourceRecord.Name,Value:ResourceRecord.Value}' \
    --output table
```

Add these CNAME records to your DNS provider. For Route 53, see next step.

---

## Step 10: Set Up DNS in GoDaddy

### Get ACM Validation Records

First, get the DNS validation records needed to validate your SSL certificate:

```bash
# Get the DNS validation records
aws acm describe-certificate \
    --certificate-arn $CERT_ARN \
    --query 'Certificate.DomainValidationOptions[*].{Domain:DomainName,Name:ResourceRecord.Name,Value:ResourceRecord.Value}' \
    --output table
```

### Add ACM Validation CNAME Records in GoDaddy

1. Log in to [GoDaddy](https://www.godaddy.com/) and go to **My Products**
2. Find your domain and click **DNS** (or **Manage DNS**)
3. Click **Add** to create a new record
4. Add CNAME record(s) for certificate validation:
   - **Type**: CNAME
   - **Name**: The `Name` value from above, but **remove the domain suffix** (e.g., if the Name is `_abc123.reflexio.com.`, enter just `_abc123`)
   - **Value**: The `Value` from the AWS output (e.g., `_xyz789.acm-validations.aws.`)
   - **TTL**: 600 (or default)
5. Click **Save**

> **Note**: If you have both `reflexio.com` and `www.reflexio.com` in your certificate, you may need to add validation records for both. Often they share the same validation record.

### Wait for Certificate Validation

```bash
# Check certificate status (repeat until "ISSUED")
aws acm describe-certificate \
    --certificate-arn $CERT_ARN \
    --query 'Certificate.Status' --output text

# Wait for validation (can take 5-30 minutes)
aws acm wait certificate-validated --certificate-arn $CERT_ARN
echo "Certificate validated!"
```

---

## Step 11: Add HTTPS Listener

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

echo "HTTPS Listener ARN: $HTTPS_LISTENER_ARN"
```
HTTPS Listener ARN: arn:aws:elasticloadbalancing:us-west-2:348297466724:listener/app/reflexio-alb/d3395fec01672eac/7dd63bd9edb63336
---

## Step 12: Redirect HTTP to HTTPS

```bash
# Modify HTTP listener to redirect to HTTPS
aws elbv2 modify-listener \
    --listener-arn $LISTENER_ARN \
    --default-actions 'Type=redirect,RedirectConfig={Protocol=HTTPS,Port=443,StatusCode=HTTP_301}'

echo "HTTP now redirects to HTTPS"
```

---

## Step 13: Create DNS Records in GoDaddy

Get your ALB DNS name:

```bash
echo "ALB DNS: $ALB_DNS"
# Example: reflexio-alb-90044493.us-west-2.elb.amazonaws.com
```
ALB DNS: reflexio-alb-90044493.us-west-2.elb.amazonaws.com

### Add DNS Records in GoDaddy

1. Log in to [GoDaddy](https://www.godaddy.com/) and go to **My Products**
2. Find your domain and click **DNS** (or **Manage DNS**)

#### For Root Domain (reflexio.com)

GoDaddy doesn't support ALIAS records, so you have two options:

**Option A: Use CNAME Flattening (Recommended if available)**
- Some GoDaddy plans support this. If available:
  - **Type**: CNAME
  - **Name**: @
  - **Value**: Your ALB DNS (e.g., `reflexio-alb-90044493.us-west-2.elb.amazonaws.com`)

**Option B: Use A Record with ALB IP (Not recommended - IPs can change)**
- Get current ALB IPs: `dig +short $ALB_DNS`
- Add A records for each IP (but these may change!)

**Option C: Use Domain Forwarding**
- Forward the root domain to `www.reflexio.com`
- Then use CNAME for www (see below)

#### For WWW Subdomain (www.reflexio.com)

1. Click **Add** to create a new record
2. Configure:
   - **Type**: CNAME
   - **Name**: www
   - **Value**: Your ALB DNS (e.g., `reflexio-alb-90044493.us-west-2.elb.amazonaws.com`)
   - **TTL**: 600 (or default)
3. Click **Save**

> **Note**: DNS propagation can take up to 48 hours, but typically completes within 15-30 minutes.

### Verify DNS Propagation

```bash
# Check if DNS is propagated
dig $DOMAIN_NAME
dig www.$DOMAIN_NAME

# Or use online tools like https://dnschecker.org
```

---

## Step 14: Verify Production Setup

```bash
echo "Testing HTTPS endpoints..."
echo ""

echo "Frontend: https://$DOMAIN_NAME/"
curl -I https://$DOMAIN_NAME/

echo ""
echo "API Health: https://$DOMAIN_NAME/health"
curl https://$DOMAIN_NAME/health

echo ""
echo "HTTP Redirect Test:"
curl -I http://$DOMAIN_NAME/
```

---

## Step 15: Optional - Remove Direct Public Access

Once ALB is confirmed working, remove direct public IP access to the tasks:

```bash
# Remove public access rules from ECS security group
aws ec2 revoke-security-group-ingress --group-id $ECS_SG --protocol tcp --port 8080 --cidr 0.0.0.0/0
aws ec2 revoke-security-group-ingress --group-id $ECS_SG --protocol tcp --port 8081 --cidr 0.0.0.0/0

echo "Direct public access removed. Traffic now only flows through ALB."
```

---

## Step 16: Optional - Add CloudFront for S3-Hosted Docs

If you have documentation hosted on S3 (see `aws-s3-mkdocs-hosting.md`) and want to serve it under `yourdomain.com/docs/*` while keeping the main app on ALB, use CloudFront with multiple origins.

### Architecture

```
                    ┌─────────────┐
    domain.com ──►  │ CloudFront  │
                    └──────┬──────┘
                           │
           ┌───────────────┴───────────────┐
           │                               │
     /docs/*                        everything else
           │                               │
           ▼                               ▼
    ┌─────────────┐                ┌─────────────┐
    │  S3 Bucket  │                │     ALB     │
    │  (MkDocs)   │                │   (ECS)     │
    └─────────────┘                └─────────────┘
```

### Additional Cost

| Resource | Monthly Cost |
|----------|-------------|
| CloudFront (low traffic) | ~$1-5 |
| CloudFront (free tier, first 12 months) | Free |

### Step 16.1: Set S3 Variables

```bash
export S3_BUCKET_NAME=reflexio
export S3_WEBSITE_ENDPOINT=$S3_BUCKET_NAME.s3-website-$AWS_REGION.amazonaws.com
```

S3_WEBSITE_ENDPOINT (doc website in s3): reflexio.s3-website-us-west-2.amazonaws.com

### Step 16.2: Create ACM Certificate in us-east-1

> **Important**: CloudFront requires ACM certificates to be in **us-east-1** region, regardless of where your other resources are located.

```bash
# Request certificate in us-east-1 (required for CloudFront)
export CF_CERT_ARN=$(aws acm request-certificate \
    --domain-name $DOMAIN_NAME \
    --subject-alternative-names "www.$DOMAIN_NAME" \
    --validation-method DNS \
    --query CertificateArn --output text \
    --region us-east-1)

echo "CloudFront Certificate ARN: $CF_CERT_ARN"

# Get DNS validation records
aws acm describe-certificate \
    --certificate-arn $CF_CERT_ARN \
    --region us-east-1 \
    --query 'Certificate.DomainValidationOptions[*].{Domain:DomainName,Name:ResourceRecord.Name,Value:ResourceRecord.Value}' \
    --output table
```

Add the CNAME validation records to GoDaddy (same process as Step 10), then wait:

```bash
# Wait for validation (5-30 minutes)
aws acm wait certificate-validated --certificate-arn $CF_CERT_ARN --region us-east-1
echo "CloudFront certificate validated!"
```

> **Note**: If you already have a validated certificate in us-east-1 for this domain, you can reuse it:
> ```bash
> export CF_CERT_ARN=$(aws acm list-certificates --region us-east-1 \
>     --query "CertificateSummaryList[?DomainName=='$DOMAIN_NAME'].CertificateArn" \
>     --output text)
> ```

### Step 16.3: Upload Docs to S3 with /docs/ Prefix

Ensure your MkDocs site is uploaded under the `/docs/` path:

```bash
cd reflexio/reflexio_client

# Update mkdocs.yml to set the base URL
# Add this line: site_url: https://reflexio.com/docs/

# Build the site
mkdocs build

# Upload to docs/ prefix in S3
aws s3 sync site/ s3://$S3_BUCKET_NAME/docs/ --delete

echo "Docs uploaded to s3://$S3_BUCKET_NAME/docs/"
```

### Step 16.4: Update ALB HTTP Listener for CloudFront

CloudFront will connect to your ALB via HTTP. Currently, your ALB HTTP listener redirects to HTTPS (from Step 12), which causes a certificate mismatch error. We need to change it back to forward traffic:

```bash
# Change HTTP listener default action from redirect to forward
aws elbv2 modify-listener \
    --listener-arn $LISTENER_ARN \
    --default-actions Type=forward,TargetGroupArn=$TG_FRONTEND_ARN

# Re-add routing rules for API paths on HTTP listener
aws elbv2 create-rule \
    --listener-arn $LISTENER_ARN \
    --priority 5 \
    --conditions Field=path-pattern,Values='/health' \
    --actions Type=forward,TargetGroupArn=$TG_API_ARN

aws elbv2 create-rule \
    --listener-arn $LISTENER_ARN \
    --priority 6 \
    --conditions Field=path-pattern,Values='/token' \
    --actions Type=forward,TargetGroupArn=$TG_API_ARN

aws elbv2 create-rule \
    --listener-arn $LISTENER_ARN \
    --priority 10 \
    --conditions Field=path-pattern,Values='/api/*' \
    --actions Type=forward,TargetGroupArn=$TG_API_ARN

echo "ALB HTTP listener updated to forward traffic"
```

> **Why HTTP?** CloudFront connects to ALB using the ALB's DNS name (e.g., `reflexio-alb-*.amazonaws.com`), but your ALB's HTTPS certificate is for `reflexio.com`. This causes a certificate mismatch. Using HTTP avoids this issue and is still secure because CloudFront handles HTTPS for external users, and CloudFront-to-ALB traffic stays within AWS.

### Step 16.5: Create CloudFront Distribution Config

```bash
cat > /tmp/cloudfront-config.json << EOF
{
  "CallerReference": "$APP_NAME-multi-origin-$(date +%s)",
  "Aliases": {
    "Quantity": 2,
    "Items": ["$DOMAIN_NAME", "www.$DOMAIN_NAME"]
  },
  "DefaultRootObject": "",
  "Origins": {
    "Quantity": 2,
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
      },
      {
        "Id": "s3-docs-origin",
        "DomainName": "$S3_WEBSITE_ENDPOINT",
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
    "Quantity": 1,
    "Items": [
      {
        "PathPattern": "/docs/*",
        "TargetOriginId": "s3-docs-origin",
        "ViewerProtocolPolicy": "redirect-to-https",
        "AllowedMethods": {
          "Quantity": 2,
          "Items": ["GET", "HEAD"],
          "CachedMethods": {"Quantity": 2, "Items": ["GET", "HEAD"]}
        },
        "CachePolicyId": "658327ea-f89d-4fab-a63d-7e88639e58f6",
        "Compress": true
      }
    ]
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

echo "CloudFront config created at /tmp/cloudfront-config.json"
```

> **Note on Cache Policies**:
> - `4135ea2d-6df8-44a3-9df3-4b5a84be39ad` = CachingDisabled (for dynamic ALB content)
> - `658327ea-f89d-4fab-a63d-7e88639e58f6` = CachingOptimized (for static S3 content)
> - `216adef6-5c7f-47e4-b989-5492eafa07d3` = AllViewer (forwards all headers to origin)

### Step 16.6: Create CloudFront Distribution

```bash
export CF_DISTRIBUTION=$(aws cloudfront create-distribution \
    --distribution-config file:///tmp/cloudfront-config.json \
    --query 'Distribution.{Id:Id,DomainName:DomainName}' \
    --output json)

export CF_DISTRIBUTION_ID=$(echo $CF_DISTRIBUTION | jq -r '.Id')
export CF_DOMAIN=$(echo $CF_DISTRIBUTION | jq -r '.DomainName')

echo "CloudFront Distribution ID: $CF_DISTRIBUTION_ID"
echo "CloudFront Domain: $CF_DOMAIN"
```
CloudFront Distribution ID: E15WBN9QYYCSND
CloudFront Domain: d1l8q2vvo6ar4w.cloudfront.net

> **Note**: Distribution creation takes 5-15 minutes to deploy globally.

### Step 16.7: Wait for Distribution to Deploy

```bash
echo "Waiting for CloudFront distribution to deploy (this takes 5-15 minutes)..."
aws cloudfront wait distribution-deployed --id $CF_DISTRIBUTION_ID
echo "Distribution deployed!"
```

### Step 16.8: Update DNS to Point to CloudFront

Update your DNS records in GoDaddy to point to CloudFront instead of ALB:

1. Log in to [GoDaddy](https://www.godaddy.com/) and go to **DNS Management**
2. Update the **www** CNAME record:
   - **Type**: CNAME
   - **Name**: www
   - **Value**: Your CloudFront domain (e.g., `d1234567890.cloudfront.net`)
   - **TTL**: 600

3. For root domain, use domain forwarding to `www.$DOMAIN_NAME` or set up CNAME flattening if supported.

### Step 16.9: Verify Setup

```bash
echo "Testing endpoints..."
echo ""

echo "Main site: https://$DOMAIN_NAME/"
curl -I https://$DOMAIN_NAME/ 2>/dev/null | head -5

echo ""
echo "Documentation: https://$DOMAIN_NAME/docs/"
curl -I https://$DOMAIN_NAME/docs/ 2>/dev/null | head -5

echo ""
echo "API Health: https://$DOMAIN_NAME/health"
curl https://$DOMAIN_NAME/health
```

### Optional: Restrict ALB to CloudFront Only

After verifying CloudFront works, you can optionally restrict the ALB to only accept traffic from CloudFront by updating the ALB security group:

```bash
# Remove public HTTP/HTTPS access from ALB security group
aws ec2 revoke-security-group-ingress --group-id $ALB_SG --protocol tcp --port 80 --cidr 0.0.0.0/0
aws ec2 revoke-security-group-ingress --group-id $ALB_SG --protocol tcp --port 443 --cidr 0.0.0.0/0

# Add CloudFront managed prefix list (allows all CloudFront IPs)
CF_PREFIX_LIST=$(aws ec2 describe-managed-prefix-lists \
    --filters "Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing" \
    --query "PrefixLists[0].PrefixListId" --output text)

aws ec2 authorize-security-group-ingress \
    --group-id $ALB_SG \
    --ip-permissions "IpProtocol=tcp,FromPort=80,ToPort=80,PrefixListIds=[{PrefixListId=$CF_PREFIX_LIST}]"

echo "ALB now only accepts traffic from CloudFront"
```

> **Note**: After this change, direct ALB access (via `reflexio-alb-*.amazonaws.com`) will no longer work. All traffic must go through CloudFront.

### Updating Documentation

When you update your MkDocs documentation:

```bash
# Rebuild and upload
cd reflexio/reflexio_client
mkdocs build
aws s3 sync site/ s3://$S3_BUCKET_NAME/docs/ --delete

# Invalidate CloudFront cache for docs
aws cloudfront create-invalidation \
    --distribution-id $CF_DISTRIBUTION_ID \
    --paths "/docs/*"

echo "Docs updated and cache invalidated!"
```

### CloudFront Quick Reference

```bash
echo "=== CloudFront Values ==="
echo "export CF_CERT_ARN=$CF_CERT_ARN"
echo "export CF_DISTRIBUTION_ID=$CF_DISTRIBUTION_ID"
echo "export CF_DOMAIN=$CF_DOMAIN"
echo "export S3_BUCKET_NAME=$S3_BUCKET_NAME"
echo "export S3_WEBSITE_ENDPOINT=$S3_WEBSITE_ENDPOINT"
```

---

## Summary of URLs

| Service | URL |
|---------|-----|
| Frontend | https://reflexio.com/ |
| API | https://reflexio.com/api/* |
| API Health | https://reflexio.com/health |
| Documentation | https://reflexio.com/docs/ (if CloudFront enabled) |
| ALB (backup) | http://reflexio-alb-90044493.us-west-2.elb.amazonaws.com/ |
| S3 Docs (direct) | http://reflexio.s3-website-us-west-2.amazonaws.com/docs/ |

---

## Quick Reference: Save These Values

```bash
echo "=== Save these values ==="
echo "export AWS_REGION=$AWS_REGION"
echo "export AWS_ACCOUNT_ID=$AWS_ACCOUNT_ID"
echo "export APP_NAME=$APP_NAME"
echo "export VPC_ID=$VPC_ID"
echo "export SUBNET_1=$SUBNET_1"
echo "export SUBNET_2=$SUBNET_2"
echo "export ALB_SG=$ALB_SG"
echo "export ECS_SG=$ECS_SG"
echo "export ALB_ARN=$ALB_ARN"
echo "export ALB_DNS=$ALB_DNS"
echo "export TG_FRONTEND_ARN=$TG_FRONTEND_ARN"
echo "export TG_API_ARN=$TG_API_ARN"
echo "export LISTENER_ARN=$LISTENER_ARN"
echo "export HTTPS_LISTENER_ARN=$HTTPS_LISTENER_ARN"
echo "export CERT_ARN=$CERT_ARN"
echo "export DOMAIN_NAME=$DOMAIN_NAME"
# CloudFront values (if Step 16 completed)
echo "export CF_CERT_ARN=$CF_CERT_ARN"
echo "export CF_DISTRIBUTION_ID=$CF_DISTRIBUTION_ID"
echo "export CF_DOMAIN=$CF_DOMAIN"
echo "export S3_BUCKET_NAME=$S3_BUCKET_NAME"
```

---

## Updating the Application

After this upgrade, use the same deployment process:

```bash
cd /Users/yilu/repos/user_profiler

# Build and push
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

## Troubleshooting

### Certificate not validating
```bash
# Check certificate status
aws acm describe-certificate --certificate-arn $CERT_ARN \
    --query 'Certificate.{Status:Status,ValidationMethod:DomainValidationOptions[0].ValidationMethod}'

# Verify DNS validation record exists
dig $(aws acm describe-certificate --certificate-arn $CERT_ARN \
    --query 'Certificate.DomainValidationOptions[0].ResourceRecord.Name' --output text)
```

### Target unhealthy
```bash
# Check target health
aws elbv2 describe-target-health --target-group-arn $TG_FRONTEND_ARN
aws elbv2 describe-target-health --target-group-arn $TG_API_ARN

# Check ECS service events
aws ecs describe-services \
    --cluster $APP_NAME-cluster \
    --services $APP_NAME-service \
    --query 'services[0].events[0:5]'
```

### View logs
```bash
aws logs tail /ecs/$APP_NAME --follow
```

---

## Cleanup (Full Stack Delete)

```bash
# Delete CloudFront distribution (if Step 16 was completed)
if [ -n "$CF_DISTRIBUTION_ID" ]; then
    # First disable the distribution
    aws cloudfront get-distribution-config --id $CF_DISTRIBUTION_ID > /tmp/cf-config.json
    ETAG=$(cat /tmp/cf-config.json | jq -r '.ETag')
    cat /tmp/cf-config.json | jq '.DistributionConfig.Enabled = false' | jq '.DistributionConfig' > /tmp/cf-disable.json
    aws cloudfront update-distribution --id $CF_DISTRIBUTION_ID --if-match $ETAG --distribution-config file:///tmp/cf-disable.json

    echo "Waiting for CloudFront distribution to disable..."
    aws cloudfront wait distribution-deployed --id $CF_DISTRIBUTION_ID

    # Get new ETag and delete
    ETAG=$(aws cloudfront get-distribution-config --id $CF_DISTRIBUTION_ID --query 'ETag' --output text)
    aws cloudfront delete-distribution --id $CF_DISTRIBUTION_ID --if-match $ETAG
    echo "CloudFront distribution deleted"

    # Delete CloudFront certificate (us-east-1)
    aws acm delete-certificate --certificate-arn $CF_CERT_ARN --region us-east-1
    echo "CloudFront certificate deleted"
fi

# Delete S3 docs bucket contents (if using S3 for docs)
if [ -n "$S3_BUCKET_NAME" ]; then
    aws s3 rm s3://$S3_BUCKET_NAME --recursive
    aws s3 rb s3://$S3_BUCKET_NAME
    echo "S3 docs bucket deleted"
fi

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
aws elbv2 delete-load-balancer --load-balancer-arn $ALB_ARN

# Wait for ALB deletion
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

# Note: Manually delete DNS records from GoDaddy:
# - Remove the ACM validation CNAME record
# - Remove the CNAME record pointing to ALB

echo "Cleanup complete"
```
