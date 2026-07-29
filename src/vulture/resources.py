from __future__ import annotations

from pathlib import Path


RESOURCE_ROOT = Path(__file__).resolve().parent / "resources"


def resource_path(*parts: str) -> Path:
    path = RESOURCE_ROOT.joinpath(*parts)
    if not path.exists():
        raise FileNotFoundError(f"Bundled resource is missing: {path}")
    return path
