---
title: "Widget 멀티스테이지 Dockerfile 추가"
label: done
---

## Parent

PRD: `.scratch/embed-chatbot-platform/PRD-frontend-docker.md`

## What to build

`embed-chat-widget` 레포에 멀티스테이지 Dockerfile을 추가한다. 스테이지 1은 `node:20-alpine`으로 의존성 레이어와 소스 레이어를 분리하여 `npm ci` → `npm run build`를 실행한다. 스테이지 2는 `alpine:3.19` 최소 이미지에 `dist/` 파일만 복사하고, CMD로 `cp -r /dist/. /output/`를 실행하는 one-shot init 컨테이너로 동작한다.

`package*.json`을 소스보다 먼저 복사하여 소스 변경 시 `npm ci` 레이어가 캐시 히트되도록 한다.

## Acceptance criteria

- [ ] `embed-chat-widget/` 루트에 `Dockerfile`이 존재한다
- [ ] `docker build -t widget-test ../embed-chat-widget` (백엔드 레포 기준 실행)가 오류 없이 완료된다
- [ ] 빌드된 이미지를 `docker run --rm widget-test ls /dist`로 확인하면 `index.html`을 포함한 번들 파일이 존재한다
- [ ] 소스 파일만 변경 후 재빌드 시 `npm ci` 단계가 캐시 히트된다 (레이어 순서 검증)
- [ ] `npm run test:run`이 이미지 빌드 결과에 영향을 받지 않는다 (devDependencies는 build stage에서만 사용)

## Blocked by

None - 즉시 시작 가능
