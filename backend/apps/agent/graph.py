from typing import Annotated, List
import operator
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from apps.agent.nodes import (
    route_search_node,
    local_search_node,
    global_search_node,
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
    search_scope: str
    assistant_response: str
    needs_hitl: bool
    hitl_reason: str
    context_sufficient: bool
    source_text_tried: bool


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


def _route_scope(state: ChatState) -> str:
    return "global_search" if state.get("search_scope") == "global" else "local_search"


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

    graph.add_node("route_search", route_search_node)
    graph.add_node("local_search", local_search_node)
    graph.add_node("global_search", global_search_node)
    graph.add_node("source_search", source_search_node)
    graph.add_node("save_messages", save_messages_node)

    graph.add_edge(START, "route_search")
    graph.add_conditional_edges("route_search", _route_scope, {
        "local_search": "local_search",
        "global_search": "global_search",
    })

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
    graph.add_edge("global_search", "call_llm")
    graph.add_edge("source_search", "call_llm")  # 원문 보강 후 LLM 재호출
    graph.add_edge("save_messages", END)

    return graph.compile(checkpointer=checkpointer)


def run_chat_agent(session, user_message: str) -> str:
    from apps.tenants.models import TenantConfig
    from apps.memory.manager import get_visitor_memories
    from apps.agent.providers import set_chat_provider, chat_provider

    config = TenantConfig.objects.get(tenant_id=session.tenant_id)
    # 챗 그래프 노드가 쓸 LLM provider를 컨텍스트에 싣는다(비밀키를 state/Checkpoint에 안 넣음).
    set_chat_provider(chat_provider(config))
    memories = get_visitor_memories(str(session.tenant_id), session.visitor_id)

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
        "search_scope": "local",
        "assistant_response": "",
        "needs_hitl": False,
        "hitl_reason": "",
        "context_sufficient": True,
        "source_text_tried": False,
    }

    saver, conn = _create_checkpointer()
    try:
        graph = build_graph(checkpointer=saver, hitl_enabled=config.hitl_enabled)
        result = graph.invoke(
            initial_state,
            config={"configurable": {"thread_id": str(session.id)}},
        )
    finally:
        conn.close()

    return result["assistant_response"]
