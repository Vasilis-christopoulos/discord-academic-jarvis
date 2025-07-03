#!/bin/bash

# setup_monitoring.sh
# Script to set up CloudWatch monitoring and alerts for the Lambda function

set -e

# Configuration
LAMBDA_FUNCTION_NAME="ragPdfIngest"
AWS_REGION="ca-central-1"
SNS_TOPIC_NAME="lambda-pdf-processing-alerts"
ALARM_PREFIX="PDF-Lambda"

echo "🔍 Setting up monitoring for Lambda function: $LAMBDA_FUNCTION_NAME"

# Create SNS topic for alerts (if it doesn't exist)
echo "📧 Creating SNS topic for alerts..."
SNS_TOPIC_ARN=$(aws sns create-topic --name "$SNS_TOPIC_NAME" --region "$AWS_REGION" --query 'TopicArn' --output text)
echo "SNS Topic ARN: $SNS_TOPIC_ARN"

# Optional: Subscribe your email to the topic (uncomment and replace with your email)
# aws sns subscribe --topic-arn "$SNS_TOPIC_ARN" --protocol email --notification-endpoint your-email@example.com --region "$AWS_REGION"

# Create CloudWatch alarms

# 1. Memory Usage Alarm
echo "💾 Creating memory usage alarm..."
aws cloudwatch put-metric-alarm \
  --alarm-name "${ALARM_PREFIX}-Memory-High" \
  --alarm-description "Lambda memory usage above 85%" \
  --metric-name "MemoryUtilization" \
  --namespace "AWS/Lambda" \
  --statistic "Maximum" \
  --period 300 \
  --threshold 85 \
  --comparison-operator "GreaterThanThreshold" \
  --evaluation-periods 2 \
  --alarm-actions "$SNS_TOPIC_ARN" \
  --dimensions Name=FunctionName,Value="$LAMBDA_FUNCTION_NAME" \
  --region "$AWS_REGION"

# 2. Error Rate Alarm
echo "❌ Creating error rate alarm..."
aws cloudwatch put-metric-alarm \
  --alarm-name "${ALARM_PREFIX}-Error-Rate-High" \
  --alarm-description "Lambda error rate above 10%" \
  --metric-name "ErrorRate" \
  --namespace "AWS/Lambda" \
  --statistic "Average" \
  --period 300 \
  --threshold 10 \
  --comparison-operator "GreaterThanThreshold" \
  --evaluation-periods 1 \
  --alarm-actions "$SNS_TOPIC_ARN" \
  --dimensions Name=FunctionName,Value="$LAMBDA_FUNCTION_NAME" \
  --region "$AWS_REGION"

# 3. Duration Alarm (for timeouts)
echo "⏱️  Creating duration alarm..."
aws cloudwatch put-metric-alarm \
  --alarm-name "${ALARM_PREFIX}-Duration-High" \
  --alarm-description "Lambda duration approaching timeout" \
  --metric-name "Duration" \
  --namespace "AWS/Lambda" \
  --statistic "Maximum" \
  --period 300 \
  --threshold 800000 \
  --comparison-operator "GreaterThanThreshold" \
  --evaluation-periods 1 \
  --alarm-actions "$SNS_TOPIC_ARN" \
  --dimensions Name=FunctionName,Value="$LAMBDA_FUNCTION_NAME" \
  --region "$AWS_REGION"

# 4. Throttle Alarm
echo "🚦 Creating throttle alarm..."
aws cloudwatch put-metric-alarm \
  --alarm-name "${ALARM_PREFIX}-Throttles" \
  --alarm-description "Lambda function being throttled" \
  --metric-name "Throttles" \
  --namespace "AWS/Lambda" \
  --statistic "Sum" \
  --period 300 \
  --threshold 1 \
  --comparison-operator "GreaterThanOrEqualToThreshold" \
  --evaluation-periods 1 \
  --alarm-actions "$SNS_TOPIC_ARN" \
  --dimensions Name=FunctionName,Value="$LAMBDA_FUNCTION_NAME" \
  --region "$AWS_REGION"

# 5. Custom metrics for our enhanced monitoring
echo "📊 Creating custom metric filters..."

# Create log group if it doesn't exist
LOG_GROUP_NAME="/aws/lambda/$LAMBDA_FUNCTION_NAME"
aws logs create-log-group --log-group-name "$LOG_GROUP_NAME" --region "$AWS_REGION" 2>/dev/null || true

# Metric filter for memory warnings
aws logs put-metric-filter \
  --log-group-name "$LOG_GROUP_NAME" \
  --filter-name "${ALARM_PREFIX}-Memory-Warnings" \
  --filter-pattern "[time, request_id, level=\"WARNING\", location, message=\"*memory*\"]" \
  --metric-transformations \
    metricName="MemoryWarnings",metricNamespace="CustomLambda/PDFProcessing",metricValue="1",defaultValue=0 \
  --region "$AWS_REGION"

# Metric filter for fallback processing
aws logs put-metric-filter \
  --log-group-name "$LOG_GROUP_NAME" \
  --filter-name "${ALARM_PREFIX}-Fallback-Usage" \
  --filter-pattern "[time, request_id, level, location, message=\"*fallback*\"]" \
  --metric-transformations \
    metricName="FallbackProcessing",metricNamespace="CustomLambda/PDFProcessing",metricValue="1",defaultValue=0 \
  --region "$AWS_REGION"

# Metric filter for processing failures
aws logs put-metric-filter \
  --log-group-name "$LOG_GROUP_NAME" \
  --filter-name "${ALARM_PREFIX}-Processing-Failures" \
  --filter-pattern "[time, request_id, level=\"ERROR\", location, message=\"*Failed to process*\"]" \
  --metric-transformations \
    metricName="ProcessingFailures",metricNamespace="CustomLambda/PDFProcessing",metricValue="1",defaultValue=0 \
  --region "$AWS_REGION"

# Create alarm for custom metrics
echo "🚨 Creating custom metric alarms..."

# Alarm for frequent fallback usage (indicates performance issues)
aws cloudwatch put-metric-alarm \
  --alarm-name "${ALARM_PREFIX}-Fallback-Usage-High" \
  --alarm-description "High usage of fallback processing" \
  --metric-name "FallbackProcessing" \
  --namespace "CustomLambda/PDFProcessing" \
  --statistic "Sum" \
  --period 3600 \
  --threshold 5 \
  --comparison-operator "GreaterThanThreshold" \
  --evaluation-periods 1 \
  --alarm-actions "$SNS_TOPIC_ARN" \
  --region "$AWS_REGION" \
  --treat-missing-data "notBreaching"

# Alarm for processing failures
aws cloudwatch put-metric-alarm \
  --alarm-name "${ALARM_PREFIX}-Processing-Failures" \
  --alarm-description "PDF processing failures detected" \
  --metric-name "ProcessingFailures" \
  --namespace "CustomLambda/PDFProcessing" \
  --statistic "Sum" \
  --period 900 \
  --threshold 2 \
  --comparison-operator "GreaterThanThreshold" \
  --evaluation-periods 1 \
  --alarm-actions "$SNS_TOPIC_ARN" \
  --region "$AWS_REGION" \
  --treat-missing-data "notBreaching"

echo ""
echo "✅ Monitoring setup completed!"
echo ""
echo "📋 Summary:"
echo "  SNS Topic: $SNS_TOPIC_ARN"
echo "  Alarms created:"
echo "    - Memory usage > 85%"
echo "    - Error rate > 10%"
echo "    - Duration > 800 seconds"
echo "    - Throttles detected"
echo "    - High fallback usage"
echo "    - Processing failures"
echo ""
echo "💡 To subscribe to alerts, run:"
echo "  aws sns subscribe --topic-arn '$SNS_TOPIC_ARN' --protocol email --notification-endpoint your-email@example.com --region '$AWS_REGION'"
echo ""
echo "📊 To view metrics in CloudWatch console:"
echo "  https://console.aws.amazon.com/cloudwatch/home?region=$AWS_REGION#alarmsV2:"
