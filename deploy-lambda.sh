#!/bin/bash

# deploy-lambda.sh
# Script to build, tag, push to ECR, and update Lambda function

set -e  # Exit on any error

# Configuration - Update these variables to match your setup
AWS_REGION="ca-central-1"  # Update if your region is different
ECR_REPOSITORY_NAME="ragpdfingest"  # Your existing ECR repository
LAMBDA_FUNCTION_NAME="ragPdfIngest"  # Your existing Lambda function
IMAGE_TAG="latest"

echo "🚀 Starting Lambda deployment process..."

# Get AWS account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
if [ -z "$AWS_ACCOUNT_ID" ]; then
    echo "❌ Failed to get AWS account ID. Make sure you're authenticated with AWS CLI"
    exit 1
fi

echo "📋 Configuration:"
echo "   AWS Account ID: $AWS_ACCOUNT_ID"
echo "   AWS Region: $AWS_REGION"
echo "   ECR Repository: $ECR_REPOSITORY_NAME"
echo "   Lambda Function: $LAMBDA_FUNCTION_NAME"
echo "   Image Tag: $IMAGE_TAG"
echo ""

# Full ECR URI
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY_NAME}"

# Step 1: Build Docker image
echo "🔨 Building Docker image..."
docker build --platform linux/amd64 --provenance=false --sbom=false -t ragpdfingest:${IMAGE_TAG} .

# Step 2: Tag image for ECR
echo "🏷️  Tagging image for ECR..."
docker tag ragpdfingest:${IMAGE_TAG} ${ECR_URI}:${IMAGE_TAG}

# Step 3: Login to ECR
echo "🔐 Logging into ECR..."
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_URI}

# Step 4: Create ECR repository if it doesn't exist
echo "📦 Ensuring ECR repository exists..."
aws ecr describe-repositories --repository-names ${ECR_REPOSITORY_NAME} --region ${AWS_REGION} 2>/dev/null || \
aws ecr create-repository --repository-name ${ECR_REPOSITORY_NAME} --region ${AWS_REGION}

# Step 5: Push image to ECR
echo "⬆️  Pushing image to ECR..."
docker push ${ECR_URI}:${IMAGE_TAG}

# Step 6: Update Lambda function
echo "🔄 Updating Lambda function..."
aws lambda update-function-code \
    --function-name ${LAMBDA_FUNCTION_NAME} \
    --image-uri ${ECR_URI}:${IMAGE_TAG} \
    --region ${AWS_REGION}

echo ""
echo "✅ Deployment completed successfully!"
echo "   Image URI: ${ECR_URI}:${IMAGE_TAG}"
echo "   Lambda function '${LAMBDA_FUNCTION_NAME}' has been updated"

# Step 7: Wait for function to be updated and test if requested
echo ""
echo "⏳ Waiting for Lambda function to be updated..."
aws lambda wait function-updated --function-name ${LAMBDA_FUNCTION_NAME} --region ${AWS_REGION}

echo "✅ Lambda function is now updated and ready!"
echo ""
echo "💡 You can now test your Lambda function with PDF uploads to S3"
echo "💡 Monitor logs with: aws logs tail /aws/lambda/${LAMBDA_FUNCTION_NAME} --follow --region ${AWS_REGION}"
