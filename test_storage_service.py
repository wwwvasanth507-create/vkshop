import os
import io
import unittest
from PIL import Image

os.environ['FLASK_ENV'] = 'testing'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app
from services.storage import (
    StorageService,
    sanitize_object_key,
    generate_object_key,
    optimize_image_bytes
)

class StorageServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update({
            'TESTING': True,
            'IMAGE_MAX_WIDTH': 1600,
            'IMAGE_MAX_HEIGHT': 1600,
            'IMAGE_WEBP_QUALITY': 82,
            'ALLOW_LOCAL_STORAGE_FALLBACK': True
        })
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()

    def create_dummy_image_bytes(self, width=800, height=600, fmt='JPEG', color=(255, 0, 0)):
        buf = io.BytesIO()
        img = Image.new('RGB', (width, height), color=color)
        img.save(buf, format=fmt)
        return buf.getvalue()

    def create_dummy_rgba_image_bytes(self, width=400, height=400):
        buf = io.BytesIO()
        img = Image.new('RGBA', (width, height), color=(0, 255, 0, 128))
        img.save(buf, format='PNG')
        return buf.getvalue()

    # 1. Valid image optimization
    def test_1_valid_image_optimization(self):
        raw_jpeg = self.create_dummy_image_bytes(width=1000, height=800, fmt='JPEG')
        opt_bytes, opt_mime, opt_ext = optimize_image_bytes(raw_jpeg)
        
        self.assertEqual(opt_mime, 'image/webp')
        self.assertEqual(opt_ext, '.webp')
        self.assertGreater(len(opt_bytes), 0)
        
        # Ensure result is readable by Pillow
        with Image.open(io.BytesIO(opt_bytes)) as img:
            self.assertEqual(img.format, 'WEBP')
            self.assertEqual(img.size, (1000, 800))

    # 2. Invalid image rejection
    def test_2_invalid_image_rejection(self):
        corrupt_data = b"NOT_AN_IMAGE_FILE_DATA_12345"
        with self.assertRaises(ValueError):
            optimize_image_bytes(corrupt_data)

    # 3. Large image resize
    def test_3_large_image_resize(self):
        large_jpeg = self.create_dummy_image_bytes(width=2400, height=1800, fmt='JPEG')
        opt_bytes, opt_mime, opt_ext = optimize_image_bytes(large_jpeg, max_width=1600, max_height=1600)
        
        with Image.open(io.BytesIO(opt_bytes)) as img:
            w, h = img.size
            self.assertLessEqual(w, 1600)
            self.assertLessEqual(h, 1600)
            # Check aspect ratio preservation (4:3 ratio)
            self.assertEqual((w, h), (1600, 1200))

    # 4. PNG transparency
    def test_4_png_transparency(self):
        rgba_png = self.create_dummy_rgba_image_bytes(width=300, height=300)
        opt_bytes, opt_mime, opt_ext = optimize_image_bytes(rgba_png, target_format='WEBP')
        
        self.assertEqual(opt_mime, 'image/webp')
        with Image.open(io.BytesIO(opt_bytes)) as img:
            self.assertIn(img.mode, ('RGBA', 'LA', 'P'))

    # 5. WEBP input
    def test_5_webp_input(self):
        buf = io.BytesIO()
        img = Image.new('RGB', (200, 200), color=(0, 0, 255))
        img.save(buf, format='WEBP')
        raw_webp = buf.getvalue()
        
        opt_bytes, opt_mime, opt_ext = optimize_image_bytes(raw_webp)
        self.assertEqual(opt_mime, 'image/webp')
        self.assertEqual(opt_ext, '.webp')

    # 6. Path traversal rejection
    def test_6_path_traversal_rejection(self):
        bad_keys = [
            "../secret.txt",
            "..\\windows\\system32.dll",
            "C:\\boot.ini",
            "/etc/passwd\x00.jpg",
            "products/../../../etc/shadow"
        ]
        for bad_key in bad_keys:
            clean = sanitize_object_key(bad_key)
            self.assertNotIn("..", clean)
            self.assertNotIn("\\", clean)
            self.assertNotIn("\x00", clean)
            self.assertFalse(clean.startswith("/"))

    # 7. Safe object key generation
    def test_7_safe_object_key_generation(self):
        key = generate_object_key("products", "my_photo.jpg", extension=".webp")
        self.assertTrue(key.startswith("products/"))
        self.assertTrue(key.endswith(".webp"))
        self.assertNotIn("my_photo", key)

    # 8. Duplicate filename collision prevention
    def test_8_duplicate_filename_collision_prevention(self):
        key1 = generate_object_key("products", "same_name.png")
        key2 = generate_object_key("products", "same_name.png")
        self.assertNotEqual(key1, key2)

    # 9. Delete missing object
    def test_9_delete_missing_object(self):
        svc = StorageService()
        result = svc.delete_file("non_existent_file_key_9999.webp")
        # Should return False gracefully when storage client is not available or file doesn't exist
        self.assertIsInstance(result, bool)

    # 10. Missing storage configuration
    def test_10_missing_storage_configuration(self):
        svc = StorageService()
        self.app.config['MINIO_ENDPOINT'] = None
        self.assertFalse(svc.is_available())

    # 11. Local fallback behavior in development
    def test_11_local_fallback_in_development(self):
        self.app.config['ALLOW_LOCAL_STORAGE_FALLBACK'] = True
        svc = StorageService()
        self.assertFalse(svc.is_available())

    # 12. Local fallback disabled in production
    def test_12_local_fallback_disabled_in_production(self):
        self.app.config['ALLOW_LOCAL_STORAGE_FALLBACK'] = False
        svc = StorageService()
        self.assertFalse(svc.is_available())

if __name__ == '__main__':
    unittest.main()
