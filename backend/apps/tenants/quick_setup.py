"""OpenAI 한방 Provider 설정 (deep module) — PRD-openai-quick-setup.

OpenAI API 키 1개로 LLM(챗+추출)·Embedding·OCR(Vision) 3종을 기본 모델/차원으로 한 번에 설정한다.
키는 chat/embed/vision 전 엔드포인트 공통이라 **1회 검증**으로 충분하고, 검증 실패 시 아무것도
저장하지 않는다(원자성). 기본 모델/차원은 여기 한 곳(서버 단일 출처)에 둔다.
"""

# 기본 모델/차원 — 저렴 기본(고급에서 gpt-4o 등으로 변경). text-embedding-3-small은 1536차원.
OPENAI_CHAT_MODEL = "gpt-4o-mini"
OPENAI_EMBED_MODEL = "text-embedding-3-small"
OPENAI_EMBED_DIM = 1536
OPENAI_OCR_MODEL = "gpt-4o-mini"


def openai_quick_setup(config, api_key: str) -> None:
    """OpenAI 키 1개로 3종 Provider를 기본값으로 설정한다.

    검증 실패 시 `ProviderError`를 올리고 config는 건드리지 않는다(검증을 필드 설정보다 먼저).
    키는 암호화 저장한다.
    """
    from apps.agent.provider_models import validate_provider
    from apps.tenants.crypto import encrypt_secret

    # 키 1회 검증(models 조회) — 실패 시 ProviderError 전파, 아래 설정/save에 도달하지 않음.
    validate_provider("llm", "openai", "", api_key, OPENAI_CHAT_MODEL)

    enc = encrypt_secret(api_key)
    config.llm_provider_type = "openai"
    config.llm_base_url = ""  # openai는 표준 주소로 자동 보정
    config.llm_api_key = enc
    config.model_id = OPENAI_CHAT_MODEL
    config.extraction_model = ""  # 빈값 = 대화 모델과 동일
    config.embed_provider_type = "openai"
    config.embed_base_url = ""
    config.embed_api_key = enc
    config.embed_model = OPENAI_EMBED_MODEL
    config.embed_dim = OPENAI_EMBED_DIM
    config.ocr_provider_type = "openai"
    config.ocr_base_url = ""
    config.ocr_api_key = enc
    config.ocr_model = OPENAI_OCR_MODEL
    config.save()
