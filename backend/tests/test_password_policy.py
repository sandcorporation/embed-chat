"""안전한 비밀번호 정책 (개인정보보호 권장) — issue 211.

규칙: 8자 이상 + 영문·숫자·특수문자 3종 모두, 또는 10자 이상 + 2종 이상. 위반 시 사용자 메시지,
통과 시 None. 가입·비밀번호 변경의 단일 검증원천(deep module). 순수 함수라 DB 불필요.
"""
from apps.tenants.password_policy import password_policy_error


def test_rejects_too_short():
    assert password_policy_error("Ab1!") is not None  # 4자


def test_accepts_10plus_with_two_classes():
    assert password_policy_error("abcdefgh12") is None  # 10자, 영문+숫자


def test_rejects_10plus_single_class():
    assert password_policy_error("abcdefghij") is not None  # 10자, 영문만(1종)


def test_accepts_8plus_with_three_classes():
    assert password_policy_error("Abcdef1!") is None  # 8자, 영문+숫자+특수


def test_rejects_8to9_with_only_two_classes():
    assert password_policy_error("abcdef12") is not None  # 8자, 2종 → 3종 필요


def test_rejects_empty():
    assert password_policy_error("") is not None


# ── 엔드포인트 적용 (가입·비밀번호 변경) ─────────────────────────────────────
import pytest

SIGNUP = "/api/tenant/agents/auth/signup"


@pytest.mark.django_db
def test_signup_rejects_weak_password(client):
    r = client.post(SIGNUP, {"tenant_name": "WeakCo", "username": "u", "password": "weak"},
                    content_type="application/json")
    assert r.status_code == 400


@pytest.mark.django_db
def test_change_password_rejects_weak_new_password(client, tenant_with_key):
    from apps.tenants.models import TenantAgent
    from apps.tenants.auth import create_tenant_agent_token

    tenant, _ = tenant_with_key
    a = TenantAgent(tenant=tenant, username="u", role="admin")
    a.set_password("Curr3nt!pw")
    a.save()
    tok = create_tenant_agent_token(a)
    r = client.post(
        "/api/tenant/agents/me/change-password",
        {"current_password": "Curr3nt!pw", "new_password": "weak"},
        content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {tok}",
    )
    assert r.status_code == 400
