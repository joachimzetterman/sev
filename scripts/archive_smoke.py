"""Archive the executed local smoke runs and render their descriptive results."""

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    destination = ROOT / "results/2026-09-27"
    destination.mkdir(parents=True, exist_ok=False)
    for source, name in (("rules-audited", "rules"), ("qwen06b-audited", "qwen06b")):
        shutil.copytree(ROOT / "artifacts" / source, destination / name)
    shutil.copyfile(ROOT / "artifacts/qwen06b-sizes.json", destination / "qwen06b-sizes.json")
    rules = json.loads((destination / "rules/report.json").read_text())
    small = json.loads((destination / "qwen06b/report.json").read_text())
    sizes = json.loads((destination / "qwen06b-sizes.json").read_text())
    support = sum(value["n"] for value in small["per_eval"].values())
    correct = lambda report: sum(sum(m["confusion"][s][s] for s in m["confusion"]) for m in report["per_eval"].values())
    ic = sum(m["classes"]["INSUFFICIENT_CONTEXT"]["support"] for m in small["per_eval"].values())
    ic_correct = sum(m["confusion"]["INSUFFICIENT_CONTEXT"]["INSUFFICIENT_CONTEXT"] for m in small["per_eval"].values())
    performance = small["performance"]
    lines = ["# Initial local experiment — 2026-09-27", "",
             "**The tested ordinary 0.6B baseline is not useful enough in its current configuration. "
             "This experiment does not establish whether a specialised sev model would be useful.**", "",
             f"On 20 authored diffs with {support} provisional judgments, Qwen3-0.6B got {correct(small)}/{support} "
             f"judgments correct and {ic_correct}/{ic} insufficient-context judgments correct. "
             "All 14 evals were requested for each diff, but only explicitly annotated labels were scored. "
             "A single assistant authored the cases and labels; no independent raters, held-out projects or real-change population were used.", "",
             "These are diagnostics for the baseline and harness, not a model benchmark or evidence of security. "
             "No specialised model was trained. The strong general-model and Kev comparisons remain unmeasured. "
             "No Modal or H100 job was started.", "",
             "A label audit corrected one provisional boundary annotation before the archived rerun: "
             "removing an explicit route gate changes the enforcement point (YES), while effective privilege "
             "still needs the missing middleware policy (INSUFFICIENT_CONTEXT). The question prompts were unchanged.", "",
             "## Executed configuration", "",
             "- Hardware: Apple M4 Pro, 24 GiB unified memory. Local Metal execution.",
             "- Ordinary model: `mlx-community/Qwen3-0.6B-4bit`, snapshot `73e3e38d981303bc594367cd910ea6eb48349da8`.",
             "- Runtime: `uv.lock`, MLX LM 0.31.3; four next-token letters, thinking disabled, separate full prefill for every question.",
             "- Dataset: `data/smoke.jsonl`; all provisional annotations, development-only.",
             "- Small model: two complete timing passes; only pass zero scored. Rules: three timing passes.",
             "- No context retrieval, prompt tuning after results, fine-tuning, cache reuse, or generated security review.", "",
             "Exact per-eval confusion matrices, calibration bins, timing samples, source hashes, "
             "model-file hashes and environment metadata are in the "
             "[small-model report](../results/2026-09-27/qwen06b/report.json) and "
             "[rules report](../results/2026-09-27/rules/report.json). "
             "Both runs completed with zero backend failures. "
             "[Small-model predictions](../results/2026-09-27/qwen06b/predictions.jsonl) allow re-scoring.", "",
             "## Descriptive quality", "",
             "| Eval | Annotated judgments | Rules correct, including abstentions as wrong | Small model correct |",
             "|---|---:|---:|---:|"]
    for name, metrics in small["per_eval"].items():
        n = metrics["n"]
        a = sum(rules["per_eval"][name]["confusion"][s][s] for s in metrics["confusion"])
        b = sum(metrics["confusion"][s][s] for s in metrics["confusion"])
        lines.append(f"| {name} | {n} | {a} | {b} |")
    lines.extend(["", f"The lexical rules got {correct(rules)}/{support} correct and frequently abstained. "
                  "This is not a comparison against Semgrep/CodeQL. Some evals have no negative or no positive support; "
                  "per-eval precision/recall/F1 and FPR/FNR are in the reports with null for undefined values. "
                  "The tiny denominators cannot support deployment thresholds or reliable confidence intervals.", "",
                  "## Timing and memory", "",
                  "| Local 0.6B measurement | Value |", "|---|---:|",
                  f"| Model import/load plus model-file hashing | {performance['model_load_ms']/1000:.2f} s |",
                  f"| First full 14-eval request | {performance['first_eval_ms']/1000:.2f} s |",
                  f"| Load plus first request | {performance['load_plus_first_eval_ms']/1000:.2f} s |",
                  f"| Warm p50, 39 subsequent requests | {performance['warm_p50_ms']/1000:.2f} s |",
                  f"| Warm p95 | {performance['warm_p95_ms']/1000:.2f} s |",
                  f"| Process peak RSS | {performance['client_peak_rss_bytes']/2**20:.1f} MiB |",
                  f"| Peak MLX allocated device memory | {max(t['peak_device_memory_bytes'] for t in small['timing'])/2**30:.2f} GiB |", "",
                  "RSS and device allocation are separate high-water marks on unified memory; do not sum them. "
                  "Load plus first excludes interpreter startup/downloads and is not a cold-machine result. "
                  "The initial earlier run had a warm median of 2.67 s; the archived final run above is the "
                  "source-fingerprinted repeat and illustrates ordinary run-to-run latency variation. "
                  "No absolute inference cost or CPU-only performance has been established.", "",
                  "The 500 ms aspiration is not met by this configuration. Repeating full context 14 times "
                  "is a measurable inefficiency; it does not quantify the gain from a pointer architecture. "
                  "Shared-prefix ordinary-LM scoring and matched-backbone comparisons must precede that conclusion.", "",
                  "## Diff-size timing controls", "",
                  "These are generated comment-padding controls, not real large diffs or quality examples. "
                  "Both repetitions and actual token usage are in the "
                  "[size sweep](../results/2026-09-27/qwen06b-sizes.json).", "",
                  "| Actual diff bytes | Total prompt tokens over 14 prefills | First request | Second request |",
                  "|---:|---:|---:|---:|"])
    for i in range(0, len(sizes["timing"]), 2):
        a, b = sizes["timing"][i:i+2]
        lines.append(f"| {a['actual_diff_bytes']} | {a['input_tokens']} | {a['latency_ms']/1000:.2f} s | {b['latency_ms']/1000:.2f} s |")
    lines.extend(["", "## What would change the conclusion", "",
                  "1. Independent agreement on the label definitions, with ordinary changes and difficult negatives.",
                  "2. A measured strong general-model baseline on the same inputs, plus simple classifier and real deterministic-tool comparisons.",
                  "3. Ordinary 1–4B models and shared-context scoring before specialised training.",
                  "4. Kev transfer, then a controlled training experiment only after enough group-disjoint labels exist.",
                  "5. Separate calibration data, family-clustered uncertainty estimates, real size strata, CPU and modest-GPU measurements.", "",
                  "The current evidence supports continuing the experiment design and data work. It does not support "
                  "shipping a security model, automated approvals, or a claim that sev already meets its thesis.", ""])
    (ROOT / "docs/results.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
