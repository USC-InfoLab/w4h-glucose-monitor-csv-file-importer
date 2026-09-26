"""Unit tests for profiling, mapping, reconciliation and chunked import — no network."""

import json
import re
import shutil
from pathlib import Path

import pytest

from w4h_glucose_monitor_csv_file_importer.__main__ import main
from w4h_glucose_monitor_csv_file_importer.csv_import import CHUNK_SIZE, import_all, import_signal
from w4h_glucose_monitor_csv_file_importer.manifest import load_manifest
from w4h_glucose_monitor_csv_file_importer.mapping import plan_directory, plan_files, slug_from_filename
from w4h_glucose_monitor_csv_file_importer.profile import infer_type, profile_csv
from w4h_glucose_monitor_csv_file_importer.reconcile import reconcile_manifest

FIXTURES = Path(__file__).parent / "fixtures"
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class FakeClient:
    def __init__(self):
        self.imports = []

    def import_csv_batch(self, dataset_id, payload):
        self.imports.append((dataset_id, payload))
        n = len(payload["rows"])
        return {"inserted": n, "skipped": 0, "physical_schema": "ds_t", "physical_table": payload["signal"]}


@pytest.fixture
def data_dir(tmp_path):
    for f in FIXTURES.glob("*.csv"):
        shutil.copy(f, tmp_path / f.name)
    return tmp_path


def _signal(manifest, slug):
    return next(s for s in manifest["signals"] if s["slug"] == slug)


def test_infer_type():
    assert infer_type(["1", "2"]) == "integer"
    assert infer_type(["1", "2.5"]) == "double precision"
    assert infer_type(["2024-06-01"]) == "date"
    assert infer_type(["2024-06-01T08:00:00"]) == "timestamp"
    assert infer_type(["6/1/2024 8:00"]) == "timestamp"
    assert infer_type(["6.1", "5.9"]) == "double precision"
    assert infer_type(["Low", "6.1"]) == "text"


def test_profile_skips_clarity_preamble(tmp_path):
    src = FIXTURES / "dexcom_clarity.csv"
    profile = profile_csv(src)
    ts = profile["headers"].index("Timestamp (YYYY-MM-DDThh:mm:ss)")
    assert profile["inferred_types"][ts] == "timestamp"


def test_slug_is_sql_identifier():
    assert slug_from_filename("dexcom_clarity.csv") == "dexcom_clarity"
    assert slug_from_filename("001.csv") == "s_001"


def test_plan_maps_dexcom_and_libre(data_dir):
    manifest = plan_directory(data_dir)
    assert manifest["vendor"] == "glucose_monitor"
    dex = _signal(manifest, "dexcom_clarity")
    assert dex["matched_shape"] == "dexcom_clarity"
    assert dex["sampling_interval"] == "5min"
    assert dex["geomts_mapping"]["subject"] == "subject_id"
    assert dex["geomts_mapping"]["time"] == {"column": "timestamp"}
    assert [v["name"] for v in dex["geomts_mapping"]["values"]] == ["glucose_mmol", "insulin_u", "carb_g"]
    assert all(IDENT.match(c["name"]) for c in dex["columns"])
    assert "Patient Info" not in {c["name"] for c in dex["columns"]}

    libre = _signal(manifest, "freestyle_libre")
    assert libre["matched_shape"] == "freestyle_libre"
    assert libre["sampling_interval"] == "15min"
    assert libre["geomts_mapping"]["subject"] == "serial_number"
    assert libre["geomts_mapping"]["time"] == {"column": "device_timestamp"}
    names = [v["name"] for v in libre["geomts_mapping"]["values"]]
    assert names == ["historic_glucose_mmol", "scan_glucose_mmol", "carb_g"]
    assert "record_type" not in names


def test_plan_output_needs_no_corrections(data_dir):
    review = reconcile_manifest(plan_directory(data_dir))
    assert review["errors"] == [] and review["corrections"] == []


def test_mg_dl_clarity_shape(tmp_path):
    p = tmp_path / "clarity_mg.csv"
    p.write_text(
        "Index,Timestamp (YYYY-MM-DDThh:mm:ss),Event Type,Event Subtype,Patient Info,"
        "Device Info,Source Device ID,Glucose Value (mg/dL),Insulin Value (u),Carb Value (grams)\n"
        "12,2024-06-01T08:00:00,EGV,,,Dexcom G7,synth,110,,\n"
    )
    manifest = plan_files([p])
    sig = manifest["signals"][0]
    assert sig["matched_shape"] == "dexcom_clarity"
    assert sig["subject_from_file"] is True
    assert sig["geomts_mapping"]["subject"] == "subject_id"
    assert any(v["name"] == "glucose_mg_dl" for v in sig["geomts_mapping"]["values"])


def test_import_skips_non_egv_and_renames_columns(tmp_path):
    src = FIXTURES / "dexcom_clarity.csv"
    shutil.copy(src, tmp_path / src.name)
    manifest = plan_directory(tmp_path)
    client = FakeClient()
    result = import_signal(client, "ds", _signal(manifest, "dexcom_clarity"), tmp_path)
    rows = client.imports[0][1]["rows"]
    assert result["inserted"] == 3
    assert len(rows) == 3
    assert rows[0]["glucose_mmol"] == "6.1"
    assert rows[0]["subject_id"] == "S-1001"
    assert all(r["event_type"] == "EGV" for r in rows)
    assert client.imports[0][1]["table_prefix"] == "glucose"
    assert client.imports[0][1]["source_name"] == "Glucose monitor"


def test_native_clarity_subject_comes_from_file_stem(tmp_path):
    folder = tmp_path / "S-2002"
    folder.mkdir()
    (folder / "clarity.csv").write_text(
        "Index,Timestamp (YYYY-MM-DDThh:mm:ss),Event Type,Event Subtype,Patient Info,"
        "Device Info,Source Device ID,Glucose Value (mmol/L),Insulin Value (u),Carb Value (grams)\n"
        "1,,FirstName,,,,,,,\n"
        "2,2024-06-01T08:00:00,EGV,,,Dexcom G7,synth,5.5,,\n"
    )
    manifest = plan_files([folder / "clarity.csv"])
    client = FakeClient()
    import_signal(client, "ds", manifest["signals"][0], tmp_path, csv_path=folder / "clarity.csv")
    assert client.imports[0][1]["rows"] == [{
        "index": "2",
        "timestamp": "2024-06-01T08:00:00",
        "event_type": "EGV",
        "event_subtype": "",
        "patient_info": "",
        "device_info": "Dexcom G7",
        "source_device_id": "synth",
        "glucose_mmol": "5.5",
        "insulin_u": "",
        "carb_g": "",
        "subject_id": "S-2002",
    }]


def test_reconcile_requires_a_subject():
    manifest = {"vendor": "glucose_monitor", "signals": [{"slug": "x", "file": "x.csv",
                "columns": [{"name": "a", "type": "text"}],
                "geomts_mapping": {"subject": None, "time": None, "values": []}}]}
    assert any("subject is required" in e for e in reconcile_manifest(manifest)["errors"])


def test_plan_command_writes_manifest(data_dir):
    assert main(["plan", "--data-dir", str(data_dir)]) == 0
    manifest = load_manifest(data_dir)
    assert manifest["vendor"] == "glucose_monitor"
    assert {s["slug"] for s in manifest["signals"]} == {"dexcom_clarity", "freestyle_libre"}


def test_import_chunks_prefix(tmp_path):
    n = CHUNK_SIZE * 2 + 1
    lines = ["id,timestamp,glucose_mmol"]
    lines += [f"s,2024-06-01T08:{i // 60:02d}:{i % 60:02d},{5 + (i % 3)}" for i in range(n)]
    (tmp_path / "hr.csv").write_text("\n".join(lines) + "\n")
    client = FakeClient()
    signal = {
        "slug": "glucose",
        "file": "hr.csv",
        "columns": [],
        "dedupe_columns": ["id"],
        "sampling_interval": "5min",
        "geomts_mapping": {"subject": "id"},
    }
    result = import_signal(client, "ds", signal, tmp_path, mode="replace")
    assert [p["mode"] for _, p in client.imports] == ["replace", "append", "append"]
    assert all(p["table_prefix"] == "glucose" for _, p in client.imports)
    assert client.imports[0][1]["mapping"]["sampling_interval"] == "5min"
    assert result["inserted"] == n


def test_import_progress_marker(tmp_path, capsys):
    (tmp_path / "a.csv").write_text("id,timestamp,glucose_mmol\nx,2024-06-01T08:00:00,6.1\n")
    signal = {"slug": "a", "file": "a.csv", "columns": [], "geomts_mapping": {}}
    import_all(FakeClient(), "ds", {"signals": [signal]}, tmp_path)
    line = next(l for l in capsys.readouterr().out.splitlines() if l.startswith("@@PROGRESS@@ "))
    progress = json.loads(line.split(" ", 1)[1])
    assert progress["signal"] == "a" and progress["rows_total"] == 1


def test_validate_command(data_dir):
    assert main(["plan", "--data-dir", str(data_dir)]) == 0
    manifest = load_manifest(data_dir)
    _signal(manifest, "dexcom_clarity")["geomts_mapping"]["subject"] = "nope"
    from w4h_glucose_monitor_csv_file_importer.manifest import write_manifest
    write_manifest(data_dir, manifest)
    assert main(["validate", "--data-dir", str(data_dir)]) == 1
