# providers.tf - the AWS provider. Credentials come from the "stocks-insights" CLI profile.

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile

  default_tags {
    tags = {
      Project   = var.project
      ManagedBy = "terraform"
    }
  }
}
