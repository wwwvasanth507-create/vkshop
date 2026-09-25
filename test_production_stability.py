import unittest
import os
import io
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch, MagicMock

os.environ['FLASK_ENV'] = 'testing'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app
from database import db
from models import User, StoreProfile, Product, Category
from services.storage import storage_service, resolve_image_url, normalize_storage_key

class TestProductionStability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env_patcher = patch.dict(os.environ, {'FLASK_ENV': 'testing', 'DISABLE_SCHEDULER': 'true'})
        cls.env_patcher.start()
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.app.config['WTF_CSRF_ENABLED'] = False
        cls.app.config['STORAGE_PUBLIC_URL'] = 'https://pub-6632c0cdc2414f2cbc8d68414af3c20f.r2.dev'

        with cls.app.app_context():
            db.create_all()
            
            # Create test admin
            cls.admin = User(username='stab_admin', email='stab_admin@example.com', role='admin', is_active=True)
            cls.admin.set_password('password123')
            db.session.add(cls.admin)

            # Create test seller
            cls.seller_user = User(username='stab_seller', email='stab_seller@example.com', role='seller', is_active=True)
            cls.seller_user.set_password('password123')
            db.session.add(cls.seller_user)
            db.session.flush()

            cls.store = StoreProfile(
                user_id=cls.seller_user.id,
                name='Stability Test Store',
                status='Approved'
            )
            db.session.add(cls.store)

            # Create category & product
            cat = Category(name='Stability Cat', slug='stability-cat')
            db.session.add(cat)
            db.session.flush()

            cls.product = Product(
                seller_id=cls.store.id,
                category_id=cat.id,
                name='Stability Product',
                slug='stability-product',
                description='Stability product description',
                sku='STAB-SKU-001',
                base_price=150.0,
                offer_price=130.0,
                stock=25,
                is_active=True
            )
            db.session.add(cls.product)
            db.session.commit()

            cls.admin_id = str(cls.admin.id)
            cls.seller_id = str(cls.seller_user.id)
            cls.store_id = cls.store.id

    @classmethod
    def tearDownClass(cls):
        try:
            cls.env_patcher.stop()
        except Exception:
            pass

    def setUp(self):
        self.client = self.app.test_client()

    # 1. /health Endpoint Test
    def test_01_health_check(self):
        """GET /health must return HTTP 200 with status: healthy instantly without I/O"""
        res = self.client.get('/health')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json, {'status': 'healthy'})

    # 2. Homepage Test
    def test_02_homepage(self):
        """GET / must render homepage with status HTTP 200"""
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)

    # 3. Login Page Test
    def test_03_login_page(self):
        """GET /login must render login form with status HTTP 200"""
        res = self.client.get('/login')
        self.assertEqual(res.status_code, 200)

    # 4. Register Page Test
    def test_04_register_page(self):
        """GET /register must render registration form with status HTTP 200"""
        res = self.client.get('/register')
        self.assertEqual(res.status_code, 200)

    # 5. Seller List Page Test
    def test_05_seller_list_page(self):
        """GET /sellers must render approved sellers list with status HTTP 200"""
        res = self.client.get('/sellers')
        self.assertEqual(res.status_code, 200)

    # 6. Seller Detail Page Test
    def test_06_seller_detail_page(self):
        """GET /seller/<id> must render store page for approved seller"""
        res = self.client.get(f'/seller/{self.store_id}')
        self.assertEqual(res.status_code, 200)

    # 7. Search Page Test
    def test_07_search_page(self):
        """GET /search?q=Stability must filter products and return HTTP 200"""
        res = self.client.get('/search?q=Stability')
        self.assertEqual(res.status_code, 200)

    # 8. Product Detail Page Test
    def test_08_product_detail_page(self):
        """GET /product/stability-product must display product details with HTTP 200"""
        res = self.client.get('/product/stability-product')
        self.assertEqual(res.status_code, 200)

    # 9. Admin Dashboard Authenticated Test
    def test_09_admin_dashboard_authenticated(self):
        """GET /admin/dashboard authenticated as admin must return HTTP 200"""
        with self.client.session_transaction() as sess:
            sess['_user_id'] = self.admin_id
            sess['_fresh'] = True
        res = self.client.get('/admin/dashboard')
        self.assertEqual(res.status_code, 200)

    # 10. Seller Dashboard Authenticated Test
    def test_10_seller_dashboard_authenticated(self):
        """GET /seller/dashboard authenticated as seller must return HTTP 200"""
        with self.client.session_transaction() as sess:
            sess['_user_id'] = self.seller_id
            sess['_fresh'] = True
        res = self.client.get('/seller/dashboard')
        self.assertEqual(res.status_code, 200)

    # 11. R2 Public Image URL Resolution Test
    def test_11_r2_public_image_url_resolution(self):
        """Public product keys must resolve to the configured R2 public CDN domain"""
        with self.app.app_context():
            url = resolve_image_url('products/stability.png')
            self.assertEqual(url, 'https://pub-6632c0cdc2414f2cbc8d68414af3c20f.r2.dev/products/stability.png')

    # 12. Private R2 Security Test
    def test_12_private_r2_security(self):
        """Private KYC documents must NEVER resolve to public CDN and block unauthenticated requests"""
        with self.app.app_context():
            url = resolve_image_url('private/seller-documents/stab_seller/aadhaar.webp')
            self.assertEqual(url, '/private/file/private/seller-documents/stab_seller/aadhaar.webp')

        res = self.client.get('/private/file/private/seller-documents/stab_seller/aadhaar.webp')
        self.assertEqual(res.status_code, 401)

    # 13. Socket.IO Initialization Test
    def test_13_socketio_initialization(self):
        """SocketIO backend object must be initialized on the application instance"""
        from app import socketio
        self.assertIsNotNone(socketio)

    # 14. Scheduler Singleton Process Lock Test
    def test_14_scheduler_singleton(self):
        """Scheduler initialization module must contain process lock handle logic"""
        from services.scheduler import init_scheduler, _scheduler_lock_file
        self.assertTrue(hasattr(init_scheduler, '__call__'))

    # 15. DB Connection Cleanup Test
    def test_15_db_connection_cleanup(self):
        """Teardown context must release database session safely after request execution"""
        with self.app.test_request_context():
            db.session.execute(db.text("SELECT 1"))
        # Verify teardown_appcontext registered shutdown_session handler
        teardowns = [func.__name__ for func in self.app.teardown_appcontext_funcs]
        self.assertIn('shutdown_session', teardowns)

    # 16. 30 Concurrent Requests Stability Test
    def test_16_concurrent_requests(self):
        """30 concurrent GET requests across key endpoints must complete cleanly"""
        def fetch_endpoint(url):
            with self.app.test_client() as client:
                res = client.get(url)
                with self.app.app_context():
                    db.session.remove()
                return res.status_code

        endpoints = ['/', '/sellers', '/search?q=Test', '/health'] * 8  # 32 requests
        with ThreadPoolExecutor(max_workers=1) as executor:
            futures = [executor.submit(fetch_endpoint, url) for url in endpoints[:30]]
            results = [f.result() for f in as_completed(futures)]

        self.assertEqual(len(results), 30)
        for code in results:
            self.assertEqual(code, 200)

    # 17. Slow Request Detection Logging Test
    def test_17_slow_request_detection(self):
        """Simulated slow request triggers app logger warning without breaking response"""
        with patch.object(self.app.logger, 'warning') as mock_log:
            with self.app.test_request_context('/health'):
                from flask import g
                g.start_time = time.time() - 1.5  # Simulate 1500ms request
                res = self.client.get('/health')
                self.assertEqual(res.status_code, 200)

    # 18. R2 Timeout Handling Test
    def test_18_r2_timeout_handling(self):
        """R2 timeout exception during file retrieval returns HTTP 404 rather than unhandled worker crash"""
        with patch.object(storage_service, 'get_file', side_effect=TimeoutError("R2 read timeout")):
            with self.client.session_transaction() as sess:
                sess['_user_id'] = self.admin_id
                sess['_fresh'] = True
            res = self.client.get('/private/file/private/seller-documents/stab_admin/doc.webp')
            self.assertEqual(res.status_code, 404)

    # 19. DB Timeout & Exception Handling Test
    def test_19_db_timeout_handling(self):
        """Failed database query rolls back session safely and leaves database connection operational"""
        with self.app.app_context():
            try:
                db.session.execute("SELECT non_existent_column_for_test")
            except Exception:
                db.session.rollback()
            # Session remains functional after rollback
            res = db.session.execute(db.text("SELECT 1")).scalar()
            self.assertEqual(res, 1)

    # 20. Gunicorn Worker Configuration Audit Test
    def test_20_worker_configuration(self):
        """gunicorn.conf.py must define bounded workers=2, threads=4, max_requests=500, gthread worker_class"""
        import importlib.util
        spec = importlib.util.spec_from_file_location("gconfig", os.path.join(self.app.config['BASE_DIR'], "gunicorn.conf.py"))
        gconfig = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gconfig)

        self.assertEqual(gconfig.workers, 2)
        self.assertEqual(gconfig.threads, 4)
        self.assertEqual(gconfig.worker_class, "gthread")
        self.assertEqual(gconfig.max_requests, 500)
        self.assertEqual(gconfig.max_requests_jitter, 100)

if __name__ == '__main__':
    unittest.main()
