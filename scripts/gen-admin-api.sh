#!/usr/bin/env bash
# admin HTTP 클라이언트를 백엔드 OpenAPI에서 재생성한다 (ADR-0014, issue 106).
# 모든 도구는 docker에서 실행한다(CLAUDE.md 규칙).
#
#   ① 백엔드 컨테이너: export_openapi → admin/openapi.json
#   ② admin node 컨테이너: orval → src/generated
#
# 사용법: bash scripts/gen-admin-api.sh
set -uo pipefail
cd "$(dirname "$0")/.."

HOST_BACKEND="$(pwd -W 2>/dev/null || pwd)/backend"

echo "① OpenAPI export (backend docker)…"
MSYS_NO_PATHCONV=1 docker compose -f docker-compose.test.yml run --rm --no-deps \
    -v "${HOST_BACKEND}:/app" test \
    python manage.py export_openapi --output /app/openapi.json || exit 1
mv backend/openapi.json admin/openapi.json

echo "② orval codegen (admin node docker)…"
MSYS_NO_PATHCONV=1 docker compose -f docker-compose.dev.yml run --rm --no-deps admin \
    sh -c "npm install --silent && npx orval --config ./orval.config.ts" || exit 1

echo "✓ admin API 클라이언트 재생성 완료 (admin/openapi.json + admin/src/generated)"
