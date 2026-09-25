import os
import io
import unittest
from unittest.mock import patch, MagicMock

os.environ['FLASK_ENV'] = 'testing'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app
from database import db
from models import User, Role, StoreProfile
from services.storage import normalize_storage_key, resolve_image_url, storage_service

class R2SecurityAndStabilityTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update({
            'TESTING': True,
            'WTF_CSRF_ENABLED': False
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    # 1. Test normalize_storage_key on full public R2 URLs containing private keys
    def test_01_normalize_full_r2_url_private(self):
        full_r2_private_url = "https://pub-6632c0cdc2414f2cbc8d68414af3c20f.r2.dev/private/seller-documents/seller1/0914bc21a490420ba99d986cbf491ff0.webp"
        key = normalize_storage_key(full_r2_private_url)
        self.assertEqual(key, "private/seller-documents/seller1/0914bc21a490420ba99d986cbf491ff0.webp")

    # 2. Test resolve_image_url blocks public CDN exposure of private objects
    def test_02_resolve_image_url_blocks_public_cdn_for_private_keys(self):
        full_r2_private_url = "https://pub-6632c0cdc2414f2cbc8d68414af3c20f.r2.dev/private/seller-documents/seller1/0914bc21a490420ba99d986cbf491ff0.webp"
        resolved_url = resolve_image_url(full_r2_private_url)
        
        # MUST resolve to authenticated Flask route, NOT public CDN domain
        self.assertFalse(resolved_url.startswith("https://pub-"))
        self.assertEqual(resolved_url, "/private/file/private/seller-documents/seller1/0914bc21a490420ba99d986cbf491ff0.webp")

    # 3. Test resolve_image_url for public R2 objects
    def test_03_resolve_image_url_public_objects(self):
        with patch.dict(os.environ, {'STORAGE_PUBLIC_URL': 'https://pub-6632c0cdc2414f2cbc8d68414af3c20f.r2.dev'}):
            full_r2_product_url = "https://pub-6632c0cdc2414f2cbc8d68414af3c20f.r2.dev/products/phone_123.webp"
            resolved_url = resolve_image_url(full_r2_product_url)
            self.assertEqual(resolved_url, "https://pub-6632c0cdc2414f2cbc8d68414af3c20f.r2.dev/products/phone_123.webp")

            rel_product_key = "products/phone_123.webp"
            resolved_rel_url = resolve_image_url(rel_product_key)
            self.assertEqual(resolved_rel_url, "https://pub-6632c0cdc2414f2cbc8d68414af3c20f.r2.dev/products/phone_123.webp")

    # 4. Test private document access control & security headers
    @patch('services.storage.storage_service.get_file')
    def test_04_private_file_security_headers(self, mock_get_file):
        mock_response = MagicMock()
        mock_response.read.return_value = b'fake_webp_bytes'
        mock_stat = MagicMock()
        mock_stat.content_type = 'image/webp'
        mock_stat.size = 15
        mock_get_file.return_value = (mock_response, mock_stat)

        with self.app.app_context():
            seller = User(username='sec_seller', email='sec@test.com', role=Role.SELLER, is_active=True)
            seller.set_password('pass123')
            db.session.add(seller)
            db.session.flush()

            store = StoreProfile(user_id=seller.id, name="Security Store", status="Approved")
            db.session.add(store)
            db.session.commit()

        # Unauthenticated request must return 401
        res_unauth = self.client.get('/private/file/private/seller-documents/sec_seller/aadhaar.webp')
        self.assertEqual(res_unauth.status_code, 401)

        # Log in as seller
        self.client.post('/login', data={'login_input': 'sec_seller', 'password': 'pass123'})
        res_auth = self.client.get('/private/file/private/seller-documents/sec_seller/aadhaar.webp')
        
        self.assertEqual(res_auth.status_code, 200)
        self.assertIn('Cache-Control', res_auth.headers)
        self.assertEqual(res_auth.headers.get('Cache-Control'), 'private, no-cache, no-store, must-revalidate')
        self.assertEqual(res_auth.headers.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(res_auth.headers.get('Content-Length'), '15')

if __name__ == '__main__':
    unittest.main()
