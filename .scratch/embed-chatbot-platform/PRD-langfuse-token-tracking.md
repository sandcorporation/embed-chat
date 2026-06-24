# PRD — Langfuse 연동 + 테넌트별 토큰 사용량 추적

Status: ready-for-agent

## Problem Statement

플랫폼은 LLM·임베딩·OCR 호출을 하지만 **누가(어느 테넌트가) 토큰을 얼마나 쓰는지 가시성이 전혀
없다**. 테넌트는 자기 사용량을 확인할 방법이 없고, 오퍼레이터는 전체 테넌트의 소비를 모니터링하거나
"왜 이렇게 답했는지" LLM 호출을 디버깅할 도구가 없다.

## Solution

LLM 관찰 플랫폼 **Langfuse를 A1에 셀프호스트**해 모든 LLM 호출의 트레이스·토큰·비용을 기록하고
(오퍼레이터의 디버깅·관찰용), 동시에 **우리 DB에 테넌트별 토큰 사용량을 집계**해 인앱 화면에서
**테넌트는 자기 사용량을, 오퍼레이터는 전체 테넌트 사용량을** 본다. 캡처는 LLM 경계 한 곳(+임베딩
경계)에서 양쪽 sink에 동시 기록한다.

## User Stories

1. As a 테넌트, I want 내 챗봇이 이번 달 토큰을 얼마나 썼는지 보기, so that 비용 규모를 파악한다.
2. As a 테넌트, I want 사용량을 chat·문서추출·임베딩·OCR로 분해해서 보기, so that 어디서 토큰이 드는지 안다.
3. As a 테넌트, I want 일별/월별 사용 추이를 차트로 보기, so that 추세를 본다.
4. As a 테넌트, I want 내 데이터만 보이기(다른 테넌트 불가), so that 격리가 보장된다.
5. As an 오퍼레이터, I want 모든 테넌트의 토큰 사용량을 한눈에 비교하기, so that 헤비 유저·이상치를 안다.
6. As an 오퍼레이터, I want 특정 LLM 호출의 실제 프롬프트·RAG 근거·응답·토큰·지연을 추적하기, so that 답변 품질을 디버깅한다.
7. As an 오퍼레이터, I want 호출을 테넌트·call_type·model로 필터하기, so that 원인을 좁힌다.
8. As an 오퍼레이터, I want 본문 캡처를 끌 수 있기, so that 프라이버시 정책 변화에 대응한다.
9. As a developer, I want 호출부 시그니처 변경 없이 계측이 붙기, so that 회귀 위험이 적다.
10. As a developer, I want OpenAI 임베딩 토큰도 추적되기, so that 토큰 그림이 완전하다.
11. As an 운영자, I want Langfuse가 운영 DB와 분리되기, so that 분석 부하가 챗봇을 흔들지 않는다.
12. As a 테넌트, I want 사용량 화면이 외부 서비스 지연 없이 빠르기, so that 즉시 확인한다.

## Implementation Decisions

- **귀속 모델**: 토큰은 **테넌트별** 추적. 테넌트는 자기 것, 오퍼레이터는 전체. 목적은 **가시성**(과금/쿼터는 범위 밖 — 테넌트가 자기 provider에 직접 결제, ADR-0012).
- **이중 sink(캡처 1곳 → 2곳)**: ① **Langfuse** = 오퍼레이터 관찰·디버깅(트레이스·본문·비용). ② **우리 DB 롤업** = 인앱 사용량 뷰(빠르고 격리·가용성 확실).
- **계측 백본 — `UsageContext` ContextVar**: tenant_id·session_id·call_type을 담아 진입점에서 set(기존 `_current_chat_provider` 패턴 재사용 → **호출부 시그니처 변경 없음**). 진입점이 call_type을 정함 — chat 그래프=`chat`, 인제스션 추출=`extraction`, OCR=`ocr`. 임베딩 래퍼는 스스로 `embedding`으로 태깅.
- **LLM 경계(`apps/agent/llm.py`)**: langchain invoke/stream config에 **Langfuse CallbackHandler + metadata**(UsageContext) 부착(자동 트레이스). 응답의 `usage_metadata`(input/output/total)를 읽어 **우리 DB에 record**. chat·추출·OCR이 모두 이 경계를 지남.
- **임베딩 경계(`get_embeddings`, httpx)**: langchain 밖 + langchain callback이 임베딩 토큰을 안정적으로 안 흘리므로, **응답 `usage`를 직접 읽어** Langfuse SDK generation + 우리 DB에 record. usage를 안 주는 provider는 tiktoken 추정 또는 생략.
- **사용량 기록 deep module** `record_usage(tenant_id, call_type, model, input_tokens, output_tokens)`: `TokenUsage` 롤업에 **원자적 upsert 증분**(GraphStore의 ON CONFLICT 패턴).
- **스키마 — `TokenUsage`(Django 모델 + 마이그레이션)**: 키 `(tenant_id, call_type, model, date)`, 필드 `input_tokens·output_tokens·total_tokens·request_count`. 일 버킷이라 월/주/일 SUM 가능. 비용은 토큰만 저장하고 UI/Langfuse에서 환산(후속).
- **본문 캡처 + 킬스위치**: Langfuse에 프롬프트/응답 본문 캡처(오퍼레이터 디버깅). env `LANGFUSE_CAPTURE_CONTENT`(기본 on)로 끌 수 있음. **우리 DB 롤업엔 본문 0**(토큰만) → 테넌트 대면 화면에 본문 노출 불가.
- **Langfuse 배포 — A1 셀프호스트 v3, 전용 데이터스토어**: docker-compose.prod.oracle.yml에 langfuse-web·langfuse-worker + **전용** postgres·redis·clickhouse·minio(운영 pg/redis와 분리). 공식 멀티아치(arm64) 이미지라 빌드 불필요. 메모리 limit. Langfuse UI는 NPM 별도 호스트(예: langfuse.도메인)로 오퍼레이터에게만 노출.
- **API(ninja → orval 재생성)**: `GET /api/tenant/usage`(테넌트 인증, 자기 것), `GET /api/operator/usage`(오퍼레이터 인증, 전체 테넌트 group by). 기간·call_type 파라미터로 집계 반환.
- **인앱 UI(admin)**: 테넌트 `/tenant/usage` 탭(자기 사용량 — 기간 선택·call_type 분해·추이), 오퍼레이터 사용량 개요(테넌트별 비교·플랫폼 추이). **recharts** 차트.

## Testing Decisions

- 좋은 테스트는 외부 동작을 본다 — 기록된 집계·API 응답·격리·화면. Langfuse/LLM 같은 외부 경계는 결정적 Fake로 교체(우리 코드 동작 검증).
- 백엔드(Docker `scripts/test.sh`):
  - **`record_usage`**: 동일 키 두 번 → 증분 누적, 키별(tenant·call_type·model·date) 격리.
  - **계측**: fake LLM(이미 conftest에 있음)이 `usage_metadata`를 반환하게 해, chat/인제스션 1턴이 올바른 tenant·call_type으로 `TokenUsage`를 적재하는지. **Langfuse SDK는 외부 경계 → Fake/비활성**(테스트가 Langfuse를 치지 않음).
  - **임베딩**: usage 있는 응답 → `embedding` 기록, usage 없는 응답 → 추정/생략 경로.
  - **API**: 테넌트 엔드포인트는 자기 데이터만(다른 테넌트 0), 오퍼레이터는 전체. 기간·call_type 집계 합 정확.
- 프론트(Docker vitest): 사용량 탭이 집계 데이터로 차트/표를 렌더, 테넌트=자기 것. recharts는 jsdom 렌더 제한 시 데이터 전달 수준 검증.
- prior art: GraphStore upsert·savepoint 테스트, conftest fake LLM, ninja 엔드포인트 테스트, admin vitest.

## Out of Scope

- **과금·쿼터 강제** — 토큰 추적 위에 얹는 별도 기능.
- **정확한 비용 계산** — 토큰 우선. 비용은 Langfuse cost 또는 후속 단가표.
- **테넌트의 Langfuse 직접 접근** — Langfuse는 오퍼레이터 전용. 테넌트는 우리 인앱 뷰만.
- **임베딩을 langchain으로 이전** — httpx 유지 + 수동 usage 캡처(langchain callback이 임베딩 토큰을 안정적으로 안 줌).

## Further Notes

- chat·추출·OCR은 모두 langchain(`build_llm_client`) 경유라 CallbackHandler가 자동 포착. 임베딩만 httpx라 수동.
- Langfuse v3는 Clickhouse·MinIO가 필요해 무겁지만, A1 가용 메모리 ~16GB로 수용 가능(전용 스토어 분리).
- 관련: ADR-0012(per-Tenant Provider), 계측은 `apps/agent/llm.py`·`apps/agent/providers.py`(ContextVar)·`apps/rag/ingesters.py`(임베딩) 경계.
