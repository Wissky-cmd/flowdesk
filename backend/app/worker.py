from celery import Celery

from .config import settings
from .job_runtime import execute_job

celery = Celery('flowdesk', broker=settings.broker_url)
celery.conf.update(
    task_serializer='json', accept_content=['json'], result_serializer='json', task_ignore_result=True,
    task_acks_late=True, task_reject_on_worker_lost=False, worker_prefetch_multiplier=1,
    task_soft_time_limit=90, task_time_limit=110, broker_connection_timeout=2,
    broker_transport_options={'socket_connect_timeout': 2, 'socket_timeout': 2, 'visibility_timeout': 120},
    task_publish_retry=False,
)


@celery.task(name='flowdesk.export', max_retries=0)
def export_csv(job_id):
    execute_job(job_id)
