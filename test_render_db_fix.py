import unittest
import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))


class TestRenderDbFix(unittest.TestCase):
    """Test suite validating the fix for Render PostgreSQL transaction crash."""

    def test_sqlite_pragma_listener_skips_non_sqlite(self):
        """Verify set_sqlite_pragma event listener ignores PostgreSQL/psycopg connections."""
        from database import set_sqlite_pragma
        
        # Mock a psycopg3 / PostgreSQL DBAPI connection
        mock_pg_conn = MagicMock()
        type(mock_pg_conn).__module__ = 'psycopg'
        
        set_sqlite_pragma(mock_pg_conn, None)
        
        # Cursor should NOT have been created or executed for non-sqlite connections
        mock_pg_conn.cursor.assert_not_called()

    def test_postgresql_url_scheme_conversion(self):
        """Verify postgres:// and postgresql:// URIs are converted to postgresql+psycopg://."""
        with patch.dict(os.environ, {
            'DATABASE_URL': 'postgres://user:secret_pass@db.render.com:5432/vdb',
            'FLASK_ENV': 'production'
        }):
            from importlib import reload
            import config
            reload(config)
            self.assertEqual(
                config.Config.SQLALCHEMY_DATABASE_URI,
                'postgresql+psycopg://user:secret_pass@db.render.com:5432/vdb'
            )

        with patch.dict(os.environ, {
            'DATABASE_URL': 'postgresql://user:secret_pass@db.render.com:5432/vdb',
            'FLASK_ENV': 'production'
        }):
            from importlib import reload
            import config
            reload(config)
            self.assertEqual(
                config.Config.SQLALCHEMY_DATABASE_URI,
                'postgresql+psycopg://user:secret_pass@db.render.com:5432/vdb'
            )

    def test_app_importable_for_gunicorn(self):
        """Verify app module and app instance can be imported by Gunicorn without error."""
        with patch.dict(os.environ, {
            'FLASK_ENV': 'testing',
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'
        }):
            from app import app
            self.assertIsNotNone(app)
            self.assertEqual(app.name, 'app')

    def test_rollback_recovers_failed_transaction(self):
        """Verify db.session.rollback() recovers session from a failed query."""
        with patch.dict(os.environ, {
            'FLASK_ENV': 'testing',
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'
        }):
            from app import create_app
            from database import db
            import sqlalchemy as sa
            
            app = create_app()
            with app.app_context():
                # Execute invalid query to cause failure
                try:
                    db.session.execute(sa.text("SELECT * FROM non_existent_table_xyz_123;"))
                except Exception:
                    db.session.rollback()

                # Session should now cleanly execute valid query
                res = db.session.execute(sa.text("SELECT 1;")).scalar()
                self.assertEqual(res, 1)


if __name__ == '__main__':
    unittest.main()
