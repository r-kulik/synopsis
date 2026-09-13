"""Build a clean source distribution: Python required, pip/npm not required."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from server.frontend_assets import require_frontend

PACKAGES = ("server", "storage", "synopsis_domain", "map", "map_settings", "geometry",
            "selection", "render", "markdown", "facts", "source_links", "transfer",
            "editor", "library", "shell")


def release_files(root: Path = ROOT) -> list[Path]:
    paths = [root / name for name in ("start.py", "Start Synopsis.cmd", "README.md", "LICENSE")]
    for name in PACKAGES:
        paths.extend(p for p in (root / name).rglob("*.py") if not {"tests", "__pycache__"}.intersection(p.relative_to(root / name).parts))
    paths.extend(p for p in (root / "frontend").rglob("*") if p.is_file())
    paths.extend((root / ".docs").rglob("*.md"))
    paths.extend(p for p in (root / ".docs/assets").iterdir() if p.suffix in {".svg", ".png"})
    for path in paths:
        if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError(f"Not a regular release file within the project: {path}")
    return sorted(set(paths))


def build_release(output: Path) -> Path:
    require_frontend(ROOT / "frontend")
    paths = release_files()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, "Synopsis/" + path.relative_to(ROOT).as_posix())
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/Synopsis-portable.zip")
    result = build_release(parser.parse_args().output.resolve())
    print(f"Built {result} ({result.stat().st_size:,} bytes). Requires Python 3.11+, no pip/npm.")
