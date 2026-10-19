# variables.tf - settings used across the infrastructure. Defaults match docs/AWS.md.

variable "project" {
  description = "Name used in resource names and tags."
  type        = string
  default     = "stocks-insights"
}

variable "aws_region" {
  description = "AWS region (Mumbai)."
  type        = string
  default     = "ap-south-1"
}

variable "aws_profile" {
  description = "CLI profile holding the stocks-insights-deploy access key."
  type        = string
  default     = "stocks-insights"
}

variable "account_id" {
  description = "AWS account ID (used to keep bucket names unique)."
  type        = string
  default     = "552808407801"
}

variable "upload_allowed_origins" {
  description = "Sites allowed to upload PDFs with presigned links (the CloudFront site, step 2.10). Add another site here only if it uploads from the browser."
  type        = list(string)
  default     = ["https://d1zkomffgjvef3.cloudfront.net"]
}

variable "alert_email" {
  description = "Where CloudWatch alarms send their messages. AWS sends a confirmation email you must click once."
  type        = string
  default     = "sachin.arpit.learning@gmail.com"
}
