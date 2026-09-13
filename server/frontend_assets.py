"""Validate the actual frontend files before advertising a usable server."""
from hashlib import sha256
from pathlib import Path
import re


REQUIRED_FILES = (
    "index.html", "course.html", "bootstrap.js", "common.js", "home.js",
    "course.js", "map.js", "markdown.js", "styles.css", "favicon.svg",
    "vendor/katex/katex.min.css",
)


def frontend_status(root: Path) -> dict:
    root = root.resolve()
    files, missing = {}, []
    required = list(REQUIRED_FILES)
    css = root / "vendor/katex/katex.min.css"
    try:
        fonts = re.findall(r"url\(([^)]+)\)", css.read_text(encoding="utf-8"))
        required.extend("vendor/katex/" + font.strip("\"'") for font in fonts)
    except OSError:
        pass  # The stylesheet itself will be reported below.
    for relative in dict.fromkeys(required):
        path = (root / relative).resolve()
        try:
            if not path.is_relative_to(root):
                raise ValueError("frontend path escapes its root")
            content = path.read_bytes()
            if not content:
                raise ValueError("empty frontend file")
            files[relative] = {"bytes": len(content), "sha256": sha256(content).hexdigest()}
        except (OSError, ValueError):
            missing.append(relative)
    fingerprint = sha256("\n".join(f"{name}:{info['sha256']}" for name, info in files.items()).encode()).hexdigest()[:16]
    return {"ok": not missing, "root": str(root), "fingerprint": fingerprint,
            "missing_files": missing, "files": files}


def require_frontend(root: Path) -> dict:
    status = frontend_status(root)
    if not status["ok"]:
        raise RuntimeError(
            "Synopsis не запущен: отсутствуют, пусты или недоступны файлы UI: "
            + ", ".join(status["missing_files"])
            + f". Каталог интерфейса: {status['root']}. Восстановите frontend/ из этой версии проекта."
        )
    return status
