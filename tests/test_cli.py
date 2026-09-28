import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sev.backends import Rules
from sev.cli import main
from sev.contracts import one_hot, read_jsonl


class CLITests(unittest.TestCase):
    def test_piped_input(self):
        stdout = io.StringIO()
        with patch("sys.stdin", io.StringIO("-x = 1\n+x = 2\n")), contextlib.redirect_stdout(stdout):
            code = main(["--backend", "rules", "--evals", "PRIVILEGE_INCREASE"])
        self.assertEqual(code, 0)
        result = json.loads(stdout.getvalue())
        self.assertIsNone(result["judgments"]["PRIVILEGE_INCREASE"]["probabilities"])
        self.assertFalse(result["model"]["calibrated"])

    def test_empty_input_fails_without_safe_verdict(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("sys.stdin", io.StringIO("")), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["eval", "--backend", "rules"])
        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), "")

    def test_explicit_stdin_shorthand(self):
        stdout = io.StringIO()
        with patch("sys.stdin", io.StringIO("-x = 1\n+x = 2\n")), contextlib.redirect_stdout(stdout):
            code = main(["-", "--backend", "rules", "--evals", "PRIVILEGE_INCREASE"])
        self.assertEqual(code, 0)
        self.assertIn("PRIVILEGE_INCREASE", json.loads(stdout.getvalue())["judgments"])

    def test_benchmark_refuses_overwrite(self):
        data = Path(__file__).resolve().parents[1] / "data/smoke.jsonl"
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(io.StringIO()):
            code = main(["bench", str(data), "--backend", "rules", "--split", "smoke", "--out", directory])
        self.assertEqual(code, 2)

    def test_benchmark_reserves_output_before_loading_backend(self):
        data = Path(__file__).resolve().parents[1] / "data/smoke.jsonl"
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "new-run"

            def build(args):
                self.assertTrue(target.is_dir())
                return Rules()

            with patch("sev.cli.build_backend", side_effect=build), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["bench", str(data), "--backend", "rules", "--split", "smoke", "--out", str(target)]), 0)
            self.assertTrue((target / "report.json").is_file())

    def test_output_failure_prevents_backend_load(self):
        data = Path(__file__).resolve().parents[1] / "data/smoke.jsonl"
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "unwritable"
            with patch("pathlib.Path.mkdir", side_effect=PermissionError("denied")), \
                    patch("sev.cli.build_backend") as build, contextlib.redirect_stderr(io.StringIO()):
                code = main(["bench", str(data), "--backend", "rules", "--split", "smoke", "--out", str(target)])
            self.assertEqual(code, 2)
            build.assert_not_called()

    def test_bad_http_row_still_writes_complete_report(self):
        source = Path(__file__).resolve().parents[1] / "data/smoke.jsonl"
        rows = [read_jsonl(source)[i] for i in (0, 2)]
        good = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"PRIVILEGE_INCREASE": one_hot("NO")})}}]}
        opener = MagicMock()
        opener.open.return_value.__enter__.side_effect = [io.BytesIO(json.dumps(response).encode())
                                                         for response in (good, {"choices": ["private text"]})]
        with tempfile.TemporaryDirectory() as directory:
            data, target = Path(directory) / "data.jsonl", Path(directory) / "run"
            data.write_text("".join(json.dumps(row) + "\n" for row in rows))
            with patch("urllib.request.build_opener", return_value=opener), contextlib.redirect_stdout(io.StringIO()):
                code = main(["bench", str(data), "--backend", "chat", "--model", "fixture", "--revision", "test",
                             "--evals", "PRIVILEGE_INCREASE", "--split", "smoke", "--out", str(target)])
            report = json.loads((target / "report.json").read_text())
            predictions = read_jsonl(target / "predictions.jsonl")
        self.assertEqual(code, 1)
        self.assertEqual(len(predictions), 2)
        self.assertEqual(len(report["errors"]), 1)
        self.assertEqual(report["per_eval"]["PRIVILEGE_INCREASE"]["coverage"], .5)
        self.assertNotIn("private text", json.dumps(report) + json.dumps(predictions))

    def test_git_diff_disables_external_execution(self):
        with patch("sev.cli.subprocess.run") as run, contextlib.redirect_stdout(io.StringIO()):
            run.return_value.returncode = 0
            run.return_value.stdout = "-x = 1\n+x = 2\n"
            self.assertEqual(main(["diff", "--staged", "--backend", "rules"]), 0)
        command = run.call_args.args[0]
        self.assertIn("--no-ext-diff", command)
        self.assertIn("--no-textconv", command)
        self.assertIn("--cached", command)


if __name__ == "__main__":
    unittest.main()
