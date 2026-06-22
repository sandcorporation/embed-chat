# PRD — Vision OCR (Paddle를 per-Tenant Vision Provider로 대체)

Status: ready-for-agent

## Problem Statement

문서 인제스션의 OCR(이미지 + 스캔/깨진 PDF 폴백)이 자체호스팅 **Paddle**(GPU 서비스)에 묶여 있다.
prod에서 GPU 서비스를 한 개 더 떠야 하고(운영·비용·VRAM 경합 부담 — 그동안 GPU 스택 flakiness를
반복적으로 겪음), 테넌트가 자기 LLM provider의 vision 능력을 쓰지 못한다. OCR 엔진이 전역 단일이라
테넌트별 품질·언어 특성을 고를 수 없다.

## Solution

OCR을 **per-Tenant Vision Provider**(테넌트가 고른 vision 모델)로 수행한다. OCR을 단일 포트
(`OCRBackend.transcribe(image_bytes, mime) -> str`) 뒤로 숨기고, 두 어댑터를 둔다:
- **VisionOCR** — 테넌트의 독립 OCR provider(LLM-shaped: openai/anthropic/custom/플랫폼기본)로
  이미지를 vision 모델에 보내 텍스트를 **그대로 전사**한다. **prod 경로.**
- **PaddleOCR** — 기존 Paddle HTTP 호출을 같은 포트로 감싼다. **dev/test 폴백 전용**(GPU를 prod에서
  제거하되, 결정적 로컬 OCR로 통합 테스트를 실제 객체로 돌리기 위해 dev/test에만 유지 — CLAUDE.md).

엔진 선택은 embedding provider와 동일한 폴백: 테넌트가 OCR provider를 설정하면 VisionOCR, 미설정 시
dev/test는 Paddle, prod는 "OCR Provider 미설정" 에러.

## User Stories

1. As a tenant agent, I want to configure an independent OCR(Vision) Provider (type·base_url·model·key), so that 문서 OCR을 내 vision 모델로 수행한다.
2. As a tenant agent, I want OCR Provider를 챗·임베딩과 별개로 고르기, so that 챗은 Claude, OCR은 Gemini처럼 vendor를 분리할 수 있다.
3. As a tenant agent, I want OCR Provider 저장 전에 연결이 검증되기, so that 잘못된 키/주소를 바로 안다.
4. As a tenant agent, I want OCR Provider의 모델 목록을 조회, so that vision 가능한 모델 id를 골라 넣는다.
5. As a tenant agent, I want 이미지(PNG·JPEG·WEBP) 업로드 시 vision OCR로 텍스트가 추출되기, so that 이미지 자료가 지식그래프에 들어간다.
6. As a tenant agent, I want 스캔/깨진 PDF가 vision OCR 폴백으로 복구되기, so that 텍스트 레이어가 없는 PDF도 사용 가능하다(ADR-0009 복구 능력 보존).
7. As a tenant agent, I want 멀쩡한 텍스트 PDF는 OCR 없이 PyMuPDF로 처리되기, so that 불필요한 vision 비용이 들지 않는다.
8. As a tenant agent, I want vision OCR이 보이는 텍스트만 그대로 전사(추론·번역·요약 금지)하기, so that Local Search citation의 원문성이 유지된다(ADR-0009).
9. As a tenant agent, I want vision OCR 후에도 깨진 청크는 저장 안 되기, so that 깨진 근거가 노출되지 않는다(is_garbled 드롭 유지).
10. As a platform operator, I want prod 배포에서 Paddle GPU 컨테이너가 제거되기, so that 운영·VRAM 부담이 준다.
11. As a developer, I want dev/test에서 Paddle 실제 객체로 OCR 통합 흐름을 검증하기, so that 비결정 vision을 Fake로 둘 때 결정적 회귀를 잃지 않는다.
12. As a developer, I want vision OCR 경계를 전용 함수로 Fake하기, so that 메모리 추출용 complete_text Fake와 섞이지 않는다.
13. As a tenant agent (prod, OCR 미설정), I want 이미지/스캔PDF 업로드가 명확한 에러로 실패하기, so that 무엇을 설정해야 하는지 안다.
14. As a platform operator, I want 거대한 스캔 PDF의 vision OCR이 페이지 상한으로 통제되기, so that 한 문서가 과도한 비용을 내지 않는다.
15. As a tenant agent, I want 기존에 Paddle로 인제스션된 문서가 그대로 유지되기, so that 마이그레이션이 재처리를 요구하지 않는다.
16. As a tenant agent, I want OCR Provider api_key가 암호화 저장·마스킹되기, so that 키가 브라우저로 새지 않는다(다른 provider와 동일).
17. As a developer, I want 백엔드 OpenAPI 변경이 orval로 admin 클라이언트에 재생성되기, so that admin 호출이 드리프트 없이 유지된다(ADR-0014).

## Implementation Decisions

- **OCR 포트(deep module)**: `OCRBackend.transcribe(image_bytes, mime_type) -> str`. 어댑터 `PaddleOCR`(기존 Paddle HTTP 래핑), `VisionOCR`(LLMProvider 보유). 팩토리 `get_ocr_backend(config)`가 엔진을 고른다 — 테넌트 OCR provider 설정됨→VisionOCR / dev·test 미설정→PaddleOCR / prod 미설정→`ValueError`. (embedding_provider 폴백 패턴과 동일.)
- **OCR Provider = 독립 설정 + LLM-shaped**: TenantConfig에 `ocr_provider_type`·`ocr_base_url`·`ocr_api_key`(암호화)·`ocr_model` 추가(dim 없음). 리졸버 `ocr_provider(config) -> LLMProvider`는 `LLMProvider` dataclass·`build_llm_client`를 재사용하고 **anthropic 포함** 모든 타입 지원(embedding과 달리). 모델 목록·검증은 `kind="ocr"`로 LLM-style(`/models`) 경유 — type=""은 OpenRouter(embed만 ollama 특례).
- **Vision 경계(전용 함수)**: `apps/agent/llm.py`에 `transcribe_image(provider, image_bytes, mime_type) -> str`. 전사 전용 시스템/유저 프롬프트(플랫폼 상수, 테넌트 설정 아님) + provider-agnostic 이미지 content block + **temperature 0**. `complete_text` 재사용하지 않음(테스트 Fake 격리).
- **전사 가드레일(ADR-0009 준수)**: 프롬프트는 "이미지에 보이는 텍스트만 그대로 전사, 추론·번역·요약·교정 금지, 판독 불가 시 빈 출력". OCR 결과도 기존 `is_garbled` 사후 드롭 유지.
- **ingester 주입**: `DocumentIngester.extract_text(file_bytes, ocr)` 시그니처로 OCR 백엔드 주입(비-OCR ingester는 무시). `ImageIngester`·`_ocr_pdf`가 `ocr.transcribe`를 호출. 기존 모듈전역 `_call_ocr`는 `PaddleOCR`로 이동. `ingest_document` 태스크가 tenant config로 백엔드를 만들어 주입.
- **PDF 폴백 페이지 상한**: `OCR_MAX_PAGES`(기본 30) 설정으로 거대한 스캔 PDF의 vision 호출 수를 통제. 초과 페이지는 OCR 생략(경고 로그).
- **인프라**: prod compose에서 `paddle-ocr` 서비스 제거. dev·test compose는 유지(`PADDLE_OCR_URL`/`PADDLE_OCR_TIMEOUT` 설정 dev/test 전용). prod 기본 OCR 엔진=vision.
- **admin API**: `TenantConfigOut`/`TenantConfigIn`에 ocr_* 추가(out은 키 마스킹), `_validate_changed_provider`에 `kind="ocr"` 분기, `update_config` 필드 목록 + `ocr_api_key` 암호화, `ProviderModelsIn.kind`에 "ocr" 허용. OpenAPI 변경 → `bash scripts/gen-admin-api.sh`로 orval 재생성(openapi.json·generated 함께 커밋).
- **admin UI**: 'AI 모델' 설정에 'OCR(Vision) Provider' 섹션(type·base_url·model·key + 모델목록·검증) — Embedding Provider 섹션 미러링.
- **ADR**: ADR-0009를 개정(보충)해 금지 범위를 "*깨진 텍스트의 LLM 정제*"로 한정하고 "*픽셀로부터의 vision OCR(전사 가드레일 하)*"을 허용으로 명시. vision OCR 채택 자체는 새 ADR(되돌리기 어렵고 trade-off가 있는 결정)로 기록.

## Testing Decisions

- 좋은 테스트는 **외부 행동**만 본다(구현 세부 아님). LLM/vision은 비결정 외부 경계 → 결정적 Fake. Paddle·DB·Neo4j·HTTP 수신부 등 결정 가능 인프라는 실제 객체(CLAUDE.md).
- **OCR 포트/팩토리**: `get_ocr_backend`가 설정/환경에 따라 Paddle vs Vision을 고르고, prod 미설정 시 에러를 내는지(실 config + settings 토글).
- **VisionOCR 어댑터**: 전용 `transcribe_image` 경계를 Fake로 두고, 이미지/마임을 받아 provider+vision 모델로 올바른 메시지를 만들어 호출하고 전사 텍스트를 반환하는지. 가드레일 프롬프트가 실린지.
- **ingester 통합(dev/test=Paddle 실제 객체)**: 이미지 업로드 → Paddle OCR → 그래프 인제스션, 스캔/깨진 PDF → 페이지 OCR 폴백 → is_garbled 드롭. 기존 `test_rag.py` OCR 테스트를 새 포트 주입에 맞게 갱신(prior art).
- **ocr_provider 리졸버**: 설정/플랫폼기본/미설정(prod) 분기 — `embedding_provider` 테스트가 prior art.
- **admin config**: ocr_* 라운드트립(키 마스킹/암호화), `kind="ocr"` 모델목록/검증 — embed provider 테스트가 prior art.
- **페이지 상한**: `OCR_MAX_PAGES` 초과 시 호출 수 제한(주입한 Fake 백엔드 호출 카운트로 검증).

## Out of Scope

- 비-LLM 전용 OCR 서비스(Google Vision·AWS Textract·Azure Document Intelligence·Mistral OCR API) 어댑터 — API 형태가 chat과 달라 별도 작업(필요 시 후속).
- 기존에 Paddle로 인제스션된 문서의 재처리(운영 수동 재업로드 — ADR-0009와 동일).
- vision 모델의 vision-가능 여부 자동 검증(연결성만 검증; 테넌트가 vision 모델을 고를 책임).
- per-페이지 정밀 폴백·표/레이아웃 구조화 추출(YAGNI — 문서 단위 전사).

## Further Notes

- OpenRouter(플랫폼 기본) 한 키로 GPT-4o·Claude·Gemini·Qwen-VL 등 대부분 vision 모델을 OCR로 쓸 수 있어, 테넌트가 별도 vendor 키 없이도 vision OCR 가능(dev에서도 opt-in 가능, 단 기본 폴백은 Paddle).
- 비용은 (1) OCR이 스캔/깨진 PDF·이미지에만 발동, (2) 테넌트가 자기 키로 저렴한 vision 모델(4o-mini·gemini-flash·qwen-vl) 선택 가능, (3) `OCR_MAX_PAGES`로 상한 — 세 겹으로 통제.
