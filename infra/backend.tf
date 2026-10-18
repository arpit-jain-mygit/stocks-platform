# backend.tf - the API: IAM role, Lambda function, and HTTP API (docs/AWS.md step 2.9).
#
# Request path: browser -> CloudFront (step 2.10) -> this HTTP API -> Lambda -> FastAPI app.
# Lambda only answers requests (questions, job status, upload links). PDF ingestion runs in an
# ECS worker task (step 2.12), so INGEST_MODE is "worker" here.

# --- Role: what the API may use ---------------------------------------------------------------
data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "api" {
  name               = "${var.project}-api"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "api_logs" {
  role       = aws_iam_role.api.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "api" {
  # Secrets (SecureString parameters under /stocks-insights/) and the key that decrypts them.
  statement {
    actions   = ["ssm:GetParametersByPath", "ssm:GetParameter", "ssm:GetParameters"]
    resources = ["arn:aws:ssm:${var.aws_region}:${var.account_id}:parameter/${var.project}/*"]
  }
  statement {
    actions   = ["kms:Decrypt"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${var.aws_region}.amazonaws.com"]
    }
  }
  # Page and vector caches.
  statement {
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.cache.arn}/*"]
  }
  # Uploads: read them, and create presigned upload links (PutObject).
  statement {
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.uploads.arn}/*"]
  }
  # Jobs table.
  statement {
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.jobs.arn]
  }
}

resource "aws_iam_role_policy" "api" {
  name   = "${var.project}-api"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api.json
}

# --- Function ----------------------------------------------------------------------------------
resource "aws_lambda_function" "api" {
  function_name    = "${var.project}-api"
  role             = aws_iam_role.api.arn
  runtime          = "python3.14"
  architectures    = ["arm64"]
  handler          = "api.lambda_handler.handler"
  memory_size      = 2048
  timeout          = 60
  s3_bucket        = aws_s3_bucket.artifacts.id
  s3_key           = aws_s3_object.api_package.key
  source_code_hash = filebase64sha256("${path.module}/../backend/dist/stocks-insights-api.zip")

  environment {
    variables = {
      SECRETS_FROM_SSM         = "true"
      CACHE_BACKEND            = "s3"
      CACHE_BUCKET             = aws_s3_bucket.cache.id
      JOB_BACKEND              = "dynamodb"
      JOBS_TABLE               = aws_dynamodb_table.jobs.name
      UPLOAD_BUCKET            = aws_s3_bucket.uploads.id
      INGEST_MODE              = "worker"
      ENABLE_RISKY_DELETE_APIS = "false"
      ENABLE_BACKUP_APIS       = "false"
    }
  }
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${aws_lambda_function.api.function_name}"
  retention_in_days = 30
}

# --- HTTP API: the public entry point (CloudFront will sit in front of it in step 2.10) ------
resource "aws_apigatewayv2_api" "api" {
  name          = "${var.project}-api"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "api" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "api" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.api.id}"
}

resource "aws_apigatewayv2_stage" "api" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "api_from_gateway" {
  statement_id  = "AllowHttpApiInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}
