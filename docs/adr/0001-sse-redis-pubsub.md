# ADR-0001: SSE + Redis pub/sub for real-time streaming

## Status
Accepted

## Context
LLM 응답을 Visitor에게 스트리밍으로 전달해야 한다. Django 백엔드가 여러 인스턴스로 수평 확장될 때, SSE 연결을 보유한 인스턴스와 LLM 응답을 처리하는 인스턴스가 다를 수 있다.

## Decision
실시간 통신은 SSE(Server-Sent Events)로 구현하고, 인스턴스 간 이벤트 전달은 Redis pub/sub으로 브리지한다.

- Visitor → Django: 일반 HTTP POST
- Django → Visitor: SSE 스트림
- 인스턴스 간: Redis pub/sub (ChatSession ID 기준 채널)

## Consequences
- WebSocket(Django Channels + Redis Channel Layer)에 비해 단방향이지만, 챗봇 패턴에는 충분하다.
- Redis는 이미 인프라에 존재하므로 추가 운영 부담이 없다.
- 수평 확장 시 SSE 연결 인스턴스와 LLM 처리 인스턴스가 달라도 정상 동작한다.
