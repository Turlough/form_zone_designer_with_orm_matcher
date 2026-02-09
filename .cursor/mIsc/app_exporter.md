# Exporter
This is a PyQt6 app that assembles completed batches into a pair of files for the customer to import.
A collection of batches is called a Job- see domain_terms.md

One file contains 'clean' data, the other contains data to which staff have added one or more comments.

This document focuses on the "Deliver" function of the app. You can assume that data and headings have already been validated.

## Summary
The output data file type will be csv.
Any multipage TIFFs will be converted to multipage PDFs. 
Files will be copied and renamed. Source files are **never** edited or moved.
The app maintains a list of field names and types from the json folder when a project is selected.

## Details
The user has chosen a job folder in the Exporter, has validated contents, and is ready to prepare customer files.
The job folder is the name of the folder the user chose when selecting the job.
They select "Deliver" from the menu.

### Images/PDFs
- A new folder is created in "_deliveries", named like the Job folder. 
- It contains a folder called "PDF", a file called <job_name>.csv, and a file called <job_name>_exceptions.csv.
- Image files (TIFF) are converted to pdf, and the converted copies are stored in this PDF folder. 
- They are named like 0001.pdf, 0002.pdf etc, 

### Data rows
- The main delivery data file is named like <job_name>.csv.
- (Any rows with one or more comments are sent instead to <job_name>_exceptions.csv)
- Both files contain the same headings as the input files. Assume that these are consistent and have been validated.
- Replace the original tiff_path with the relative path to the output pdf.
- Any Text fields should be surrounded with double quotes.
- Numeric fields (IntegerField, NumericRadioGroup, DecimalField) are not surrounded by quotes.
- Empty cells remain empty- do not replace  with zero, for example.
