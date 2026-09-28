"""Reproducible evaluation and timing; never tune on the test partition."""

import json
import platform
import resource
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .backends import prompt_fingerprint
from .contracts import SCHEMA_VERSION, digest, dumps, validate_prediction
from .metrics import percentile, summarize
from .taxonomy import VERSION


def evaluate(dataset, backend, names, repeats=1, load_ms=None):
    if repeats < 1:
        raise ValueError("repeats must be positive")
    if hasattr(backend, "check_evaluation"):
        backend.check_evaluation(dataset)
    predictions, timing = [], []
    for repeat in range(repeats):
        for row in dataset:
            started = time.perf_counter()
            stats, error = {}, None
            try:
                prediction, stats = backend.predict(row["input"], names)
                validate_prediction(prediction, names)
            except (ValueError, RuntimeError, OSError) as exc:
                # Do not repeat untrusted provider messages or submitted code in artifacts.
                prediction = {name: {"probabilities": None} for name in names}
                error = type(exc).__name__
            elapsed = (time.perf_counter() - started) * 1000
            timing.append({**stats, "id": row["id"], "repeat": repeat, "latency_ms": elapsed,
                           "success": error is None, "error_type": error})
            if repeat == 0:
                predictions.append({"id": row["id"], "input_hash": digest(row["input"]),
                                    "judgments": prediction, "error_type": error})
    return build_report(dataset, backend.metadata, names, predictions, timing,
                        repeats=repeats, load_ms=load_ms), predictions


def build_report(dataset, metadata, names, predictions, timing, *, repeats=1, load_ms=None,
                 timing_scope="client_request", load_scope="client_backend_initialization", source_paths=None):
    """Shared scoring/report contract for live backends and recorded remote samples."""
    if not dataset or len(predictions) != len(dataset) or len(timing) != len(dataset) * repeats:
        raise ValueError("incomplete experiment samples")
    samples, buckets, sizes = {name: [] for name in names}, {}, {}
    for row, prediction in zip(dataset, predictions):
        if prediction["id"] != row["id"] or prediction["input_hash"] != digest(row["input"]):
            raise ValueError("prediction does not match dataset input")
        validate_prediction(prediction["judgments"], names)
        for name in names:
            if name in row["judgments"]:
                samples[name].append((row["judgments"][name]["state"], prediction["judgments"][name]["probabilities"]))
        size = len(row["input"]["diff"].encode())
        buckets[row["id"]] = "<1KiB" if size < 1024 else "1-4KiB" if size < 4096 else "4-16KiB" if size < 16384 else ">=16KiB"
    for sample in timing:
        sizes.setdefault(buckets[sample["id"]], []).append(sample["latency_ms"])
    errors = [{key: sample[key] for key in ("id", "repeat", "error_type")}
              for sample in timing if sample["error_type"] is not None]
    root = Path(__file__).resolve().parents[1]
    paths = sorted((root / "sev").glob("*.py"))
    if (root / "uv.lock").exists():
        paths.append(root / "uv.lock")
    source_hashes = {str(path.relative_to(root)): digest(path.read_text()) for path in paths}
    source_hashes.update({name: digest(path.read_text()) for name, path in (source_paths or {}).items()})
    calibration = metadata["probability_kind"] != "rule_indicator"
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss_bytes = rss if sys.platform == "darwin" else rss * 1024
    warm = [row["latency_ms"] for row in timing[1:]]
    costs = [row.get("cost_usd") for row in timing]
    first_ms = timing[0]["latency_ms"]
    report = {
        "schema_version": SCHEMA_VERSION, "taxonomy_version": VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_hash": digest(dataset), "records": len(dataset), "repeats": repeats,
        "splits": dict(Counter(row["split"] for row in dataset)),
        "annotation_status": dict(Counter(row["annotation"]["status"] for row in dataset)),
        "model": metadata, "prompt_hash": prompt_fingerprint(names),
        "source_hashes": source_hashes,
        "environment": {"python": platform.python_version(), "platform": platform.platform(), "machine": platform.machine()},
        "per_eval": {name: summarize(rows, calibration=calibration) for name, rows in samples.items()},
        "errors": errors,
        "performance": {"model_load_ms": load_ms, "first_eval_ms": first_ms,
                        "timing_scope": timing_scope, "model_load_scope": load_scope,
                        "load_plus_first_eval_ms": load_ms + first_ms if load_ms is not None and first_ms is not None else None,
                        "warm_p50_ms": percentile(warm, .5), "warm_p95_ms": percentile(warm, .95),
                        "client_peak_rss_bytes": rss_bytes,
                        "by_diff_bytes": {key: {"n": len(values), "p50_ms": percentile(values, .5), "p95_ms": percentile(values, .95)} for key, values in sizes.items()},
                        "inference_cost_usd": sum(costs) if all(v is not None for v in costs) else None,
                        "server_memory_bytes": None, "server_cold_start_ms": None},
        "timing": timing,
        "limitations": ["Only repeat zero is scored; repeats are timing samples.",
                        "Warm includes every request after the first, including failures; inspect errors.",
                        "Load plus first excludes interpreter startup and work outside the recorded load/request scopes.",
                        "Peak RSS is this client's process lifetime high-water mark, not remote/GPU memory.",
                        "No model is calibrated for sev; calibration metrics assess raw scores.",
                        "Authored/provisional smoke data cannot establish utility or generalisation."],
    }
    return report


def write_results(directory, report, predictions):
    """Write results into a directory reserved before model loading/inference."""
    (directory / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    (directory / "predictions.jsonl").write_text("".join(dumps(row) + "\n" for row in predictions))
