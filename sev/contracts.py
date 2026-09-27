"""Small, strict contracts. Missing annotations are never negative examples."""

import hashlib
import json
import math
import re
from pathlib import Path

from .taxonomy import EVALS, STATES, VERSION

SCHEMA_VERSION = "sev-0.1"
MAX_INPUT_BYTES = 262_144


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def digest(value):
    return hashlib.sha256(dumps(value).encode()).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def loads(text):
    return json.loads(text, object_pairs_hook=_unique_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"invalid JSON number: {value}")))


def read_jsonl(path):
    rows = []
    for index, line in enumerate(Path(path).read_text().splitlines(), 1):
        if line.strip():
            try:
                row = loads(line)
                if not isinstance(row, dict):
                    raise ValueError("record must be an object")
                rows.append(row)
            except ValueError as exc:
                raise ValueError(f"{path}:{index}: {exc}") from exc
    if not rows:
        raise ValueError(f"empty JSONL file: {path}")
    return rows


def validate_input(value):
    if not isinstance(value, dict) or set(value) != {"diff", "context"}:
        raise ValueError("input requires exactly diff and context")
    if not isinstance(value["diff"], str) or not value["diff"].strip():
        raise ValueError("diff must be a nonempty string")
    if not isinstance(value["context"], list):
        raise ValueError("context must be a list")
    for item in value["context"]:
        if not isinstance(item, dict) or set(item) != {"path", "content"} or not all(isinstance(v, str) and v for v in item.values()):
            raise ValueError("each context item requires nonempty path and content strings")
    if len(dumps(value).encode()) > MAX_INPUT_BYTES:
        raise ValueError(f"input exceeds {MAX_INPUT_BYTES} bytes; no silent truncation")
    return value


def validate_prediction(value, names):
    if not isinstance(value, dict) or set(value) != set(names):
        raise ValueError("prediction must contain exactly the requested evals")
    for name, judgment in value.items():
        if not isinstance(judgment, dict) or set(judgment) != {"probabilities"}:
            raise ValueError(f"{name}: requires only probabilities")
        ps = judgment["probabilities"]
        if ps is None:  # Explicit algorithmic abstention, not a semantic UNKNOWN label.
            continue
        if not isinstance(ps, dict) or set(ps) != set(STATES):
            raise ValueError(f"{name}: requires all four states")
        if any(type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1 for p in ps.values()):
            raise ValueError(f"{name}: probabilities must be finite numbers in [0, 1]")
        if abs(sum(ps.values()) - 1) > 1e-5:
            raise ValueError(f"{name}: probabilities must sum to one")
    return value


def decision(probabilities):
    # A tie is never silently resolved to a negative judgment.
    order = ("INSUFFICIENT_CONTEXT", "UNKNOWN", "YES", "NO")
    return max(order, key=probabilities.__getitem__)


def one_hot(state):
    return {"probabilities": {key: float(key == state) for key in STATES}}


def validate_dataset(rows):
    ids, groups, projects, commits, diffs = set(), {}, {}, {}, {}
    for row in rows:
        required = {"schema_version", "taxonomy_version", "id", "split", "group_id", "source", "input", "judgments", "annotation"}
        if set(row) != required:
            raise ValueError("dataset record has missing or unexpected fields")
        if row["schema_version"] != SCHEMA_VERSION or row["taxonomy_version"] != VERSION:
            raise ValueError("unsupported schema/taxonomy version")
        if not isinstance(row["id"], str) or not row["id"] or row["id"] in ids:
            raise ValueError("duplicate or invalid record id")
        ids.add(row["id"])
        split = row["split"]
        if split not in ("smoke", "train", "dev", "calibration", "test"):
            raise ValueError("invalid dataset split")
        if not isinstance(row["group_id"], str) or not row["group_id"]:
            raise ValueError("group_id is required")
        source = row["source"]
        if not isinstance(source, dict) or set(source) != {"kind", "project", "revision", "license", "url"}:
            raise ValueError("source requires kind, project, revision, license and url")
        if source["kind"] not in ("authored", "repository", "dataset") or not all(isinstance(v, str) for v in source.values()):
            raise ValueError("invalid source metadata")
        if not source["project"] or not source["license"]:
            raise ValueError("project and source license/provenance status must be explicit")
        validate_input(row["input"])
        # Hunk positions are irrelevant to exact-content contamination checks.
        normalized = re.sub(r"(?m)^@@.*@@.*$", "@@", row["input"]["diff"])
        for table, key in ((groups, row["group_id"]), (projects, source["project"]),
                           (diffs, digest(normalized))):
            if key in table and table[key] != split:
                raise ValueError(f"cross-split contamination: {key}")
            table[key] = split
        if source["revision"]:
            key = (source["project"], source["revision"])
            if key in commits and commits[key] != split:
                raise ValueError("commit crosses splits")
            commits[key] = split
        judgments = row["judgments"]
        if not isinstance(judgments, dict) or not judgments or not set(judgments) <= set(EVALS):
            raise ValueError("judgments must be a nonempty subset of taxonomy evals")
        for name, label in judgments.items():
            if not isinstance(label, dict) or set(label) != {"state", "rationale", "evidence", "missing_context"}:
                raise ValueError(f"{name}: invalid annotation fields")
            if label["state"] not in STATES or not isinstance(label["rationale"], str) or not label["rationale"]:
                raise ValueError(f"{name}: requires state and rationale")
            for field in ("evidence", "missing_context"):
                if not isinstance(label[field], list) or not all(isinstance(v, str) and v for v in label[field]):
                    raise ValueError(f"{name}: {field} must contain strings")
            if label["state"] == "INSUFFICIENT_CONTEXT" and not label["missing_context"]:
                raise ValueError(f"{name}: name the missing fact")
            if label["state"] in ("YES", "NO") and not label["evidence"]:
                raise ValueError(f"{name}: evidence is required")
        annotation = row["annotation"]
        if not isinstance(annotation, dict) or set(annotation) != {"status", "raters"}:
            raise ValueError("annotation requires status and raters")
        if annotation["status"] not in ("provisional", "adjudicated") or not isinstance(annotation["raters"], list):
            raise ValueError("invalid annotation metadata")
        if not annotation["raters"] or not all(isinstance(r, str) and r for r in annotation["raters"]):
            raise ValueError("rater identifiers are required")
        if split == "test" and (annotation["status"] != "adjudicated" or len(set(annotation["raters"])) < 2):
            raise ValueError("test requires adjudication and at least two distinct raters")
    if not rows:
        raise ValueError("dataset is empty")
    return rows
