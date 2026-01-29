# "Radio Grids"
## Summary
Radio Grid represents a collection of radio groups, where each radio group is a row or a column,
and the RadioButtons within share the same names.

For example, a form may have many questions, to which the answers will always be one of: "small", "medium", or "large".
Each question is a radio group, and the three available answers don't change.
Therefore the three RadioButtons of each RadioGroup will always be named "small", "medium" and "large". 

Assume horizontal orientation: 
Each row is a question (i.e. RadioGroup) and colums define the answers (i.e. the names of the RadioButtons)

Radio Grids are not serialized as objects in themselves; they can be repesented as a list of radio groups
no different from any others.
However, they are useful when designing forms, as the form template often contains such grids.

## Implementation for form_zone_designer.py
- Launch a new window for this, "GridDesigner".
    - Ensure there is a button to launch this new window.
- The GridDesigner window shows:
    - Horizontally, an editable set of column labels, with an "Add" button to add another column. These are the answers to the questions, and define the names of the RadioButtons of each RadioGroup. I think the writing should be vertical here for compactness, i.e rotated 90 counterclockwise.
    - Vertically, an editable set of row labels, with an "Add" button to add another row. These are the questions, and define the names of the RadioGroups within the grid.
    - Allow 50 characters for labels.
    - The current page is displayed under the columns, to the right of the rows.
    - The detected fiducial is shown, but no other fields are displayed, even if they have already been defined for the page.
    - The user may draw a rectangle that defines the outline of the grid.
    - For each column heading, draw a boundary between them, equally spaced at first (e.g. Three columns require two boundaries)
    - Likewise for rows. 
    - The selection rectangle now contains a regular x by y grid.
    - Allow the users to drag row/column boundaries to match the grid on the template, which may be irregular. No snap behaviour is required. Horizontal lines remain horizontal and verticals remain vertical.
    - When the user clicks Submit:
        - Ensure there is at least one row and two columns. Show toast if not.
        - Each cell rectangle becomes a radio button.
        - Each row becomes a radio group, containing the related radio buttons.
        - The list of radio groups is returned to main window.
        - The bounding rectangle is no longer needed; we have instead a list of RadioGroups.