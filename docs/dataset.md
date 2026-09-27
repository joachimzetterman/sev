# Dataset and annotation protocol

## Wire format

One JSON object per line, schema `sev-0.1`, taxonomy `sev-taxonomy-0.1`.
[`data/smoke.jsonl`](../data/smoke.jsonl) contains complete examples. Fields:

| Field | Meaning |
|---|---|
| `id` | Stable example identifier; never sent to the model |
| `split` | `smoke`, `train`, `dev`, `calibration`, or `test` |
| `group_id` | Family linking a fix, vulnerable variant, context variants, injection variants, forks/backports and synthetic siblings |
| `source` | `kind`, `project`, immutable `revision`, source `license`, source `url` |
| `input.diff` | Before-to-after unified diff with paths/hunk context |
| `input.context` | Explicit list of `{path, content}` snippets; no automatic retrieval |
| `judgments` | Partial mapping of eval ID to state, rationale, evidence and missing-context facts |
| `annotation` | `provisional` or `adjudicated`; distinct rater identifiers |

Example judgment:

```json
{
  "state": "INSUFFICIENT_CONTEXT",
  "rationale": "Removing this route check does not establish effective privilege.",
  "evidence": ["ownership check removed from route"],
  "missing_context": ["middleware implementation and route binding"]
}
```

Evidence is a human annotation locator/description in v0.1. It is not yet a
validated machine span. Empty/absent annotations mean unlabelled, never NO.
Future span annotations should use side (`before`/`after`/context path), line
numbers and content hashes. Source metadata, CVE descriptions, commit messages,
gold rationales and raters must stay outside model input: they can reveal labels.

Only `input` reaches a backend. The model sees the fixed taxonomy definitions,
not source IDs, split IDs, provenance, or gold judgments. Reports persist source
hashes and scores without copying the diffs.

## Acquisition and independence

Start with a 100–200 change annotation pilot spanning application code, IAM,
configuration, CI and SQL; keep this pilot in development. Sample ordinary
engineering changes as well as security fixes. Match negatives by project,
language, change size and subsystem; a constant-only negative set would inflate
results. A fixed commit remains security-relevant and is not an automatic NO.

Two raters independently label each eval using the same supplied context and
definitions. Require a short rationale and evidence for YES/NO, a conflicting
fact for UNKNOWN, and a specific missing fact for INSUFFICIENT_CONTEXT. Retain
each independent annotation file before adjudication; a third reviewer resolves
disagreement. The current 20 examples have one assistant author and are
provisional. No inter-rater agreement has been measured yet.

```sh
uv run sev agreement annotations/rater-a.jsonl annotations/rater-b.jsonl
uv run sev validate data/train.jsonl data/dev.jsonl data/calibration.jsonl data/test.jsonl
```

The agreement command reports per-eval raw agreement and Cohen's kappa. Inspect
class prevalence and disagreements alongside kappa; missing overlap is not
agreement. For the pilot, aim for raw agreement >= 0.85 and kappa >= 0.6 on
adequately represented labels. These are provisional research gates, not claims
about what has been achieved. Merge/rewrite/drop labels with persistent ambiguity,
especially broad trust-boundary and authorization-boundary distinctions.

After revising the taxonomy, acquire new independently labelled data. Assign
whole projects/families to partitions before model or prompt selection. Suggested
starting allocation is 60/15/10/15% train/dev/calibration/test, adjusted for label
support. Reserve an additional later-time, unseen-project panel. Aim for at least
100 positives and 100 negatives per priority eval in the independent assessment,
plus meaningful missing-context and ambiguous cases; sparse labels must report
wide uncertainty rather than a headline score.

The validator rejects repeated IDs, cross-split projects/groups/commits and exact
diff duplicates after removing hunk coordinates. It also requires adjudication
and two rater identifiers on `test`. This enforces metadata, not the honesty of
an annotation. It cannot detect undocumented forks, near duplicates, shared
synthetic templates, or foundation-model pretraining exposure. Curate a manifest
that connects those families, perform near-duplicate review before freezing,
and disclose unknown pretraining contamination. Normalizing whitespace alone is
unsafe for languages where whitespace changes semantics.

Freeze dataset/taxonomy/prompt hashes, evaluation code, threshold choices and
model snapshots before opening test results. All prompt examples come from
train/dev, never calibration/test. Do not generate the benchmark with the model
being evaluated and call it independently labelled.

## Candidate public sources

These are acquisition candidates, not imported examples or confirmed sev labels.
Their existing vulnerability targets do not answer the proposed taxonomy.

| Source | Useful material | Main limitation / acquisition action |
|---|---|---|
| [SAP Project KB](https://github.com/SAP/project-kb) | Curated vulnerability-to-fix references; recover parent/fix diffs | Positive-fix sampling bias; inspect original patch license and include ordinary neighbouring changes |
| [GitHub Advisory Database](https://github.com/github/advisory-database) | Advisory references that can lead to real fix commits across ecosystems | References are not always precise fix mappings; advisory metadata must not be model context |
| [PrimeVul](https://github.com/DLVulDet/PrimeVul) | Curated vulnerability examples, paired material and commit metadata | Mostly C/C++ function-level vulnerability targets; reconstruct full diffs and relabel; preserve its contamination groupings |
| [BigVul/MSR20](https://github.com/ZeoVan/MSR_20_Code_vulnerability_CSV_Dataset) | Before/after code and commit/CVE metadata | Label noise and overlap with other corpora; never mix derived families across partitions |
| [OWASP BenchmarkJava](https://github.com/OWASP-Benchmark/BenchmarkJava) | Controlled positive/negative tests for deterministic-tool sanity checks | Test cases are not natural engineering diffs; any derived edits are synthetic families |
| [Django](https://github.com/django/django) | Authentication, middleware, input handling and ordinary framework changes | Framework knowledge can hide required context; sample non-security commits and document supplied context |
| [Keycloak](https://github.com/keycloak/keycloak) | Identity, role and realm boundary changes | Identity-heavy source bias; realm semantics need explicit annotation |
| [Terraform AWS provider](https://github.com/hashicorp/terraform-provider-aws) | Policy/configuration handling and tests | Provider code changes are not automatically effective infrastructure permission changes |

For every imported example record the upstream repository, parent and changed
commit, path licenses, extraction tool version, acquisition time and family
relationships in a companion provenance manifest. The minimal v0.1 source field
holds the changed revision; the manifest carries both sides. Check rights before
redistributing source snippets; a dataset's metadata license does not relicense
the underlying projects. This prototype redistributes only authored examples.

Semgrep's [community rules](https://github.com/semgrep/semgrep-rules) can guide a
deterministic comparison, but they have their own Rules License. Do not bundle
them under sev's license or treat a rule hit as ground truth for a contextual
label.

## Adversarial panel

Keep clean and perturbed variants in the same family. Include fake system
messages, literal model control tokens, comments claiming nonexistent checks,
security-looking identifiers in benign edits, removed-line instructions,
minified/generated files, multi-file moves, Unicode confusables, irrelevant
padding and tail-only security changes. For code-preserving perturbations,
measure paired decision flips and change in positive/uncertainty probability.
Do not assume every perturbation preserves semantics: a changed configuration
or executable string can be a real engineering change.

Context variants must include the same route alone, with a real middleware
control, and with a middleware control that does not apply. Score whether the
model requests the missing fact, resolves it when supplied, and avoids inventing
it. Full repository retrieval remains out of scope.
