"""Explicit, pinned, optional download; inference never downloads implicitly."""

import argparse
import json
from pathlib import Path

from huggingface_hub import snapshot_download

MODEL = "mlx-community/Qwen3-0.6B-4bit"
REVISION = "73e3e38d981303bc594367cd910ea6eb48349da8"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("manifest already exists")
    path = snapshot_download(MODEL, revision=REVISION)
    manifest = {"model": MODEL, "revision": REVISION, "path": path,
                "upstream_base": "Qwen/Qwen3-0.6B", "quantization": "MLX 4-bit"}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
