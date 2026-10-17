"""本地仿真工作台：python -m motorlab.app（只需要 Python 和浏览器）。"""
import argparse
import csv
import errno
from dataclasses import asdict
import io
import json
import math
import mimetypes
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from .diagrams import DIAGRAMS, SIGNALS
from .simulation import DEFAULT_CONFIG, Simulation
from .inverter import WAVE_KEYS
from .version import build_info

WEB = Path(__file__).with_name("web")
DEFAULT_PORT = 8765


class WorkbenchServer(ThreadingHTTPServer):
    daemon_threads = True
    # Windows SO_REUSEADDR can permit two listeners on the same address.
    allow_reuse_address = not hasattr(socket, "SO_EXCLUSIVEADDRUSE")

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def __init__(self, address, config=None):
        super().__init__(address, Handler)
        self.simulation = Simulation(config)
        self.sim_lock = threading.Lock()
        self.build = build_info()
        # Keep the page paired with the loaded engine even if files are updated
        # while this process is running. A new download needs a new process.
        self.assets = {file.name: file.read_bytes() for file in WEB.iterdir() if file.is_file()}

    def state(self):
        sim = self.simulation
        return {"snapshot": sim.snapshot(), "metrics": sim.metrics(),
                "done": sim.done, "config": sim.config,
                "motor_parameters": asdict(sim.parameters),
                "switching_rows": len(sim.switching)}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send(self, status, content, content_type="application/json; charset=utf-8", filename=None):
        if not isinstance(content, bytes):
            content = json.dumps(content, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        try:
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/version":
            self.send(200, self.server.build)
            return
        with self.server.sim_lock:
            if path == "/api/config":
                self.send(200, {"defaults": DEFAULT_CONFIG, "signals": SIGNALS,
                                "diagrams": DIAGRAMS, "app": self.server.build, **self.server.state()})
                return
            if path == "/api/state":
                self.send(200, self.server.state())
                return
            if path == "/api/history":
                self.send(200, {"samples": self.server.simulation.history, **self.server.state()})
                return
            if path == "/api/pwm-trace":
                try:
                    query = parse_qs(urlparse(self.path).query)
                    end = float(query.get('end', [self.server.simulation.snapshot()['time']])[0])
                    start = float(query.get('start', [max(0., end-.002)])[0])
                    if not math.isfinite(start+end) or start < 0 or end < start:
                        raise ValueError('高频窗口的起止时间无效')
                    sim = self.server.simulation
                    self.send(200, {'keys': WAVE_KEYS, 'rows': sim.switching.window(start, end),
                                    'start': start, 'end': end, 'total_rows': len(sim.switching),
                                    'switching': sim.config['inverter_model'] == 'svpwm'})
                except (ValueError, TypeError) as exc:
                    self.send(400, {'error': str(exc)})
                return
            if path == "/api/export-pwm":
                self.send_response(200)
                self.send_header('Content-Type', 'text/csv; charset=utf-8')
                self.send_header('Content-Disposition', 'attachment; filename="motorlab-switching.csv"')
                self.send_header('Connection', 'close')
                self.end_headers()
                buffer = io.StringIO(newline='')
                writer = csv.writer(buffer)
                writer.writerow(WAVE_KEYS)
                try:
                    self.wfile.write(b'\xef\xbb\xbf')
                    for i, row in enumerate(self.server.simulation.switching.rows()):
                        writer.writerow(row)
                        if i%1000 == 999:
                            self.wfile.write(buffer.getvalue().encode('utf-8'))
                            buffer.seek(0); buffer.truncate(0)
                    self.wfile.write(buffer.getvalue().encode('utf-8'))
                except (BrokenPipeError, ConnectionResetError):
                    pass
                self.close_connection = True
                return
            if path == "/api/export":
                rows = self.server.simulation.history
                buffer = io.StringIO(newline="")
                keys = list(self.server.simulation.snapshot())
                writer = csv.DictWriter(buffer, fieldnames=keys)
                writer.writeheader()
                writer.writerows(rows)
                self.send(200, buffer.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", "motorlab-trace.csv")
                return
            if path == "/api/export.json":
                self.send(200, self.server.state(), filename="motorlab-experiment.json")
                return
        assets = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js",
                  "/style.css": "style.css", "/overview.css": "overview.css",
                  "/motor3d.js": "motor3d.js", "/pwm-scope.js": "pwm-scope.js"}
        if path in assets:
            name = assets[path]
            if name in self.server.assets:
                mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
                self.send(200, self.server.assets[name], mime + "; charset=utf-8")
                return
        self.send(404, {"error": "找不到该资源。"})

    def do_POST(self):
        # 所有实验修改串行执行；运行状态属于此服务器，各浏览器共享。
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != self.headers.get("Host"):
            self.send(403, {"error": "请从工作台页面操作实验。"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 32768:
                raise ValueError("请求体大小无效。")
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ValueError("参数必须为 JSON 对象。")
            path = urlparse(self.path).path
            with self.server.sim_lock:
                if path == "/api/reset":
                    # 新配置验证成功后才替换，失败时保留已有实验。
                    fresh = Simulation(body)
                    self.server.simulation = fresh
                    self.send(200, self.server.state())
                elif path == "/api/step":
                    count = body.get("count", 1)
                    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 2000:
                        raise ValueError("步数应为 1–2000 的整数。")
                    samples = self.server.simulation.step(count)
                    self.send(200, {"samples": samples, **self.server.state()})
                else:
                    self.send(404, {"error": "未知操作。"})
        except (ValueError, TypeError, OverflowError) as exc:
            self.send(400, {"error": str(exc)})
        except Exception as exc:
            # 数值异常显示给操作者，不将失败伪装为完成。
            self.send(500, {"error": f"仿真停止：{type(exc).__name__}: {exc}"})


def create_server(port=None):
    """Use a free port if an older session occupies the default; never attach to it."""
    try:
        return WorkbenchServer(("127.0.0.1", DEFAULT_PORT if port is None else port))
    except OSError as exc:
        if port is not None or exc.errno not in {errno.EADDRINUSE, 10048}:
            raise
        return WorkbenchServer(("127.0.0.1", 0))


def main(argv=None):
    parser = argparse.ArgumentParser(description="异步电机 FOC 与在线电阻辨识工作台")
    parser.add_argument("--port", type=int, default=None, help="默认使用 8765；占用时自动换空闲端口")
    parser.add_argument("--open", action="store_true", help="启动后自动打开系统浏览器")
    parser.add_argument("--check", action="store_true", help="检查依赖并显示当前版本、源码位置后退出")
    args = parser.parse_args(argv)
    if args.port is not None and not 0 <= args.port <= 65535:
        parser.error("端口必须在 0–65535 之间；0 表示选择空闲端口。")
    info = build_info()
    print(f"MotorLab v{info['version']} · SVPWM / 3D 电机\n"
          f"构建编号：{info['build_id']}\n运行目录：{info['source_directory']}", flush=True)
    if args.check:
        print("引擎依赖检查通过。使用 python run_workbench.py --open 启动。", flush=True)
        return
    try:
        server = create_server(args.port)
    except OSError as exc:
        parser.exit(2, f"无法启动：{exc}\n可使用 --port 0 自动选择空闲端口。\n")
    address = f"http://127.0.0.1:{server.server_port}/?build={server.build['build_id']}"
    if args.port is None and server.server_port != DEFAULT_PORT:
        print(f"端口 {DEFAULT_PORT} 已被占用，本次使用 {server.server_port}。请使用下面的新地址。", flush=True)
    print(f"工作台已启动：{address}\n按 Ctrl+C 退出。仿真时间按采样推进，不保证硬实时。", flush=True)
    if args.open:
        webbrowser.open(address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
