import dramatiq

try:
    from dramatiq.brokers.redis import RedisBroker
    from app.config import get_settings
    settings = get_settings()
    broker = RedisBroker(url=settings.redis_url)
    dramatiq.set_broker(broker)
except Exception:
    # Tests without Redis — use stub broker
    from dramatiq.brokers.stub import StubBroker
    broker = StubBroker()
    dramatiq.set_broker(broker)
