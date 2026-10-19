# github_oidc.tf - lets GitHub Actions deploy without stored AWS keys (docs/AWS.md step 3.5).
# A workflow asks GitHub for a short-lived token; AWS accepts it only from the repo and branches
# listed below, and gives back temporary credentials for the role. No access keys are saved in GitHub.

locals {
  github_repo = "arpit-jain-mygit/stocks-platform"
  # Branches allowed to deploy. aws-serverless is the migration branch; remove it after the cut-over.
  github_branches = ["main", "aws-serverless"]
}

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1c58a3a8518e8759bf075b76b750d4f2df264fcd",
  ]
}

data "aws_iam_policy_document" "github_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [for branch in local.github_branches : "repo:${local.github_repo}:ref:refs/heads/${branch}"]
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  name               = "${var.project}-github-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_assume.json
}

data "aws_iam_policy_document" "github_deploy" {
  # Backend: the Lambda zip, and the worker source zip for CodeBuild.
  statement {
    sid       = "UploadBuilds"
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${aws_s3_bucket.artifacts.arn}/api/*", "${aws_s3_bucket.artifacts.arn}/build/*"]
  }
  statement {
    sid       = "UpdateApiFunction"
    actions   = ["lambda:UpdateFunctionCode", "lambda:GetFunction", "lambda:GetFunctionConfiguration"]
    resources = [aws_lambda_function.api.arn]
  }
  statement {
    sid       = "BuildWorkerImage"
    actions   = ["codebuild:StartBuild", "codebuild:BatchGetBuilds"]
    resources = [aws_codebuild_project.worker.arn]
  }
  # Frontend: the Angular build goes to the site bucket, then the CloudFront cache is cleared.
  statement {
    sid       = "UploadSite"
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${aws_s3_bucket.frontend.arn}/*"]
  }
  statement {
    sid       = "ListSite"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.frontend.arn]
  }
  statement {
    sid       = "InvalidateSite"
    actions   = ["cloudfront:CreateInvalidation"]
    resources = [aws_cloudfront_distribution.site.arn]
  }
}

resource "aws_iam_role_policy" "github_deploy" {
  name   = "${var.project}-github-deploy"
  role   = aws_iam_role.github_deploy.id
  policy = data.aws_iam_policy_document.github_deploy.json
}

output "github_deploy_role_arn" {
  value       = aws_iam_role.github_deploy.arn
  description = "Put this in GitHub: repo Settings -> Secrets and variables -> Actions -> Variables as AWS_ROLE_ARN"
}
