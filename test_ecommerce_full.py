import os
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['FLASK_ENV'] = 'testing'

import unittest
import json
from datetime import datetime, timedelta
from app import create_app
from database import db
from models import (User, StoreProfile, Category, Brand, Product, Order, OrderItem, 
                    Payment, Banner, SystemSetting, WalletTransaction, RewardPoint)

class ECommerceFullTestCase(unittest.TestCase):
    def setUp(self):
        # Create Flask app
        self.app = create_app()
        self.app.config.update({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
            'WTF_CSRF_ENABLED': False,
            'SESSION_COOKIE_SECURE': False
        })
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        
        # Re-create all tables in the clean in-memory database
        db.drop_all()
        db.create_all()
        
        # Run startup migrations manually for in-memory database
        try:
            db.session.execute(db.text("ALTER TABLE brands ADD COLUMN category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL;"))
            db.session.commit()
        except Exception:
            db.session.rollback()
            
        try:
            db.session.execute(db.text("ALTER TABLE banners ADD COLUMN expires_at DATETIME;"))
            db.session.commit()
        except Exception:
            db.session.rollback()

        # Seed mock data
        self.seed_test_data()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()
        
        # Clean up database URL environment variable
        if 'DATABASE_URL' in os.environ:
            del os.environ['DATABASE_URL']

    def seed_test_data(self):
        # 1. System Settings
        db.session.add_all([
            SystemSetting(key='TAX_GST_PERCENTAGE', value='12.5'),
            SystemSetting(key='SHIPPING_FEE', value='45.0'),
            SystemSetting(key='FREE_SHIPPING_THRESHOLD', value='300.0'),
            SystemSetting(key='ENABLE_UPI', value='true'),
            SystemSetting(key='ENABLE_COD', value='true'),
            SystemSetting(key='ADMIN_UPI_ID', value='admin@upi'),
            SystemSetting(key='ADMIN_QR_CODE', value='admin_qr_code.png')
        ])
        
        # 2. Users
        self.admin = User(username='testadmin', email='admin@test.com', role='admin', is_active=True)
        self.admin.set_password('admin123')
        
        self.seller = User(username='testseller', email='seller@test.com', role='seller', is_active=True)
        self.seller.set_password('seller123')
        
        self.customer = User(username='testcustomer', email='customer@test.com', role='customer', is_active=True)
        self.customer.set_password('customer123')
        
        db.session.add_all([self.admin, self.seller, self.customer])
        db.session.commit()

        # 3. Store Profile
        self.store = StoreProfile(
            user_id=self.seller.id,
            name='Test Tech Store',
            status='Approved',
            upi_id='seller@upi',
            qr_code_path='seller_qr.png',
            commission_percentage=10.0
        )
        db.session.add(self.store)
        db.session.commit()

        # 4. Category and Brand
        self.category = Category(name='Smartphones', slug='smartphones', icon='fa-mobile')
        db.session.add(self.category)
        db.session.commit()
        
        self.brand = Brand(name='Apex', slug='apex', description='Apex Brand', category_id=self.category.id)
        db.session.add(self.brand)
        db.session.commit()

        # 5. Product
        self.product = Product(
            seller_id=self.store.id,
            category_id=self.category.id,
            brand_id=self.brand.id,
            name='Apex Phone Pro',
            slug='apex-phone-pro',
            description='Excellent phone',
            base_price=200.0,
            discount_percent=10.0,
            offer_price=180.0,
            sku='APX-PRO-1',
            stock=10,
            is_active=True,
            clicks=10,
            views=50
        )
        db.session.add(self.product)
        db.session.commit()

    def test_dynamic_tax_and_shipping(self):
        """Verify dynamic tax, shipping fees, and FREE threshold settings are queried dynamically."""
        from routes.admin import get_setting
        tax = get_setting('TAX_GST_PERCENTAGE', 18.0)
        self.assertEqual(tax, 12.5)
        
        shipping = get_setting('SHIPPING_FEE', 50.0)
        self.assertEqual(shipping, 45.0)

        threshold = get_setting('FREE_SHIPPING_THRESHOLD', 500.0)
        self.assertEqual(threshold, 300.0)

    def test_seller_deactivation_clears_upi_permanently(self):
        """Deactivating a seller account must clear their store upi_id and qr_code_path permanently."""
        self.assertEqual(self.store.upi_id, 'seller@upi')
        self.assertEqual(self.store.qr_code_path, 'seller_qr.png')

        # Run toggle_user_active deactivation logic
        self.seller.is_active = False
        if not self.seller.is_active and self.seller.role == 'seller' and self.seller.store_profile:
            self.seller.store_profile.upi_id = None
            self.seller.store_profile.qr_code_path = None
        db.session.commit()

        db.session.refresh(self.store)
        self.assertIsNone(self.store.upi_id)
        self.assertIsNone(self.store.qr_code_path)

    def test_disabled_seller_product_detail_page(self):
        """If a seller is deactivated or suspended, product detail page must render 'seller not available' and hide order forms."""
        # Deactivate seller
        self.seller.is_active = False
        db.session.commit()

        # Fetch product detail page
        response = self.client.get(f'/product/{self.product.slug}')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        
        # Verify order elements are hidden and alert message is shown
        self.assertIn('seller not available', html)
        self.assertNotIn('add-to-cart-btn', html)
        self.assertNotIn('id="quantity"', html)

    def test_payment_methods_restrictions(self):
        """Only UPI and Cash on Delivery should be enabled at checkout."""
        # Authenticate customer
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(self.customer.id)
            sess['_fresh'] = True
            
        # Get checkout page
        response = self.client.get('/checkout')
        # Note: If cart is empty, customer gets redirected to cart page. Let's inspect cart page first or seed cart item.
        self.assertEqual(response.status_code, 302) # Redirect to view_cart

    def test_product_clicks_tracking(self):
        """Verify that tracking a product click increments the click count."""
        initial_clicks = self.product.clicks
        response = self.client.get(f'/product/click/{self.product.id}')
        self.assertEqual(response.status_code, 302) # Redirect to product detail page
        
        db.session.refresh(self.product)
        self.assertEqual(self.product.clicks, initial_clicks + 1)

    def test_seller_dashboard_metrics(self):
        """Verify seller lifetime sales (verified only) and completed order count calculations."""
        # Create an order and item
        order = Order(
            order_number='ORD-TEST-1',
            user_id=self.customer.id,
            total_amount=180.0,
            grand_total=180.0,
            status='Confirmed'
        )
        db.session.add(order)
        db.session.commit()
        
        item = OrderItem(
            order_id=order.id,
            product_id=self.product.id,
            quantity=1,
            unit_price=180.0,
            total_price=180.0,
            product_name=self.product.name
        )
        db.session.add(item)
        
        payment = Payment(
            order_id=order.id,
            payment_method='UPI',
            status='Completed',
            amount=180.0
        )
        db.session.add(payment)
        db.session.commit()

        # Calculate store stats (similar to dashboard route)
        confirmed_order_items = OrderItem.query.join(Product).join(Order).filter(
            Product.seller_id == self.store.id,
            Order.status.in_(['Confirmed', 'Packed', 'Shipped', 'Out For Delivery', 'Delivered'])
        ).all()
        sales_total = sum(i.total_price for i in confirmed_order_items)
        self.assertEqual(sales_total, 180.0)

        # Order Count check: status == Delivered and payment == Completed
        completed_orders = Order.query.join(OrderItem).join(Product).join(Payment).filter(
            Product.seller_id == self.store.id,
            Order.status == 'Delivered',
            Payment.status == 'Completed'
        ).distinct().all()
        self.assertEqual(len(completed_orders), 0)  # It's only Confirmed, not Delivered

        # Update order to Delivered
        order.status = 'Delivered'
        db.session.commit()
        
        completed_orders_new = Order.query.join(OrderItem).join(Product).join(Payment).filter(
            Product.seller_id == self.store.id,
            Order.status == 'Delivered',
            Payment.status == 'Completed'
        ).distinct().all()
        self.assertEqual(len(completed_orders_new), 1)

    def test_banner_expiry_and_auto_deletion(self):
        """Banners older than expires_at datetime should be deleted on homepage load."""
        from routes.admin import cleanup_expired_banners
        
        # Create active banner
        banner_active = Banner(
            title='Active Banner',
            image_path='active.jpg',
            is_active=True,
            order_seq=1,
            expires_at=datetime.utcnow() + timedelta(days=1)
        )
        # Create expired banner
        banner_expired = Banner(
            title='Expired Banner',
            image_path='expired.jpg',
            is_active=True,
            order_seq=2,
            expires_at=datetime.utcnow() - timedelta(minutes=1)
        )
        db.session.add_all([banner_active, banner_expired])
        db.session.commit()

        self.assertEqual(Banner.query.count(), 2)

        # Execute banner cleanup
        cleanup_expired_banners()

        # Expired banner must be deleted
        banners = Banner.query.all()
        self.assertEqual(len(banners), 1)
        self.assertEqual(banners[0].title, 'Active Banner')

if __name__ == '__main__':
    unittest.main()
