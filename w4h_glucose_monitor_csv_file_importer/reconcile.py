"""Deterministic validation + auto-correction of a mapping manifest.

Ported from w4h-api's reconcileManifest() (six checks). Returns
{errors, corrections, notes}: errors block an import; corrections are fixes already
applied to the manifest but reported as a proposed -> corrected diff so the reviewer
sees exactly what changed; notes are FYI.
"""

import re

# Type names the ingest endpoint understands (PG_TYPE_MAP keys in lib/ingest-csv.js).
PG_TYPES = {"text", "string", "integer", "int", "bigint", "double", "float", "double precision",
            "numeric", "boolean", "date", "timestamp"}
_TYPE_SYNONYMS = {"timestamp with time zone": "timestamp", "timestamptz": "timestamp", "time": "text"}
_DATE_NAME_RE = re.compile(r"^date$", re.I)
_TIME_NAME_RE = re.compile(r"^(time|timestamp)$", re.I)


def _structural(manifest: dict, errors: list, notes: list) -> None:
    if not isinstance(manifest, dict):
        errors.append("manifest: not a mapping")
        return
    if not manifest.get("vendor"):
        errors.append("manifest: vendor is required (string)")
    signals = manifest.get("signals")
    if not isinstance(signals, list) or not signals:
        errors.append("manifest: signals must be a non-empty array")
        return
    seen = set()
    for i, sig in enumerate(signals):
        label = f"signal[{i}] '{sig.get('slug')}'"
        if not sig.get("slug"):
            errors.append(f"manifest: {label}: slug is required")
        elif sig["slug"] in seen:
            errors.append(f"manifest: {label}: duplicate slug")
        else:
            seen.add(sig["slug"])
        if not sig.get("file"):
            errors.append(f"manifest: {label}: file is required")
        if not sig.get("columns"):
            errors.append(f"manifest: {label}: columns must be a non-empty array")
        mapping = sig.get("geomts_mapping")
        if not isinstance(mapping, dict):
            errors.append(f"manifest: {label}: geomts_mapping is required")
        elif not mapping.get("subject"):
            errors.append(f"manifest: {label}: geomts_mapping.subject is required (no id-like column found)")
        else:
            names = {c.get("name") for c in sig.get("columns", [])}
            for j, v in enumerate(mapping.get("values") or []):
                if v.get("source") and v["source"] not in names:
                    notes.append(f"manifest: {label}: values[{j}].source '{v['source']}' has no matching column")


def _column_types(manifest, notes, errors):
    for sig in manifest["signals"]:
        for col in sig.get("columns", []):
            raw = str(col.get("type", "")).strip()
            low = raw.lower()
            if low in PG_TYPES:
                continue
            if low in _TYPE_SYNONYMS:
                notes.append(f"{sig['slug']}: column \"{col['name']}\" type \"{raw}\" corrected to \"{_TYPE_SYNONYMS[low]}\"")
                col["type"] = _TYPE_SYNONYMS[low]
            else:
                errors.append(f"{sig['slug']}: column \"{col['name']}\" has an unrecognized type \"{raw}\"")


def _time_mapping(manifest, corrections):
    """A date column + a separate time-of-day column MUST be combined (a bare time has no date)."""
    for sig in manifest["signals"]:
        mapping = sig.get("geomts_mapping")
        if not mapping:
            continue
        cols = sig.get("columns", [])
        date_col = next((c for c in cols if _DATE_NAME_RE.match(c["name"]) and str(c["type"]).lower() == "date"), None)
        time_col = next((c for c in cols if _TIME_NAME_RE.match(c["name"]) and c is not date_col), None)
        if not date_col or not time_col:
            continue
        combine = (mapping.get("time") or {}).get("combine") if isinstance(mapping.get("time"), dict) else None
        combined = isinstance(combine, list) and date_col["name"] in combine and time_col["name"] in combine
        if str(time_col["type"]).lower() == "timestamp":
            corrections.append({
                "signal_slug": sig["slug"], "field": f"columns[{time_col['name']}].type",
                "ai_value": "timestamp", "corrected_value": "text",
                "reason": f'"{time_col["name"]}" is combined with "{date_col["name"]}" for its date, so it can only hold a bare time-of-day.',
            })
            time_col["type"] = "text"
        if combined:
            continue
        new_time = {"combine": [date_col["name"], time_col["name"]]}
        corrections.append({
            "signal_slug": sig["slug"], "field": "geomts_mapping.time",
            "ai_value": mapping.get("time"), "corrected_value": new_time,
            "reason": f'"{date_col["name"]}" (date) and "{time_col["name"]}" (time-of-day) must be combined for correct ordering.',
        })
        mapping["time"] = new_time


def _dedupe(manifest, corrections):
    """Every combined time column must be in dedupe_columns or rows on different dates silently collide."""
    for sig in manifest["signals"]:
        time = (sig.get("geomts_mapping") or {}).get("time")
        combine = time.get("combine") if isinstance(time, dict) else None
        if not isinstance(combine, list) or len(combine) < 2:
            continue
        sig.setdefault("dedupe_columns", [])
        missing = [c for c in combine if c not in sig["dedupe_columns"]]
        if missing:
            corrections.append({
                "signal_slug": sig["slug"], "field": "dedupe_columns",
                "ai_value": list(sig["dedupe_columns"]), "corrected_value": [*sig["dedupe_columns"], *missing],
                "reason": f"Missing {missing} from the combined time mapping — rows with the same time-of-day on different dates would be dropped.",
            })
            sig["dedupe_columns"].extend(missing)


def _null_time_values(manifest, corrections):
    """A signal with no time axis cannot have per-timestamp values."""
    for sig in manifest["signals"]:
        mapping = sig.get("geomts_mapping")
        if mapping and mapping.get("time") is None and mapping.get("values"):
            corrections.append({
                "signal_slug": sig["slug"], "field": "geomts_mapping.values",
                "ai_value": mapping["values"], "corrected_value": [],
                "reason": "This signal has no time dimension (time: null), so it can't have per-timestamp values.",
            })
            mapping["values"] = []


def _column_references(manifest, errors):
    for sig in manifest["signals"]:
        names = {c.get("name") for c in sig.get("columns", [])}
        mapping = sig.get("geomts_mapping") or {}
        if mapping.get("subject") and mapping["subject"] not in names:
            errors.append(f"{sig['slug']}: geomts_mapping.subject \"{mapping['subject']}\" has no matching column")
        for dc in sig.get("dedupe_columns", []):
            if dc not in names:
                errors.append(f"{sig['slug']}: dedupe_columns references \"{dc}\" which has no matching column")
        time = mapping.get("time")
        refs = (time.get("combine") or [time.get("column")]) if isinstance(time, dict) else []
        for ref in refs:
            if ref and ref not in names:
                errors.append(f"{sig['slug']}: geomts_mapping.time references \"{ref}\" which has no matching column")


def reconcile_manifest(manifest: dict) -> dict:
    errors, corrections, notes = [], [], []
    _structural(manifest, errors, notes)
    signals = manifest.get("signals") if isinstance(manifest, dict) else None
    # The correction passes need well-formed signals; skip them if the structure is broken.
    if isinstance(signals, list) and signals and all(
        isinstance(s, dict) and s.get("slug") and s.get("columns") for s in signals
    ):
        _column_types(manifest, notes, errors)
        _time_mapping(manifest, corrections)
        _dedupe(manifest, corrections)
        _null_time_values(manifest, corrections)
        _column_references(manifest, errors)
    return {"errors": errors, "corrections": corrections, "notes": notes}
