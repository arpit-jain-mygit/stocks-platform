# frontend.tf - the public site and API behind one CloudFront distribution (docs/AWS.md 2.10, 2.11).
#   /            the Angular site, read from the frontend bucket (private, via origin access control)
#   /api/*       the backend: rewritten to API Gateway, only the allowed routes (cf/api_router.js)
# The browser only ever talks to this distribution. CloudFront adds the secret X-API-Key header,
# so the key never reaches the browser.

# --- Secret for the API key header ---------------------------------------------------------------
# Read from SSM Parameter Store (filled in step 2.6). It ends up in the encrypted Terraform state,
# the same as the other values read by Terraform.
data "aws_ssm_parameter" "app_api_key" {
  name            = "/stocks-insights/APP_API_KEY"
  with_decryption = true
}

# --- Frontend bucket access: only this distribution may read it -------------------------------
resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${var.project}-frontend-oac"
  description                       = "Lets CloudFront read the private frontend bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

data "aws_iam_policy_document" "frontend_read" {
  statement {
    sid       = "AllowCloudFrontRead"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.frontend.arn}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.site.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  policy = data.aws_iam_policy_document.frontend_read.json
}

# --- Routing function: /api rules and Angular routes --------------------------------------------
resource "aws_cloudfront_function" "router" {
  name    = "${var.project}-router"
  runtime = "cloudfront-js-2.0"
  comment = "Allowed API paths only; /api prefix removed; Angular routes to index.html"
  publish = true
  code    = file("${path.module}/cf/api_router.js")
}

# --- The distribution ----------------------------------------------------------------------------
resource "aws_cloudfront_distribution" "site" {
  enabled             = true
  comment             = "${var.project}: site and API"
  default_root_object = "index.html"
  is_ipv6_enabled     = true
  http_version        = "http2and3"
  price_class         = "PriceClass_200" # includes Asia (India), not only US and Europe

  origin {
    origin_id                = "frontend"
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  origin {
    origin_id   = "api"
    domain_name = replace(aws_apigatewayv2_api.api.api_endpoint, "https://", "")
    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
    custom_header {
      name  = "X-API-Key"
      value = data.aws_ssm_parameter.app_api_key.value
    }
  }

  # The site: read-only, cached.
  default_cache_behavior {
    target_origin_id       = "frontend"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = "658327ea-f89d-4fab-a63d-7e88639e58f6" # AWS managed: CachingOptimized
    compress               = true
    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.router.arn
    }
  }

  # The API: never cached, all viewer headers and the body are passed on.
  ordered_cache_behavior {
    path_pattern             = "/api/*"
    target_origin_id         = "api"
    viewer_protocol_policy   = "https-only"
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad" # AWS managed: CachingDisabled
    origin_request_policy_id = "b689b0a8-53d0-40ab-baf2-68738e2966ac" # AWS managed: AllViewerExceptHostHeader
    compress                 = true
    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.router.arn
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}
