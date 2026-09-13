import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch
from urllib.request import urlopen
from uuid import uuid4
import zipfile

from server import launcher
from server.http_server import create_server


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / '.ui-test-data' / ('launcher-' + uuid4().hex)
        self.root.mkdir(parents=True)
        self.addCleanup(lambda: shutil.rmtree(self.root))

    @contextlib.contextmanager
    def running_server(self):
        server = create_server(self.root / 'data', port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    def test_default_browser_and_stable_default_data_directory(self):
        with patch.object(launcher, 'launch', return_value=0) as run:
            self.assertEqual(launcher.main([]), 0)
            run.assert_called_once_with(launcher.PROJECT_ROOT / '.synopsis-data', 8765, browser=True)
        with patch.object(launcher, 'launch', return_value=0) as run:
            launcher.main(['--no-browser', '--port', '0'])
            self.assertFalse(run.call_args.kwargs['browser'])

    def test_browser_opens_only_when_the_actual_instance_is_ready(self):
        with self.running_server() as server:
            url = f'http://127.0.0.1:{server.server_port}'
            def opened(address):
                health = launcher.health_at(address)
                self.assertEqual(health['instance_id'], server.instance_id)
                with urlopen(address + '/static/course.js', timeout=3) as response:
                    self.assertEqual(response.status, 200)
                return True
            with patch.object(launcher.webbrowser, 'open_new_tab', side_effect=opened) as browser:
                launcher.open_when_ready(url, server.instance_id, threading.Event())
                browser.assert_called_once_with(url)

    def test_stopped_or_wrong_instance_cannot_open_a_browser(self):
        stopped = threading.Event()
        with patch.object(launcher, 'health_at', side_effect=[{'instance_id':'other','status':'ok'}, {'instance_id':'ours','status':'ok'}]), patch.object(launcher.webbrowser, 'open_new_tab', return_value=True) as browser:
            launcher.open_when_ready('http://127.0.0.1:1234', 'ours', stopped)
            browser.assert_called_once()
            stopped.set()
            launcher.open_when_ready('http://127.0.0.1:1234', 'ours', stopped)
            browser.assert_called_once()

    def test_second_launch_reuses_same_server_without_another_writer(self):
        with self.running_server() as server, patch.object(launcher.webbrowser, 'open_new_tab', return_value=True) as browser:
            self.assertEqual(launcher.launch(self.root / 'data', server.server_port), 0)
            url = f'http://127.0.0.1:{server.server_port}'
            browser.assert_called_once_with(url)
            self.assertEqual(launcher.health_at(url)['instance_id'], server.instance_id)

    def test_busy_port_never_opens_a_different_library(self):
        with self.running_server() as server, patch.object(launcher.webbrowser, 'open_new_tab') as browser:
            with self.assertRaisesRegex(RuntimeError, 'занят'):
                launcher.launch(self.root / 'other-data', server.server_port)
            browser.assert_not_called()
            self.assertEqual(launcher.health_at(f'http://127.0.0.1:{server.server_port}')['instance_id'], server.instance_id)

    def test_browser_failure_keeps_a_clear_manual_fallback(self):
        with patch.object(launcher.webbrowser, 'open_new_tab', return_value=False), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertFalse(launcher.open_browser('http://127.0.0.1:1234'))
            self.assertIn('http://127.0.0.1:1234', output.getvalue())

    def test_clean_distribution_runs_without_site_packages_from_another_directory(self):
        spec = importlib.util.spec_from_file_location('build_release', launcher.PROJECT_ROOT / 'tools/build-release.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        archive_path = builder.build_release(self.root / 'Synopsis.zip')
        extracted = self.root / 'Папка с пробелами'
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            self.assertIn('Synopsis/frontend/course.js', names)
            self.assertIn('Synopsis/Start Synopsis.cmd', names)
            self.assertIn('Synopsis/.docs/assets/workspace.png', names)
            self.assertFalse(any(any(part in name for part in ('.synopsis-data', 'node_modules', '.ui-test-data', '__pycache__')) for name in names))
            archive.extractall(extracted)
        outside = self.root / 'different-cwd'
        outside.mkdir()
        app_root = extracted / 'Synopsis'
        process = subprocess.Popen([sys.executable, '-S', '-B', str(app_root / 'start.py'), '--port', '0', '--no-browser'], cwd=outside, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
        output = queue.Queue()
        def consume():
            for line in process.stdout:
                output.put(line)
            output.put(None)
        reader = threading.Thread(target=consume, daemon=True)
        reader.start()
        try:
            line = output.get(timeout=10)
            self.assertIsNotNone(line, 'Packaged process exited before startup')
            self.assertTrue(line.startswith('Synopsis: http://127.0.0.1:'), line)
            url = line.split()[1]
            health = launcher.health_at(url)
            self.assertTrue(health['ui']['ok'])
            self.assertEqual(Path(health['data_dir']), app_root / '.synopsis-data')
            self.assertEqual(Path(health['ui']['root']), app_root / 'frontend')
            with urlopen(url + '/static/course.js', timeout=3) as response:
                self.assertEqual(response.headers.get_content_type(), 'text/javascript')
            self.assertFalse((outside / '.synopsis-data').exists())
            if os.name == 'nt':
                # Exercise the actual double-click entry point, including spaces,
                # Cyrillic paths, a different cwd and an already-running instance.
                port = url.rsplit(':', 1)[1]
                command = f'cmd.exe /d /s /c ""{app_root / "Start Synopsis.cmd"}" --port {port} --no-browser"'
                second = subprocess.run(command, cwd=outside, capture_output=True, text=True, encoding='utf-8', timeout=10)
                self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
                self.assertIn('Synopsis уже запущен:', second.stdout)
                self.assertEqual(launcher.health_at(url)['instance_id'], health['instance_id'])
        finally:
            process.terminate()
            process.wait(timeout=5)
            reader.join(timeout=2)
            process.stdout.close()


if __name__ == '__main__':
    unittest.main()
