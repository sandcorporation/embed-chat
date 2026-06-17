---
title: Frontend Docker Compose Integration
label: ready-for-agent
---

## Problem Statement

위젯(embed-chat-widget)과 어드민(embed-chat-admin) 프론트엔드 레포에 Dockerfile이 없고, `docker-compose.prod.yml`이 `widget_dist`·`admin_dist` named volume을 nginx에 마운트하도록 선언되어 있지만 이 볼륨을 채워주는 서비스가 존재하지 않는다. 결과적으로 `docker compose ... up`으로 프로덕션 스택을 올리면 nginx가 빈 디렉토리를 서빙한다.

개발 환경에서 프론트엔드는 `npm run dev`로 네이티브 실행하기로 결정되어 있어(ADR C) Docker 서비스가 불필요하지만, 프로덕션 배포 경로가 전혀 정의되어 있지 않은 상태다.

## Solution

각 프론트엔드 레포에 멀티스테이지 Dockerfile을 추가한다. 빌드 스테이지는 `node:20-alpine`으로 `npm run build`를 실행하고, 최종 스테이지는 `alpine`으로 `dist/` 파일만 포함한다. `docker-compose.prod.yml`에 "init 컨테이너" 패턴으로 `widget-init`, `admin-init` 서비스를 추가하여 named volume에 정적 파일을 복사한 뒤 종료하고, nginx는 이 두 서비스가 성공적으로 완료된 후에만 시작되도록 `depends_on` 조건을 설정한다. 개발 환경(`docker-compose.dev.yml`)은 변경하지 않는다.

## User Stories

1. As an Operator, I want to start the entire production stack with a single `docker compose` command, so that I can deploy without manually building frontend assets.
2. As an Operator, I want the widget to be accessible at `/embed/` in production, so that Tenant embed URLs work correctly.
3. As an Operator, I want the admin UI to be accessible at `/admin-ui/` in production, so that Tenant and Operator can manage settings via the web.
4. As a developer, I want the frontend to remain runnable with `npm run dev` locally without Docker, so that my inner-loop iteration stays fast.
5. As a developer, I want `docker compose -f docker-compose.yml -f docker-compose.prod.yml build` to produce reproducible images, so that CI/CD can cache layers consistently.
6. As a developer, I want nginx to only start after the static files are ready, so that the service never starts serving 404s during initialization.
7. As a developer, I want the Dockerfile to use `npm ci` (not `npm install`), so that the lockfile is respected and builds are deterministic.
8. As a developer, I want the node_modules layer to be cached separately from source code, so that incremental rebuilds are fast when only source files change.

## Implementation Decisions

### Dockerfile pattern (widget and admin, identical structure)

멀티스테이지 빌드. 스테이지 1: `node:20-alpine`에서 `package*.json` 복사 → `npm ci` → 소스 복사 → `npm run build`. 스테이지 2: `alpine:3.19` (최소 이미지)에 `dist/`만 복사. CMD는 `cp -r /dist/. /output/` — 볼륨에 파일을 복사하고 즉시 종료하는 one-shot 컨테이너.

- Widget Vite base: `/embed/` → dist 결과물은 `/embed/` prefix로 번들됨
- Admin Vite base: `/admin-ui/` → dist 결과물은 `/admin-ui/` prefix로 번들됨

### docker-compose.prod.yml 변경

`widget-init`, `admin-init` 두 서비스를 추가한다.

```yaml
# 결정을 인코딩한 프로토타입 스니펫 (실제 구현 시 경로는 맥락에 따라 조정)
widget-init:
  build:
    context: ../embed-chat-widget
  volumes:
    - widget_dist:/output
  # CMD가 cp -r /dist/. /output/ 이므로 command 오버라이드 불필요

nginx:
  depends_on:
    widget-init:
      condition: service_completed_successfully
    admin-init:
      condition: service_completed_successfully
    api:
      condition: service_started
```

- `service_completed_successfully` 조건: Docker Compose v2.1+ 기능. exit code 0으로 종료한 경우에만 nginx 시작.
- `widget_dist`, `admin_dist` 볼륨 선언은 base `docker-compose.yml`에 이미 존재.

### nginx.conf — 변경 없음

기존 설정이 이미 올바르다:
- `/embed/` → `alias /app/widget/; try_files $uri /embed/index.html;`
- `/admin-ui/` → `alias /app/admin/; try_files $uri /admin-ui/index.html;`

SPA 폴백 라우팅도 포함되어 있어 추가 수정 불필요.

### 개발 환경

`docker-compose.dev.yml` 변경 없음. 개발 시 프론트엔드는 기존대로:
- Widget: `npm run dev` (포트 5173, `/api` → `localhost:8000` 프록시)
- Admin: `npm run dev` (포트 5174, `/api` → `localhost:8000` 프록시)

## Testing Decisions

이 기능은 인프라이므로 unit/component 테스트보다 **smoke 검증**이 적합하다.

- **검증 방법**: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d` 실행 후:
  - `curl -s -o /dev/null -w "%{http_code}" http://localhost/embed/` → 200
  - `curl -s -o /dev/null -w "%{http_code}" http://localhost/admin-ui/` → 200
  - `curl -s -o /dev/null -w "%{http_code}" http://localhost/api/health` → 200 (있다면)
- **레이어 캐시 검증**: 소스만 변경 후 재빌드 시 `npm ci` 레이어가 캐시 히트되는지 확인
- **init 컨테이너 완료 순서**: nginx 로그에 에러 없이 정상 기동되는지 확인

자동화 테스트(vitest 등)는 Dockerfile/Compose 변경에 대해 작성하지 않는다 — 해당 계층은 실제 Docker 런타임 없이 테스트 불가능하며 기존 프론트엔드 단위 테스트(widget 9개, admin 25개)가 이미 컴포넌트 동작을 보장한다.

## Out of Scope

- CI/CD 파이프라인 통합 (별도 이슈)
- HTTPS/TLS 종단 (별도 이슈)
- Widget/Admin 핫리로드(HMR)를 Docker 내에서 지원하는 개발 모드 컨테이너 (결정: dev는 native)
- CDN 배포 또는 S3 정적 호스팅

## Further Notes

- 두 프론트엔드 레포(`embed-chat-widget`, `embed-chat-admin`)가 백엔드 레포(`embed-chat`)와 별도 디렉토리에 있으므로 `build.context`에 상대 경로(`../embed-chat-widget`)를 사용한다. `docker compose`는 `docker-compose.yml` 위치 기준으로 context를 해석한다.
- `service_completed_successfully` 조건은 Docker Compose v2.4+ (Docker Desktop 4.x 이상)에서 지원된다. 이보다 낮은 환경에서는 healthcheck 대신 `restart: on-failure`로 폴백할 수 있으나 권장하지 않는다.
- 볼륨에 파일 복사 후 init 컨테이너가 종료되므로 `docker compose down` 시 `--volumes` 플래그 없이는 캐시된 빌드 산출물이 유지된다. 프로덕션 재배포 시 `docker compose down -v && docker compose up --build`로 볼륨을 초기화해야 최신 빌드가 반영된다.
