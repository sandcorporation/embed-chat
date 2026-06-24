"""ASGI 엔트리포인트 — uvicorn이 서빙한다(전면 async, ADR-0022).

async ninja view + async SSE generator(asse_event_stream)를 이벤트루프에서 네이티브로
돌린다. WSGI(gunicorn/gevent) 경로는 폐기 — gevent 블로킹-허브 병이 원천 제거된다.
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
application = get_asgi_application()
