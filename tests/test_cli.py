import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sev.cli import main


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

    def test_benchmark_refuses_overwrite(self):
        data = Path(__file__).resolve().parents[1] / "data/smoke.jsonl"
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(io.StringIO()):
            code = main(["bench", str(data), "--backend", "rules", "--split", "smoke", "--out", directory])
        self.assertEqual(code, 2)

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
