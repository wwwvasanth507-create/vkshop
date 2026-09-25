from flask import Blueprint, jsonify, current_app
from database import db
from services.storage import storage_service

monitoring_bp = Blueprint('monitoring', __name__)

@monitoring_bp.route('/health')
def health_check():
    status = {
        'status': 'healthy',
        'database': 'unknown',
        'redis': 'unknown',
        'minio': 'unknown'
    }
    has_error = False

    # 1. Check Database connection
    try:
        db.session.execute(db.text("SELECT 1"))
        status['database'] = 'connected'
    except Exception as e:
        status['database'] = f"error: {str(e)}"
        status['status'] = 'unhealthy'
        has_error = True

    # 2. Check Redis connection
    if current_app.config.get('SESSION_TYPE') == 'redis':
        try:
            redis_client = current_app.config.get('SESSION_REDIS')
            if redis_client:
                redis_client.ping()
                status['redis'] = 'connected'
            else:
                status['redis'] = 'not_configured_client'
                status['status'] = 'unhealthy'
                has_error = True
        except Exception as e:
            status['redis'] = f"error: {str(e)}"
            status['status'] = 'unhealthy'
            has_error = True
    else:
        status['redis'] = 'disabled'

    # 3. Check MinIO S3 connection
    if current_app.config.get('MINIO_ENDPOINT'):
        try:
            cli = storage_service.client
            if cli:
                cli.list_buckets()
                status['minio'] = 'connected'
            else:
                status['minio'] = 'not_initialized'
                status['status'] = 'unhealthy'
                has_error = True
        except Exception as e:
            status['minio'] = f"error: {str(e)}"
            status['status'] = 'unhealthy'
            has_error = True
    else:
        status['minio'] = 'disabled'

    response_code = 500 if has_error else 200
    return jsonify(status), response_code
