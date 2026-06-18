"""Identity Verification (deep module).

식별된 Visitor의 visitor_id 위조를 막는 HMAC 해시를 계산·검증한다(ADR-0011).
해시는 tenant_id로 스코프된 안정값(visitor_id당 결정적)이라 유저당 1회 계산해 캐시한다.
외부 의존이 없어 결정적으로 단위 테스트된다.
"""
import hashlib
import hmac

from django.conf import settings


def compute_identity_hash(tenant_id: str, visitor_id: str) -> str:
    msg = f"{tenant_id}:{visitor_id}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()


def verify_identity(tenant_id: str, visitor_id: str, provided_hash: str) -> bool:
    if not provided_hash:
        return False
    return hmac.compare_digest(compute_identity_hash(tenant_id, visitor_id), provided_hash)
