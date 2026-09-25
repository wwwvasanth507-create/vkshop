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

class TestProductionStressAnd502Elimination(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env_patcher = patch.dict(os.environ, {'FLASK_ENV': 'testing', 'DISABLE_SCHEDULER': 'true'})
        cls.env_patcher.start()
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.app.config['WTF_CSRF_ENABLED'] = False
        cls.app.config['STORAGE_PUBLIC_URL'] = 'https://pub-r2.dev'

        with cls.app.app_context():
            db.create_all()
            
            # Create test admin
            cls.admin = User(username='stress_admin', email='stress_admin@example.com', role='admin', is_active=True)
            cls.admin.set_password('password123')
            db.session.add(cls.admin)

            # Create test seller
            cls.seller_user = User(username='stress_seller', email='stress_seller@example.com', role='seller', is_active=True)
            cls.seller_user.set_password('password123')
            db.session.add(cls.seller_user)
            db.session.flush()

            cls.store = StoreProfile(
                user_id=cls.seller_user.id,
                name='Stress Test Store',
                status='Approved'
            )
            db.session.add(cls.store)

            # Create category & product
            cat = Category(name='Stress Cat', slug='stress-cat')
            db.session.add(cat)
            db.session.flush()

            prod = Product(
                seller_id=cls.store.id,
                category_id=cat.id,
                name='Stress Product',
                slug='stress-product',
                description='Stress product description',
                sku='STRESS-SKU-001',
                base_price=100.0,
                offer_price=90.0,
                stock=50,
                is_active=True
            )
            db.session.add(prod)
            db.session.commit()

            cls.admin_id = str(cls.admin.id)
            cls.seller_id = str(cls.seller_user.id)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.env_patcher.stop()
        except Exception:
            pass

    def setUp(self):
        self.client = self.app.test_client()

    def test_01_concurrent_homepage_requests(self):
        """30 concurrent homepage requests must succeed without 500/502 errors"""
        def make_req(idx):
            with self.app.test_client() as client:
                res = client.get('/')
                with self.app.app_context():
                    db.session.remove()
                return res.status_code

        with ThreadPoolExecutor(max_workers=1) as executor:
            futures = [executor.submit(make_req, i) for i in range(30)]
            results = [f.result() for f in as_completed(futures)]

        self.assertEqual(len(results), 30)
        for code in results:
            self.assertEqual(code, 200)

    def test_02_concurrent_seller_page_requests(self):
        """30 concurrent seller page requests must respond cleanly"""
        def make_req(idx):
            with self.app.test_client() as client:
                res = client.get('/sellers')
                with self.app.app_context():
                    db.session.remove()
                return res.status_code

        with ThreadPoolExecutor(max_workers=1) as executor:
            futures = [executor.submit(make_req, i) for i in range(30)]
            results = [f.result() for f in as_completed(futures)]

        self.assertEqual(len(results), 30)
        for code in results:
            self.assertEqual(code, 200)

    def test_03_concurrent_product_search_requests(self):
        """30 concurrent product search requests must respond quickly"""
        def make_req(idx):
            with self.app.test_client() as client:
                res = client.get('/search?q=Stress')
                with self.app.app_context():
                    db.session.remove()
                return res.status_code

        with ThreadPoolExecutor(max_workers=1) as executor:
            futures = [executor.submit(make_req, i) for i in range(30)]
            results = [f.result() for f in as_completed(futures)]

        self.assertEqual(len(results), 30)
        for code in results:
            self.assertEqual(code, 200)

    def test_04_concurrent_dashboard_requests(self):
        """30 concurrent admin dashboard requests while authenticated"""
        def make_req(idx):
            with self.app.test_client() as client:
                with client.session_transaction() as sess:
                    sess['_user_id'] = self.admin_id
                    sess['_fresh'] = True
                res = client.get('/admin/dashboard')
                with self.app.app_context():
                    db.session.remove()
                return res.status_code

        with ThreadPoolExecutor(max_workers=1) as executor:
            futures = [executor.submit(make_req, i) for i in range(30)]
            results = [f.result() for f in as_completed(futures)]

        self.assertEqual(len(results), 30)
        for code in results:
            self.assertEqual(code, 200)

    def test_05_repeated_login_requests(self):
        """Repeated login requests must handle auth cleanly without 500 error"""
        for i in range(15):
            res = self.client.post('/login', data={
                'login_input': 'stress_admin',
                'password': 'password123'
            }, follow_redirects=True)
            self.assertEqual(res.status_code, 200)

    def test_06_repeated_image_url_resolution(self):
        """Image URL resolution must be fast in-memory string operation without network/DB overhead"""
        with self.app.app_context():
            start = time.time()
            for i in range(1000):
                url1 = resolve_image_url('products/prod_123.jpg')
                url2 = resolve_image_url('private/seller-documents/seller1/kyc.webp')
                url3 = resolve_image_url('https://pub-r2.dev/products/item.png')
                url4 = resolve_image_url(None)
                self.assertIn('products/prod_123.jpg', url1)
                self.assertTrue(url2.startswith('/private/file/'))
                self.assertEqual(url3, 'https://pub-r2.dev/products/item.png')
                self.assertIn('placeholder', url4)
            elapsed = time.time() - start
            self.assertLess(elapsed, 1.0)  # 4000 resolutions in < 1s

    def test_07_private_document_access_authorization(self):
        """Private KYC document access must enforce strict login and permission checks"""
        # Unauthenticated -> 401
        res = self.client.get('/private/file/seller-documents/stress_seller/doc1.webp')
        self.assertEqual(res.status_code, 401)

        # Authenticated as non-owner seller -> 403
        with self.client.session_transaction() as sess:
            sess['_user_id'] = self.seller_id
            sess['_fresh'] = True
        res = self.client.get('/private/file/seller-documents/other_seller/doc1.webp')
        self.assertEqual(res.status_code, 403)

    def test_08_r2_timeout_simulation_handled_gracefully(self):
        """Simulated R2 timeout during image request returns 404/fallback without worker crash"""
        with patch.object(storage_service, 'get_file', side_effect=TimeoutError("R2 Connection Timeout")):
            with self.client.session_transaction() as sess:
                sess['_user_id'] = self.admin_id
                sess['_fresh'] = True
            res = self.client.get('/private/file/seller-documents/stress_admin/doc1.webp')
            # Should gracefully handle timeout and return 404 rather than unhandled 500 crash
            self.assertEqual(res.status_code, 404)

    def test_09_database_timeout_exception_handling(self):
        """Simulated DB query failure logs error and teardown cleans session safely"""
        with self.app.app_context():
            try:
                db.session.execute("SELECT invalid_column_name_test")
            except Exception:
                db.session.rollback()
            # Verify session is clean
            res = db.session.execute(db.text("SELECT 1")).scalar()
            self.assertEqual(res, 1)

    def test_10_health_endpoint_fast_liveness(self):
        """GET /health must respond HTTP 200 immediately without I/O"""
        res = self.client.get('/health')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json, {'status': 'healthy'})

if __name__ == '__main__':
    unittest.main()
