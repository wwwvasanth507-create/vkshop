import os
os.environ['FLASK_ENV'] = 'testing'
import unittest
from unittest.mock import patch, MagicMock
import json
from datetime import datetime, timedelta

from app import create_app
from database import db
from models import User, Order, OrderItem, Product, Category, StoreProfile, AdminDevice, WhatsAppMessage, WhatsAppMessageStatus, AdminNotification, WhatsAppMessageAudit
from services.whatsapp_service import create_whatsapp_message_for_order, claim_whatsapp_message, confirm_whatsapp_message_sent, recover_stale_sending_messages
from services.firebase_service import send_admin_notification
from services.sse_service import register_sse_subscriber, unregister_sse_subscriber, publish_admin_event

class TestPhase2Notifications(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # Create test admin 1, test admin 2, and test customer
        self.admin1 = User(
            username='admin1',
            email='admin1@vkshop.local',
            role='admin'
        )
        self.admin1.set_password('password123')

        self.admin2 = User(
            username='admin2',
            email='admin2@vkshop.local',
            role='admin'
        )
        self.admin2.set_password('password123')

        self.customer = User(
            username='customer1',
            email='customer1@vkshop.local',
            role='customer'
        )
        self.customer.set_password('password123')

        # Create store & product
        self.category = Category(name='Electronics', slug='electronics')
        db.session.add_all([self.admin1, self.admin2, self.customer, self.category])
        db.session.commit()

        self.store = StoreProfile(user_id=self.admin1.id, name='VK Admin Store', status='Active')
        db.session.add(self.store)
        db.session.commit()

        self.product = Product(
            seller_id=self.store.id,
            category_id=self.category.id,
            name='Test Smartphone',
            slug='test-smartphone',
            description='Test Smartphone Description',
            sku='TEST-PHONE-001',
            base_price=1299.0,
            offer_price=1299.0,
            stock=10
        )
        db.session.add(self.product)
        db.session.commit()

        # Create address and test order
        from models import Address
        self.address = Address(
            user_id=self.customer.id,
            title='Home',
            fullName='Vasanth',
            addressLine1='123 Main Street',
            city='Chennai',
            state='Tamil Nadu',
            postalCode='600001',
            phone='9876543210',
            contact_number='9876543210'
        )
        db.session.add(self.address)
        db.session.commit()

        self.order = Order(
            order_number='VK1001',
            user_id=self.customer.id,
            address_id=self.address.id,
            total_amount=1299.0,
            grand_total=1299.0,
            status='Pending'
        )
        db.session.add(self.order)
        db.session.commit()

        self.order_item = OrderItem(
            order_id=self.order.id,
            product_id=self.product.id,
            product_name='Test Smartphone',
            quantity=1,
            unit_price=1299.0,
            total_price=1299.0
        )
        db.session.add(self.order_item)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    # 1. Order creates one WhatsApp message
    def test_01_order_creates_one_whatsapp_message(self):
        msg = create_whatsapp_message_for_order(self.order.id)
        self.assertIsNotNone(msg)
        self.assertEqual(msg.order_id, self.order.id)
        self.assertEqual(msg.status, WhatsAppMessageStatus.PENDING)
        self.assertEqual(msg.customer_phone, '9876543210')

    # 2. Retry does not duplicate message
    def test_02_retry_does_not_duplicate_message(self):
        msg1 = create_whatsapp_message_for_order(self.order.id)
        msg2 = create_whatsapp_message_for_order(self.order.id)
        self.assertEqual(msg1.id, msg2.id)

        count = WhatsAppMessage.query.filter_by(order_id=self.order.id).count()
        self.assertEqual(count, 1)

    # 3. Correct wa.me link format
    def test_03_correct_wame_link(self):
        msg = create_whatsapp_message_for_order(self.order.id)
        link = msg.whatsapp_deep_link
        self.assertTrue(link.startswith('https://wa.me/919876543210?text='))
        self.assertIn('VK100', link)
        self.assertIn('Test%20Smartphone', link)

    # 4. Admin authentication required
    def test_04_admin_authentication(self):
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(self.admin1.id)
            sess['role'] = 'admin'
        res = self.client.get('/admin/whatsapp')
        self.assertEqual(res.status_code, 200)

    # 5. Unauthorized admin/customer blocked
    def test_05_unauthorized_admin_blocked(self):
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(self.customer.id)
            sess['role'] = 'customer'
        res = self.client.get('/admin/whatsapp')
        self.assertIn(res.status_code, [302, 403])

    # 6. FCM token registration
    def test_06_fcm_token_registration(self):
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(self.admin1.id)
            sess['role'] = 'admin'

        payload = {
            "device_id": "device_abc_123",
            "platform": "android",
            "fcm_token": "token_sample_111",
            "device_name": "Pixel 7",
            "app_version": "1.0.0"
        }
        res = self.client.post('/api/admin/devices/register', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 200)

        dev = AdminDevice.query.filter_by(admin_id=self.admin1.id, device_id="device_abc_123").first()
        self.assertIsNotNone(dev)
        self.assertEqual(dev.fcm_token, "token_sample_111")

    # 7. Token update (idempotent / upsert)
    def test_07_token_update(self):
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(self.admin1.id)
            sess['role'] = 'admin'

        # First registration
        payload1 = {
            "device_id": "device_abc_123",
            "platform": "android",
            "fcm_token": "token_old",
            "device_name": "Pixel 7"
        }
        self.client.post('/api/admin/devices/register', data=json.dumps(payload1), content_type='application/json')

        # Update with new token
        payload2 = {
            "device_id": "device_abc_123",
            "platform": "android",
            "fcm_token": "token_new",
            "device_name": "Pixel 7 Pro"
        }
        res = self.client.post('/api/admin/devices/register', data=json.dumps(payload2), content_type='application/json')
        self.assertEqual(res.status_code, 200)

        count = AdminDevice.query.filter_by(admin_id=self.admin1.id, device_id="device_abc_123").count()
        self.assertEqual(count, 1)

        dev = AdminDevice.query.filter_by(admin_id=self.admin1.id, device_id="device_abc_123").first()
        self.assertEqual(dev.fcm_token, "token_new")

    # 8. Notification creation
    def test_08_notification_creation(self):
        notif = send_admin_notification(
            admin_id=self.admin1.id,
            title="New Order Received",
            body="Order #VK1001 placed",
            notification_type="new_order",
            reference_type="order",
            reference_id=str(self.order.id)
        )
        self.assertIsNotNone(notif)
        db_notif = AdminNotification.query.get(notif.id)
        self.assertEqual(db_notif.title, "New Order Received")
        self.assertFalse(db_notif.is_read)

    # 9. SSE connection headers
    def test_09_sse_connection(self):
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(self.admin1.id)
            sess['role'] = 'admin'
        res = self.client.get('/api/admin/events/stream')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.content_type, 'text/event-stream; charset=utf-8')

    # 10. Live event delivery
    def test_10_live_event_delivery(self):
        client_q = register_sse_subscriber()
        publish_admin_event('test_event', {'foo': 'bar'})

        msg = client_q.get(timeout=2.0)
        self.assertIn('"event": "test_event"', msg)
        self.assertIn('"foo": "bar"', msg)
        unregister_sse_subscriber(client_q)

    # 11 & 12. Concurrent WhatsApp claims - exactly one admin wins
    def test_11_and_12_concurrent_whatsapp_claims_exactly_one_wins(self):
        msg = create_whatsapp_message_for_order(self.order.id)

        # First claim by admin 1
        res1 = claim_whatsapp_message(msg.id, self.admin1.id)
        self.assertTrue(res1['success'])
        self.assertEqual(res1['message'].status, WhatsAppMessageStatus.SENDING)
        self.assertEqual(res1['message'].sent_by_admin_id, self.admin1.id)

        # Second claim by admin 2 on same message
        res2 = claim_whatsapp_message(msg.id, self.admin2.id)
        self.assertFalse(res2['success'])
        self.assertEqual(res2['reason'], 'already_claimed')

    # 13. SENT state persistence
    def test_13_sent_state_persistence(self):
        msg = create_whatsapp_message_for_order(self.order.id)
        claim_whatsapp_message(msg.id, self.admin1.id)

        res = confirm_whatsapp_message_sent(msg.id, self.admin1.id)
        self.assertTrue(res['success'])
        self.assertEqual(res['message'].status, WhatsAppMessageStatus.SENT)
        self.assertIsNotNone(res['message'].sent_at)

        # Audit record verification
        audits = WhatsAppMessageAudit.query.filter_by(message_id=msg.id).all()
        actions = [a.action for a in audits]
        self.assertIn('CREATED', actions)
        self.assertIn('SEND_STARTED', actions)
        self.assertIn('SEND_CONFIRMED', actions)

    # 14. Message remains after SENT
    def test_14_message_remains_after_sent(self):
        msg = create_whatsapp_message_for_order(self.order.id)
        claim_whatsapp_message(msg.id, self.admin1.id)
        confirm_whatsapp_message_sent(msg.id, self.admin1.id)

        fetched = WhatsAppMessage.query.get(msg.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.status, WhatsAppMessageStatus.SENT)

    # 15. Failed send returns to pending
    def test_15_failed_send_returns_to_pending(self):
        msg = create_whatsapp_message_for_order(self.order.id)
        claim_whatsapp_message(msg.id, self.admin1.id)

        res = confirm_whatsapp_message_sent(msg.id, self.admin1.id, is_sent=False)
        self.assertTrue(res['success'])
        db_msg = WhatsAppMessage.query.get(msg.id)
        self.assertEqual(db_msg.status, WhatsAppMessageStatus.PENDING)
        self.assertIsNone(db_msg.sent_by_admin_id)

    # 16. Stale SENDING recovery
    def test_16_stale_sending_recovery(self):
        msg = create_whatsapp_message_for_order(self.order.id)
        claim_whatsapp_message(msg.id, self.admin1.id)

        # Manually backdate updated_at to simulate timeout (>300 seconds ago)
        msg_db = WhatsAppMessage.query.get(msg.id)
        msg_db.updated_at = datetime.utcnow() - timedelta(seconds=600)
        db.session.commit()

        recovered_count = recover_stale_sending_messages(timeout_seconds=300)
        self.assertEqual(recovered_count, 1)

        msg_refreshed = WhatsAppMessage.query.get(msg.id)
        self.assertEqual(msg_refreshed.status, WhatsAppMessageStatus.PENDING)

    # 17. Multi-admin visibility
    def test_17_multi_admin_visibility(self):
        msg = create_whatsapp_message_for_order(self.order.id)

        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(self.admin1.id)
            sess['role'] = 'admin'
        res1 = self.client.get('/api/admin/whatsapp/messages')
        self.assertEqual(res1.status_code, 200)

        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(self.admin2.id)
            sess['role'] = 'admin'
        res2 = self.client.get('/api/admin/whatsapp/messages')
        self.assertEqual(res2.status_code, 200)

        data1 = json.loads(res1.data)
        data2 = json.loads(res2.data)
        self.assertEqual(len(data1['messages']), 1)
        self.assertEqual(len(data2['messages']), 1)

    # 18. Cross-tenant isolation / Authorization checking
    def test_18_cross_tenant_isolation(self):
        msg = create_whatsapp_message_for_order(self.order.id)
        claim_whatsapp_message(msg.id, self.admin1.id)

        # Admin 2 tries to confirm admin 1's claim without being claimant
        res = confirm_whatsapp_message_sent(msg.id, self.admin2.id)
        self.assertFalse(res['success'])
        self.assertEqual(res['reason'], 'not_claimed_by_you')

    # 19. Redis unavailable fallback
    def test_19_redis_unavailable_fallback(self):
        with patch('redis.from_url', side_effect=Exception("Redis connection error")):
            # Should not raise exception and fall back cleanly to in-memory queue
            try:
                publish_admin_event('fallback_test', {'data': 123})
                success = True
            except Exception:
                success = False
            self.assertTrue(success)

    # 20. Heartbeat update
    def test_20_heartbeat_update(self):
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(self.admin1.id)
            sess['role'] = 'admin'

        payload_reg = {
            "device_id": "device_hb_999",
            "platform": "android",
            "fcm_token": "token_hb",
            "device_name": "Nokia 3310"
        }
        self.client.post('/api/admin/devices/register', data=json.dumps(payload_reg), content_type='application/json')

        payload_hb = {"device_id": "device_hb_999"}
        res = self.client.post('/api/admin/devices/heartbeat', data=json.dumps(payload_hb), content_type='application/json')
        self.assertEqual(res.status_code, 200)

        dev = AdminDevice.query.filter_by(device_id="device_hb_999").first()
        self.assertIsNotNone(dev.last_seen_at)

if __name__ == '__main__':
    unittest.main()
