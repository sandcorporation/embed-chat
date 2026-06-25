"""안전한 비밀번호 정책 (개인정보보호위원회/KISA 권장) — deep module.

규칙: **8자 이상 + 영문·숫자·특수문자 3종 모두**, 또는 **10자 이상 + 2종 이상**. 가입·비밀번호 변경이
공유하는 단일 검증원천. 위반 시 사용자에게 보일 메시지(str), 통과 시 None을 반환한다.
"""
import re

POLICY_HINT = "비밀번호는 8자 이상 영문·숫자·특수문자 3종 조합, 또는 10자 이상 2종 조합이어야 합니다."

_LETTER = re.compile(r"[A-Za-z]")
_DIGIT = re.compile(r"\d")
_SPECIAL = re.compile(r"[^A-Za-z0-9]")


def _classes(pw: str) -> int:
    return sum(bool(rx.search(pw)) for rx in (_LETTER, _DIGIT, _SPECIAL))


def password_policy_error(pw: str) -> str | None:
    if not pw or len(pw) < 8:
        return "비밀번호는 8자 이상이어야 합니다."
    classes = _classes(pw)
    if (len(pw) >= 10 and classes >= 2) or (len(pw) >= 8 and classes >= 3):
        return None
    return POLICY_HINT
