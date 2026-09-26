"""Glucose-monitor column descriptions. Fills empty fields only."""

from .shapes import canonicalize_header

TITLE = "Glucose monitor CSV import"
DESCRIPTION = (
    "Dexcom Clarity or FreeStyle Libre CSV mapped from public export layouts. "
    "Review each signal before importing. Kaggle samples are cited in the README; "
    "this package does not ship those files."
)

# Keyed by matched shape, then by canonical physical column name.
SHAPES: dict[str, dict] = {
    "dexcom_clarity": {
        "description": (
            "Dexcom Clarity estimated glucose values (Event Type EGV), 5-minute samples. "
            "Layout from the Kaggle Dexcom sensor export."
        ),
        "source_url": "https://www.kaggle.com/datasets/mauddib/dexcom-sensor-data",
        "sampling_interval": "5min",
        "columns": {
            "subjectid": {"description": "Wearer id. Native Clarity files are one person per file; the importer fills this from the file name when the column is absent."},
            "timestamp": {"description": "Reading time from the Clarity timestamp column."},
            "glucosemgdl": {"description": "Estimated glucose value.", "unit": "mg/dL"},
            "glucosemmol": {"description": "Estimated glucose value.", "unit": "mmol/L"},
            "insulinu": {"description": "Insulin recorded on this row, when present.", "unit": "U"},
            "carbg": {"description": "Carbohydrates recorded on this row, when present.", "unit": "g"},
            "eventtype": {"description": "Clarity event type. Import keeps EGV rows."},
            "deviceinfo": {"description": "Reporting app / device, e.g. a Dexcom G7 mobile app."},
        },
        "values": {
            "glucosemgdl": {"name": "glucose_mg_dl", "description": "Estimated glucose value", "unit": "mg/dL"},
            "glucosemmol": {"name": "glucose_mmol", "description": "Estimated glucose value", "unit": "mmol/L"},
            "insulinu": {"name": "insulin_u", "description": "Insulin on this reading", "unit": "U"},
            "carbg": {"name": "carb_g", "description": "Carbohydrates on this reading", "unit": "g"},
        },
    },
    "freestyle_libre": {
        "description": (
            "FreeStyle LibreLink historic (15 min) and scan glucose. "
            "Layout from the Kaggle LibreLink glucose-readings export."
        ),
        "source_url": "https://www.kaggle.com/datasets/reneelinmedical/glucose-readings-from-cgm",
        "sampling_interval": "15min",
        "columns": {
            "serialnumber": {"description": "Device serial. Used as the wearer id for a single-patient Libre export."},
            "devicetimestamp": {"description": "Device timestamp of the record."},
            "historicglucosemmol": {"description": "Historic interstitial glucose.", "unit": "mmol/L"},
            "historicglucosemgdl": {"description": "Historic interstitial glucose.", "unit": "mg/dL"},
            "scanglucosemmol": {"description": "Scan glucose.", "unit": "mmol/L"},
            "scanglucosemgdl": {"description": "Scan glucose.", "unit": "mg/dL"},
            "carbg": {"description": "Carbohydrates logged on this row, when present.", "unit": "g"},
            "rapidinsulinu": {"description": "Rapid-acting insulin logged on this row, when present.", "unit": "U"},
            "device": {"description": "Export source app, typically FreeStyle LibreLink."},
            "recordtype": {"description": "Libre record type (historic vs scan)."},
        },
        "values": {
            "historicglucosemmol": {"name": "historic_glucose_mmol", "description": "Historic interstitial glucose", "unit": "mmol/L"},
            "historicglucosemgdl": {"name": "historic_glucose_mg_dl", "description": "Historic interstitial glucose", "unit": "mg/dL"},
            "scanglucosemmol": {"name": "scan_glucose_mmol", "description": "Scan glucose", "unit": "mmol/L"},
            "scanglucosemgdl": {"name": "scan_glucose_mg_dl", "description": "Scan glucose", "unit": "mg/dL"},
            "carbg": {"name": "carb_g", "description": "Carbohydrates on this row", "unit": "g"},
            "rapidinsulinu": {"name": "rapid_insulin_u", "description": "Rapid-acting insulin on this row", "unit": "U"},
        },
    },
}


def _signal_def(signal: dict) -> dict:
    return SHAPES.get(signal.get("matched_shape") or "") or {}


def apply_catalog(manifest: dict) -> None:
    """Fill empty title/description/units from the catalog, in place."""
    if not manifest.get("title"):
        manifest["title"] = TITLE
    if not manifest.get("description"):
        manifest["description"] = DESCRIPTION
    for signal in manifest.get("signals", []):
        sdef = _signal_def(signal)
        for key in ("description", "source_url", "sampling_interval"):
            if not signal.get(key) and sdef.get(key):
                signal[key] = sdef[key]
        for col in signal.get("columns", []):
            canon = canonicalize_header(col["name"])
            meta = sdef.get("columns", {}).get(canon)
            if not meta:
                continue
            if not col.get("description") and meta.get("description"):
                col["description"] = meta["description"]
            if not col.get("unit") and meta.get("unit"):
                col["unit"] = meta["unit"]
        for v in signal.get("geomts_mapping", {}).get("values") or []:
            meta = sdef.get("values", {}).get(canonicalize_header(v["source"]))
            if not meta:
                continue
            if meta.get("name") and v.get("name") == v.get("source"):
                v["name"] = meta["name"]
            if not v.get("description") and meta.get("description"):
                v["description"] = meta["description"]
            if not v.get("unit") and meta.get("unit"):
                v["unit"] = meta["unit"]
