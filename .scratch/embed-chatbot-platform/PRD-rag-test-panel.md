# PRD: Tenant 대시보드 RAG 테스트 패널

Status: ready-for-agent
Labels: ready-for-agent

## Problem Statement

Tenant Agent가 PDF/TXT 문서를 업로드한 후, RAG 시스템이 실제로 원하는 내용을 검색하는지 확인할 방법이 없다. 문서를 업로드하고 챗 위젯에서 질문을 던져봐야 간접적으로 확인할 수 있는데, 이는 느리고 번거롭다. 어떤 청크가 얼마나 유사도가 높게 검색되는지 직접 볼 수 없어 RAG 품질을 튜닝하기 어렵다.

## Solution

Tenant 대시보드의 문서 탭(DocumentsTab) 하단에 **RAG 테스트 패널**을 추가한다. Tenant Agent가 쿼리 텍스트를 입력하고 검색하면, 현재 Tenant의 문서 청크 중 유사도가 높은 결과를 (문서명, 내용, 거리 점수와 함께) 즉시 확인할 수 있다.

백엔드 엔드포인트(`POST /api/tenant/documents/query`)는 이미 구현되어 있으며, 프론트엔드 연결과 UI 컴포넌트만 추가하면 된다.

## User Stories

1. As a Tenant Agent, I want to type a query in the document tab and see which chunks are retrieved, so that I can verify my documents are indexed correctly.
2. As a Tenant Agent, I want to see the similarity score for each retrieved chunk, so that I can understand which documents are most relevant for a given question.
3. As a Tenant Agent, I want to see the source document name alongside each chunk, so that I can trace which uploaded file produced the result.
4. As a Tenant Agent, I want to see the actual chunk content in the results, so that I can confirm the right text is being sent to the AI.
5. As a Tenant Agent, I want to control how many results (top_k) are returned, so that I can see more or fewer candidates when debugging.
6. As a Tenant Agent, I want the RAG test panel to show a loading state while querying, so that I know the system is working.
7. As a Tenant Agent, I want to see a clear "검색 결과 없음" message when no chunks match, so that I know if my documents need to be re-uploaded or re-indexed.
8. As a Tenant Agent, I want to press Enter in the query input to trigger a search, so that I don't have to use the mouse.
9. As a Tenant Agent, I want the RAG test panel to appear below the document list, so that I can see the document list and test results on the same screen.

## Implementation Decisions

- **백엔드 변경 없음**: `POST /api/tenant/documents/query` 엔드포인트는 이미 `{query: str, top_k: int}` 입력, `[{document_name, content, score}]` 출력으로 동작한다.
- **`api.js` 추가**: `queryDocuments(agentToken, query, topK)` 함수 추가. 내부적으로 `POST /api/tenant/documents/query`를 호출한다.
- **`DocumentsTab.jsx` 확장**: 기존 문서 목록 아래에 "RAG 테스트" 섹션을 추가한다. 분리된 컴포넌트로 추출하지 않고 같은 파일 내 함수 컴포넌트로 구현한다.
- **top_k 기본값**: 5, UI에서 숫자 입력으로 변경 가능 (1~20 범위).
- **점수 표시**: L2 거리 기반 score를 소수점 4자리까지 표시. 낮을수록 유사도가 높음을 표시 문구로 안내.
- **상태**: 로딩 중(`loading`), 결과 있음(`results`), 결과 없음(`empty`), 에러(`error`) 4가지 상태 처리.

## Testing Decisions

- **좋은 테스트 기준**: API 계약(입력/출력 형태)과 사용자 관찰 가능 동작(화면에 표시되는 내용)만 검증한다. 내부 상태나 구현 세부사항은 검증하지 않는다.
- **테스트 대상**:
  - `POST /api/tenant/documents/query` 엔드포인트 (백엔드): 기존 `test_rag_query_endpoint_returns_chunks_with_score_and_document_name` 테스트가 이미 커버한다. 추가 백엔드 테스트 불필요.
  - 프론트엔드 E2E: Playwright로 "문서 업로드 → RAG 쿼리 → 결과 확인" 흐름 검증.
- **Prior art**: `e2e/tests/visitors-tab.spec.js`의 패턴 (setup, loginAsTenantAgent, createVisitorSession) 참조.

## Out of Scope

- 쿼리 결과를 저장하거나 히스토리로 관리하는 기능
- 청크 단위 편집 또는 삭제
- 임베딩 모델 선택 UI
- 유사도 임계값(threshold) 필터링

## Further Notes

- 업로드된 문서가 없는 경우(`status=ready` 청크 없음) 빈 결과가 반환되며, "문서를 먼저 업로드하세요" 안내가 표시되는 것이 자연스럽다.
- 검색 결과의 score(L2 거리)는 낮을수록 더 유사함을 의미하므로 UI에 "(낮을수록 유사)" 부연 설명을 포함한다.
