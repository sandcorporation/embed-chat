# 01 — Project foundation & Docker Compose

Status: ready-for-agent

## What to build

백엔드 레포의 기반 구조를 세운다. Django 프로젝트 스켈레톤, Django Ninja 설치, PostgreSQL + pgvector, Redis, Nginx를 Docker Compose(Base + dev override + prod override)로 묶는다. `.env.example`을 커밋하고 실제 `.env`는 `.gitignore`에 추가한다.

로컬에서 `docker compose -f docker-compose.yml -f docker-compose.dev.yml up` 한 번으로 전체 백엔드 스택이 뜨고, Django Ninja의 `/api/health` 엔드포인트가 200을 반환하면 이 슬라이스는 완료다.

## Acceptance criteria

- [ ] `docker-compose.yml` (base), `docker-compose.dev.yml`, `docker-compose.prod.yml` 세 파일 존재
- [ ] 서비스: `api`, `worker`(Celery), `db`(PostgreSQL + pgvector 확장), `redis`, `nginx`
- [ ] `GET /api/health` → `{"status": "ok"}` 반환
- [ ] `.env.example`에 필요한 모든 환경 변수 키가 주석과 함께 나열됨
- [ ] `.env`는 `.gitignore`에 포함됨
- [ ] `docker compose -f docker-compose.yml -f docker-compose.dev.yml up` 으로 오류 없이 전체 스택 기동

## Blocked by

None — can start immediately
