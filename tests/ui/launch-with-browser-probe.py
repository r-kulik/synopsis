"""Observe the app's real auto-open request without changing the user's browser."""
from pathlib import Path
import runpy
import sys
import webbrowser

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))


class BrowserProbe:
    def open(self, url, new=0, autoraise=True):
        print('BROWSER_OPEN ' + url, flush=True)
        return True


webbrowser.register('synopsis-test-probe', None, BrowserProbe(), preferred=True)
runpy.run_path(str(root / 'start.py'), run_name='__main__')
