"""Timing-only padded controls. These are not independent quality examples."""

import argparse
import json
import platform
import sys
import time
from pathlib import Path

from sev.cli import backend_args, build_backend
from sev.contracts import digest, validate_input
from sev.taxonomy import select


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    backend_args(parser)
    parser.add_argument("--bytes", type=int, nargs="+", default=[512, 2048, 8192])
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists() or args.repeats < 1 or any(size < 128 or size > 65_536 for size in args.bytes):
        parser.error("choose a new output file, positive repeats and sizes from 128 to 65536")
    names = list(select(args.evals.split(",") if args.evals else None))
    start = time.perf_counter()
    backend = build_backend(args)
    load_ms = (time.perf_counter() - start) * 1000
    timings = []
    for size in args.bytes:
        count = max(1, (size - 100) // 25)
        diff = ('--- a/ui.py\n+++ b/ui.py\n@@ -1 +1,' + str(count + 1) + ' @@\n'
                '-BUTTON_COLOUR = "blue"\n+BUTTON_COLOUR = "green"\n'
                + '+# timing-only filler xx\n' * count)
        value = validate_input({"diff": diff, "context": []})
        for repeat in range(args.repeats):
            start = time.perf_counter()
            _, stats = backend.predict(value, names)
            timings.append({"target_bytes": size, "actual_diff_bytes": len(diff.encode()),
                            "input_hash": digest(value), "repeat": repeat,
                            "latency_ms": (time.perf_counter() - start) * 1000, **stats})
            print(f"Completed size={size}, repeat={repeat}", file=sys.stderr, flush=True)
    result = {"timing_only": True, "model": backend.metadata, "load_ms": load_ms,
              "environment": platform.platform(), "question_count": len(names), "timing": timings,
              "limitations": ["Synthetic padding, not representative real-diff quality or token distribution.",
                              "First request per size includes possible shape/kernel warmup.",
                              "There is no prefix cache in the ordinary MLX baseline."]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
