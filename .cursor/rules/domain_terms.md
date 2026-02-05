# Domain terminology
These rules apply to this project only. 
It describes the domain and some common terms.

## Domain
The app is primarily an indexing app. 
Staff are digitising scanned survey forms; the results are exported as data.
The app specialises in digitising survey/questionnaire forms, with tickboxes, radio groups, etc.
The project also contains a form design app that defines fields and locations that are used while indexing.

## Terms
- Staff/Indexer: personnel who view and capture data from each page of a scanned image file. The file may have multiple pages.
- Indexing: the process of capturing data from a document.
- Template: An unfilled form with no data, used when designing the form.
- Fiducial: A CV-recognisable region on a page. This is used to compensate for minor variations in scanning to provide consistent positioning for fields. Often a logo or heading is used.
- Zone/Location: A rectangular area on the scanned image on which data is to be found. This is measured from one corner of a fiducial, not from the corner of the page.
- Design (app/mode): Before indexing can begin, the layout and fields of a form must be defined. A template is scanned, and the Designer describes the layouts and positions that will be used later in indexing. 
- Designer: Designers are a separate stakeholder to indexers. They identify and locate the fields on the scanned template.
- Document/Form/Survey/Questionnaire: A multipage scanned document from which data is to be captured. Normally, this is a single file. 
- Form- design vs instance: In design, a template (i.e. no data) may be described as a form. While indexing, a form has data, and is an instance to be indexed.
- Field: data representing one question of a form. A field has a name, a location/zone, a type, etc. When indexing, we assign it a value.
- Value: The data captured for a Field during indexing.
- Page: Forms have multiple pages.
- Batch: A group of similar documents, all with the same fields of interest. Each batch lives in a directory that contains images, a file representing the captured data, and a link to the source document.
- Project: Defines a form type and the data to be captured from it.
