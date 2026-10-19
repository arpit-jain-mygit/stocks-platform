# monitoring.tf - alarms for the API, the CloudFront site and the ingestion worker (docs/AWS.md step 2.13).
# Every alarm sends a message to one SNS topic, which emails alert_email.
#
# Not covered: a job that fails inside the worker still exits with code 0 (the error is saved on
# the job), so it does not raise an alarm. Check the job status or the /ecs log group for those.

resource "aws_sns_topic" "alerts" {
  name = "${var.project}-alerts"
}

resource "aws_sns_topic_subscription" "alerts_email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# CloudWatch alarms and EventBridge rules may publish to the topic.
data "aws_iam_policy_document" "alerts" {
  statement {
    sid       = "AllowAlarmsAndEvents"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alerts.arn]
    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com", "events.amazonaws.com"]
    }
  }
}

resource "aws_sns_topic_policy" "alerts" {
  arn    = aws_sns_topic.alerts.arn
  policy = data.aws_iam_policy_document.alerts.json
}

# --- API (Lambda) -------------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "api_errors" {
  alarm_name          = "${var.project}-api-errors"
  alarm_description   = "The API Lambda raised an error in the last 5 minutes"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.api.function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "api_throttles" {
  alarm_name          = "${var.project}-api-throttles"
  alarm_description   = "The API Lambda was throttled in the last 5 minutes"
  namespace           = "AWS/Lambda"
  metric_name         = "Throttles"
  dimensions          = { FunctionName = aws_lambda_function.api.function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# 5xx from API Gateway: the API itself failed (4xx are the callers' mistakes and are not alarmed).
resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name        = "${var.project}-api-5xx"
  alarm_description = "API Gateway returned 5xx responses in the last 5 minutes"
  namespace         = "AWS/ApiGateway"
  metric_name       = "5xx"
  dimensions = {
    ApiId = aws_apigatewayv2_api.api.id
    Stage = aws_apigatewayv2_stage.api.name
  }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# --- Ingestion worker (ECS) ---------------------------------------------------------------------
# A task that exits with an error code (crash, out of memory, killed).
resource "aws_cloudwatch_event_rule" "worker_crashed" {
  name        = "${var.project}-worker-crashed"
  description = "An ingestion worker task stopped with a non-zero exit code"
  event_pattern = jsonencode({
    source        = ["aws.ecs"]
    "detail-type" = ["ECS Task State Change"]
    detail = {
      clusterArn = [aws_ecs_cluster.worker.arn]
      lastStatus = ["STOPPED"]
      containers = { exitCode = [{ "anything-but" = 0 }] }
    }
  })
}

# A task that could not start at all (no image, no network, not enough capacity).
resource "aws_cloudwatch_event_rule" "worker_not_started" {
  name        = "${var.project}-worker-not-started"
  description = "An ingestion worker task failed to start"
  event_pattern = jsonencode({
    source        = ["aws.ecs"]
    "detail-type" = ["ECS Task State Change"]
    detail = {
      clusterArn = [aws_ecs_cluster.worker.arn]
      lastStatus = ["STOPPED"]
      stopCode   = ["TaskFailedToStart"]
    }
  })
}

resource "aws_cloudwatch_event_target" "worker_crashed" {
  rule = aws_cloudwatch_event_rule.worker_crashed.name
  arn  = aws_sns_topic.alerts.arn
}

resource "aws_cloudwatch_event_target" "worker_not_started" {
  rule = aws_cloudwatch_event_rule.worker_not_started.name
  arn  = aws_sns_topic.alerts.arn
}
