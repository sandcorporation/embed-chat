# ADR-0003: iframe embed over script tag injection

## Status
Accepted

## Context
Tenant 사이트에 챗봇 위젯을 삽입하는 방법으로 `<iframe>`과 `<script>` 태그 방식 중 선택해야 한다.

## Decision
`<iframe src="{EmbedToken URL}" />` 방식을 사용한다.

## Consequences
- CSS/JS가 완전히 격리되어 Tenant 사이트와의 스타일 충돌이 없다.
- EmbedToken이 iframe src URL에 자연스럽게 담기므로 별도 전달 메커니즘이 불필요하다.
- Tenant 통합 코드가 한 줄로 단순하다.
- 부모 페이지와 양방향 통신이 필요한 경우 `postMessage`를 써야 하는 제약이 있으나, 현재 요구사항에는 해당하지 않는다.
