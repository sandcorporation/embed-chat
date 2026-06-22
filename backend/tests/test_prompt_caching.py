"""프롬프트 캐싱 친화 메시지 재구조화 (issues 133-134).

휘발성(RAG·Visitor Memory)을 안정 system prefix에서 빼 뒤쪽 사용자 턴으로 옮겨,
provider 프롬프트 캐싱이 작동하도록 한다. LLM 판단이 아니라 우리 조립 코드를 검증한다(결정적).
"""


# ── Issue 133: 캐시 친화 메시지 재배치 ────────────────────────────────────────

def test_system_prefix_stable_across_volatile_context():
    """캐시 분기점: system prefix는 RAG/메모리가 달라져도 byte-동일해야 캐싱이 작동한다."""
    from apps.agent.nodes import _assemble_lc_messages

    base = {"system_prompt": "You are X.", "messages": [], "user_message": "안녕"}
    a = _assemble_lc_messages({**base, "rag_chunks": ["fact A"], "visitor_memories": []})
    b = _assemble_lc_messages({**base, "rag_chunks": ["fact B 1920x1080"], "visitor_memories": ["좋아함"]})

    # 안정 system prefix는 휘발성과 무관하게 동일
    assert a[0].content == b[0].content
    # 휘발성은 system에 없다
    assert "fact A" not in a[0].content
    assert "fact B" not in b[0].content
    assert "좋아함" not in b[0].content


def test_volatile_context_moves_to_trailing_user_turn():
    """RAG·Visitor Memory는 뒤쪽 사용자 턴에 UNTRUSTED_DATA 격리로 실린다."""
    from apps.agent.nodes import _assemble_lc_messages

    msgs = _assemble_lc_messages({
        "system_prompt": "You are X.",
        "messages": [],
        "rag_chunks": ["해상도 1920x1080"],
        "visitor_memories": ["이름 홍길동"],
        "user_message": "해상도 알려줘",
    })

    trailing = msgs[-1].content
    assert "1920x1080" in trailing       # RAG가 뒤쪽 턴에
    assert "이름 홍길동" in trailing      # 메모리도 뒤쪽 턴에
    assert "UNTRUSTED_DATA" in trailing  # 격리 유지
    assert "해상도 알려줘" in trailing    # 현재 질문도 같은 턴
    # 보안 지침은 안정 system에 남는다
    assert "노출" in msgs[0].content


# ── Issue 134: Anthropic cache_control 마커 (boundary, provider-aware) ─────────

def test_anthropic_provider_marks_system_with_cache_control():
    """anthropic provider면 안정 system 블록 끝에 cache_control(ephemeral) 분기점이 붙는다."""
    from langchain_core.messages import SystemMessage, HumanMessage
    from apps.agent.llm import _mark_cache_breakpoint
    from apps.agent.providers import LLMProvider

    msgs = [SystemMessage(content="STABLE PREFIX"), HumanMessage(content="질문")]
    out = _mark_cache_breakpoint(LLMProvider(type="anthropic", model="claude"), msgs)

    sys = out[0]
    assert isinstance(sys.content, list)                       # 블록 리스트로 변환
    assert sys.content[-1]["text"] == "STABLE PREFIX"
    assert sys.content[-1]["cache_control"] == {"type": "ephemeral"}
    assert out[1].content == "질문"                             # 나머지는 불변


def test_non_anthropic_providers_get_no_marker():
    """openai/custom/플랫폼기본은 자동 prefix 캐싱 — cache_control 마커를 붙이지 않는다."""
    from langchain_core.messages import SystemMessage, HumanMessage
    from apps.agent.llm import _mark_cache_breakpoint
    from apps.agent.providers import LLMProvider

    for t in ("openai", "custom", ""):
        msgs = [SystemMessage(content="STABLE PREFIX"), HumanMessage(content="질문")]
        out = _mark_cache_breakpoint(LLMProvider(type=t, model="m"), msgs)
        assert out[0].content == "STABLE PREFIX"  # 문자열 그대로, 마커 없음
