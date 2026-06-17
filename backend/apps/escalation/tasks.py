from config.celery import app


@app.task(bind=True, max_retries=3)
def dispatch_webhook_task(self, escalation_id: str) -> None:
    from apps.escalation.webhook import dispatch_webhook

    try:
        dispatch_webhook(escalation_id)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)
