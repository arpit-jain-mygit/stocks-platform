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
