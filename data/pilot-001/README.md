# First real-diff development batch

32 unlabelled candidates, acquired 2026-09-28. This is the first batch toward the
100–200-change annotation pilot, not training data or an independent test set.
There are no human labels, model predictions or agreement measurements here.

| Project | Acquisition snapshot | Candidates | Notices retained |
|---|---|---:|---|
| [Django](https://github.com/django/django) | 5.2.7 | 8 | [BSD-3-Clause](licenses/django/LICENSE), [Python-2.0](licenses/django/LICENSE.python) |
| [Flask](https://github.com/pallets/flask) | 3.1.2 | 8 | [BSD-3-Clause](licenses/flask/LICENSE.txt) |
| [Werkzeug](https://github.com/pallets/werkzeug) | 3.1.3 | 8 | [BSD-3-Clause](licenses/werkzeug/LICENSE.txt) |
| [Terraform AWS IAM modules](https://github.com/terraform-aws-modules/terraform-aws-iam) | v6.2.0 | 8 | [Apache-2.0](licenses/iam/LICENSE) |

Full immutable snapshot, parent and change IDs are in [manifest.json](manifest.json).
Imported source retains these upstream licenses; sev's license does not replace
them. Input patches preserve before/after source text; extraction does not edit
the source. The manifest maps included paths to upstream projects and notices.

## Selection

The curator considered the newest 80 non-merge commits reachable from each
snapshot (`git rev-list --date-order --no-merges --max-count=80`), then manually
selected eight per project. The manifest records all 320 decisions, including
288 exclusions and their reasons. Exclusion never means a negative security label.

Inputs cover Python application/framework changes, SQL-related ORM implementation,
IAM Terraform and CI workflows. They include ordinary changes, documented fixes,
security-sensitive changes, and candidates intended to probe missing context or
misleading security terminology. These are sampling intentions, not labels. SQL
coverage is ORM code, not raw SQL migrations; application and language coverage
remain limited.

Two Django SQL-alias changes share a family. Three IAM external-secrets policy
changes share another: 32 changes represent 29 provisional families. Future forks,
backports and variants must join their existing family; whole-project isolation
is still required before independent evaluation.

Selection references include the upstream
[Django release notice](https://www.djangoproject.com/weblog/2025/oct/01/security-releases/)
and [Werkzeug advisory](https://github.com/pallets/werkzeug/security/advisories/GHSA-f9vj-2wh5-fj8j).
Do not give these links or this curation summary to reviewers before annotation.

## Files and limitations

- [candidates.jsonl](candidates.jsonl): supplied inputs, opaque IDs and hashes;
  no labels or curation metadata. Every context list is empty.
- [manifest.json](manifest.json): provenance, license review, families, selection
  decisions and input hashes; coordinator material.
- [report.json](report.json): extraction provenance and omitted-file audit;
  coordinator material.
- `licenses/`: complete upstream notices, verified at both sides of each change.

This is a historical, manually selected, Python-framework/IAM-heavy sample.
Negatives and missing-context cases remain hypotheses until independently
labelled. Selected-file views omit tests, release notes and other changed files;
they cannot establish whole-commit security. Public source may have appeared in
model pretraining. Recognition and selection bias remain even with commit and
advisory metadata excluded.

Follow [the intake protocol](../../docs/intake.md) for offline verification,
reproduction and annotation handoff. Expand the pilot after reviewing initial
label coverage and disagreements.
