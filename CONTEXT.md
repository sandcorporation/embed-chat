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
Tenant별로 벡터 인덱싱된 문서 집합. 응대 매뉴얼 등 Tenant가 업로드한 문서로 구성됨. Visitor 무관, Tenant 전체에 적용됨.

**Document Label**
Tenant가 문서에 부여하는 사용자 편집 가능한 식별 이름. 업로드 시 파일명을 기본값으로 채우며, 이후 언제든 수정 가능. `Document.name` 필드에 저장됨. DocumentChunk 임베딩 시 `"<label>: <chunk_content>"` 형태로 prefix되어, 문서 본문에 제품명이 없어도 제품명 기반 쿼리로 해당 청크를 검색할 수 있게 한다. 레이블 변경 시 해당 문서의 모든 청크가 자동으로 재임베딩된다.
_Avoid_: 파일명, 문서명, title

**DocumentIngester**
문서를 벡터로 변환·저장하는 인터페이스. PDF/TXT/이미지(PNG·JPG·WEBP)를 지원하며 추가 형식을 확장 가능한 구조. PDF는 pymupdf로 먼저 추출하고, 추출 단어 수가 `PDF_OCR_FALLBACK_MIN_WORDS`(50) 미만이면 PaddleOCR로 재시도한다. 이미지 파일은 항상 PaddleOCR(`ch` 언어 모드, 한/영 혼용)을 통해 텍스트를 추출한다.
_Avoid_: OCR Ingester (이미지 전용이 아닌 PDF fallback도 포함하므로 ImageIngester/PDFIngester 클래스명을 사용)

**DocumentChunk**
DocumentIngester가 추출한 순수 텍스트 조각. `content`에는 Document Label prefix 없이 추출 원문만 저장된다. `embedding`은 `"<Document Label>: <content>"` 형태로 생성되며, 검색 결과를 LLM에 전달할 때도 같은 형태로 동적으로 prefix를 붙인다.
_Avoid_: chunk (단독 사용 시 모호함)

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
