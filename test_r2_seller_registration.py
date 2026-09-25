import os
os.environ['FLASK_ENV'] = 'testing'
import io
import unittest
from unittest.mock import patch
from app import create_app
from database import db
from models import User, Role, StoreProfile
from services.storage import storage_service

class TestR2SellerRegistration(unittest.TestCase):
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

    def _create_dummy_image(self, name="test.jpg"):
        """Create a minimal valid JPEG image in bytes."""
        from PIL import Image
        buf = io.BytesIO()
        img = Image.new('RGB', (100, 100), color='blue')
        img.save(buf, format='JPEG')
        buf.seek(0)
        return (buf, name)

    def test_seller_registration_all_4_images_success(self):
        """Verify seller registration uploads all 4 documents to storage and creates account."""
        f_front, n_front = self._create_dummy_image('aadhaar_front.jpg')
        f_back, n_back = self._create_dummy_image('aadhaar_back.jpg')
        f_photo, n_photo = self._create_dummy_image('photo.jpg')
        f_sig, n_sig = self._create_dummy_image('signature.jpg')

        data = {
            'username': 'r2_seller_test',
            'email': 'r2seller@vkshop.com',
            'password': 'password123',
            'confirm_password': 'password123',
            'role': Role.SELLER,
            'aadhaar_number': '987654321012',
            'agreed': 'true',
            'aadhaar_front': (f_front, n_front),
            'aadhaar_back': (f_back, n_back),
            'photo': (f_photo, n_photo),
            'signature': (f_sig, n_sig)
        }

        response = self.client.post('/register', data=data, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 302)  # Redirects to login on success

        user = User.query.filter_by(username='r2_seller_test').first()
        self.assertIsNotNone(user)
        self.assertEqual(user.role, Role.SELLER)

        store = StoreProfile.query.filter_by(user_id=user.id).first()
        self.assertIsNotNone(store)

        # Verify ALL 4 image keys exist and start with private/seller-documents/
        self.assertTrue(store.aadhaar_front.startswith('private/seller-documents/r2_seller_test/'))
        self.assertTrue(store.aadhaar_back.startswith('private/seller-documents/r2_seller_test/'))
        self.assertTrue(store.photo.startswith('private/seller-documents/r2_seller_test/'))
        self.assertTrue(store.signature.startswith('private/seller-documents/r2_seller_test/'))

    def test_seller_registration_missing_image_rejection(self):
        """Verify registration fails with 400 when any of the 4 images is missing."""
        f_front, n_front = self._create_dummy_image('aadhaar_front.jpg')

        data = {
            'username': 'incomplete_seller',
            'email': 'incomplete@vkshop.com',
            'password': 'password123',
            'confirm_password': 'password123',
            'role': Role.SELLER,
            'aadhaar_number': '111122223333',
            'agreed': 'true',
            'aadhaar_front': (f_front, n_front),
            # Missing back, photo, signature
        }

        response = self.client.post('/register', data=data, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 400)

        user = User.query.filter_by(username='incomplete_seller').first()
        self.assertIsNone(user)

    def test_seller_registration_oversized_image_rejection(self):
        """Verify registration fails with 400 when an image exceeds 10MB limit."""
        huge_data = io.BytesIO(b'0' * (11 * 1024 * 1024))  # 11MB file
        f_back, n_back = self._create_dummy_image('aadhaar_back.jpg')
        f_photo, n_photo = self._create_dummy_image('photo.jpg')
        f_sig, n_sig = self._create_dummy_image('signature.jpg')

        data = {
            'username': 'huge_file_seller',
            'email': 'huge@vkshop.com',
            'password': 'password123',
            'confirm_password': 'password123',
            'role': Role.SELLER,
            'aadhaar_number': '444455556666',
            'agreed': 'true',
            'aadhaar_front': (huge_data, 'huge_aadhaar.jpg'),
            'aadhaar_back': (f_back, n_back),
            'photo': (f_photo, n_photo),
            'signature': (f_sig, n_sig)
        }

        response = self.client.post('/register', data=data, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 400)

        user = User.query.filter_by(username='huge_file_seller').first()
        self.assertIsNone(user)

if __name__ == '__main__':
    unittest.main()
