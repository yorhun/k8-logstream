import os
import time
import socket
from datetime import datetime, timezone
from urllib.parse import urlparse, unquote

import redis
from opensearchpy import OpenSearch, helpers

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
OPENSEARCH_URL = os.environ.get("OPENSEARCH_URL", "http://localhost:9200")
STREAM_NAME = os.environ.get("STREAM_NAME", "logs:raw")
GROUP_NAME = "logstream-cg"
CONSUMER_NAME = socket.gethostname()  # unique per pod replica


def connect_redis(url: str) -> redis.Redis:
    while True:
        try:
            r = redis.from_url(url, decode_responses=True)
            r.ping()
            print("Connected to Redis")
            return r
        except Exception as exc:
            print(f"Redis not ready: {exc} — retrying in 2s")
            time.sleep(2)


def connect_opensearch(url: str) -> OpenSearch:
    parsed = urlparse(url)
    host = parsed.hostname
    port = parsed.port or 9200
    http_auth = None
    if parsed.username and parsed.password:
        http_auth = (parsed.username, unquote(parsed.password))
    use_ssl = parsed.scheme == "https"
    client = OpenSearch(
        hosts=[{"host": host, "port": port}],
        http_auth=http_auth,
        http_compress=True,
        use_ssl=use_ssl,
        verify_certs=False,
        ssl_show_warn=False,
    )
    while True:
        try:
            if client.ping():
                print("Connected to OpenSearch")
                return client
            else:
                print(f"OpenSearch ping returned False (auth failure?) — retrying in 2s")
        except Exception as exc:
            print(f"OpenSearch not ready: {exc} — retrying in 2s")
        time.sleep(2)


def _bulk_index(client: OpenSearch, fields_list: list, *, is_duplicate: bool, processor_pod: str) -> None:
    now = datetime.now(timezone.utc)
    index_name = f"logs-{now.strftime('%Y.%m.%d')}"
    actions = [
        {
            "_index": index_name,
            "_source": {
                **fields,
                "@timestamp": now.isoformat(),
                "processed_at": now.isoformat(),
                "is_duplicate": is_duplicate,
                "processor_pod": processor_pod,
            },
        }
        for fields in fields_list
    ]
    helpers.bulk(client, actions, raise_on_error=False)


def main():
    r = connect_redis(REDIS_URL)
    os_client = connect_opensearch(OPENSEARCH_URL)

    try:
        r.xgroup_create(STREAM_NAME, GROUP_NAME, id="0", mkstream=True)
        print(f"Consumer group '{GROUP_NAME}' created")
    except redis.exceptions.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise
        print(f"Consumer group '{GROUP_NAME}' already exists")

    while True:
        messages = r.xreadgroup(
            GROUP_NAME, CONSUMER_NAME, {STREAM_NAME: ">"}, count=100, block=1000
        )
        if not messages:
            continue

        entries = messages[0][1]  # [(stream_id, {fields}), ...]

        # Batch dedup check via pipeline — one round-trip to Redis
        pipe = r.pipeline()
        for _, fields in entries:
            pipe.sismember("logs:processed", fields.get("log_id"))
        seen_flags = pipe.execute()

        new_entries = []   # (msg_id, fields) for unseen messages
        dup_entries = []   # (msg_id, fields) for duplicates

        for (msg_id, fields), is_dup in zip(entries, seen_flags):
            if is_dup:
                dup_entries.append((msg_id, fields))
            else:
                new_entries.append((msg_id, fields))

        # Index duplicates with is_duplicate=True, then ACK
        if dup_entries:
            _bulk_index(os_client, [f for _, f in dup_entries], is_duplicate=True, processor_pod=CONSUMER_NAME)
            r.xack(STREAM_NAME, GROUP_NAME, *[mid for mid, _ in dup_entries])

        # Index new messages, mark in dedup set, then ACK
        if new_entries:
            _bulk_index(os_client, [f for _, f in new_entries], is_duplicate=False, processor_pod=CONSUMER_NAME)
            pipe = r.pipeline()
            for _, fields in new_entries:
                pipe.sadd("logs:processed", fields["log_id"])
            pipe.xack(STREAM_NAME, GROUP_NAME, *[mid for mid, _ in new_entries])
            pipe.execute()


if __name__ == "__main__":
    main()
