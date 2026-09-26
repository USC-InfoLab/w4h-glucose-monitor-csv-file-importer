"""CLI entry: w4h-glucose-monitor-csv-file-import

  plan      profile CSVs (contribution.yaml live sample, or --data-dir)
  validate  re-check a reviewed manifest.yaml next to --data-dir
  import    load every CSV
  sync      append one CSV for one signal
"""

import argparse
import sys
from pathlib import Path

from .client import W4HClient
from .config import dataset_id as env_dataset_id
from .contribution import live_sample_paths
from .csv_import import import_all, import_signal
from .manifest import load_manifest, signal_by_slug, write_manifest, write_plan
from .mapping import plan_directory, plan_files
from .reconcile import reconcile_manifest


def _check(manifest: dict) -> dict:
    review = reconcile_manifest(manifest)
    if review["errors"]:
        raise SystemExit("Mapping has errors — fix manifest.yaml and re-run:\n  " + "\n  ".join(review["errors"]))
    return review


def _print_plan(manifest: dict, review: dict) -> None:
    for sig in manifest["signals"]:
        m = sig["geomts_mapping"]
        print(f"{sig['slug']}: subject={m['subject']} time={m['time']} values={[v['name'] for v in m['values']]}")
    for c in review["corrections"]:
        print(f"corrected {c['signal_slug']} {c['field']}: {c['reason']}")
    for e in review["errors"]:
        print(f"ERROR {e}")


def _resolve_sources(args) -> tuple[Path, dict, bool]:
    """Return (data_dir, planned_manifest_or_None, write_sidecar).

    Default: contribution.yaml live sample, planned in memory (in-app Run).
    --data-dir: that folder + reviewed-manifest flow.
    """
    if getattr(args, "data_dir", None):
        return Path(args.data_dir).resolve(), None, True
    source, paths = live_sample_paths()
    print(f"Using live sample from contribution.yaml ({source}):")
    for p in paths:
        print(f"  {p}")
    return paths[0].parent, plan_files(paths), False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import glucose-monitor CSV files into W4H (API key from .env or in-app Run)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p, needs_dataset=True):
        if needs_dataset:
            p.add_argument("--dataset-id", default=env_dataset_id(), help="Target catalog dataset id")
        p.add_argument("--data-dir", help="Optional folder of CSVs (default: contribution.yaml live sample)")

    common(sub.add_parser("plan", help="Build a draft mapping for review"), False)
    common(sub.add_parser("validate", help="Re-check manifest.yaml in --data-dir"), False)
    p_import = sub.add_parser("import", help="Load every CSV")
    common(p_import)
    p_import.add_argument("--mode", choices=["replace", "append"], default="append")
    p_sync = sub.add_parser("sync", help="Append one CSV for one signal")
    common(p_sync)
    p_sync.add_argument("--signal", required=True, help="Signal slug")
    p_sync.add_argument("--file", help="CSV path (default: the manifest's file for the signal)")

    args = parser.parse_args(argv)
    data_dir, planned, write_sidecar = _resolve_sources(args)

    if args.command == "plan":
        manifest = planned if planned is not None else plan_directory(data_dir)
        review = reconcile_manifest(manifest)
        if write_sidecar:
            write_manifest(data_dir, manifest)
            write_plan(data_dir, manifest, review)
            dest = data_dir / "manifest.yaml"
        else:
            dest = "(not written — live sample is planned in memory)"
        _print_plan(manifest, review)
        print(f"Review {dest}, then run `import`.")
        return 1 if review["errors"] else 0

    if args.command == "validate":
        if planned is not None:
            parser.error("validate needs --data-dir pointing at a folder with manifest.yaml")
        manifest = load_manifest(data_dir)
        review = reconcile_manifest(manifest)
        write_manifest(data_dir, manifest)
        write_plan(data_dir, manifest, review)
        for c in review["corrections"]:
            print(f"corrected {c['signal_slug']} {c['field']}: {c['reason']}")
        for e in review["errors"]:
            print(f"ERROR {e}")
        print("manifest OK" if not review["errors"] else "manifest has errors")
        return 1 if review["errors"] else 0

    if not args.dataset_id:
        parser.error("--dataset-id is required (in-app Run passes it in the process environment)")
    manifest = planned if planned is not None else load_manifest(data_dir)
    _check(manifest)
    client = W4HClient()

    if args.command == "import":
        for r in import_all(client, args.dataset_id, manifest, data_dir, mode=args.mode):
            print(
                f"{r['signal']}: inserted={r['inserted']} skipped={r['skipped']} "
                f"→ {r.get('physical_schema')}.{r.get('physical_table')}"
            )
        return 0

    signal = signal_by_slug(manifest, args.signal)
    csv_path = Path(args.file).resolve() if args.file else None
    r = import_signal(client, args.dataset_id, signal, data_dir, mode="append", csv_path=csv_path)
    print(f"sync {r['signal']}: inserted={r['inserted']} skipped={r['skipped']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
