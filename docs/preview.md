# Developer preview

This release makes the existing inference backends usable from a terminal or
Python application. It does not ship a trained sev checkpoint. Its purpose is to
learn whether these judgments help during real development, while the independent
dataset and model comparisons continue separately.

## Install and configure once

From this repository, using Python 3.11+ and uv:

```sh
uv tool install .
sev --version
```

If you already run a local server implementing `/v1/chat/completions`, configure
its model ID and the model revision that server actually serves:

```sh
sev configure --backend chat --endpoint http://127.0.0.1:8000 \
  --model MODEL_ID --revision MODEL_REVISION
```

The server must support JSON-object responses and the existing chat-completion
request contract. `MODEL_ID` and `MODEL_REVISION` are placeholders, not downloads
or model recommendations. The revision is recorded as operator supplied; sev
cannot verify what a remote server actually loaded.

For a local MLX model on Apple Silicon, install the optional runtime and point at
an already downloaded snapshot directory:

```sh
uv tool install --force '.[mlx]'
sev configure --backend mlx --model /absolute/path/to/model/snapshot
```

Configuration does not download, load or contact a model. It saves settings in
`$XDG_CONFIG_HOME/sev/config.json`, or `~/.config/sev/config.json` when unset.
Use `--force` to replace existing settings. Local model paths become absolute,
so evaluation works from other repositories. `SEV_CONFIG` or `--config PATH`
selects another file. Repository configuration is never discovered automatically.

There is deliberately no bundled default checkpoint: the measured 0.6B baseline
performed poorly on the small smoke set. See [the results](results.md). Choosing
another model does not establish its security judgment quality either.

## Evaluate a change

```sh
git diff | sev
sev diff --staged
sev diff --base origin/main
sev eval change.diff --json
sev diff --context snippets.json --evals AUTHORIZATION_RELEVANT,PRIVILEGE_INCREASE
```

`diff` evaluates unstaged tracked changes by default. `--staged` compares the
index to HEAD. `--base` evaluates committed branch changes from the common
ancestor of that revision and HEAD; it excludes uncommitted edits. Fetch the base
branch yourself if needed. Untracked files are not implicitly included.

Terminal output shows each judgment as `YES`, `NO`, `UNKNOWN`,
`INSUFFICIENT_CONTEXT`, or algorithmic `ABSTAIN`. It omits confidence percentages.
Redirected/piped output is JSON; `--json` and `--text` select a format explicitly.
JSON retains the existing envelope, raw uncalibrated distributions, model
provenance and input hash. Exit 0 means evaluation completed, never "secure".
Empty or oversized input and malformed model responses fail explicitly.

An explicit `--backend` selects a complete one-off configuration without loading
saved model or endpoint settings. Other evaluation flags override saved settings.
Benchmarks still require explicit `--backend` and do not use saved defaults.

To try the command plumbing without any model or network:

```sh
sev eval data/example.diff --backend rules --text
```

Use your own diff file in place of `data/example.diff`. Rules are a lexical
diagnostic backend and usually abstain; this is not the contextual model.

## Python

```python
from sev import security_eval

result = security_eval(diff_text, questions=["AUTHORIZATION_RELEVANT", "PRIVILEGE_INCREASE"])
```

The function uses your saved configuration. Optional `context` accepts the same
explicit path/content objects as the CLI. Optional `config` selects a settings
file. For repeated calls, supply a reusable backend with `backend=` to avoid
reloading a local model. The function evaluates only supplied text and returns
the same JSON-compatible envelope as the CLI; it does not invoke Git or retrieve
repository context.

## Explicit remote inference

Configure an HTTPS server with `--allow-remote` to authorize sending future diffs
to that endpoint. If authentication is required, set `SEV_API_KEY` in your process
environment; credentials are never stored in sev's configuration. Changing the
endpoint on an evaluation requires fresh `--allow-remote` consent. No redirects
are followed and no provider error body is printed.

There is no mandatory remote service, telemetry, model download, cloud deployment
or inference fallback. Local inference stays local unless you select a remote
backend. Preview validation covers contracts, CLI/SDK agreement and a local HTTP
fixture; it is not a new real-model quality or latency measurement.
