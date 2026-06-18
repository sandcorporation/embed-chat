from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from pydantic import BaseModel

from apps.agent import llm as llm_boundary
from apps.chat.sse import publish_token, publish_done, publish_hitl_start, publish_hitl_new


class HITLResponse(BaseModel):
    response: str
    needs_hitl: bool
    hitl_reason: str = ""


class PlainResponse(BaseModel):
    """HITL-OFF Tenant용 구조화 출력 — needs_hitl 필드가 없어 escalation을 표현할 수 없다."""
    response: str


class SearchRoute(BaseModel):
    search_scope: str = "local"  # "local" | "global"


def route_search_node(state: dict) -> dict:
    """질의를 local/global로 분류한다 (구조화 출력 한 번)."""
    prompt = (
        "Classify the scope of the user's question. Respond with search_scope = "
        "'global' if it asks for a summary across many documents or common themes; "
        "'local' if it is about a specific entity or fact.\n\n"
        f"Question: {state['user_message']}"
    )
    result = llm_boundary.complete_structured(
        state["model_id"], [HumanMessage(content=prompt)], SearchRoute
    )
    scope = result.search_scope if result.search_scope in ("local", "global") else "local"
    return {"search_scope": scope}


def local_search_node(state: dict) -> dict:
    """엔티티 중심 근거 — 질의로 resolved Entity를 찾고 그 이웃 관계를 모은다.

    거대한 Text Unit chunk 대신 구조화된 Entity·Relation을 근거로 전달한다(ADR-0010).
    """
    from apps.rag.graph_store import GraphStore

    gs = GraphStore(state["tenant_id"])
    matched = gs.search_entities(state["user_message"], top_k=5)

    chunks = []
    seen_entities = set()
    seen_edges = set()
    for ent in matched:
        name = ent["name"]
        if name in seen_entities:
            continue
        seen_entities.add(name)
        desc = ent.get("description") or ""
        chunks.append(f"{name}: {desc}".strip(": ") if desc else name)

        for edge in gs.neighbors(name)["edges"]:
            key = (edge["source"], edge["target"], edge.get("description"))
            if key in seen_edges:
                continue
            seen_edges.add(key)
            chunks.append(f"{edge['source']} —{edge.get('description') or ''}→ {edge['target']}")

    return {"rag_chunks": chunks}


def global_search_node(state: dict) -> dict:
    """전체/요약형 근거 — Tenant의 Community 요약을 모은다."""
    from apps.rag.graph_store import GraphStore

    communities = GraphStore(state["tenant_id"]).query_community_summaries()
    return {"rag_chunks": [c["summary"] for c in communities if c.get("summary")]}


def _assemble_lc_messages(state: dict) -> list:
    """system 프롬프트 + Visitor Context/Memory + RAG + 대화 history로 LLM 입력을 조립한다.

    프롬프트 조립물(lc_messages)은 LLM 호출용 임시 산출물이므로 그래프 채널에 저장하지 않고
    호출 노드 내부 로컬로만 사용한다 (Checkpoint 중복 방지).
    """
    parts = [state["system_prompt"]]

    if state.get("visitor_memories"):
        mem_lines = "\n".join(f"- {m}" for m in state["visitor_memories"])
        parts.append(f"\n## Visitor Memory\n{mem_lines}")

    if state.get("rag_chunks"):
        rag_text = "\n\n".join(state["rag_chunks"])
        parts.append(f"\n## Knowledge Base\n{rag_text}")

    system_content = "\n".join(parts)

    lc_messages = [SystemMessage(content=system_content)]
    for msg in state.get("messages", []):
        if msg["role"] == "user":
            lc_messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            lc_messages.append(AIMessage(content=msg["content"]))
    lc_messages.append(HumanMessage(content=state["user_message"]))
    return lc_messages


def call_llm_structured(state: dict) -> dict:
    lc_messages = _assemble_lc_messages(state)

    result = llm_boundary.complete_structured(state["model_id"], lc_messages, HITLResponse)

    # HITL 여부와 무관하게, AI가 만든 응답(전환 멘트 포함)이 있으면 사용자에게 스트리밍한다.
    if result.response:
        publish_token(state["session_id"], result.response)
        publish_done(state["session_id"])

    return {
        "assistant_response": result.response,
        "needs_hitl": result.needs_hitl,
        "hitl_reason": result.hitl_reason,
    }


def call_llm_plain(state: dict) -> dict:
    """HITL-OFF 경로: needs_hitl 없는 response-only 출력. 전환 멘트 누수가 구조적으로 불가능."""
    lc_messages = _assemble_lc_messages(state)
    result = llm_boundary.complete_structured(state["model_id"], lc_messages, PlainResponse)

    if result.response:
        publish_token(state["session_id"], result.response)
        publish_done(state["session_id"])

    return {"assistant_response": result.response, "needs_hitl": False, "hitl_reason": ""}


def create_escalation_node(state: dict) -> dict:
    from apps.chat.models import ChatSession, ChatMessage
    from apps.escalation.models import Escalation

    session = ChatSession.objects.get(id=state["session_id"])
    session.is_hitl = True
    session.save(update_fields=["is_hitl"])

    # AI가 만든 전환 멘트가 있으면 사용자 대화에 남긴다(이미 SSE로 스트리밍됨).
    response = state.get("assistant_response") or ""
    if response:
        ChatMessage.objects.create(
            session=session, role=ChatMessage.ROLE_ASSISTANT, content=response
        )

    escalation = Escalation.objects.create(
        session=session,
        trigger_type=Escalation.TRIGGER_AI,
        reason=state.get("hitl_reason", ""),
        status=Escalation.STATUS_PENDING,
    )

    publish_hitl_start(state["session_id"])
    publish_hitl_new(state["tenant_id"], state["session_id"], state.get("hitl_reason", ""))

    try:
        from apps.escalation.tasks import dispatch_webhook_task
        dispatch_webhook_task.delay(str(escalation.id))
    except Exception:
        pass

    messages = [{"role": "user", "content": state["user_message"]}]
    if response:
        messages.append({"role": "assistant", "content": response})
    return {"messages": messages}


def save_messages_node(state: dict) -> dict:
    from apps.chat.models import ChatSession, ChatMessage
    from apps.memory.tasks import schedule_memory_extraction

    try:
        session = ChatSession.objects.get(id=state["session_id"])
        ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_ASSISTANT,
            content=state["assistant_response"],
        )
        schedule_memory_extraction.delay(
            str(session.tenant_id),
            session.visitor_id,
            str(session.id),
        )
    except Exception:
        pass

    return {
        "messages": [
            {"role": "user", "content": state["user_message"]},
            {"role": "assistant", "content": state["assistant_response"]},
        ]
    }
