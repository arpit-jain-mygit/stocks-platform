#!/usr/bin/env bash
# build_worker_image.sh - builds the ingestion worker image in AWS CodeBuild and pushes it to ECR.
#
# No Docker is needed on this Mac:
# 1. Zips the backend folder (the same files the Dockerfile copies, minus what .dockerignore drops).
# 2. Uploads the zip to the artifacts bucket (build/worker-src.zip).
# 3. Starts the CodeBuild project, which runs backend/Dockerfile and pushes the image to ECR
#    under a timestamp tag and under "latest".
# 4. Waits for the build and prints the result.
#
# Run from backend/:  bash scripts/build_worker_image.sh
set -euo pipefail

PROFILE="stocks-insights"
REGION="ap-south-1"
BUCKET="stocks-insights-artifacts-552808407801"
PROJECT="stocks-insights-worker-build"
ZIP="dist/worker-src.zip"
AWS="aws --profile $PROFILE --region $REGION"

# Step 1: the source zip. Secrets, data, caches and tests stay out of it.
mkdir -p dist
rm -f "$ZIP"
zip -qr "$ZIP" . \
  -x ".venv/*" "dist/*" "build/*" "tests/*" "data/*" "cache/*" "eval/results/*" \
     ".env" ".env.*" "*/__pycache__/*" "__pycache__/*" "*.pyc" ".git/*" ".pytest_cache/*"

# Step 2: upload it.
$AWS s3 cp "$ZIP" "s3://$BUCKET/build/worker-src.zip" --only-show-errors

# Step 3: start the build with a timestamp tag.
TAG="$(date +%Y%m%d%H%M%S)"
BUILD_ID="$($AWS codebuild start-build --project-name "$PROJECT" \
  --environment-variables-override "name=IMAGE_TAG,value=$TAG,type=PLAINTEXT" \
  --query "build.id" --output text)"
echo "build $BUILD_ID started (image tag $TAG)"

# Step 4: wait until it finishes (about 5 to 10 minutes).
STATUS="IN_PROGRESS"
while [ "$STATUS" = "IN_PROGRESS" ]; do
  sleep 20
  STATUS="$($AWS codebuild batch-get-builds --ids "$BUILD_ID" --query "builds[0].buildStatus" --output text)"
done
echo "build status: $STATUS"
if [ "$STATUS" != "SUCCEEDED" ]; then
  echo "build failed; see the CodeBuild log for $BUILD_ID" >&2
  exit 1
fi
echo "pushed image tags: $TAG and latest"
