import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from flask import Flask, redirect, url_for, flash, render_template, request, send_file
from flask_login import LoginManager, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
from flask_wtf.csrf import CSRFProtect
from flask_socketio import SocketIO, emit, join_room, leave_room
from database import db, init_db
from flask_caching import Cache
from models import User

# Create SocketIO and Cache instances at module level
socketio = SocketIO(cors_allowed_origins="*", async_mode='threading', allow_upgrades=False)
cache = Cache()

_categories_cache = None
_categories_cache_timestamp = 0

def get_cached_categories():
    global _categories_cache, _categories_cache_timestamp
    import time
    now = time.time()
    if _categories_cache is None or (now - _categories_cache_timestamp) > 60:
        from models import Category
        try:
            _categories_cache = Category.query.filter(Category.parent_id == None).all()
            _categories_cache_timestamp = now
        except Exception:
            return _categories_cache or []
    return _categories_cache

def clear_categories_cache():
    global _categories_cache
    _categories_cache = None

def monkeypatch_file_storage():
    """Intercept all uploads and transparently upload to MinIO S3 instead of local disk."""
    from werkzeug.datastructures import FileStorage
    from flask import current_app
    
    original_save = FileStorage.save
    
    def patched_save(self, dst, buffer_size=16384):
        normalized_dst = os.path.abspath(dst)
        uploads_dir = os.path.abspath(current_app.config.get('UPLOAD_FOLDER'))
        
        if normalized_dst.startswith(uploads_dir):
            rel_path = os.path.relpath(normalized_dst, uploads_dir)
            object_name = rel_path.replace('\\', '/')
            
            self.stream.seek(0)
            from services.storage import storage_service
            if storage_service.client is not None:
                storage_service.upload_file_stream(self.stream, object_name, content_type=self.content_type)
                return
                
        original_save(self, dst, buffer_size)
        
    FileStorage.save = patched_save

def create_app():
    app = Flask(__name__)
    
    # Dynamic Configuration Loader
    env = os.environ.get('FLASK_ENV', 'production').lower()
    if env == 'development':
        app.config.from_object('config.DevelopmentConfig')
    elif env == 'testing':
        app.config.from_object('config.TestingConfig')
    else:
        app.config.from_object('config.ProductionConfig')
    
    # Initialize Server-side Session with Redis if configured
    session_type = app.config.get('SESSION_TYPE')
    if session_type and str(session_type).lower() in ['redis', 'memcached', 'filesystem', 'mongodb', 'sqlalchemy', 'peewee', 'null']:
        from flask_session import Session
        Session(app)
        
    # Enable Caching
    if app.config.get('SESSION_TYPE') == 'redis':
        cache.init_app(app, config={
            'CACHE_TYPE': 'RedisCache',
            'CACHE_REDIS_URL': app.config.get('REDIS_URL', 'redis://127.0.0.1:6379/0')
        })
    else:
        cache.init_app(app, config={'CACHE_TYPE': 'SimpleCache'})
        
    # Execute FileStorage monkeypatch
    monkeypatch_file_storage()
    
    # 0. ProxyFix middleware for reverse proxy support (Cloudflare / Nginx)
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # 1. Enable CORS for cross-domain REST safety
    CORS(app)
    
    # 2. Enable Production CSRF Security
    csrf = CSRFProtect(app)
    
    # 3. Setup File Error Logger
    if not app.debug:
        logs_dir = os.path.join(app.config['BASE_DIR'], 'logs')
        os.makedirs(logs_dir, exist_ok=True)
        file_handler = RotatingFileHandler(
            os.path.join(logs_dir, 'app.log'),
            maxBytes=10 * 1024 * 1024,  # 10 MB limit
            backupCount=5
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('E-COM Production-Grade Application Starting...')

    # 4. Initialize Database connection
    init_db(app)
    
    # 5. Set up User Sessions Manager
    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'warning'
    login_manager.init_app(app)
    
    @login_manager.user_loader
    def load_user(user_id):
        user = User.query.get(int(user_id))
        if user:
            if not user.is_active:
                return None
            if user.role == 'verifier' and user.is_suspended:
                return None
        return user
        
    # 6. Set up Rate Limiter
    limiter = Limiter(
        key_func=get_remote_address,
        app=app,
        default_limits=["150 per minute"]
    )
    
    # 7. Global Context Data Injector
    @app.context_processor
    def inject_global_data():
        wishlist_ids = []
        if current_user.is_authenticated:
            try:
                from models import Wishlist
                wishlist_ids = [item.product_id for item in Wishlist.query.filter_by(user_id=current_user.id).all()]
            except Exception:
                pass
        return dict(
            all_categories=get_cached_categories(),
            wishlist_product_ids=wishlist_ids
        )
        
    # 8. Outgoing Security Headers Injector
    @app.after_request
    def inject_security_headers(response):
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        if request.path.startswith('/static/'):
            response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        if not app.debug:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response
        
    # 9. Register Blueprints
    from routes.auth import auth_bp
    from routes.main import main_bp
    from routes.customer import customer_bp
    from routes.seller import seller_bp
    from routes.admin import admin_bp
    from routes.api import api_bp
    from routes.monitoring import monitoring_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(customer_bp)
    app.register_blueprint(seller_bp, url_prefix='/seller')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(monitoring_bp)
    
    # 10. Unified Production Error Pages
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('errors/404.html'), 404
        
    @app.errorhandler(500)
    def internal_server_error(e):
        # Log server exceptions
        app.logger.error(f"Internal Exception on {request.url}: {str(e)}")
        return render_template('errors/500.html'), 500
        
    # 11. Start background tasks
    from services.scheduler import init_scheduler
    init_scheduler(app)
    
    # 12. Dynamic serve uploads from MinIO S3
    @app.route('/static/uploads/<path:filename>')
    def serve_minio_upload(filename):
        from services.storage import storage_service
        try:
            response, stat = storage_service.get_file(filename)
            import io
            file_data = response.read()
            response.close()
            response.release_conn()
            return send_file(
                io.BytesIO(file_data),
                mimetype=stat.content_type or 'application/octet-stream',
                as_attachment=False
            )
        except Exception:
            local_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(local_path):
                return send_file(local_path)
            from flask import abort
            abort(404)
            
    # 13. Sync uploads on startup
    with app.app_context():
        try:
            from services.storage import sync_local_uploads_to_minio
            sync_local_uploads_to_minio()
        except Exception as e:
            app.logger.error(f"Failed to sync local uploads to MinIO on startup: {e}")
            
    return app

app = create_app()

# Initialize SocketIO with the app
socketio.init_app(app, cors_allowed_origins="*")

# Socket.IO Events
@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        room = f"user_{current_user.id}"
        join_room(room)
        if current_user.role in ['admin', 'sub_admin']:
            join_room('admin_room')
        elif current_user.role == 'seller' and current_user.store_profile:
            join_room(f"seller_{current_user.store_profile.id}")

@socketio.on('disconnect')
def handle_disconnect():
    if current_user.is_authenticated:
        room = f"user_{current_user.id}"
        leave_room(room)
        if current_user.role in ['admin', 'sub_admin']:
            leave_room('admin_room')
        elif current_user.role == 'seller' and current_user.store_profile:
            leave_room(f"seller_{current_user.store_profile.id}")

@socketio.on('join_admin')
def handle_join_admin():
    if current_user.is_authenticated and current_user.role in ['admin', 'sub_admin']:
        join_room('admin_room')

def emit_notification(user_id, title, message, type='general'):
    """Emit a real-time notification to a specific user."""
    socketio.emit('notification', {
        'title': title,
        'message': message,
        'type': type,
        'timestamp': datetime.utcnow().isoformat()
    }, room=f"user_{user_id}")

def emit_order_update(order_id, status, order_number):
    """Emit real-time order status update."""
    socketio.emit('order_update', {
        'order_id': order_id,
        'status': status,
        'order_number': order_number,
        'timestamp': datetime.utcnow().isoformat()
    }, room='admin_room')

def emit_commission_update(store_id, status, amount):
    """Emit real-time commission status update."""
    socketio.emit('commission_update', {
        'store_id': store_id,
        'status': status,
        'amount': amount,
        'timestamp': datetime.utcnow().isoformat()
    }, room=f"seller_{store_id}")
    socketio.emit('commission_update', {
        'store_id': store_id,
        'status': status,
        'amount': amount,
        'timestamp': datetime.utcnow().isoformat()
    }, room='admin_room')

def emit_analytics_update(store_id):
    """Trigger analytics refresh for a seller."""
    socketio.emit('analytics_update', {
        'store_id': store_id,
        'timestamp': datetime.utcnow().isoformat()
    }, room=f"seller_{store_id}")

def emit_settings_update():
    """Notify admins of settings changes."""
    socketio.emit('settings_update', {
        'timestamp': datetime.utcnow().isoformat()
    }, room='admin_room')

def emit_force_logout(user_id, reason="Your session has been terminated by the Main Admin."):
    """Force a sub admin to logout in real-time."""
    socketio.emit('force_logout', {
        'reason': reason,
        'timestamp': datetime.utcnow().isoformat()
    }, room=f"user_{user_id}")

if __name__ == '__main__':
    # Initialize DB automatically if missing or empty
    with app.app_context():
        if User.query.count() == 0:
            print("Database is empty. Initiating seeder...")
            from seed import seed_database
            seed_database()
        
    print("Launching Local Dev Server (SocketIO)...")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)