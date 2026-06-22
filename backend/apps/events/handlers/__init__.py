"""import 시 모든 소비자 핸들러를 레지스트리에 등록한다.

consume_events 커맨드가 이 패키지를 import해 group→handler 매핑을 채운다.
"""
from apps.events.handlers import webhook, visitor_bridge, console_bridge, presence_bridge  # noqa: F401
