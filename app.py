import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from flask import Flask, redirect, url_for, flash, render_template, request, send_file, jsonify
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
    """Intercept all uploads, apply image optimization, and upload to S3/Object storage."""
    from werkzeug.datastructures import FileStorage
    from flask import current_app
    import logging
    
    logger = logging.getLogger('storage')
    original_save = FileStorage.save
    
    def patched_save(self, dst, buffer_size=16384):
        normalized_dst = os.path.abspath(dst)
        uploads_dir = os.path.abspath(current_app.config.get('UPLOAD_FOLDER'))
        
        if normalized_dst.startswith(uploads_dir):
            rel_path = os.path.relpath(normalized_dst, uploads_dir)
            object_name = rel_path.replace('\\', '/')
            
            from services.storage import storage_service, optimize_image_bytes
            
            if storage_service.is_available():
                self.stream.seek(0)
                content_type = self.content_type or ''
                
                # If uploaded file is an image, attempt Pillow optimization
                if content_type.startswith('image/') or any(object_name.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp', '.bmp']):
                    try:
                        raw_bytes = self.stream.read()
                        self.stream.seek(0)
                        opt_bytes, opt_mime, opt_ext = optimize_image_bytes(raw_bytes)
                        storage_service.upload_bytes(opt_bytes, object_name, content_type=opt_mime)
                        logger.info(f"Optimized image upload: {object_name} ({len(raw_bytes)} -> {len(opt_bytes)} bytes)")
                        return
                    except Exception as err:
                        logger.warning(f"Image optimization skipped for {object_name}, uploading raw stream: {err}")
                        self.stream.seek(0)
                
                # Upload raw stream for non-image files or if optimization skipped
                storage_service.upload_file_stream(self.stream, object_name, content_type=self.content_type)
                return
            else:
                allow_fallback = current_app.config.get('ALLOW_LOCAL_STORAGE_FALLBACK', True)
                if not allow_fallback:
                    error_msg = f"Persistent object storage is unavailable and ALLOW_LOCAL_STORAGE_FALLBACK is disabled. Failed to save {object_name}."
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)
                logger.warning(f"S3 Object storage unavailable. Using local fallback for {object_name}.")
                
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
    
    # 7. Global Context Data Injector & Image URL Resolver
    from services.storage import resolve_image_url
    app.jinja_env.filters['image_url'] = resolve_image_url
    app.jinja_env.globals['resolve_image_url'] = resolve_image_url
    app.jinja_env.globals['image_url'] = resolve_image_url

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
            wishlist_product_ids=wishlist_ids,
            image_url=resolve_image_url
        )
        
    @app.before_request
    def handle_head_and_start_timer():
        from flask import g, Response
        import time
        g.start_time = time.time()
        if request.method == 'HEAD':
            return Response('', status=200, mimetype='text/html')

    # 8. Outgoing Security Headers & Slow Request Logging Injector
    @app.after_request
    def inject_security_headers(response):
        from flask import g
        import time
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        if request.path.startswith('/static/'):
            response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        if not app.debug:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
            
        if hasattr(g, 'start_time'):
            duration_ms = int((time.time() - g.start_time) * 1000)
            pid = os.getpid()
            if duration_ms > 5000:
                app.logger.error(f"[CRITICAL_SLOW_REQUEST] method={request.method} path={request.path} duration_ms={duration_ms} status={response.status_code} pid={pid}")
            elif duration_ms > 1000:
                app.logger.warning(f"[SLOW_REQUEST] method={request.method} path={request.path} duration_ms={duration_ms} status={response.status_code} pid={pid}")
        return response

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db.session.remove()
        
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
    
    # 9.5 Safe Media Route for Static Uploads (No Gunicorn Proxying; Direct CDN Redirect + Placeholder Guard)
    @app.route('/static/uploads/<path:filename>')
    def serve_upload_file(filename):
        from services.storage import storage_service
        upload_folder = app.config.get('UPLOAD_FOLDER', os.path.join(app.root_path, 'static', 'uploads'))
        local_path = os.path.abspath(os.path.join(upload_folder, filename.replace('/', os.sep)))
        
        # 1. Serve local file if present on disk (with long-lived immutable cache header)
        if os.path.exists(local_path) and os.path.isfile(local_path):
            resp = send_file(local_path)
            resp.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
            return resp
            
        # 2. In production / S3 mode, REDIRECT browser directly to CDN/S3 URL (Bypasses Gunicorn worker threads)
        if storage_service.is_available():
            direct_cdn_url = storage_service.get_public_url(filename)
            if not direct_cdn_url.startswith('/static/uploads/'):
                return redirect(direct_cdn_url, code=302)
                
        # 3. Fallback placeholder if file is missing everywhere
        placeholder = os.path.join(app.root_path, 'static', 'uploads', 'placeholder.jpg')
        if os.path.exists(placeholder):
            resp = send_file(placeholder, mimetype='image/jpeg')
            resp.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
            return resp
        return jsonify({'error': 'File not found'}), 404

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

    # 13. Authenticated Route for Private Documents
    @app.route('/private/file/<path:filename>')
    def serve_private_document(filename):
        from flask_login import current_user
        from flask import abort
        if not current_user.is_authenticated:
            abort(401)

        # Clean key prefix if necessary
        clean_key = filename
        if clean_key.startswith('users/private/'):
            clean_key = clean_key[len('users/'):]
        elif 'private/' in clean_key and not clean_key.startswith('private/'):
            clean_key = clean_key[clean_key.find('private/'):]

        # Authorization check for seller documents: admins, verifiers, or the document owner
        if 'seller-documents/' in clean_key:
            parts = clean_key.split('/')
            try:
                doc_idx = parts.index('seller-documents')
                if doc_idx + 1 < len(parts):
                    doc_username = parts[doc_idx + 1]
                    if current_user.role not in ['admin', 'sub_admin', 'verifier'] and current_user.username != doc_username:
                        abort(403)
            except ValueError:
                pass
            
        from services.storage import storage_service
        try:
            response, stat = storage_service.get_file(clean_key)
            import io
            file_data = response.read()
            response.close()
            response.release_conn()
            mime = stat.content_type if stat and hasattr(stat, 'content_type') and stat.content_type else 'image/webp'
            resp = send_file(
                io.BytesIO(file_data),
                mimetype=mime,
                as_attachment=False
            )
            resp.headers['Cache-Control'] = 'private, no-cache, no-store, must-revalidate'
            resp.headers['Pragma'] = 'no-cache'
            resp.headers['Expires'] = '0'
            resp.headers['X-Content-Type-Options'] = 'nosniff'
            if stat and hasattr(stat, 'size') and stat.size:
                resp.headers['Content-Length'] = str(stat.size)
            return resp
        except Exception as err:
            local_path = os.path.join(app.config['UPLOAD_FOLDER'], clean_key.replace('/', os.sep))
            if os.path.exists(local_path):
                resp = send_file(local_path)
                resp.headers['Cache-Control'] = 'private, no-cache, no-store, must-revalidate'
                resp.headers['X-Content-Type-Options'] = 'nosniff'
                return resp
            app.logger.warning(f"[PRIVATE FILE 404] Could not serve '{clean_key}': {err}")
            abort(404)

            
    # 13. Sync uploads on startup if explicitly enabled
    if os.environ.get('SYNC_ON_STARTUP', 'False').lower() in ('true', '1', 't'):
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