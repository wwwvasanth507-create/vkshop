import unittest
import os
import sys
from unittest.mock import patch

# Ensure root workspace is in path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from config import Config, ProductionConfig, DevelopmentConfig
from app import create_app
from services.storage import resolve_image_url


class TestRenderProductionConfig(unittest.TestCase):
    """Test suite for STEP 4 Render production deployment configuration requirements."""

    def test_postgres_url_normalization(self):
        """Verify postgres:// is converted to postgresql+psycopg:// in database URI."""
        with patch.dict(os.environ, {
            'DATABASE_URL': 'postgres://user:pass@ep-host.render.com/vdb',
            'FLASK_ENV': 'production'
        }):
            from importlib import reload
            import config
            reload(config)
            self.assertEqual(
                config.Config.SQLALCHEMY_DATABASE_URI,
                'postgresql+psycopg://user:pass@ep-host.render.com/vdb'
            )

    def test_missing_postgres_in_production_raises_error(self):
        """Verify missing PostgreSQL in FLASK_ENV=production raises RuntimeError."""
        env_without_db = {
            'FLASK_ENV': 'production',
            'DATABASE_URL': '',
            'POSTGRES_USER': '',
            'POSTGRES_PASSWORD': '',
            'POSTGRES_HOST': '',
            'POSTGRES_PORT': '',
            'POSTGRES_DB': ''
        }
        with patch.dict(os.environ, env_without_db, clear=True):
            from importlib import reload
            import config
            with self.assertRaises(RuntimeError) as ctx:
                reload(config)
            self.assertIn("Production mode requires PostgreSQL", str(ctx.exception))

    def test_production_local_fallback_disabled_by_default(self):
        """Verify ALLOW_LOCAL_STORAGE_FALLBACK defaults to False in production mode."""
        env_prod = {
            'FLASK_ENV': 'production',
            'DATABASE_URL': 'postgresql://u:p@localhost:5432/db'
        }
        with patch.dict(os.environ, env_prod):
            from importlib import reload
            import config
            reload(config)
            self.assertFalse(config.Config.ALLOW_LOCAL_STORAGE_FALLBACK)

    def test_health_endpoint(self):
        """Verify /health endpoint returns HTTP 200 and status ok."""
        with patch.dict(os.environ, {
            'FLASK_ENV': 'testing',
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'
        }):
            app = create_app()
            client = app.test_client()
            response = client.get('/health')
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertIsNotNone(data)
            self.assertIn(data.get('status'), ['healthy', 'ok'])

    def test_public_image_url_resolution_with_cdn(self):
        """Verify resolve_image_url prepends STORAGE_PUBLIC_URL when set."""
        with patch.dict(os.environ, {
            'STORAGE_PUBLIC_URL': 'https://cdn.vkshop.com',
            'FLASK_ENV': 'testing'
        }):
            from services import storage
            from importlib import reload
            reload(storage)
            url = storage.resolve_image_url('products/test_image.webp')
            self.assertEqual(url, 'https://cdn.vkshop.com/products/test_image.webp')

    def test_private_file_unauthorized_rejection(self):
        """Verify unauthorized request to /private/file returns 401."""
        with patch.dict(os.environ, {
            'FLASK_ENV': 'testing',
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'
        }):
            app = create_app()
            client = app.test_client()
            res = client.get('/private/file/private/seller-documents/1/doc.webp')
            self.assertEqual(res.status_code, 401)

    def test_gunicorn_port_configuration(self):
        """Verify gunicorn.conf.py reads PORT environment variable correctly."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("gconf", os.path.join(os.path.dirname(__file__), "gunicorn.conf.py"))
        
        with patch.dict(os.environ, {'PORT': '10000'}):
            gconf = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(gconf)
            self.assertEqual(gconf.bind, '0.0.0.0:10000')

        with patch.dict(os.environ, {'PORT': '5000'}):
            gconf = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(gconf)
            self.assertEqual(gconf.bind, '0.0.0.0:5000')


if __name__ == '__main__':
    unittest.main()
