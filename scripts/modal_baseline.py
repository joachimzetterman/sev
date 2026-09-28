"""One bounded, ephemeral general-model experiment. Never deploys an endpoint.

MODAL_PROFILE=chosen-profile uv run --with modal==1.5.5 python -m scripts.modal_baseline \
    --data data/smoke.jsonl --out artifacts/general-modal
"""

import argparse
import os
import time
from pathlib import Path

import modal

from sev.backends import messages
from sev.contracts import digest, dumps, loads, read_jsonl, validate_dataset, validate_prediction
from sev.experiment import build_report, write_results
from sev.taxonomy import EVALS

MODEL = "Qwen/Qwen3.5-27B"
REVISION = "fc05daec18b0a78c049392ed2e771dde82bdf654"
VLLM = "0.24.0"
app = modal.App("sev-general-model-experiment")
image = (modal.Image.debian_slim(python_version="3.12")
         .pip_install(f"vllm=={VLLM}")
         .add_local_python_source("sev"))


@app.function(image=image, gpu="H100", cpu=4, memory=32768, timeout=1200,
              max_containers=1, retries=0, scaledown_window=2)
def infer(prompts, names):
    """Only rendered inputs/questions cross this boundary, never gold labels."""
    import importlib.metadata
    import resource
    import torch
    from vllm import LLM, SamplingParams

    started = time.perf_counter()
    llm = LLM(model=MODEL, revision=REVISION, dtype="bfloat16", max_model_len=8192,
              gpu_memory_utilization=.9, enforce_eager=True, enable_prefix_caching=False,
              limit_mm_per_prompt={"image": 0, "video": 0}, trust_remote_code=False, seed=0)
    tokenizer = llm.get_tokenizer()
    load_ms = (time.perf_counter() - started) * 1000
    samples = []
    params = SamplingParams(temperature=0, max_tokens=4096)
    for prompt in prompts:
        started = time.perf_counter()
        text = tokenizer.apply_chat_template(prompt, tokenize=False, add_generation_prompt=True, enable_thinking=False)
        if len(tokenizer.encode(text)) + 4096 > 8192:
            raise ValueError("general-model context budget exceeded; no truncation")
        generated = llm.generate([text], params, use_tqdm=False)[0]
        output = generated.outputs[0]
        error = None
        try:
            if output.finish_reason != "stop":
                raise ValueError("incomplete answer")
            judgments = validate_prediction(loads(output.text), names)
        except (ValueError, TypeError):
            judgments = {name: {"probabilities": None} for name in names}
            error = "invalid_structured_response"
        samples.append({"judgments": judgments, "error_type": error,
                        "latency_ms": (time.perf_counter() - started) * 1000,
                        "input_tokens": len(generated.prompt_token_ids), "output_tokens": len(output.token_ids)})
    return {"samples": samples, "model_load_ms": load_ms,
            "server_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
            "gpu_name": torch.cuda.get_device_name(0),
            "allocated_gpu_memory_bytes": torch.cuda.max_memory_allocated(),
            "runtime_versions": {name: importlib.metadata.version(name) for name in ("vllm", "torch", "transformers")}}


def report_remote(rows, names, result, wall_ms):
    """Adapt recorded server samples to the common report contract; no RPC here."""
    samples = result["samples"]
    if len(samples) != len(rows):
        raise ValueError("incomplete cloud experiment")
    predictions = [{"id": row["id"], "input_hash": digest(row["input"]),
                    "judgments": sample["judgments"], "error_type": sample["error_type"]}
                   for row, sample in zip(rows, samples)]
    timing = [{"id": row["id"], "repeat": 0, "success": sample["error_type"] is None,
               **{key: sample[key] for key in ("latency_ms", "error_type", "input_tokens", "output_tokens")}}
              for row, sample in zip(rows, samples)]
    metadata = {"model": MODEL, "revision": REVISION, "backend": "modal-vllm", "dtype": "bfloat16",
                "temperature": 0, "thinking": False, "prefix_cache": False, "vllm": VLLM,
                "probability_kind": "self_reported", "calibrated": False}
    report = build_report(rows, metadata, names, predictions, timing, load_ms=result["model_load_ms"],
                          timing_scope="server_tokenization_and_generation",
                          load_scope="server_model_download_and_initialization",
                          source_paths={"scripts/modal_baseline.py": Path(__file__).resolve()})
    report["performance"].update({key: result[key] for key in (
        "server_peak_rss_bytes", "gpu_name", "allocated_gpu_memory_bytes", "runtime_versions")})
    report["performance"]["client_wall_including_image_startup_ms"] = wall_ms
    report["limitations"].extend([
        "Server latency excludes RPC; local baseline used a different runtime and machine.",
        "20-minute per-job timeout bounds GPU work, not image-build cost or exact invoice.",
        "Actual billed cost must be obtained from the selected Modal workspace."])
    return report, predictions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not os.environ.get("MODAL_PROFILE"):
        parser.error("set MODAL_PROFILE explicitly to choose the billing account")
    rows = validate_dataset(read_jsonl(args.data))
    if len(rows) > 20 or any(r["split"] != "smoke" or r["source"]["kind"] != "authored" for r in rows):
        parser.error("this first cloud experiment accepts at most 20 authored smoke examples")
    try:
        args.out.mkdir(parents=True, exist_ok=False)
    except OSError:
        parser.error("cannot reserve output directory; choose a new writable path")
    names = list(EVALS)
    started = time.perf_counter()
    with modal.enable_output(), app.run():
        result = infer.remote([messages(row["input"], names) for row in rows], names)
    report, predictions = report_remote(rows, names, result, (time.perf_counter() - started) * 1000)
    write_results(args.out, report, predictions)
    print(dumps({"report": str(args.out / "report.json"), "errors": len(report["errors"])}))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
