# Research roadmap

Status reviewed: 2026-10-05. Update this file as milestones are completed or the
evidence changes the plan. The linked protocols hold the detailed definitions;
this file records the execution order and next deliverable.

The milestone is to establish whether small models can make useful contextual
security judgments over engineering diffs at worthwhile quality, latency and
cost. A trained model remains an unproven outcome.

## Immediate priority: usable developer preview

The current priority is trying sev during real development. The
[developer preview](preview.md) adds one-time inference configuration, terminal
and JSON output, staged/base-branch diffs and an embeddable `security_eval()`.
It uses existing backends and keeps local inference as the default deployment
choice. It does not bundle a recommended checkpoint, claim calibrated confidence
or introduce a security gate.

Independent annotation and specialised training are no longer prerequisites for
trying the tool. They remain prerequisites for credible model-quality claims.
The next practical step is to configure a model and try representative changes,
recording confusing judgments, missing context and end-to-end latency. Model
generated feedback remains provisional. Avoid expanding the product until this
small workflow proves useful.

The real-diff intake and 32-candidate batch are prepared in
[PR #2](https://github.com/joachimzetterman/sev/pull/2), which is still separate
from this preview. The research sequence below remains the longer-term plan.

## Current evidence

- The prototype has 14 evals, dataset contracts, a CLI, scoring and interchangeable
  baseline backends. [Contributor guidance](../AGENTS.md) records project rules.
- Local rules and an ordinary 0.6B model have been measured on 20 authored smoke
  examples. Those provisional examples are not an independent benchmark.
- The tested small-model configuration needs improvement. It does not establish
  whether specialisation or Kev's architecture would help.
- Independent annotation, real deterministic-tool comparisons, strong
  general-model measurements and Kev comparisons remain outstanding.

See [the measured results](results.md) for exact evidence and limitations.

## 1. Prepared in PR #2: real-diff intake and first annotation batch

Build a reproducible importer and prepare 30–50 real changes as the first batch
of the [100–200-change development pilot](dataset.md).

- Record upstream project, immutable parent/change commits, extraction settings,
  source licenses and family relationships. Check redistribution rights before
  committing imported source text.
- Include ordinary changes, security fixes, hard negatives and missing-context
  cases across application code, IAM, SQL and CI/configuration. Avoid sampling
  only vulnerability fixes or obvious security keywords.
- Preserve the exact diff and explicitly supplied context seen by annotators.
  Keep advisory text and other potential label leaks outside model input.
- Keep unlabelled intake separate from the annotated dataset contract. Do not
  invent judgments to make a candidate pass validation.

**Done when:** the batch can be reproduced from its manifest, related examples
are grouped, inclusion/exclusion decisions are recorded, and the same inputs
are ready for independent annotation. This PR need not train or run a model.

## 2. Validate the taxonomy through independent annotation

Two reviewers independently label the same supplied inputs using the
[annotation guide](taxonomy.md). Retain their original annotations, measure
per-eval agreement and use a third reviewer to adjudicate disagreements.

Revise, merge or remove questions that reviewers cannot apply consistently.
Check missing-context judgments and hard negatives explicitly. Human review
capacity is a dependency; model-generated labels remain provisional.

**Done when:** agreement, disagreements, adjudication and taxonomy changes are
documented, with enough examples to identify problematic labels. Keep this pilot
in development; it must never become the held-out test set.

## 3. Establish measured baseline comparisons

After the pilot, freeze the evaluation protocol and acquire separate training,
development, calibration and test data. Assign whole projects and related
families to partitions before model or prompt selection. Use the
[dataset protocol](dataset.md) for contamination controls and annotation rules.

Compare actual deterministic tools, the simple classifier trained only on the
training partition, ordinary small language models and a strong general model.
Use identical evaluation inputs and the [experiment protocol](experiment.md).
Include an ordinary model with shared-context scoring so repeated full prefills
do not artificially favour the pointer architecture.

**Done when:** the comparison reports per-eval support, precision/recall, errors,
uncertainty and calibration alongside cold/warm latency, memory and cost. Select
thresholds without consulting test labels, and report uncertainty intervals and
coverage gaps rather than relying on a single aggregate score.

## 4. Test the added value of Kev and security specialisation

Measure off-the-shelf Kev transfer, then investigate specialised training only
after suitable independent training labels exist. Follow the
[Kev investigation](kev.md) and matched-backbone controls in the experiment
protocol: ordinary LM, fixed heads, pointer heads and adaptation with equal data
and selection budgets.

**Done when:** evidence supports a decision to continue, simplify or reject the
specialised-model hypothesis. Prefer the simpler approach if it matches the
useful quality/cost trade-off. The sub-500 ms latency target remains aspirational.

Routine validation stays local and CPU-only. Cloud/GPU experiments are separate
opt-in work with explicit resource limits and cost estimates. This roadmap does
not schedule compute. Dashboard, commercial and compliance features remain
outside this research milestone.
