"""async 배포 엔트리포인트 스모크 (issue 196).

uvicorn(asgi:application)·taskiq 워커(taskiq_worker:broker) 부트스트랩이 import 시점에 깨지지
않음을 잠근다. 테스트는 AsyncClient를 쓰므로 이 엔트리포인트들은 평소 import되지 않아, CI가
배포용 진입점의 import 오류를 놓치는 사각을 메운다.
"""
import os


def test_asgi_application_is_callable():
    """uvicorn이 띄우는 config.asgi:application이 ASGI 콜러블로 import된다."""
    from config.asgi import application

    assert callable(application)


def test_taskiq_worker_bootstrap_registers_chat_task():
    """taskiq 워커가 import하는 config.taskiq_worker가 broker·chat_task를 등록한다."""
    from config import taskiq_worker
    from apps.chat.chat_task import chat_task

    assert taskiq_worker.broker is not None
    # @broker.task로 등록되면 task_name이 부여된다.
    assert getattr(chat_task, "task_name", None)


def test_conn_cleanup_middleware_absent_under_inmemory_broker():
    """테스트(InMemory) 브로커에는 커넥션 정리 미들웨어가 붙지 않는다(django_db 격리 보호)."""
    assert os.environ.get("TASKIQ_INMEMORY") == "1"
    from config import taskiq_worker

    names = [type(m).__name__ for m in taskiq_worker.broker.middlewares]
    assert "DjangoORMConnCleanupMiddleware" not in names
