import unittest
import os
import sys
import uuid
import io
from unittest.mock import patch, MagicMock, ANY

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from services.storage import (
    storage_service,
    sanitize_object_key,
    generate_object_key,
    resolve_image_url,
    optimize_image_bytes,
    upload_file_field
)


class TestStep6bR2Configuration(unittest.TestCase):
    """Test suite for STEP 6B Cloudflare R2 configuration & security requirements."""

    def test_r2_endpoint_cleaning(self):
        """Verify endpoint string is cleaned of protocol prefixes and trailing slashes."""
        with patch.dict(os.environ, {
            'MINIO_ENDPOINT': 'https://abcdef1234567890.r2.cloudflarestorage.com///',
            'MINIO_ACCESS_KEY': 'test_acc_key',
            'MINIO_SECRET_KEY': 'test_sec_key',
            'MINIO_BUCKET_NAME': 'vkshop-uploads',
            'MINIO_SECURE': 'True'
        }):
            from services.storage import StorageService
            svc = StorageService()
            with patch('services.storage.Minio') as mock_minio:
                with patch.object(svc, 'ensure_bucket'):
                    _ = svc.client
                    mock_minio.assert_called_once_with(
                        'abcdef1234567890.r2.cloudflarestorage.com',
                        access_key='test_acc_key',
                        secret_key='test_sec_key',
                        secure=True,
                        http_client=ANY
                    )

    def test_public_asset_url_generation(self):
        """Verify public objects return STORAGE_PUBLIC_URL + key without double slashes."""
        with patch.dict(os.environ, {
            'STORAGE_PUBLIC_URL': 'https://pub-r2.vkshop.com/',
            'FLASK_ENV': 'testing'
        }):
            url1 = resolve_image_url('products/item1.webp')
            self.assertEqual(url1, 'https://pub-r2.vkshop.com/products/item1.webp')

            url2 = resolve_image_url('stores/logo.webp')
            self.assertEqual(url2, 'https://pub-r2.vkshop.com/stores/logo.webp')

    def test_private_file_protection_against_public_cdn(self):
        """Verify private files never use STORAGE_PUBLIC_URL."""
        with patch.dict(os.environ, {
            'STORAGE_PUBLIC_URL': 'https://pub-r2.vkshop.com/',
            'FLASK_ENV': 'testing'
        }):
            url_doc = resolve_image_url('private/seller-documents/12/front.webp')
            self.assertEqual(url_doc, '/private/file/private/seller-documents/12/front.webp')
            self.assertNotIn('pub-r2.vkshop.com', url_doc)

            url_pay = resolve_image_url('private/payment/receipt.webp')
            self.assertEqual(url_pay, '/private/file/private/payment/receipt.webp')
            self.assertNotIn('pub-r2.vkshop.com', url_pay)

    def test_path_traversal_sanitization(self):
        """Verify sanitize_object_key strips path traversal sequences."""
        dirty_key = "../../../etc/passwd"
        clean_key = sanitize_object_key(dirty_key)
        self.assertEqual(clean_key, "etc/passwd")

        win_key = "C:\\Windows\\System32\\test.png"
        clean_win = sanitize_object_key(win_key)
        self.assertEqual(clean_win, "Windows/System32/test.png")

    def test_uuid_object_key_generation(self):
        """Verify generate_object_key uses UUID and correct extensions."""
        key = generate_object_key('products', 'my_original_photo.JPG')
        self.assertTrue(key.startswith('products/'))
        self.assertTrue(key.endswith('.jpg'))
        self.assertNotIn('my_original_photo', key)

    def test_live_r2_connection_if_credentials_present(self):
        """
        If R2 credentials exist in environment, run a safe non-destructive upload & delete test.
        Otherwise, skip gracefully.
        """
        endpoint = os.environ.get('MINIO_ENDPOINT')
        access_key = os.environ.get('MINIO_ACCESS_KEY')
        secret_key = os.environ.get('MINIO_SECRET_KEY')

        if not all([endpoint, access_key, secret_key]):
            self.skipTest("Live Cloudflare R2 credentials not present in environment; skipping live network connection test.")

        # Real connection test
        test_key = f"__vkshop_preflight__/test-{uuid.uuid4().hex}.txt"
        test_content = b"VKShop Cloudflare R2 Preflight Connection Verification"

        # 1. Upload
        uploaded_key = storage_service.upload_bytes(test_content, test_key, content_type='text/plain')
        self.assertEqual(uploaded_key, test_key)

        # 2. File exists check
        self.assertTrue(storage_service.file_exists(test_key))

        # 3. Delete
        deleted = storage_service.delete_file(test_key)
        self.assertTrue(deleted)

        # 4. Verify gone
        self.assertFalse(storage_service.file_exists(test_key))

    def test_live_r2_image_optimization_and_upload_if_credentials_present(self):
        """
        If R2 credentials exist, test Pillow image optimization + upload to temporary R2 key.
        Otherwise, skip gracefully.
        """
        endpoint = os.environ.get('MINIO_ENDPOINT')
        access_key = os.environ.get('MINIO_ACCESS_KEY')
        secret_key = os.environ.get('MINIO_SECRET_KEY')

        if not all([endpoint, access_key, secret_key]):
            self.skipTest("Live Cloudflare R2 credentials not present in environment; skipping live image upload test.")

        # Create 100x100 RGB test image
        from PIL import Image
        img_buf = io.BytesIO()
        test_img = Image.new('RGB', (100, 100), color='blue')
        test_img.save(img_buf, format='JPEG')
        raw_bytes = img_buf.getvalue()

        # Optimize
        opt_bytes, mime, ext = optimize_image_bytes(raw_bytes)
        self.assertEqual(mime, 'image/webp')
        self.assertEqual(ext, '.webp')

        # Upload
        test_key = f"__vkshop_preflight__/test_img-{uuid.uuid4().hex}.webp"
        uploaded_key = storage_service.upload_bytes(opt_bytes, test_key, content_type=mime)
        self.assertEqual(uploaded_key, test_key)

        # Cleanup
        storage_service.delete_file(test_key)
        self.assertFalse(storage_service.file_exists(test_key))


if __name__ == '__main__':
    unittest.main()
