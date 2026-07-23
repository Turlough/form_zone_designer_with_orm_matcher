# Templates and project setup (before Designer)

Complete this setup **before** you open Form Zone Designer. Designer, Indexer, and Exporter all use the same **project folder** (sometimes called the config folder). A project defines one form type: blank template scan, fiducial, field layouts, and settings for indexing and export.

## What you are building

| Term | Meaning |
|------|---------|
| **Project** | One form design: folder on disk with template, fiducial, JSON field definitions, and `project_config.json`. |
| **Template** | Multipage scan of a **blank** form (no respondent data). Used only for design and as the size reference when indexing. |
| **Fiducial** | A small, stable image patch (often a logo or heading) that the app finds on each page so field zones stay aligned when scans shift slightly. |
| **Zone** | A rectangle where data is read. Coordinates are stored **relative to the top-left corner of the fiducial**, not the page corner. |

## Project folder layout

Create one folder per form type (project). Typical layout:

```text
MyProject/
  template.tif          # required — multipage blank form scan
  fiducials/            # required for normal pages — fiducial image(s)
    logo.png            # see “Fiducial image” below
  json/
    project_config.json # strongly recommended before indexing; partial keys used in Designer
    1.json              # page 1 field definitions (created/updated in Designer)
    2.json              # page 2, etc.
  qc_comments.txt       # optional — preset QC comment lines for Indexer
```

Designer creates `json/` and `fiducials/` if they are missing when you load the folder. **`template.tif` must already exist** or Designer cannot open the project.

File names are matched **without regard to case** (for example `Template.TIF` or `LOGO.PNG` are fine).

## Template scan (`template.tif`)

- **Format:** Multipage TIFF is the expected format (one file, one page per frame).
- **Content:** Use a clean **unfilled** form. The same layout will be used to define zones; indexed batches use filled scans with the same page count and layout.
- **Quality:** Scan at consistent resolution and orientation. Skew and scale differences are partly corrected via the fiducial, but poor scans make matching and OCR harder.
- **Page count:** Every page that will appear on live forms should be present in the template. Page JSON files use **1-based** names: first page → `1.json`, second → `2.json`, and so on.

## Fiducial image

Place **one** fiducial image in the `fiducials/` subfolder. The apps look for the first existing file among (in order):

1. `logo.png`
2. `logo.tif`
3. `fiducial.png`
4. `fiducial.jpg`

**How to choose the crop**

- Cut a tight image from the **template** of a mark that **appears on every page** that uses a fiducial (logo, printed heading, fixed graphic). That mark may sit in **different positions on different pages**; the apps search each page separately and align fields to wherever it is found.
- Use a region that is **unique** on the page (avoid generic lines or empty margins).
- Prefer sharp, high-contrast artwork; avoid heavy JPEG compression on the fiducial file.
- The patch should match what appears on **production scans** (same form revision).

**In the apps**

- Designer and Indexer run template matching **on each page** to locate the fiducial. Position can differ from page to page; field zones are still stored relative to that page’s detected top-left corner. When found, the fiducial is highlighted (green in Designer).
- Field `x`, `y`, `width`, and `height` in JSON are **offsets from the fiducial top-left**. If no fiducial is found on a page, zones are treated as relative to the page origin `(0, 0)`, which is fragile for indexing—fix the fiducial or scan rather than relying on that fallback.

**Pages without a fiducial**

Some pages (covers, instructions) may have no repeatable mark. List their **zero-based page indices** in `project_config.json`:

```json
"pages_without_fiducial": [0]
```

Here `0` is the **first** page of the template. Omit the key or use `[]` if every page uses a fiducial.

Create or edit `project_config.json` **before** loading the project in Designer if you need this list; Designer reads it when detecting fiducials.

## `json/project_config.json`

Single JSON file per project for paths, review rules, and validations. Indexer and Exporter require several keys; Designer uses it mainly for `pages_without_fiducial` (and loads the same file later for other apps).

Example (adjust paths and field names for your job):

```json
{
  "batch_folder": "c:\\Jobs\\MyForm\\batches",
  "import_filename": "EXPORT.TXT",
  "always_review": ["Field3", "Another field"],
  "quick_review": ["Field 5", "Field 6"],
  "lookup_list": "optional/path/to/lookup.csv",
  "pages_without_fiducial": [0],
  "validations": [
    {
      "strategy": "max_tickboxes",
      "field_names": ["q1_a", "q1_b"],
      "params": { "max": 1 }
    },
    {
      "strategy": "value_exists_in_lookup",
      "field_names": ["herd_number"],
      "params": { "lookup_column": 0 }
    }
  ]
}
```

| Key | Purpose |
|-----|---------|
| `batch_folder` | Root folder for batch directories (Indexer batch menu, Exporter). **Required** for Indexer/Exporter workflows. |
| `import_filename` | Name of each batch’s import/list file (for example `EXPORT.TXT`). **Required** for Indexer/Exporter. |
| `always_review` | Field names that QC should always review (Field Review / QC flows). |
| `quick_review` | Field names for quick review lists in Indexer. |
| `lookup_list` | Optional CSV path for lookup-backed validations. |
| `pages_without_fiducial` | Zero-based page indices with no fiducial search. |
| `validations` | Optional project-level rules (see validation docs / Indexer behaviour). |

You can add `project_config.json` early with only the keys you need and expand it before indexing starts. **`batch_folder` and `import_filename` must be valid before operators use Indexer or Exporter.**

Paths may be absolute or relative; use valid JSON escaping for Windows paths (`\\`).

## Page field JSON (`json/1.json`, `json/2.json`, …)

Designer creates and updates these files when you save field work. You normally **do not** hand-author them, but the structure matters for downstream apps:

- One file per template page, named by **page number** (`1.json` = first page).
- Content is a **JSON array** of field objects.
- Each object includes `_type` (for example `Tickbox`, `TextField`, `RadioGroup`, `IntegerField`, `SignatureField`, …), `name`, `x`, `y`, `width`, `height`, and type-specific properties (for example tickbox `checked_value`, radio group `radio_buttons`).
- **Names** become column headings in batch import/export files; choose stable, unique names before indexing goes live.

If a page file is missing, Designer starts with an empty page; Indexer expects definitions for every page that has fields to capture.

## Optional: `qc_comments.txt`

Plain text, one preset comment per line. If present in the project folder, Indexer loads these as QC comment shortcuts. Not required for design.

## Environment (optional)

Copy `env.example` to `.env` in the repo root if you use shared defaults:

- **`DESIGNER_CONFIG_FOLDER`** — Parent directory that contains project folders. Designer’s **File → Load Config Folder** dialog opens here by default; you still select the **project** subfolder, not the parent.

Indexer/Exporter use their own project selection (Project menu) pointing at the same project folder layout.

## Pre-design checklist

1. Create the project folder and subfolders `json/` and `fiducials/` (or let Designer create them on first load).
2. Place **`template.tif`** (multipage blank form) in the project folder.
3. Add a fiducial image under **`fiducials/`** using one of the supported file names; verify the app can detect that patch on each page that should use a fiducial (position may differ per page).
4. Add **`json/project_config.json`** with at least `pages_without_fiducial` if any page lacks a mark; add `batch_folder` and `import_filename` before indexing.
5. Confirm page count in the template matches the number of pages you will design.
6. Open **`INSTRUCTIONS-2-Designer.md`** and start Form Zone Designer (**File → Load Config Folder** → select the project folder).

After setup, design staff define zones on each page in Designer; indexing staff then use the same project folder in Indexer with batch files under `batch_folder`.
