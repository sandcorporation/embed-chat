# PRD: GraphRAG Local Search — 미스 기반 원문(TextUnit) 폴백

Status: ready-for-agent

관련 ADR: [ADR-0007](../../docs/adr/0007-graphrag-neo4j-replaces-2step-vector-rag.md) (GraphRAG Neo4j) · [ADR-0010](../../docs/adr/0010-entity-resolution-mention-entity-context-equivalence.md) (구조화 근거 — local에서 TextUnit 제외 결정을 본 PRD가 보강)

## Problem Statement

Local Search는 Knowledge Graph 투영(Entity + Relation)만 근거로 쓴다(ADR-0010: *"거대한 Text Unit chunk 대신 구조화된 Entity·Relation"*). 그런데 스펙·수치·표 형태의 사실(예: `해상도 1920×1080`, 사전설정 해상도 표, 전원/단자 사양)은 엔티티-관계 추출이 **속성-값/표로 흘려버려 그래프에 남지 않는다.** 그 결과 원문 문서엔 답이 멀쩡히 있어도 Local Search가 못 찾고, AI가 "제공된 데이터에 정보가 없다"며 **불필요하게 HITL로 에스컬레이션하거나 "모른다"고 답한다.**

실증(HP모니터.pdf): 텍스트 레이어가 깨끗(44p, 8066단어, garbled=False)하고 *"1920 × 1080 해상도의 FHD"* + *표 A-4 사전 설정 디스플레이 해상도*가 명확히 들어 있는데, 그 테넌트의 체크포인트 그래프엔 토픽 엔티티(Display Center·블루라이트·앞면 구성·자가진단·스탠드…)만 남아 "지원하는 모니터의 해상도" 질의가 HITL로 빠졌다. 원문 `TextUnit`은 임베딩까지 저장돼 있으나 **챗 경로가 호출하지 않는다.**

## Solution

질의가 "스펙형이냐"를 **미리 분류하지 않는다**(분류는 다국어·패러프레이즈에 불안정). 대신 **증거 기반 폴백**으로 푼다(Self-RAG의 ISSUP/CRAG 계열의 경량 변형 — 아래 Further Notes):

1. Local Search(그래프-only)로 먼저 답을 시도한다.
2. LLM이 "제공된 근거만으로는 답할 수 없다"(`context_sufficient=False`)고 표시하면, **원문 `TextUnit`을 `vector_search`로 끌어와 근거에 보강한 뒤 한 번 더 호출**한다.
3. 보강 후에도 답이 없으면 기존 경로(HITL 또는 HITL-OFF의 "모른다")로 간다.

원문은 **그래프가 실패한 질의에만, 2패스에서만** 들어가므로 평상시 토큰 이점(구조화 근거)을 유지하면서 스펙형 질의의 정확도를 회복한다. 원문 TextUnit은 이미 임베딩 저장돼 있어 **재인제스션이 필요 없다 — 검색 배선만 추가**한다.

## User Stories

1. As a Visitor, I want the bot to answer a spec question (e.g., supported resolution) that is stated in the source manual, so that I get the fact instead of being told it isn't available.
2. As a Visitor, I want numeric/table facts (resolution, refresh rate, ports, power) answered from the document, so that I don't have to dig through a PDF myself.
3. As a Visitor, I want the bot to fall back to the original text only when the structured answer fails, so that normal answers stay fast.
4. As a Visitor asking something genuinely absent from all sources, I want a clear "정보 없음"/handoff, so that I'm not given a hallucinated spec.
5. As a TenantAgent, I want spec questions to stop unnecessarily escalating to me, so that HITL volume reflects real gaps, not extraction blind spots.
6. As a TenantAgent, I want the fallback to use my documents' original text units, so that the answer is grounded in my uploaded source, not invented.
7. As a TenantAgent, I want the token cost of the original-text fallback paid only on a miss, so that my per-message cost doesn't balloon on every query.
8. As a TenantAgent on a HITL-OFF bot, I want the same original-text fallback before the bot says "모른다", so that AI-only mode also answers spec questions.
9. As a TenantAgent, I want the original text fed as untrusted data (delimited), so that the existing prompt-injection isolation still holds for web-ingested content.
10. As a TenantAgent, I want a bounded number of original-text chunks pulled on fallback, so that one query can't stuff the whole document into context.
11. As a TenantAgent inspecting the Checkpoint, I want to see whether the answer came from the structured graph or from the original-text fallback, so that I can debug retrieval quality.
12. As a developer, I want the fallback to reuse the existing `vector_search` (TextUnit embeddings already stored), so that no re-ingestion or new index is needed.
13. As a developer, I want a single `context_sufficient` signal on the structured output to drive the fallback, so that I don't need a separate query classifier.
14. As a developer, I want the fallback to retry at most once (one source-augment pass), so that a single message can't loop the LLM indefinitely.
15. As a developer, I want the happy path (graph answered) to never call `vector_search`, so that the token guard is structural, not best-effort.
16. As a developer, I want the behavior verified end-to-end through `run_chat_agent`, so that the test survives internal refactors of the graph topology.

## Implementation Decisions

- **`context_sufficient: bool` 신호**: 챗 구조화 출력 스키마(HITL 경로의 `HITLResponse`와 HITL-OFF 경로의 `PlainResponse`) 둘 다에 추가한다. LLM이 *제공된 근거만으로 사용자 질문에 답할 수 있었는가*를 표시한다. 이것이 "miss" 감지기다(별도 질의 분류기 불필요).
- **상태 채널**: `ChatState`에 `source_text_tried: bool`(폴백 1회 보장 가드) 추가, `context_sufficient`는 노드 출력으로 흐른다.
- **원문 보강 노드(source_search)**: `GraphStore.vector_search(user_message, top_k)`로 최근접 `TextUnit.content`를 가져와 `rag_chunks`에 append한다(이미 있는 청크와 중복 회피). `top_k`는 작게 캡(예: 3~5).
- **토폴로지(프로토타입 수준 결정)**:
  ```
  call_llm → _route_after_llm:
      context_sufficient == False  AND  source_text_tried == False  → source_search → call_llm(재호출, source_text_tried=True)
      그 외 → 기존 라우팅 (HITL 경로: needs_hitl ? create_escalation : save_messages / HITL-OFF: save_messages)
  ```
  HITL·HITL-OFF 두 토폴로지 모두에 동일 폴백 분기를 단다.
- **deep module 재사용**: `GraphStore.vector_search`는 그대로 쓴다(변경 없음, 이미 결정적 테스트됨). 새 코드는 그래프 배선 + 얇은 보강 노드 + 플래그뿐.
- **주입 격리 유지**: 보강된 원문은 기존 `UNTRUSTED_DATA` 구역(비신뢰 데이터)으로 들어간다 — 웹 인제스션발 간접 인젝션 격리를 그대로 유지.
- **토큰 가드(구조적)**: `context_sufficient=True`(그래프로 답함)면 `source_search`/`vector_search`가 호출되지 않는다 → happy path는 토큰 추가 0.

## Testing Decisions

- **무엇이 좋은 테스트인가**: 내부 토폴로지가 아니라 **외부 행위**를 본다 — `run_chat_agent` 종단에서, *그래프엔 없고 `TextUnit`에만 있는 사실*을 묻는 질의가 **HITL/"모른다" 대신 원문으로 답하는지**. 그래프 토폴로지를 리팩터해도 살아남는 테스트.
- **LLM은 Fake**(CLAUDE.md): `complete_structured`를 결정적 Fake로 — 근거(rag_chunks)에 정답 키워드가 있으면 `context_sufficient=True` + 답, 없으면 `context_sufficient=False`. 이는 **우리 배선**(miss 시 원문을 보강하고 재호출하는지)을 검증하지 외부 모델의 판단력을 검증하지 않는다.
- **Neo4j·임베딩·`vector_search`는 실제**(결정적). 픽스처: `TextUnit`을 임베딩과 함께 직접 upsert(또는 소형 문서 인제스트)하고, 같은 사실의 엔티티는 그래프에 두지 않아 "그래프 miss, 원문 hit" 상황을 구성.
- **토큰 가드 테스트**: 그래프로 답한 happy path에서 `source_search`/`vector_search`가 **호출되지 않고** `rag_chunks`가 불변임을 확인.
- **Prior art**: `test_graph_search.py`(실제 `vector_search`), `test_provider.py`의 `fake_chat_llm`(LLM 경계 Fake), `test_rag.py`(인제스션 종단).

## Out of Scope

- **추출 단계 개선**(스펙/표를 엔티티로 더 잘 뽑기): 별개. 본 PRD는 *검색 보강*만 한다.
- **OCR/표 인식 개선**(가설 2): 별개. 본 케이스는 텍스트 레이어가 깨끗해 무관(`is_garbled=False`).
- **스펙형 질의 사전 분류기**(LLM/키워드): 채택 안 함 — 증거 기반 폴백으로 대체.
- **Global Search**(커뮤니티 요약): 변경 없음.
- **`route_search`의 별도 LLM 호출 제거**(룰/임베딩 라우팅): 별개 최적화.

## Further Notes

- ADR-0010은 "거대한 Text Unit 대신 구조화 근거"를 택했는데, 본 PRD는 그 결정을 **폐기하지 않고 miss 시에만 원문을 보강**해 양립한다 — 평상시 구조화 토큰 이점 유지, 스펙형에서만 원문 비용 지불. 이 trade-off(정석 GraphRAG의 local에 TextUnit을 되살리되 조건부)는 ADR로 남길 가치가 있다(후속).
- 원문 `TextUnit`은 인제스션 시 이미 임베딩 저장 → **재인제스션 불필요**, 검색 배선만 추가.
- **패턴 계보**: `context_sufficient`는 **Self-RAG의 ISSUP(답이 근거에 뒷받침되는가) reflection을 boolean 한 칸으로 축약**한 경량형이고, miss 시 보정 검색은 **CRAG(Corrective RAG)** 계열이다. 약점은 LLM 자가보고의 과신(거짓 `True` → 조용한 miss)이며, 강한 grounding 프롬프트 + 구조화 필드로 완화한다. 검색측 점수 트리거(CRAG 본형)는 **이 케이스를 못 잡는다** — 엔티티는 매칭되고 빠진 건 *속성값*이라 답을 시도해야 드러나기 때문(그래서 답변측 신호를 택함). 장기적으로 에이전트를 tool-calling 검색으로 승격하면 이 플래그를 툴 호출로 대체할 수 있다.
