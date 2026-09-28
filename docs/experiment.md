# Experiment protocol

## Research question and decision rule

Can a small specialised model improve security triage over deterministic signals
at sufficiently low latency and cost, while approaching a strong general model's
quality on **independent** labels? There is no trained sev checkpoint yet.

Before opening the independent test set, preregister the application, label costs,
model snapshots, prompts, calibration procedure and thresholds. Initial candidate
gates, to revise using the annotation pilot before freezing:

- Priority evals: PRIVILEGE_INCREASE, AUTHORIZATION_BOUNDARY_CHANGE and
  TENANT_BOUNDARY_CHANGE. At a development-selected operating point, seek >=90%
  positive recall and <=10% false-positive rate. Report uncertainty intervals and
  support; a one-positive smoke result is not evidence for this gate.
- Missing-context detection: recall >=80%, and <=5% confident definitive answers
  on gold INSUFFICIENT_CONTEXT cases at a preregistered 0.9 confidence cutoff.
- Useful cost/latency: target a material improvement, initially 3x lower warm
  latency or cost at comparable priority-label recall to the general baseline.
  Report absolute memory and latency as well. <500 ms for common diffs remains
  an aspiration, not an acceptance claim.
- Architecture: if a fixed classifier or ordinary small LM matches the pointer
  model's quality/latency trade-off, prefer the simpler approach. If deterministic
  tooling already covers the useful cases, or the general model is affordable
  enough and substantially better, the original specialised-model thesis weakens.

The thresholds above are proposed research criteria, not operational security
guarantees. Never collapse label costs into a single accuracy objective.

## Baseline matrix

| Arm | Status in prototype | What it isolates |
|---|---|---|
| A0: lexical indicators | Executable `--backend rules`, measured on smoke examples | Transparent low-cost floor; false positives from comments expected |
| A1: deterministic tools | Protocol below; not run | Actual scanner value and coverage, distinct from A0 |
| A2: simple classifier | Executable bag-of-words Naive Bayes, requires separate training data | Whether a neural backbone is necessary at all |
| B: strong general model | Executable `--backend chat`, frozen prompt, endpoint required | General contextual reasoning baseline; not measured here |
| C: ordinary small LM | Executable `--backend mlx`, pinned 0.6B model, measured | Prompted next-token classification before specialised training |
| D0: off-the-shelf Kev | Executable `--backend kev`, server/checkpoint required | Transfer of a generic decision model; not measured here |
| D1: security-adapted head/LoRA | Deferred until independent training labels exist | Effect of specialisation, with matched training/backbone controls |
| E: deterministic signals + model | Later controlled ablation | Incremental gain from combining tools and contextual judgments |

For A1, pin Semgrep/CodeQL/secret/policy engine versions and rulesets. Run relevant
tools on before/after checkouts in isolated environments, recording unavailable
build/language coverage separately. Compare newly introduced, removed and
unchanged findings; a tool can often require more than a raw diff. Publish a
frozen finding-to-eval mapping based on what each rule actually establishes. No
finding means abstention unless a rule proves a negative. Do not compare the
lexical floor to a neural model and call that a Semgrep comparison. The prototype
does not yet import tool findings automatically.

For A2, Naive Bayes uses token counts with Laplace smoothing, one four-class
classifier per eval, and only explicitly annotated training examples. It can
reveal shortcut learning. Log priors and sparse log likelihoods are cached at
model load; this trades initialization work and memory for cheaper predictions.
A later TF-IDF/logistic-regression comparison should use
the identical grouped splits and calibration protocol. Training on smoke data is
forbidden by the fit command.

For B, a concrete open-weight candidate is
[Qwen3.5-397B-A17B](https://huggingface.co/Qwen/Qwen3.5-397B-A17B), a large
general-purpose model. This is a candidate reference, not a claim it is strongest
for security; include a leading general reasoning model available to the team as
another comparator when access exists. Use a compatible server, exact model
revision, fixed context budget, temperature zero and the checked-in structured
prompt. The runner submits all questions over one input and rejects malformed or
truncated responses. Self-reported probabilities must be evaluated as such; they
are not equivalent to token logits. The endpoint's `/v1/chat/completions` contract
is supported by runtimes such as [vLLM](https://github.com/vllm-project/vllm).

The zero-shot B prompt includes operational definitions and explicit data/instruction
separation. Improve it only on development data; freeze a separate few-shot arm
if examples help. Do not expose gold rationales, advisories or commit messages.
No general-model inference endpoint was available during this task, so B's
quality, latency and cost remain unmeasured. A runner is not a measured baseline.

For C, use ordinary [Qwen3-0.6B](https://huggingface.co/Qwen/Qwen3-0.6B),
the pinned [MLX 4-bit conversion](https://huggingface.co/mlx-community/Qwen3-0.6B-4bit),
and [MLX LM](https://github.com/ml-explore/mlx-lm). The model receives one question
and the full diff per forward pass with thinking disabled. Score next-token
letters A/B/C/D, then normalize only those four logits. This avoids JSON-format
errors but conditions on the four-letter answer space; `answer_token_mass_min`
records how much full-vocabulary probability that space had. Low mass means the
restricted probabilities can be misleading. The implementation checks that all
four letters are distinct single tokens. It performs separate full prefills,
with no prefix caching or fine-tuning. It is intentionally an unoptimised ordinary
model control, not a fair demonstration of Kev's potential speedup.

For D0/D1, four-way Choice maps directly to the same state contract. Record base
and adapter revisions, pointer dimensions, LoRA configuration, dtype, context
limits and the checkpoint's shipped temperature. `calibrated: false` in sev means
not validated on security data, even if Kev ships a fitted temperature. Add the
following before claiming an architecture result: ordinary LM on the same base,
fixed four-way heads, pointer head without LoRA, pointer+LoRA, and matched
supervised ordinary LM; equal training labels and selection budgets. Repeat over
at least three seeds. Test order permutations and hybrid row/cache parity.

An optional [Modal runner](../scripts/modal_baseline.py) prepares an ephemeral
single-H100 Qwen3.5-27B comparison, with pinned model/runtime, a 20-minute job
timeout, no retries and a maximum of 20 authored smoke examples. Its local command
interface was checked; **no cloud job was started**. It does not deploy an
endpoint. The exact candidates are in [the baseline manifest](../experiments/baselines.json).
Cloud inference remains a separate, explicitly selected experiment; the local
runtime has no Modal dependency. Record billed duration and startup time when a
cloud comparison is eventually authorised.
The runner adapts its server samples into the same report builder and artifact
writer used by local evaluation. Contract tests use a fake Modal SDK and recorded
sample fixtures; they do not establish that cloud inference works.

## Scoring contract

Per eval, report class support, a four-state confusion matrix plus ABSTAIN,
precision/recall/F1 for each class, coverage and accuracy both with and without
algorithmic abstentions. Missing predictions and backend errors stay in the
denominator; missing gold labels are excluded. Repeated timing runs do not become
additional independent examples.

`resolved_binary` uses only gold YES/NO rows. Its recall denominator includes all
gold positives, even if the model returns uncertainty or abstains. Explicit
false-negative rate counts predicted NO on gold YES. The separate
`missed_positive_rate_including_abstentions` counts every non-YES on gold YES;
otherwise a model could improve apparent recall by refusing difficult cases.
False-positive rate uses all gold negatives. Four-class metrics additionally
penalize a confident YES on a gold missing-context case.

Calibration reports multiclass Brier (sum over four states, range 0–2), log loss
(probabilities clipped at 1e-15 for the logarithm), and 10 equal-width top-label
ECE bins. Bins include probability 1.0 in the last bin. These are raw probability
diagnostics, not evidence of calibrated operation. Calibration metrics are null
for deterministic rule indicators. Undefined metrics are null, never zero.

After adequate labels exist, fit temperature(s) on **calibration only**, selecting
global versus per-eval fitting on dev with minimum support constraints. Preserve
raw and transformed probabilities. Choose routing/abstention thresholds on dev or
a separately reserved policy-selection partition, never test. The current harness
measures calibration but deliberately does not fit a temperature to 20 smoke
examples. Implement fitting and threshold artifacts before any trained release.

For uncertainty, inspect UNKNOWN and INSUFFICIENT_CONTEXT separately. Plot
risk/coverage with ties grouped, retained error and missed positives; measure the
fraction of gold insufficient cases receiving definitive YES/NO at >=0.9.
Uncertainty can be correct even when the code happens to be safe in its full
repository. Use paired, **family-clustered** bootstrap intervals when comparing
arms; do not treat 14 labels on one diff as 14 independent changes. Confidence
intervals, threshold curves and automatic calibration fitting are protocol work
remaining beyond the current smoke scorer.

## Timing and resources

Reports record per-call latency, first evaluation, model initialization, load plus
first evaluation, warm p50/p95, peak client RSS, input throughput when available,
MLX device allocation high-water mark, failure counts and buckets by diff bytes.
`timing_scope` and `model_load_scope` identify the measured boundaries. For local
MLX, `load_plus_first_eval_ms` excludes interpreter startup and model download,
and includes file hashing. Modal's server load measurement includes model
download/initialization, while its per-request samples exclude RPC and image
startup. Neither is a complete remote server cold start. Client environment/RSS
and server runtime/GPU/RSS remain separately identified; unmeasured server
startup/memory fields are null. Local inference cost is unknown
unless a documented electricity/hardware or GPU-hour rate is supplied; no API
charge does not mean zero total cost. Rules report zero metered inference charge.

Measure separately: fresh-process startup with warm filesystem cache; cold machine
or container startup; loaded-model/new-diff calls; repeated identical-diff cache
hits; 1/5/14/20 questions; realistic 256/1k/4k/8k token inputs; large/minified or
unsupported inputs. Use real varied diffs for quality and padded controls only
for timing. Pin thread count, model runtime, OS, CPU/GPU, RAM, dtype, quantization,
seed, power mode and concurrency. Report prompt-token counts rather than treating
bytes as tokens. Do not average cache hits into new-diff latency.

Hardware matrix: this 24 GiB Apple Silicon machine first, then CPU-only, then a
modest single GPU/CI runner, and a sufficiently sized GPU reference for B. A
result on one Mac is not a CPU or CI performance claim. Measure before porting,
batching, quantizing further or adding retrieval.

## Minimal CLI

```text
git diff | uv run sev --backend MODEL
git diff | uv run sev - --backend MODEL
uv run sev eval change.diff --backend MODEL [--context snippets.json]
uv run sev diff --backend MODEL          # unstaged, tracked changes
uv run sev diff --staged --backend MODEL # index versus HEAD
```

JSON is always emitted; no `--json` switch is needed yet. Untracked files are not
implicitly included. Empty input, over-budget input and invalid outputs fail
explicitly. No pass/fail security gate, automatic fixes, long review text or
invented context paths. Exit 0 means the requested operation completed, 1 means
a benchmark contains backend failures, and 2 means an input/configuration error.
`--context` takes a JSON file path, not inline JSON. Benchmark runs reserve a new
output directory before loading a model or starting inference. A failed startup
can leave an empty directory; inspect it and choose a fresh run identifier.

Inference output uses an envelope with schema/taxonomy/model information and
per-eval state distributions. The output never contains a `secure` field.
Callers can later request context or trigger deterministic policy/human review;
sev must not become the sole authorization boundary.
