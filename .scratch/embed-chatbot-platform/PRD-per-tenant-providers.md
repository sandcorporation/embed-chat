Status: ready-for-agent

# PRD: Tenant 부담 멀티 Provider (LLM · Embedding) (C)

ADR: `docs/adr/0012-per-tenant-llm-embedding-providers.md`

## Problem Statement

현재 모든 LLM 호출은 플랫폼 단일 키로 과금되고 Tenant는 모델 문자열만 고른다. 임베딩은 플랫폼 로컬 ollama bge-m3(GPU)로 처리된다. 그러나 프로덕션 타깃 Oracle A1(Ampere ARM)에는 **GPU가 없어** 로컬 임베딩이 불가능하고, LLM·임베딩 비용을 플랫폼이 떠안기도 부담스럽다. Tenant가 자기 비용을 부담하며 자기 provider를 쓰게 해야 한다.

## Solution

per-Tenant **LLM Provider**(챗+추출)와 **Embedding Provider**를 독립 설정으로 도입한다. Tenant가 자기 키를 넣으면 provider가 Tenant에게 직접 과금한다. 타입은 OpenAI·Claude·Custom(임베딩은 OpenAI·Custom). 임베딩 모델이 벡터 공간을 정의하므로 **Embedding Provider 변경 시에만** 재임베딩(무중단 swap)이 발생하고, LLM Provider 변경은 재구축이 없다. 벡터 인덱스는 가변 차원 때문에 per-Tenant로 격리한다. 로컬 dev는 provider를 로컬 docker(fake-llm + ollama)로 향하게 한다.

## User Stories

1. Tenant로서, 내 OpenAI 키를 넣어 챗·추출·임베딩 비용을 내 계정으로 부담하고 싶다.
2. Tenant로서, 챗에 Claude(Anthropic)를 쓰고 싶다.
3. Tenant로서, OpenRouter·Deepinfra 같은 임의 OpenAI-호환 엔드포인트를 Custom으로 지정하고 싶다.
4. Tenant로서, Claude로 챗을 쓰면서 임베딩은 OpenAI/Custom으로 따로 설정하고 싶다(Anthropic 임베딩 부재).
5. Tenant로서, LLM Provider와 Embedding Provider를 독립적으로 고르고 싶다.
6. Tenant로서, 챗 LLM provider를 바꿔도 기존 그래프·검색이 그대로 동작하길 바란다(재구축 없음).
7. Tenant로서, Embedding Provider를 바꾸면 기존 임베딩이 새 모델로 재계산되길(재임베딩) 바란다.
8. Tenant로서, 재임베딩 중에도 기존 임베딩으로 Local Search가 계속 동작하길 바란다(무중단).
9. Tenant로서, 재임베딩이 끝나면 새 인덱스로 원자적 전환되길 바란다.
10. Tenant로서, 재구축 진행 상태(Graph Freshness=rebuilding)를 알 수 있길 바란다.
11. Tenant로서, 추출 LLM을 바꾸면 신규 문서부터 적용되고 기존 그래프는 유지되길 바란다.
12. Tenant로서, 내 API 키가 암호화되어 저장되고 화면에 다시 노출되지 않길 바란다.
13. Tenant로서, 저장된 키는 마스킹되어 보이고 교체만 가능하길 바란다.
14. Operator로서, Tenant 키가 평문으로 로그·응답에 새지 않길 바란다.
15. Tenant로서, 프로덕션에서 Embedding Provider를 설정해야 인제스션·검색이 가능함을 온보딩에서 안내받고 싶다.
16. 개발자로서, 로컬 dev에서 실 키 없이 fake-llm + ollama로 전체 흐름을 돌리고 싶다.
17. 개발자로서, dev 기본 provider가 로컬 docker를 가리켜 자동 동작하길 바란다.
18. Tenant로서, 서로 다른 임베딩 차원(OpenAI 1536, bge 1024 등)을 써도 내 그래프가 격리된 인덱스에서 정확히 검색되길 바란다.
19. Operator로서, 한 Tenant의 임베딩 차원 변경이 다른 Tenant 인덱스에 영향을 주지 않길 바란다.
20. Tenant로서, Custom provider에 base_url과 크레덴셜을 직접 입력하고 싶다.
21. Operator로서, 챗·추출·메모리 추출 등 모든 LLM 호출이 해당 Tenant provider로 라우팅되길 바란다.

## Implementation Decisions

- **ProviderResolver deep module**: Tenant provider 설정(type·base_url·key·model) → LLM/임베딩 클라이언트. 타입 분기: OpenAI/Custom → OpenAI-호환 클라이언트, Claude → Anthropic 네이티브 클라이언트. LLM 경계가 전역 settings 대신 이 리졸버를 통해 per-Tenant 클라이언트를 얻는다(챗·추출·메모리 호출 전부).
- **Provider 설정 모델**: LLM Provider `{type: openai|anthropic|custom, base_url, api_key(암호화), chat_model, extraction_model}` + Embedding Provider `{type: openai|custom, base_url, api_key(암호화), embed_model, embed_dim}`. 독립. `TenantConfig.model_id` → LLM Provider `chat_model`로 흡수(migration).
- **임베딩 클라이언트**: OpenAI-호환 `/v1/embeddings`로 통일(현재 ollama 네이티브 `/api/embed` 대체). base_url·key·model provider-설정 가능.
- **키 암호화 deep module**: Fernet류 대칭 암호화(플랫폼 시크릿). 저장 시 암호화, API write-only, 조회 시 마스킹.
- **per-Tenant 벡터 인덱스**: Neo4j 벡터 인덱스가 (label, property)당 고정 차원이므로, 단일 전역 인덱스 → per-Tenant 격리(구현은 per-Tenant 라벨/프로퍼티). search/ingest가 Tenant 인덱스를 타깃.
- **재임베딩 재구축 플로우(Celery)**: Embedding Provider 변경 트리거. `Graph Freshness=rebuilding` → 옛 인덱스/벡터 서빙 유지하며 새 인덱스에 새 차원으로 재임베딩(Text Unit·Mention) → 원자적 swap → 옛것 폐기. 그래프 구조(Entity·관계·Community)는 보존. dual-write 전환 패턴.
- **트리거 분리**: Embedding Provider 변경 → 재임베딩. LLM Provider(챗/추출) 변경 → 재구축 없음. 추출 LLM 변경은 신규 문서에만(원하면 수동 전체 재인제스션).
- **dev proxy**: dev/test 기본 provider를 Custom 타입으로 로컬 docker(fake-llm `/v1`, ollama `/v1/embeddings`)에 향하게. env 기반 플랫폼 기본 폴백 — dev는 채우고 prod는 비움(prod는 Tenant 설정 필수).
- **provider CRUD API**: 어드민에서 LLM/Embedding provider 조회(마스킹)·설정·교체.

## Testing Decisions

좋은 테스트는 외부 행위만 검증한다. 실제 객체(Neo4j·Redis·DB·ollama 임베딩 실물), LLM 챗 경계만 Fake. 최대 커버리지 — deep module + 인덱스 격리·재임베딩·provider CRUD 통합.

- **ProviderResolver** [결정적 단위]: openai/custom 설정 → OpenAI-호환 클라이언트(base_url·key 반영), anthropic 설정 → Anthropic 클라이언트. embedding 설정에 anthropic 타입 거부.
- **키 암호화** [순수·결정적 단위]: 암호화→복호화 왕복, 저장값이 평문 아님, API 응답이 마스킹.
- **임베딩 클라이언트** [ollama 실물 결정적]: OpenAI-호환 `/v1/embeddings`로 임베딩 획득, 차원 일치.
- **per-Tenant 인덱스 격리 통합**: 서로 다른 차원의 두 Tenant가 각자 인덱스에서 정확히 검색되고, 교차 오염 없음.
- **재임베딩 재구축 통합**: Embedding Provider 변경 → 재임베딩 중 옛 임베딩으로 Local Search 동작 → 완료 후 새 인덱스로 검색. 그래프 구조(Entity·관계) 보존 확인. LLM Provider 변경 → 재구축 미발생 확인.
- **provider 라우팅 통합**: Tenant provider 설정에 따라 챗 호출이 해당 클라이언트로 감(Fake로 호출 인자 검증).
- **provider CRUD 통합**: 키 설정→마스킹 조회, 교체, 미설정 prod에서 인제스션 거부/안내.
- Prior art: `tests/test_rag.py`(임베딩·Neo4j 실물), `tests/test_graph_search.py`(벡터 검색), `tests/conftest.py`(fake_chat_llm 경계).

## Out of Scope

- 플랫폼 차원의 LLM 비용 미터링·청구(provider가 Tenant에 직접 과금).
- 임베딩 모델 자동 추천·벤치마킹.
- provider별 모델 카탈로그 동기화 UI(자유 입력).
- 추출 LLM 변경 시 자동 전체 재인제스션(수동만).
- 멀티 키 로테이션·사용량 대시보드.

## Further Notes

- 트리거 분리가 핵심: 비용 절감용 흔한 LLM provider 교체는 재구축 0, 임베딩 모델 변경만 재임베딩.
- 벡터 공간 호환은 차원이 아니라 모델 정체성으로 판단한다(같은 1024라도 다른 모델이면 재임베딩).
- A1 레이트리밋이 Tenant 키를 공개 URL 남용으로부터 보호하는 역할을 겸한다.
- 프로덕션 무 GPU(Oracle A1) 제약이 임베딩의 Tenant-사이드 이동을 강제한다.
