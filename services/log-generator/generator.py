import os
import time
import uuid
import random
from collections import deque
from datetime import datetime, timezone

import redis

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
LOG_RATE = float(os.environ.get("LOG_RATE", "10"))  # messages per second
STREAM_NAME = "logs:raw"

LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
SERVICES = ["auth-service", "payment-service", "inventory-service", "api-gateway", "user-service"]

MESSAGES = {
    "DEBUG": [
        "Cache hit; skipping DB query.",
        "Acquired DB connection from pool.",
        lambda: f"Parsed request headers in {random.randint(1, 15)}ms.",
        lambda: f"Query executed in {random.randint(2, 50)}ms.",
        "Entering retry loop for downstream call.",
        lambda: f"Session token validated in {random.randint(1, 10)}ms.",
        "Spawning background task for async processing.",
        lambda: f"Request queued; current depth={random.randint(1, 30)}.",
        "Feature flag evaluated: enabled.",
        "Feature flag evaluated: disabled.",
        lambda: f"Deserialized payload in {random.randint(1, 8)}ms.",
        "DB connection returned to pool.",
        lambda: f"Cache TTL refreshed to {random.randint(60, 600)}s.",
        "Outbound HTTP request initiated.",
        lambda: f"Response received in {random.randint(10, 200)}ms.",
    ],
    "INFO": [
        "User login successful.",
        lambda: f"Payment processed for order #{random.randint(10000, 99999)}.",
        "Health check passed.",
        lambda: f"New user registered: user_{random.randint(1000, 9999)}.",
        lambda: f"Order #{random.randint(10000, 99999)} shipped.",
        "Service started successfully.",
        lambda: f"Processed {random.randint(10, 500)} items in batch.",
        "Config reloaded from environment.",
        lambda: f"Cache warmed: {random.randint(100, 2000)} keys loaded.",
        "Scheduled job completed without errors.",
        lambda: f"API request served in {random.randint(20, 300)}ms.",
        "Database migration applied successfully.",
        lambda: f"Inventory updated for SKU-{random.randint(1000, 9999)}.",
        "Rate limiter reset for new window.",
        lambda: f"Webhook delivered to endpoint in {random.randint(50, 400)}ms.",
        "Session created for authenticated user.",
        lambda: f"Exported {random.randint(1, 500)} records to storage.",
        "Token refreshed successfully.",
        lambda: f"Queue depth: {random.randint(0, 200)} messages pending.",
        "Graceful shutdown initiated.",
    ],
    "WARNING": [
        lambda: f"Response latency elevated: {random.randint(500, 2000)}ms.",
        "Retry limit approaching.",
        lambda: f"Disk usage at {random.randint(70, 89)}%.",
        lambda: f"Memory usage above threshold: {random.randint(75, 90)}%.",
        lambda: f"Connection pool at {random.randint(80, 95)}% capacity.",
        "Deprecated API version called; client should upgrade.",
        lambda: f"Cache miss rate elevated: {random.randint(20, 45)}%.",
        "Upstream service returning elevated 4xx rate.",
        lambda: f"Queue depth growing: {random.randint(500, 2000)} messages.",
        "JWT expiry within 5 minutes; proactive refresh triggered.",
        lambda: f"Config value missing, using default: {random.randint(1, 100)}.",
        "Rate limit threshold at 80% — throttling may begin soon.",
        lambda: f"Slow DB query ({random.randint(300, 1500)}ms) on table users.",
        "Circuit breaker half-open; testing upstream availability.",
    ],
    "ERROR": [
        lambda: f"DB connection timed out after {random.randint(3000, 10000)}ms.",
        "Failed to verify JWT.",
        "Payment gateway returned HTTP 502.",
        "Redis XADD failed.",
        lambda: f"Upstream returned HTTP 503 after {random.randint(1, 3)} retries.",
        "Failed to parse response body: unexpected EOF.",
        lambda: f"S3 upload failed for key logs/{random.randint(1000, 9999)}.gz.",
        "Database constraint violation on INSERT.",
        "OAuth token exchange returned 401 Unauthorized.",
        lambda: f"gRPC call failed with DEADLINE_EXCEEDED after {random.randint(2000, 8000)}ms.",
        "Failed to acquire distributed lock.",
        "Message deserialization error: unknown field.",
        lambda: f"Retry budget exhausted after {random.randint(3, 10)} attempts.",
        "Webhook delivery failed; event will be retried.",
        "Config parsing error: invalid JSON in env var.",
    ],
    "CRITICAL": [
        "Circuit breaker OPEN — all calls failing.",
        "DB connection pool exhausted.",
        "Authentication service unreachable.",
        "Data loss risk: write-ahead log full.",
        "Out of memory — pod approaching OOM kill.",
        "Encryption key unavailable; all requests rejected.",
        "Persistent volume mount failed; data at risk.",
        "Message broker unreachable; stream processing halted.",
        lambda: f"Cascading failure detected across {random.randint(2, 5)} services.",
    ],
}


def resolve_message(entry) -> str:
    if callable(entry):
        return entry()
    return entry


def new_log() -> dict:
    level = random.choices(LEVELS, weights=[10, 55, 20, 12, 3])[0]
    return {
        "log_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "service": random.choice(SERVICES),
        "message": resolve_message(random.choice(MESSAGES[level])),
        "trace_id": str(uuid.uuid4()),
    }


def main():
    r = redis.from_url(REDIS_URL, decode_responses=True)
    recent: deque = deque(maxlen=50)

    batch_end = 0.0
    delay = 3.0 / random.randint(200, 1500)

    while True:
        now = time.monotonic()
        if now >= batch_end:
            # Alternate between quiet and busy periods to drive visible autoscaling
            if random.random() < 0.35:
                target_count = random.randint(25, 50)   # quiet
            else:
                target_count = random.randint(50, 250)  # busy
            delay = 3.0 / target_count
            batch_end = now + 3.0

        # 15% chance to re-send a recent message as a duplicate
        if recent and random.random() < 0.15:
            log = random.choice(list(recent))
        else:
            log = new_log()
            recent.append(log)

        r.xadd(STREAM_NAME, log)
        time.sleep(delay)


if __name__ == "__main__":
    main()
