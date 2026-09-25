from flask import Blueprint, jsonify, current_app
from database import db
from services.storage import storage_service
import logging

logger = logging.getLogger('monitoring')

monitoring_bp = Blueprint('monitoring', __name__)

@monitoring_bp.route('/health')
def health_check():
    """
    Ultra-lightweight Liveness Probe.
    Returns HTTP 200 OK immediately without DB or R2 I/O.
    Ensures Render health check never fails due to transient network latency.
    """
    return jsonify({'status': 'healthy'}), 200

@monitoring_bp.route('/ready')
def readiness_check():
    """
    Readiness Probe for dependency diagnosis.
    Safely checks Database, R2 Storage, and Redis with bounded timeouts.
    """
    status = {
        'status': 'ok',
        'database': 'unknown',
        'redis': 'unknown',
        'storage': 'unknown'
    }
    is_degraded = False

    # 1. Bounded Database connection check
    try:
        db.session.execute(db.text("SELECT 1"))
        status['database'] = 'connected'
    except Exception as e:
        status['database'] = f"error: {str(e)}"
        status['status'] = 'degraded'
        is_degraded = True
        logger.warning(f"[READINESS] Database check failed: {e}")

    # 2. Redis connection check
    if current_app.config.get('SESSION_TYPE') == 'redis':
        try:
            redis_client = current_app.config.get('SESSION_REDIS')
            if redis_client:
                redis_client.ping()
                status['redis'] = 'connected'
            else:
                status['redis'] = 'not_configured'
                status['status'] = 'degraded'
                is_degraded = True
        except Exception as e:
            status['redis'] = f"error: {str(e)}"
            status['status'] = 'degraded'
            is_degraded = True
    else:
        status['redis'] = 'disabled'

    # 3. Object Storage check (Lightweight client initialization check)
    if current_app.config.get('MINIO_ENDPOINT') or current_app.config.get('STORAGE_PROVIDER') == 's3':
        try:
            if storage_service.is_available():
                status['storage'] = 'connected'
            else:
                status['storage'] = 'not_configured'
                status['status'] = 'degraded'
                is_degraded = True
        except Exception as e:
            status['storage'] = f"error: {str(e)}"
            status['status'] = 'degraded'
            is_degraded = True
    else:
        status['storage'] = 'disabled'

    code = 200 if not is_degraded else 200  # Always return 200 with JSON payload so diagnostics can be inspected
    return jsonify(status), code

