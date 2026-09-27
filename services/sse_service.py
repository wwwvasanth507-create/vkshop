import json
import logging
import time
import os
from queue import Queue, Empty

logger = logging.getLogger('sse_service')

# In-memory subscription registries per worker process
_subscribers = set()

def register_sse_subscriber():
    q = Queue(maxsize=100)
    _subscribers.add(q)
    logger.info(f"[SSE] New subscriber registered (active process subscribers: {len(_subscribers)})")
    return q

def unregister_sse_subscriber(q):
    _subscribers.discard(q)
    logger.info(f"[SSE] Subscriber unregistered (active process subscribers: {len(_subscribers)})")

def publish_admin_event(event_name, data):
    """
    Broadcasts a live SSE event to all connected admin clients.
    Uses Redis Pub/Sub if available so events propagate across multiple Gunicorn workers.
    Also notifies local in-memory subscribers.
    """
    payload = {
        'event': event_name,
        'data': data or {},
        'timestamp': time.time()
    }
    json_payload = json.dumps(payload)

    # 1. Publish to Redis Pub/Sub if Redis is available
    from config import Config
    redis_url = getattr(Config, 'REDIS_URL', None) or os.environ.get('REDIS_URL')
    if redis_url:
        try:
            import redis
            r = redis.from_url(redis_url, socket_timeout=1)
            r.publish('vkshop_admin_sse_events', json_payload)
            logger.info(f"[SSE-REDIS] Published event '{event_name}' via Redis Pub/Sub.")
        except Exception as err:
            logger.warning(f"[SSE-REDIS] Redis Pub/Sub publish failed (fallback to in-memory): {err}")

    # 2. Local in-memory broadcast
    _broadcast_local_payload(json_payload)


def _broadcast_local_payload(json_payload):
    dead_queues = []
    for q in list(_subscribers):
        try:
            q.put_nowait(json_payload)
        except Exception:
            dead_queues.append(q)

    for dq in dead_queues:
        _subscribers.discard(dq)


def listen_redis_sse_events_loop(app):
    """
    Background listener loop subscribing to Redis channel 'vkshop_admin_sse_events'.
    Relays cross-worker events to local process in-memory subscribers.
    """
    redis_url = app.config.get('REDIS_URL') or os.environ.get('REDIS_URL')
    if not redis_url:
        return

    import redis
    try:
        r = redis.from_url(redis_url)
        pubsub = r.pubsub()
        pubsub.subscribe('vkshop_admin_sse_events')
        logger.info("[SSE-REDIS] Subscribed to Redis channel 'vkshop_admin_sse_events'")

        for item in pubsub.listen():
            if item['type'] == 'message':
                data_str = item['data']
                if isinstance(data_str, bytes):
                    data_str = data_str.decode('utf-8')
                _broadcast_local_payload(data_str)
    except Exception as err:
        logger.warning(f"[SSE-REDIS] Listener loop stopped: {err}")
