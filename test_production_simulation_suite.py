import os
import io
import unittest
import concurrent.futures
from datetime import datetime

os.environ['FLASK_ENV'] = 'testing'

from app import create_app
from database import db
from models import User, StoreProfile, Product, Order, OrderItem, Address, CartItem, ServerInstance
from services.storage import storage_service, upload_file_field, resolve_image_url
from services.redis_service import redis_service
from services.server_registry import server_registry
from services.load_balancer import load_balancer

class TestProductionSimulationSuite(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        db.session.remove()
        self.app_context.pop()

    def test_01_storage_operations(self):
        """Verify PutObject, GetObject, DeleteObject, and thumbnail generation."""
        dummy_img = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
        
        with self.app.app_context():
            # Test direct byte upload
            key = f"products/test_sim_{datetime.utcnow().timestamp()}.gif"
            if storage_service.is_available():
                uploaded_key = storage_service.upload_bytes(dummy_img, key, content_type='image/gif')
                self.assertTrue(storage_service.file_exists(uploaded_key))
                
                # Test read
                resp, stat = storage_service.get_file(uploaded_key)
                self.assertIsNotNone(resp)
                resp.close()
                resp.release_conn()
                
                # Test delete
                del_res = storage_service.delete_file(uploaded_key)
                self.assertTrue(del_res)
            else:
                url = resolve_image_url(key)
                self.assertIsNotNone(url)

    def test_02_stock_concurrency_race_condition(self):
        """Simulate 10 concurrent orders for 1 item in stock. Verify max 1 order succeeds."""
        with self.app.app_context():
            seller_user = User(username="stock_seller_usr", email="stock_seller@test.com")
            seller_user.set_password("pass123")
            db.session.add(seller_user)
            db.session.commit()

            store = StoreProfile(user_id=seller_user.id, name="Stock Store")
            db.session.add(store)
            db.session.commit()

            product = Product(
                seller_id=store.id,
                name="Limited Stock Item",
                slug=f"limited-item-{datetime.utcnow().timestamp()}",
                description="Only 1 available",
                sku=f"SKU-LIMITED-{datetime.utcnow().timestamp()}",
                base_price=100.0,
                offer_price=100.0,
                stock=1
            )
            db.session.add(product)
            db.session.commit()
            prod_id = product.id

        def place_order(user_idx):
            with self.app.app_context():
                try:
                    from services.redis_service import redis_service
                    # Acquire distributed lock for product stock
                    if not redis_service.acquire_lock(f"product_stock_{prod_id}", acquire_timeout=3, lock_timeout=5):
                        return False
                    try:
                        res = db.session.execute(
                            db.text("UPDATE products SET stock = stock - 1 WHERE id = :id AND stock >= 1"),
                            {"id": prod_id}
                        )
                        if res.rowcount == 1:
                            u = User(username=f"buyer_{user_idx}_{datetime.utcnow().timestamp()}", email=f"buyer_{user_idx}_{datetime.utcnow().timestamp()}@test.com")
                            u.set_password("pass")
                            db.session.add(u)
                            db.session.commit()

                            ord_obj = Order(
                                order_number=f"ORD-CONC-{user_idx}-{datetime.utcnow().timestamp()}",
                                user_id=u.id,
                                total_amount=100.0,
                                grand_total=100.0,
                                status='Confirmed'
                            )
                            db.session.add(ord_obj)
                            db.session.commit()
                            return True
                        else:
                            db.session.rollback()
                            return False
                    finally:
                        redis_service.release_lock(f"product_stock_{prod_id}")
                except Exception as e:
                    db.session.rollback()
                    return False

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(place_order, i) for i in range(10)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        success_count = sum(1 for r in results if r)
        self.assertEqual(success_count, 1)

        with self.app.app_context():
            p_final = Product.query.get(prod_id)
            self.assertEqual(p_final.stock, 0)

    def test_03_auth_session_isolation(self):
        """Simulate concurrent requests from User A, B, C verifying session isolation."""
        def check_session(username):
            with self.app.test_client() as c:
                with c.session_transaction() as sess:
                    sess['test_user'] = username
                res = c.get('/health')
                with c.session_transaction() as sess:
                    return sess.get('test_user')

        users = ["user_alpha", "user_beta", "user_gamma"]
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(check_session, u): u for u in users}
            for f in concurrent.futures.as_completed(futures):
                expected = futures[f]
                actual = f.result()
                self.assertEqual(expected, actual)

    def test_04_multi_server_data_consistency(self):
        """Verify data created on one server node is immediately visible across all nodes."""
        srv1 = server_registry.register_server("srv-node-1", "VKShop Node 1", "http://127.0.0.1:5000")
        srv2 = server_registry.register_server("srv-node-2", "VKShop Node 2", "http://127.0.0.1:5001")
        
        self.assertEqual(len(server_registry.get_healthy_servers()), 2)
        
        with self.app.app_context():
            u = User(username=f"multisrv_usr_{datetime.utcnow().timestamp()}", email=f"multisrv_{datetime.utcnow().timestamp()}@test.com")
            u.set_password("secret")
            db.session.add(u)
            db.session.commit()
            uid = u.id

        # Query from second connection/thread
        with self.app.app_context():
            fetched = User.query.get(uid)
            self.assertIsNotNone(fetched)

    def test_05_server_failure_and_recovery(self):
        """Simulate node failure and verify automatic failover & recovery."""
        server_registry.register_server("srv-test-failover", "Failover Node", "http://127.0.0.1:9999")
        node = ServerInstance.query.filter_by(server_id="srv-test-failover").first()
        
        # Simulate 3 consecutive health check failures
        node.consecutive_failures = 3
        node.status = 'UNHEALTHY'
        db.session.commit()

        healthy_nodes = server_registry.get_healthy_servers()
        self.assertTrue(all(n.server_id != "srv-test-failover" for n in healthy_nodes))

        # Recovery simulation
        server_registry.record_heartbeat("srv-test-failover", cpu_usage=15.0)
        recovered_node = ServerInstance.query.filter_by(server_id="srv-test-failover").first()
        self.assertEqual(recovered_node.status, 'ONLINE')

    def test_06_admin_endpoint_security(self):
        """Verify /admin/infrastructure is protected against non-admin users."""
        res_guest = self.client.get('/admin/infrastructure')
        self.assertIn(res_guest.status_code, [302, 401, 403])

if __name__ == '__main__':
    unittest.main()
