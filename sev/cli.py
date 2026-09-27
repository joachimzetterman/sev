"""Minimal experiment interface. JSON on stdout; errors on stderr."""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from .backends import HTTP, MLX, Rules
from .classifier import NaiveBayes, fit
from .contracts import MAX_INPUT_BYTES, SCHEMA_VERSION, digest, dumps, loads, read_jsonl, validate_dataset, validate_input, validate_prediction
from .experiment import evaluate
from .metrics import agreement
from .taxonomy import VERSION, contract, select


def backend_args(parser):
    parser.add_argument("--backend", choices=("rules", "nb", "mlx", "chat", "kev"), required=True)
    parser.add_argument("--model", help="local MLX directory or HTTP model identifier")
    parser.add_argument("--revision", help="operator-supplied immutable HTTP model revision")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8000", help="base URL without /v1")
    parser.add_argument("--allow-remote", action="store_true", help="send this input to the specified HTTPS endpoint")
    parser.add_argument("--evals", help="comma-separated taxonomy IDs; defaults to all 14")


def build_backend(args):
    if args.backend == "rules":
        return Rules()
    if args.backend == "nb":
        if not args.model:
            raise ValueError("Naive Bayes requires --model with a fitted artifact")
        return NaiveBayes(args.model)
    if args.backend == "mlx":
        if not args.model:
            raise ValueError("MLX requires --model with a local snapshot directory")
        return MLX(args.model)
    return HTTP(args.endpoint, args.model, args.revision, args.allow_remote, kev=args.backend == "kev")


def read_diff(path):
    if path == "-":
        text = sys.stdin.read(MAX_INPUT_BYTES + 1)
    else:
        with Path(path).open() as stream:
            text = stream.read(MAX_INPUT_BYTES + 1)
    if len(text.encode()) > MAX_INPUT_BYTES:
        raise ValueError("diff exceeds byte budget; no silent truncation")
    return text


def parser():
    root = argparse.ArgumentParser(description="sev research harness; no trained security model is shipped")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("taxonomy", help="emit the versioned taxonomy and annotation examples")
    validate = commands.add_parser("validate", help="validate dataset and split isolation")
    validate.add_argument("data", nargs="+")
    train = commands.add_parser("fit-nb", help="fit the simple classifier on train data only")
    train.add_argument("data", nargs="+")
    train.add_argument("--out", type=Path, required=True)
    agree = commands.add_parser("agreement", help="compare two independent annotation files")
    agree.add_argument("left")
    agree.add_argument("right")
    for command in ("eval", "diff"):
        cmd = commands.add_parser(command)
        backend_args(cmd)
        if command == "eval":
            cmd.add_argument("input", nargs="?", default="-")
            cmd.add_argument("--context", help="JSON list of explicitly supplied path/content objects")
        else:
            cmd.add_argument("--staged", action="store_true", help="compare index to HEAD; default is unstaged")
    bench = commands.add_parser("bench", help="score a selected dataset partition; persist report and predictions")
    backend_args(bench)
    bench.add_argument("data", nargs="+")
    bench.add_argument("--split", choices=("smoke", "dev", "calibration", "test"), required=True)
    bench.add_argument("--repeats", type=int, default=1)
    bench.add_argument("--out", type=Path, required=True, help="new output directory; refuses overwrite")
    return root


def main(argv=None):
    args_list = list(sys.argv[1:] if argv is None else argv)
    # `git diff | sev --backend ...` is a shorthand for `sev eval - ...`.
    if not args_list or (args_list[0].startswith("--") and args_list[0] not in ("--help",)):
        args_list.insert(0, "eval")
    args = parser().parse_args(args_list)
    try:
        if args.command == "taxonomy":
            output = contract()
        elif args.command == "validate":
            rows = validate_dataset([row for path in args.data for row in read_jsonl(path)])
            output = {"valid": True, "records": len(rows), "dataset_hash": digest(rows)}
        elif args.command == "agreement":
            left, right = (validate_dataset(read_jsonl(path)) for path in (args.left, args.right))
            output = agreement(left, right)
        elif args.command == "fit-nb":
            if args.out.exists():
                raise ValueError("model output already exists")
            artifact = fit([row for path in args.data for row in read_jsonl(path)])
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(dumps(artifact) + "\n")
            output = {"model": str(args.out), "training_hash": artifact["training_hash"]}
        else:
            names = list(select(args.evals.split(",") if args.evals else None))
            if args.command == "bench":
                rows = validate_dataset([row for path in args.data for row in read_jsonl(path)])
                rows = [row for row in rows if row["split"] == args.split]
                if not rows:
                    raise ValueError("requested split is empty")
                if args.repeats < 1:
                    raise ValueError("repeats must be positive")
                if args.out.exists():
                    raise ValueError("output directory already exists; use a new run identifier")
            else:
                if args.command == "diff":
                    command = ["git", "--no-pager", "diff", "--no-ext-diff", "--no-textconv", "--no-color"]
                    if args.staged:
                        command.append("--cached")
                    # The diff is data. Do not execute textconv or external diff drivers.
                    proc = subprocess.run(command + ["--"], capture_output=True, text=True, check=False)
                    if proc.returncode:
                        raise ValueError("git diff failed; run inside the repository to evaluate")
                    value = {"diff": proc.stdout, "context": []}
                else:
                    context = loads(Path(args.context).read_text()) if args.context else []
                    value = {"diff": read_diff(args.input), "context": context}
                validate_input(value)
            started = time.perf_counter()
            backend = build_backend(args)
            load_ms = (time.perf_counter() - started) * 1000
            if args.command == "bench":
                output, predictions = evaluate(rows, backend, names, repeats=args.repeats, load_ms=load_ms)
                args.out.mkdir(parents=True, exist_ok=False)
                (args.out / "report.json").write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
                (args.out / "predictions.jsonl").write_text("".join(dumps(row) + "\n" for row in predictions))
                print(dumps({"report": str(args.out / "report.json"), "records": len(rows), "errors": len(output["errors"])}))
                return 1 if output["errors"] else 0
            prediction, stats = backend.predict(value, names)
            output = {"schema_version": SCHEMA_VERSION, "taxonomy_version": VERSION, "input_hash": digest(value),
                      "model": backend.metadata, "judgments": validate_prediction(prediction, names), "usage": stats}
        print(json.dumps(output, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, ImportError) as exc:
        print(f"sev: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
