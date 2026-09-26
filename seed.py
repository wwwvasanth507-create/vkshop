import os
import shutil
from database import db, init_db
from models import User, Role, SystemSetting
from flask import Flask

def seed_database():
    app = Flask(__name__)
    from config import DevelopmentConfig, ProductionConfig
    env = os.environ.get('FLASK_ENV', 'production').lower()
    if env == 'development':
        app.config.from_object(DevelopmentConfig)
    else:
        app.config.from_object(ProductionConfig)
    init_db(app)
    
    with app.app_context():
        # Re-create database safely handling circular foreign key dependencies
        try:
            db.drop_all()
        except Exception as drop_err:
            db.session.rollback()
            try:
                db.session.execute(db.text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
                db.session.commit()
            except Exception:
                db.session.rollback()
        db.create_all()
        print("Database tables initialized successfully.")
        
        # 1. Create Admin User only
        admin = User(
            username='admin',
            email='admin@vkshop.com',
            role=Role.ADMIN,
            is_active=True,
            email_verified=True
        )
        admin.set_password('admin123')
        db.session.add(admin)
        
        # 2. Seed System Settings
        settings_to_seed = {
            'TAX_GST_PERCENTAGE': '18.0',
            'SHIPPING_FEE': '50.0',
            'FREE_SHIPPING_THRESHOLD': '500.0',
            'ENABLE_UPI': 'true',
            'ENABLE_COD': 'true',
            'ENABLE_OUT_FOR_DELIVERY': 'true',
            'ENABLE_DELIVERED': 'true',
            'ENABLE_RETURNS': 'true',
            'MARKETPLACE_ADDRESS_INVOICE': '123 Innovation Way, Tech Park\nBangalore, KA 560001',
            'SUPPORT_OFFICIAL_EMAIL': 'support@vkshop.com',
            'MARKETPLACE_ADDRESS_SUPPORT': 'VKshop Support Center, 123 E-Commerce Way, Bangalore - 560001',
            'ADMIN_UPI_ID': 'admin@upi'
        }
        for k, v in settings_to_seed.items():
            db.session.add(SystemSetting(key=k, value=v))
            
        db.session.commit()
        print("Admin user created and default system settings seeded successfully.")
        
        # Clean up sample upload directories
        uploads_dir = os.path.join(app.config['BASE_DIR'], 'static', 'uploads')
        if os.path.exists(uploads_dir):
            for folder in ['products', 'store', 'banners', 'users', 'categories', 'admin']:
                folder_path = os.path.join(uploads_dir, folder)
                if os.path.exists(folder_path):
                    for fname in os.listdir(folder_path):
                        fpath = os.path.join(folder_path, fname)
                        if os.path.isfile(fpath):
                            try:
                                os.remove(fpath)
                            except Exception:
                                pass
                os.makedirs(folder_path, exist_ok=True)
        print("Cleaned uploaded mock files.")

if __name__ == '__main__':
    seed_database()
