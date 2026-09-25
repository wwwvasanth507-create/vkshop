import os
os.environ['FLASK_ENV'] = 'testing'
import io
import unittest
from unittest.mock import patch, MagicMock
from app import create_app
from database import db
from models import User, Role, StoreProfile
from services.storage import resolve_image_url, storage_service
from services.seller_pdf import SellerPdfService

class TestR2FullAudit(unittest.TestCase):
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

    def test_image_url_resolution_normalization(self):
        """Verify resolve_image_url strips legacy local prefixes and correctly routes private keys."""
        # Test legacy /static/uploads/ wrapping private document
        raw1 = "/static/uploads/users/private/seller-documents/seller1/abc.webp"
        res1 = resolve_image_url(raw1)
        self.assertEqual(res1, "/private/file/private/seller-documents/seller1/abc.webp")

        # Test plain private document key
        raw2 = "private/seller-documents/seller1/xyz.webp"
        res2 = resolve_image_url(raw2)
        self.assertEqual(res2, "/private/file/private/seller-documents/seller1/xyz.webp")

        # Test public product image key
        raw3 = "products/prod123.webp"
        res3 = resolve_image_url(raw3)
        self.assertTrue(res3.endswith("/products/prod123.webp"))

    def test_private_document_access_control(self):
        """Verify role-based authorization for private documents."""
        seller1_user = User(username='seller_owner', email='s1@vkshop.com', role=Role.SELLER, is_active=True)
        seller1_user.set_password('pass123')
        seller2_user = User(username='other_seller', email='s2@vkshop.com', role=Role.SELLER, is_active=True)
        seller2_user.set_password('pass123')
        admin_user = User(username='admin_boss', email='adminboss@vkshop.com', role=Role.ADMIN, is_active=True)
        admin_user.set_password('pass123')

        db.session.add_all([seller1_user, seller2_user, admin_user])
        db.session.flush()

        store1 = StoreProfile(user_id=seller1_user.id, name="Owner Store", status="Approved")
        store2 = StoreProfile(user_id=seller2_user.id, name="Other Store", status="Approved")
        db.session.add_all([store1, store2])
        db.session.commit()

        # 1. Unauthenticated request -> 401
        res_unauth = self.client.get('/private/file/private/seller-documents/seller_owner/doc1.webp')
        self.assertEqual(res_unauth.status_code, 401)

        # 2. Login as other_seller and attempt to access seller_owner's document -> 403
        self.client.post('/login', data={'login_input': 'other_seller', 'password': 'pass123'})
        res_other = self.client.get('/private/file/private/seller-documents/seller_owner/doc1.webp')
        self.assertEqual(res_other.status_code, 403)
        self.client.get('/logout')

        # 3. Login as admin_boss and attempt to access seller_owner's document -> 404 (authorized, file missing)
        self.client.post('/login', data={'login_input': 'admin_boss', 'password': 'pass123'})
        res_admin = self.client.get('/private/file/private/seller-documents/seller_owner/doc1.webp')
        self.assertEqual(res_admin.status_code, 404)  # 404 proving authorization passed!

    def test_seller_pdf_export_generation(self):
        """Verify PDF export builds cleanly with store profile."""
        user = User(username='pdf_seller', email='pdf@vkshop.com', role=Role.SELLER, is_active=True)
        user.set_password('pass123')
        db.session.add(user)
        db.session.flush()

        store = StoreProfile(
            user_id=user.id,
            name="PDF Test Store",
            description="Testing PDF generation",
            aadhaar_number="123456789012",
            aadhaar_front="private/seller-documents/pdf_seller/front.webp",
            aadhaar_back="private/seller-documents/pdf_seller/back.webp",
            photo="private/seller-documents/pdf_seller/photo.webp",
            signature="private/seller-documents/pdf_seller/sig.webp",
            status="Pending"
        )
        db.session.add(store)
        db.session.commit()

        pdf_buffer = SellerPdfService.generate_seller_profile_pdf(store)
        self.assertIsNotNone(pdf_buffer)
        pdf_bytes = pdf_buffer.getvalue()
        self.assertTrue(len(pdf_bytes) > 0)
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))

    def test_seller_detail_view_store_permissions(self):
        """Verify View Store route works for pending seller profile when viewed by admin."""
        user = User(username='pending_seller', email='pending@vkshop.com', role=Role.SELLER, is_active=True)
        user.set_password('pass123')
        admin_user = User(username='admin_store_viewer', email='adminview@vkshop.com', role=Role.ADMIN, is_active=True)
        admin_user.set_password('pass123')
        db.session.add_all([user, admin_user])
        db.session.flush()

        store = StoreProfile(user_id=user.id, name="Pending Store", status="Pending")
        db.session.add(store)
        db.session.commit()

        # Anonymous view -> 404
        res_anon = self.client.get(f'/seller/{store.id}')
        self.assertEqual(res_anon.status_code, 404)

        # Logged in admin view -> 200 OK
        self.client.post('/login', data={'login_input': 'admin_store_viewer', 'password': 'pass123'})
        res_admin = self.client.get(f'/seller/{store.id}')
        self.assertEqual(res_admin.status_code, 200)

if __name__ == '__main__':
    unittest.main()
