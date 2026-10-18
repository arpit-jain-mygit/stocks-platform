# AWS serverless – plan, steps and troubleshooting

Goal: run stocks-insights.ai on AWS with pay-as-you-go pricing, provisioned with
Terraform. Tick each box as it is done. Keep Supabase, Qdrant Cloud and Gemini as
they are. Railway and Vercel stay as the fallback until AWS is proven.

Related: [README.md](README.md) · [features.md](features.md) · [UX.md](UX.md)

---

## Progress log

| Date | Step | Result / note |
|---|---|---|
| 2026-10-18 | Chose Terraform, `ap-south-1`, API + frontend first, default CloudFront / API Gateway addresses | Decisions recorded in section 0 |
| 2026-10-18 | Confirmed `ap-south-1` (Mumbai) is enabled by default | No opt-in needed |
| 2026-10-18 | Checked CLI: AWS CLI 2.36 installed; Terraform not installed at that time | Installed later (see below) |
| 2026-10-18 | CLI showed signed-in user `matchanalyzer-cli` (another project) | Not used for this project |
| 2026-10-18 | Started creating a classic IAM user in the IAM console | Stopped in favour of IAM Identity Center, which gives temporary credentials. If an IAM user `stocks-insights-admin` was created there, delete it (IAM → Users) |
| 2026-10-18 | Enabled IAM Identity Center as an **account instance** (not an organization), single region `ap-south-1` | Organization would have switched the account to pay-as-you-go and expired free-tier credits. Account instance can't be upgraded to an organization later |
| 2026-10-18 | Created Identity Center user `stocks-insights-admin` | Invitation email sent to the owner's address |
| 2026-10-18 | Set up MFA (authenticator app on phone) for `stocks-insights-admin` | MFA is required by the organisation's policy |
| 2026-10-18 | Access portal URL noted: `https://d-9f675bd66a.awsapps.com/start` | Not a secret |
| 2026-10-18 | Found that the Identity Center account instance has no "Multi-account permissions" (permission sets), so it cannot grant CLI access to the account | Decided on option 2: an IAM user with an access key. The Identity Center user stays unused |
| 2026-10-18 | Terraform 1.16.6 installed to `~/bin` (Homebrew blocked by outdated Command Line Tools) | `terraform -version` works |
| 2026-10-18 | Created IAM user `stocks-insights-deploy`, access key, profile `stocks-insights` (region `ap-south-1`, output `json`) | `aws sts get-caller-identity --profile stocks-insights` works |
| 2026-10-18 | Phase 1 code complete on `aws-serverless`: storage (local/S3), job store (memory/DynamoDB), presigned uploads, Lambda handler (Mangum), Lambda Dockerfile, ECS worker and dispatch, env settings, 158 backend tests passing (AWS calls faked) | Not yet built or run on AWS. Dockerfile.lambda not built (no Docker locally) |

### Still to do

- [x] Create IAM user `stocks-insights-deploy` (IAM → Users → Create user), with no console access, and attach `PowerUserAccess` and `IAMFullAccess` for now (narrow in Phase 5)
- [x] Create an access key for the user (use case: Command Line Interface). Save the key and secret somewhere safe; the secret is shown only once
- [x] Configure the profile on your Mac: `aws configure --profile stocks-insights` (enter the key, the secret, region `ap-south-1`, output `json`)
- [x] Install Terraform 1.16.6 (Homebrew install was blocked by outdated Command Line Tools, so the binary was installed to `~/bin` and added to PATH; `terraform -version` works)
- [x] Check with `aws sts get-caller-identity --profile stocks-insights` (done: account 552808407801, JSON returned)
- [ ] Put a reminder in your calendar to rotate the access key in 90 days (IAM → Users → stocks-insights-deploy → Security credentials)

---

## 0. Decisions (answer before Phase 2)

- [x] **IaC tool:** Terraform (chosen)
- [x] **AWS login:** IAM user `stocks-insights-deploy` with an access key, used by the CLI and Terraform (option 2). The Identity Center account instance does not assign AWS account access, so it is not used for the CLI. Not the `matchanalyzer-cli` user, which belongs to another project
- [x] **Scope of first release:** API + frontend only, with ingestion still on Railway
- [x] **Region:** `ap-south-1` (Mumbai)
- [x] **Domain:** default CloudFront and API Gateway addresses for now (no domain cost). A custom domain can be added in section 4.2 later: roughly $10–15 a year for a standard domain (more for `.ai`), plus about $0.50 a month for a Route 53 hosted zone

---

### 0.1 Create the project login (you, in the AWS console)

1. Sign in to the AWS console as the account owner (root) and open **IAM Identity Center**. Enable it if you haven't. Choose `ap-south-1` as its home region.
2. **Users → Add user**: username `stocks-insights-admin`, your email. Set a password and accept the invitation email.
3. **AWS accounts → your account → Assign users**: select this user and create a permission set named `StocksInsightsDeploy`. For the first setup use `PowerUserAccess` plus `IAMFullAccess`; we will narrow it to least privilege in Phase 5.
4. On your Mac, run `aws configure sso` and enter the start URL and region `ap-south-1`. Name the profile `stocks-insights`.
5. Check it works: `aws sts get-caller-identity --profile stocks-insights`. It should show an ARN with `stocks-insights` in the role name, not `matchanalyzer-cli`.
6. Tell me when step 5 works, and I'll tick section 2.2.

---

## Phase 1 – Code changes (no AWS resources, no cost)

Branch: `aws-serverless`.

- [x] **1.1 Storage abstraction.** A `Store` interface with a local-folder version (today) and an S3 version. Used by `utils/page_cache.py` and `utils/vector_cache.py`
- [x] **1.2 Job store.** Ingestion jobs saved to a `jobs` table (DynamoDB) instead of the in-memory dict in `api/main.py`
- [x] **1.3 Presigned uploads.** `POST /uploads` returns a presigned S3 URL; the client uploads there, then calls `POST /ingest` with the S3 key. Removes the 10 MB API Gateway limit
- [x] **1.4 Lambda entry point.** `api/lambda_handler.py` wraps the FastAPI app with Mangum. The same app still runs locally with uvicorn
- [x] **1.5 Container for Lambda.** (written; not built locally: Docker is not installed) A second Dockerfile (or a build target) based on the AWS Lambda Python base image
- [x] **1.6 Ingestion worker.** A small entry point (`python -m ingest.worker <s3-key> <job-id>`) for a Fargate task
- [x] **1.7 Config.** Read `CACHE_BACKEND=local|s3`, `JOB_BACKEND=memory|dynamodb`, `UPLOAD_BUCKET`, `CACHE_BUCKET`, `JOBS_TABLE` from environment variables
- [x] **1.8 Tests.** Existing 145 backend tests still pass; new tests for the S3 and DynamoDB stores using stubs (no AWS calls)
- [ ] **1.9 Commit and review** (local only, push on your go-ahead)

---

## Phase 2 – Provision AWS with Terraform

- [ ] **2.1 Install tools:** `brew install terraform` and `brew install awscli` (already installed)
- [ ] **2.2 AWS login:** create the IAM user or SSO profile chosen in section 0, then `aws configure --profile stocks-insights`
- [ ] **2.3 Budget alarm:** monthly budget with an email alert at 80% and 100%
- [ ] **2.4 Remote state:** S3 bucket for Terraform state (versioning and encryption on) and a DynamoDB table for locks
- [ ] **2.5 `infra/` folder:** `providers.tf`, `variables.tf`, `outputs.tf`, one module per component
- [ ] **2.6 Secrets:** SSM Parameter Store (SecureString) for `APP_API_KEY`, `ADMIN_API_KEY`, `GEMINI_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, `DATABASE_URL`. Values are entered once, not written into Terraform files
- [ ] **2.7 Storage:** S3 buckets for the frontend, uploads and caches (private, encrypted, lifecycle rules on uploads)
- [ ] **2.8 Metadata table:** DynamoDB `jobs` table (on-demand billing)
- [ ] **2.9 Backend:** ECR repository, Lambda function (container image, 2–3 GB memory, 5 min timeout), API Gateway HTTP API, IAM role with least privilege
- [ ] **2.10 Frontend:** CloudFront distribution with origin access control to the frontend bucket
- [ ] **2.11 API routing:** CloudFront behaviours for `/api/*` to API Gateway, allowing only `companies*`, `doc-types`, `documents*`, `ask`, `uploads`, `jobs/*`. The `X-API-Key` header is added as a CloudFront origin header
- [ ] **2.12 Ingestion (phase 2b, optional now):** Fargate task definition, ECS cluster, Step Functions state machine
- [ ] **2.13 Monitoring:** CloudWatch log groups with a 30-day retention, alarms for Lambda errors and API 5xx
- [ ] **2.14 Apply:** `terraform plan` reviewed by you, then `terraform apply`

---

## Phase 3 – Build and deploy

- [ ] **3.1 Backend image:** build, push to ECR, update the Lambda function
- [ ] **3.2 Database migrations:** run `python db/migrate.py` once from your Mac (or a one-off task). Migrations already applied to Supabase are skipped
- [ ] **3.3 Frontend:** `npm run build`, upload `dist/stocks-ui/browser` to the frontend bucket, create a CloudFront invalidation
- [ ] **3.4 Smoke tests:** `/health`, `/companies?ingested=true`, one question in the chat, one upload
- [ ] **3.5 CI/CD:** GitHub Actions with OIDC (no stored AWS keys): backend workflow and frontend workflow, both running the tests first

---

## Phase 4 – Cut over

- [ ] **4.1 Parallel run:** AWS and Railway/Vercel both up; compare answers for 10 questions
- [ ] **4.2 Domain:** ACM certificate (us-east-1 for CloudFront), Route 53 record
- [ ] **4.3 Switch:** point the domain at CloudFront
- [ ] **4.4 Fallback:** keep Railway and Vercel running for one week, then decide whether to shut them down

---

## Phase 5 – Security and cost review

- [ ] **5.1 WAF:** rate limit on `/api/ask` and `/api/uploads`
- [ ] **5.2 Risky APIs:** keep `ENABLE_RISKY_DELETE_APIS` and `ENABLE_BACKUP_APIS` off in Lambda
- [ ] **5.3 Secret rotation:** a dated note to rotate `APP_API_KEY` every 90 days
- [ ] **5.4 Cost check:** Cost Explorer after the first full month, compared with the estimate

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `AccessDenied` on `terraform apply` | The IAM user lacks a permission | Read the error for the action name; add it to the project's policy, never `AdministratorAccess` |
| `BucketAlreadyExists` | S3 bucket names are global | Add an account ID or random suffix to the bucket name |
| CloudFront shows 403 from S3 | Origin access control or bucket policy missing | Check the bucket policy allows `cloudfront.amazonaws.com` for this distribution only |
| CloudFront certificate error | Certificate not in `us-east-1` | Request the ACM certificate in `us-east-1` |
| API Gateway returns 413 | Upload larger than 10 MB sent through the API | Use presigned uploads (1.3) |
| Lambda timeout (503 or 504) | Ingestion running inside the API request | Move ingestion to the Fargate worker (1.6, 2.12); `/ask` only needs a few seconds |
| Lambda `Runtime.ExitError` or out of memory | Memory too low for PDF rendering | Raise memory to 2–3 GB |
| Cold start of 5–10 seconds | Large container image | Trim dependencies; provisioned concurrency only if needed |
| `InvalidParameterException` for the container image | Image not pushed to ECR yet, or wrong tag | Push first, then `terraform apply` again |
| Terraform state lock error | An earlier run did not finish | `terraform force-unlock <id>` after checking nothing is running |
| Duplicate jobs after a retry | The job store is not used by the worker | Check `JOB_BACKEND=dynamodb` and the job id passed to the worker |
| Answers differ from Railway | Different `GEMINI_API_KEY` or environment variables | Compare SSM parameters with Railway's variables |
| Surprise bill | Forgotten NAT gateway, or a Fargate task left running | Budget alarm (2.3); check Cost Explorer by service |

---

## Useful commands

```bash
aws sts get-caller-identity --profile stocks-insights
```
```bash
cd infra && terraform init && terraform plan
```
```bash
cd infra && terraform apply
```
```bash
aws logs tail /aws/lambda/stocks-insights-api --follow --profile stocks-insights
```
