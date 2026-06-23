# PRD — OpenAI 키 한방(one-shot) Provider 설정

Status: ready-for-agent

## Problem Statement

Operator가 테넌트에게 계정을 발급하면, 테넌트는 로그인 직후 **Provider가 비어 있는** 상태다(ADR-0012:
prod는 플랫폼 기본 폴백 없음). 지금은 설정 탭에서 **LLM·Embedding·OCR 3종**을 각각 type·키·모델·차원을
손으로 채워야 동작한다 — 비개발자 테넌트에겐 진입장벽이 높고, Embedding 차원(1536)을 틀리거나 OCR을
빼먹으면 RAG 검색·이미지 업로드가 prod에서 `ValueError`로 조용히 실패한다.

## Solution

설정 탭에 처음 들어온(Provider 미설정) 테넌트에게 **OpenAI API 키 한 칸만 받아 3종을 한 번에 설정**하는
화면을 보여준다. 키 하나로 챗·RAG검색·이미지OCR이 모두 같은 OpenAI 키·올바른 기본 모델/차원으로 켜진다.
기존의 vendor별 상세 설정은 "고급 설정"으로 접어, 비개발자는 한방으로 끝내고 파워유저는 고급에서 섞는다.

## User Stories

1. As an operator, I want 테넌트에게 계정만 주면 되기, so that 내가 대신 Provider를 설정할 필요가 없다.
2. As a 신규 테넌트, I want 로그인 후 설정 탭에서 OpenAI API 키 한 칸만 입력하면 끝나기, so that 개발 지식 없이 바로 챗봇을 켤 수 있다.
3. As a 신규 테넌트, I want 키 하나로 LLM·Embedding·OCR이 모두 설정되기, so that 챗·자료검색·이미지OCR이 한꺼번에 동작한다.
4. As a 신규 테넌트, I want 임베딩 차원이 자동으로 올바르게(1536) 잡히기, so that 차원 불일치로 RAG가 깨지지 않는다.
5. As a 신규 테넌트, I want 한방 설정 전에 키가 유효한지 즉시 검증되기, so that 잘못된 키를 바로 알 수 있다.
6. As a 신규 테넌트, I want 잘못된 키면 아무것도 저장되지 않기, so that 깨진 부분 설정 상태가 남지 않는다.
7. As a 테넌트, I want 설정이 끝나면 무엇이 켜졌는지 한 줄 요약을 보기, so that 안심하고 다음 단계로 간다.
8. As a 파워유저 테넌트, I want 기존 vendor별 상세 설정을 "고급 설정"에서 그대로 쓰기, so that Claude·Gemini·custom·기본(OpenRouter)을 섞을 수 있다.
9. As a 파워유저 테넌트, I want 한방으로 깐 기본 모델을 고급에서 `gpt-4o` 등으로 올리기, so that 품질을 높일 수 있다.
10. As a 테넌트, I want 3종 provider가 같으면 컴팩트 요약, 섞였으면 고급만 보기, so that 화면이 내 상태에 맞게 깔끔하다.
11. As a dev 테넌트, I want 미설정이어도 막히지 않고 고급에서 `기본(OpenRouter)`을 고를 수 있기, so that dev에선 OpenAI 키 없이도 작업한다.
12. As a 테넌트, I want 입력한 OpenAI 키가 암호화 저장·마스킹되기, so that 키가 브라우저로 새지 않는다.
13. As a 운영자, I want 기본 모델·차원이 서버 한 곳에 있기, so that 모델 갱신 시 한 곳만 고친다.
14. As a 테넌트, I want 한방 설정 직후 화면이 요약으로 자동 전환되기, so that 다시 새로고침하지 않아도 된다.
15. As a developer, I want OpenAPI 변경이 orval로 admin 클라이언트에 재생성되기, so that admin 호출이 드리프트 없이 유지된다(ADR-0014).

## Implementation Decisions

- **범위**: OpenAI 키 1개로 **3종 모두** 설정 — LLM(챗+추출)·Embedding·OCR(Vision)을 `type=openai` + 같은 키로.
- **기본 모델(서버 상수, 단일 출처)**: 챗(`model_id`)=`gpt-4o-mini`, 추출(`extraction_model`)=빈값(챗과 동일 폴백), 임베딩=`text-embedding-3-small` + `embed_dim=1536`, OCR=`gpt-4o-mini`. base_url은 전부 빈값(openai는 표준 주소로 자동 보정). 고급에서 `gpt-4o` 등으로 변경 가능.
- **백엔드 deep module + 전용 엔드포인트**: `POST /api/tenant/providers/quick-setup` `{api_key}`. 핵심 로직은 테스트 가능한 deep module(예: OpenAI 기본값 적용 + **키 1회 검증**(`list_provider_models`로 models 조회 — OpenAI 키는 chat/embed/vision 공통) + 3종을 원자적으로 저장). 검증 실패 시 400 + 미저장. 키는 암호화 저장.
- **재임베딩**: 임베딩 provider 변경이라 기존 `update_config`처럼 reembed 트리거 — 단 신규(임베딩 없는) 테넌트엔 no-op.
- **상태 판별(프론트, `_config_out` 필드 사용)**:
  - **미설정** = `llm_provider_type === ''` → OpenAI 한방 카드(키 입력).
  - **3종 동일 타입**(`llm===embed===ocr` 비빈값, 모델은 달라도 됨) → 컴팩트 요약 카드(*"AI 제공자: OpenAI · 챗 X · 임베딩 Y · OCR Z"* + [고급에서 변경]).
  - **섞임**(타입 불일치) → 요약 없음, 고급 설정 기본 펼침.
- **non-blocking + collapse**: 'AI 모델' 탭 = `[상단: 한방 카드 / 요약 / 없음]` + `▸ 고급 설정`(접힘) → 기존 LLM·Embedding·OCR 3종 상세 그대로. dev는 고급의 `기본(OpenRouter)` 옵션 유지. 카드 문구만 env로(prod="필수", dev="키로 바로 설정 또는 고급에서 기본").
- **admin 클라이언트**: 새 엔드포인트 → `bash scripts/gen-admin-api.sh`로 orval 재생성(openapi.json·generated 함께 커밋).

## Testing Decisions

- 좋은 테스트는 외부 행동만 검증(구현 세부 아님). provider HTTP(OpenAI)는 외부 경계 → 결정적 Fake(현 `test_provider_models`가 prior art: `httpx.get/post`를 Fake).
- **백엔드 quick-setup(deep module/엔드포인트)**: ① 유효 키 → 3종이 openai로 저장되고 모델·dim(1536)이 기본값으로 채워짐, ② 키 검증 실패 → 400 + **아무것도 저장 안 됨**(원자성), ③ 키 1회만 검증(중복 호출 없음), ④ 저장 키는 암호화·GET 마스킹. prior art: `test_provider_models`의 update_config 검증 테스트.
- **admin UI(ConfigTab)**: ① `llm_provider_type=''` → 한방 카드 표시 + 키 입력→quick-setup 호출, ② 3종 동일 → 요약 카드, ③ 섞임 → 요약 없음·고급 펼침, ④ 기존 3종 상세가 고급에 그대로(회귀). prior art: 기존 `ConfigTab.test.tsx`.

## Out of Scope

- OpenAI 외 vendor의 한방(예: Claude 키 한방) — 후속(고급에서 수동 설정은 가능).
- 한방 화면에서 모델 선택 UI — 키만 받고 기본값 적용(변경은 고급).
- 기존 `update_config`/provider 상세 로직 변경 — 그대로 두고 한방은 별도 경로.
- per-Tenant 기본 모델 커스터마이즈(테넌트별 다른 기본값) — 플랫폼 공통 기본값.

## Further Notes

- OpenAI 키 1개가 chat·embedding·vision 전 엔드포인트 공통이라 검증·설정이 진짜 "한방"이 된다.
- 임베딩 차원 1536은 어느 모델 선택이든 `text-embedding-3-small`에 고정(틀리면 RAG 깨짐 — 자동화의 핵심 이유).
- 관련: ADR-0012(per-Tenant providers), 0014(orval), 0020(Vision OCR), 0021(pgvector GraphStore).
