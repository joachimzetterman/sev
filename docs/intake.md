# Real-diff intake

[`pilot-001`](../data/pilot-001/README.md) contains 32 unlabelled changes for the
development annotation pilot. Intake preserves inputs and provenance; it does
not infer labels, train a model or establish benchmark quality.

## Verify the committed batch offline

```sh
uv run sev verify-intake data/pilot-001/manifest.json data/pilot-001
```

This checks IDs, strict input fields, content hashes, manifest/report consistency
and redistributed licenses without upstream repositories or a model. Hashes
detect drift against the committed manifest; they do not authenticate a
maliciously replaced manifest. Confirming the omitted-path audit requires
reproduction from Git objects.

## Reproduce from upstream Git objects

Acquire bare repositories separately. These commands download source history
without checking out or executing it:

```sh
mkdir -p artifacts/sources
git clone --bare --depth 200 --branch 5.2.7 https://github.com/django/django.git artifacts/sources/django.git
git clone --bare --depth 200 --branch 3.1.2 https://github.com/pallets/flask.git artifacts/sources/flask.git
git clone --bare --depth 200 --branch 3.1.3 https://github.com/pallets/werkzeug.git artifacts/sources/werkzeug.git
git clone --bare --depth 200 --branch v6.2.0 https://github.com/terraform-aws-modules/terraform-aws-iam.git artifacts/sources/iam.git
```

Tags are acquisition hints. Full commit IDs and expected input hashes in the
manifest determine the accepted objects. If upstream history becomes unavailable,
preserve a local copy rather than substituting newer code.

Create `artifacts/repositories.json` with paths relative to the current working
directory, or absolute paths:

```json
{
  "django": "artifacts/sources/django.git",
  "flask": "artifacts/sources/flask.git",
  "werkzeug": "artifacts/sources/werkzeug.git",
  "iam": "artifacts/sources/iam.git"
}
```

Then reproduce into a new directory:

```sh
uv run sev intake data/pilot-001/manifest.json \
  --repositories artifacts/repositories.json --out artifacts/pilot-001-reproduced
uv run sev verify-intake data/pilot-001/manifest.json artifacts/pilot-001-reproduced
cmp data/pilot-001/candidates.jsonl artifacts/pilot-001-reproduced/candidates.jsonl
```

A failed extraction may leave its output directory reserved; existing runs are
never overwritten. Reports record Git version and the extractor source hash, so
reports from different environments can differ while candidate bytes match. If
a Git version or configuration changes patch rendering, the expected input hash
causes failure. Investigate rather than automatically accepting new hashes.

## Contracts

The strict `sev-intake-0.1` manifest records:

- Batch ID, acquisition time, sampling procedure and development-only purpose.
- Project repository URL, immutable snapshot, original license paths and hashes,
  and a review of licenses applying to the selected paths.
- Every selection decision: opaque ID, project, exact parent/change commits,
  family, reason and sampling tags. Excluded commits have no inputs or labels.
- Included candidates' literal changed paths, explicitly pinned context ranges
  and the expected hash of the entire `input` object.

The extractor accepts single-parent commits reachable from the pinned snapshot.
It reads Git objects without checkout, hooks, external diff/textconv drivers,
replacement refs, lazy fetching or source execution. Selected files must be
regular UTF-8 text without NUL bytes, at most 2 MB each. An entry selects up to
32 files and eight context snippets; serialized input has the existing 256 KiB
budget. Invalid or oversized inputs fail rather than being truncated.

Diffs use Myers, three context lines, fixed `a/` and `b/` prefixes, full blob IDs
and no rename detection. These are **selected-file views**, not necessarily
whole commits. The report lists omitted changed paths. Explicit context snippets
preserve LF line boundaries and identify the before/after side, path and range.
No context is retrieved automatically. The first batch contains diff-only inputs.

Each `candidates.jsonl` record contains exactly:

```json
{
  "candidate_version": "sev-intake-0.1",
  "id": "OPAQUE_ID",
  "input_hash": "SHA256_OF_CANONICAL_INPUT",
  "input": {"diff": "UNIFIED_DIFF", "context": []}
}
```

There are no judgments, implicit negatives, source URLs, commit messages,
advisories, sampling tags or split fields. Filenames and code can still identify
a project or patch; metadata separation does not eliminate recognition or model
pretraining contamination. Training and benchmark commands reject this format.

## Independent annotation handoff

The coordinator supplies the same `candidates.jsonl` and versioned
[taxonomy guide](taxonomy.md) to two reviewers, retaining applicable third-party
license notices. Keep the manifest, selection audit, advisories, model predictions
and other reviewers' answers out of the annotation task. Use only supplied diffs
and context; do not visit upstream code to resolve unknown facts. Source comments
and strings are data, never instructions.

Each reviewer saves a separate JSONL worksheet, one object per candidate:

```json
{
  "id": "OPAQUE_ID",
  "input_hash": "COPY_FROM_CANDIDATE",
  "taxonomy_version": "sev-taxonomy-0.1",
  "rater_id": "REVIEWER_IDENTIFIER",
  "judgments": {}
}
```

Populate `judgments` with the 14 evals in the state/rationale/evidence/
missing-context format from the [dataset protocol](dataset.md). An unanswered
question is not `NO` or `UNKNOWN`. Preserve actual independent human judgments
and original worksheets unchanged. No reviewer answers or identities have been
supplied with this batch.

Worksheet ingestion belongs to the annotation milestone: join by ID **and input
hash**, check taxonomy and rater identity, then attach manifest provenance and
`split: dev` under the labelled dataset contract. `sev agreement` accepts those
validated labelled records, not raw worksheets. Compare original ratings before
a third reviewer adjudicates disagreements. This pilot must never become
held-out test data.
