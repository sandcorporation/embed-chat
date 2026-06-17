from ninja import NinjaAPI
from apps.core.api import router as core_router
from apps.tenants.api import operator_router, tenant_router, agent_router
from apps.chat.api import embed_router, chat_router
from apps.rag.api import rag_router
from apps.memory.api import memory_router, session_router
from apps.escalation.api import escalation_router

api = NinjaAPI(title="Embed Chat API", version="1.0.0")

api.add_router("/", core_router)
api.add_router("/operator", operator_router)
api.add_router("/tenant", tenant_router)
api.add_router("/tenant/agents", agent_router)
api.add_router("/embed", embed_router)
api.add_router("/chat", chat_router)
api.add_router("/tenant/documents", rag_router)
api.add_router("/tenant/visitors", memory_router)
api.add_router("/tenant/sessions", session_router)
api.add_router("/tenant/escalations", escalation_router)
