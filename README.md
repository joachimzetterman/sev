# sev

**sev is an open security evaluation model built to run on every engineering change.**

That is the project hypothesis. This repository currently contains a research
prototype, **not a trained sev model or a security gate**. The first milestone is
to determine whether small models make useful contextual security judgments over
diffs at a worthwhile quality, latency and cost.

The name means security eval / `security_eval()`, with architectural inspiration
from the jev → kev → sev lineage. [Kev](https://github.com/jaredpalmer/kev) is a
starting hypothesis; simpler classifiers and ordinary prompted models remain contenders.

## Start the experiment

Use Python 3.11+ and [uv](https://docs.astral.sh/uv/):

```sh
uv sync --locked
uv run sev taxonomy
uv run sev validate data/smoke.jsonl
uv run python -m unittest discover -s tests -v
uv run sev bench data/smoke.jsonl --split smoke --backend rules --out artifacts/rules
git diff | uv run sev --backend rules
uv run sev diff --staged --backend rules
```

The `rules` backend is an intentionally weak lexical comparison, not Semgrep or
a security model. A null distribution is an explicit abstention. One-hot rule
indicators are not estimated probabilities. The CLI is experiment plumbing;
there is no default model and no pass/fail security exit code.

[GitHub Actions](.github/workflows/ci.yml) runs the contract tests, dataset
validation, rules smoke experiment and package build on Python 3.11 and 3.13.
CI uses standard Ubuntu CPU runners with a five-minute timeout per job, cancels
superseded runs, and runs on pull requests and pushes to `main` to avoid duplicate
branch/PR runs. It downloads no models, starts no cloud inference, and uploads no
caches or artifacts.

For a local ordinary language-model baseline on Apple Silicon:

```sh
uv sync --locked --extra mlx
uv run --extra mlx python scripts/download_small_model.py --out artifacts/small-model.json
uv run --extra mlx sev bench data/smoke.jsonl --split smoke --backend mlx \
  --model /path/to/downloaded/snapshot --repeats 3 --out artifacts/small
```

The download script reports the pinned snapshot path. Subsequent evaluations use
only that local path and can run offline. The optional MLX dependency is specific
to Apple Silicon; HTTP model runners and the rest of the harness are portable.

For a general-purpose model served by a compatible chat-completion endpoint:

```sh
uv run sev bench data/smoke.jsonl --split smoke --backend chat \
  --endpoint http://127.0.0.1:8000 --model MODEL_ID --revision IMMUTABLE_REVISION \
  --out artifacts/general
```

Use `SEV_API_KEY` if the endpoint needs authentication. Sending input outside
loopback requires an explicit HTTPS endpoint and `--allow-remote`. No hosted
inference account is required for local use. An existing local Kev server can be
compared with `--backend kev --endpoint http://127.0.0.1:8009` and its model/revision.

## What is here

- [Agent contributor guidance](AGENTS.md): research scope, experiment contracts and validation commands.
- [Kev architecture investigation](docs/kev.md): exact source revision, shared context, pointer readout, hybrid-backbone caveats and required security adaptations.
- [Taxonomy and annotation guide](docs/taxonomy.md): 14 evals, definitions and four kinds of examples per eval.
- [Dataset design and candidate sources](docs/dataset.md): provenance, annotation, hard negatives and contamination controls.
- [Experiment protocol](docs/experiment.md): baselines, metrics, calibration, cost, hardware matrix and falsification criteria.
- [Measured results and limitations](docs/results.md): distinguishes executed runs from planned comparisons.

The authored smoke set is provisional, partially labeled, public development
material. It is neither a held-out benchmark nor training data. Missing labels
are not negatives. No claim about model usefulness follows from passing it.

Once independent training/development data exists, compare the simple classifier:

```sh
uv run sev fit-nb data/train.jsonl --out artifacts/nb.json
uv run sev bench data/dev.jsonl --split dev --backend nb \
  --model artifacts/nb.json --out artifacts/nb-dev
```

`fit-nb` rejects every non-training split. Evaluation checks the fitted artifact's
training projects, families and input hashes for overlap.

Output contains distributions over `YES`, `NO`, `UNKNOWN` and
`INSUFFICIENT_CONTEXT` for each requested eval. Relevance is not vulnerability;
`NO` is not proof of security. Review routing remains a separate policy decision.

No source code is executed, no repository context is retrieved automatically,
and no external model is contacted unless its backend is selected. Reports
contain model/configuration fingerprints and input hashes, not raw source text.

## Scope

This is `git diff → security evals`. There is no dashboard, SaaS control plane,
retrieval agent, compliance claim or specialised training pipeline yet. Static
tools remain complementary. The runtime and experiment code use Apache-2.0;
external examples, model weights and model runtimes retain their own licenses.
No European backbone-provenance claim is made.
