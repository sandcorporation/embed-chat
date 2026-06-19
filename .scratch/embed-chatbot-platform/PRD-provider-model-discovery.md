# PRD: Provider 모델 조회 + 저장 시 연결 검증

Status: ready-for-agent

관련 ADR: [ADR-0012](../../docs/adr/0012-per-tenant-llm-embedding-providers.md) (per-Tenant Provider 확장)

## Problem Statement

Tenant가 어드민 설정에서 LLM·Embedding Provider의 모델을 정할 때, 지금은 `model_id`만 하드코딩 인기목록 드롭다운이고 `extraction_model`·`embed_model`은 **free-text 직접 입력**이다. 오타가 나거나 provider가 지원하지 않는 모델명을 넣어도 저장은 되고, 실제 챗·인제스션 시점에야 조용히 실패한다. 또 잘못된 api_key/base_url로 provider를 등록해도 저장되어, 역시 사용 시점에 깨진다. Tenant는 "내 provider가 실제로 제공하는 모델을 골라서 설정하고, 키가 틀리면 저장 자체가 막히길" 원한다.

## Solution

provider 설정 옆에 **"모델 불러오기" 버튼**을 두어, 백엔드가 그 provider의 모델 목록 API를 프록시 조회해 **드롭다운으로 채운다**(free-text는 폴백으로 공존). 그리고 provider를 저장할 때 **실제 기능 호출로 연결을 검증**해, 키/URL이 틀리면 **저장을 거부**(broken provider 등록 차단)한다. 프론트는 provider를 직접 못 부르므로(CORS + api_key 서버 암호화) 백엔드가 중계한다.

## User Stories

1. As a TenantAgent, I want to click "모델 불러오기" next to my LLM Provider, so that I see the models my provider actually offers instead of guessing names.
2. As a TenantAgent, I want the fetched LLM models to populate both the chat model and the extraction model dropdowns, so that I pick valid models for both from one fetch.
3. As a TenantAgent, I want a separate "모델 불러오기" for my Embedding Provider, so that the embedding model dropdown reflects that provider.
4. As a TenantAgent, I want to fetch models using the values currently in the form (even unsaved), so that I can verify a provider before saving it.
5. As a TenantAgent, I want a masked (unchanged) API key to still work for fetching, so that I don't have to re-enter my key just to list models.
6. As a TenantAgent, I want the full model list with no filtering, so that no valid model is hidden by a heuristic.
7. As a TenantAgent, I want free-text entry to remain available, so that I can still type a custom model name or proceed before fetching.
8. As a TenantAgent, I want my currently-saved model to always appear as an option, so that my configuration never silently disappears.
9. As a TenantAgent, I want a clear error when a fetch fails, so that I know the key/base_url is wrong.
10. As a TenantAgent, I want saving an invalid provider (bad key/url) to be rejected, so that I never persist a broken provider that fails later.
11. As a TenantAgent, I want provider validation to use the provider's real function (embedding call for Embedding, model list for LLM), so that a provider without a `/models` endpoint is not falsely blocked when its key is valid.
12. As a TenantAgent, I want validation to run only when provider fields changed, so that saving an unrelated setting (e.g., system prompt) does not re-call my provider every time.
13. As a TenantAgent, I want validation to check connectivity (reachable + key valid), not whether a specific model is in the list, so that a valid-but-unlisted model is not rejected.
14. As a TenantAgent using OpenAI/Custom (OpenAI-compatible), I want models listed from `/models`, so that the standard endpoint is used.
15. As a TenantAgent using Claude (Anthropic), I want models listed from the Anthropic models endpoint, so that the native provider is supported.
16. As a developer in dev, I want the platform-default embedding (ollama) listed from `/api/tags`, so that the dropdown works locally.
17. As a TenantAgent, I want the platform-default (OpenRouter) LLM models listed when platform defaults are enabled, so that the default option is also discoverable in dev.
18. As a TenantAgent, I want the fetch/validation to time out gracefully, so that a hanging provider does not freeze the admin.
19. As a developer, I want the provider-querying logic behind a small deep module, so that each provider type's normalization is tested in isolation.
20. As an operator, I want secrets never returned to the browser, so that the model-fetch endpoint only returns model ids, never the key.

## Implementation Decisions

### Modules

- **ProviderModels (backend, deep module)** — provider API를 호출해 정규화된 모델 id 목록을 돌려준다.
  - `list_provider_models(type, base_url, api_key) -> list[str]`: 타입별 분기 — OpenAI-호환(openai/custom/"" 플랫폼기본) `GET {base_url}/models` → `{data:[{id}]}`; Anthropic `GET /v1/models`(x-api-key + anthropic-version 헤더); ollama(플랫폼기본 임베딩) `GET {ollama}/api/tags` → `{models:[{name}]}`. 실패 시 `ProviderError`(사람이 읽을 메시지). httpx, 타임아웃.
  - `validate_provider(kind, type, base_url, api_key, model) -> None`: **기능 호출 검증**. kind=llm → `list_provider_models` 성공(연결+키). kind=embed → 1-텍스트 임베딩 호출 성공(provider의 실제 용도). 실패 시 `ProviderError`. 연결성만 검증(특정 model 상장 여부는 강제 안 함).
- **Provider 모델 엔드포인트 (backend)** — `POST /api/tenant/providers/models` `{kind, type, base_url, api_key, model}` → `{models:[id]}` 또는 4xx + 에러 메시지. tenant_agent_auth. **마스크 키(`********`)면 저장된 키 복호화 사용**(update_config 마스크 처리와 동일). 응답엔 모델 id만(키 미노출).
- **update_config 검증 (backend, 수정)** — LLM/Embedding provider 필드(type/base_url/key)가 **변경됐고 type이 non-empty**면 `validate_provider` 호출, 실패 시 PATCH **거부(4xx, 저장 안 됨)**. provider 미변경 시 검증 생략.
- **ConfigTab (frontend, 수정)** — LLM·Embedding 섹션에 "모델 불러오기" 버튼. 클릭 시 엔드포인트 호출(폼 현재 값) → 결과로 select 채움(LLM은 model_id+extraction_model 공유, Embedding은 embed_model). free-text 폴백 공존, 저장값 항상 옵션 유지. 조회/저장 실패 시 에러 노출.
- **api 파사드 + 생성 클라이언트** — 모델 조회 함수 추가, 백엔드 스키마 변경분 재생성(ADR-0014 파이프라인).

### 계약/결정

- 검증 = **연결성**(도달+키 유효), 특정 model_id 상장 강제 안 함.
- 검증 트리거 = provider 필드 변경 시에만.
- 키는 절대 브라우저로 안 감(엔드포인트는 모델 id만 반환).
- 필터링 없음(전체 목록).

## Testing Decisions

**좋은 테스트**: 외부 행위만. ProviderModels는 "openai 타입은 /models의 data[].id를 반환", "ollama 타입은 /api/tags의 models[].name을 반환", "실패하면 ProviderError" 같은 정규화·에러를 검증. provider HTTP는 **외부 경계이므로 결정적 Fake로 교체**(CLAUDE.md: 외부 API는 mock 대상). 엔드포인트는 마스크 키→저장 키, 모델 목록/4xx. update_config는 invalid provider면 저장 거부·valid면 저장·미변경이면 검증 생략.

- **ProviderModels (pytest, fake HTTP)**: 타입별 정규화, 실패 시 ProviderError, validate_provider(llm=list, embed=embed call).
- **엔드포인트 (pytest)**: 모델 목록 반환, 마스크 키→저장 키, 조회 실패 4xx, 키 미노출.
- **update_config (pytest)**: provider 변경+invalid → 거부, valid → 저장, provider 미변경 → 검증 생략(provider 미호출).
- **ConfigTab (vitest)**: "모델 불러오기"가 엔드포인트 호출 후 select를 채움; 저장 실패 시 에러 표시. 생성 모듈 mock.
- **Prior art**: 백엔드 provider 테스트(`test_provider.py`, `test_embedding_provider.py`)의 fake/monkeypatch 경계; 프론트는 `ConfigTab.test.tsx`의 생성 모듈 mock.

## Out of Scope

- 모델별 메타데이터(가격·컨텍스트 길이) 표시 — id만.
- 모델 목록 캐싱(온디맨드라 불필요).
- 휴리스틱 필터링(전체 표시로 결정).
- provider 검증을 위한 별도 "테스트 연결" 버튼 — 저장 시 검증으로 충분.

## Further Notes

- ADR-0012의 per-Tenant Provider를 확장한다. "provider 저장이 연결 검증으로 차단될 수 있다"는 행동 변화가 핵심.
- Anthropic은 임베딩 API가 없으므로 embed 검증은 항상 OpenAI-호환 `/embeddings` 호출.
- 플랫폼 기본(OpenRouter/ollama)은 PLATFORM_DEFAULT_PROVIDERS_ENABLED가 켜진 dev에서만 "기본" 옵션이 보이며, 그 목록도 조회 가능.
