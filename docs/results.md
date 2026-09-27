# Initial local experiment — 2026-09-27

**The tested ordinary 0.6B baseline is not useful enough in its current configuration. This experiment does not establish whether a specialised sev model would be useful.**

On 20 authored diffs with 59 provisional judgments, Qwen3-0.6B got 23/59 judgments correct and 0/6 insufficient-context judgments correct. All 14 evals were requested for each diff, but only explicitly annotated labels were scored. A single assistant authored the cases and labels; no independent raters, held-out projects or real-change population were used.

These are diagnostics for the baseline and harness, not a model benchmark or evidence of security. No specialised model was trained. The strong general-model and Kev comparisons remain unmeasured. No Modal or H100 job was started.

A label audit corrected one provisional boundary annotation before the archived rerun: removing an explicit route gate changes the enforcement point (YES), while effective privilege still needs the missing middleware policy (INSUFFICIENT_CONTEXT). The question prompts were unchanged.

## Executed configuration

- Hardware: Apple M4 Pro, 24 GiB unified memory. Local Metal execution.
- Ordinary model: `mlx-community/Qwen3-0.6B-4bit`, snapshot `73e3e38d981303bc594367cd910ea6eb48349da8`.
- Runtime: `uv.lock`, MLX LM 0.31.3; four next-token letters, thinking disabled, separate full prefill for every question.
- Dataset: `data/smoke.jsonl`; all provisional annotations, development-only.
- Small model: two complete timing passes; only pass zero scored. Rules: three timing passes.
- No context retrieval, prompt tuning after results, fine-tuning, cache reuse, or generated security review.

Exact per-eval confusion matrices, calibration bins, timing samples, source hashes, model-file hashes and environment metadata are in the [small-model report](../results/2026-09-27/qwen06b/report.json) and [rules report](../results/2026-09-27/rules/report.json). Both runs completed with zero backend failures. [Small-model predictions](../results/2026-09-27/qwen06b/predictions.jsonl) allow re-scoring.

## Descriptive quality

| Eval | Annotated judgments | Rules correct, including abstentions as wrong | Small model correct |
|---|---:|---:|---:|
| AUTHENTICATION_CHANGE | 4 | 1 | 3 |
| AUTHORIZATION_RELEVANT | 10 | 2 | 2 |
| AUTHORIZATION_BOUNDARY_CHANGE | 3 | 0 | 1 |
| PRIVILEGE_INCREASE | 10 | 0 | 2 |
| TENANT_BOUNDARY_CHANGE | 4 | 3 | 2 |
| SENSITIVE_DATA_HANDLING | 5 | 1 | 2 |
| DATA_EXPOSURE_CHANGE | 4 | 0 | 0 |
| UNTRUSTED_INPUT_HANDLING_CHANGE | 2 | 0 | 0 |
| TRUST_BOUNDARY_CHANGE | 1 | 0 | 0 |
| NETWORK_EGRESS_CHANGE | 3 | 1 | 3 |
| CODE_EXECUTION_RELEVANT | 5 | 1 | 4 |
| FILESYSTEM_ACCESS_CHANGE | 2 | 1 | 1 |
| DESTRUCTIVE_OPERATION | 2 | 1 | 2 |
| ADDITIONAL_CONTEXT_REQUIRED | 4 | 0 | 1 |

The lexical rules got 11/59 correct and frequently abstained. This is not a comparison against Semgrep/CodeQL. Some evals have no negative or no positive support; per-eval precision/recall/F1 and FPR/FNR are in the reports with null for undefined values. The tiny denominators cannot support deployment thresholds or reliable confidence intervals.

## Timing and memory

| Local 0.6B measurement | Value |
|---|---:|
| Model import/load plus model-file hashing | 2.71 s |
| First full 14-eval request | 2.12 s |
| Load plus first request | 4.83 s |
| Warm p50, 39 subsequent requests | 2.82 s |
| Warm p95 | 4.84 s |
| Process peak RSS | 654.7 MiB |
| Peak MLX allocated device memory | 1.40 GiB |

RSS and device allocation are separate high-water marks on unified memory; do not sum them. Load plus first excludes interpreter startup/downloads and is not a cold-machine result. The initial earlier run had a warm median of 2.67 s; the archived final run above is the source-fingerprinted repeat and illustrates ordinary run-to-run latency variation. No absolute inference cost or CPU-only performance has been established.

The 500 ms aspiration is not met by this configuration. Repeating full context 14 times is a measurable inefficiency; it does not quantify the gain from a pointer architecture. Shared-prefix ordinary-LM scoring and matched-backbone comparisons must precede that conclusion.

## Diff-size timing controls

These are generated comment-padding controls, not real large diffs or quality examples. Both repetitions and actual token usage are in the [size sweep](../results/2026-09-27/qwen06b-sizes.json).

| Actual diff bytes | Total prompt tokens over 14 prefills | First request | Second request |
|---:|---:|---:|---:|
| 488 | 7109 | 2.72 s | 2.64 s |
| 2013 | 12233 | 4.63 s | 4.64 s |
| 8164 | 32911 | 15.50 s | 14.39 s |

## What would change the conclusion

1. Independent agreement on the label definitions, with ordinary changes and difficult negatives.
2. A measured strong general-model baseline on the same inputs, plus simple classifier and real deterministic-tool comparisons.
3. Ordinary 1–4B models and shared-context scoring before specialised training.
4. Kev transfer, then a controlled training experiment only after enough group-disjoint labels exist.
5. Separate calibration data, family-clustered uncertainty estimates, real size strata, CPU and modest-GPU measurements.

The current evidence supports continuing the experiment design and data work. It does not support shipping a security model, automated approvals, or a claim that sev already meets its thesis.
