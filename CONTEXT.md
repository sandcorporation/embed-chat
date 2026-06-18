# Domain Glossary

## Actors

**Operator**
이 챗봇 플랫폼 자체를 운영하는 팀. 어드민 페이지 최상위 권한 보유. Tenant 계정 생성/정지, 전체 현황 모니터링 담당.

**Tenant**
챗봇을 자기 사이트에 embed해서 쓰는 B2B 계약 고객사. 자기 RAG Knowledge Base, Visitor Memory를 어드민 페이지에서 직접 관리.

**TenantAgent**
Tenant 조직 소속의 개별 상담원 계정. 고유한 username/password를 갖고, Tenant 어드민 UI에 개인 자격으로 로그인한다. HITL `EscalationClaim.claimed_by` 식별자로 사용되어 누가 어떤 세션을 담당하는지 추적한다. TENANT_KEY(서버사이드 시크릿)와 구분되며, TenantAgent는 조직 내 여러 명이 존재할 수 있다.

**Visitor**
Tenant 사이트에서 챗봇을 실제로 사용하는 최종 사용자. Tenant 시스템의 회원 ID일 수도 있고, 익명 사용자일 수도 있음.

## Authentication & Session

**TENANT_KEY**
Tenant를 식별하는 서버사이드 전용 시크릿. 절대 브라우저에 노출되지 않음. 두 가지 용도로만 사용: (1) Tenant 서버가 EmbedToken 발급 요청 시, (2) TenantAgent 계정을 API로 생성할 때. 어드민 UI 로그인에는 사용하지 않음.

**TenantAgent 자격증명**
TenantAgent가 어드민 UI에 로그인할 때 사용하는 username/password. Operator가 Tenant를 생성하면 초기 TenantAgent의 username과 임시 password가 1회 화면에 표시된다. 이후 추가 TenantAgent 계정은 TENANT_KEY로 인증된 API 또는 어드민 UI "팀원" 탭에서 생성한다. 로그인 성공 시 JWT를 발급받아 어드민 UI 전 기능에 접근한다.

**EmbedToken**
Operator가 발급하는 단기 서명 토큰 (TTL 보유). Tenant 서버가 `TENANT_KEY + VisitorId`로 발급 요청하면 생성됨. iframe src URL에 포함되어 Visitor 브라우저에 전달.

**ChatSession**
Visitor가 EmbedToken으로 최초 연결할 때 생성되는 세션. VisitorId에 귀속되며, 세션 이후 채팅 이력은 ChatSession 단위로 저장됨.

**VisitorContext**
EmbedToken 발급 시 Tenant가 함께 넘기는 Visitor의 정적 메타데이터. 예: `{ "name": "홍길동", "plan": "premium", "language": "ko" }`. LLM 시스템 프롬프트에 주입되어 응대 방식을 조정하는 데 사용됨.

## Knowledge & Memory

**RAG Knowledge Base**
Tenant별 지식그래프(Knowledge Graph). Tenant가 업로드한 문서에서 추출한 Entity와 그 관계, 그리고 Community 요약으로 구성됨. 응대 매뉴얼 등이 원천이며, Visitor 무관·Tenant 전체에 적용됨.
_Avoid_: 벡터 인덱스(이제 그래프가 1차 구조이며 벡터는 그 위의 검색 보조 수단)

**Knowledge Graph**
RAG Knowledge Base의 1차 구조. 노드는 Entity, 엣지는 Entity 간 관계. 각 노드/관계는 어떤 Document에서 추출됐는지(출처)와 소속 Tenant를 보유한다.

**Entity Mention**
문서에서 LLM이 추출한 개별 언급(이름 + 그 문맥의 설명 + 출처 Document). 같은 표기라도 맥락이 다르면 별개의 Mention이다(한강 "다리"와 신체 "다리"는 다른 Mention). Entity Equivalence를 거쳐 Entity로 묶이기 전의 원자료다.
_Avoid_: Entity(동치로 묶기 이전 단계는 Mention)

**Entity**
같은 실세계 대상(referent)을 가리키는 Entity Mention들이 동치로 묶인 정체(예: 특정 제품, 사양, 액세서리). **정체성은 이름이 아니라 맥락(설명·이웃 관계·출처)으로 결정된다** — 같은 이름이라도 맥락이 다르면 다른 Entity(한강 "다리" vs 신체 "다리"), 이름이 달라도 맥락이 같으면 같은 Entity("FCB1010"="FCB-1010"). 이름과 설명으로 **의미 검색**이 가능하며, 한↔영 등 다국어·동의어 질의도 매칭된다(예: "메뉴" → "OSD Menu").
_Avoid_: 벡터 인덱스; "이름으로 식별"(이름은 약한 보조 신호일 뿐)

**Entity Equivalence**
두 Entity Mention이 같은 referent를 가리키는 동치 관계. 이름 유사도만으론 불충분하며(동음이의·표기변이가 이름을 오도한다) 맥락 정합으로 판별한다. 동치인 Mention들이 하나의 Entity를 이룬다.
_Avoid_: 정규화(텍스트 정규화와 혼동); 병합(노드를 물리적으로 합치지 않는 비파괴 동치다)

**Community**
Knowledge Graph에서 밀접하게 연결된 Entity 묶음. 각 Community에는 LLM이 생성한 요약(Community 요약)이 붙어, 글로벌/요약형 질의에 사용된다.

**Local Search**
특정 Entity와 그 이웃(관계로 연결된 Entity·출처 문서 조각)을 탐색하는 검색. "이 제품의 사양은?"처럼 한 대상에 집중된 질의에 사용.

**Global Search**
Community 요약들을 가로질러(map-reduce) 답을 구성하는 검색. "공통으로 권장하는 설정은?"처럼 전체/요약형 질의에 사용. Local Search보다 비싸다.

**Document Label**
Tenant가 문서에 부여하는 사용자 편집 가능한 식별 이름. 업로드 시 파일명을 기본값으로 채우며, 이후 언제든 수정 가능. `Document.name` 필드에 저장됨. Knowledge Graph에서 해당 문서를 대표하는 Entity의 이름이자, 그 문서에서 추출된 노드/관계의 출처 표시에 쓰인다. (옛 벡터 RAG의 "청크 임베딩 prefix + 재임베딩" 메커니즘은 GraphRAG의 Entity 추출로 대체됨 — 본문에 없는 제품명도 Entity로 잡히므로 prefix가 불필요.)
_Avoid_: 파일명, 문서명, title

**DocumentIngester**
문서에서 텍스트를 추출한 뒤 그 텍스트를 Knowledge Graph 기여분(Entity·관계)으로 변환·저장하는 인터페이스. PDF/TXT/이미지(PNG·JPG·WEBP)를 지원. 텍스트 추출 단계: PDF는 추출 후 **단어 수 부족 또는 깨진 추출(Garbled Extraction) 감지 시 OCR로 재추출(fallback)**, 이미지는 OCR. 추출된 텍스트는 LLM Entity/관계 추출을 거쳐 그래프에 기여하며, 각 기여 노드/관계에는 출처 Document가 기록된다.
_Avoid_: OCR Ingester (이미지 전용이 아닌 PDF fallback도 포함하므로 ImageIngester/PDFIngester 클래스명을 사용); "벡터로 변환"(이제 그래프 기여가 1차 산출물)

**Garbled Extraction**
PDF 텍스트 레이어의 폰트 인코딩(ToUnicode/CID 매핑) 부재로 글리프가 의미 없는 문자열(mojibake)로 추출된 상태. 원문 정보가 텍스트 레이어에서 소실되어 LLM 정제로는 복원할 수 없고(추측=창작이 됨) OCR(픽셀 재인식)로만 되찾을 수 있다. 추출 직후 문자 클래스 비율 휴리스틱으로 문서 단위 감지하며, 감지 시 OCR 재추출이 트리거된다.
_Avoid_: 인코딩 오류(너무 일반적), 깨진 글자

**Text Unit**
문서를 일정 크기로 나눈 텍스트 조각. Knowledge Graph의 노드로 저장되며 임베딩을 가져 Local Search의 근거 문맥(citation)으로 쓰인다. 어떤 Entity들이 이 조각에서 추출됐는지, 그리고 출처 Document와 연결된다. citation은 검증의 기준점이므로 **추출 원문(또는 OCR 재추출본)에 충실**해야 하며 LLM이 정제·생성한 텍스트를 담지 않는다 — 이 점에서 LLM 해석물인 Entity와 구분된다(Garbled Extraction 참조).
_Avoid_: DocumentChunk(옛 pgvector 모델의 명칭 — GraphRAG에선 그래프 노드인 Text Unit), chunk(단독 사용 시 모호)

**Graph Freshness**
Tenant Knowledge Graph의 전역 신선도 상태: `fresh`(Community 요약이 최신) / `stale`(문서 추가·삭제로 재구축 필요) / `rebuilding`(재구축 중). 문서별 처리 상태(`Document.status`)와 별개이며, Global Search의 최신성을 나타낸다. stale이어도 직전 Community 요약으로 Global Search는 동작한다.

**Visitor Memory**
특정 Visitor에 대해 ChatSession을 넘어 축적되는 장기 기억. LLM이 대화 중 자동 추출하며, 어드민이 조회·수정·삭제 가능.

**Conversation Memory**
단일 ChatSession 내의 대화 히스토리. LangGraph Checkpoint로 관리됨. `thread_id = session_id`로 세션별로 구분되며, 수동 히스토리 로드 없이 LangGraph가 이전 state를 자동 복원함.

**LangGraph Checkpoint**
LangGraph가 PostgreSQL에 저장하는 그래프 실행 state 전체 스냅샷. `thread_id = session_id`로 ChatSession에 귀속됨. 매 LLM 호출 후 자동 저장되며, 다음 호출 시 자동 복원됨. ChatMessage와 별개로 존재하며 ChatMessage는 Visitors 탭 조회용으로 별도 유지됨.

## Tenant Configuration

**TenantConfig**
Tenant별 설정 집합. 어드민에서 Tenant가 직접 관리. 포함 항목:
- `model_id`: OpenRouter 모델 식별자 (예: `anthropic/claude-sonnet-4-5`)
- `system_prompt`: Tenant가 직접 편집하는 Base System Prompt. Operator가 기본 템플릿을 제공하며 Tenant가 수정 가능. RAG 결과·VisitorContext·Visitor Memory는 이 프롬프트에 자동 주입됨
- `welcome_message`: ChatWidget이 열릴 때 Visitor에게 자동으로 표시되는 환영 메시지. 비어 있으면 표시하지 않음. SSE `connected` 이벤트 payload에 포함되어 전달됨
- `agent_display_name`: HITL 모드에서 Visitor 위젯에 표시되는 상담원 발신자 이름. 예: "ABC쇼핑 고객센터"
- `webhook_url`: HITL 발생 시 알림을 보낼 웹훅 URL
- `webhook_type`: 웹훅 플랫폼 종류. `slack` / `discord` / `generic` 중 하나. 플랫폼별로 페이로드 포맷이 다르게 전송됨

**WebhookConfig**
TenantConfig 내 웹훅 설정 집합. HITL 발생 시 Slack·Discord·Generic 엔드포인트로 알림을 발송하기 위한 정보. 알림 페이로드에는 HITL 트리거 유형, 마지막 N개 대화, VisitorContext, 어드민 UI 딥링크가 포함됨.

## Human-in-the-Loop (HITL)

**Escalation**
ChatSession이 AI 응대에서 사람 응대로 전환되는 이벤트이자 상태. 트리거는 두 가지: (1) LLM이 Structured Output으로 `needs_hitl: true`를 반환할 때(AI 불확실 판단 + Visitor의 상담원 요청 키워드 감지 통합), (2) Visitor가 명시적으로 상담원 요청 키워드를 입력할 때. Escalation 상태: `pending` → `claimed` → `resolved`.

**EscalationClaim**
Tenant 팀원이 특정 Escalation의 처리를 수락한 행위 및 기록. 클레임된 Escalation은 해당 클레이머에게 잠기고, 다른 팀원은 읽기 전용. 클레이머가 "AI에게 넘기기"를 누르면 Escalation이 `resolved` 상태로 전환되고 ChatSession은 AI 모드로 복귀.

**HITL 모드**
Escalation이 `pending` 또는 `claimed` 상태인 동안 ChatSession이 처하는 운영 상태. 이 모드에서는 AI가 완전히 침묵하고, Visitor 위젯에 시스템 메시지("상담원 연결 중" 또는 "상담원과 연결되었습니다")가 표시됨. Visitor는 HITL 전환 사실을 알 수 있음.

**HumanTurn**
HITL 모드에서 Tenant 상담원이 Visitor에게 보내는 메시지. ChatMessage와 동일한 구조이나 `role`이 `human_agent`로 저장됨. Visitor 위젯에서는 TenantConfig의 `agent_display_name`으로 표시됨.
