import copy
import tempfile
import unittest
from pathlib import Path

from sev.contracts import digest, dumps, loads, read_jsonl, validate_dataset
from sev.intake import PROFILE, VERSION, extract_input, git, reproduce, sha256, validate_manifest, verify_batch


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repository"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.name", "Fixture")
        git(self.repo, "config", "user.email", "fixture@example.invalid")
        git(self.repo, "config", "commit.gpgsign", "false")
        (self.repo / "LICENSE").write_text("Fixture license\n")
        (self.repo / "route.py").write_text("def route():\n    return 'before'\n")
        (self.repo / "context.py").write_text("one\ntwo\u2028still two\nthree\n")
        (self.repo / "notes.md").write_text("Old notes\n")
        (self.repo / ".gitattributes").write_text("*.py diff=trap\n")
        self.parent = self.commit()
        (self.repo / "route.py").write_text("def route():\n    return 'after'\n")
        (self.repo / "notes.md").write_text("Curator-only notes\n")
        self.revision = self.commit()
        self.manifest = self.make_manifest()

    def commit(self):
        git(self.repo, "add", "--all")
        git(self.repo, "commit", "-qm", "Fixture metadata must not reach annotators")
        return git(self.repo, "rev-parse", "HEAD").decode().strip()

    def make_manifest(self, paths=None, context=None):
        entry = {"id": "C001", "project": "fixture", "parent": self.parent, "revision": self.revision,
                 "group_id": "fixture-family", "paths": paths or ["route.py"], "context": context or [],
                 "decision": "include", "reason": "Curator-only selection reason", "selection_tags": ["ordinary"],
                 "expected_input_hash": None}
        entry["expected_input_hash"] = digest(extract_input(self.repo, entry)[0])
        excluded = {**entry, "id": "C002", "paths": [], "context": [], "decision": "exclude",
                    "reason": "Unused context variant", "expected_input_hash": None}
        return {"schema_version": VERSION, "batch_id": "fixture", "purpose": "development-pilot",
                "acquired_at": "2026-09-28T00:00:00Z", "selection_notes": "Unit-test fixtures only",
                "extraction": PROFILE.copy(), "entries": [entry, excluded],
                "projects": {"fixture": {"repository": "https://example.invalid/fixture", "snapshot": self.revision,
                            "snapshot_ref": "fixture-tag", "license_review": "Original fixture text",
                            "licenses": [{"path": "LICENSE", "spdx": "fixture-only",
                                          "sha256": sha256((self.repo / "LICENSE").read_bytes())}]}}}

    def reproduce(self, manifest=None, name="output"):
        out = self.root / name
        report = reproduce(manifest or self.manifest, {"fixture": str(self.repo)}, out)
        return out, report

    def test_reproduction_preserves_inputs_licenses_and_selection_audit(self):
        out, report = self.reproduce()
        again, second = self.reproduce(name="second")
        self.assertEqual(report, second)
        self.assertEqual((out / "candidates.jsonl").read_bytes(), (again / "candidates.jsonl").read_bytes())
        rows = read_jsonl(out / "candidates.jsonl")
        self.assertEqual(set(rows[0]), {"candidate_version", "id", "input_hash", "input"})
        self.assertEqual(set(rows[0]["input"]), {"diff", "context"})
        self.assertIn("-    return 'before'", rows[0]["input"]["diff"])
        self.assertIn("+    return 'after'", rows[0]["input"]["diff"])
        self.assertNotIn("Curator-only", dumps(rows))
        self.assertNotIn("Fixture metadata", dumps(rows))
        self.assertEqual(report["audit"][0]["omitted_paths"], ["notes.md"])
        self.assertEqual((out / "licenses/fixture/LICENSE").read_bytes(), (self.repo / "LICENSE").read_bytes())
        self.assertTrue(verify_batch(self.manifest, out)["valid"])
        with self.assertRaisesRegex(ValueError, "dataset record"):
            validate_dataset(rows)  # Unlabelled intake cannot silently become training data.

    def test_context_is_pinned_and_preserves_lf_line_boundaries(self):
        context = [{"revision": self.parent, "path": "context.py", "start_line": 2, "end_line": 2}]
        manifest = self.make_manifest(context=context)
        value, _ = extract_input(self.repo, manifest["entries"][0])
        self.assertEqual(value["context"], [{"path": "before:context.py:2-2", "content": "two\u2028still two\n"}])
        manifest["entries"][0]["context"][0]["end_line"] = 4
        with self.assertRaisesRegex(ValueError, "beyond file"):
            extract_input(self.repo, manifest["entries"][0])

    def test_git_filters_hooks_and_worktree_edits_do_not_execute_or_change_input(self):
        marker = self.root / "executed"
        trap = self.root / "trap"
        trap.write_text(f"#!/bin/sh\ntouch '{marker}'\necho injected\n")
        trap.chmod(0o755)
        for setting in ("diff.external", "diff.trap.textconv", "diff.trap.command", "core.fsmonitor"):
            git(self.repo, "config", setting, str(trap))
        hook = self.repo / ".git/hooks/post-checkout"
        hook.write_bytes(trap.read_bytes())
        hook.chmod(0o755)
        (self.repo / "route.py").write_text("Uncommitted text must not be imported\n")
        out, _ = self.reproduce()
        self.assertFalse(marker.exists())
        self.assertNotIn("Uncommitted", (out / "candidates.jsonl").read_text())

    def test_literal_paths_do_not_expand_globs(self):
        (self.repo / "[x].py").write_text("literal\n")
        (self.repo / "x.py").write_text("not selected\n")
        self.parent, self.revision = self.revision, self.commit()
        manifest = self.make_manifest(paths=["[x].py"])
        value, omitted = extract_input(self.repo, manifest["entries"][0])
        self.assertIn("a/[x].py b/[x].py", value["diff"])
        self.assertIn("+literal", value["diff"])
        self.assertNotIn("not selected", value["diff"])
        self.assertEqual(omitted, ["x.py"])

    def test_wrong_parent_and_merge_commit_rejected(self):
        entry = copy.deepcopy(self.manifest["entries"][0])
        entry["parent"] = self.revision
        with self.assertRaisesRegex(ValueError, "exact parent"):
            extract_input(self.repo, entry)
        tree = git(self.repo, "rev-parse", self.revision + "^{tree}").decode().strip()
        merge = git(self.repo, "commit-tree", tree, "-p", self.parent, "-p", self.revision, "-m", "merge").decode().strip()
        entry.update(parent=self.parent, revision=merge)
        with self.assertRaisesRegex(ValueError, "single-parent"):
            extract_input(self.repo, entry)

    def test_manifest_rejects_mutable_revisions_traversal_and_inconsistent_families(self):
        mutations = [("revision", "HEAD"), ("parent", "main"), ("paths", ["../route.py"]),
                     ("paths", ["/route.py"]), ("paths", ["route.py", "route.py"]),
                     ("project", []), ("group_id", "different"), ("expected_input_hash", None)]
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                manifest = copy.deepcopy(self.manifest)
                manifest["entries"][0][field] = value
                with self.assertRaises(ValueError):
                    validate_manifest(manifest)
        for purpose in ("train", "test"):
            manifest = copy.deepcopy(self.manifest)
            manifest["purpose"] = purpose
            with self.assertRaises(ValueError):
                validate_manifest(manifest)

    def test_binary_symlink_and_oversized_diff_rejected(self):
        entry = copy.deepcopy(self.manifest["entries"][0])
        for index, kind in enumerate(("binary", "symlink", "oversized")):
            path = self.repo / f"bad-{index}"
            if kind == "binary":
                path.write_bytes(b"text\0binary")
            elif kind == "symlink":
                path.symlink_to("route.py")
            else:
                path.write_text("x" * 300_000)
            parent = git(self.repo, "rev-parse", "HEAD").decode().strip()
            entry.update(parent=parent, revision=self.commit(), paths=[path.name])
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                extract_input(self.repo, entry)

    def test_hash_mismatch_and_changed_license_rejected(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["entries"][0]["expected_input_hash"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "input hash mismatch"):
            self.reproduce(manifest, "bad-hash")
        (self.repo / "LICENSE").write_text("Changed license\n")
        (self.repo / "route.py").write_text("another change\n")
        self.parent, self.revision = self.revision, self.commit()
        manifest = self.make_manifest()
        with self.assertRaisesRegex(ValueError, "source license changed"):
            self.reproduce(manifest, "changed-license")

    def test_existing_output_refused_without_overwrite(self):
        out, _ = self.reproduce()
        original = (out / "candidates.jsonl").read_bytes()
        with self.assertRaises(FileExistsError):
            self.reproduce()
        self.assertEqual((out / "candidates.jsonl").read_bytes(), original)

    def test_offline_verification_detects_tampering(self):
        for kind in ("input", "license", "count", "audit", "manifest", "provenance-leak"):
            with self.subTest(kind=kind):
                out, report = self.reproduce(name=kind)
                manifest = copy.deepcopy(self.manifest)
                if kind in ("input", "provenance-leak"):
                    rows = read_jsonl(out / "candidates.jsonl")
                    if kind == "input":
                        rows[0]["input"]["diff"] += "+injected\n"
                    else:
                        rows[0]["source"] = {"advisory": "leaked"}
                    (out / "candidates.jsonl").write_text(dumps(rows[0]) + "\n")
                elif kind == "license":
                    (out / "licenses/fixture/LICENSE").write_text("relicensed")
                elif kind == "manifest":
                    manifest["entries"][0]["reason"] = "changed"
                else:
                    if kind == "count":
                        report["included"] += 1
                    else:
                        report["audit"][0]["decision"] = "exclude"
                    (out / "report.json").write_text(dumps(report))
                with self.assertRaises(ValueError):
                    verify_batch(manifest, out)


class PilotTests(unittest.TestCase):
    def test_committed_batch_is_unlabelled_and_integrity_checked(self):
        directory = Path(__file__).resolve().parents[1] / "data/pilot-001"
        manifest = loads((directory / "manifest.json").read_text())
        self.assertEqual(verify_batch(manifest, directory)["candidates"], 32)
        self.assertEqual(len(manifest["entries"]), 320)
        self.assertEqual({e["project"] for e in manifest["entries"]}, {"django", "flask", "werkzeug", "iam"})


if __name__ == "__main__":
    unittest.main()
