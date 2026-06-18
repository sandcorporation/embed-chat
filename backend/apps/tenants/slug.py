"""Tenant Slug 검증 (deep module).

공개 챗봇 URL(/chatbot/{slug}/)에 쓰이는 식별자의 형식·예약어를 순수 함수로 검증한다.
외부 의존이 없어 결정적으로 단위 테스트된다.
"""
import re

# 소문자 영숫자 + 단일 하이픈. 선행/후행/연속 하이픈 금지.
_SLUG_RE = re.compile(r"[a-z0-9](-?[a-z0-9])*")

# 라우트·정적 경로와 충돌할 수 있는 예약어. slug로 등록 불가.
RESERVED_SLUGS = frozenset({
    "admin", "api", "chatbot", "static", "media", "health", "www",
})


def is_valid_slug(slug: str) -> bool:
    if not slug or _SLUG_RE.fullmatch(slug) is None:
        return False
    if slug in RESERVED_SLUGS:
        return False
    return True
