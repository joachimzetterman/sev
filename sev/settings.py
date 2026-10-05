"""User-owned inference settings; never discover configuration in a repository."""

import os
from pathlib import Path

from .backends import HTTP, MLX, Rules
from .classifier import NaiveBayes
from .contracts import dumps, loads

BACKENDS = ("rules", "nb", "mlx", "chat", "kev")
DEFAULTS = {"backend": None, "model": None, "revision": None,
            "endpoint": "http://127.0.0.1:8000", "allow_remote": False}


def config_path(path=None):
    if path is not None:
        return Path(path).expanduser()
    if os.environ.get("SEV_CONFIG"):
        return Path(os.environ["SEV_CONFIG"]).expanduser()
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "sev/config.json"


def validate_settings(settings):
    if not isinstance(settings, dict) or set(settings) != set(DEFAULTS):
        raise ValueError("invalid sev configuration fields; API keys belong in SEV_API_KEY")
    if settings["backend"] not in BACKENDS:
        raise ValueError("choose a backend with sev configure --backend, or pass --backend for this call")
    for field in ("model", "revision", "endpoint"):
        if settings[field] is not None and (not isinstance(settings[field], str) or not settings[field].strip()):
            raise ValueError(f"invalid configuration field: {field}")
    if type(settings["allow_remote"]) is not bool:
        raise ValueError("allow_remote must be a boolean")
    if settings["backend"] in ("mlx", "nb") and not settings["model"]:
        raise ValueError("local inference requires --model with a local path")
    if settings["backend"] in ("chat", "kev"):
        # Validates the endpoint and consent without loading a model or making a request.
        HTTP(settings["endpoint"], settings["model"], settings["revision"], settings["allow_remote"])
    return settings


def load_settings(path=None):
    path = config_path(path)
    if not path.exists():
        raise ValueError("no sev configuration; run sev configure --backend ... or pass --backend for this call")
    document = loads(path.read_text())
    if not isinstance(document, dict) or set(document) != {"version", "inference"} or document["version"] != 1:
        raise ValueError("unsupported sev configuration")
    return validate_settings(document["inference"])


def resolve_settings(overrides, path=None):
    # An explicit backend is a complete one-off selection, independent of saved credentials/consent.
    saved = DEFAULTS.copy() if overrides.get("backend") is not None else load_settings(path).copy()
    if overrides.get("endpoint") is not None and overrides["endpoint"] != saved["endpoint"]:
        saved["allow_remote"] = False  # Saved consent applies only to the saved endpoint.
    saved.update({key: value for key, value in overrides.items() if value is not None})
    return validate_settings(saved)


def save_settings(settings, path=None, force=False):
    settings = validate_settings(settings.copy())
    if settings["backend"] in ("mlx", "nb"):
        model = Path(settings["model"]).expanduser().resolve()
        if not (model.is_dir() if settings["backend"] == "mlx" else model.is_file()):
            raise ValueError("local model path does not exist")
        settings["model"] = str(model)
    path = config_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # O_EXCL prevents an accidental overwrite, including symlinks, without explicit --force.
    flags = os.O_WRONLY | os.O_CREAT | (os.O_TRUNC if force else os.O_EXCL)
    with os.fdopen(os.open(path, flags, 0o600), "w") as stream:
        stream.write(dumps({"version": 1, "inference": settings}) + "\n")
    return path


def create_backend(settings):
    settings = validate_settings(settings)
    if settings["backend"] == "rules":
        return Rules()
    if settings["backend"] == "nb":
        return NaiveBayes(settings["model"])
    if settings["backend"] == "mlx":
        return MLX(settings["model"])
    return HTTP(settings["endpoint"], settings["model"], settings["revision"], settings["allow_remote"],
                kev=settings["backend"] == "kev")
