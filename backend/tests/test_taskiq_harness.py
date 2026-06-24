"""taskiq 테스트 하네스 — InMemoryBroker가 task를 인라인 실행하는지 검증(issue 190).

전면 async 개편(ADR-0022)의 토대. 이후 chat 태스크 테스트가 이 하네스 위에서 돈다.
"""
from config.taskiq_broker import broker


@broker.task
async def _echo(x: str) -> str:
    return x


async def test_taskiq_inmemory_executes_inline():
    """TASKIQ_INMEMORY=1이면 kiq가 인라인 실행되고 결과를 회수할 수 있다."""
    sent = await _echo.kiq("ping")
    result = await sent.wait_result(timeout=5)
    assert result.return_value == "ping"
