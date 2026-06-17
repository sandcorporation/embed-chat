# ADR-0005: Docker + Docker Compose as primary infrastructure

## Status
Accepted

## Context
개발/테스트/배포 환경을 일관되게 관리할 도구가 필요하다. 서비스 구성이 여러 컴포넌트(Django API, Celery worker, PostgreSQL, Redis, Nginx)로 이루어져 있어 로컬 환경 세팅 복잡도가 높다.

## Decision
Docker + Docker Compose를 개발·테스트·배포의 주 인프라로 사용한다.

### Compose 파일 구조 (Base + Override)
- `docker-compose.yml` — 공통 서비스 정의 (PostgreSQL, Redis, 서비스 이름)
- `docker-compose.dev.yml` — 개발 전용 (코드 볼륨 마운트, 핫리로드, 디버그 포트)
- `docker-compose.prod.yml` — 프로덕션 전용 (Nginx 정적 파일 서빙, 리소스 제한, SSL)

### 서비스 목록
| 서비스 | dev | prod |
|--------|-----|------|
| `api` | 코드 볼륨 마운트 | 이미지 빌드 |
| `worker` | 코드 볼륨 마운트 | 이미지 빌드 |
| `db` | PostgreSQL + pgvector | 동일 |
| `redis` | Redis (SSE pub/sub + Celery 브로커) | 동일 |
| `nginx` | 선택적 | Django API 프록시 + 정적 파일 서빙 |
| `widget` | 미포함 (네이티브 npm run dev) | 빌드된 정적 파일을 nginx로 서빙 |
| `admin` | 미포함 (네이티브 npm run dev) | 빌드된 정적 파일을 nginx로 서빙 |

### 비동기 워커
Celery + Redis 조합. Redis는 SSE pub/sub 브로커로 이미 존재하므로 Celery 브로커로 재사용. 처리 대상: 문서 인제스트(PDF/TXT → 임베딩 → pgvector), Visitor Memory 추출.

### 시크릿 관리
`.env` 파일 + `.env.example` 패턴. 실제 `.env`는 `.gitignore`, `.env.example`은 레포에 커밋.

## Consequences
- 모든 개발자가 동일한 환경에서 작업 가능하다.
- 프론트엔드(위젯/어드민)는 개발 시 네이티브 `npm run dev`로 실행하여 파일 변경 감지 성능을 확보한다.
- CI/CD는 추후 결정. 초기에는 서버에서 수동으로 `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d` 실행.
- Docker Swarm/k8s 없이 단일 서버 운영 기준. 수평 확장 시 재검토 필요.
