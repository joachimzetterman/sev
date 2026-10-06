# Research findings and experiment priorities

Decision recorded: 2026-10-06. Focus sev's research on its own labelled code diffs
and controlled experiments. Use the SecJev and OpenJev investigations to improve
the training method, baseline implementation and evaluation controls. A stronger
ordinary-model baseline with shared-prefix scoring is the next engineering
experiment alongside annotation work.

The [roadmap](roadmap.md) owns current priorities and completion status. This
note preserves the evidence and reasoning behind them. The developer preview
can continue using existing models while annotation proceeds; independent labels
are required for credible quality claims and specialised training, not for trying
the workflow.

## Work to prioritise

| Priority | Next deliverable | Evidence needed to proceed |
|---|---|---|
| Own dataset | Independently annotate the [32 real-diff candidates](../data/pilot-001/README.md), resolve taxonomy disagreements, then expand the 100–200-change development pilot. | Retained independent annotations, per-eval agreement, adjudication and coverage of ordinary changes, fixes, hard negatives and missing context. |
| Stronger baseline | Compare a capable ordinary model with fresh and shared-prefix scoring on the same inputs; use MLX for the local experiment. | Pinned model and runtime, identical prompt tokens between execution paths, per-eval errors and end-to-end latency/memory for 1, 4 and 14 questions. |
| Controlled training | Measure off-the-shelf Kev transfer, then test a small LoRA and pointer-head adaptation against matched ordinary-model and simpler-head controls. | Independent train/dev/calibration/test partitions, fixed selection rules and equal data/selection budgets. The pilot and smoke set cannot become the held-out test set. |
| Calibration | Fit confidence scaling separately from model selection and measure confident errors and abstention coverage. | Held-out code-diff calibration data, per-eval support, NLL/Brier/ECE and family-grouped uncertainty estimates. |

The baseline experiment can diagnose speed and workflow problems before the
independent dataset is complete. Any quality observations on smoke or provisional
pilot labels remain developmental. Continue to use the [dataset](dataset.md) and
[experiment](experiment.md) protocols for the full evaluation.

## What SecJev contributes

SecJev is a trained security adaptation of Kev's candidate pointer scorer. Its
released corpus covers telemetry, tool outputs, authentication events and
explicit policy decisions. Those tasks do not establish performance on sev's
before-to-after code changes or its four-state uncertainty contract.
[Model and corpus](https://github.com/UESTC1010/SecJev/blob/24d96fd8e8759db61147a689776619ea2f668498/README.md).

Borrow its implemented training discipline: freeze the backbone, adapt LoRA and
the decision head, weight each question by the inverse number of questions in
its scene, select on development data, then fit temperature on a separate
calibration partition. For sev, scene weighting would prevent heavily annotated
diffs from dominating the objective; it does not by itself balance rare labels.
[Training recipe](https://github.com/UESTC1010/SecJev/blob/24d96fd8e8759db61147a689776619ea2f668498/TRAINING.md).

The paper's matched 0.8B comparison reports 90.46% task-macro accuracy for SecJev
versus 90.01% for one-token generative fine-tuning. Short-input latency is
79.2 versus 80.4 ms and peak memory 2.56 versus 3.52 GiB on an RTX 3090, with one
question per request and no prompt-cache reuse. This supports testing the value
of task supervision across several readouts; it does not establish a large
pointer-head speed advantage for our multi-question workload.
[Paper section 5.3](https://arxiv.org/html/2610.03073v1#S5.SS3).

Keep three implementation details in mind if revisiting SecJev:

- Its [reference runner](https://github.com/UESTC1010/SecJev/blob/24d96fd8e8759db61147a689776619ea2f668498/infer.py)
  calls the full-row forward path, repeating the state per question on Qwen3.5.
  Shared-prefix serving requires a different execution path in
  [its pinned Kev implementation](https://github.com/jaredpalmer/kev/blob/90990a5fac2995b9faa3190f7d437e84f2067768/kev/model.py).
- That Kev version rounds answer probabilities to two decimals. Sev's current
  [HTTP client](../sev/backends.py) only tolerates four-decimal rounding error.
  A reproduced contract check rejected a valid distribution after it rounded to
  a sum of 0.99. An adapter should preserve SecJev's separate unrounded values.
- The published 9B adapter is epoch 3; the paper uses epoch 2 after inspecting
  transfer scores. Pin the artifact before comparing results.
  [Checkpoint explanation](https://arxiv.org/html/2610.03073v1#A6).

SecJev's custom agreement also distinguishes its original contributions from
upstream data rights, including ToN-IoT's commercial-permission requirement.
It provides no blanket commercial clearance for the corpus and does not declare
that data terms automatically determine every resulting weight's license.
[License](https://github.com/UESTC1010/SecJev/blob/24d96fd8e8759db61147a689776619ea2f668498/LICENSE).
Importing its corpus or adopting its checkpoint is not a current priority.

## What the OpenJev discussion contributes

The [Hacker News discussion](https://news.ycombinator.com/item?id=49752041) links
to **TheoLeeCJ/SemIf-OpenJev**, which scores existing models' answer-token logits.
This is a different readout from Kev's trained pointer head. Its most useful
contribution for sev is an ordinary-model baseline with shared-state inference.

SemIf reports 333.1 seconds for fresh scoring versus 38.8 seconds for parallel
suffixes over 777 decisions on one RTX 3090. The faster path changed 6 decisions;
serial reuse changed 5. These are external systems measurements, not projected
sev or Mac timings. They make execution-shape parity an evaluation requirement.
[Results](https://github.com/TheoLeeCJ/SemIf-OpenJev/blob/23cf1f39fc9534fe81437200959b6dfc7106e45a/docs/RESULTS.md).

Its MLX implementation copies both attention and recurrent state, keys reuse by
exact prefix tokens, and checks variable-length branches, reordering and repeat
calls. Our current prompts put question-specific material before the diff, so
shared diff prefill requires a prompt-layout change. Compare fresh and cached
execution under the same new layout, and measure the layout's quality effect
separately from cache reuse.
[MLX method](https://github.com/TheoLeeCJ/SemIf-OpenJev/blob/23cf1f39fc9534fe81437200959b6dfc7106e45a/docs/MLX.md),
[current sev prompts](../sev/backends.py).

SemIf also retains logits and evaluates workload-specific temperature scaling
with group-disjoint folds. Its WANLI calibration error falls from 20.8% to 6.9%
without changing selected answers. Borrow the method, not the fitted temperature
or a confidence threshold. Calibration on natural-language inference is not
calibration on code changes.
[Calibration](https://github.com/TheoLeeCJ/SemIf-OpenJev/blob/23cf1f39fc9534fe81437200959b6dfc7106e45a/docs/CALIBRATION.md).

SGLang now documents native decision scoring and a System One compatible route;
this is a potential GPU baseline without maintaining a custom server. The
documentation advises a nightly build until a release includes the feature.
Pin and check support before use. API compatibility does not identify the model
architecture: ordinary answer-token scores must not inherit sev's
`pointer_softmax` metadata merely by using the Kev-shaped endpoint.
[SGLang decision models](https://docs.sglang.io/docs/supported-models/decision_models).

## Controls to preserve in our experiments

- **Evidence use:** include missing-context variants and supply the deciding fact
  in a paired case. Test shuffled diffs with labels held fixed as a negative
  control against reliance on label priors. The linked
  [jevlike starter](https://github.com/vinnylarouge/jevlike) uses shuffled-context
  controls; its model results do not transfer to sev.
- **Semantic direction:** distinguish a security-relevant fix from a newly
  introduced vulnerability. Reverse changes only with independently checked
  labels; reversal does not imply every judgment should flip.
- **Robustness:** reorder questions and options, add irrelevant context and
  instruction-like comments, and vary batch shape. Keep related variants in one
  family and inspect individual flips, not just aggregate accuracy.
- **Uncertainty:** retain `YES`, `NO`, `UNKNOWN`, `INSUFFICIENT_CONTEXT` and
  separate algorithmic abstention. A normalized option distribution is not proof
  that any supplied option is supported by the evidence.

## Evidence scope and conditions for revisiting the plan

The comparison used sev at `29477091f7f1edb9285cbe41235037fde599debe`, SecJev at
`24d96fd8e8759db61147a689776619ea2f668498`, and the linked SemIf documents verified
at `23cf1f39fc9534fe81437200959b6dfc7106e45a`. SGLang documentation is a changing
reference, checked during the October 5 investigation.

Local investigation verified the SecJev corpus archive checksum, 27 manifested
file hashes, four split-content hashes, 115,324 unique scenes, 170,185 questions
and no cross-split overlap among 1,638 declared groups. It also checked the 0.8B
metric aggregation and the rounding incompatibility above. These checks do not
validate label correctness, undisclosed near-duplicates or model quality. No
SecJev or SemIf model inference was reproduced; their performance figures remain
author-reported. Sev's own executed measurements remain in [results.md](results.md).

Start specialised training when the taxonomy is usable, independent partitions
exist and the stronger baselines are measured. Prefer a simpler readout if it
matches the useful quality, confidence and cost trade-off. Revisit external
checkpoints when matched code-diff evaluation shows an advantage. Update the
roadmap when evidence changes these choices; preserve the dates and source
revisions behind historical findings.
