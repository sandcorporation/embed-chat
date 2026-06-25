"""Tenant Self-Signup (ADR-0025) — deep module.

조직 이름(전역 unique·대소문자/공백 무시)·username·password로 Tenant와 그 조직의 첫 Tenant Admin을
한 트랜잭션에 만든다. 이름은 표시명이자 로그인 식별자라 정규화(trim)해 저장하고, 충돌은 대소문자
무시로 본다(DB는 Lower(name) unique로 backstop).
"""
import secrets
from django.db import transaction

from apps.tenants.models import Tenant, TenantAgent


class DuplicateOrgName(Exception):
    """이미 사용 중인 조직 이름."""


class InvalidSignup(Exception):
    """가입 입력이 유효하지 않음(빈 이름/username 등)."""


def normalize_org_name(name: str) -> str:
    return (name or "").strip()


@transaction.atomic
def register_tenant(name: str, username: str, password: str) -> tuple[Tenant, TenantAgent]:
    from apps.tenants.password_policy import password_policy_error

    name = normalize_org_name(name)
    username = (username or "").strip()
    if not name or not username or not password:
        raise InvalidSignup("조직 이름·username·password는 비울 수 없습니다.")
    pw_err = password_policy_error(password)
    if pw_err:
        raise InvalidSignup(pw_err)
    if Tenant.objects.filter(name__iexact=name).exists():  # 친절한 사전 검사(DB는 backstop)
        raise DuplicateOrgName(name)

    raw_key = secrets.token_urlsafe(32)
    tenant = Tenant.objects.create_with_key(name=name, raw_key=raw_key)  # Tenant + TenantConfig
    agent = TenantAgent(tenant=tenant, username=username, role=TenantAgent.ROLE_ADMIN)
    agent.set_password(password)
    agent.save()
    return tenant, agent
