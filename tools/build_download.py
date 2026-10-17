"""Build an identifiable, source-only ZIP; refresh the legacy filename as well."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from motorlab.version import VERSION, build_info


def build(output=None):
    output = Path(output) if output else ROOT / "outputs"
    output.mkdir(parents=True, exist_ok=True)
    paths = [ROOT / name for name in (
        "README.md", "requirements.txt", "pyproject.toml", "run_workbench.py",
        "start_windows.bat", "start_workbench.sh", "下载后先看这里.txt", ".gitignore")]
    for directory in ("motorlab", "docs", "tests", "tools"):
        paths.extend(file for file in (ROOT/directory).rglob("*")
                     if file.is_file() and "__pycache__" not in file.parts
                     and file.suffix != ".pyc")
    paths = sorted(set(paths))
    content = {path.relative_to(ROOT).as_posix(): path.read_bytes() for path in paths}
    info = build_info()
    manifest = {"version": VERSION, "build_id": info["build_id"],
                "files": {name: hashlib.sha256(data).hexdigest() for name, data in content.items()}}
    archive = output / f"MotorLab-v{VERSION}.zip"
    prefix = f"MotorLab-v{VERSION}/"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        for name, data in content.items():
            zipped.writestr(prefix+name, data)
        zipped.writestr(prefix+"DOWNLOAD-MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    # Previously this filename could keep pointing to an obsolete v0.2 build.
    shutil.copyfile(archive, output/"MotorLab.zip")
    print(json.dumps({"archive": str(archive), "version": VERSION, "build_id": info["build_id"],
                      "files": len(content), "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}, ensure_ascii=False))
    return archive


if __name__ == "__main__":
    build()
