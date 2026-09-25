import os
import secrets
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    BASE_DIR = BASE_DIR
    # Core Flask Configuration
    ENV = os.environ.get('FLASK_ENV', 'production').lower()
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1', 't')
    TESTING = False
    
    # Secure Secret Key Generation
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        SECRET_KEY = os.environ.get('SECRET_KEY_FALLBACK', 'dev_secret_key_amazon_flipkart_clone_99384')
        if ENV == 'production' and SECRET_KEY == 'dev_secret_key_amazon_flipkart_clone_99384':
            SECRET_KEY = secrets.token_hex(32)
            
    # Database Configuration
    DB_DIR = os.path.join(BASE_DIR, 'database')
    os.makedirs(DB_DIR, exist_ok=True)
    
    # Check for DATABASE_URL or build PostgreSQL URI
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    if not SQLALCHEMY_DATABASE_URI:
        db_user = os.environ.get('POSTGRES_USER')
        db_password = os.environ.get('POSTGRES_PASSWORD')
        db_host = os.environ.get('POSTGRES_HOST')
        db_port = os.environ.get('POSTGRES_PORT')
        db_name = os.environ.get('POSTGRES_DB')
        if all([db_user, db_password, db_host, db_port, db_name]):
            SQLALCHEMY_DATABASE_URI = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        else:
            SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(DB_DIR, 'ecommerce.db')
            
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Connection Pool Tuning
    if SQLALCHEMY_DATABASE_URI.startswith('sqlite'):
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_pre_ping': True
        }
    else:
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_size': int(os.environ.get('DATABASE_POOL_SIZE', 10)),
            'max_overflow': int(os.environ.get('DATABASE_MAX_OVERFLOW', 20)),
            'pool_recycle': int(os.environ.get('DATABASE_POOL_RECYCLE', 1800)),
            'pool_pre_ping': True
        }
    
    # Redis Session Config
    SESSION_TYPE = os.environ.get('SESSION_TYPE', 'redis')
    if SESSION_TYPE == 'redis':
        import redis
        REDIS_URL = os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379/0')
        SESSION_REDIS = redis.from_url(REDIS_URL)
        SESSION_USE_SIGNER = True
        SESSION_PERMANENT = True
        SESSION_KEY_PREFIX = 'ecom_sess:'
        
    # Rate Limiting Settings
    RATELIMIT_STORAGE_URI = os.environ.get('REDIS_URL', 'memory://')
    
    # MinIO S3 Settings
    MINIO_ENDPOINT = os.environ.get('MINIO_ENDPOINT')
    MINIO_ACCESS_KEY = os.environ.get('MINIO_ACCESS_KEY')
    MINIO_SECRET_KEY = os.environ.get('MINIO_SECRET_KEY')
    MINIO_BUCKET_NAME = os.environ.get('MINIO_BUCKET_NAME', 'ecom-uploads')
    MINIO_SECURE = os.environ.get('MINIO_SECURE', 'False').lower() in ('true', '1', 't')
    
    # Local Upload Directories (retained for backward compatibility / sync)
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    PRODUCT_UPLOADS = os.path.join(UPLOAD_FOLDER, 'products')
    USER_UPLOADS = os.path.join(UPLOAD_FOLDER, 'users')
    STORE_UPLOADS = os.path.join(UPLOAD_FOLDER, 'store')
    BANNER_UPLOADS = os.path.join(UPLOAD_FOLDER, 'banners')
    CATEGORY_UPLOADS = os.path.join(UPLOAD_FOLDER, 'categories')
    ADMIN_UPLOADS = os.path.join(UPLOAD_FOLDER, 'admin')
    
    # Ensure local upload directories exist
    for folder in [PRODUCT_UPLOADS, USER_UPLOADS, STORE_UPLOADS, BANNER_UPLOADS, CATEGORY_UPLOADS, ADMIN_UPLOADS]:
        os.makedirs(folder, exist_ok=True)
        
    # App Settings
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB limit
    
    # Session Cookie Security Options
    SESSION_COOKIE_NAME = 'ecom_session'
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() in ('true', '1', 't')
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

class DevelopmentConfig(Config):
    ENV = 'development'
    DEBUG = True
    SESSION_COOKIE_SECURE = False

class ProductionConfig(Config):
    ENV = 'production'
    DEBUG = False
    SESSION_COOKIE_SECURE = True

class TestingConfig(Config):
    ENV = 'testing'
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SESSION_TYPE = None  # Use cookie-based session for standalone testing
    RATELIMIT_STORAGE_URI = 'memory://'
    # Disable engine options for sqlite memory connection
    SQLALCHEMY_ENGINE_OPTIONS = {}
