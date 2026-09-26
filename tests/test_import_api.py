"""Integration test against a running w4h-api. Run: pytest -m integration -q

Needs W4H_API_KEY (and optionally W4H_API_BASE / W4H_DATASET_ID); skipped otherwise.
"""

import os

import pytest

from w4h_glucose_monitor_csv_file_importer.client import W4HClient


@pytest.mark.integration
def test_import_glucose_batch():
    if not os.environ.get("W4H_API_KEY", "").strip():
        pytest.skip("W4H_API_KEY not set")
    dataset_id = os.environ.get("W4H_DATASET_ID", "").strip()
    if not dataset_id:
        pytest.skip("W4H_DATASET_ID not set")
    result = W4HClient().import_csv_batch(
        dataset_id,
        {
            "signal": "glucose_probe",
            "table_prefix": "glucose",
            "mode": "append",
            "dedupe_columns": ["subject_id", "timestamp"],
            "columns": [
                {"name": "subject_id", "type": "text"},
                {"name": "timestamp", "type": "timestamp"},
                {"name": "glucose_mmol", "type": "double precision"},
            ],
            "mapping": {
                "signal_type": "glucose_probe",
                "subject": "subject_id",
                "time": {"column": "timestamp"},
                "values": [{"source": "glucose_mmol", "name": "glucose_mmol", "type": "double precision"}],
            },
            "rows": [{"subject_id": "S-TEST", "timestamp": "2024-06-01T08:00:00", "glucose_mmol": "5.5"}],
            "source_name": "Glucose monitor",
            "description": "integration test row",
        },
    )
    assert result.get("success") is True
