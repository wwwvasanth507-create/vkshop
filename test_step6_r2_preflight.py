import unittest
import os
import sys
from unittest.mock import patch, MagicMock, ANY

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))


class TestStep6R2Preflight(unittest.TestCase):
    """Test suite for STEP 6A Cloudflare R2 + Render deployment preflight validation."""

    def test_r2_endpoint_sanitization(self):
        """Verify storage_service normalizes R2 endpoints with https:// prefixes and trailing slashes."""
        with patch.dict(os.environ, {
            'MINIO_ENDPOINT': 'https://1234567890abcdef.r2.cloudflarestorage.com/',
            'MINIO_ACCESS_KEY': 'dummy_access_key',
            'MINIO_SECRET_KEY': 'dummy_secret_key',
            'MINIO_BUCKET_NAME': 'vkshop-uploads',
            'MINIO_SECURE': 'True'
        }):
            from services.storage import StorageService
            storage = StorageService()
            
            with patch('services.storage.Minio') as mock_minio:
                with patch.object(storage, 'ensure_bucket') as mock_bucket:
                    _ = storage.client
                    mock_minio.assert_called_once_with(
                        '1234567890abcdef.r2.cloudflarestorage.com',
                        access_key='dummy_access_key',
                        secret_key='dummy_secret_key',
                        secure=True,
                        http_client=ANY
                    )

    def test_r2_public_url_resolution(self):
        """Verify STORAGE_PUBLIC_URL formats R2 public object keys without double slashes."""
        with patch.dict(os.environ, {
            'STORAGE_PUBLIC_URL': 'https://pub-1234.r2.dev/',
            'FLASK_ENV': 'testing'
        }):
            from services.storage import resolve_image_url
            url = resolve_image_url('products/test_product_123.webp')
            self.assertEqual(url, 'https://pub-1234.r2.dev/products/test_product_123.webp')

    def test_r2_private_file_protection(self):
        """Verify private seller documents never use STORAGE_PUBLIC_URL."""
        with patch.dict(os.environ, {
            'STORAGE_PUBLIC_URL': 'https://pub-1234.r2.dev/',
            'FLASK_ENV': 'testing'
        }):
            from services.storage import resolve_image_url
            url = resolve_image_url('private/seller-documents/10/aadhaar.webp')
            self.assertEqual(url, '/private/file/private/seller-documents/10/aadhaar.webp')
            self.assertFalse(url.startswith('https://pub-1234.r2.dev'))

    def test_no_local_fallback_in_production(self):
        """Verify upload_file_field returns error when persistent storage is unavailable in production."""
        from app import create_app
        with patch.dict(os.environ, {
            'FLASK_ENV': 'testing',
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
            'ALLOW_LOCAL_STORAGE_FALLBACK': 'False'
        }):
            app = create_app()
            with app.test_request_context():
                from services.storage import upload_file_field, storage_service
                mock_file = MagicMock()
                mock_file.filename = 'test.jpg'
                mock_file.content_type = 'image/jpeg'
                mock_file.stream.read.return_value = b'fake image data'
                
                with patch.object(storage_service, 'is_available', return_value=False):
                    key, err = upload_file_field(mock_file, 'products')
                    self.assertIsNone(key)
                    self.assertIn("Persistent object storage is unavailable", err)

    def test_render_yaml_has_r2_placeholders(self):
        """Verify render.yaml contains required S3/R2 environment variable specifications."""
        render_path = os.path.join(os.path.dirname(__file__), 'render.yaml')
        with open(render_path, 'r', encoding='utf-8') as f:
            content = f.read()

        required_vars = [
            'STORAGE_PROVIDER',
            'MINIO_ENDPOINT',
            'MINIO_ACCESS_KEY',
            'MINIO_SECRET_KEY',
            'MINIO_BUCKET_NAME',
            'MINIO_SECURE',
            'STORAGE_PUBLIC_URL',
            'ALLOW_LOCAL_STORAGE_FALLBACK'
        ]
        for var in required_vars:
            self.assertIn(var, content)


if __name__ == '__main__':
    unittest.main()
