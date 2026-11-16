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
| 2026-10-18 | Budget `stocks-insights-monthly`: $20/month, email alerts at 80% and 100% to the owner's address | Created with `aws budgets create-budget` |
| 2026-10-18 | Terraform state: S3 bucket `stocks-insights-tfstate-552808407801` (ap-south-1, versioning on, public access blocked, AES256 encryption) and DynamoDB lock table `stocks-insights-tfstate-lock` (on-demand) | Created with the AWS CLI; they are the only resources so far |
| 2026-10-18 | `infra/` Terraform skeleton (versions, providers, variables, S3 backend); `terraform init`, `validate` and `plan` succeed | No resources yet: `main.tf` is intentionally empty |
| 2026-10-18 | Six SecureString parameters under `/stocks-insights/`: APP_API_KEY, ADMIN_API_KEY, GEMINI_API_KEY, QDRANT_URL, QDRANT_API_KEY, DATABASE_URL | Entered by the owner in Terminal; values are not in git or chat. Verified by listing names and types |
| 2026-10-18 | Terraform applied step 2.7: buckets `stocks-insights-frontend-552808407801`, `stocks-insights-uploads-552808407801` (30-day expiry on `uploads/`), `stocks-insights-cache-552808407801`; public access blocked, AES256 | 11 resources added. Applied from saved plan |
| 2026-10-18 | Terraform applied step 2.8: DynamoDB table `stocks-insights-jobs` (pay per request, TTL on `expires_at`) | 1 resource added; status ACTIVE. Expiry not active until the app sets `expires_at` |

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
- [x] **2.3 Budget alarm:** monthly budget with an email alert at 80% and 100%
- [x] **2.4 Remote state:** S3 bucket for Terraform state (versioning and encryption on) and a DynamoDB table for locks
- [x] **2.5 `infra/` folder:** `providers.tf`, `variables.tf`, `outputs.tf`, one module per component
- [x] **2.6 Secrets:** SSM Parameter Store (SecureString) for `APP_API_KEY`, `ADMIN_API_KEY`, `GEMINI_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, `DATABASE_URL`. Values are entered once, not written into Terraform files
- [x] **2.7 Storage:** frontend, uploads and cache buckets created (11 resources) S3 buckets for the frontend, uploads and caches (private, encrypted, lifecycle rules on uploads)
- [x] **2.8 Metadata table:** `stocks-insights-jobs` created (pay per request). Expiry still needs the app to set `expires_at` (follow-up to step 1.2) DynamoDB `jobs` table (on-demand billing)
- [x] **2.9 Backend:** (applied: 15 resources added. API endpoint https://9l1e52v7ia.execute-api.ap-south-1.amazonaws.com, GET /health returns 200. Zip package, not Docker; no ECR) IAM role with least privilege, Lambda function (zip, arm64, python 3.14, 2048 MB, 60 s timeout), API Gateway HTTP API. Zip is 40 MB zipped / 131 MB unzipped (limit 250 MB) after moving PDF, Office, uvicorn packages out of the Lambda build; the API imports without them (test_lambda_imports.py)
- [x] **2.10 Frontend:** applied. CloudFront https://d1zkomffgjvef3.cloudfront.net; origin access control, routing function (`infra/cf/api_router.js`), bucket policy. Site root returns 403 until the Angular build is uploaded (phase 3). Support case 179233617900178 approved the account
- [x] **2.11 API routing:** (applied: `/api/*` to API Gateway. The function allows GET companies, doc-types, documents, jobs/<id>, POST ask and uploads only; other paths and methods get 404; `/api` is removed before forwarding). The `X-API-Key` header is added as a CloudFront origin header
- [x] **2.12 Ingestion:** applied 2026-10-19 (ECR, CodeBuild, ECS cluster and task definition, roles, security group, Lambda ECS settings). Worker image built and pushed by `backend/scripts/build_worker_image.sh`. The push failed at first because the CodeBuild role had the wrong action name (`ecr:BatchCheckLayerAvailable`, correct: `ecr:BatchCheckLayerAvailability`). Fixed. End-to-end test passed 2026-10-19: upload link, S3 PUT, /ingest (direct to API Gateway, /ingest is not routed through CloudFront), worker task, job complete, one cited answer. Worker fixes on the way: load SSM secrets before imports; IAM ListBucket on the cache bucket (worker and API). Test filing (VIDEOIND, Q2 FY10, e2e-test.pdf) removed afterwards with ingest/remove.py, dry run first. Was planned as: Fargate task definition, ECS cluster, Step Functions state machine (Step Functions skipped)
- [x] **2.13 Monitoring:** (applied 2026-10-19. ACTION: click the confirmation link in the AWS email to start alerts. Alarms show INSUFFICIENT_DATA until traffic arrives. Planned as: `infra/monitoring.tf`, 10 to add. SNS topic emailing alert_email (confirm the email AWS sends), alarms for API Lambda errors and throttles, API Gateway 5xx, and EventBridge rules for worker tasks that crash or fail to start. Limitation: a job that fails inside the worker exits with 0 and does not alarm. Worker log group already keeps 30 days) Was: CloudWatch log groups with a 30-day retention, alarms for Lambda errors and API 5xx
- [x] **2.15 Hardening (applied 2026-10-19; the TTL is confirmed on the next new job):** jobs get a 30-day TTL (`expires_at`, code in `utils/jobs.py`); upload CORS limited to the CloudFront domain (was `*`). Plan: Lambda code update and the CORS change. If uploads ever come from another site (for example the Vercel domain), add it to `upload_allowed_origins`
- [ ] **2.14 Apply:** `terraform plan` reviewed by you, then `terraform apply`

---

## Phase 3 – Build and deploy

- [ ] **3.1 Backend image:** build, push to ECR, update the Lambda function
- [ ] **3.2 Database migrations:** run `python db/migrate.py` once from your Mac (or a one-off task). Migrations already applied to Supabase are skipped
- [x] **3.3 Frontend:** done 2026-10-19: 4 files uploaded to the frontend bucket, invalidation IBCFPFN4FFTNZVZUQHONPFTTBZ on E1AIR4NMCC3PLD. Was: `npm run build`, upload `dist/stocks-ui/browser` to the frontend bucket, create a CloudFront invalidation
- [~] **3.4 Smoke tests:** passed 2026-10-19: site root and Angular route 200, `/api/companies?ingested=true`, `/api/doc-types`, `/api/companies/OFSS` 200, `/api/ask` answered with sources (one Gemini call), `/api/ingest` and `/api/risky-delete/x` 404. Upload not tested: ingest waits for 2.12. Was: `/health`, `/companies?ingested=true`, one question in the chat, one upload
- [ ] **3.5 CI/CD:** (OIDC role applied 2026-10-19: arn:aws:iam::552808407801:role/stocks-insights-github-deploy. Workflows committed locally, not yet pushed. Still to do in GitHub: variables AWS_ROLE_ARN and CLOUDFRONT_DISTRIBUTION_ID (E1AIR4NMCC3PLD). Then push to run them. Planned as: `infra/github_oidc.tf` (3 to add: GitHub OIDC provider, deploy role limited to this repo's main and aws-serverless branches) and `.github/workflows/backend.yml` and `frontend.yml`. Set GitHub variables AWS_ROLE_ARN and CLOUDFRONT_DISTRIBUTION_ID. Caveat: CI overwrites the Lambda zip at the key Terraform uses, so the next `terraform apply` re-uploads the local zip. Run the zip build before any apply.) Was: GitHub Actions with OIDC (no stored AWS keys): backend workflow and frontend workflow, both running the tests first

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

## Operations – Gemini key and resuming a failed ingest

The worker reads `GEMINI_API_KEY` from SSM Parameter Store (`/stocks-insights/GEMINI_API_KEY`) each time a task starts. Changing the parameter needs no Terraform apply and no image rebuild. The next ingest uses the new key.

### Update the key

Paste the key at the prompt, so it never appears in shell history:

```bash
read -s "GEMINI_KEY?Paste new Gemini key: "
```
```bash
echo ${#GEMINI_KEY}
```
```bash
aws ssm put-parameter --name /stocks-insights/GEMINI_API_KEY --type SecureString --value "$GEMINI_KEY" --overwrite --profile stocks-insights --region ap-south-1
```
```bash
unset GEMINI_KEY
```

The `echo` prints the key's length only. If it prints `0`, the paste did not register; run the `read` line again in the same terminal.

A key from the same Google Cloud project shares that project's Gemini quota. A 429 `RESOURCE_EXHAUSTED` error means the quota is used up, not that the key is wrong. Use a key from another project, or enable billing on the project.

### Resume a failed ingest

Each successful slide (or scanned page) is cached in the S3 cache bucket as soon as it is read. A re-run reads the cached results and calls Gemini only for the parts that failed, so it does not pay for the whole file again.

Re-submit the same upload. Use the `upload_key` from the first run; the file is still in the uploads bucket for 30 days.

```bash
API=https://9l1e52v7ia.execute-api.ap-south-1.amazonaws.com
```
```bash
curl -s -X POST "$API/ingest" -H "X-API-Key: $APP_API_KEY" -F "upload_key=uploads/14d47d47402f45e88186a1be5815805e/MSFT-Earnings-Release-FY27-Q1.pptx" -F "file_name=MSFT-Earnings-Release-FY27-Q1.pptx" -F "company=MSFT" -F "period=Q1 FY27 (quarter ended 30-Sep-2026)" -F "doc_type=quarterly_results"
```

The response contains a new `job_id`. Check it with:

```bash
curl -s "$API/jobs/<job_id>" -H "X-API-Key: $APP_API_KEY"
```

If the API refuses the re-submit because the document already exists, add `-F "force=true"` to the command.

### Example job record (DynamoDB)

Each ingest job is stored in the `stocks-insights-jobs` table. The record is created when the job is queued, and the worker updates its `status` as the job runs. The API returns the same record from `GET /jobs/<job_id>`.

Example for the MSFT press release (`MSFT-PressReleaseFY27q1.docx`):

```json
{"job_id": "52646861dff84065b414db80234b6aae", "status": "complete", "doc_id": "d4095fad1d7cb26a83e91cef1c16040b4011466e629d2dbe73458ee964f5e767", "file_name": "MSFT-PressReleaseFY27q1.docx", "company_id": "MSFT", "period": "Q1 FY27 (quarter ended 30-Sep-2026)", "doc_type": "quarterly_results", "created_at": "2026-10-31T00:22:53.517963+00:00", "result": {"doc_id": "d4095fad1d7cb26a83e91cef1c16040b4011466e629d2dbe73458ee964f5e767", "file_name": "MSFT-PressReleaseFY27q1.docx", "company_id": "MSFT", "company": "Microsoft Corporation", "fiscal_year": 2027, "quarter": 1, "period_end": "2026-09-30", "period": "Q1 FY27 (quarter ended 30-Sep-2026)", "doc_type": "quarterly_results", "status": "complete", "pages": 7, "ocr_pages": [], "chunks": 42}, "finished_at": "2026-10-31T00:23:30.402844+00:00"}
```

Fields to check:

- `status`: `queued`, `running`, `complete`, or `failed`. A failed job has an `error` field instead of `result`.
- `chunks`: how many pieces of text were stored for search. The press release has 42.
- `ocr_pages`: pages that needed OCR. Empty means every page had a text layer or went to the vision model.
- `doc_id`: the same for the same file and period. A re-run keeps it.

**All timestamps in these records are UTC.** `created_at` 00:22:53 UTC is 05:52:53 IST (India). Use UTC when comparing with the CloudWatch logs and the S3 listing, which also show UTC.

### Site URL

The UI is served at **https://d1zkomffgjvef3.cloudfront.net**.

This is the default `*.cloudfront.net` name that AWS gives the CloudFront distribution. It stays the same as long as the distribution exists. It changes only if the distribution is deleted and created again, for example by `terraform destroy` followed by `terraform apply`.

To get the current URL:

```bash
cd infra && terraform output -raw site_url
```

To use your own domain later, request an ACM certificate in `us-east-1`, add the domain as an alias on the distribution, and add the new origin to `upload_allowed_origins` in `infra/variables.tf` so uploads from that origin are allowed.

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
| Scanned pages fail on AWS with an OCR error | The OCR fallback ran in an image without Tesseract | Ingestion runs in the ECS worker, built from `backend/Dockerfile` (includes Tesseract). Check the task definition uses that image. Lambda does not read PDFs |
| ECS task starts but exits at once | The task definition's command is still `uvicorn`, not the worker | Set the container command to `python -m ingest.worker` in the task definition |
| Lambda `Runtime.ExitError` or out of memory | Memory too low for PDF rendering | Raise memory to 2–3 GB |
| Cold start of 5–10 seconds | Large container image | Trim dependencies; provisioned concurrency only if needed |
| `InvalidParameterException` for the container image | Image not pushed to ECR yet, or wrong tag | Push first, then `terraform apply` again |
| Terraform state lock error | An earlier run did not finish | `terraform force-unlock <id>` after checking nothing is running |
| Duplicate jobs after a retry | The job store is not used by the worker | Check `JOB_BACKEND=dynamodb` and the job id passed to the worker |
| Answers differ from Railway | Different `GEMINI_API_KEY` or environment variables | Compare SSM parameters with Railway's variables |
| Surprise bill | Forgotten NAT gateway, or a Fargate task left running | Budget alarm (2.3); check Cost Explorer by service |
| Job `failed` with `429 RESOURCE_EXHAUSTED` | Gemini quota used up for the key's project | Wait for the quota reset, or use a key from another project or a billed project. Then re-submit (see "Resume a failed ingest") |
| `aws ssm put-parameter` fails with `Member must have length greater than or equal to 1` | The shell variable holding the key is empty | Run the `read -s` line in the same terminal, check `echo ${#GEMINI_KEY}`, then run `put-parameter` |

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
