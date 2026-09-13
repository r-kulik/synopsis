"""Compatibility entry point; pages and assets now live in frontend/."""
from pathlib import Path

def index_page():
    return (Path(__file__).resolve().parent.parent / "frontend" / "index.html").read_text(encoding="utf-8")
