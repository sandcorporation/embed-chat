"""챗 응답 토큰 스트리밍 (PRD-chat-token-streaming, issues 170-172). 노드 async화 전환.

LLM은 결정적 Fake(conftest fake가 astream_structured로 제어필드 먼저 → response 청크 yield).
노드가 델타를 apublish하고 폴백 패스에선 억제하는 행동을 검증한다.
"""
import pytest
from asgiref.sync import sync_to_async

adb = sync_to_async


def _capture_publish(monkeypatch, tokens, dones):
    from apps.agent import nodes
    async def _atok(sid, content):
        tokens.append(content)
    async def _adone(sid):
        dones["n"] += 1
    monkeypatch.setattr(nodes, "apublish_token", _atok)
    monkeypatch.setattr(nodes, "apublish_done", _adone)


@pytest.mark.django_db(transaction=True)
async def test_chat_answer_streams_token_deltas(tenant_with_key, fake_chat_llm, monkeypatch):
    """종단 패스에서 응답이 토큰 델타로 여러 번 publish되고 누적이 전체와 일치한다(실시간)."""
    from apps.agent.graph import run_chat_agent_async
    from apps.agent.nodes import HITLResponse
    from apps.chat.models import ChatSession

    fake_chat_llm.override = lambda messages: HITLResponse(
        response="안녕하세요 반갑습니다", needs_hitl=False, hitl_reason="", context_sufficient=True)
    tokens, dones = [], {"n": 0}
    _capture_publish(monkeypatch, tokens, dones)

    tenant, _ = tenant_with_key
    session = await adb(ChatSession.objects.create)(tenant_id=tenant.id, visitor_id="v-stream")
    answer = await run_chat_agent_async(session, "안녕")

    assert answer == "안녕하세요 반갑습니다"
    assert len(tokens) >= 2                          # 델타로 여러 번 흘림
    assert "".join(tokens) == "안녕하세요 반갑습니다"   # 누적 = 전체
    assert dones["n"] == 1


@pytest.mark.django_db(transaction=True)
async def test_streaming_degrades_to_oneshot_when_control_field_late(tenant_with_key, monkeypatch):
    """제어필드가 response보다 늦게 오는 provider면 자동으로 one-shot 저하한다(중복·깨짐 없음)."""
    from apps.agent import llm
    from apps.agent.graph import run_chat_agent_async
    from apps.chat.models import ChatSession

    async def control_late_astream(provider, messages, schema):
        yield {"response": "전체응답입니다"}                       # response 먼저(제어 없음)
        yield {"response": "전체응답입니다", "context_sufficient": True}  # 제어 늦게
    monkeypatch.setattr(llm, "astream_structured", control_late_astream)

    tokens, dones = [], {"n": 0}
    _capture_publish(monkeypatch, tokens, dones)

    tenant, _ = tenant_with_key
    session = await adb(ChatSession.objects.create)(tenant_id=tenant.id, visitor_id="v-late")
    answer = await run_chat_agent_async(session, "안녕")

    assert answer == "전체응답입니다"
    assert tokens == ["전체응답입니다"]   # 점진 스트림 없이 한 번에(저하)
    assert dones["n"] == 1


@pytest.mark.django_db(transaction=True)
async def test_hitl_off_path_streams_token_deltas(tenant_with_key, fake_chat_llm, monkeypatch):
    """HITL-off 테넌트(call_llm_plain / PlainResponse)도 델타로 스트리밍한다(issue 171)."""
    from apps.agent.graph import run_chat_agent_async
    from apps.agent.nodes import PlainResponse
    from apps.chat.models import ChatSession
    from apps.tenants.models import TenantConfig

    tenant, _ = tenant_with_key

    def _disable():
        config = TenantConfig.objects.get(tenant=tenant)
        config.hitl_enabled = False
        config.save()
    await adb(_disable)()

    fake_chat_llm.override = lambda messages: PlainResponse(
        response="도와드릴게요 무엇이든", context_sufficient=True)
    tokens, dones = [], {"n": 0}
    _capture_publish(monkeypatch, tokens, dones)

    session = await adb(ChatSession.objects.create)(tenant_id=tenant.id, visitor_id="v-plain")
    answer = await run_chat_agent_async(session, "안녕")

    assert answer == "도와드릴게요 무엇이든"
    assert len(tokens) >= 2
    assert "".join(tokens) == "도와드릴게요 무엇이든"
    assert dones["n"] == 1


@pytest.mark.django_db(transaction=True)
async def test_kill_switch_disables_streaming(tenant_with_key, fake_chat_llm, settings, monkeypatch):
    """CHAT_STREAMING_ENABLED=False면 현행 one-shot으로 동작한다(델타 없이 1회·issue 172)."""
    settings.CHAT_STREAMING_ENABLED = False
    from apps.agent.graph import run_chat_agent_async
    from apps.agent.nodes import HITLResponse
    from apps.chat.models import ChatSession

    fake_chat_llm.override = lambda messages: HITLResponse(
        response="한방에 답합니다", needs_hitl=False, hitl_reason="", context_sufficient=True)
    tokens, dones = [], {"n": 0}
    _capture_publish(monkeypatch, tokens, dones)

    tenant, _ = tenant_with_key
    session = await adb(ChatSession.objects.create)(tenant_id=tenant.id, visitor_id="v-killswitch")
    answer = await run_chat_agent_async(session, "안녕")

    assert answer == "한방에 답합니다"
    assert tokens == ["한방에 답합니다"]   # one-shot(델타 아님)
    assert dones["n"] == 1


@pytest.mark.django_db(transaction=True)
async def test_stream_error_propagates_without_false_done(tenant_with_key, monkeypatch):
    """스트림 도중 예외는 에러 경계로 전파되며(거짓 done 없이), chat_task가 publish_error로 알린다."""
    from apps.agent import llm
    from apps.agent.graph import run_chat_agent_async
    from apps.chat.models import ChatSession

    async def boom(provider, messages, schema):
        yield {"context_sufficient": True, "response": "부분"}
        raise RuntimeError("stream blew up")
    monkeypatch.setattr(llm, "astream_structured", boom)

    tokens, dones = [], {"n": 0}
    _capture_publish(monkeypatch, tokens, dones)

    tenant, _ = tenant_with_key
    session = await adb(ChatSession.objects.create)(tenant_id=tenant.id, visitor_id="v-err")
    with pytest.raises(RuntimeError):
        await run_chat_agent_async(session, "안녕")

    assert dones["n"] == 0   # 에러 시 거짓 완료(done) 미발행 — chat_task가 publish_error 처리
