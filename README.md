# W4H Glucose Monitor CSV File Importer

Notebook + CLI to import **glucose-monitor CSV files you supply** into W4H. The two layouts it recognizes are Dexcom Clarity and Abbott FreeStyle LibreLink. Pick your own files (or point the CLI at a folder); the importer builds a GeoMTS mapping from their headers, lets you review it, and ingests them through the W4H API. Credentials stay in a local `.env` (never committed).

**Publisher:** usc-infolab · **Kinds:** notebook, CLI · **Language:** Python

This repo is bootstrapped from [w4h-fitbit-csv-file-importer](https://github.com/USC-InfoLab/w4h-fitbit-csv-file-importer): `plan` → review `manifest.yaml` → `import` / `sync` via `POST /datasets/:id/import/csv-batch`. Every payload sends `table_prefix: "glucose"`.

## Kaggle samples

Do not commit those downloads. They can contain real names, serial numbers, and glucose traces. `tests/fixtures/` is a few synthetic rows that use the same headers.

| Device | Kaggle dataset | What the importer keeps |
|--------|----------------|-------------------------|
| Dexcom Clarity (G6/G7), mg/dL or mmol/L | [dexcom sensor data](https://www.kaggle.com/datasets/mauddib/dexcom-sensor-data) | Rows whose Event Type is `EGV`. Preamble and alert rows are skipped. Sampling interval on the mapping is 5 min. |
| FreeStyle LibreLink | [Glucose Readings from CGM](https://www.kaggle.com/datasets/reneelinmedical/glucose-readings-from-cgm) | Rows with a historic or scan glucose value. Sampling interval on the mapping is 15 min. |

Clarity headers such as `Glucose Value (mmol/L)` are renamed to SQL identifiers (`glucose_mmol`) before import. The original header is stored on the column as `source`. A Clarity file is one wearer: add a `subject_id` column, or the importer fills `subject_id` from the parent folder name (else the file stem). Libre uses `Serial Number` as the subject.

`Low` / `High` glucose tokens are left as text if they show up in the type sample. Prefer numeric cells.

## Who should do what

| Role | What to do |
|------|------------|
| **Admin** | Ingest your CSVs into **your team's** catalog. Use the CLI (`import` / `sync`) for cron and incremental updates. |
| **User** | Use analysis contributions against loaded datasets. You cannot add datasets or edit raw tables. |
| **Super admin** | Catalog this repo after it is on a git remote. This package is not seeded into `w4h.contributions` until then. |

## How it works

1. **Files** — one CSV per export, header row, UTF-8. The **notebook** has a file chooser. **In-app Run / `./run.sh` do not use the notebook** — they call the CLI and load the fixtures listed in [`contribution.yaml`](contribution.yaml).
2. **Plan** — profiles each CSV locally (headers and inferred types only), builds a GeoMTS mapping in this package, runs the six deterministic checks, and writes `manifest.yaml` + `plan.json` when you pass `--data-dir`. Review the mapping before import.
3. **Import** — streams kept rows in 500-row chunks to `POST /datasets/:id/import/csv-batch` with `table_prefix: "glucose"`. Progress is reported through `@@PROGRESS@@` lines.

## Prerequisites

- Running **w4h-api** and a personal API key (Profile → API keys)
- A dataset you can ingest into
- Python 3.10+

## Credentials

```bash
cp .env.example .env
# Edit .env — W4H_API_KEY only
```

## Install

```bash
pip install -e ".[dev,notebook]"
```

## Notebook

Open [`notebook/import_glucose_monitor_csv_file.ipynb`](notebook/import_glucose_monitor_csv_file.ipynb) and run the cells in order: **pick dataset → pick files → review mapping → import**.

## CLI

```bash
w4h-glucose-monitor-csv-file-import plan --data-dir /path/to/csvs
export W4H_API_KEY=w4h_sk_...
w4h-glucose-monitor-csv-file-import import --dataset-id my-cgm-data --data-dir /path/to/csvs --mode append
```

`--data-dir` defaults to the `contribution.yaml` live sample (the synthetic fixtures). `--mode replace` truncates each signal's table on its first batch.

## One-command run (`run.sh`)

```bash
./run.sh plan
./run.sh import
```

## Tests

```bash
pytest tests/ -q -m "not integration"
```

Optional API test, needs a running w4h-api:

```bash
export W4H_API_KEY=... W4H_DATASET_ID=my-cgm-data
pytest tests/test_import_api.py -m integration -q
```
