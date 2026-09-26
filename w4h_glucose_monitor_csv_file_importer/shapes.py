"""Known glucose-monitor CSV layouts.

Column sets are taken from public Kaggle exports (do not vendor those files;
they can contain real names and serials). A file matches when its canonical
headers cover >= SHAPE_MIN_OVERLAP of a core set and include a glucose column.

- dexcom_clarity: Dexcom Clarity CSV
  https://www.kaggle.com/datasets/mauddib/dexcom-sensor-data
- freestyle_libre: Abbott FreeStyle LibreLink patient CSV
  https://www.kaggle.com/datasets/reneelinmedical/glucose-readings-from-cgm
"""

import re

SHAPE_MIN_OVERLAP = 0.9

# Physical column names the ingest API accepts (sql identifiers). Keyed by
# canonical header. Unlisted unsafe headers are snake-cased in mapping.py.
PREFERRED_COLUMNS = {
    "index": "index",
    "timestampyyyymmddthhmmss": "timestamp",
    "eventtype": "event_type",
    "eventsubtype": "event_subtype",
    "patientinfo": "patient_info",
    "deviceinfo": "device_info",
    "sourcedeviceid": "source_device_id",
    "glucosevaluemgdl": "glucose_mg_dl",
    "glucosevaluemmoll": "glucose_mmol",
    "insulinvalueu": "insulin_u",
    "carbvaluegrams": "carb_g",
    "durationhhmmss": "duration",
    "glucoserateofchangemgdlmin": "glucose_rate_mg_dl_min",
    "glucoserateofchangemmollmin": "glucose_rate_mmol_min",
    "transmittertimelonginteger": "transmitter_time",
    "transmitterid": "transmitter_id",
    "device": "device",
    "serialnumber": "serial_number",
    "devicetimestamp": "device_timestamp",
    "recordtype": "record_type",
    "historicglucosemgdl": "historic_glucose_mg_dl",
    "historicglucosemmoll": "historic_glucose_mmol",
    "scanglucosemgdl": "scan_glucose_mg_dl",
    "scanglucosemmoll": "scan_glucose_mmol",
    "nonnumericrapidactinginsulin": "rapid_insulin_note",
    "rapidactinginsulinunits": "rapid_insulin_u",
    "nonnumericfood": "food_note",
    "carbohydratesgrams": "carb_g",
    "carbohydratesservings": "carb_servings",
    "subjectid": "subject_id",
    "subject": "subject_id",
}

# First match wins, before the generic "id" regex. Serial number is the Libre wearer proxy.
SUBJECT_CANON = ("subjectid", "participantid", "id", "serialnumber")

# Not a wearer id even though the header contains "id" or "patient".
NOT_SUBJECT = {
    "patientinfo",
    "sourcedeviceid",
    "deviceinfo",
    "transmitterid",
    "index",
    "recordtype",
}

# Numeric columns that are not measurements.
NOT_VALUES = {"index", "recordtype", "transmittertimelonginteger", "label"}

_GLUCOSE = {
    "glucosevaluemgdl",
    "glucosevaluemmoll",
    "historicglucosemgdl",
    "historicglucosemmoll",
    "scanglucosemgdl",
    "scanglucosemmoll",
}

SHAPES: dict[str, dict] = {
    "dexcom_clarity": {
        "columns": {
            "index",
            "timestampyyyymmddthhmmss",
            "eventtype",
            "eventsubtype",
            "patientinfo",
            "deviceinfo",
            "sourcedeviceid",
            "insulinvalueu",
            "carbvaluegrams",
        },
        "any": {"glucosevaluemgdl", "glucosevaluemmoll"},
    },
    "freestyle_libre": {
        "columns": {
            "device",
            "serialnumber",
            "devicetimestamp",
            "recordtype",
            "rapidactinginsulinunits",
            "carbohydratesgrams",
        },
        "any": {
            "historicglucosemgdl",
            "historicglucosemmoll",
            "scanglucosemgdl",
            "scanglucosemmoll",
        },
    },
}


def canonicalize_header(header: str) -> str:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(header or ""))
    return re.sub(r"[^a-z0-9]+", "", spaced.lower())


def _canon_set(headers: list[str]) -> set[str]:
    return {canonicalize_header(h) for h in headers}


def matched_shape(headers: list[str]) -> str | None:
    """Most specific core-set match that also has a glucose column."""
    canon = _canon_set(headers)
    best = None
    best_n = 0
    for name, spec in SHAPES.items():
        cols = spec["columns"]
        n = len(cols & canon)
        if n / len(cols) < SHAPE_MIN_OVERLAP:
            continue
        if spec.get("any") and not (spec["any"] & canon):
            continue
        if n > best_n:
            best, best_n = name, n
    return best


def _is_dexcom(headers: list[str]) -> bool:
    canon = _canon_set(headers)
    return "eventtype" in canon and "timestampyyyymmddthhmmss" in canon


def _is_libre(headers: list[str]) -> bool:
    canon = _canon_set(headers)
    return "serialnumber" in canon and "devicetimestamp" in canon


def keep_row(headers: list[str], cells: list[str]) -> bool:
    """Drop Clarity preamble / non-EGV events, and Libre rows with no glucose.

    Clarity files mix device metadata and alerts into the same CSV. Only EGV
    (estimated glucose value) rows are the glucose time series. Libre historic
    and scan readings both count; note rows with an empty glucose cell do not.
    """
    if not cells or not any(str(c).strip() for c in cells):
        return False
    canon = [canonicalize_header(h) for h in headers]

    if _is_dexcom(headers) and "eventtype" in canon:
        i = canon.index("eventtype")
        event = cells[i].strip().upper() if i < len(cells) else ""
        return event == "EGV"

    if _is_libre(headers):
        glucose_at = [
            i
            for i, c in enumerate(canon)
            if c.startswith("historicglucose") or c.startswith("scanglucose") or c.startswith("glucosevalue")
        ]
        if glucose_at:
            return any(i < len(cells) and str(cells[i]).strip() for i in glucose_at)
    return True
