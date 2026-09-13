"""One-command desktop launch with a readiness-checked browser opening."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import threading
import time
from urllib.request import build_opener, ProxyHandler
import webbrowser

from .frontend_assets import require_frontend
from .http_server import FRONTEND, create_server


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / ".synopsis-data"


def health_at(url: str) -> dict | None:
    """Loopback checks bypass corporate HTTP proxies and never make writes."""
    try:
        opener = build_opener(ProxyHandler({}))
        with opener.open(url + "/api/health", timeout=0.5) as response:
            value = json.load(response)
            return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def open_browser(url: str) -> bool:
    try:
        opened = webbrowser.open_new_tab(url)
    except Exception:
        opened = False
    if not opened:
        print(f"Не удалось открыть браузер автоматически. Откройте {url}", flush=True)
    return bool(opened)


def open_when_ready(url: str, instance_id: str, stopped: threading.Event) -> None:
    deadline = time.monotonic() + 8
    while not stopped.is_set() and time.monotonic() < deadline:
        health = health_at(url)
        if health and health.get("instance_id") == instance_id and health.get("status") == "ok":
            if not stopped.is_set():
                open_browser(url)
            return
        stopped.wait(0.05)
    if not stopped.is_set():
        print(f"Сервер ещё не подтвердил готовность. Диагностика: {url}/api/health", flush=True)


def same_instance(health: dict | None, data_dir: Path, ui: dict) -> bool:
    try:
        return bool(
            health and health["app"] == "synopsis" and health["status"] == "ok"
            and health["ui"]["ok"] and health["instance_id"]
            and Path(health["data_dir"]).resolve() == data_dir.resolve()
            and Path(health["ui"]["root"]).resolve() == FRONTEND.resolve()
            and health["ui"]["fingerprint"] == ui["fingerprint"]
        )
    except (KeyError, TypeError, ValueError, OSError):
        return False


def launch(data_dir: Path | str = DEFAULT_DATA_DIR, port: int = 8765, *, browser: bool = True) -> int:
    """Run one server; a second launch may reopen only that same app/data pair."""
    data_dir = Path(data_dir).resolve()
    ui = require_frontend(FRONTEND)
    try:
        httpd = create_server(data_dir, port=port)
    except OSError as error:
        if error.errno not in {48, 98, 10048} and getattr(error, "winerror", None) != 10048:
            raise
        url = f"http://127.0.0.1:{port}"
        if same_instance(health_at(url), data_dir, ui):
            print(f"Synopsis уже запущен: {url}\nДанные: {data_dir}", flush=True)
            if browser:
                open_browser(url)
            return 0
        raise RuntimeError(
            f"Порт {port} занят другим процессом или другой копией Synopsis. "
            "Ничего не остановлено. Закройте прежний сервер или запустите: python start.py --port 8766"
        ) from error
    stopped = threading.Event()
    browser_thread = None
    with httpd:
        url = f"http://127.0.0.1:{httpd.server_port}"
        print(f"Synopsis: {url}  data: {data_dir}", flush=True)
        print(f"UI: {ui['root']}  build: {ui['fingerprint']}  instance: {httpd.instance_id}", flush=True)
        print("Оставьте это окно открытым. Для остановки нажмите Ctrl+C.", flush=True)
        if browser:
            browser_thread = threading.Thread(
                target=open_when_ready, args=(url, httpd.instance_id, stopped), daemon=True,
            )
            browser_thread.start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nSynopsis остановлен. Сохранённые курсы остались на диске.", flush=True)
        finally:
            stopped.set()
            if browser_thread:
                browser_thread.join(timeout=1)
    return 0


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Synopsis — локальные конспекты и карта знаний. Браузер откроется сам.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR, help="каталог данных (по умолчанию .synopsis-data рядом со start.py)")
    parser.add_argument("--port", type=int, default=8765, help="локальный порт (по умолчанию 8765)")
    parser.add_argument("--no-browser", action="store_true", help="не открывать браузер автоматически")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("порт должен быть от 0 до 65535")
    try:
        return launch(args.data_dir, args.port, browser=not args.no_browser)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Не удалось запустить Synopsis: {error}", file=sys.stderr, flush=True)
        return 1
