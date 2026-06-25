"""주제범위 제어 (deep module) — PRD-topic-scope-enforcement.

봇이 응대 범위(scope_description) 밖 질문에 답하지 않게 한다. 프롬프트로 모델이 in_scope를
판정하게 유도하고(scope_instruction), 코드가 백스톱으로 거절을 강제한다(scope_decision) — 모델이
지침을 무시해도 범위 밖 답이 새지 않는다. 토글 OFF나 범위 미설정이면 완전 미작동(fail-open)이라
기존 동작은 무변경이다.
"""

_STANDARD_REFUSAL = "죄송해요, 저는 {scope} 관련 문의를 도와드려요. 그쪽 내용으로 다시 물어봐 주시겠어요?"


def _active(enabled: bool, scope_description: str) -> bool:
    """게이트가 실제로 작동하는 조건 — 토글 ON이고 범위 설명이 비어 있지 않을 때만(fail-open)."""
    return bool(enabled and (scope_description or "").strip())


def scope_decision(*, enabled: bool, scope_description: str, in_scope: bool,
                   model_response: str, refusal_message: str = "") -> tuple[bool, str]:
    """주제범위 백스톱 결정. 반환 (refused, final_response).

    미작동(토글 OFF·범위 공백) 또는 in_scope=True면 모델 응답 그대로 통과. in_scope=False면 거절 —
    refusal_message가 있으면 그 문구, 없으면 scope_description을 인용한 표준 템플릿.
    """
    if not _active(enabled, scope_description) or in_scope:
        return False, model_response
    msg = (refusal_message or "").strip() or _STANDARD_REFUSAL.format(scope=scope_description.strip())
    return True, msg


def scope_instruction(enabled: bool, scope_description: str) -> str:
    """토글 ON + 범위 있으면 system prompt에 붙일 스코프 지침 블록, 아니면 ''."""
    if not _active(enabled, scope_description):
        return ""
    scope = scope_description.strip()
    return (
        "\n## 응대 범위 (반드시 준수)\n"
        f"- 이 어시스턴트의 응대 범위: {scope}\n"
        "- 위 범위를 벗어난 질문이면 in_scope를 false로 두세요(코드가 정중히 거절합니다).\n"
        "- 인사·감사·범위 안내 같은 대화 턴은 in_scope를 true로 두고 자연스럽게 응답하세요.\n"
        "- 범위 안 질문은 제공된 Knowledge Base 근거로만 답하세요."
    )
