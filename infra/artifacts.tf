# artifacts.tf - the private bucket holding the Lambda code zip (docs/AWS.md step 2.9).
# Zips are about 81 MB, above the 50 MB limit for uploading straight to Lambda, so they go via S3.

resource "aws_s3_bucket" "artifacts" {
  bucket        = "${var.project}-artifacts-${var.account_id}"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  versioning_configuration {
    status = "Enabled"
  }
}

# The zip built by backend/scripts/build_lambda.sh. Changing the file changes its hash, so
# terraform apply uploads the new version and points Lambda at it.
resource "aws_s3_object" "api_package" {
  bucket = aws_s3_bucket.artifacts.id
  key    = "api/stocks-insights-api.zip"
  source = "${path.module}/../backend/dist/stocks-insights-api.zip"
  etag   = filemd5("${path.module}/../backend/dist/stocks-insights-api.zip")
}
