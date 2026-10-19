# worker.tf - the ingestion worker (docs/AWS.md step 2.12).
#
# The API (Lambda) starts one Fargate task per upload (backend/utils/worker_dispatch.py). The task
# runs `python -m ingest.worker`: reads the PDF from the uploads bucket, ingests it, and writes the
# result to the jobs table. Tasks have no inbound ports; they only call out to Gemini, Qdrant,
# Supabase and AWS.
#
# The image is built by CodeBuild from backend/Dockerfile and pushed to ECR (scripts/build_worker_image.sh).
# Docker is not needed on your Mac.

# --- Network: the default VPC (public subnets, no NAT gateway) --------------------------------
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_security_group" "worker" {
  name        = "${var.project}-worker"
  description = "Ingestion worker: outbound only"
  vpc_id      = data.aws_vpc.default.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# --- Image repository ---------------------------------------------------------------------------
resource "aws_ecr_repository" "worker" {
  name                 = "${var.project}-worker"
  image_tag_mutability = "MUTABLE"
  force_delete         = false

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "worker" {
  repository = aws_ecr_repository.worker.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "keep the last 5 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = { type = "expire" }
    }]
  })
}

# --- Image builder: CodeBuild (no Docker on your Mac) ------------------------------------------
data "aws_iam_policy_document" "codebuild_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["codebuild.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "codebuild" {
  name               = "${var.project}-worker-build"
  assume_role_policy = data.aws_iam_policy_document.codebuild_assume.json
}

data "aws_iam_policy_document" "codebuild" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:${var.aws_region}:${var.account_id}:log-group:/aws/codebuild/${var.project}-worker-build*"]
  }
  statement {
    sid       = "Login"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    sid = "Push"
    actions = [
      "ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage", "ecr:CompleteLayerUpload",
      "ecr:GetDownloadUrlForLayer", "ecr:InitiateLayerUpload",
      "ecr:PutImage", "ecr:UploadLayerPart",
    ]
    resources = [aws_ecr_repository.worker.arn]
  }
  statement {
    sid       = "Source"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.artifacts.arn}/build/*"]
  }
}

resource "aws_iam_role_policy" "codebuild" {
  name   = "${var.project}-worker-build"
  role   = aws_iam_role.codebuild.id
  policy = data.aws_iam_policy_document.codebuild.json
}

resource "aws_codebuild_project" "worker" {
  name          = "${var.project}-worker-build"
  service_role  = aws_iam_role.codebuild.arn
  build_timeout = 30

  # The source is the backend folder, zipped by scripts/build_worker_image.sh and uploaded to build/.
  source {
    type      = "S3"
    location  = "${aws_s3_bucket.artifacts.id}/build/worker-src.zip"
    buildspec = <<-EOT
      version: 0.2
      phases:
        pre_build:
          commands:
            - aws ecr get-login-password --region $AWS_DEFAULT_REGION | docker login --username AWS --password-stdin $REGISTRY
        build:
          commands:
            - docker build -t $REPO_URL:$IMAGE_TAG .
        post_build:
          commands:
            - docker push $REPO_URL:$IMAGE_TAG
            - docker tag $REPO_URL:$IMAGE_TAG $REPO_URL:latest
            - docker push $REPO_URL:latest
    EOT
  }

  artifacts {
    type = "NO_ARTIFACTS"
  }

  environment {
    compute_type    = "BUILD_GENERAL1_SMALL"
    image           = "aws/codebuild/standard:7.0"
    type            = "LINUX_CONTAINER"
    privileged_mode = true # needed for docker build

    environment_variable {
      name  = "REGISTRY"
      value = split("/", aws_ecr_repository.worker.repository_url)[0]
    }
    environment_variable {
      name  = "REPO_URL"
      value = aws_ecr_repository.worker.repository_url
    }
    environment_variable {
      name  = "IMAGE_TAG"
      value = "manual"
    }
  }
}

# --- Runtime: ECS cluster, task roles, and the task definition --------------------------------
resource "aws_ecs_cluster" "worker" {
  name = var.project
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/${var.project}-worker"
  retention_in_days = 30
}

data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# Execution role: lets ECS pull the image and write the logs.
resource "aws_iam_role" "worker_execution" {
  name               = "${var.project}-worker-exec"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "worker_execution" {
  role       = aws_iam_role.worker_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Task role: what the running code may use (same resources the API uses, plus the uploads read).
resource "aws_iam_role" "worker" {
  name               = "${var.project}-worker"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

data "aws_iam_policy_document" "worker" {
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
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.uploads.arn}/*"]
  }
  statement {
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.cache.arn}/*"]
  }
  # Without ListBucket, a missing cache object is "access denied" instead of "not found".
  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.cache.arn]
  }
  statement {
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.jobs.arn]
  }
}

resource "aws_iam_role_policy" "worker" {
  name   = "${var.project}-worker"
  role   = aws_iam_role.worker.id
  policy = data.aws_iam_policy_document.worker.json
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${var.project}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "2048"
  memory                   = "4096"
  execution_role_arn       = aws_iam_role.worker_execution.arn
  task_role_arn            = aws_iam_role.worker.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name      = "worker"
    image     = "${aws_ecr_repository.worker.repository_url}:latest"
    essential = true
    command   = ["python", "-m", "ingest.worker"]
    environment = [
      { name = "SECRETS_FROM_SSM", value = "true" },
      { name = "CACHE_BACKEND", value = "s3" },
      { name = "CACHE_BUCKET", value = aws_s3_bucket.cache.id },
      { name = "JOB_BACKEND", value = "dynamodb" },
      { name = "JOBS_TABLE", value = aws_dynamodb_table.jobs.name },
      { name = "UPLOAD_BUCKET", value = aws_s3_bucket.uploads.id },
      { name = "AWS_REGION", value = var.aws_region },
      { name = "AWS_DEFAULT_REGION", value = var.aws_region },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.worker.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "worker"
      }
    }
  }])
}
