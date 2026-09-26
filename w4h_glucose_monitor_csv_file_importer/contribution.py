"""Load contribution.yaml and resolve automated / live sample files."""

from pathlib import Path

import yaml

_PKG_ROOT = Path(__file__).resolve().parent.parent


def load_contribution(root: Path | None = None) -> dict:
    path = (root or _PKG_ROOT) / "contribution.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"contribution.yaml not found at {path}")
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError("contribution.yaml must be a mapping")
    return doc


def _fixture_paths(spec: dict, root: Path) -> list[Path]:
    folder = (root / spec.get("path", "tests/fixtures")).resolve()
    named = spec.get("files")
    if named:
        paths = []
        for rel in named:
            p = Path(rel)
            candidate = p if p.is_absolute() else (folder / p)
            if not candidate.is_file():
                candidate = root / rel
            paths.append(candidate.resolve())
    else:
        paths = sorted(folder.glob("*.csv"))
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        raise FileNotFoundError("Fixture CSVs not found:\n  " + "\n  ".join(missing))
    if not paths:
        raise FileNotFoundError(f"No CSV fixtures under {folder}")
    return paths


def _sibling_paths(spec: dict, root: Path) -> list[Path] | None:
    repo = spec.get("repo")
    files = spec.get("files") or []
    if not repo or not files:
        return None
    sibling = (root.parent / repo).resolve()
    paths = [(sibling / rel).resolve() for rel in files]
    if all(p.is_file() for p in paths):
        return paths
    return None


def automated_sample_paths(root: Path | None = None) -> list[Path]:
    """Tiny in-repo fixtures for pytest (no network, no sibling checkout)."""
    pkg = root or _PKG_ROOT
    spec = (load_contribution(pkg).get("tests") or {}).get("automated") or {}
    sample = spec.get("sample") or {"kind": "fixtures", "path": "tests/fixtures"}
    if sample.get("kind") != "fixtures":
        raise ValueError("tests.automated.sample.kind must be 'fixtures'")
    return _fixture_paths(sample, pkg)


def live_sample_paths(root: Path | None = None) -> tuple[str, list[Path]]:
    """Files for in-app Run / ./run.sh.

    Prefers the sibling W4H sample repo declared in yaml; falls back to
    in-repo fixtures when that checkout is missing.
    """
    pkg = root or _PKG_ROOT
    spec = ((load_contribution(pkg).get("tests") or {}).get("live") or {}).get("sample") or {}
    kind = spec.get("kind")
    if kind == "sibling":
        paths = _sibling_paths(spec, pkg)
        if paths:
            return spec["repo"], paths
        fallback = spec.get("fallback") or {"kind": "fixtures", "path": "tests/fixtures"}
        if fallback.get("kind") == "fixtures":
            return "fixtures", _fixture_paths(fallback, pkg)
        raise FileNotFoundError(
            f"Sibling sample {spec.get('repo')!r} not found — clone it next to this repo, "
            "or keep tests/fixtures as fallback."
        )
    if kind == "fixtures":
        return "fixtures", _fixture_paths(spec, pkg)
    raise ValueError("tests.live.sample.kind must be 'sibling' or 'fixtures'")
