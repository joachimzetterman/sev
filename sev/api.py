"""The small embeddable security_eval() interface, shared with the CLI."""

from .contracts import SCHEMA_VERSION, decision, digest, validate_input, validate_prediction
from .settings import create_backend, load_settings
from .taxonomy import VERSION, select


def security_eval(change, questions=None, *, context=None, backend=None, config=None):
    """Evaluate supplied text only. Pass a reusable backend to avoid repeated model loading."""
    value = validate_input({"diff": change, "context": [] if context is None else context})
    names = list(select(questions))
    if backend is not None and config is not None:
        raise ValueError("choose backend or config, not both")
    if backend is None:
        backend = create_backend(load_settings(config))
    prediction, stats = backend.predict(value, names)
    return {"schema_version": SCHEMA_VERSION, "taxonomy_version": VERSION, "input_hash": digest(value),
            "model": backend.metadata, "judgments": validate_prediction(prediction, names), "usage": stats}


def render_text(result):
    rows = []
    for name, judgment in result["judgments"].items():
        probabilities = judgment["probabilities"]
        state = "ABSTAIN" if probabilities is None else decision(probabilities)
        rows.append(f"{name:<36} {state}")
    rows.append(f"\nModel: {result['model']['model']} | experimental judgments, not a security verdict")
    return "\n".join(rows)
