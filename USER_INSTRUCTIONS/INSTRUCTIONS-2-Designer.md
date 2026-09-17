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
| **All uppercase** | `False` | Dropdown. When `True`, Indexer stores typed and OCR text in uppercase (`all_uppercase`). Missing key is treated as `False`. |

OK saves to `json/project_config.json`. Set **batch_folder** and **import filename** before using Indexer or **Create Test Batch**.

### Create Test Batch

Creates a throwaway batch so you can open Indexer against the current design.

1. Prefills **Batch name** `test001` and **Number of documents** `1`.
2. OK creates `<batch_folder>/<batch name>/`.
3. Copies `template.pdf` that many times as `0001.pdf`, `0002.pdf`, … (a TIFF/PDF template is converted if `template.pdf` is missing).
4. Writes **import_filename** (for example `EXPORT.TXT`) in that folder, listing those PDFs in the **File** column.

The batch folder must not already exist. Indexer then lists this batch from the project’s `batch_folder`.

If the project has a **print crop** (trimmed production scans), a test batch made from the untrimmed template will not match live forms. Use a real trimmed scan to check Print crop, or clear `print_crop` before indexing a test batch built from the template.

## Fiducials

The **Fiducials** menu is enabled after a project is loaded.

### Select rectangle

Draw a rectangle on the current template page to save `fiducials/logo-pN.png` for that page (1-based N). That patch overrides the default `logo.png` when matching.

### Print crop

Use this when production sheets are trimmed inside crop marks that still appear on the **template**.

1. **Fiducials → Print crop…** opens a two-pane window.
2. Left: template page. Drag the cyan rectangle onto the crop marks (same rectangle is used for every page).
3. **File → Load cropped version** (in this window) opens a sample scanned PDF/TIFF of a finished sheet. The picker starts in the project’s **batch_folder** (from Basic Indexing Config).
4. Page, zoom, and scroll at the bottom (and scrolling either pane) move **both** images together. Dragging the crop rectangle only moves the overlay; the template image stays at the current zoom.
5. Click punctuation, box corners, or other sharp marks on the **right** scan. Numbered crosses appear on both panes. Adjust the crop until each left-hand cross sits on the same printed feature as the matching right-hand click. **Clear registration marks** removes them (also cleared when you change page or load another sample).
6. On mouseup, the right pane pastes the sample into the crop rectangle on a template-sized canvas (the same step Indexer will run), then draws the fiducial (green) and field zones. The match score is shown at the bottom. Page through to confirm every page.
7. If some pages miss the fiducial even when registration marks line up, go to a page where the **green box** sits on the mark and click **Save detected fiducial**. That overwrites the default file in `fiducials/` (`fiducial.png` or `logo.png`) with the patch from the scan. Confirm first — the app does not keep a backup. Then page through again; other pages that use the default fiducial now match this scanned appearance.
8. **Save print crop** writes `print_crop` to `json/project_config.json`. **Clear** removes the key so Indexer stretches scans to the full template again.

Do not redesign fields on a filled scan; keep the original template and use Print crop for finish size.
