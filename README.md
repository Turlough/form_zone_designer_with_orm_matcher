# Form Zone Designer
This is a PyQt6 app that allows the user to load a scanned multipage form (or survey, etc) 
as a template. Multipage tiff is the expected format.

## Features

- **Page Navigation**: Thumbnails of each page are shown on the left panel. Click a thumbnail to display the full page on the right.
- **Logo Detection**: Automatically detects and highlights logos on each page using ORM matching (shown in green).
- **Field Rectangle Drawing**: Draw rectangles around form fields (e.g., tick boxes) by clicking and dragging on the page image.
  - Rectangles are shown in **red** on the page and thumbnails
  - While drawing, the current rectangle is shown in **blue**
  - Rectangles are stored per page and persist across page switches
- **Edit Controls**:
  - **Undo Last Field**: Remove the most recently drawn rectangle on the current page
  - **Clear All Fields on Page**: Remove all field rectangles from the current page

## Usage

1. Set up a `.env` file with:
   - `LOGO_PATH`: Path to the logo image file for ORM matching
   - `MULTIPAGE_TIFF`: Path to the multipage TIFF file to load
2. Run the application: `python form_zone_designer.py`
3. Click on a page thumbnail to view and edit it
4. Click and drag on the page to draw rectangles around fields
5. Use the control buttons to undo or clear field rectangles as needed