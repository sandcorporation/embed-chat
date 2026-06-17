---
title: "docker-compose.prod.yml 프론트엔드 init 컨테이너 통합"
label: done
---

## Parent

PRD: `.scratch/embed-chatbot-platform/PRD-frontend-docker.md`

## What to build

`docker-compose.prod.yml`에 `widget-init`과 `admin-init` 두 서비스를 추가하고, nginx의 `depends_on`을 갱신하여 두 init 컨테이너가 성공적으로 종료된 후에만 nginx가 기동되도록 한다.

init 컨테이너는 각 프론트엔드 Dockerfile로 빌드된 이미지를 실행하며, named volume(`widget_dist`, `admin_dist`)을 `/output`에 마운트받아 정적 파일을 복사한 뒤 exit 0으로 종료한다. nginx는 기존과 동일하게 이 볼륨을 읽어 `/embed/`, `/admin-ui/` 경로로 서빙한다.

결정이 인코딩된 스니펫 (프로토타입에서):
```yaml
widget-init:
  build:
    context: ../embed-chat-widget
  volumes:
    - widget_dist:/output

nginx:
  depends_on:
    widget-init:
      condition: service_completed_successfully
    admin-init:
      condition: service_completed_successfully
    api:
      condition: service_started
```

## Acceptance criteria

- [ ] `docker-compose.prod.yml`에 `widget-init`, `admin-init` 서비스가 추가된다
- [ ] 각 init 서비스는 해당 프론트엔드 Dockerfile로 빌드되고, `widget_dist`/`admin_dist` 볼륨을 `/output`에 마운트한다
- [ ] nginx `depends_on`에 두 init 서비스가 `condition: service_completed_successfully`로 추가된다
- [ ] `docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d` 실행 후 `curl http://localhost/embed/`가 HTTP 200을 반환한다
- [ ] `curl http://localhost/admin-ui/`가 HTTP 200을 반환한다
- [ ] `curl http://localhost/api/`가 정상 응답한다 (백엔드 통합 깨지지 않음)
- [ ] init 컨테이너 두 개는 파일 복사 후 `Exited (0)` 상태가 된다

## Blocked by

- issue-13: Widget 멀티스테이지 Dockerfile
- issue-14: Admin 멀티스테이지 Dockerfile
