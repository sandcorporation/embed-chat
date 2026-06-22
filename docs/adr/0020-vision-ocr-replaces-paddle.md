# ADR-0020: OCR을 per-Tenant Vision Provider로 (Paddle는 dev/test 격하)

## Status
Accepted

## Context
문서 인제스션의 OCR(이미지 + 스캔/깨진 PDF 폴백)이 자체호스팅 PaddleOCR(GPU 서비스)에 묶여 있었다.
prod에서 GPU 컨테이너를 추가로 떠야 하고(운영·VRAM 경합 — GPU 스택 flakiness를 반복적으로 겪음),
테넌트가 자기 LLM provider의 vision 능력을 OCR에 쓸 수 없었다. 한편 langchain `ChatOpenAI`/
`ChatAnthropic`는 이미지 content block을 지원해, 기존 per-Tenant provider 추상화(ADR-0012)로
vendor별 코드 없이 vision OCR이 가능하다.

## Decision
OCR을 단일 포트(`OCRBackend.transcribe`) 뒤로 숨기고, 엔진을 두 어댑터로 둔다:
- **VisionOCR** — per-Tenant **독립** OCR(Vision) Provider(LLM-shaped: openai/anthropic/custom).
  전사 전용 프롬프트 + temperature 0(ADR-0009 가드레일)로 환각을 통제. **prod 경로.**
- **PaddleOCR** — 기존 Paddle HTTP를 같은 포트로 래핑. **dev/test 폴백 전용.**

엔진 선택은 embedding_provider와 동일한 폴백: OCR Provider 설정됨 → Vision / dev·test 미설정 →
Paddle / prod 미설정 → 에러. prod compose에서 paddle-ocr 서비스를 제거하고, dev/test compose에만 유지한다.

## Considered Options
- **Paddle을 prod에도 유지**: 기각. GPU 운영 부담·경합이 이 전환의 핵심 동기. per-Tenant 품질 선택도 불가.
- **OCR을 LLM Provider(챗)에 종속(별도 필드 없음)**: 기각. 챗 provider가 text-only일 수 있어(Embedding을 분리한 이유와 동일) 깨진다. → 독립 OCR Provider 필드(ocr_*).
- **OCR을 extraction_model처럼 같은 provider+모델만 분리**: 기각. vendor 분리 요구(챗=Claude, OCR=Gemini)가 현실적이라 독립 provider로 둔다.
- **비-LLM 전용 OCR(Google Vision·Textract·Azure DI·Mistral OCR)**: 보류. API 형태가 chat과 달라 vendor별 어댑터 필요(YAGNI — 필요 시 후속, OCRBackend 포트로 확장).
- **Paddle도 prod에서 제거하고 dev/test도 vision Fake**: 기각. dev/test에서 결정적 로컬 OCR(실제 객체)로 통합 흐름을 검증하는 가치가 큼(CLAUDE.md mocking 원칙).

## Consequences
- prod에서 GPU OCR 서비스가 사라진다(운영·VRAM 이득). 대신 OCR 비용은 테넌트의 vision provider 호출로 발생 — (1) OCR은 이미지·스캔/깨진 PDF에만 발동, (2) 테넌트가 저렴한 vision 모델 선택 가능, (3) `OCR_MAX_PAGES` 상한으로 통제.
- prod 테넌트는 이미지·스캔 PDF를 올리려면 OCR Provider를 설정해야 한다(미설정 시 명확한 에러).
- vision은 비결정 외부 경계 → 테스트는 전용 `transcribe_image` Fake로 격리하고, Paddle 통합은 dev/test 실제 객체로 검증.
- ADR-0009의 "Text Unit은 LLM 생성물 불가" 규약은 유지(픽셀 OCR은 생성물 아님 — ADR-0009 Amendment 참조).
