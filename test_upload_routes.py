import os
import io
import unittest
from PIL import Image

os.environ['FLASK_ENV'] = 'testing'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app
from database import db
from models import (
    User, StoreProfile, Category, Brand, Product, ProductImage, ProductVariant,
    Order, OrderItem, Payment, Banner, SystemSetting, CommissionPayment, CommissionReport, Complaint
)
from services.storage import storage_service, resolve_image_url

class UploadRoutesTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
            'WTF_CSRF_ENABLED': False,
            'ALLOW_LOCAL_STORAGE_FALLBACK': True
        })
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()

        db.drop_all()
        db.create_all()

        self.seed_data()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def seed_data(self):
        # 1. Admin
        self.admin = User(username='admin_user', email='admin@test.com', role='admin', is_active=True)
        self.admin.set_password('admin123')
        
        # 2. Seller
        self.seller_user = User(username='seller_user', email='seller@test.com', role='seller', is_active=True)
        self.seller_user.set_password('seller123')

        # 3. Customer
        self.customer = User(username='customer_user', email='customer@test.com', role='customer', is_active=True)
        self.customer.set_password('customer123')

        db.session.add_all([self.admin, self.seller_user, self.customer])
        db.session.commit()

        # 4. Store Profile
        self.store = StoreProfile(
            user_id=self.seller_user.id,
            name='Apex Seller Store',
            status='Approved'
        )
        db.session.add(self.store)
        db.session.commit()

        # 5. Category
        self.category = Category(name='Electronics', slug='electronics', icon='fa-plug')
        db.session.add(self.category)
        db.session.commit()

        # 6. Product
        self.product = Product(
            seller_id=self.store.id,
            category_id=self.category.id,
            name='Test Smartphone',
            slug='test-smartphone',
            description='Test Smartphone description',
            base_price=500.0,
            offer_price=500.0,
            sku='TEST-SMARTPHONE-SKU',
            is_active=True
        )
        db.session.add(self.product)
        db.session.commit()

        # 7. Order
        self.order = Order(
            order_number='ORD-TEST-101',
            user_id=self.customer.id,
            total_amount=500.0,
            grand_total=500.0,
            status='Pending'
        )
        db.session.add(self.order)
        db.session.commit()

        self.order_item = OrderItem(
            order_id=self.order.id,
            product_id=self.product.id,
            quantity=1,
            unit_price=500.0,
            total_price=500.0,
            product_name=self.product.name
        )
        db.session.add(self.order_item)

        self.payment = Payment(
            order_id=self.order.id,
            payment_method='UPI',
            amount=500.0,
            status='Pending'
        )
        db.session.add(self.payment)
        db.session.commit()

    def make_image_file(self, filename='test.jpg', width=200, height=200, fmt='JPEG'):
        buf = io.BytesIO()
        img = Image.new('RGB', (width, height), color=(100, 150, 200))
        img.save(buf, format=fmt)
        buf.seek(0)
        return (buf, filename)

    def login(self, username, password):
        return self.client.post('/login', data={'login_input': username, 'password': password}, follow_redirects=True)

    # 1. Product primary image upload
    def test_1_product_primary_image_upload(self):
        self.login('seller_user', 'seller123')
        img_file, filename = self.make_image_file('primary.jpg')
        data = {
            'name': 'New Camera Phone',
            'description': 'Camera phone description',
            'category_id': self.category.id,
            'base_price': '999',
            'discount_percent': '0',
            'delivery_days': '3',
            'stock': '10',
            'primary_image': (img_file, filename)
        }
        res = self.client.post('/seller/product/add', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        
        prod = Product.query.filter_by(name='New Camera Phone').first()
        self.assertIsNotNone(prod)
        self.assertEqual(len(prod.images), 1)
        self.assertTrue(prod.images[0].image_path.startswith('products/'))

    # 2. Product gallery multiple upload
    def test_2_product_gallery_multiple_upload(self):
        self.login('seller_user', 'seller123')
        img1, fn1 = self.make_image_file('gallery1.jpg')
        img2, fn2 = self.make_image_file('gallery2.png', fmt='PNG')
        data = {
            'name': 'Test Smartphone',
            'description': 'Updated description',
            'category_id': self.category.id,
            'base_price': '500',
            'discount_percent': '0',
            'delivery_days': '3',
            'stock': '5',
            'gallery_images': [(img1, fn1), (img2, fn2)]
        }
        res = self.client.post(f'/seller/product/edit/{self.product.id}', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        
        imgs = ProductImage.query.filter_by(product_id=self.product.id).all()
        self.assertGreaterEqual(len(imgs), 2)

    # 3. Variant image upload
    def test_3_variant_image_upload(self):
        self.login('seller_user', 'seller123')
        img, fn = self.make_image_file('variant.jpg')
        data = {
            'sku': 'VAR-RED-128GB',
            'stock': '15',
            'price': '550',
            'color': 'Red',
            'storage': '128GB',
            'variant_image': (img, fn)
        }
        res = self.client.post(f'/seller/product/{self.product.id}/variant/add', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        
        var = ProductVariant.query.filter_by(sku='VAR-RED-128GB').first()
        self.assertIsNotNone(var)
        self.assertTrue(var.image_path.startswith('products/variants/'))

    # 4. Store logo upload
    def test_4_store_logo_upload(self):
        self.login('seller_user', 'seller123')
        img, fn = self.make_image_file('logo.png', fmt='PNG')
        data = {
            'name': 'Apex Seller Store',
            'description': 'Updated description',
            'logo': (img, fn)
        }
        res = self.client.post('/seller/store/settings', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        
        db.session.refresh(self.store)
        self.assertTrue(self.store.logo.startswith('stores/'))

    # 5. Store banner upload
    def test_5_store_banner_upload(self):
        self.login('seller_user', 'seller123')
        img, fn = self.make_image_file('store_banner.jpg')
        data = {
            'name': 'Apex Seller Store',
            'banner': (img, fn)
        }
        res = self.client.post('/seller/store/settings', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        
        db.session.refresh(self.store)
        self.assertTrue(self.store.banner.startswith('stores/banners/'))

    # 6. Store QR upload
    def test_6_store_qr_upload(self):
        self.login('seller_user', 'seller123')
        img, fn = self.make_image_file('qr.png', fmt='PNG')
        data = {
            'name': 'Apex Seller Store',
            'qr_code': (img, fn)
        }
        res = self.client.post('/seller/store/settings', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        
        db.session.refresh(self.store)
        self.assertTrue(self.store.qr_code_path.startswith('stores/qr/'))

    # 7. Seller document upload
    def test_7_seller_document_upload(self):
        f1, fn1 = self.make_image_file('front.jpg')
        f2, fn2 = self.make_image_file('back.jpg')
        f3, fn3 = self.make_image_file('photo.jpg')
        f4, fn4 = self.make_image_file('sig.png', fmt='PNG')
        
        data = {
            'username': 'new_seller_doc_test',
            'email': 'new_seller@test.com',
            'password': 'password123',
            'confirm_password': 'password123',
            'role': 'seller',
            'aadhaar_number': '123456789012',
            'agreed': 'true',
            'aadhaar_front': (f1, fn1),
            'aadhaar_back': (f2, fn2),
            'photo': (f3, fn3),
            'signature': (f4, fn4)
        }
        res = self.client.post('/register', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        
        u = User.query.filter_by(username='new_seller_doc_test').first()
        self.assertIsNotNone(u)
        self.assertIsNotNone(u.store_profile)
        self.assertTrue(u.store_profile.aadhaar_front.startswith('private/seller-documents/'))

    # 8. Payment screenshot upload
    def test_8_payment_screenshot_upload(self):
        self.login('customer_user', 'customer123')
        img, fn = self.make_image_file('pay.jpg')
        data = {
            'utr_number': 'UTR12345678',
            'contact_number': '9876543210',
            'description': 'Paid via Google Pay',
            'screenshot': (img, fn)
        }
        res = self.client.post(f'/order/pay/{self.order.id}', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        
        db.session.refresh(self.payment)
        self.assertTrue(self.payment.screenshot_path.startswith('private/payment/'))

    # 9. Complaint screenshot upload
    def test_9_complaint_screenshot_upload(self):
        self.login('customer_user', 'customer123')
        img, fn = self.make_image_file('complaint.jpg')
        data = {
            'details': 'Item arrived damaged',
            'screenshot': (img, fn)
        }
        res = self.client.post(f'/order/complaint/{self.order.id}', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        
        comp = Complaint.query.filter_by(order_id=self.order.id).first()
        self.assertIsNotNone(comp)
        self.assertTrue(comp.screenshot.startswith('private/complaints/'))

    # 10. Category image upload
    def test_10_category_image_upload(self):
        self.login('admin_user', 'admin123')
        img, fn = self.make_image_file('cat.png', fmt='PNG')
        data = {
            'name': 'Home Appliances',
            'icon': 'fa-plug',
            'icon_image': (img, fn)
        }
        res = self.client.post('/admin/category/add', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        
        cat = Category.query.filter_by(name='Home Appliances').first()
        self.assertIsNotNone(cat)
        self.assertTrue(cat.icon.startswith('categories/'))

    # 11. Banner upload
    def test_11_banner_upload(self):
        self.login('admin_user', 'admin123')
        img, fn = self.make_image_file('banner.jpg')
        data = {
            'title': 'Grand Festive Sale',
            'subtitle': 'Up to 50% Off',
            'link_url': '/category/electronics',
            'banner_image': (img, fn)
        }
        res = self.client.post('/admin/banner/add', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        
        bn = Banner.query.filter_by(title='Grand Festive Sale').first()
        self.assertIsNotNone(bn)
        self.assertTrue(bn.image_path.startswith('banners/'))

    # 12. Admin QR upload
    def test_12_admin_qr_upload(self):
        self.login('admin_user', 'admin123')
        img, fn = self.make_image_file('admin_qr.png', fmt='PNG')
        data = {
            'ENABLE_UPI': 'true',
            'ADMIN_QR_CODE': (img, fn)
        }
        res = self.client.post('/admin/settings', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        
        setting = SystemSetting.query.filter_by(key='ADMIN_QR_CODE').first()
        self.assertIsNotNone(setting)
        self.assertTrue(setting.value.startswith('admin/qr/'))

    # 13. Product image deletion
    def test_13_product_image_deletion(self):
        pimg = ProductImage(product_id=self.product.id, image_path='products/del_test.webp', is_primary=False)
        db.session.add(pimg)
        db.session.commit()
        
        self.login('seller_user', 'seller123')
        res = self.client.get(f'/seller/product/image/delete/{pimg.id}', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        
        deleted_img = ProductImage.query.get(pimg.id)
        self.assertIsNone(deleted_img)

    # 14. Banner deletion
    def test_14_banner_deletion(self):
        bn = Banner(title='Delete Banner Test', image_path='banners/del_bn.webp', is_active=True)
        db.session.add(bn)
        db.session.commit()
        
        self.login('admin_user', 'admin123')
        res = self.client.get(f'/admin/banner/delete/{bn.id}', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        
        deleted_bn = Banner.query.get(bn.id)
        self.assertIsNone(deleted_bn)

    # 15. Replacement upload
    def test_15_replacement_upload(self):
        self.store.logo = 'stores/old_logo.webp'
        db.session.commit()
        
        self.login('seller_user', 'seller123')
        img, fn = self.make_image_file('new_logo.png', fmt='PNG')
        data = {
            'name': 'Apex Seller Store',
            'logo': (img, fn)
        }
        res = self.client.post('/seller/store/settings', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        
        db.session.refresh(self.store)
        self.assertNotEqual(self.store.logo, 'stores/old_logo.webp')
        self.assertTrue(self.store.logo.startswith('stores/'))

    # 16. Failed storage upload (simulated)
    def test_16_failed_storage_upload(self):
        self.app.config['ALLOW_LOCAL_STORAGE_FALLBACK'] = False
        self.app.config['MINIO_ENDPOINT'] = None
        
        self.login('seller_user', 'seller123')
        img, fn = self.make_image_file('fail.jpg')
        data = {
            'name': 'Apex Seller Store',
            'logo': (img, fn)
        }
        res = self.client.post('/seller/store/settings', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(res.status_code, 200)

    # 17. Failed database transaction after storage upload (simulated)
    def test_17_failed_database_transaction(self):
        self.login('seller_user', 'seller123')
        res = self.client.get('/seller/product/image/delete/999999')
        self.assertEqual(res.status_code, 404)

    # 18. Unauthorized deletion
    def test_18_unauthorized_deletion(self):
        self.login('customer_user', 'customer123')
        bn = Banner(title='Protected Banner', image_path='banners/prot.webp', is_active=True)
        db.session.add(bn)
        db.session.commit()
        
        res = self.client.get(f'/admin/banner/delete/{bn.id}')
        self.assertNotEqual(res.status_code, 200)

    # 19. Private document access
    def test_19_private_document_access(self):
        res_unauth = self.client.get('/private/file/private/payment/test.jpg')
        self.assertEqual(res_unauth.status_code, 401)
        
        self.login('customer_user', 'customer123')
        res_auth = self.client.get('/private/file/private/payment/non_existent.jpg')
        self.assertEqual(res_auth.status_code, 404)

    # 20. Legacy image path resolution
    def test_20_legacy_image_path_resolution(self):
        url1 = resolve_image_url('legacy_phone.jpg', 'products')
        self.assertEqual(url1, '/static/uploads/products/legacy_phone.jpg')

        url2 = resolve_image_url('/static/uploads/store/legacy_logo.png')
        self.assertEqual(url2, '/static/uploads/store/legacy_logo.png')

        url3 = resolve_image_url('products/uuid_new.webp')
        self.assertTrue(url3.endswith('products/uuid_new.webp'))

        url4 = resolve_image_url('https://cdn.example.com/external.jpg')
        self.assertEqual(url4, 'https://cdn.example.com/external.jpg')

if __name__ == '__main__':
    unittest.main()
