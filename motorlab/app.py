"""本地仿真工作台：python -m motorlab.app（只需要 Python 和浏览器）。"""
import argparse
import csv
from dataclasses import asdict
import io
import json
import mimetypes
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .diagrams import DIAGRAMS, SIGNALS
from .simulation import DEFAULT_CONFIG, Simulation

WEB = Path(__file__).with_name("web")


class WorkbenchServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, config=None):
        super().__init__(address, Handler)
        self.simulation = Simulation(config)
        self.sim_lock = threading.Lock()

    def state(self):
        sim = self.simulation
        return {"snapshot": sim.snapshot(), "metrics": sim.metrics(),
                "done": sim.done, "config": sim.config,
                "motor_parameters": asdict(sim.parameters)}


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
        with self.server.sim_lock:
            if path == "/api/config":
                self.send(200, {"defaults": DEFAULT_CONFIG, "signals": SIGNALS,
                                "diagrams": DIAGRAMS, **self.server.state()})
                return
            if path == "/api/state":
                self.send(200, self.server.state())
                return
            if path == "/api/history":
                self.send(200, {"samples": self.server.simulation.history, **self.server.state()})
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
        assets = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/style.css": "style.css"}
        if path in assets:
            asset = WEB / assets[path]
            if asset.is_file():
                mime = mimetypes.guess_type(asset.name)[0] or "application/octet-stream"
                self.send(200, asset.read_bytes(), mime + "; charset=utf-8")
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


def main():
    parser = argparse.ArgumentParser(description="异步电机 FOC 与在线电阻辨识工作台")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="启动后自动打开系统浏览器")
    args = parser.parse_args()
    server = WorkbenchServer(("127.0.0.1", args.port))
    address = f"http://127.0.0.1:{server.server_port}"
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
