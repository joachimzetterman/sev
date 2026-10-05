import contextlib
import io
import json
import os
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

from sev import security_eval
from sev.api import render_text
from sev.backends import Rules
from sev.cli import git_diff, main
from sev.contracts import one_hot
from sev.settings import DEFAULTS, load_settings, resolve_settings, save_settings

DIFF = "--- a/query.sql\n+++ b/query.sql\n@@ -1 +1 @@\n-SELECT 1;\n+DROP TABLE users;\n"


class PreviewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.config = self.directory / "user/config.json"
        environment = patch.dict(os.environ, {"SEV_CONFIG": str(self.config)})
        environment.start()
        self.addCleanup(environment.stop)

    def cli(self, args, diff=DIFF):
        out, err = io.StringIO(), io.StringIO()
        with patch("sys.stdin", io.StringIO(diff)), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(args)
        return code, out.getvalue(), err.getvalue()

    def test_configure_then_bare_pipe_and_sdk_share_output(self):
        self.assertEqual(self.cli(["configure", "--backend", "rules"])[0], 0)
        code, output, _ = self.cli([])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output), security_eval(DIFF))
        self.assertEqual(json.loads(output)["judgments"]["DESTRUCTIVE_OPERATION"], one_hot("YES"))
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)

    def test_configuration_does_not_load_model_or_contact_endpoint(self):
        with patch("sev.settings.create_backend") as create, patch("urllib.request.build_opener") as opener:
            self.assertEqual(self.cli(["configure", "--backend", "chat", "--model", "fixture", "--revision", "r1"])[0], 0)
        create.assert_not_called()
        opener.assert_not_called()

    def test_configure_refuses_overwrite_and_secrets_in_file(self):
        self.cli(["configure", "--backend", "rules"])
        original = self.config.read_bytes()
        self.assertEqual(self.cli(["configure", "--backend", "rules"])[0], 2)
        self.assertEqual(self.config.read_bytes(), original)
        self.assertEqual(self.cli(["configure", "--backend", "rules", "--force"])[0], 0)
        document = json.loads(self.config.read_text())
        document["inference"]["api_key"] = "should-not-be-stored"
        self.config.write_text(json.dumps(document))
        with self.assertRaisesRegex(ValueError, "API keys belong"):
            load_settings()

    def test_missing_settings_and_explicit_backend_override(self):
        code, output, error = self.cli([])
        self.assertEqual((code, output), (2, ""))
        self.assertIn("sev configure", error)
        self.config.parent.mkdir()
        self.config.write_text("invalid saved configuration")
        self.assertEqual(self.cli(["--backend", "rules"])[0], 0)
        with patch("sev.settings.create_backend") as create, self.assertRaises(ValueError):
            security_eval("")
        create.assert_not_called()

    def test_remote_consent_is_scoped_to_configured_endpoint(self):
        remote = {**DEFAULTS, "backend": "chat", "model": "fixture", "revision": "r1",
                  "endpoint": "https://approved.example", "allow_remote": True}
        save_settings(remote)
        self.assertTrue(resolve_settings({})["allow_remote"])
        with self.assertRaisesRegex(ValueError, "remote inference requires"):
            resolve_settings({"endpoint": "https://different.example"})
        allowed = resolve_settings({"endpoint": "https://different.example", "allow_remote": True})
        self.assertTrue(allowed["allow_remote"])
        with self.assertRaisesRegex(ValueError, "remote inference requires"):
            resolve_settings({"backend": "chat", "model": "fixture", "revision": "r2",
                              "endpoint": "https://approved.example"})
        self.assertFalse(resolve_settings({"backend": "rules"})["allow_remote"])

    def test_local_model_path_survives_working_directory_change(self):
        model = self.directory / "model"
        model.mkdir()
        save_settings({**DEFAULTS, "backend": "mlx", "model": str(model)})
        self.assertEqual(load_settings()["model"], str(model.resolve()))
        with self.assertRaisesRegex(ValueError, "does not exist"):
            save_settings({**DEFAULTS, "backend": "mlx", "model": str(model / "missing")}, force=True)
        self.assertEqual(load_settings()["model"], str(model.resolve()))

    def test_text_preserves_uncertainty_and_abstention_without_percentages(self):
        result = security_eval(DIFF, ["DESTRUCTIVE_OPERATION", "PRIVILEGE_INCREASE"], backend=Rules())
        result["judgments"]["PRIVILEGE_INCREASE"] = one_hot("INSUFFICIENT_CONTEXT")
        result["judgments"]["AUTHORIZATION_RELEVANT"] = one_hot("UNKNOWN")
        result["judgments"]["TENANT_BOUNDARY_CHANGE"] = {"probabilities": None}
        rendered = render_text(result)
        for state in ("YES", "INSUFFICIENT_CONTEXT", "UNKNOWN", "ABSTAIN"):
            self.assertIn(state, rendered)
        self.assertNotIn("%", rendered)
        self.assertNotIn("secure", rendered.lower())
        code, output, _ = self.cli(["--backend", "rules", "--text"])
        self.assertEqual(code, 0)
        self.assertIn("DESTRUCTIVE_OPERATION", output)
        self.assertEqual(self.cli(["--backend", "rules", "--json"])[0], 0)

    def test_configured_local_http_round_trip_sends_only_supplied_input(self):
        received = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
                prediction = {"DESTRUCTIVE_OPERATION": one_hot("YES")}
                body = json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(prediction)}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            code, _, _ = self.cli(["configure", "--backend", "chat", "--model", "fixture", "--revision", "r1",
                                   "--endpoint", f"http://127.0.0.1:{server.server_port}"])
            self.assertEqual(code, 0)
            code, output, _ = self.cli(["--evals", "DESTRUCTIVE_OPERATION", "--json"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output)["judgments"]["DESTRUCTIVE_OPERATION"], one_hot("YES"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        self.assertEqual(received[0][0], "/v1/chat/completions")
        self.assertEqual(json.loads(received[0][1]["messages"][1]["content"]), {"diff": DIFF, "context": []})


class BaseDiffTests(unittest.TestCase):
    def test_base_uses_common_ancestor_and_excludes_uncommitted_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
            env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)

            def git(*args):
                return subprocess.run(["git", "-C", directory, "-c", "user.name=Fixture", "-c",
                                       "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false",
                                       "-c", "core.hooksPath=/dev/null", *args],
                                      env=env, check=True, capture_output=True, text=True).stdout.strip()

            git("init", "-q")
            (repo / "code.py").write_text("original\n")
            git("add", ".")
            git("commit", "-qm", "initial")
            git("branch", "base")
            (repo / "code.py").write_text("feature\n")
            git("commit", "-qam", "feature")
            (repo / "code.py").write_text("uncommitted\n")
            # GIT_DIR/WORK_TREE avoids changing the process-wide working directory.
            with patch.dict(os.environ, {**env, "GIT_DIR": str(repo / ".git"), "GIT_WORK_TREE": str(repo)}):
                diff = git_diff(base="base")
                self.assertIn("+feature", diff)
                self.assertNotIn("uncommitted", diff)
                with self.assertRaisesRegex(ValueError, "must resolve"):
                    git_diff(base="--output=unwanted-file")
                self.assertFalse((repo / "unwanted-file").exists())


if __name__ == "__main__":
    unittest.main()
