"""Developer preview and research commands; errors go to stderr."""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from . import __version__
from .api import render_text, security_eval
from .classifier import fit
from .contracts import MAX_INPUT_BYTES, digest, dumps, loads, read_jsonl, validate_dataset, validate_input
from .experiment import evaluate, write_results
from .metrics import agreement
from .settings import BACKENDS, DEFAULTS, create_backend, resolve_settings, save_settings
from .taxonomy import contract, select


def backend_args(parser, required=False):
    parser.add_argument("--backend", choices=BACKENDS, required=required)
    parser.add_argument("--model", help="local MLX directory or HTTP model identifier")
    parser.add_argument("--revision", help="operator-supplied immutable HTTP model revision")
    parser.add_argument("--endpoint", help="base URL without /v1; defaults to local port 8000")
    parser.add_argument("--allow-remote", action="store_true", default=None, help="allow sending diffs to the specified HTTPS endpoint")
    parser.add_argument("--evals", help="comma-separated taxonomy IDs; defaults to all 14")


def build_backend(args):
    settings = resolve_settings({key: getattr(args, key) for key in DEFAULTS}, getattr(args, "config", None))
    return create_backend(settings)


def read_diff(path):
    if path == "-":
        text = sys.stdin.read(MAX_INPUT_BYTES + 1)
    else:
        with Path(path).open() as stream:
            text = stream.read(MAX_INPUT_BYTES + 1)
    if len(text.encode()) > MAX_INPUT_BYTES:
        raise ValueError("diff exceeds byte budget; no silent truncation")
    return text


def git_diff(staged=False, base=None):
    command = ["git", "-c", "core.fsmonitor=false", "--no-pager", "diff", "--no-ext-diff", "--no-textconv", "--no-color"]
    if staged:
        command.append("--cached")
    if base is not None:
        revisions = []
        for ref in (base, "HEAD"):
            result = subprocess.run(["git", "rev-parse", "--verify", "--end-of-options", ref + "^{commit}"],
                                    capture_output=True, text=True, check=False, timeout=10)
            if result.returncode:
                raise ValueError("base and HEAD must resolve to local commits; fetch the base branch first")
            revisions.append(result.stdout.strip())
        common = subprocess.run(["git", "merge-base", *revisions], capture_output=True, text=True, check=False, timeout=10)
        if common.returncode:
            raise ValueError("base and HEAD have no available common ancestor")
        command.extend([common.stdout.strip(), revisions[1]])
    result = subprocess.run(command + ["--"], capture_output=True, text=True, check=False, timeout=30)
    if result.returncode:
        raise ValueError("git diff failed; run inside the repository to evaluate")
    return result.stdout


def parser():
    root = argparse.ArgumentParser(description="sev developer preview: security judgments over diffs using your configured model")
    root.add_argument("--version", action="version", version=f"sev {__version__} (developer preview)")
    commands = root.add_subparsers(dest="command", required=True)
    configure = commands.add_parser("configure", help="save inference settings once; no model is downloaded or contacted")
    backend_args(configure, required=True)
    configure.add_argument("--config", type=Path, help="settings file; default is the user's sev configuration")
    configure.add_argument("--force", action="store_true", help="replace existing settings")
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
        cmd.add_argument("--config", type=Path, help="explicit settings file; repository files are never loaded automatically")
        formatting = cmd.add_mutually_exclusive_group()
        formatting.add_argument("--json", dest="format", action="store_const", const="json", help="machine-readable output")
        formatting.add_argument("--text", dest="format", action="store_const", const="text", help="readable judgments without confidence percentages")
        cmd.add_argument("--context", help="JSON file containing a list of supplied path/content objects")
        if command == "eval":
            cmd.add_argument("input", nargs="?", default="-")
        else:
            source = cmd.add_mutually_exclusive_group()
            source.add_argument("--staged", action="store_true", help="compare index to HEAD; default is unstaged")
            source.add_argument("--base", help="compare the merge base with this revision to HEAD (committed changes only)")
    bench = commands.add_parser("bench", help="score a selected dataset partition; persist report and predictions")
    backend_args(bench, required=True)
    bench.add_argument("data", nargs="+")
    bench.add_argument("--split", choices=("smoke", "dev", "calibration", "test"), required=True)
    bench.add_argument("--repeats", type=int, default=1)
    bench.add_argument("--out", type=Path, required=True, help="new output directory; refuses overwrite")
    return root


def main(argv=None):
    args_list = list(sys.argv[1:] if argv is None else argv)
    # `git diff | sev --backend ...` is a shorthand for `sev eval - ...`.
    if not args_list or args_list[0] == "-" or (args_list[0].startswith("--") and args_list[0] not in ("--help", "--version")):
        args_list.insert(0, "eval")
    args = parser().parse_args(args_list)
    try:
        if args.command == "taxonomy":
            output = contract()
        elif args.command == "configure":
            if args.evals:
                raise ValueError("select evals when evaluating a diff; saved configuration always defaults to all evals")
            settings = resolve_settings({key: getattr(args, key) for key in DEFAULTS})
            path = save_settings(settings, args.config, args.force)
            output = {"config": str(path), "backend": settings["backend"], "model": settings["model"],
                      "remote_inference_authorized": settings["allow_remote"]}
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
                args.out.mkdir(parents=True, exist_ok=False)
            else:
                context = loads(Path(args.context).read_text()) if args.context else []
                if args.command == "diff":
                    value = {"diff": git_diff(args.staged, args.base), "context": context}
                else:
                    value = {"diff": read_diff(args.input), "context": context}
                validate_input(value)
            started = time.perf_counter()
            backend = build_backend(args)
            load_ms = (time.perf_counter() - started) * 1000
            if args.command == "bench":
                output, predictions = evaluate(rows, backend, names, repeats=args.repeats, load_ms=load_ms)
                write_results(args.out, output, predictions)
                print(dumps({"report": str(args.out / "report.json"), "records": len(rows), "errors": len(output["errors"])}))
                return 1 if output["errors"] else 0
            output = security_eval(value["diff"], names, context=value["context"], backend=backend)
            if args.format == "text" or (args.format is None and sys.stdout.isatty()):
                print(render_text(output))
                return 0
        print(json.dumps(output, indent=2, allow_nan=False))
        return 0
    except subprocess.TimeoutExpired:
        print("sev: git operation timed out", file=sys.stderr)
        return 2
    except (ValueError, OSError, ImportError) as exc:
        print(f"sev: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
