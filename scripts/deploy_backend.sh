#!/usr/bin/env bash
set -euo pipefail

: "${GCP_PROJECT:?GCP_PROJECT is required}"
: "${GCP_REGION:?GCP_REGION is required}"
: "${DEPLOY_SHA:?DEPLOY_SHA is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
: "${GITHUB_OUTPUT:?GITHUB_OUTPUT is required}"

if [[ ! "$DEPLOY_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Deployment requires an immutable commit SHA." >&2
  exit 1
fi

# 빌드 중 더 새 main이 올라왔다면 과거 버전으로 DB/서버를 덮어쓰지 않는다.
latest="$(gh api "repos/$GITHUB_REPOSITORY/commits/main" --jq .sha)"
if [[ "$latest" != "$DEPLOY_SHA" ]]; then
  echo "A newer main commit exists; skipping this deployment."
  echo "deployed=false" >> "$GITHUB_OUTPUT"
  exit 0
fi

image="$GCP_REGION-docker.pkg.dev/$GCP_PROJECT/feynmi-images/api:$DEPLOY_SHA"
cloud=(--project="$GCP_PROJECT" --region="$GCP_REGION" --quiet)

# 기존 작업의 비밀 참조·서비스 계정·Cloud SQL 연결은 유지한다.
# 마이그레이션 실패 시 서비스 이미지를 바꾸지 않는다.
gcloud run jobs update feynmi-migrate --image="$image" "${cloud[@]}"
gcloud run jobs execute feynmi-migrate --wait "${cloud[@]}"
gcloud run services update feynmi-api --image="$image" "${cloud[@]}"

url="$(gcloud run services describe feynmi-api "${cloud[@]}" --format='value(status.url)')"
curl --fail --silent --show-error --retry 5 --retry-delay 2 "$url/health"
echo "deployed=true" >> "$GITHUB_OUTPUT"
