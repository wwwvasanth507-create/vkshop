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
        # Re-create database
        db.drop_all()
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
        
        # 1.5 Seed 3000 Random Customers
        import random
        from werkzeug.security import generate_password_hash
        first_names = ["John", "Jane", "Alice", "Bob", "Charlie", "David", "Emma", "Fiona", "George", "Hannah", "Ian", "Julia", "Kevin", "Laura", "Michael", "Nina", "Oscar", "Sarah", "Thomas", "Ursula", "Victor", "Wendy", "Xavier", "Yvonne", "Zach"]
        last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson", "White", "Harris"]
        default_hash = generate_password_hash("CustPassword123")
        
        print("Generating 3000 random customer accounts...")
        users = []
        used_usernames = set()
        used_emails = set()
        for _ in range(3000):
            while True:
                first = random.choice(first_names)
                last = random.choice(last_names)
                suffix = random.randint(1000, 999999)
                username = f"{first.lower()}_{last.lower()}_{suffix}"
                email = f"{username}@gmail.com"
                if username not in used_usernames and email not in used_emails:
                    used_usernames.add(username)
                    used_emails.add(email)
                    break
            
            user = User(
                username=username,
                email=email,
                password_hash=default_hash,
                role=Role.CUSTOMER,
                is_active=True,
                email_verified=True
            )
            users.append(user)
            if len(users) >= 500:
                db.session.bulk_save_objects(users)
                db.session.commit()
                users = []
        if users:
            db.session.bulk_save_objects(users)
            db.session.commit()
        print("Successfully seeded 3000 customer accounts.")
        
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
