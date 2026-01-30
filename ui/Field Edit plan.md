# Rectangle Selected
## Summary
The current method of editing fields is still a bit unintuitive. Let's rethink.
We are assuming that rectangles have been drawn or detected already on the current page, as this works well already.

We will no longer use the DesignerEditPanel for converting detected rectangles to Fields. 
We will remove this. We will instead show a new RectangleSelectedDialog

## Functionality
The RectangleSelectedDialog is shown to the right of the mouse-up event, centered vertically on mouse location.
If there is not enough room, show to the left instead.

When submit is completed, notify:
- The main window- the rectangle is now a Field (i.e. subclass of Field)
- The field list in the DesignerFieldList
- Update the JSON file

### User left clicks within a rectangle
When the user left-clicks within a rectangle, show a RectangleSelectedDialog (see designer_rectangle_selected_dialog.py).
The dialog initially shows:
- A text box for the name of the new field
- A vertical pick list (not a dropdown) for choosing field type
- Delete, Submit and Cancel buttons. 
    - (The Delete button deletes the selected rectangle. Close the dialog and refresh the UI, showing the remaining rectangles.) 
- The RadioGroup option is shown as disabled.

### User completes drawing of a rectangle
When the user has hand drawn a rectangle, on mouse-up:
- Show the same dialog, but with RadioGroup enabled.
- If the user selects RadioGroup, then all rectangles fully within the drawn rectangle will become RadioButtons on submission.
- For each rectangle, add a text box to name it within the dialog. 
- When the user clicks Submit, the outer rectangle becomes the named RadioGroup, and the inner rectangles become named Radio buttons within it.
- If the user deletes a RadioGroup, do not delete any RadioButtons or rectangles within.

### User clicks within the rectangle of an existing field
Show the same dialog, with RadioGroup disabled.
Pre-fill the dialog with the field's current name and type, with the current type selected in the pick list, since renaming is the more common use case.
Highlight the field in DesignerFieldList.
Notify the preview panel. This functionality works already, so no change needed.




