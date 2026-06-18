# Embed Chat — GraphRAG 기반 멀티테넌트 챗봇 플랫폼

Embed Chat는 타사 웹사이트에 iframe으로 삽입하는 챗봇을 제공하는 멀티테넌트 SaaS 플랫폼입니다. **Operator**(운영자)가 플랫폼을 관리하고 **Tenant**(고객사)를 생성하면, Tenant는 자기 문서를 업로드해 **지식그래프(Knowledge Graph) 기반 RAG**로 답하는 챗봇을 자기 사이트의 **Visitor**에게 노출합니다. AI가 불확실하거나 방문자가 상담원을 찾으면 **HITL(Human-in-the-Loop)**로 사람 상담원에게 넘어갑니다.

용어는 [`CONTEXT.md`](./CONTEXT.md)(도메인 글로서리), 설계 결정은 [`docs/adr/`](./docs/adr/)를 참조하세요.

---

## 1. 시스템 구성

| 컴포넌트 | 역할 |
|----------|------|
| **Django API** (`/api/`) | 인증, 채팅(SSE), RAG/지식그래프, Visitor Memory, HITL |
| **Celery Worker** | 문서 인제스션(그래프 구축), 커뮤니티 재구축, 메모리 추출 비동기 처리 |
| **Neo4j** (Community) | **Knowledge Graph**(Entity·관계·Community)와 벡터 인덱스(Text Unit/Entity 임베딩) |
| **PostgreSQL** | Django 모델(Tenant·Document·ChatMessage 등) + **LangGraph Checkpoint**(대화 state) |
| **Ollama** | 임베딩 모델 `bge-m3`(다국어, 1024차원) 서빙. (선택적으로 로컬 LLM도) |
| **PaddleOCR 서비스** | 이미지/스캔 PDF에서 텍스트 추출(OCR, 한·영 혼용) |
| **Redis** | SSE pub/sub + Celery 브로커 |
| **Widget** (`/embed/`) | Visitor용 채팅 위젯 (React) |
| **Admin UI** (`/admin-ui/`) | Operator·Tenant 관리 화면 (React) — 문서·**지식그래프 인스펙터**·Visitors·설정·팀원·HITL 탭 |
| **Nginx** | 리버스 프록시, 정적 파일 서빙 |

> **저장소 역할 분담**: PostgreSQL은 관계형 데이터 + LangGraph 대화 체크포인트, **Neo4j는 RAG 지식그래프와 모든 RAG 임베딩**을 담당합니다. (과거 pgvector 기반 벡터 RAG는 GraphRAG로 대체됨 — [ADR-0007](./docs/adr/0007-graphrag-neo4j-replaces-2step-vector-rag.md).)

---

## 2. 지식그래프 기반 RAG 원리

기존의 2-step 벡터 RAG(쿼리 임베딩 → 최근접 청크 → LLM)는 (a) 본문에 제품명이 없는 엔티티 질의, (b) 여러 문서를 가로지르는 멀티홉/요약 질의에 약했습니다. Embed Chat는 이를 **Microsoft GraphRAG식 지식그래프**로 대체했습니다.

### 2.1 그래프 구조

Tenant마다 하나의 지식그래프가 Neo4j에 저장됩니다. 모든 노드/관계는 `tenant_id` 속성으로 격리됩니다(아래 2.5).

- **Entity** — 문서에서 LLM이 추출한 의미 단위(제품·사양·액세서리·기능 등). `name`/`type`/`description`을 가지며, `(tenant_id, name)`로 식별되어 **여러 문서에 같은 이름으로 등장하면 한 노드로 병합**됩니다(이름 기반 정규화). 각 Entity는 출처 Document 집합을 보유합니다.
- **관계(RELATED)** — Entity 간 엣지(`description` 보유). 추출된 (subject, relation, object) 트리플에서 생성됩니다.
- **Document(레이블) Entity** — 업로드한 문서를 대표하는 Entity. 그 문서에서 추출된 모든 Entity와 `mentions` 관계로 연결되어, **본문에 제품명이 없어도** 문서를 통해 내부 엔티티에 도달할 수 있습니다.
- **Text Unit** — 문서를 일정 크기로 나눈 텍스트 조각 노드. `bge-m3` 임베딩을 가지며 Local Search의 근거 문맥(citation)으로 쓰입니다.
- **Community** — 밀접하게 연결된 Entity 묶음(연결 요소). 각 Community에는 LLM이 생성한 요약이 붙어 Global Search에 사용됩니다.

### 2.2 인제스션 파이프라인 (업로드 → 그래프)

문서를 업로드하면 Celery 태스크가 실행됩니다:

```
업로드 → 텍스트 추출 → LLM Entity/관계 추출 → 그래프 기여 → Text Unit 임베딩 → Graph Freshness=stale
```

1. **텍스트 추출**: PDF는 PyMuPDF로 추출하고, 추출 단어 수가 50 미만이면 PaddleOCR로 OCR fallback. 이미지(PNG·JPG·WEBP)는 항상 OCR. TXT는 그대로.
2. **Entity/관계 추출**: 추출 텍스트를 **플랫폼 전용 추출 모델**(`GRAPH_EXTRACTION_MODEL`)에 구조화 출력으로 보내 `(entities, relations)`를 받습니다. 추출은 **해당 문서 내부만** 봅니다(기존 그래프와 비교하지 않음). 문서 레이블 Entity를 시드하고, 추출된 각 Entity에 `mentions` 관계로 연결합니다.
3. **임베딩**: 추출된 Entity(`name+description`)와 Text Unit을 `bge-m3`로 **배치 임베딩**해 Neo4j 벡터 인덱스(`entity_embedding`, `text_unit_embedding`, 둘 다 1024차원 cosine)에 저장합니다.
4. **신선도 표시**: 그래프가 바뀌었으므로 Community 요약은 `stale`로 표시됩니다. Community 탐지·요약은 전역 연산이라 업로드마다 돌리지 않고 **배치/트리거**로 재구축합니다([ADR-0008](./docs/adr/0008-incremental-ingest-batched-community-rebuild.md)).

### 2.3 검색: route → Local / Global

채팅 그래프(LangGraph)는 질의를 분류해 검색 방식을 라우팅합니다:

```
route_search ──(search_scope)──▶ local_search ─┐
                              └▶ global_search ─┴▶ call_llm
```

- **Local Search** — 특정 Entity·근거 문맥 질의("이 제품의 전원 사양은?"). Text Unit 벡터 검색 + Entity 이웃 탐색으로 근거를 모읍니다.
- **Global Search** — 전체/요약형 질의("매뉴얼들이 공통 권장하는 설정은?"). Community 요약들을 map-reduce해 답을 구성합니다(Local보다 비쌈).
- 라우팅은 별도 LLM 호출 없이 구조화 출력의 `search_scope` 필드로 결정합니다.

### 2.4 엔티티 의미 검색 (다국어 하이브리드)

지식그래프 인스펙터(어드민 "🕸️ 지식그래프" 탭)와 검색은 **하이브리드**로 동작합니다:

- **어휘(lexical)** — 이름/설명 부분일치. 정확 이름·문서 레이블 검색을 보장.
- **의미(semantic)** — `bge-m3`가 다국어라, 한↔영·동의어 질의를 임베딩 공간에서 매칭. 예: **"메뉴" → "OSD Menu"** 검색이 가능합니다.

두 결과를 이름 키로 dedup해 합칩니다. (관계는 임베딩하지 않고, 엔티티에서 이웃 확장으로 도달합니다.)

### 2.5 멀티테넌시 격리

단일 Neo4j 그래프에 모든 Tenant가 공존하되, **모든 노드/관계에 `tenant_id` 속성**을 두고 **`GraphStore` 경계 모듈**이 모든 쿼리에 `tenant_id`를 강제로 주입합니다. tenant_id 없이는 그래프에 접근할 수 없어 테넌트 간 누수를 구조적으로 막습니다. (Enterprise 멀티 DB 대신 Community + 속성 격리 — 운영 단순성 우선.)

### 2.6 그래프 신선도와 재구축

- **Graph Freshness**: `fresh`(요약 최신) / `stale`(문서 추가·삭제로 재구축 필요) / `rebuilding`.
- 문서 추가/삭제 시 `stale`. 어드민의 **"재구축" 버튼** 또는 자동 트리거로 Community를 재탐지·재요약하고, 임베딩이 없는 기존 Entity도 이때 백필합니다.
- `stale` 상태에서도 직전 Community 요약으로 Global Search는 계속 동작합니다.
- 문서 삭제 시 노드/관계의 출처 집합에서 그 문서를 제거하고, **출처가 빈 것만** prune합니다(여러 문서가 공유하는 Entity는 보존).

---

## 3. 채팅 & 대화 메모리

채팅은 LangGraph로 구현됩니다:

```
START → route_search → (local_search | global_search) → call_llm
                                                            ├─(needs_hitl)→ create_escalation → END
                                                            └─────────────→ save_messages    → END
```

- **Conversation Memory**: 단일 ChatSession 내 히스토리는 **LangGraph Checkpoint**(PostgreSQL)로 관리됩니다. `thread_id = session_id`라 수동 로드 없이 이전 state가 자동 복원됩니다.
- **Visitor Memory**: ChatSession을 넘어 축적되는 장기 기억. 대화 중 LLM이 자동 추출하며 어드민에서 조회·수정·삭제할 수 있습니다.
- **VisitorContext**: EmbedToken 발급 시 Tenant가 넘긴 정적 메타데이터(이름·플랜·언어 등)가 시스템 프롬프트에 주입됩니다.
- **스트리밍**: 토큰·HITL 이벤트는 Redis pub/sub(`session:{id}` 채널)을 통해 SSE로 전달됩니다([ADR-0001](./docs/adr/0001-sse-redis-pubsub.md)). 다중 API 인스턴스에서도 스트리밍이 보장됩니다.

### HITL (Human-in-the-Loop)

- **트리거**: (1) LLM이 구조화 출력으로 `needs_hitl: true` 반환(불확실 판단 + 상담원 요청 키워드 통합), (2) 방문자의 명시적 상담원 요청.
- **상태**: Escalation `pending` → `claimed` → `resolved`.
- HITL 모드에서는 AI가 침묵하고, 팀원이 "수락하기"로 클레임한 뒤 메시지를 보냅니다. "AI에게 넘기기"로 다시 AI 모드로 복귀합니다.
- Escalation 발생 시 Slack/Discord/Generic **웹훅**으로 알림을 보냅니다.

---

## 4. 기술 사양

| 영역 | 사양 |
|------|------|
| 백엔드 | Python 3.12, Django 5 + Django-Ninja, Celery 5, Gunicorn(gevent) |
| LLM 오케스트레이션 | LangChain + LangGraph (PostgresSaver 체크포인트) |
| Chat LLM | OpenRouter(OpenAI 호환). Tenant별 `model_id` 설정 |
| 추출 LLM | 플랫폼 전용 `GRAPH_EXTRACTION_MODEL`(구조화 출력) |
| 임베딩 | `bge-m3`(Ollama, 다국어, 1024차원), cosine |
| Knowledge Graph | Neo4j 5.x Community + 네이티브 벡터 인덱스 |
| OCR | PaddleOCR(PP-OCRv5, 한·영) — 이미지/스캔 PDF |
| 관계형 DB | PostgreSQL 16 (Django 모델 + LangGraph 체크포인트) |
| 메시징 | Redis 7 (SSE pub/sub + Celery 브로커) |
| 프론트 | React 18 + Vite. 그래프 시각화: `react-force-graph-2d` |
| 인증 | JWT(python-jose). EmbedToken은 단기 서명 토큰 |

> **GPU**: PaddleOCR·Ollama는 GPU 빌드를 사용합니다. Docker Desktop에서는 `runtime: nvidia` + `NVIDIA_VISIBLE_DEVICES=all`로 패스스루합니다. bge-m3가 GPU flash-attention에서 NaN 임베딩을 내는 이슈가 있어 `OLLAMA_FLASH_ATTENTION=0`을 설정합니다.

---

## 5. 환경 변수 (.env)

| 변수 | 설명 | 예시 |
|------|------|------|
| `SECRET_KEY` | Django 서명 키 | 임의의 긴 문자열 |
| `DB_NAME / DB_USER / DB_PASSWORD / DB_HOST / DB_PORT` | PostgreSQL 접속 정보 | |
| `REDIS_URL` | Redis URL | `redis://redis:6379/0` |
| `NEO4J_URI` | Neo4j Bolt URL | `bolt://neo4j:7687` |
| `NEO4J_USER / NEO4J_PASSWORD` | Neo4j 자격 | `neo4j` / `...` |
| `OPEN_ROUTER_API_KEY` | OpenRouter API 키 | `sk-or-v1-...` |
| `OPEN_ROUTER_DEFAULT_MODEL` | 기본 Chat LLM | `openrouter/owl-alpha` |
| `OPEN_ROUTER_BASE_URL` | OpenRouter endpoint | `https://openrouter.ai/api/v1` |
| `GRAPH_EXTRACTION_MODEL` | Entity/관계 추출 모델 | (미지정 시 기본 모델) |
| `OLLAMA_BASE_URL` | Ollama URL(임베딩) | `http://ollama:11434` |
| `OLLAMA_EMBED_MODEL` | 임베딩 모델 | `bge-m3` |
| `PADDLE_OCR_URL` | PaddleOCR 서비스 URL | `http://paddle-ocr:8080` |
| `EMBED_TOKEN_TTL_SECONDS` | EmbedToken 만료(초) | `300` |
| `DEBUG` | 디버그 모드 | `False`(운영) |

---

## 6. 빠른 시작 (개발)

```bash
# 1. 환경 변수
cp .env.example .env
# .env에 DB/Redis/Neo4j/OpenRouter 키 입력

# 2. 인프라 + 앱 기동 (dev 스택: db, redis, neo4j, ollama(+bge-m3), paddle-ocr, api, worker, widget, admin)
docker compose -f docker-compose.dev.yml up --build

# 3. 최초 1회: 마이그레이션 + Operator 계정
docker compose exec api python manage.py migrate
docker compose exec api python manage.py createsuperuser
```

접근 경로:

| 경로 | 용도 |
|------|------|
| `http://localhost:5174/admin-ui/` | Operator·Tenant 관리 화면 |
| `http://localhost:8000/api/docs` | Django-Ninja 자동 API 문서 |
| `http://localhost:5173/embed/?token=...` | Visitor 챗봇 위젯 |
| `http://localhost:7474` | Neo4j Browser (그래프 직접 조회, 개발용) |

## 프로덕션 배포

```bash
cp .env.example .env   # DB_HOST=db, REDIS_URL=redis://redis:6379/0, NEO4J_URI=bolt://neo4j:7687 등
docker compose -f docker-compose.prod.yml up --build -d --force-recreate
docker compose exec api python manage.py migrate
docker compose exec api python manage.py createsuperuser
```

---

## 7. 사용 흐름

### Tenant 발급 (Operator)
1. Admin UI에서 Operator로 로그인 → **Tenant 추가** → `TENANT_KEY`와 초기 상담원 임시 비밀번호가 **1회** 표시됨.
2. `TENANT_KEY`는 DB에 해시만 저장되므로 분실 시 재발급. Tenant 서버가 EmbedToken 발급/팀원 생성에만 사용(브라우저 비노출).

### Tenant 운영 (TenantAgent)
1. 어드민 UI 로그인 → **문서 탭**에서 PDF/TXT/이미지 업로드(레이블 지정 가능) → 그래프 자동 구축.
2. **🕸️ 지식그래프 탭**: 엔티티 검색(다국어 의미 검색) → 노드-엣지 그래프로 탐색, 노드 클릭으로 이웃 확장.
3. 그래프 신선도 확인 후 **재구축** 트리거. **HITL 탭**에서 에스컬레이션 수락·응대.

### Visitor
- Tenant 사이트에 임베드된 위젯이 EmbedToken으로 연결 → 지식그래프 RAG로 응답, 필요 시 HITL 전환.

---

## 8. API 개요 (`GET /api/docs`에 전체)

| 엔드포인트 | 인증 | 용도 |
|------------|------|------|
| `POST /api/operator/auth/login` | 없음 | Operator JWT |
| `POST /api/operator/tenants/` | Operator JWT | Tenant 생성 |
| `POST /api/tenant/agents/auth/login` | 없음 | TenantAgent JWT |
| `POST /api/embed/token` | TENANT_KEY | EmbedToken 발급 |
| `POST /api/chat/message` | EmbedToken 세션 | 방문자 메시지(SSE로 응답) |
| `POST /api/tenant/documents/` | TenantAgent JWT | 문서 업로드(그래프 인제스션 트리거) |
| `GET /api/tenant/documents/{id}/chunks` | TenantAgent JWT | 문서의 Text Unit 조회 |
| `GET /api/tenant/documents/graph/search?q=` | TenantAgent JWT | 엔티티 하이브리드 검색 → 서브그래프 |
| `GET /api/tenant/documents/graph/neighbors?entity=` | TenantAgent JWT | 엔티티 1홉 이웃 서브그래프 |
| `GET /api/tenant/documents/graph/status` | TenantAgent JWT | Graph Freshness |
| `POST /api/tenant/documents/graph/rebuild` | TenantAgent JWT | Community 재구축 트리거 |

---

## 9. 테스트

- **단위/통합**: `docker-compose.test.yml`의 `test` 서비스(pytest). **실제 Neo4j·실제 bge-m3**를 사용(결정적). 비결정적 외부 경계인 **LLM 호출만 결정적 Fake로 교체**합니다(`apps/agent/llm` 경계 + conftest Fake) — 외부 모델 판단이 아니라 우리 코드 동작을 검증.
  - **실행**: `./scripts/test.ps1` (PowerShell) 또는 `bash scripts/test.sh` — 호스트 `backend/`를 마운트해 코드 변경을 즉시 반영하고, **종료 시 테스트 전용 인프라(Neo4j·OCR·ollama 등 GPU 포함)를 자동 `stop`** 하여 VRAM/메모리를 돌려줍니다(다음 실행은 `start`로 빠르게 재개). 인자로 특정 테스트 경로를 넘길 수 있습니다(예: `bash scripts/test.sh tests/test_rag.py`).
- **E2E**: Playwright. 챗 LLM은 OpenAI 호환 **Fake LLM 서비스**(`fake_llm/`)로 결정화합니다.
- 인제스션·추출 프롬프트의 실제 타당성은 실제 OpenRouter로 bring-up 검증합니다.

---

## 10. 설계 결정(ADR)

- `0001` SSE + Redis pub/sub
- `0003` iframe 임베드 / `0004` 서버사이드 EmbedToken
- `0005` Docker Compose 인프라
- **`0007` GraphRAG(Neo4j)가 2-step 벡터 RAG를 대체** (pgvector ADR-0002 supersede)
- **`0008` 증분 인제스션 + 배치 Community 재구축**
