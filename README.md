# Embed Chat — GraphRAG 기반 멀티테넌트 챗봇 플랫폼

Embed Chat는 타사 웹사이트에 iframe으로 삽입하는 챗봇을 제공하는 멀티테넌트 SaaS 플랫폼입니다. **Operator**(운영자)가 플랫폼을 관리하고 **Tenant**(고객사)를 생성하면, Tenant는 자기 문서·Excel·웹 URL을 올려 **지식그래프(Knowledge Graph) 기반 RAG**로 답하는 챗봇을 **공개 URL `/chatbot/{slug}/`**(토큰 발급 없이)로 자기 사이트의 **Visitor**에게 노출합니다. Tenant는 **자기 LLM·임베딩 Provider를 설정해 비용을 직접 부담**할 수 있고, **HITL(Human-in-the-Loop)** 사용 여부도 선택합니다 — 켜진 경우 AI가 불확실하거나 방문자가 상담원을 찾으면 사람 상담원에게 넘어갑니다.

용어는 [`CONTEXT.md`](./CONTEXT.md)(도메인 글로서리), 설계 결정은 [`docs/adr/`](./docs/adr/)를 참조하세요.

---

## 1. 시스템 구성

| 컴포넌트 | 역할 |
|----------|------|
| **Django API** (`/api/`) | 인증, 채팅(SSE), RAG/지식그래프, Visitor Memory, HITL, Provider 설정 |
| **Celery Worker** (배치) | 문서 인제스션(그래프 구축), 엔티티 해소(SAME_AS) 재구축, 재임베딩, 메모리 추출 |
| **Celery worker-chat** (chat 전용 큐) | Visitor chat 1턴 실행 — gevent web 워커에서 분리·격리(배치가 chat을 굶기지 않게) |
| **Neo4j** (Community) | **Knowledge Graph**(Entity Mention·관계) + **per-Tenant 가변차원 벡터 인덱스**(Text Unit/Mention 임베딩) |
| **PostgreSQL** | Django 모델(Tenant·Document·ChatMessage 등) + **LangGraph Checkpoint**(대화 state) |
| **Ollama** | dev 기본 임베딩 `bge-m3`(다국어, 1024차원). prod에선 Tenant Embedding Provider가 대체 |
| **PaddleOCR 서비스** | 이미지/스캔 PDF에서 텍스트 추출(OCR, 한·영 혼용) |
| **Redis** | SSE pub/sub + Celery 브로커 + 레이트리밋·세션 락 |
| **Widget** (`/chatbot/{slug}/`) | Visitor용 채팅 위젯 (React) — 토큰 없이 slug로 접근 |
| **Admin UI** (`/admin-ui/`) | Operator·Tenant 관리 화면 (React + Tailwind/shadcn) — **좌측 사이드바 내비 + 자원별 URL 라우트**(ADR-0017). 문서·**지식그래프 인스펙터**·Visitors·설정(Provider 포함)·팀원·HITL 섹션 |
| **Nginx** | 리버스 프록시, 정적 파일 서빙 |

> **저장소 역할 분담**: PostgreSQL은 관계형 데이터 + LangGraph 대화 체크포인트, **Neo4j는 RAG 지식그래프와 모든 RAG 임베딩**을 담당합니다. (과거 pgvector 기반 벡터 RAG는 GraphRAG로 대체됨 — [ADR-0007](./docs/adr/0007-graphrag-neo4j-replaces-2step-vector-rag.md).)

---

## 2. 지식그래프 기반 RAG 원리

기존의 2-step 벡터 RAG(쿼리 임베딩 → 최근접 청크 → LLM)는 (a) 본문에 제품명이 없는 엔티티 질의, (b) 여러 문서를 가로지르는 멀티홉/요약 질의에 약했습니다. Embed Chat는 이를 **Microsoft GraphRAG식 지식그래프**로 대체했습니다.

### 2.1 그래프 구조

Tenant마다 하나의 지식그래프가 Neo4j에 저장됩니다. 모든 노드/관계는 `tenant_id` 속성으로 격리됩니다(아래 2.5).

- **Entity Mention** — 문서에서 LLM이 추출한 개별 언급(`name`+그 문맥의 `description`+출처 Document). **같은 표기라도 맥락이 다르면 별개 노드**입니다(한강 "다리" vs 신체 "다리"). `(tenant_id, mention_id)`로 식별되며 이름으로 병합하지 **않습니다** — 정체성은 이름이 아니라 맥락이기 때문([ADR-0010](./docs/adr/0010-entity-resolution-mention-entity-context-equivalence.md)).
- **Entity (동치 클러스터)** — 같은 실세계 대상을 가리키는 Mention들이 **`SAME_AS` 비파괴 동치 엣지**로 묶인 정체. 동치는 이름 유사도가 아니라 **맥락(name+description 임베딩) 정합**으로 판별합니다 — 표기변이(`FCB1010`=`FCB-1010`)는 묶고, 동음이의는 분리. 노드를 물리적으로 합치지 않아 잘못 묶이면 엣지만 끊어 되돌립니다.
- **관계(RELATED)** — Mention 간 엣지(`description` 보유). 추출된 (subject, relation, object) 트리플에서 생성됩니다.
- **Document(레이블) Mention** — 업로드 소스를 대표하는 Mention. 그 문서에서 추출된 모든 Mention과 `mentions` 관계로 연결되어, **본문에 제품명이 없어도** 문서를 통해 내부 엔티티에 도달할 수 있습니다.
- **Text Unit** — 문서를 일정 크기로 나눈 텍스트 조각 노드. 임베딩을 가지며 Local Search의 원문 폴백 근거(citation)로 쓰입니다. citation은 추출 원문에 충실하며 LLM 정제물을 담지 않습니다.

### 2.2 인제스션 파이프라인 (업로드 → 그래프)

문서를 업로드하면 Celery 태스크가 실행됩니다:

```
업로드 → 텍스트 추출 → LLM Entity/관계 추출 → 그래프 기여 → Text Unit 임베딩 → Graph Freshness=stale
```

소스는 **파일 업로드**(PDF·TXT·이미지·**Excel xlsx/xls**)와 **웹 URL**(명시적, 재귀 크롤 아님) 두 가지입니다(Document Source로 분기).

1. **텍스트 추출**: PDF는 PyMuPDF로 추출하되 **단어 수 부족 또는 깨진 추출(Garbled Extraction, mojibake) 감지 시 PaddleOCR로 재추출**([ADR-0009](./docs/adr/0009-garbled-extraction-ocr-not-llm-cleanup.md) — LLM 정제가 아니라 OCR로 픽셀 재인식). 이미지는 OCR, TXT는 그대로, **Excel은 시트별 헤더-키 행별 텍스트로 평탄화**, **웹은 URL을 fetch해 메인 콘텐츠 추출**(보일러플레이트 제거).
2. **Entity/관계 추출**: 추출 텍스트를 **추출 LLM**(Tenant Provider 또는 플랫폼 기본)에 구조화 출력으로 보내 `(entities, relations)`를 받습니다. 추출은 **해당 문서 내부만** 봅니다. 문서 레이블 Mention을 시드하고, 추출된 각 Mention을 `mentions` 관계로 연결합니다(이름 병합 없이 — 동치는 재구축 단계에서 `SAME_AS`로).
3. **임베딩**: Mention(`name+description`)과 Text Unit을 **Tenant Embedding Provider**(미설정 시 dev=ollama `bge-m3`)로 배치 임베딩해 **per-Tenant 벡터 인덱스**에 저장합니다. 인덱스 차원은 Tenant의 임베딩 모델에 맞춰지고, Tenant마다 라벨·인덱스가 격리됩니다([ADR-0012](./docs/adr/0012-per-tenant-llm-embedding-providers.md)).
4. **신선도 표시**: 그래프가 바뀌었으므로 `stale`로 표시됩니다. **Entity Resolution(SAME_AS)**은 전역 연산이라 업로드마다 돌리지 않고 **배치/트리거**로 재구축합니다([ADR-0008](./docs/adr/0008-incremental-ingest-batched-community-rebuild.md), [ADR-0016](./docs/adr/0016-remove-global-search-keep-entity-resolution.md)).

### 2.3 검색: Local + 원문(TextUnit) 폴백

채팅 그래프(LangGraph)는 항상 **Local Search**로 가고, 그래프-only로 답을 못 내면 원문으로 보강합니다([ADR-0016](./docs/adr/0016-remove-global-search-keep-entity-resolution.md) — Global Search 제거):

```
local_search ─▶ call_llm ──(context_sufficient=False)──▶ source_search ─▶ call_llm(재호출)
```

- **Local Search** — Entity 중심 근거. 질의로 resolved Entity를 찾고 그 이웃 관계를 구조화 근거로 모읍니다([ADR-0010](./docs/adr/0010-entity-resolution-mention-entity-context-equivalence.md)).
- **원문 폴백(source_search)** — LLM이 "제공된 근거로 답할 수 없다"(`context_sufficient=False`)고 표시하면, 질의 임베딩으로 최근접 **Text Unit 원문**을 `vector_search`해 근거에 보강하고 한 번 더 호출합니다(top_k 캡). 추출이 버린 스펙·수치·표를 원문으로 회복합니다([ADR-0016](./docs/adr/0016-remove-global-search-keep-entity-resolution.md)). 그래프로 답한 경우엔 호출되지 않아 토큰을 통제합니다.
- **Global Search는 제거됨** — 커뮤니티 요약이 이름-only로 공허하고 지원 봇 질의는 대부분 특정형이라, local+원문 폴백으로 대체했습니다(ADR-0016).

### 2.4 엔티티 의미 검색 (다국어 하이브리드)

지식그래프 인스펙터(어드민 "🕸️ 지식그래프" 탭)와 검색은 **하이브리드**로 동작합니다:

- **어휘(lexical)** — 이름/설명 부분일치. 정확 이름·문서 레이블 검색을 보장.
- **의미(semantic)** — `bge-m3`가 다국어라, 한↔영·동의어 질의를 임베딩 공간에서 매칭. 예: **"메뉴" → "OSD Menu"** 검색이 가능합니다.

두 결과를 이름 키로 dedup해 합칩니다. (관계는 임베딩하지 않고, 엔티티에서 이웃 확장으로 도달합니다.)

### 2.5 멀티테넌시 격리

단일 Neo4j 그래프에 모든 Tenant가 공존하되, **모든 노드/관계에 `tenant_id` 속성**을 두고 **`GraphStore` 경계 모듈**이 모든 쿼리에 `tenant_id`를 강제로 주입합니다. tenant_id 없이는 그래프에 접근할 수 없어 테넌트 간 누수를 구조적으로 막습니다. (Enterprise 멀티 DB 대신 Community + 속성 격리 — 운영 단순성 우선.)

### 2.6 그래프 신선도와 재구축

- **Graph Freshness**: `fresh`(엔티티 해소 최신) / `stale`(문서 추가·삭제로 재구축 필요) / `rebuilding`.
- 문서 추가/삭제 시 `stale`. 어드민의 **"재구축" 버튼** 또는 자동 트리거로 **Entity Resolution(SAME_AS)**을 재수행하고, 임베딩이 없는 기존 Entity도 이때 백필합니다.
- 문서 삭제 시 노드/관계의 출처 집합에서 그 문서를 제거하고, **출처가 빈 것만** prune합니다(여러 문서가 공유하는 Entity는 보존).

---

## 3. 채팅 & 대화 메모리

채팅은 LangGraph로 구현됩니다:

```
START → local_search → call_llm ─(context_sufficient=False)─→ source_search → call_llm
                           │
                           ├─(needs_hitl?)─→ create_escalation → END
                           └──────────────→ save_messages     → END
```

채팅 그래프는 **Tenant의 `hitl_enabled` 토글에 따라 다르게 컴파일**됩니다. HITL-OFF면 `call_llm`이 `needs_hitl` 필드 없는 response-only 스키마를 쓰고 `save_messages`로 직행해, escalation 분기 자체가 없습니다(지키지 못할 전환 멘트 누수를 구조적으로 차단).

- **실행 격리**: chat 1턴은 gevent web 워커가 아니라 **전용 Celery `worker-chat`**(chat 큐)에서 실행되어 블로킹이 SSE 서빙을 얼리지 않습니다. 동일 세션 동시 실행은 Redis 락으로 직렬화하며, 공개 URL 남용은 (tenant, visitor)당 레이트리밋으로 막습니다(at-most-once).
- **Conversation Memory**: 단일 ChatSession 내 히스토리는 **LangGraph Checkpoint**(PostgreSQL)로 관리됩니다. `thread_id = session_id`라 수동 로드 없이 이전 state가 자동 복원됩니다.
- **Visitor Memory**: ChatSession을 넘어 축적되는 장기 기억. 대화 중 LLM이 자동 추출하며 어드민에서 조회·수정·삭제할 수 있습니다.
- **프롬프트 하드닝**(인젝션 방어): 비신뢰 입력(RAG·메모리·Visitor 메시지)을 `UNTRUSTED_DATA` 구역으로 격리·라벨링하고, 플랫폼이 anti-disclosure 지침을 항상 주입합니다. 테넌트 스코프 RAG와 무도구 에이전트가 크로스테넌트·행동 위험을 이미 차단합니다.
- **스트리밍**: 토큰·HITL 이벤트는 Redis pub/sub(`session:{id}` 채널)을 통해 SSE로 전달됩니다([ADR-0001](./docs/adr/0001-sse-redis-pubsub.md)). 다중 API 인스턴스에서도 스트리밍이 보장됩니다.

### HITL (Human-in-the-Loop)

- **활성화**: Tenant가 `hitl_enabled`로 켜고 끕니다(기본 켜짐). 끄면 AI 전용으로 운영되며 escalation이 발생하지 않습니다.
- **트리거**: (1) LLM이 구조화 출력으로 `needs_hitl: true` 반환(불확실 판단 + 상담원 요청 키워드 통합), (2) 방문자의 명시적 상담원 요청.
- **상태**: Escalation `pending` → `claimed` → `resolved`.
- HITL 모드에서는 AI가 침묵하고, 팀원이 "수락하기"로 클레임한 뒤 메시지를 보냅니다. "AI에게 넘기기"로 다시 AI 모드로 복귀합니다.
- Escalation 발생 시 Slack/Discord/Generic **웹훅**으로 알림을 보냅니다.

### Visitor 접근 & 신원 (공개 Slug URL)

옛 EmbedToken(per-session 서명 토큰) 방식은 폐지되고, **공개 `/chatbot/{slug}/` URL**로 대체됐습니다([ADR-0011](./docs/adr/0011-public-slug-url-replaces-embed-token.md)). Tenant는 발급 단계 없이 iframe만 박으면 됩니다.

- **Tenant Slug**: 표시명과 분리된 고유·URL-safe 공개 식별자. Tenant가 어드민에서 설정.
- **Visitor 신원 — 계층형**:
  - *익명*: 위젯이 생성·localStorage에 저장하는 **Anonymous Visitor ID**(세션 넘어 지속).
  - *식별 기본*: `?visitor_id=` 평문(마찰 0).
  - *식별 보안(opt-in)*: Tenant가 "신원검증 요구"를 켜면, `HMAC(tenant secret, visitor_id)` 해시를 요구·검증해 위조를 막습니다. 해시는 안정값이라 유저당 1회 계산해 캐시하며, Operator의 HMAC API(`POST /api/chat/identity`, TENANT_KEY 인증)로 받거나 직접 계산합니다.

---

## 4. 기술 사양

| 영역 | 사양 |
|------|------|
| 백엔드 | Python 3.12, Django 5 + Django-Ninja, Celery 5, Gunicorn(gevent) |
| LLM 오케스트레이션 | LangChain + LangGraph (PostgresSaver 체크포인트) |
| LLM Provider | **per-Tenant** — OpenAI / Claude(Anthropic 네이티브) / Custom(OpenAI-호환). 미설정 시 플랫폼 기본(OpenRouter). 챗·추출 공용, 키 암호화 저장 |
| Embedding Provider | **per-Tenant**(LLM과 독립) — OpenAI/Custom, OpenAI-호환 `/v1/embeddings`. dev 기본 `bge-m3`(Ollama, 1024차원) |
| Knowledge Graph | Neo4j 5.x Community + **per-Tenant 가변차원** 네이티브 벡터 인덱스 |
| OCR | PaddleOCR(PP-OCRv5, 한·영) — 이미지/스캔 PDF·깨진 추출 |
| 관계형 DB | PostgreSQL 16 (Django 모델 + LangGraph 체크포인트) |
| 메시징 | Redis 7 (SSE pub/sub + Celery 브로커 + 레이트리밋·세션 락) |
| 프론트 | React 18 + Vite. 그래프 시각화: `react-force-graph-2d` |
| 인증 | JWT(python-jose). Visitor는 공개 slug URL + opt-in HMAC 신원검증. TENANT_KEY는 HMAC API·팀원 생성용 |

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
| `OPEN_ROUTER_API_KEY` | 플랫폼 기본 LLM 키(Tenant Provider 미설정 시) | `sk-or-v1-...` |
| `OPEN_ROUTER_DEFAULT_MODEL` | 플랫폼 기본 Chat LLM | `openrouter/owl-alpha` |
| `OPEN_ROUTER_BASE_URL` | 플랫폼 기본 LLM endpoint | `https://openrouter.ai/api/v1` |
| `GRAPH_EXTRACTION_MODEL` | 플랫폼 기본 추출 모델 | (미지정 시 기본 모델) |
| `OLLAMA_BASE_URL` | Ollama URL(dev 기본 임베딩) | `http://ollama:11434` |
| `OLLAMA_EMBED_MODEL` | dev 기본 임베딩 모델 | `bge-m3` |
| `PLATFORM_DEFAULT_PROVIDERS_ENABLED` | 플랫폼 기본 Provider 폴백(OpenRouter LLM + ollama 임베딩). **dev만 `true`**, prod(GPU 없음)는 `false` → Tenant가 LLM·Embedding Provider 설정 필수. `dev.py`/`prod.py`에서 명시(env 아님) | `True`(dev)/`False`(prod) |
| `CHAT_RATE_LIMIT_PER_VISITOR` / `CHAT_RATE_LIMIT_PER_TENANT` | 공개 URL 레이트리밋(분당) | `20` / `300` |
| `PADDLE_OCR_URL` | PaddleOCR 서비스 URL | `http://paddle-ocr:8080` |
| `DEBUG` | 디버그 모드 | `False`(운영) |

---

## 6. 빠른 시작 (개발)

```bash
# 1. 환경 변수
cp .env.example .env
# .env에 DB/Redis/Neo4j/OpenRouter 키 입력

# 2. 인프라 + 앱 기동 (dev 스택: db, redis, neo4j, ollama(+bge-m3), paddle-ocr,
#    api, worker(배치), worker-chat(chat 전용), widget, admin)
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
| `http://localhost:5173/chatbot/{slug}/` | Visitor 챗봇 위젯 (토큰 없이 slug로) |
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
2. `TENANT_KEY`는 DB에 해시만 저장되므로 분실 시 재발급. Tenant 서버가 HMAC 신원검증 API 호출/팀원 생성에만 사용(브라우저 비노출).

### Tenant 운영 (TenantAgent)
1. 어드민 UI 로그인 → **설정 탭**에서 Tenant Slug, (선택) LLM·Embedding Provider 키, HITL 토글, 브랜드 텍스트, 신원검증 등을 설정.
2. **문서 탭**: PDF/TXT/이미지/**Excel** 업로드 또는 **웹 URL** 추가(레이블 지정 가능) → 그래프 자동 구축.
3. **🕸️ 지식그래프 탭**: 엔티티 검색(다국어 의미 검색) → 노드-엣지 그래프로 탐색, 노드 클릭으로 이웃 확장.
4. 그래프 신선도 확인 후 **재구축** 트리거. **HITL 탭**에서 에스컬레이션 수락·응대.

### Visitor
- Tenant 사이트에 임베드된 위젯이 **`/chatbot/{slug}/`**(필요 시 `?visitor_id=`·`hash`)로 연결 → 지식그래프 RAG로 응답, HITL이 켜져 있으면 필요 시 사람 전환.

---

## 8. API 개요 (`GET /api/docs`에 전체)

| 엔드포인트 | 인증 | 용도 |
|------------|------|------|
| `POST /api/operator/auth/login` | 없음 | Operator JWT |
| `POST /api/operator/tenants/` | Operator JWT | Tenant 생성 |
| `POST /api/tenant/agents/auth/login` | 없음 | TenantAgent JWT |
| `POST /api/chat/identity` | TENANT_KEY | visitor_id 신원검증 HMAC 해시 발급 |
| `GET /api/chat/stream?slug=&visitor_id=&hash=` | 없음(slug 공개) | 방문자 SSE 연결(ChatSession) |
| `POST /api/chat/message` | 세션 | 방문자 메시지(레이트리밋, SSE로 응답) |
| `PATCH /api/tenant/slug/` | TenantAgent JWT | Tenant Slug 설정 |
| `PATCH /api/tenant/config/` | TenantAgent JWT | 설정(Provider·HITL·brand·신원검증 등). 임베딩 Provider 변경 시 재임베딩 트리거 |
| `POST /api/tenant/documents/` | TenantAgent JWT | 파일 업로드(PDF·TXT·이미지·Excel) |
| `POST /api/tenant/documents/url` | TenantAgent JWT | 웹 URL(들) 인제스션 |
| `POST /api/tenant/documents/{id}/refetch` | TenantAgent JWT | 웹 Document 재-fetch |
| `GET /api/tenant/documents/graph/search?q=` | TenantAgent JWT | 엔티티 하이브리드 검색 → 서브그래프 |
| `GET /api/tenant/documents/graph/status` | TenantAgent JWT | Graph Freshness |
| `POST /api/tenant/documents/graph/rebuild` | TenantAgent JWT | 엔티티 해소(SAME_AS) 재구축 트리거 |

---

## 9. 테스트

- **단위/통합**: `docker-compose.test.yml`의 `test` 서비스(pytest). **실제 Neo4j·실제 bge-m3**를 사용(결정적). 비결정적 외부 경계인 **LLM 호출만 결정적 Fake로 교체**합니다(`apps/agent/llm` 경계 + conftest Fake) — 외부 모델 판단이 아니라 우리 코드 동작을 검증.
  - **실행**: `./scripts/test.ps1` (PowerShell) 또는 `bash scripts/test.sh` — 호스트 `backend/`를 마운트해 코드 변경을 즉시 반영하고, **종료 시 테스트 전용 인프라(Neo4j·OCR·ollama 등 GPU 포함)를 자동 `stop`** 하여 VRAM/메모리를 돌려줍니다(다음 실행은 `start`로 빠르게 재개). 인자로 특정 테스트 경로를 넘길 수 있습니다(예: `bash scripts/test.sh tests/test_rag.py`).
- **E2E**: Playwright. 챗 LLM은 OpenAI 호환 **Fake LLM 서비스**(`fake_llm/`)로 결정화합니다.
- 인제스션·추출 프롬프트의 실제 타당성은 실제 OpenRouter로 bring-up 검증합니다.

---

## 10. 설계 결정(ADR)

- `0001` SSE + Redis pub/sub
- `0003` iframe 임베드 / ~~`0004` 서버사이드 EmbedToken~~ (0011로 supersede)
- `0005` Docker Compose 인프라
- **`0007` GraphRAG(Neo4j)가 2-step 벡터 RAG를 대체** (pgvector ADR-0002 supersede)
- **`0008` 증분 인제스션 + 배치 Community 재구축**
- **`0009` 깨진 추출(Garbled)은 LLM 정제가 아니라 OCR 재추출**
- **`0010` Entity 정체성은 이름이 아니라 맥락 — Mention/Entity 분리 + 비파괴 SAME_AS 동치**
- **`0011` 공개 Tenant Slug URL이 EmbedToken을 대체** + 계층형 Visitor 신원(opt-in HMAC)
- **`0012` Tenant 부담 멀티 Provider(LLM·Embedding) + per-Tenant 가변차원 인덱스 + 재임베딩 재구축**
- **`0013` 어드민 인증 access/refresh 토큰**
- **`0014` 어드민 HTTP 클라이언트 OpenAPI(orval) 코드젠 + 전체 TS 전환**
- **`0015` oracle 무중단(rolling) 배포 — docker-rollout + expand/contract + GHCR(arm64)** (제안)
- **`0016` Global Search 제거(Community 요약 폐기) — Local + 원문 폴백으로 대체, 엔티티 해소는 잔존**
- **`0017` 어드민 리디자인 — React 유지(Next.js 기각) + Tailwind/shadcn + 중첩 URL 라우트 + 사이드바 셸**
