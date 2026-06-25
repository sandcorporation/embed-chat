# langgraph add_node / psycopg PostgresSaver의 느슨한 시그니처 타입 — 런타임은 정상.
# pyright: reportArgumentType=false
from typing import Annotated, List
import operator
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from apps.agent.nodes import (
    local_search_node,
    source_search_node,
    call_llm_structured,
    call_llm_plain,
    create_escalation_node,
    save_messages_node,
)


class ChatState(TypedDict):
    session_id: str
    tenant_id: str
    visitor_id: str
    system_prompt: str
    model_id: str
    user_message: str
    messages: Annotated[List[dict], operator.add]
    rag_chunks: List[str]
    visitor_memories: List[str]
    assistant_response: str
    needs_hitl: bool
    hitl_reason: str
    context_sufficient: bool
    source_text_tried: bool
    operational_notice: str
    topic_scope_enabled: bool
    scope_description: str


def _route_after_llm(state: ChatState) -> str:
    """그래프-only가 답을 못 냈고(폴백 미사용) 원문을 아직 안 썼으면 원문 폴백으로, 아니면 기존 라우팅."""
    if not state.get("context_sufficient", True) and not state.get("source_text_tried", False):
        return "source_search"
    return "create_escalation" if state.get("needs_hitl") else "save_messages"


def _route_after_llm_plain(state: ChatState) -> str:
    """HITL-OFF 경로: 폴백 분기 + save_messages 직행(escalation 없음)."""
    if not state.get("context_sufficient", True) and not state.get("source_text_tried", False):
        return "source_search"
    return "save_messages"


def _build_conninfo() -> str:
    from django.db import connection as django_connection
    d = django_connection.settings_dict
    return (
        f"dbname={d['NAME']} user={d['USER']} "
        f"password={d['PASSWORD']} host={d['HOST']} port={d['PORT']}"
    )


def _create_checkpointer():
    import psycopg
    from langgraph.checkpoint.postgres import PostgresSaver

    conninfo = _build_conninfo()
    # setup()은 CREATE INDEX CONCURRENTLY를 사용하므로 autocommit 필요
    with psycopg.connect(conninfo, autocommit=True) as setup_conn:
        PostgresSaver(setup_conn).setup()

    # autocommit=True: PostgresSaver.put()이 명시적 commit을 호출하지 않아
    # non-autocommit 연결에서 close() 시 롤백이 발생하기 때문
    conn = psycopg.connect(conninfo, autocommit=True)
    saver = PostgresSaver(conn)
    return saver, conn


def build_graph(checkpointer=None, hitl_enabled=True):
    """hitl_enabled 불리언으로 토폴로지+call_llm 스키마를 다르게 컴파일한다(issue 88).

    HITL-OFF는 response-only call_llm → save_messages 직행이며 escalation 노드가 없어,
    needs_hitl을 구조적으로 표현할 수 없다(전환 멘트 누수 차단).
    """
    graph = StateGraph(ChatState)

    graph.add_node("local_search", local_search_node)
    graph.add_node("source_search", source_search_node)
    graph.add_node("save_messages", save_messages_node)

    # Global Search/router 제거(ADR-0016) — 항상 Local Search로 직결.
    graph.add_edge(START, "local_search")

    if hitl_enabled:
        graph.add_node("call_llm", call_llm_structured)
        graph.add_node("create_escalation", create_escalation_node)
        # 그래프-only가 답을 못 내면 원문 폴백(1회) → 재호출, 아니면 hitl/save로 분기.
        graph.add_conditional_edges("call_llm", _route_after_llm, {
            "source_search": "source_search",
            "create_escalation": "create_escalation",
            "save_messages": "save_messages",
        })
        graph.add_edge("create_escalation", END)
    else:
        graph.add_node("call_llm", call_llm_plain)
        graph.add_conditional_edges("call_llm", _route_after_llm_plain, {
            "source_search": "source_search",
            "save_messages": "save_messages",
        })

    graph.add_edge("local_search", "call_llm")
    graph.add_edge("source_search", "call_llm")  # 원문 보강 후 LLM 재호출
    graph.add_edge("save_messages", END)

    return graph.compile(checkpointer=checkpointer)


def _off_hours_notice(config) -> str:
    """상담시간 외에 trailing 컨텍스트로 실을 운영 안내(휘발성이라 system prefix를 안 깸)."""
    return (
        "[운영 안내] 지금은 상담원 연결 가능 시간이 아닙니다. "
        "운영시간에 다시 문의해 주시면 상담원이 도와드립니다. 현재는 AI가 답변합니다."
    )


def _load_chat_inputs(session, user_message: str):
    """DB 의존 입력(config·memories·영업시간 게이팅)으로 initial_state·effective_hitl·provider를 만든다(sync).

    provider/usage ContextVar는 여기서 설정하지 않는다 — sync_to_async 스레드의 ContextVar는 이벤트
    루프 노드로 전파되지 않으므로, 호출자(run_chat_agent_async, 이벤트루프)가 반환된 provider로 set한다.
    """
    from django.utils import timezone
    from apps.tenants.models import TenantConfig
    from apps.tenants import business_hours
    from apps.memory.manager import get_visitor_memories
    from apps.agent.providers import chat_provider

    config = TenantConfig.objects.get(tenant_id=session.tenant_id)
    provider = chat_provider(config)
    memories = get_visitor_memories(str(session.tenant_id), session.visitor_id)

    # 영업시간 게이팅(issue 136): HITL이 켜져 있어도 상담시간 외엔 plain 그래프로 떨어뜨려 AI 자동
    # escalation을 막는다. 시간 외엔 운영 안내를 trailing 컨텍스트에 실어 AI가 자연스럽게 안내한다.
    open_now = business_hours.is_open(config, timezone.now())
    effective_hitl = config.hitl_enabled and open_now
    operational_notice = _off_hours_notice(config) if (config.hitl_enabled and not open_now) else ""

    initial_state: ChatState = {
        "session_id": str(session.id),
        "tenant_id": str(session.tenant_id),
        "visitor_id": session.visitor_id,
        "system_prompt": config.system_prompt,
        "model_id": config.model_id,
        "user_message": user_message,
        "messages": [],  # Checkpoint이 이전 메시지 복원
        "rag_chunks": [],
        "visitor_memories": memories,
        "assistant_response": "",
        "needs_hitl": False,
        "hitl_reason": "",
        "context_sufficient": True,
        "source_text_tried": False,
        "operational_notice": operational_notice,
        "topic_scope_enabled": config.topic_scope_enabled,
        "scope_description": config.scope_description or "",
    }
    return initial_state, effective_hitl, provider


async def run_chat_agent_async(session, user_message: str) -> str:
    """chat 1턴을 async로 실행한다(노드 async화 — issue 192/195). 호출 위치(taskiq/인라인) 무관.

    DB 의존 입력은 sync_to_async로 로드하고, provider/usage ContextVar는 이벤트루프 컨텍스트에서
    set해 async 노드(call_llm 등)로 전파한다. 체크포인터는 from_conn_string(async context manager)으로
    커넥션을 확실히 정리한다. 노드가 async라 ainvoke가 네이티브로 실행 — executor 스레드 누수 없음.
    """
    from asgiref.sync import sync_to_async
    from apps.agent.providers import set_chat_provider
    from apps.usage.context import set_usage_context
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    initial_state, effective_hitl, provider = await sync_to_async(_load_chat_inputs)(session, user_message)
    set_chat_provider(provider)  # 이벤트루프 컨텍스트 → async 노드로 전파(비밀키는 state/Checkpoint에 안 넣음)
    set_usage_context(session.tenant_id, "chat", session_id=session.id)

    conninfo = _build_conninfo()
    async with AsyncPostgresSaver.from_conn_string(conninfo) as saver:
        await saver.setup()
        graph = build_graph(checkpointer=saver, hitl_enabled=effective_hitl)
        result = await graph.ainvoke(
            initial_state,
            config={"configurable": {"thread_id": str(session.id)}},
        )

    return result["assistant_response"]
