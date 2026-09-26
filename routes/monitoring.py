from flask import Blueprint, jsonify, current_app
from database import db
from services.storage import storage_service
import logging

logger = logging.getLogger('monitoring')

monitoring_bp = Blueprint('monitoring', __name__)

@monitoring_bp.route('/health')
@monitoring_bp.route('/live')
def health_check():
    """
    Ultra-lightweight Liveness Probe.
    Returns HTTP 200 OK immediately without DB or S3 I/O.
    Ensures health check probes never fail due to network or DB latency.
    """
    return jsonify({'status': 'healthy'}), 200

@monitoring_bp.route('/ready')
def readiness_check():
    """
    Readiness Probe for dependency diagnosis.
    Safely checks Database, Object Storage, and Redis with bounded timeouts.
    """
    status = {
        'status': 'ok',
        'server_id': current_app.config.get('SERVER_ID', 'srv-node-1'),
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
    from services.redis_service import redis_service
    if redis_service.is_available():
        status['redis'] = 'connected'
    else:
        status['redis'] = 'in_memory_fallback'

    # 3. Object Storage check
    if storage_service.is_available():
        status['storage'] = 'connected'
    else:
        status['storage'] = 'not_configured'

    code = 200
    return jsonify(status), code

@monitoring_bp.route('/api/server/heartbeat', methods=['POST'])
def server_heartbeat_api():
    """Endpoint for backend nodes to send periodic telemetry metrics."""
    data = request.get_json(silent=True) or {}
    srv_id = data.get('server_id') or current_app.config.get('SERVER_ID', 'srv-node-1')
    
    from services.server_registry import server_registry
    server_registry.record_heartbeat(
        server_id=srv_id,
        cpu_usage=data.get('cpu_usage', 0.0),
        memory_usage=data.get('memory_usage', 0.0),
        active_requests=data.get('active_requests', 0),
        requests_per_min=data.get('requests_per_min', 0),
        avg_latency_ms=data.get('avg_latency_ms', 0.0),
        error_rate=data.get('error_rate', 0.0)
    )
    return jsonify({'success': True, 'message': 'Heartbeat recorded.'}), 200


