import os
import unittest
import concurrent.futures

os.environ['FLASK_ENV'] = 'testing'

from app import create_app
from database import db
from models import User, Product, Category, ServerInstance
from services.storage import storage_service, resolve_image_url
from services.redis_service import redis_service
from services.server_registry import server_registry

class TestMultiServerAndConcurrency(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        db.session.remove()
        self.app_context.pop()

    def test_liveness_and_readiness_probes(self):
        """Verify /health and /ready return HTTP 200 without crashing."""
        res = self.client.get('/health')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'healthy')

        res_ready = self.client.get('/ready')
        self.assertEqual(res_ready.status_code, 200)
        data_ready = res_ready.get_json()
        self.assertEqual(data_ready['database'], 'connected')

    def test_s3_access_denied_resilience(self):
        """Verify storage_service.ensure_bucket handles AccessDenied safely."""
        from unittest.mock import MagicMock
        with self.app.app_context():
            mock_cli = MagicMock()
            mock_cli.bucket_exists.side_class = Exception("AccessDenied: Access Denied to ListBucket")
            mock_cli.bucket_exists.side_effect = Exception("AccessDenied: Access Denied to ListBucket")
            original_client = storage_service._client
            storage_service._client = mock_cli
            storage_service._bucket_checked = False
            try:
                res = storage_service.ensure_bucket()
                self.assertTrue(res)
            finally:
                storage_service._client = original_client
                storage_service._bucket_checked = False

    def test_resolve_image_url_fallbacks(self):
        """Verify resolve_image_url never returns empty or invalid links."""
        url1 = resolve_image_url("products/test.webp")
        self.assertTrue("products/test.webp" in url1)

        url_null = resolve_image_url(None)
        self.assertEqual(url_null, "/static/uploads/placeholder.jpg")

    def test_redis_service_fallback(self):
        """Verify redis_service get/set/lock operations work cleanly."""
        res_set = redis_service.set("test_key", "test_val", ttl_seconds=10)
        self.assertTrue(res_set)
        res_get = redis_service.get("test_key")
        self.assertEqual(res_get, "test_val")

    def test_server_registration_and_heartbeat(self):
        """Verify multi-server node registration and heartbeat updates."""
        srv = server_registry.register_server(
            server_id="test-srv-1",
            name="Test Render Node 1",
            api_endpoint="http://127.0.0.1:5000"
        )
        self.assertIsNotNone(srv)
        self.assertEqual(srv.status, 'ONLINE')

        server_registry.record_heartbeat("test-srv-1", cpu_usage=25.5, memory_usage=40.0)
        fetched = ServerInstance.query.filter_by(server_id="test-srv-1").first()
        self.assertEqual(fetched.cpu_usage, 25.5)

    def test_rest_api_endpoints_for_mobile_app(self):
        """Verify products and categories REST API endpoints return JSON for Android App."""
        res = self.client.get('/api/products')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])

        res_cat = self.client.get('/api/categories')
        self.assertEqual(res_cat.status_code, 200)

    def test_concurrent_requests_stress(self):
        """Stress-test 50 concurrent requests against the application."""
        def make_req(idx):
            with self.app.test_client() as c:
                return c.get('/health').status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_req, i) for i in range(50)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        self.assertEqual(len(results), 50)
        self.assertTrue(all(code == 200 for code in results))

if __name__ == '__main__':
    unittest.main()
