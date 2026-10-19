# outputs.tf - values printed after `terraform apply` (e.g. the API and site addresses). Added later.

# The address of the site and the API (one CloudFront domain).
output "site_url" {
  value       = "https://${aws_cloudfront_distribution.site.domain_name}"
  description = "Open this in the browser; /api/* goes to the backend"
}
