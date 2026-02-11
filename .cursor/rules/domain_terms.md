# Domain terminology
These rules apply to this project only. 
It describes the domain and some common terms.

## Domain
The app is primarily an indexing app. 
Staff are digitising scanned survey forms; the results are exported as data.
The app specialises in digitising survey/questionnaire forms, with tickboxes, radio groups, etc.
The project also contains a form design app that defines fields and locations that are used while indexing.

## Terms
- Indexing: the process of capturing data from a document.
- Indexer: the application that staff will use for indexing.
- Staff/Indexing staff: personnel who view and capture data from each page of a scanned image file. The file may have multiple pages. Indexing staff use the Indexer app for this.
- Designer: The app used for defining fields on a form. Before indexing can begin, the layout and fields of a form must be defined. A template is scanned, and design staff define the layouts and positions that will be used later in indexing. 
- Design staff: Design staff identify and locate the fields on the scanned template. In practice, that's me.
- QC/Quality Control: Final step before release of a batch. When a batch has been indexed, it is reviewed by QC staff. In any form, indexing staff may have flagged one or more fields for review- QC staff will resolve or escalate the issue. QC staff use the Indexer app for this.
- QC staff: staff assigned to perform Quality Control.
- Template: An unfilled form with no data, used when designing the form.
- Fiducial: A CV-recognisable region on a page. This is used to compensate for minor variations in scanning to provide consistent positioning for fields. Often a logo or heading is used.
- Zone/Location: A rectangular area on the scanned image on which data is to be found. This is measured from one corner of a fiducial, not from the corner of the page.
- Document/Form/Survey/Questionnaire: A multipage scanned document from which data is to be captured. Normally, this is a single file. 
- Form- design vs instance: In design, a template (i.e. no data) may be described as a form. While indexing, a form has data, and is an instance to be indexed. It should be clear from context which meaning to assume, but ask if unclear.
- Field: data representing one question of a form. A field has a name, a location/zone, a type, etc. When indexing, we assign it a value.
- Value: The data captured for a Field during indexing.
- Page: Forms have multiple pages.
- Batch: A group of similar documents, all with the same fields of interest. Each batch lives in a directory that contains images, a file representing the captured data, and a link to the source document.
- Project: Defines a form type and the data to be captured from it.
- Job: A collection of batches from the same project, typically gathered in a "job folder" on the file system. A project may have several jobs, and each job may have multiple batches.
- Validation: These are automatic boolean tests on Field values, such as "is_empty", "is_not_decimal" etc. Validations help indexers by providing visual cues to staff while indexing. For QC staff, validations can additionally form a list of values to check.
- Double keying: A quality control method in which two operators index the same batch, and any differences in output data are escalated. The remainder is deemed 'good', because both operators have agreed on it.
