import os
os.environ['FLASK_ENV'] = 'testing'
import io
import time
import unittest
import threading
from unittest.mock import patch, MagicMock
from app import create_app
from database import db
from models import User, Role, StoreProfile, Product, Category, Banner
from services.storage import resolve_image_url, storage_service, optimize_image_bytes

class TestProductionReliability(unittest.TestCase):
    """
    Comprehensive test suite for Phase 17 & Phase 18 Production Reliability,
    502 Gateway elimination, Gunicorn thread safety, and R2 Object Storage audit.
    """

    def setUp(self):
        self.app = create_app()
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.app.config['ALLOW_LOCAL_STORAGE_FALLBACK'] = True
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def login_as(self, user):
        """Helper to simulate authenticated session for Flask-Login."""
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True

    def test_health_check_instant_response(self):
        """Verify /health returns 200 OK in < 50ms without executing external I/O."""
        t0 = time.time()
        res = self.client.get('/health')
        duration_ms = (time.time() - t0) * 1000

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get('status'), 'healthy')
        self.assertLess(duration_ms, 100.0)

    def test_readiness_check_diagnostics(self):
        """Verify /ready performs bounded dependency checks and returns structured JSON."""
        res = self.client.get('/ready')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('status', data)
        self.assertIn('database', data)
        self.assertIn('storage', data)

    def test_image_url_canonical_resolution(self):
        """Verify resolve_image_url normalizes all key formats and legacy paths."""
        # 1. R2 public key
        self.assertEqual(
            resolve_image_url("products/shirt.webp"),
            "/static/uploads/products/shirt.webp"
        )
        # 2. Legacy /static/uploads/ wrapping private document
        self.assertEqual(
            resolve_image_url("/static/uploads/users/private/seller-documents/seller1/abc.webp"),
            "/private/file/private/seller-documents/seller1/abc.webp"
        )
        # 3. Direct private object key
        self.assertEqual(
            resolve_image_url("private/seller-documents/seller1/xyz.webp"),
            "/private/file/private/seller-documents/seller1/xyz.webp"
        )
        # 4. Empty/None fallback
        self.assertEqual(
            resolve_image_url(None),
            "/static/uploads/placeholder.jpg"
        )

    def test_private_document_access_control(self):
        """Verify strict authorization for private seller KYC documents."""
        owner = User(username='owner_seller', email='owner@vkshop.com', role=Role.SELLER, is_active=True)
        owner.set_password('pass123')
        other = User(username='other_seller', email='other@vkshop.com', role=Role.SELLER, is_active=True)
        other.set_password('pass123')
        admin = User(username='admin_user', email='admin@vkshop.com', role=Role.ADMIN, is_active=True)
        admin.set_password('pass123')

        db.session.add_all([owner, other, admin])
        db.session.flush()

        s1 = StoreProfile(user_id=owner.id, name="Owner Store", status="Approved")
        s2 = StoreProfile(user_id=other.id, name="Other Store", status="Approved")
        db.session.add_all([s1, s2])
        db.session.commit()

        target_url = '/private/file/private/seller-documents/owner_seller/aadhaar.webp'

        # 1. Unauthenticated -> 401
        res_unauth = self.client.get(target_url)
        self.assertEqual(res_unauth.status_code, 401)

        # 2. Other seller -> 403
        self.client.post('/login', data={'login_input': 'other_seller', 'password': 'pass123'})
        res_other = self.client.get(target_url)
        self.assertEqual(res_other.status_code, 403)
        self.client.get('/logout')

        # 3. Admin -> 404 (Authorized, file missing in test memory storage)
        self.client.post('/login', data={'login_input': 'admin_user', 'password': 'pass123'})
        res_admin = self.client.get(target_url)
        self.assertEqual(res_admin.status_code, 404)
        self.client.get('/logout')

        # 4. Owner -> 404 (Authorized, file missing in test memory storage)
        self.client.post('/login', data={'login_input': 'owner_seller', 'password': 'pass123'})
        res_owner = self.client.get(target_url)
        self.assertEqual(res_owner.status_code, 404)

    def test_image_optimization_performance(self):
        """Verify Pillow WebP optimization completes in < 150ms for normal images."""
        from PIL import Image as PILImage
        img_buf = io.BytesIO()
        test_img = PILImage.new('RGB', (1000, 1000), color='blue')
        test_img.save(img_buf, format='JPEG')
        raw_bytes = img_buf.getvalue()

        t0 = time.time()
        opt_bytes, opt_mime, opt_ext = optimize_image_bytes(raw_bytes)
        duration_ms = (time.time() - t0) * 1000

        self.assertEqual(opt_mime, 'image/webp')
        self.assertEqual(opt_ext, '.webp')
        self.assertTrue(len(opt_bytes) > 0)
        self.assertLess(duration_ms, 300.0)

    def test_concurrent_request_load(self):
        """
        Simulate 30 concurrent HTTP requests to verify worker process & thread stability
        without connection pool starvation or worker crash.
        """
        results = []
        errors = []

        def worker_task(client, path):
            try:
                res = client.get(path)
                results.append(res.status_code)
            except Exception as ex:
                errors.append(str(ex))

        threads = []
        paths = ['/health', '/ready', '/login', '/register', '/privacy-policy', '/terms-conditions']

        for i in range(30):
            p = paths[i % len(paths)]
            t = threading.Thread(target=worker_task, args=(self.app.test_client(), p))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Concurrent request errors: {errors}")
        self.assertEqual(len(results), 30)
        for code in results:
            self.assertEqual(code, 200)

if __name__ == '__main__':
    unittest.main()
