import os
os.environ['FLASK_ENV'] = 'testing'
import unittest
from unittest.mock import patch, MagicMock
from app import create_app
from services.scheduler import keep_alive_self_ping_job, scheduler


class TestKeepAlive(unittest.TestCase):
    def setUp(self):
        os.environ['FLASK_ENV'] = 'testing'
        self.app = create_app()
        self.client = self.app.test_client()

    def test_health_check_endpoint(self):
        """Verify /health endpoint returns 200 OK for keep-alive pings."""
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data.get('status'), 'healthy')

    @patch('urllib.request.urlopen')
    def test_keep_alive_self_ping_job(self, mock_urlopen):
        """Verify keep_alive_self_ping_job issues HTTP GET request to configured URL."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_response

        with patch.dict(os.environ, {'RENDER_EXTERNAL_URL': 'https://vkshop.onrender.com'}):
            keep_alive_self_ping_job(self.app)
            
            mock_urlopen.assert_called_once()
            args, _ = mock_urlopen.call_args
            req = args[0]
            self.assertEqual(req.full_url, 'https://vkshop.onrender.com/health')

    def test_scheduler_contains_keep_alive_job(self):
        """Verify the keep_alive_self_ping job is registered in APScheduler."""
        from services.scheduler import init_scheduler, scheduler
        with patch.dict(os.environ, {'WERKZEUG_RUN_MAIN': 'true'}):
            self.app.debug = False
            init_scheduler(self.app)
        job_ids = [job.id for job in scheduler.get_jobs()]
        self.assertIn('keep_alive_self_ping', job_ids)



if __name__ == '__main__':
    unittest.main()
