"""Issue 102 — 만료·폐기 RefreshToken 정리(GC). ADR-0013.

동시 Family 수 상한이 없으므로 이 정리가 유일한 GC 경로다.
"""
import pytest


def _make_operator(username="pruneop"):
    from apps.tenants.models import Operator
    return Operator.objects.create(username=username)


@pytest.mark.django_db
def test_prune_deletes_expired_and_revoked_keeps_valid():
    from datetime import timedelta
    from django.utils import timezone
    from apps.tenants.models import RefreshToken
    from apps.tenants.refresh_tokens import issue_session, prune_refresh_tokens, _hash

    op = _make_operator()
    valid_raw = issue_session(op)

    expired_raw = issue_session(op)
    RefreshToken.objects.filter(token_hash=_hash(expired_raw)).update(
        family_expires_at=timezone.now() - timedelta(seconds=1)
    )

    revoked_raw = issue_session(op)
    RefreshToken.objects.filter(token_hash=_hash(revoked_raw)).update(revoked=True)

    deleted = prune_refresh_tokens()

    hashes = set(RefreshToken.objects.values_list("token_hash", flat=True))
    assert _hash(valid_raw) in hashes          # 유효 row 보존
    assert _hash(expired_raw) not in hashes     # 만료 삭제
    assert _hash(revoked_raw) not in hashes     # 폐기 삭제
    assert deleted == 2


@pytest.mark.django_db
def test_prune_command_runs():
    from django.core.management import call_command
    from apps.tenants.refresh_tokens import issue_session

    op = _make_operator("cmdop")
    issue_session(op)
    # 관리 커맨드가 예외 없이 실행된다(주기 작업 진입점)
    call_command("prune_refresh_tokens")
