# Indexer

## Who is using the app

Indexer uses the Windows account you are logged in as. The name appears in the window title (`Field Indexer - username - …`). There is no separate login screen.

## Batch folders and `batch.log`

Batches live under the project’s job folder (`batch_folder` in `project_config.json`). Indexer moves a batch folder when you open or complete it. After each successful move it appends a line to `batch.log` beside `EXPORT.TXT` (or whatever `import_filename` is):

| Event | Previous location | New location |
| --- | --- | --- |
| Open Batch | job folder (for example `SCANS`) | `_in_progress` |
| Complete Batch | `_in_progress` | `_qc` |
| Open Batch | `_qc` | `_qc/_in_progress` |
| Complete Batch | `_qc` or `_qc/_in_progress` | `_complete` |

Columns: `Datetime`, `User`, `Event`, `Previous location`, `New location` (tab-separated). Reopening a batch already in `_in_progress` (resume or session restore) does not move it and does not add a log line.

**Log → View log** shows that table for the open batch. Close the dialog when finished. If no batch is open, Indexer asks you to open one first.

The Exporter reads finished batches from `_complete`.
