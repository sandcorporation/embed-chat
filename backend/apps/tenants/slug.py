"""Tenant Slug 검증 (deep module).

공개 챗봇 URL(/chatbot/{slug}/)에 쓰이는 식별자의 형식·정규화·예약어를 순수 함수로 검증한다.
완성형 한글 + 라틴(대소문자) + 숫자 + 하이픈을 허용한다(issue 187). 외부 의존이 없어 결정적으로
단위 테스트된다.
"""
import re
import unicodedata

# 완성형 한글(가-힣) + 라틴 대소문자 + 숫자 + 단일 하이픈. 선행/후행/연속 하이픈 금지.
# 자모 단독(ㄱ-ㅎ,ㅏ-ㅣ)·한자·이모지는 제외(혼동·사칭 표면 축소).
_SLUG_RE = re.compile(r"[가-힣A-Za-z0-9](-?[가-힣A-Za-z0-9])*")

MAX_SLUG_LEN = 63  # Tenant.slug CharField(max_length=63)

# 라우트·정적 경로와 충돌할 수 있는 예약어. slug로 등록 불가(대소문자 무시 비교).
RESERVED_SLUGS = frozenset({
    "admin", "api", "chatbot", "static", "media", "health", "www",
})


def normalize_slug(raw: str) -> str:
    """저장·비교 전 정규화: NFC + 앞뒤 공백 제거. 대소문자는 보존(원형 유지).

    macOS 자모분리(NFD)와 완성형(NFC)이 다른 바이트라 정규화 없이는 조회가 깨진다.
    """
    return unicodedata.normalize("NFC", (raw or "").strip())


def slug_key(slug: str) -> str:
    """대소문자 무시 비교 키(조회·중복·예약어용). 라틴만 접히고 한글은 무영향."""
    return normalize_slug(slug).casefold()


def is_valid_slug(slug: str) -> bool:
    s = normalize_slug(slug)
    if not s or len(s) > MAX_SLUG_LEN or _SLUG_RE.fullmatch(s) is None:
        return False
    if slug_key(s) in RESERVED_SLUGS:   # RESERVED는 소문자라 casefold 키와 직접 비교 가능
        return False
    return True
