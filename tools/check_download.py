"""Extract a real download and launch it from an unrelated working directory."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def check(archive):
    with tempfile.TemporaryDirectory(prefix="motorlab-download-") as directory:
        temp = Path(directory)
        with zipfile.ZipFile(archive) as zipped:
            for name in zipped.namelist():
                target = (temp/name).resolve()
                if not target.is_relative_to(temp.resolve()):
                    raise ValueError("下载包包含目录外路径")
            zipped.extractall(temp)
        roots = list(temp.glob("*/run_workbench.py"))
        assert len(roots) == 1, "下载包应包含一个明确的启动目录"
        extracted = roots[0].parent
        manifest_path = extracted/"DOWNLOAD-MANIFEST.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for name, expected in manifest["files"].items():
                assert hashlib.sha256((extracted/name).read_bytes()).hexdigest() == expected, name
        # An older checkout on PYTHONPATH must not replace the downloaded package.
        env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUNBUFFERED": "1"}
        log_path = temp/"startup.log"
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen([sys.executable, str(extracted/"run_workbench.py"), "--port", "0"],
                                       cwd=temp, env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic()+20
                address = None
                while time.monotonic() < deadline:
                    output = log_path.read_text(encoding="utf-8")
                    match = re.search(r"http://127\.0\.0\.1:\d+/\?build=[0-9a-f]+", output)
                    if match:
                        address = match.group(); break
                    if process.poll() is not None:
                        raise AssertionError(output)
                    time.sleep(.05)
                assert address, log_path.read_text(encoding="utf-8")
                base = address.split('/?')[0]

                def request(path, body=None):
                    req = Request(base+path, data=None if body is None else json.dumps(body).encode(),
                                  headers={"Content-Type": "application/json"})
                    with urlopen(req, timeout=20) as response:
                        return response.read()

                info = json.loads(request('/api/version'))
                assert info['version'] == '0.4.0', info
                assert Path(info['source_directory']).resolve() == extracted.resolve(), info
                assert f'data-version="{info["version"]}"'.encode() in request('/')
                for name in ('motor3d.js', 'pwm-scope.js', 'overview.css'):
                    assert request('/'+name) == (extracted/'motorlab'/'web'/name).read_bytes()
                request('/api/reset', {'duration': .5, 'sample_time': .00025, 'motor_rs': 2., 'motor_poles': 3})
                state = json.loads(request('/api/step', {'count': 2000}))
                assert state['done'] and state['snapshot']['time'] == .5
                assert state['motor_parameters']['rs'] == 2 and state['motor_parameters']['poles'] == 3
                assert state['snapshot']['rotor_angle'] > 0
                trace = json.loads(request('/api/pwm-trace?start=0.498&end=0.5'))
                gate = trace['keys'].index('gate_au')
                assert trace['switching'] and {row[gate] for row in trace['rows']} == {0., 1.}
                print(json.dumps({'archive': str(archive), 'version': info['version'], 'build_id': info['build_id'],
                                  'result': 'passed', 'checks': 'fresh extraction, own source, real startup, parameters, rotor motion, switching gates'}, ensure_ascii=False))
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    check(parser.parse_args().archive)
