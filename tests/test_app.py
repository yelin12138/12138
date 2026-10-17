"""真实 HTTP 请求覆盖单步、重置、导出与模块/信号映射。"""
import csv
import io
import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from motorlab.app import WorkbenchServer


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = WorkbenchServer(("127.0.0.1", 0))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, path, body=None):
        request = Request(self.base+path, data=None if body is None else json.dumps(body).encode(),
                          headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=10) as response:
            return response.read()

    def setUp(self):
        self.request("/api/reset", {})

    def test_single_sample_and_export(self):
        state = json.loads(self.request("/api/step", {"count": 1}))
        self.assertEqual(len(state["samples"]), 1)
        self.assertAlmostEqual(state["snapshot"]["time"], state["config"]["sample_time"])
        rows = list(csv.DictReader(io.StringIO(self.request("/api/export").decode("utf-8-sig"))))
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(float(rows[0]["rr_est"]), state["snapshot"]["rr_est"])

    def test_invalid_reset_preserves_experiment(self):
        self.request("/api/step", {"count": 3})
        before = json.loads(self.request("/api/state"))
        with self.assertRaises(HTTPError) as caught:
            self.request("/api/reset", {"sample_time": -1})
        self.assertEqual(caught.exception.code, 400)
        after = json.loads(self.request("/api/state"))
        self.assertEqual(before["snapshot"], after["snapshot"])

    def test_diagram_signal_integrity(self):
        payload = json.loads(self.request("/api/config"))
        sample = json.loads(self.request("/api/step", {"count": 2}))["snapshot"]
        diagrams, signals = payload["diagrams"], payload["signals"]
        self.assertIn("system", diagrams)
        for name, diagram in diagrams.items():
            ids = {node["id"] for node in diagram["nodes"]}
            self.assertEqual(len(ids), len(diagram["nodes"]), name)
            for node in diagram["nodes"]:
                if node.get("child"):
                    self.assertIn(node["child"], diagrams, name)
            for edge in diagram["edges"]:
                self.assertIn(edge["from"], ids, name)
                self.assertIn(edge["to"], ids, name)
            for element in diagram["nodes"] + diagram["edges"]:
                if element.get("signal"):
                    key = element["signal"]
                    self.assertIn(key, signals, name)
                    self.assertIn(key, sample, f"{name}: {key}")

    def test_bad_count_is_rejected(self):
        with self.assertRaises(HTTPError) as caught:
            self.request("/api/step", {"count": 2.5})
        self.assertEqual(caught.exception.code, 400)
        state = json.loads(self.request("/api/state"))
        self.assertEqual(state["snapshot"]["time"], 0)

    def test_switching_window_and_lossless_csv(self):
        self.request('/api/step', {'count': 3})
        trace=json.loads(self.request('/api/pwm-trace?start=0&end=0.0015'))
        self.assertTrue(trace['switching'])
        self.assertGreater(len(trace['rows']), 20)
        self.assertEqual(len(trace['rows']), trace['total_rows'])
        self.assertAlmostEqual(trace['rows'][-1][0], .0015)
        exported=list(csv.DictReader(io.StringIO(self.request('/api/export-pwm').decode('utf-8-sig'))))
        self.assertEqual(len(exported), trace['total_rows'])
        self.assertAlmostEqual(float(exported[-1]['time']), .0015)
        self.assertEqual(int(float(exported[-1]['gate_au']))+int(float(exported[-1]['gate_al'])), 1)

    def test_parameter_update_and_average_mode(self):
        state=json.loads(self.request('/api/reset', {'motor_rs':2.,'motor_poles':3,'inverter_model':'average'}))
        self.assertEqual(state['motor_parameters']['rs'],2.)
        self.assertEqual(state['motor_parameters']['poles'],3)
        self.request('/api/step', {'count':3})
        trace=json.loads(self.request('/api/pwm-trace'))
        self.assertFalse(trace['switching'])
        self.assertEqual(trace['rows'],[])


if __name__ == "__main__":
    unittest.main()
