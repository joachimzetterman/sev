"""Report adaptation tests with a fake Modal SDK; never start cloud compute."""

import contextlib
import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sev.backends import Rules
from sev.contracts import digest, one_hot, read_jsonl
from sev.experiment import build_report, evaluate

ROOT = Path(__file__).resolve().parents[1]


class ModalReportTests(unittest.TestCase):
    def setUp(self):
        self.sdk = MagicMock()
        self.sdk.App.return_value.function.return_value = lambda function: function
        spec = importlib.util.spec_from_file_location("sev_modal_report_fixture", ROOT / "scripts/modal_baseline.py")
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict("sys.modules", {"modal": self.sdk}):
            spec.loader.exec_module(self.module)
        self.rows = [read_jsonl(ROOT / "data/smoke.jsonl")[i] for i in (0, 2)]
        self.names = ["PRIVILEGE_INCREASE"]
        self.result = {
            "samples": [
                {"judgments": {self.names[0]: one_hot("NO")}, "error_type": None,
                 "latency_ms": 100, "input_tokens": 12, "output_tokens": 5},
                {"judgments": {self.names[0]: {"probabilities": None}}, "error_type": "invalid_structured_response",
                 "latency_ms": 200, "input_tokens": 15, "output_tokens": 20}],
            "model_load_ms": 10, "server_peak_rss_bytes": 1000, "gpu_name": "fake-gpu",
            "allocated_gpu_memory_bytes": 2000, "runtime_versions": {"vllm": "fixture"}}

    def test_common_report_fields_failures_and_server_timings(self):
        report, predictions = self.module.report_remote(self.rows, self.names, self.result, 999)
        ordinary, _ = evaluate(self.rows, Rules(), self.names)
        self.assertEqual(report.keys(), ordinary.keys())
        self.assertLessEqual(ordinary["performance"].keys(), report["performance"].keys())
        self.assertEqual(report["annotation_status"], {"provisional": 2})
        self.assertIn("uv.lock", report["source_hashes"])
        self.assertIn("scripts/modal_baseline.py", report["source_hashes"])
        self.assertEqual(report["performance"]["timing_scope"], "server_tokenization_and_generation")
        self.assertEqual(report["performance"]["first_eval_ms"], 100)
        self.assertEqual(report["performance"]["warm_p50_ms"], 200)
        self.assertEqual(report["performance"]["load_plus_first_eval_ms"], 110)
        self.assertEqual(report["performance"]["by_diff_bytes"]["<1KiB"]["n"], 2)
        self.assertIsNone(report["performance"]["inference_cost_usd"])
        self.assertEqual(report["per_eval"][self.names[0]]["coverage"], .5)
        self.assertEqual(report["per_eval"][self.names[0]]["accuracy_including_abstentions"], .5)
        self.assertEqual(report["errors"], [{"id": self.rows[1]["id"], "repeat": 0,
                                            "error_type": "invalid_structured_response"}])
        self.assertEqual(len(predictions), 2)
        self.sdk.App.return_value.run.assert_not_called()

    def test_incomplete_samples_are_rejected(self):
        self.result["samples"].pop()
        with self.assertRaisesRegex(ValueError, "incomplete cloud experiment"):
            self.module.report_remote(self.rows, self.names, self.result, 999)

    def test_runner_sources_can_be_outside_installed_package(self):
        report, predictions = self.module.report_remote(self.rows, self.names, self.result, 999)
        with tempfile.TemporaryDirectory() as directory:
            runner = Path(directory) / "runner.py"
            runner.write_text("# separate checkout using the installed sev package\n")
            rebuilt = build_report(self.rows, report["model"], self.names, predictions, report["timing"],
                                   source_paths={"scripts/runner.py": runner})
            self.assertEqual(rebuilt["source_hashes"]["scripts/runner.py"], digest(runner.read_text()))

    def test_existing_output_prevents_cloud_start(self):
        with tempfile.TemporaryDirectory() as directory:
            argv = ["modal_baseline", "--data", str(ROOT / "data/smoke.jsonl"), "--out", directory]
            with patch("sys.argv", argv), patch.dict(os.environ, {"MODAL_PROFILE": "fixture"}), \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stopped:
                self.module.main()
        self.assertEqual(stopped.exception.code, 2)
        self.sdk.App.return_value.run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
