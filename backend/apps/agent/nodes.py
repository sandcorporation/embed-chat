from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from pydantic import BaseModel

from apps.agent import llm as llm_boundary
from apps.chat.sse import publish_token, publish_done, publish_hitl_start, publish_hitl_new


class HITLResponse(BaseModel):
    response: str
    needs_hitl: bool
    hitl_reason: str = ""


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
    """엔티티 중심 근거 — Knowledge Graph의 Text Unit을 벡터로 검색한다."""
    from apps.rag.graph_store import GraphStore
    from apps.rag.ingesters import get_embeddings

    query_embedding = get_embeddings([state["user_message"]])[0]
    units = GraphStore(state["tenant_id"]).vector_search(query_embedding, top_k=5)
    return {"rag_chunks": [u["content"] for u in units]}


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

    if state.get("visitor_context"):
        ctx_lines = "\n".join(f"- {k}: {v}" for k, v in state["visitor_context"].items())
        parts.append(f"\n## Visitor Context\n{ctx_lines}")

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

    if not result.needs_hitl and result.response:
        publish_token(state["session_id"], result.response)
        publish_done(state["session_id"])

    return {
        "assistant_response": result.response,
        "needs_hitl": result.needs_hitl,
        "hitl_reason": result.hitl_reason,
    }


def create_escalation_node(state: dict) -> dict:
    from apps.chat.models import ChatSession
    from apps.escalation.models import Escalation

    session = ChatSession.objects.get(id=state["session_id"])
    session.is_hitl = True
    session.save(update_fields=["is_hitl"])

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

    return {
        "messages": [
            {"role": "user", "content": state["user_message"]},
        ]
    }


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
