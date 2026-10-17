"""Identify the source actually used by this Python process, including ZIP installs."""
import hashlib
from pathlib import Path

VERSION = "0.4.0"


def build_info():
    package = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for file in sorted(package.rglob("*")):
        if file.is_file() and file.suffix in {".py", ".js", ".css", ".html"}:
            digest.update(file.relative_to(package).as_posix().encode())
            digest.update(b"\0")
            digest.update(file.read_bytes())
    return {"version": VERSION, "build_id": digest.hexdigest()[:12],
            "source_directory": str(package.parent),
            "features": ["svpwm-switching", "motor-3d", "editable-motor", "editable-timing"]}
