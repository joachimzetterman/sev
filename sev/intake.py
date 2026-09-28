"""Reproduce unlabelled development candidates from local, pinned Git objects."""

import hashlib
import os
import re
import subprocess
from collections import Counter
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from .contracts import MAX_INPUT_BYTES, digest, dumps, loads, read_jsonl, validate_input

VERSION = "sev-intake-0.1"
PROFILE = {"diff_algorithm": "myers", "context_lines": 3, "renames": False,
           "scope": "selected-files", "max_input_bytes": MAX_INPUT_BYTES}
MAX_BLOB_BYTES = 2_000_000


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def object_keys(value, keys, name):
    require(isinstance(value, dict) and set(value) == set(keys), f"invalid {name} fields")


def text(value):
    return isinstance(value, str) and bool(value.strip())


def oid(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) is not None


def hash_value(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def path_value(value):
    require(text(value) and not any(c in value for c in "\x00\n\r\\"), "invalid source path")
    path = PurePosixPath(value)
    require(not path.is_absolute() and all(part not in ("", ".", "..") for part in value.split("/")),
            "source paths must be literal relative paths without traversal")
    return value


def validate_manifest(manifest):
    object_keys(manifest, ("schema_version", "batch_id", "purpose", "acquired_at", "selection_notes",
                           "extraction", "projects", "entries"), "manifest")
    require(manifest["schema_version"] == VERSION and manifest["purpose"] == "development-pilot",
            "intake is unlabelled development material, never train or test")
    require(all(text(manifest[k]) for k in ("batch_id", "acquired_at", "selection_notes")), "missing batch provenance")
    require(manifest["extraction"] == PROFILE, "unsupported extraction profile")
    projects = manifest["projects"]
    require(isinstance(projects, dict) and projects, "projects are required")
    for name, project in projects.items():
        require(isinstance(name, str) and re.fullmatch(r"[a-z0-9_-]+", name) is not None, "invalid project identifier")
        object_keys(project, ("repository", "snapshot", "snapshot_ref", "licenses", "license_review"), "project")
        require(text(project["repository"]), "repository URL is required")
        url = urlsplit(project["repository"])
        require(url.scheme == "https" and url.hostname and not (url.username or url.password or url.query or url.fragment),
                "source repository must be an HTTPS URL without credentials")
        require(oid(project["snapshot"]) and text(project["snapshot_ref"]) and text(project["license_review"]),
                "project needs a pinned snapshot and license review")
        require(isinstance(project["licenses"], list) and project["licenses"], "license files are required")
        for license_file in project["licenses"]:
            object_keys(license_file, ("path", "spdx", "sha256"), "license")
            path_value(license_file["path"])
            require(text(license_file["spdx"]) and hash_value(license_file["sha256"]), "invalid license provenance")
    entries = manifest["entries"]
    require(isinstance(entries, list) and 1 <= len(entries) <= 1000, "manifest needs 1–1000 entries")
    ids, revisions = set(), {}
    for entry in entries:
        object_keys(entry, ("id", "project", "parent", "revision", "group_id", "paths", "context",
                            "decision", "reason", "selection_tags", "expected_input_hash"), "entry")
        require(text(entry["id"]) and entry["id"] not in ids, "duplicate or invalid candidate id")
        ids.add(entry["id"])
        require(text(entry["project"]) and entry["project"] in projects
                and oid(entry["parent"]) and oid(entry["revision"]), "invalid revision provenance")
        require(text(entry["group_id"]) and text(entry["reason"]), "family and selection reason are required")
        key = (entry["project"], entry["revision"])
        require(revisions.setdefault(key, entry["group_id"]) == entry["group_id"], "context variants must share a family")
        require(entry["decision"] in ("include", "exclude"), "invalid selection decision")
        require(isinstance(entry["selection_tags"], list) and entry["selection_tags"]
                and all(text(t) for t in entry["selection_tags"]), "selection tags are required")
        paths = entry["paths"]
        require(isinstance(paths, list) and len(paths) <= 32 and all(isinstance(p, str) for p in paths), "invalid selected paths")
        require(len(paths) == len(set(paths)), "duplicate selected path")
        for path in paths:
            path_value(path)
        contexts = entry["context"]
        require(isinstance(contexts, list) and len(contexts) <= 8, "invalid context list")
        for context in contexts:
            object_keys(context, ("revision", "path", "start_line", "end_line"), "context")
            path_value(context["path"])
            require(context["revision"] in (entry["parent"], entry["revision"]), "context must come from a pinned side of the change")
            require(type(context["start_line"]) is int and type(context["end_line"]) is int
                    and 1 <= context["start_line"] <= context["end_line"], "invalid context line range")
        if entry["decision"] == "include":
            require(paths and hash_value(entry["expected_input_hash"]), "included candidates need paths and an expected input hash")
        else:
            require(not paths and not contexts and entry["expected_input_hash"] is None,
                    "excluded entries must not contain model inputs")
    require({e["project"] for e in entries if e["decision"] == "include"} == set(projects),
            "each project needs an included candidate")
    return manifest


def git(repo, *args):
    # Read Git objects only: never checkout, execute source, use hooks or fetch.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0",
               GIT_NO_LAZY_FETCH="1", GIT_NO_REPLACE_OBJECTS="1", LC_ALL="C")
    command = ["git", "--literal-pathspecs", "-C", str(repo), "-c", "core.quotePath=true",
               "-c", "core.attributesFile=" + os.devnull, "-c", "core.hooksPath=" + os.devnull,
               "-c", "protocol.allow=never", "-c", "core.fsmonitor=false", *args]
    try:
        result = subprocess.run(command, capture_output=True, env=env, timeout=30, check=False)
    except subprocess.TimeoutExpired:
        raise ValueError("Git extraction timed out") from None
    require(result.returncode == 0, "Git extraction failed; provide the pinned commits in a local repository")
    return result.stdout


def blob(repo, revision, path):
    listing = git(repo, "ls-tree", "-z", revision, "--", path)
    if not listing:
        return None
    records = listing.rstrip(b"\0").split(b"\0")
    require(len(records) == 1, "expected a single source file")
    mode_type_oid, actual_path = records[0].split(b"\t", 1)
    mode, kind, blob_id = mode_type_oid.split()
    require(actual_path.decode("utf-8") == path and kind == b"blob" and mode in (b"100644", b"100755"),
            "symlinks, submodules and directories are not source text")
    require(int(git(repo, "cat-file", "-s", blob_id.decode())) <= MAX_BLOB_BYTES, "source file exceeds intake byte budget")
    raw = git(repo, "cat-file", "blob", blob_id.decode())
    require(b"\0" not in raw, "binary source files are unsupported")
    raw.decode("utf-8")
    return raw


def extract_input(repo, entry):
    parent, revision = entry["parent"], entry["revision"]
    header = git(repo, "cat-file", "-p", revision).split(b"\n\n", 1)[0]
    parents = [line[7:].decode() for line in header.split(b"\n") if line.startswith(b"parent ")]
    require(parents == [parent], "intake requires the exact parent of a single-parent commit")
    changed = git(repo, "diff", "--no-ext-diff", "--no-textconv", "--no-renames", "--name-only", "-z", parent, revision)
    changed = [path.decode("utf-8") for path in changed.split(b"\0") if path]
    require(set(entry["paths"]) <= set(changed), "selected paths must be changed files")
    for path in entry["paths"]:
        blob(repo, parent, path)
        blob(repo, revision, path)
    patch = git(repo, "diff", "--no-ext-diff", "--no-textconv", "--no-color", "--no-renames", "--no-relative",
                "--full-index", "--src-prefix=a/", "--dst-prefix=b/", "--diff-algorithm=myers", "--no-indent-heuristic",
                "--unified=3", "--inter-hunk-context=0", "--ignore-submodules=none", "-O", os.devnull,
                parent, revision, "--", *entry["paths"])
    require(len(patch) <= MAX_INPUT_BYTES, "diff exceeds intake byte budget; no silent truncation")
    context = []
    for item in entry["context"]:
        raw = blob(repo, item["revision"], item["path"])
        require(raw is not None, "context file does not exist at the pinned revision")
        # Preserve source text exactly; line boundaries are LF, not Unicode separators.
        lines = raw.decode("utf-8").split("\n")
        count = len(lines) - int(lines[-1] == "")
        require(item["end_line"] <= count, "context range extends beyond file")
        content = "\n".join(lines[item["start_line"] - 1:item["end_line"]])
        if item["end_line"] < len(lines):
            content += "\n"
        side = "before" if item["revision"] == parent else "after"
        context.append({"path": f"{side}:{item['path']}:{item['start_line']}-{item['end_line']}", "content": content})
    value = validate_input({"diff": patch.decode("utf-8"), "context": context})
    return value, sorted(set(changed) - set(entry["paths"]))


def reproduce(manifest, repositories, out):
    validate_manifest(manifest)
    require(isinstance(repositories, dict) and set(manifest["projects"]) <= set(repositories), "map every project to a local repository")
    require(all(text(repositories[name]) for name in manifest["projects"]), "repository paths must be strings")
    out.mkdir(parents=True, exist_ok=False)
    records, audit, licenses = [], [], {}
    for entry in manifest["entries"]:
        if entry["decision"] == "exclude":
            audit.append({"id": entry["id"], "decision": "exclude", "reason": entry["reason"]})
            continue
        project = manifest["projects"][entry["project"]]
        repo = Path(repositories[entry["project"]])
        # A repository mapping is location only, never authority for changing the inputs.
        require(git(repo, "rev-parse", project["snapshot"] + "^{commit}").decode().strip() == project["snapshot"], "missing source snapshot")
        git(repo, "merge-base", "--is-ancestor", entry["revision"], project["snapshot"])
        for license_file in project["licenses"]:
            for revision in (entry["parent"], entry["revision"]):
                raw = blob(repo, revision, license_file["path"])
                require(raw is not None and sha256(raw) == license_file["sha256"], "source license changed; review and pin its new contents")
                licenses[f"{entry['project']}/{license_file['path']}"] = raw
        value, omitted = extract_input(repo, entry)
        require(digest(value) == entry["expected_input_hash"], f"input hash mismatch: {entry['id']}")
        records.append({"candidate_version": VERSION, "id": entry["id"], "input_hash": digest(value), "input": value})
        audit.append({"id": entry["id"], "decision": "include", "omitted_paths": omitted})
    require(records, "batch has no included candidates")
    records.sort(key=lambda row: row["id"])
    (out / "candidates.jsonl").write_text("".join(dumps(row) + "\n" for row in records))
    for name, raw in licenses.items():
        destination = out / "licenses" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
    report = {"schema_version": VERSION, "manifest_hash": digest(manifest), "candidates_hash": digest(records),
              "included": len(records), "excluded": len(audit) - len(records),
              "by_project": dict(Counter(e["project"] for e in manifest["entries"] if e["decision"] == "include")),
              "git_version": git(Path(repositories[next(iter(manifest["projects"]))]), "--version").decode().strip(),
              "extractor_hash": sha256(Path(__file__).read_bytes()), "audit": audit}
    (out / "report.json").write_text(dumps(report) + "\n")
    return report


def verify_batch(manifest, directory):
    """Offline integrity checks; does not replace reproduction from Git objects."""
    validate_manifest(manifest)
    rows = read_jsonl(directory / "candidates.jsonl")
    expected = {e["id"]: e for e in manifest["entries"] if e["decision"] == "include"}
    seen = set()
    for row in rows:
        object_keys(row, ("candidate_version", "id", "input_hash", "input"), "candidate")
        require(row["candidate_version"] == VERSION and text(row["id"])
                and row["id"] in expected and row["id"] not in seen,
                "unexpected, duplicate or invalid candidate")
        seen.add(row["id"])
        validate_input(row["input"])
        require(digest(row["input"]) == row["input_hash"] == expected[row["id"]]["expected_input_hash"], "candidate input hash mismatch")
    require(seen == set(expected), "incomplete candidate batch")
    report = loads((directory / "report.json").read_text())
    object_keys(report, ("schema_version", "manifest_hash", "candidates_hash", "included", "excluded",
                        "by_project", "git_version", "extractor_hash", "audit"), "batch report")
    require(report["manifest_hash"] == digest(manifest) and report["candidates_hash"] == digest(rows), "batch report hash mismatch")
    require(report["schema_version"] == VERSION and hash_value(report["extractor_hash"])
            and text(report["git_version"]), "invalid extraction provenance")
    require(report["included"] == len(rows) and report["excluded"] == len(manifest["entries"]) - len(rows)
            and report["by_project"] == dict(Counter(e["project"] for e in expected.values())), "invalid batch counts")
    require(isinstance(report["audit"], list) and len(report["audit"]) == len(manifest["entries"]), "incomplete selection audit")
    for entry, audit in zip(manifest["entries"], report["audit"]):
        extra = "reason" if entry["decision"] == "exclude" else "omitted_paths"
        object_keys(audit, ("id", "decision", extra), "audit entry")
        require(audit["id"] == entry["id"] and audit["decision"] == entry["decision"], "audit selection mismatch")
        if extra == "reason":
            require(audit["reason"] == entry["reason"], "audit reason mismatch")
        else:
            require(isinstance(audit[extra], list) and all(isinstance(p, str) for p in audit[extra]), "invalid omitted paths")
            require(audit[extra] == sorted(set(audit[extra])) and not set(audit[extra]) & set(entry["paths"]), "invalid omitted paths")
    for project, info in manifest["projects"].items():
        for license_file in info["licenses"]:
            raw = (directory / "licenses" / project / license_file["path"]).read_bytes()
            require(sha256(raw) == license_file["sha256"], "redistributed license hash mismatch")
    return {"valid": True, "candidates": len(rows), "manifest_hash": digest(manifest)}
