# Gunicorn Production Configuration
import os
import multiprocessing

# Bind to localhost/all interfaces on Render dynamic PORT
port = os.environ.get('PORT', '5000')
bind = f"0.0.0.0:{port}"

# Multi-threaded worker setup (highly optimized for ultra-fast performance)
workers = multiprocessing.cpu_count() * 2 + 1
threads = 16
worker_class = "gthread"
worker_connections = 2000

# Timeout options
timeout = 60
keepalive = 15

# Logging settings
accesslog = "logs/gunicorn_access.log"
errorlog = "logs/gunicorn_error.log"
loglevel = "info"

# Security: set secure headers and request limits
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Ensure log directory exists
import os
os.makedirs("logs", exist_ok=True)
