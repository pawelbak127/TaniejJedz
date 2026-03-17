"""Dramatiq actor: flush analytics buffer from Redis to PG.

Runs periodically (every 10s via dramatiq-crontab or external scheduler).
Can also be triggered manually.
"""

import dramatiq

from app.config import get_settings
from app.services.analytics_service import AnalyticsFlusher


@dramatiq.actor(queue_name="background", max_retries=1)
def flush_analytics(batch_size: int = 500) -> None:
    """Pop buffered analytics events from Redis, INSERT into PG."""
    settings = get_settings()
    flusher = AnalyticsFlusher(redis_url=settings.redis_url)
    try:
        count = flusher.flush(batch_size=batch_size)
        if count > 0:
            import logging
            logging.getLogger(__name__).info(f"Flushed {count} analytics events to PG.")
    finally:
        flusher.close()
