# Exporter

## Tools → Deliver

After batches are loaded and validated, choose one of:

1. **Single export NO comments** — one `<job_name>.csv` under `_deliveries/<job_name>/`, with the Comments column omitted; all rows in batch order. TIFF paths are converted to PDFs in the `PDF` subfolder as for other deliver modes.
2. **Single export WITH comments** — one `<job_name>.csv` with all rows and the Comments column included.
3. **Create split export** — `<job_name>.csv` (rows with no comments) and `<job_name>_exceptions.csv` (rows with one or more comments).
