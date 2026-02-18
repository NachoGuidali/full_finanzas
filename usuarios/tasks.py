from celery import shared_task
from django.core.management import call_command

@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def actualizar_cotizaciones_task(self):
    try:
        call_command("actualizar_cotizacion")  # nombre del command SIN .py
        return "ok"
    except Exception as e:
        raise self.retry(exc=e)
