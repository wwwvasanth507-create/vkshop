import os
os.environ['FLASK_ENV'] = 'testing'
import unittest
from unittest.mock import patch
import json
import re
from app import create_app
from database import db
from models import Product, Category, StoreProfile, User

class TestGatewayArchitecture(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_permanent_gateway_url_configuration(self):
        """Verify PERMANENT_GATEWAY_URL defaults to home.vkshop.workers.dev and environment overrides work."""
        self.assertEqual(self.app.config['PERMANENT_GATEWAY_URL'], 'https://home.vkshop.workers.dev')
        
        # Test override via environment
        with patch.dict(os.environ, {'GATEWAY_URL': 'https://custom-gateway.domain.com', 'ORIGIN_URL': 'http://custom-origin:8080'}):
            custom_app = create_app()
            self.assertEqual(custom_app.config['PERMANENT_GATEWAY_URL'], 'https://custom-gateway.domain.com')
            self.assertEqual(custom_app.config['ORIGIN_URL'], 'http://custom-origin:8080')

    def test_gateway_config_api_endpoint(self):
        """Verify GET /api/gateway/config returns expected gateway and origin parameters."""
        response = self.client.get('/api/gateway/config')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertEqual(data['gateway_url'], 'https://home.vkshop.workers.dev')
        self.assertEqual(data['status'], 'operational')
        self.assertIn('origin_url', data)
        self.assertIn('app_url', data)

    def test_no_hardcoded_temporary_domains_in_source_code(self):
        """Audit source code files to guarantee zero hard-coded temporary domains exist."""
        forbidden_domains = ['vkshop.dpdns.org', 'vkshop.onrender.com']
        root_dir = os.path.abspath(os.path.dirname(__file__))
        
        source_extensions = ('.py', '.dart', '.js', '.json', '.html', '.css', '.sh')
        ignore_dirs = {'.git', 'venv', '__pycache__', 'logs', 'backups', 'database'}
        
        violations = []
        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames[:] = [d for d in dirnames if d not in ignore_dirs]
            for fname in filenames:
                if fname.endswith(source_extensions) and not fname.startswith('test_'):
                    fpath = os.path.join(dirpath, fname)
                    try:
                        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            for domain in forbidden_domains:
                                if domain in content:
                                    rel_path = os.path.relpath(fpath, root_dir)
                                    violations.append(f"{rel_path}: contains '{domain}'")
                    except Exception:
                        pass
                        
        self.assertEqual(len(violations), 0, f"Found hardcoded temporary domain violations: {violations}")

    def test_existing_apis_still_working(self):
        """Verify core existing APIs (/health, /api/search-suggestions, /api/cart/items-count) work seamlessly."""
        # 1. Health check endpoint
        res_health = self.client.get('/health')
        self.assertEqual(res_health.status_code, 200)
        data_health = json.loads(res_health.data)
        self.assertEqual(data_health['status'], 'healthy')

        # 2. Search suggestions endpoint
        res_search = self.client.get('/api/search-suggestions?q=test')
        self.assertEqual(res_search.status_code, 200)

        # 3. Cart items count endpoint
        res_cart = self.client.get('/api/cart/items-count')
        self.assertEqual(res_cart.status_code, 200)
        data_cart = json.loads(res_cart.data)
        self.assertIn('count', data_cart)

if __name__ == '__main__':
    import unittest.mock
    unittest.main()
