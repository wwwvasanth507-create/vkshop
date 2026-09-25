import os
os.environ['FLASK_ENV'] = 'testing'
import unittest
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app
from database import db
from models import User, Role
from scripts.create_admin import bootstrap_admin


class TestAdminBootstrap(unittest.TestCase):
    """Test suite for safe one-time admin bootstrap script."""

    def test_bootstrap_admin_creates_and_updates_account(self):
        """Verify bootstrap_admin creates admin user and is idempotent when run twice."""
        with patch.dict(os.environ, {
            'FLASK_ENV': 'testing',
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'
        }):
            app = create_app()
            with app.app_context():
                # 1. Run bootstrap to create user
                bootstrap_admin()
                
                admin = User.query.filter_by(username='admin').first()
                self.assertIsNotNone(admin)
                self.assertEqual(admin.email, 'admin@vkshop.com')
                self.assertEqual(admin.role, Role.ADMIN)
                self.assertTrue(admin.is_active)
                self.assertTrue(admin.email_verified)
                self.assertTrue(admin.check_password('admin123'))
                self.assertFalse(admin.check_password('wrongpass'))

                # 2. Run bootstrap again to verify idempotency (repair mode)
                admin.is_active = False
                db.session.commit()
                
                bootstrap_admin()
                
                admin_repaired = User.query.filter_by(username='admin').first()
                self.assertIsNotNone(admin_repaired)
                self.assertTrue(admin_repaired.is_active)
                self.assertEqual(admin_repaired.failed_login_attempts, 0)
                self.assertTrue(admin_repaired.check_password('admin123'))


if __name__ == '__main__':
    unittest.main()
