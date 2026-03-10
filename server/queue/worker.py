# server/queue/worker.py — ARQ worker configuration
# Start the worker with: arq server.queue.worker.WorkerSettings
# Requires Redis: docker run -p 6379:6379 redis:7-alpine
from arq.connections import RedisSettings


class WorkerSettings:
    """
    ARQ worker configuration.
    Start with: arq server.queue.worker.WorkerSettings
    Requires Redis: docker run -p 6379:6379 redis:7-alpine
    """
    functions = ["server.queue.tasks.evaluate_async"]
    redis_settings = RedisSettings()  # defaults to localhost:6379
    max_jobs = 10
    job_timeout = 60
