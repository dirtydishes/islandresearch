import os
import time

from rq import Connection, Queue, Worker
from redis import Redis


def get_redis() -> Redis:
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    return Redis.from_url(redis_url)


def main() -> None:
    queue_name = os.getenv("QUEUE_NAME", "ingest")
    with Connection(get_redis()):
        worker = Worker([Queue(queue_name)])
        worker.work(with_scheduler=True, burst=False)


if __name__ == "__main__":
    # Simple retry loop until Redis is reachable to keep container healthy on startup.
    for _ in range(10):
        try:
            get_redis().ping()
            break
        except Exception:
            time.sleep(2)
    main()
