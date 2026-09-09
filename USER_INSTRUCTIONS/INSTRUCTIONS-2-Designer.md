# Form Zone Designer

Use Designer to define field zones on a blank template. Complete **Templates and project setup** (`INSTRUCTIONS-1-Templates.md`) first.

Start the app (`app_designer.py`). **File → Load Config Folder** (`Ctrl+O`) opens a folder picker; choose the **project** folder (the one that contains `template.pdf` / `template.tif`, `json/`, and `fiducials/`). The window title shows the project name.

**Help** is the last menu. **Help → Designer** (`F1`) opens these instructions in your default browser. **Help → Templates** opens the Templates and project setup instructions.

## Indexing Config

The **Indexing Config** menu sits immediately after **File**. It writes indexing keys into `json/project_config.json` and can create a sample batch for Indexer. Load a project first; the menu items stay disabled until then.

### Basic Indexing Config

Opens a dialog with OK / Cancel. Existing values are loaded from `project_config.json` when present. Unrelated keys (validations, rectangle detection, review lists) are left unchanged.

| Field | Default when empty | Notes |
|-------|-------------------|--------|
| **Project name** | The project folder name | Stored as `project_name`. |
| **Batch folder** | *(blank)* | Folder picker. Root that will hold Indexer batch directories (`batch_folder`). |
| **Import filename** | `EXPORT.TXT` | File name only, not a path (`import_filename`). |
| **Lookup list** | *(blank)* | Optional file picker for a lookup CSV (`lookup_list`). Clear the field to remove the key. |
| **Lookup prime index** | `0` | Zero-based key column in that CSV (`lookup_prime_index`). |
| **Pages without fiducial** | `[0, 1]` | Zero-based page indices skipped during fiducial search (`pages_without_fiducial`). Use `[]` if every page has a mark. Saving this list re-runs fiducial detection on the open template. |

OK saves to `json/project_config.json`. Set **batch_folder** and **import filename** before using Indexer or **Create Test Batch**.

### Create Test Batch

Creates a throwaway batch so you can open Indexer against the current design.

1. Prefills **Batch name** `test001` and **Number of documents** `1`.
2. OK creates `<batch_folder>/<batch name>/`.
3. Copies `template.pdf` that many times as `0001.pdf`, `0002.pdf`, … (a TIFF/PDF template is converted if `template.pdf` is missing).
4. Writes **import_filename** (for example `EXPORT.TXT`) in that folder, listing those PDFs in the **File** column.

The batch folder must not already exist. Indexer then lists this batch from the project’s `batch_folder`.
