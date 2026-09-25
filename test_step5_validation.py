import unittest
import os
import sys
import re

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))


class TestStep5ProductionValidation(unittest.TestCase):
    """Test suite for STEP 5 live deployment prep & security validation."""

    def test_gitignore_covers_sensitive_files(self):
        """Verify .gitignore includes .env, databases, logs, and sessions."""
        gitignore_path = os.path.join(os.path.dirname(__file__), '.gitignore')
        self.assertTrue(os.path.exists(gitignore_path), ".gitignore file must exist")
        
        with open(gitignore_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn('.env', content)
        self.assertIn('__pycache__/', content)
        self.assertIn('database/*', content)
        self.assertIn('logs/*', content)

    def test_no_hardcoded_credentials_in_config(self):
        """Verify config.py does not contain hardcoded secret values."""
        config_path = os.path.join(os.path.dirname(__file__), 'config.py')
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Ensure no real AWS / MinIO secret keys are hardcoded
        self.assertNotIn('minioadmin123', content)
        self.assertNotIn('AKIAIOSFODNN7EXAMPLE', content)
        self.assertNotIn('wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY', content)

    def test_render_yaml_validity(self):
        """Verify render.yaml contains required service and database fields."""
        render_path = os.path.join(os.path.dirname(__file__), 'render.yaml')
        self.assertTrue(os.path.exists(render_path), "render.yaml must exist")
        
        with open(render_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn('type: web', content)
        self.assertIn('name: vkshop', content)
        self.assertIn('env: python', content)
        self.assertIn('buildCommand: pip install -r requirements.txt', content)
        self.assertIn('startCommand: gunicorn -c gunicorn.conf.py app:app', content)
        self.assertIn('healthCheckPath: /health', content)
        self.assertIn('databases:', content)

    def test_max_content_length_setting(self):
        """Verify MAX_CONTENT_LENGTH is configured to 16 MB in config.py."""
        from config import Config
        self.assertEqual(Config.MAX_CONTENT_LENGTH, 16 * 1024 * 1024)

    def test_requirements_file_has_production_deps(self):
        """Verify requirements.txt contains gunicorn, psycopg, pillow, minio."""
        req_path = os.path.join(os.path.dirname(__file__), 'requirements.txt')
        with open(req_path, 'r', encoding='utf-8') as f:
            reqs = f.read().lower()

        required_packages = ['gunicorn', 'psycopg', 'pillow', 'minio', 'flask-socketio']
        for pkg in required_packages:
            self.assertIn(pkg, reqs)


if __name__ == '__main__':
    unittest.main()
