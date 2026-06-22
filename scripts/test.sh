#!/usr/bin/env bash
# backend 단위/통합 테스트 실행 후, 테스트 전용 인프라(GPU 포함)를 자동 중지한다.
#
# - 코드 변경 즉시 반영을 위해 호스트 backend/를 컨테이너에 마운트한다(rebuild 불필요).
# - 종료 시(성공/실패/중단 무관) db/redis/neo4j/paddle-ocr/ollama 테스트 컨테이너를 stop하여
#   VRAM·메모리를 돌려준다. stop이라 다음 실행은 start로 빠르게 재개된다(워밍업 회피).
# - e2e 서비스(api-e2e 등)는 별도 워크플로우이므로 건드리지 않는다.
#
# 사용법:
#   bash scripts/test.sh
#   bash scripts/test.sh tests/test_rag.py
#   bash scripts/test.sh tests/test_rag.py::test_pdf_normal_text_skips_ocr
set -uo pipefail
cd "$(dirname "$0")/.."

COMPOSE_FILE="docker-compose.test.yml"
INFRA=(test db-test redis-test paddle-ocr-test ollama-test ollama-test-init)
TARGET=("${@:-tests/}")

# Git Bash(MSYS)에서 '/app' 인자와 -v 경로가 호스트 경로로 변환되는 것을 막는다.
# 또한 Git Bash는 Windows 경로(pwd -W)를 줘야 Docker 볼륨 마운트가 동작한다.
HOST_BACKEND="$(pwd -W 2>/dev/null || pwd)/backend"

cleanup() {
    MSYS_NO_PATHCONV=1 docker compose -f "$COMPOSE_FILE" stop "${INFRA[@]}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

MSYS_NO_PATHCONV=1 docker compose -f "$COMPOSE_FILE" run --rm \
    -v "${HOST_BACKEND}:/app" test \
    python -m pytest "${TARGET[@]}" -v --tb=short
