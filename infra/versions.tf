# versions.tf - Terraform and provider versions, and where the state is stored.

terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # State lives in the bucket and lock table created in docs/AWS.md (step 2.4).
  # Backend blocks cannot use variables, so the names are fixed here.
  backend "s3" {
    bucket         = "stocks-insights-tfstate-552808407801"
    key            = "stocks-insights/terraform.tfstate"
    region         = "ap-south-1"
    dynamodb_table = "stocks-insights-tfstate-lock"
    encrypt        = true
  }
}
