import os
import logging
import json
import time
from typing import Any, Optional

logger = logging.getLogger('redis_service')

class RedisService:
    def __init__(self):
        self._client = None
        self._in_memory_cache = {}
        self._cache_ttls = {}
        self._initialized = False

    @property
    def client(self):
        if not self._initialized:
            self._initialized = True
            redis_url = os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379/0')
            try:
                import redis
                cli = redis.from_url(redis_url, socket_timeout=2, socket_connect_timeout=2)
                cli.ping()
                self._client = cli
                logger.info(f"Redis connection established successfully ({redis_url})")
            except Exception as e:
                logger.warning(f"Redis unavailable ({e}). Using thread-safe in-memory fallback cache.")
                self._client = None
        return self._client

    def is_available(self) -> bool:
        return self.client is not None

    def get(self, key: str) -> Optional[Any]:
        cli = self.client
        if cli:
            try:
                val = cli.get(key)
                if val:
                    try:
                        return json.loads(val.decode('utf-8'))
                    except Exception:
                        return val.decode('utf-8')
            except Exception as e:
                logger.warning(f"Redis get failed for {key}: {e}")
                return None
        else:
            # Fallback memory cache
            now = time.time()
            if key in self._cache_ttls and now > self._cache_ttls[key]:
                self._in_memory_cache.pop(key, None)
                self._cache_ttls.pop(key, None)
                return None
            return self._in_memory_cache.get(key)

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = 300) -> bool:
        cli = self.client
        val_str = json.dumps(value) if isinstance(value, (dict, list, bool, int, float)) else str(value)
        if cli:
            try:
                if ttl_seconds:
                    cli.setex(key, ttl_seconds, val_str)
                else:
                    cli.set(key, val_str)
                return True
            except Exception as e:
                logger.warning(f"Redis set failed for {key}: {e}")
                return False
        else:
            self._in_memory_cache[key] = value
            if ttl_seconds:
                self._cache_ttls[key] = time.time() + ttl_seconds
            return True

    def delete(self, key: str) -> bool:
        cli = self.client
        if cli:
            try:
                cli.delete(key)
                return True
            except Exception:
                return False
        else:
            self._in_memory_cache.pop(key, None)
            self._cache_ttls.pop(key, None)
            return True

    def acquire_lock(self, lock_name: str, acquire_timeout: int = 5, lock_timeout: int = 10) -> bool:
        """Acquire a distributed lock using Redis or thread-safe in-memory lock table."""
        cli = self.client
        lock_key = f"lock:{lock_name}"
        if cli:
            try:
                end = time.time() + acquire_timeout
                while time.time() < end:
                    if cli.set(lock_key, "1", nx=True, ex=lock_timeout):
                        return True
                    time.sleep(0.05)
                return False
            except Exception:
                pass
        
        # Thread-safe in-memory lock fallback
        import threading
        if not hasattr(self, '_mem_lock'):
            self._mem_lock = threading.Lock()
            self._active_mem_locks = {}

        end_t = time.time() + acquire_timeout
        while time.time() < end_t:
            with self._mem_lock:
                now = time.time()
                # Clean expired locks
                expired = [k for k, exp in self._active_mem_locks.items() if now > exp]
                for k in expired:
                    self._active_mem_locks.pop(k, None)

                if lock_key not in self._active_mem_locks:
                    self._active_mem_locks[lock_key] = now + lock_timeout
                    return True
            time.sleep(0.02)
        return False

    def release_lock(self, lock_name: str):
        cli = self.client
        lock_key = f"lock:{lock_name}"
        if cli:
            try:
                cli.delete(lock_key)
            except Exception:
                pass

        if hasattr(self, '_mem_lock'):
            with self._mem_lock:
                self._active_mem_locks.pop(lock_key, None)

redis_service = RedisService()
