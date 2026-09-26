"""Read/write the manifest.yaml that lives next to the user's CSV files."""

import json
from pathlib import Path

import yaml

MANIFEST_NAME = "manifest.yaml"
PLAN_NAME = "plan.json"  # manifest + review diff, for the in-app mapping review


def load_manifest(data_dir: Path) -> dict:
    path = Path(data_dir) / MANIFEST_NAME
    if not path.is_file():
        raise FileNotFoundError(
            f"{MANIFEST_NAME} not found at {path} — run `plan` first and review the mapping"
        )
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def write_manifest(data_dir: Path, manifest: dict) -> Path:
    path = Path(data_dir) / MANIFEST_NAME
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(manifest, f, sort_keys=False, allow_unicode=True)
    return path


def write_plan(data_dir: Path, manifest: dict, review: dict) -> Path:
    path = Path(data_dir) / PLAN_NAME
    path.write_text(json.dumps({"manifest": manifest, "review": review}, indent=2), encoding="utf-8")
    return path


def signal_by_slug(manifest: dict, slug: str) -> dict:
    for sig in manifest.get("signals", []):
        if sig.get("slug") == slug:
            return sig
    raise KeyError(f"Unknown signal slug: {slug}")
