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

**QC → Batch QC Complete** asks the same question as reaching the last page of the last document: click Yes to complete the batch, or No to keep reviewing. Yes moves the batch the same way as finishing that last page. If no batch is open, Indexer asks you to open one first.

The Exporter reads finished batches from `_complete`.

## Text fields

Click a text field on the page (plain text, number, date, and the other text types). The cursor goes to the value box under the close-up on the right, with the current value selected, so you can type immediately. A small box also appears under the field on the page and stays in step with that value. Press Enter to move to the next text field on the page.

## Page → Drag fields

If a fiducial is missed, field outlines sit in the wrong place on the scan. **Page → Drag fields** opens a maximised window with that page centred on screen:

- Yellow outlines show each field. A blue box encloses all of them.
- Drag inside the box to move every field together.
- Drag an edge to stretch in that direction only.
- Drag a corner to resize while keeping the box’s shape.

**Apply** uses that placement for overlays, clicks, the close-up, and OCR until you leave the page. **Cancel** leaves the page as it was. The placement is not saved. Open the page again and the fields are back on the fiducial, or on their original positions if no fiducial was found.
