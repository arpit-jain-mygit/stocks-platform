# jobs.tf - the ingestion jobs table (docs/AWS.md step 2.8).
# One item per job: job_id (key) and body (the job as JSON text). Pay per request, so no cost while idle.
# Expiry: DynamoDB deletes items whose expires_at (epoch seconds) has passed. The app must set
# expires_at when a job is created (not done yet - a code change to be made before relying on expiry).

resource "aws_dynamodb_table" "jobs" {
  name         = "${var.project}-jobs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "job_id"

  attribute {
    name = "job_id"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = false
  }
}
