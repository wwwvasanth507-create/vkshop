# Gunicorn Production Configuration
import os

# Bind to localhost/all interfaces on Render dynamic PORT
port = os.environ.get('PORT', '5000')
bind = f"0.0.0.0:{port}"

# Bounded worker & thread count optimized for Render container limits (512MB RAM / 1 CPU)
workers = int(os.environ.get('WEB_CONCURRENCY', os.environ.get('GUNICORN_WORKERS', '2')))
threads = int(os.environ.get('GUNICORN_THREADS', '4'))
worker_class = "gthread"
worker_connections = 1000

# Worker lifecycle & recycling settings (prevents memory leaks over time)
max_requests = int(os.environ.get('GUNICORN_MAX_REQUESTS', '500'))
max_requests_jitter = int(os.environ.get('GUNICORN_MAX_REQUESTS_JITTER', '100'))

# Bounded Timeout options
timeout = 60
graceful_timeout = 30
keepalive = 5

# Logging settings - stream to stdout/stderr for Render log aggregator
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get('GUNICORN_LOG_LEVEL', 'info').lower()

# Security & Request header size limits
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Worker Lifecycle Logging Hooks
def on_starting(server):
    server.log.info("[WORKER_BOOT] Gunicorn Master process starting (workers=%s, threads=%s, worker_class=%s)", workers, threads, worker_class)

def post_worker_init(worker):
    worker.log.info("[WORKER_BOOT] Worker booted successfully (pid=%s)", worker.pid)

def worker_exit(server, worker):
    server.log.info("[WORKER_EXIT] Worker exited (pid=%s)", worker.pid)

def worker_abort(worker):
    worker.log.warning("[WORKER_ABORT] [WORKER_TIMEOUT] Worker received SIGABRT/timeout alert (pid=%s)", worker.pid)


