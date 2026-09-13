"""Regressions for the reported /static/course.js 404 and incomplete installs."""
import hashlib
import json
from pathlib import Path
import shutil
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen
from uuid import uuid4

from server.frontend_assets import frontend_status, require_frontend
from server.http_server import FRONTEND, create_server


class UiDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / '.ui-test-data' / ('delivery-' + uuid4().hex)
        self.root.mkdir(parents=True)
        self.addCleanup(lambda: shutil.rmtree(self.root))

    def test_incomplete_frontend_refuses_startup_before_creating_storage(self):
        incomplete = self.root / 'incomplete'
        incomplete.mkdir()
        with patch('server.http_server.FRONTEND', incomplete):
            with self.assertRaisesRegex(RuntimeError, r'course\.js'):
                create_server(self.root / 'data', port=0)
        self.assertFalse((self.root / 'data').exists())

    def test_exact_script_url_has_javascript_bytes_and_instance_diagnostics(self):
        server = create_server(self.root / 'data', port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f'http://127.0.0.1:{server.server_port}'
            with urlopen(f'http://localhost:{server.server_port}/static/course.js', timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers.get_content_type(), 'text/javascript')
            with urlopen(base + '/api/health', timeout=5) as response:
                health = json.load(response)
                self.assertEqual(health['instance_id'], response.headers['X-Synopsis-Instance'])
            self.assertEqual(health['ui']['root'], str(FRONTEND.resolve()))
            self.assertEqual(health['data_dir'], str((self.root / 'data').resolve()))
            self.assertEqual(health['ui']['missing_files'], [])
            for name in health['ui']['files']:
                with self.subTest(file=name), urlopen(base + '/static/' + name, timeout=5) as response:
                    raw = response.read()
                    self.assertEqual(hashlib.sha256(raw).hexdigest(), health['ui']['files'][name]['sha256'])
                    if name.endswith('.js'):
                        self.assertEqual(response.headers.get_content_type(), 'text/javascript')
                    self.assertEqual(response.headers['Cache-Control'], 'no-store')
            with self.assertRaises(HTTPError) as error:
                urlopen(base + '/static/missing.js', timeout=5)
            self.assertEqual(error.exception.code, 404)
            detail = json.load(error.exception)
            error.exception.close()
            self.assertEqual(detail['path'], 'missing.js')
            self.assertEqual(detail['diagnostics'], '/api/health')
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    def test_missing_or_empty_script_is_identified_not_silently_ready(self):
        real_read = Path.read_bytes
        def missing_course(path):
            if path == FRONTEND / 'course.js':
                raise FileNotFoundError(path)
            return real_read(path)
        with patch.object(Path, 'read_bytes', missing_course):
            status = frontend_status(FRONTEND)
            self.assertFalse(status['ok'])
            self.assertEqual(status['missing_files'], ['course.js'])
            with self.assertRaisesRegex(RuntimeError, r'course\.js'):
                require_frontend(FRONTEND)


if __name__ == '__main__':
    unittest.main()
