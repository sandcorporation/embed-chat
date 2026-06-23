#!/usr/bin/env bash
# oracle(Ampere A1) 무중단 배포 — GitHub Actions deploy job이 SSH로 호출한다(ADR-0015).
#
# 사용법(원격 A1에서): IMAGE_TAG=<git-sha> bash scripts/deploy.sh <git-sha>
#
# 전제(A1 호스트에 1회 준비):
#   - docker + compose v2 + `docker rollout` 플러그인(https://github.com/wowu/docker-rollout)
#   - `docker login ghcr.io`(read:packages PAT) — pull 인증, ~/.docker/config.json에 영속
#   - 이 repo가 $DEPLOY_PATH에 clone돼 있고 워크플로우가 배포 SHA로 checkout함
#   - .env(SECRET_KEY·DB_PASSWORD·Fernet 키·ALLOWED_HOSTS 등) 호스트에 상주(이미지·git 제외)
#   - docker-compose.prod.oracle.yml(이미지 GHCR 참조 + ${IMAGE_TAG} 핀)
#
# 무중단 원리: stateless 앱(api·worker·worker-chat)만 `docker rollout`으로 start-first 교체.
# db·redis·nginx·relay·bridge는 교체하지 않거나 짧은 재시작 허용(이벤트는 outbox/at-least-once
# 라 소비자 순간 단절을 버팀). 마이그레이션은 롤아웃 전에(expand/contract — 옛/새 코드 공존).
set -euo pipefail

GIT_SHA="${1:?usage: deploy.sh <git-sha>}"
export IMAGE_TAG="$GIT_SHA"

COMPOSE_FILE="docker-compose.prod.oracle.yml"
COMPOSE="docker compose -f $COMPOSE_FILE"

echo "▶ pull ($IMAGE_TAG)"
$COMPOSE pull

echo "▶ 데이터스토어 기동(마이그레이션 전제)"
$COMPOSE up -d db redis

echo "▶ migrate + collectstatic (롤아웃 전 — expand/contract)"
$COMPOSE run --rm api python manage.py migrate --noinput
$COMPOSE run --rm api python manage.py collectstatic --noinput

echo "▶ 정적 SPA 갱신(init이 dist를 볼륨에 복사 후 종료)"
$COMPOSE up -d --no-deps widget-init admin-init

# --no-deps: depends_on로 api가 딸려 재생성돼 다운타임 나는 것을 막는다(api는 아래서 롤링).
echo "▶ 인프라·이벤트 소비자 기동/갱신"
$COMPOSE up -d --no-deps nginx relay \
  worker-webhook worker-visitor-bridge worker-console-bridge worker-presence-bridge

echo "▶ 무중단 롤링(start-first → /api/health 통과 → 옛 컨테이너 드레인)"
for svc in api worker worker-chat; do
  docker rollout -f "$COMPOSE_FILE" "$svc"
done

echo "▶ 스모크"
curl -fsS http://localhost/api/health >/dev/null && echo "✔ deploy OK: $IMAGE_TAG"
