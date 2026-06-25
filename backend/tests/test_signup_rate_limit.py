"""공개 가입 IP 레이트리밋 (issue 211 후속) — IP당 1시간 1회, 성공 가입만 슬롯 소비.

실 Redis로 결정적 검증(우리 인프라). 가입 RL 키는 conftest autouse가 테스트마다 정리해 독립성을 보장.
"""
import pytest

SIGNUP = "/api/tenant/agents/auth/signup"


def test_allow_then_block_same_ip():
    from apps.tenants.signup_rate_limit import signup_allowed, mark_signup
    ip = "203.0.113.7"
    assert signup_allowed(ip) is True
    mark_signup(ip)
    assert signup_allowed(ip) is False


def _signup(client, org, ip, pw="pw12345678"):
    return client.post(
        SIGNUP, {"tenant_name": org, "username": "u", "password": pw},
        content_type="application/json", HTTP_X_FORWARDED_FOR=ip,
    )


@pytest.mark.django_db
def test_second_signup_same_ip_within_hour_is_429(client):
    assert _signup(client, "RL One", "198.51.100.5").status_code == 201
    assert _signup(client, "RL Two", "198.51.100.5").status_code == 429


@pytest.mark.django_db
def test_failed_signup_does_not_consume_slot(client):
    assert _signup(client, "RL Weak", "198.51.100.6", pw="weak").status_code == 400  # 정책 위반
    assert _signup(client, "RL Good", "198.51.100.6").status_code == 201             # 슬롯 미소비 → 허용


@pytest.mark.django_db
def test_different_ip_not_limited(client):
    assert _signup(client, "RL A", "198.51.100.10").status_code == 201
    assert _signup(client, "RL B", "198.51.100.11").status_code == 201
