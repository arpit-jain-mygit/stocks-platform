# storage.tf - the three S3 buckets (docs/AWS.md step 2.7).
#   frontend  the Angular site; served by CloudFront (step 2.10), never public
#   uploads   PDFs uploaded through presigned links; deleted after 30 days
#   cache     page and vector caches (cache/ prefix); kept until removed

locals {
  bucket_suffix = var.account_id
}

# Shared settings for every bucket: no public access, encrypted at rest.
resource "aws_s3_bucket" "frontend" {
  bucket        = "${var.project}-frontend-${local.bucket_suffix}"
  force_destroy = false
}

resource "aws_s3_bucket" "uploads" {
  bucket        = "${var.project}-uploads-${local.bucket_suffix}"
  force_destroy = false
}

resource "aws_s3_bucket" "cache" {
  bucket        = "${var.project}-cache-${local.bucket_suffix}"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "all" {
  for_each = {
    frontend = aws_s3_bucket.frontend.id
    uploads  = aws_s3_bucket.uploads.id
    cache    = aws_s3_bucket.cache.id
  }
  bucket                  = each.value
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "all" {
  for_each = {
    frontend = aws_s3_bucket.frontend.id
    uploads  = aws_s3_bucket.uploads.id
    cache    = aws_s3_bucket.cache.id
  }
  bucket = each.value
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Uploads: the browser sends PDFs straight here with a presigned PUT link.
# CORS lets the site's browser make that request. Tighten allowed_origins once the
# CloudFront domain exists (step 2.10).
resource "aws_s3_bucket_cors_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id
  cors_rule {
    allowed_methods = ["PUT"]
    allowed_origins = var.upload_allowed_origins
    allowed_headers = ["*"]
    max_age_seconds = 3000
  }
}

# Uploads are only needed while they are being ingested: delete them after 30 days.
resource "aws_s3_bucket_lifecycle_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id
  rule {
    id     = "delete-old-uploads"
    status = "Enabled"
    filter {
      prefix = "uploads/"
    }
    expiration {
      days = 30
    }
  }
}
