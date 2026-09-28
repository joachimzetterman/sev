# Kev architecture investigation

Inspected source: [`jaredpalmer/kev` at `5920c5fe4ca8e0970ed4209ac2c9b8e18bea5109`](https://github.com/jaredpalmer/kev/tree/5920c5fe4ca8e0970ed4209ac2c9b8e18bea5109),
2026-09-27. This is a source inspection, not an independent reproduction of Kev's
published accuracy or speed. No Kev implementation or model weights are vendored.

## What the primitive actually does

Kev converts a document (`state`) and questions into contextual option scores.
Its `noul` API maps a binary question to two options, false and true; `choice`
maps each supplied option to a named probability; `score` maps ordered levels to
options and reports their expected index. These share the same internal pointer
operation. Question IDs are bookkeeping, not model input. The advertised
`confidence` transformation is not a measured accuracy rate, and the API's output
token count measures serialized output size, not generated tokens.
[API implementation](https://github.com/jaredpalmer/kev/blob/5920c5fe4ca8e0970ed4209ac2c9b8e18bea5109/kev/api.py).

## Encoding and the attention-only case

The internal logical layout is:

```text
[state] diff and supplied context
[q] question 1 [opt] NO [/opt] [opt] YES [/opt] ... [decide]
[q] question 2 [opt] NO [/opt] [opt] YES [/opt] ... [decide]
```

These are conceptual names. The encoder reuses five existing Qwen special tokens
instead of adding embedding rows. It returns token IDs, segment IDs, position IDs,
each decision-token offset and each option's closing-token offset.

For an attention-only backbone, let `seg=0` be the state and `seg=k` be question
k. Query token `i` can attend to key `j` iff:

```text
j <= i AND (seg[j] == 0 OR seg[j] == seg[i])
```

Each question's position IDs restart at the end of the state. The state cannot
read any questions, and questions cannot read one another. Removing an unrelated
question therefore should not change another question's answer, apart from
numerical variation. This is stronger than merely placing all questions into an
ordinary autoregressive prompt. It is **not** a guarantee that malicious state
content cannot influence judgments.

The implementation materializes a dense L×L attention mask; mathematical branch
independence does not automatically imply sparse compute. The row-form fallback
also handles attention-only inputs above the packed token budget. Shared prefix
work and avoided decoding are concrete savings to measure, not a guarantee of
linear scaling in the number of questions.

The option representation is the hidden state at its closing delimiter; the
query representation is the hidden state at `[decide]`. Two learned affine
projections, both into a default 256-dimensional space, produce:

```text
z_j = dot(W_k h_option_j + b_k, W_q h_decide + b_q) / sqrt(256)
p_j = softmax(z / T)_j
```

This points to a supplied **answer option**, not a source-code location or
retrieved evidence span. There is no token-by-token answer generation and no
vocabulary head in the decision backbone. Normal option spans remain causal:
later options can see earlier options. Optional option-isolation masks exist for
attention-only models; ordinary question isolation is not option-permutation
invariance.
[Encoder, masks and pointer head](https://github.com/jaredpalmer/kev/blob/5920c5fe4ca8e0970ed4209ac2c9b8e18bea5109/kev/model.py).

## Why the current hybrid models need a different execution path

The current Qwen3.5/Qwen3.8 families mix attention with recurrent Gated DeltaNet
layers. An attention mask cannot stop recurrence from carrying state between
concatenated question segments. Kev detects `linear_attention` layers and uses
independent rows instead:

```text
state -> one prefix prefill -> cache
                              |-> question 1 row -> options
                              |-> question 2 row -> options
                              |-> question N row -> options
```

Each row contains exactly the state plus one question at the same logical
positions. `forward()`/the plain training and benchmark path recomputes the state
per row. `probs()` and serving prefill the state once, then continue separate
branches from its cache. The cache includes attention keys/values **and** the
DeltaNet convolution/recurrent state; copying KV alone would be incorrect.
Mutable cache state is replicated for each group of branches so one branch cannot
contaminate the next. Token-budgeted chunks bound memory; cache replication and
question-to-state attention still cost work as question count grows.
[Row and prefix paths](https://github.com/jaredpalmer/kev/blob/5920c5fe4ca8e0970ed4209ac2c9b8e18bea5109/kev/model.py).

Shared-prefix training is an additional implementation, not automatic inference
cache reuse under autograd. It keeps functional per-layer prefix state so branch
gradients accumulate into the prefix and checkpoint replay remains valid.
[Shared-prefix training](https://github.com/jaredpalmer/kev/blob/5920c5fe4ca8e0970ed4209ac2c9b8e18bea5109/kev/shared_prefix.py).

Tests compare packed and row forms, cached and uncached paths, repeated prefix
reuse, question isolation, chunking, and shared-prefix gradients. Their existence
supports the intended invariants; they were inspected but not run in this sev
work. Porting the architecture requires repeating these tests on the chosen
backbone, dtype and runtime.
[Model parity tests](https://github.com/jaredpalmer/kev/blob/5920c5fe4ca8e0970ed4209ac2c9b8e18bea5109/tests/test_model.py).

## Training, calibration and operational details

Kev trains a rank-16 LoRA adapter plus the pointer head in its standard recipe.
Its trainer supports cross-entropy against hard or soft option targets, optional
ordinal penalties for scores, and option-order augmentation/consistency losses.
The labels teach contextual decisions, not reconstruction of arbitrary security
documentation. These are useful precedents for sev; none establish security
judgment quality.
[Training losses and configuration](https://github.com/jaredpalmer/kev/blob/5920c5fe4ca8e0970ed4209ac2c9b8e18bea5109/kev/train.py).

At inference the pointer divides logits by a fitted temperature. A global
temperature preserves argmax and cannot repair incorrect rankings. Kev's
calibration tooling explicitly distinguishes in-sample fits from group-disjoint
out-of-fold evaluation. sev must fit its own calibration partition; a temperature
learned on support or policy data is not evidence of calibration on code diffs.
[Calibration methodology](https://github.com/jaredpalmer/kev/blob/5920c5fe4ca8e0970ed4209ac2c9b8e18bea5109/kev/calibrate.py).

Serving also has a cross-request prefix cache. A repeated-diff cache hit must be
measured separately from a new-diff evaluation. Its key uses state token IDs and
the option-isolation setting. Concurrent batching, precision and cache eviction
can materially alter latency and memory.
[Serving/cache implementation](https://github.com/jaredpalmer/kev/blob/5920c5fe4ca8e0970ed4209ac2c9b8e18bea5109/kev/serve.py).

The generic encoder defaults to a 384-token state, but that is not a description
of all current training: released checkpoints include later long-document
adaptation. Serving limits are not a demonstrated accuracy guarantee. Inspect
the exact checkpoint's training history and measure code-diff length effects.
[0.8B model card](https://github.com/jaredpalmer/kev/blob/5920c5fe4ca8e0970ed4209ac2c9b8e18bea5109/docs/model-cards/kev-0.8b.md).

## What changes for sev

1. **Task and targets:** use four-way Choice questions with explicit NO, YES,
   UNKNOWN and INSUFFICIENT_CONTEXT definitions. Noul alone cannot express why a
   question is unresolved. A claim about present authorization evidence is a
   separate task from authorization relevance.
2. **Input representation:** preserve file paths, hunk context and added/removed
   lines. Include only explicitly supplied context initially. Reject over-budget
   inputs rather than deleting the security-relevant tail silently.
3. **Data:** train on security decisions, direction-sensitive minimal pairs,
   correct fixes, hard negatives and missing-context variants. Group siblings
   together; do not turn vulnerability labels directly into relevance labels.
4. **Calibration and routing:** fit on a separate security calibration partition;
   evaluate uncertainty as a target and algorithmic abstention separately. Review
   routing belongs to the caller's policy.
5. **Robustness:** keep comments as data, escape structural tokens, and test
   semantic prompt injection, forged delimiters, option order, question order,
   misleading names and omitted context. Isolation alone is insufficient.
6. **Controlled comparisons:** compare ordinary LM letter scoring, generated JSON,
   fixed multi-label heads, and the pointer head on matched backbone sizes,
   training examples, context limits and precision before attributing a gain to
   the architecture. Qwen3-0.6B versus Kev-Qwen3.5-0.8B is a product comparison,
   not an architecture ablation.
7. **Portability:** a backbone adapter must supply tokenization, branch isolation,
   cache semantics and hidden states. New backbones may require new delimiters,
   masks or recurrent-state handling. The high-level question contract can remain
   stable. Open weights and local execution do not imply European provenance.

**Decision:** retain Kev as an experiment arm. Do not train a specialised sev
checkpoint until independent labels and ordinary-model baselines exist. The
plausible saving is shared prefill plus bounded option scoring; its magnitude on
multi-file security diffs remains an empirical question.
