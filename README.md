# dermsr-ui

A web UI for [DERMS-R](https://github.com/edramos-lab/dermsr) analysis. Upload a
training-log JSON file (one row per architecture &times; dataset-ratio pair) and get:

- A results table (accuracy, parameter count, standard deviation, dataset ratio, DERMS-R
  raw and normalized score) -- downloadable as CSV or XLSX.
- A radar-chart grid, one panel per architecture, at its own optimal dataset ratio.
- A DERMS-R-per-architecture bar chart across every evaluated ratio.
- A scatter plot of DERMS-R at each architecture's optimal operating point.
- Friedman test + Nemenyi critical-difference statistical comparison across architectures.

Every chart has a **PNG (300 DPI)** and **PDF (vector)** download button, rendered server-side
with matplotlib specifically for that export (not a screenshot of the on-screen interactive
chart), so the downloaded file is suitable for direct inclusion in a paper.

All scoring and statistics are computed by the [`dermsr`](https://github.com/edramos-lab/dermsr)
reference implementation (pinned to `v0.1.0`) -- this repo only provides the upload/visualization
layer around it.

## Quickstart

```bash
docker compose up --build
```

Then open <http://localhost:8090>. Click **Load example data** to try it immediately with the
paper's own verified CIFAR-10 benchmark (12 architectures &times; 5 dataset ratios), or upload
your own JSON file.

## Input JSON schema

A JSON array of row objects, one per (architecture, dataset_ratio) pair:

```json
[
  {
    "architecture": "efficientvit_b0",
    "dataset_ratio": 0.10,
    "n_parameters": 2141818,
    "mean_val_accuracy": 0.89924,
    "std_val_accuracy": 0.00345
  }
]
```

Required fields: `architecture`, `dataset_ratio` (fraction of training data used, in `(0, 1]`),
`n_parameters` (raw trainable parameter count). For the accuracy statistics, provide **either**:

- `mean_val_accuracy` + `std_val_accuracy` directly (both on the 0-1 scale), **or**
- `fold_1_accuracy`, `fold_2_accuracy`, ... (at least 2 folds) -- the mean and sample standard
  deviation are computed from these automatically.

Common alternate column names are accepted automatically: `ratio`/`num_parameters`/
`mean_validation_accuracy`/`sd_validation_accuracy` (matching the `derms-r` benchmark pipeline's
own CSV export naming).

Click **Load example data** in the running app to try the tool immediately against a real file in
this exact schema (the paper's own CIFAR-10 benchmark), or fetch it directly via `GET /api/example`
to use as a download/template.

## Development (without Docker)

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8090
```
