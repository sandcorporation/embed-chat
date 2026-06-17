---
title: "Admin 멀티스테이지 Dockerfile 추가"
label: done
---

## Parent

PRD: `.scratch/embed-chatbot-platform/PRD-frontend-docker.md`

## What to build

`embed-chat-admin` 레포에 멀티스테이지 Dockerfile을 추가한다. 구조는 issue-13(Widget Dockerfile)과 동일하다. 스테이지 1은 `node:20-alpine`으로 `npm ci` → `npm run build`, 스테이지 2는 `alpine:3.19`에 `dist/`만 복사하고 `cp -r /dist/. /output/` CMD로 종료하는 init 컨테이너.

Admin의 Vite base는 `/admin-ui/`이므로 빌드 산출물은 해당 prefix로 번들된다.

## Acceptance criteria

- [ ] `embed-chat-admin/` 루트에 `Dockerfile`이 존재한다
- [ ] `docker build -t admin-test ../embed-chat-admin`가 오류 없이 완료된다
- [ ] `docker run --rm admin-test ls /dist`에 `index.html`을 포함한 번들 파일이 존재한다
- [ ] 소스 변경 후 재빌드 시 `npm ci` 레이어가 캐시 히트된다
- [ ] `react-router-dom` 등 runtime 의존성이 번들에 포함되어 정상 동작한다

## Blocked by

None - issue-13과 병렬 진행 가능
