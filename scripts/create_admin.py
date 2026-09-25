import sys
import os

# Add parent directory to sys.path so project modules can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from database import db
from models import User, Role


def bootstrap_admin(app=None, raise_on_error=False):
    """
    Safely bootstrap or repair the primary admin account in PostgreSQL/SQLite.
    Idempotent and safe to run multiple times. Does NOT call db.drop_all() or modify schema.
    """
    from flask import has_app_context, current_app

    if app is None:
        if has_app_context():
            app = current_app._get_current_object()
        else:
            app = create_app()

    with app.app_context():
        try:
            # Query for existing admin account by username or email
            admin_user = User.query.filter(
                (User.username == 'admin') | (User.email == 'admin@vkshop.com')
            ).first()

            if not admin_user:
                admin_user = User(
                    username='admin',
                    email='admin@vkshop.com',
                    role=Role.ADMIN,
                    is_active=True,
                    email_verified=True,
                    failed_login_attempts=0,
                    locked_until=None
                )
                admin_user.set_password('admin123')
                db.session.add(admin_user)
                db.session.commit()
                print("SUCCESS: Admin account created successfully (username: admin, email: admin@vkshop.com).")
            else:
                admin_user.username = 'admin'
                admin_user.email = 'admin@vkshop.com'
                admin_user.role = Role.ADMIN
                admin_user.is_active = True
                admin_user.email_verified = True
                admin_user.failed_login_attempts = 0
                admin_user.locked_until = None
                admin_user.set_password('admin123')
                db.session.commit()
                print("SUCCESS: Existing admin account updated and repaired successfully (username: admin, email: admin@vkshop.com).")
            return True
        except Exception as e:
            db.session.rollback()
            print(f"ERROR: Failed to bootstrap admin account: {e}")
            if raise_on_error:
                raise
            return False


if __name__ == '__main__':
    success = bootstrap_admin()
    if not success:
        sys.exit(1)

