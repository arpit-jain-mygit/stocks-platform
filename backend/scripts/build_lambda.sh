#!/usr/bin/env bash
# build_lambda.sh - builds the API as a zip for AWS Lambda (no Docker needed).
#
# 1. Downloads the packages from requirements.txt for Lambda's environment:
#    Linux, arm64 (Graviton), Python 3.14. Only pre-built wheels are used, so
#    nothing is compiled on your Mac.
# 2. Copies the backend code next to them (no tests, data, secrets or caches).
# 3. Zips everything to dist/stocks-insights-api.zip and prints its size.
#
# Run from backend/:  bash scripts/build_lambda.sh
set -euo pipefail

PYTHON_VERSION="3.14"
# Amazon Linux 2023 (Lambda, glibc 2.34) runs these wheels. Some packages ship only the older
# manylinux2014 tag (grpcio), so both are allowed.
PLATFORMS=(--platform manylinux_2_28_aarch64 --platform manylinux2014_aarch64)
BUILD_DIR="build/lambda"
OUT="dist/stocks-insights-api.zip"

rm -rf "$BUILD_DIR" && mkdir -p "$BUILD_DIR" dist

# Step 1: packages for Lambda (arm64, Linux). --only-binary refuses anything that would need compiling.
../.venv/bin/python -m pip install --quiet --upgrade \
  "${PLATFORMS[@]}" --implementation cp --python-version "$PYTHON_VERSION" \
  --only-binary=:all: --target "$BUILD_DIR" -r requirements.txt

# Step 2: the backend code (the same folders the Docker image would copy).
for folder in api ingest query utils ops db eval; do
  cp -R "$folder" "$BUILD_DIR/"
done
find "$BUILD_DIR" -name "__pycache__" -type d -prune -exec rm -rf {} +
find "$BUILD_DIR" -name "tests" -type d -prune -exec rm -rf {} +
# The Lambda Python runtime already includes boto3, botocore, s3transfer and jmespath, so they
# are left out of the zip (about 35 MB saved, which keeps the build under the 250 MB limit).
rm -rf "$BUILD_DIR"/boto3 "$BUILD_DIR"/boto3-* "$BUILD_DIR"/botocore "$BUILD_DIR"/botocore-* \
       "$BUILD_DIR"/s3transfer "$BUILD_DIR"/s3transfer-* "$BUILD_DIR"/jmespath "$BUILD_DIR"/jmespath-*

# Step 3: the zip, and its size (Lambda allows 250 MB unzipped).
rm -f "$OUT"
(cd "$BUILD_DIR" && zip -qr "../../$OUT" .)
UNZIPPED_MB=$(du -sm "$BUILD_DIR" | cut -f1)
ZIPPED_MB=$(du -sm "$OUT" | cut -f1)
echo "built $OUT: ${ZIPPED_MB} MB zipped, ${UNZIPPED_MB} MB unzipped (limit 250 MB unzipped)"
if [ "$UNZIPPED_MB" -gt 250 ]; then echo "TOO LARGE for Lambda" >&2; exit 1; fi
