from celery import Celery
from celery.schedules import crontab

celery_app = Celery("orders", broker="redis://cache:6379/1")
celery_app.conf.beat_schedule = {
    "nightly-settlement": {"task": "app.tasks.settle_orders", "schedule": crontab(hour=1, minute=30)},
}


@celery_app.task
def settle_orders() -> None:
    """Nightly settlement export."""
