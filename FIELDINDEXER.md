# Field Indexer
(field_indexer.py) is a PyQt6 app that enables the user to index form data from scanned completed forms.
It is the sister app to (form_zone_designer.py), which has previously been used to define field locations and types on each page.

## Loading a batch of completed forms
A "Load Import File" button allows the user to select a text file (.txt or .csv).
The text file contains a list of relative paths to multipage tiffs, one on each line of the file. These are scans of the completed forms. 
The first item on each row of the file is always prefilled- this is the relative path to the form.

This file is updated as the user indexes the form. 
A user may import a file that has already been partly or fully indexed.

## Headings
The file may or may not have headings. If not, they are immediately added to the file, comma separated.
The headings are defined by the field names in the json files. 
Iterate through each toplevel element in each json file, appending its 'name' as the next colum heading.
RadioGroups are captured by one cell- the selected button's name is the value of the cell.

Add matching commas for each row (if missing), so that data cells are predefined.

## Navigation
The list of tiff names is shown on the left hand panel.
Selecting an image displays the first page of the tiff in the right hand panel.
The user navigates through pages using navigation buttons (use icons for these) over the page image.

# Pages
When the user navigates to a new page, the fiducial/logo is detected, then the fields are drawn relative to its top left corner. 
The fields have already been defined in the json files for each page. 
The location for the json definition files is defined by the .env value JSON_FOLDER, 
and they are named 1.json, 2.json etc; one for each page of the form.

On each page, the user may:
Qt6 Widgets are not shown on the form- the user interacts directly with the overlaid rectangles instead.
1. Click on a TickBox.  The tickbox is filled with a semitransparent color as a visual clue. Clicking again toggles the tick state.
2. Select one RadioButton in from each RadioGroup. The name of the button becomes the value assigned to the radio group. Selecting one button deselects the others. The selected button is filled semitransparent.
3. Enter text on a TextField. A dialog is shown allowing text entry. When submitted, the text is shown under the rectangle.

If data has already been defined in the input file, update the UI as above.
This allows for an import file to be indexed in several sessions if necessary.

## Output
Each row of the selected text file represents a full multipage form.
As the user edits (i.e. ticks, unticks, adds text, etc), the corresponding cell in the text file is updated.
