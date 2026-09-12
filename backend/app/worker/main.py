"""RQ worker entry point. Run with: python -m app.worker.main"""
import logging
from redis import Redis
from rq import Worker, Queue
from app.config import settings
from app.ingestion import qdrant_mgr

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


def main():
    qdrant_mgr.ensure_collection()
    redis_conn = Redis.from_url(settings.REDIS_URL)
    queue = Queue("ingestion", connection=redis_conn)
    worker = Worker([queue], connection=redis_conn)
    log.info("Worker started, listening on queue 'ingestion'")
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
