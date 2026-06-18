#!/usr/bin/env pwsh
# backend 단위/통합 테스트 실행 후, 테스트 전용 인프라(GPU 포함)를 자동 중지한다.
#
# - 코드 변경 즉시 반영을 위해 호스트 backend/를 컨테이너에 마운트한다(rebuild 불필요).
# - 종료 시(성공/실패 무관) db/redis/neo4j/paddle-ocr/ollama 테스트 컨테이너를 stop하여
#   VRAM·메모리를 돌려준다. stop이라 다음 실행은 start로 빠르게 재개된다(워밍업 회피).
# - e2e 서비스(api-e2e 등)는 별도 워크플로우이므로 건드리지 않는다.
#
# 사용법:
#   ./scripts/test.ps1
#   ./scripts/test.ps1 tests/test_rag.py
#   ./scripts/test.ps1 tests/test_rag.py::test_pdf_normal_text_skips_ocr

$ErrorActionPreference = 'Continue'
Set-Location (Join-Path $PSScriptRoot '..')

$composeFile = 'docker-compose.test.yml'
$infra = @('test', 'db-test', 'redis-test', 'neo4j-test', 'paddle-ocr-test', 'ollama-test', 'ollama-test-init')
$pytestTarget = if ($args.Count -gt 0) { $args } else { @('tests/') }
$code = 0

try {
    docker compose -f $composeFile run --rm -v "$($PWD.Path)/backend:/app" test `
        python -m pytest @pytestTarget -v --tb=short
    $code = $LASTEXITCODE
}
finally {
    Write-Host "`n[test.ps1] 테스트 인프라 중지 중(GPU/메모리 해제)..." -ForegroundColor Cyan
    docker compose -f $composeFile stop @infra | Out-Null
}
exit $code
