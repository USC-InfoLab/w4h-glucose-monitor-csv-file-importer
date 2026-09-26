# AGENTS.md — w4h-glucose-monitor-csv-file-importer

Importer module for **user-supplied glucose-monitor CSV files** (notebook + CLI + tests). Recognizes Dexcom Clarity and FreeStyle LibreLink headers. No bundled Kaggle download. The notebook picks files with a chooser. In-app **Run** / `./run.sh` calls the CLI and loads the synthetic fixtures declared in `contribution.yaml`.

Kaggle references (do not copy those files into git):

- https://www.kaggle.com/datasets/mauddib/dexcom-sensor-data
- https://www.kaggle.com/datasets/reneelinmedical/glucose-readings-from-cgm

- API key via `W4H_API_KEY` in local `.env` only — never in git.
- Do not add direct Postgres / `to_sql` paths; use the W4H API (`POST /datasets/:id/import/csv-batch`).
- The module owns its mapping logic (`profile.py`, `mapping.py`, `reconcile.py`, `catalog.py`, `shapes.py`). Do not call any W4H API route except `csv-batch` and `GET /datasets` (notebook picker).
- Clarity columns with spaces or units are renamed to SQL identifiers. `columns[].source` keeps the original header.
- Clarity import keeps `Event Type == EGV` only. Libre import keeps rows that have a historic or scan glucose cell.
- A Clarity file with no subject column gets `subject_id` from the parent folder (or the file stem). Libre uses `Serial Number`.
- Every `csv-batch` payload sends `table_prefix: "glucose"` (`config.TABLE_PREFIX`) — do not drop it.
- Progress: keep printing `@@PROGRESS@@ {json}` lines (contribution-runner.js parses them).
- Tests: `pytest tests/ -q -m "not integration"`. `contribution.yaml` is the test contract. `-m integration` tests need a running w4h-api.
