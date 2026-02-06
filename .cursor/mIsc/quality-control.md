When indexing, staff may need to flag one or more fields on the form for review.
We will add an extra field, "Comments" to the output text file.
Any fields on the form that have been marked for review are concataneted, with a pipe (|) separator between them, and recorded in this field.
The format looks like:
```P1: Fieldname: comment | P5: Fieldname: comment``` etc. (P1 represents the page number, e.g P1 for page 1)

When a field has been marked for review like this, it is highlighted red in the field list on the right hand panel. 
Additionally, a red X is shown to the right of the field on the main image display.

Both indexing staff and qc staff are enabled to edit or remove a comment.
QC staff are additionally allowed to escalate a flagged field.

Currently, indexing data each batch is represented by a CSV file within the batch folder.
If form contains an escalated field, the corresponding row is removed from this csv file, 
and instead appended to a file "review.csv" in the same batch folder.
This keeps the 'clean' data separate from 'dirty' data.