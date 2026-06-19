"""Issue 103 — OpenAPI export 관리 커맨드 (orval 입력 + 드리프트 기준). ADR-0014.

서버 기동 없이 스키마를 결정적으로 덤프하는지 검증한다.
"""
import json


def test_export_openapi_dumps_valid_schema(tmp_path):
    from django.core.management import call_command

    out = tmp_path / "openapi.json"
    call_command("export_openapi", output=str(out))

    data = json.loads(out.read_text(encoding="utf-8"))
    assert "openapi" in data
    assert "paths" in data and data["paths"]
    # admin 엔드포인트 경로가 포함된다
    assert any(p.startswith("/api/operator") for p in data["paths"])
    assert any(p.startswith("/api/tenant") for p in data["paths"])


def test_export_openapi_is_deterministic(tmp_path):
    """같은 스키마는 같은 바이트로 덤프(드리프트 체크의 전제)."""
    from django.core.management import call_command

    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    call_command("export_openapi", output=str(a))
    call_command("export_openapi", output=str(b))

    assert a.read_text(encoding="utf-8") == b.read_text(encoding="utf-8")
