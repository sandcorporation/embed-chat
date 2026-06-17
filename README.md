# Embed Chat — Operator Guide

Embed Chat는 타사 웹사이트에 챗봇을 삽입할 수 있는 멀티테넌트 SaaS 플랫폼입니다. Operator(운영자)는 플랫폼 전체를 관리하고 Tenant(고객사)를 생성합니다.

## 구성 요소

| 컴포넌트 | 역할 |
|----------|------|
| Django API (`/api/`) | 인증, 채팅, RAG, 메모리 |
| Celery Worker | 문서 임베딩, 메모리 추출 비동기 처리 |
| PostgreSQL + pgvector | 데이터 저장 + 벡터 검색 |
| Redis | SSE pub/sub + Celery 브로커 |
| Widget (`/embed/`) | Visitor용 채팅 위젯 (React) |
| Admin UI (`/admin-ui/`) | Tenant·Operator 관리 화면 (React) |
| Nginx | 리버스 프록시, 정적 파일 서빙 |

## 빠른 시작 (개발)

```bash
# 1. 환경 변수 설정
cp .env.example .env
# .env에서 DB, Redis, OpenRouter API 키 등을 입력

# 2. 인프라 기동 (DB + Redis)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up db redis -d

# 3. Python 의존성 설치 및 마이그레이션
pip install -r requirements.txt
python manage.py migrate

# 4. Operator 계정 생성
python manage.py createsuperuser

# 5. API 서버 + Celery 기동
python manage.py runserver
celery -A config.celery worker --loglevel=debug

# 6. 프론트엔드 (별도 터미널, 별도 레포)
# cd ../embed-chat-widget && npm run dev   # 위젯: http://localhost:5173
# cd ../embed-chat-admin  && npm run dev   # 어드민: http://localhost:5174
```

## 프로덕션 배포

```bash
cp .env.example .env
# .env 설정 (DB_HOST=db, REDIS_URL=redis://redis:6379/0 등)

docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d

# 최초 1회: 마이그레이션 + Operator 계정 생성
docker compose exec api python manage.py migrate
docker compose exec api python manage.py createsuperuser
```

배포 후 접근 경로:

| 경로 | 용도 |
|------|------|
| `http://your-domain/admin-ui/` | Operator·Tenant 관리 화면 |
| `http://your-domain/api/docs` | Django Ninja 자동 생성 API 문서 |
| `http://your-domain/embed/?token=...` | Visitor 챗봇 위젯 |

> **재배포 시 주의**: 정적 파일 볼륨 초기화가 필요하면 `docker compose down -v` 후 재기동하세요.

## 환경 변수 (.env)

| 변수 | 설명 | 예시 |
|------|------|------|
| `SECRET_KEY` | Django 서명 키 | 임의의 긴 문자열 |
| `DB_NAME / DB_USER / DB_PASSWORD / DB_HOST / DB_PORT` | PostgreSQL 접속 정보 | |
| `REDIS_URL` | Redis URL | `redis://redis:6379/0` |
| `OPEN_ROUTER_API_KEY` | OpenRouter API 키 | `sk-or-v1-...` |
| `OPEN_ROUTER_DEFAULT_MODEL` | 기본 LLM 모델 | `openrouter/owl-alpha` |
| `OPEN_ROUTER_BASE_URL` | OpenRouter endpoint | `https://openrouter.ai/api/v1` |
| `EMBED_TOKEN_TTL_SECONDS` | EmbedToken 만료 시간(초) | `300` |
| `DEBUG` | 디버그 모드 | `False` (운영) |

## Tenant 관리

Operator Admin UI(`/admin-ui/`)에서 Operator 계정으로 로그인 후:

1. **Tenant 추가** → 고객사 이름 입력 → `TENANT_KEY` 발급 (한 번만 표시됨)
2. `TENANT_KEY`를 해당 고객사에 안전하게 전달
3. Tenant 상태를 **활성 / 정지** 전환 가능
4. 필요 시 Tenant 삭제

> `TENANT_KEY`는 생성 직후에만 평문으로 표시됩니다. DB에는 해시만 저장되므로 분실 시 재발급 필요.

## API 개요

전체 API 문서: `GET /api/docs`

| 엔드포인트 | 인증 | 용도 |
|------------|------|------|
| `POST /api/operator/auth/login` | 없음 | Operator JWT 발급 |
| `POST /api/operator/tenants/` | Operator JWT | Tenant 생성 |
| `GET /api/operator/tenants/` | Operator JWT | Tenant 목록 |
| `PATCH /api/operator/tenants/{id}/suspend` | Operator JWT | Tenant 정지 |
| `DELETE /api/operator/tenants/{id}` | Operator JWT | Tenant 삭제 |

## 아키텍처 메모

- **SSE + Redis pub/sub**: 여러 API 인스턴스가 있어도 `session:{id}` 채널을 통해 스트리밍 보장
- **EmbedToken**: Tenant 백엔드에서 서명 후 iframe src에 전달 → TENANT_KEY가 브라우저에 노출되지 않음
- **벡터 검색**: pgvector `L2Distance`, 임베딩 모델 `BAAI/bge-small-en-v1.5` (로컬, API 불필요)
