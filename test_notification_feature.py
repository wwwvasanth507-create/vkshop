import unittest
import json
from app import create_app
from database import db
from models import User, Role, Product, Notification, StoreProfile, Category

class TestNotificationFeature(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()
            
            # Create Customer User
            self.customer = User(username='cust_test', email='cust@test.com', role=Role.CUSTOMER, is_active=True)
            self.customer.set_password('password123')
            db.session.add(self.customer)
            
            # Create Seller User & Store
            self.seller_user = User(username='seller_test', email='seller@test.com', role=Role.SELLER, is_active=True)
            self.seller_user.set_password('password123')
            db.session.add(self.seller_user)
            db.session.commit()
            
            self.store = StoreProfile(user_id=self.seller_user.id, name='Test Store', status='Approved')
            db.session.add(self.store)
            
            self.category = Category(name='Electronics', slug='electronics')
            db.session.add(self.category)
            db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_unread_notification_api(self):
        """Test unread notification count API endpoint."""
        with self.app.app_context():
            # Create unread notification for customer
            notif = Notification(user_id=self.customer.id, title='New Product Listed', message='Product A listed', is_read=False, type='product')
            db.session.add(notif)
            db.session.commit()

        # Login customer
        self.client.post('/login', data={'username': 'cust@test.com', 'password': 'password123'})
        
        # Test unread count endpoint
        res = self.client.get('/api/notifications/unread-count')
        data = json.loads(res.data)
        self.assertTrue(data['success'])
        self.assertEqual(data['unread_count'], 1)
        self.assertTrue(data['has_unread'])

        # Test mark read endpoint
        res_mark = self.client.post('/api/notifications/mark-read')
        data_mark = json.loads(res_mark.data)
        self.assertTrue(data_mark['success'])

        # Verify unread count is now 0
        res2 = self.client.get('/api/notifications/unread-count')
        data2 = json.loads(res2.data)
        self.assertEqual(data2['unread_count'], 0)
        self.assertFalse(data2['has_unread'])

    def test_new_product_creates_notifications(self):
        """Test that adding a product creates DB notifications and triggers events."""
        with self.app.app_context():
            seller_user = User.query.filter_by(username='seller_test').first()
            store = StoreProfile.query.filter_by(user_id=seller_user.id).first()
            category = Category.query.first()
            
            # Simulate adding a product
            prod = Product(
                seller_id=store.id, category_id=category.id, name='Wireless Mouse',
                slug='wireless-mouse', description='Gaming mouse', base_price=1000.0,
                offer_price=800.0, stock=50, sku='PROD-MOUSE-1', is_active=True
            )
            db.session.add(prod)
            db.session.commit()

            # Create notification for users
            users = User.query.filter(User.id != seller_user.id).all()
            for u in users:
                db.session.add(Notification(user_id=u.id, title='New Product Added: Wireless Mouse', message='Test store listed Wireless Mouse', type='product'))
            db.session.commit()

            # Verify notification created
            notifs = Notification.query.filter_by(user_id=self.customer.id).all()
            self.assertEqual(len(notifs), 1)
            self.assertIn('Wireless Mouse', notifs[0].title)

if __name__ == '__main__':
    unittest.main()
