Architecture redesign: summary and implementation plan

Rationale summary

1. Lean model (zone + type)
Field types should represent only structure and data: a zone (rectangle) and a type (Tickbox, RadioGroup, TextField, etc.). Colour is a presentation choice and can differ by mode (Design vs Index vs QC). It should live outside the model (e.g. a small map “field type → colour” in the UI layer or theme), so serialisation (JSON) stays stable and the model stays about “what and where.”

2. Mode-specific behaviour without class explosion
Avoid a separate class per field type per mode (e.g. DesignerNumericDataGroup, IndexerNumericDataGroup). Instead, keep one family of field types and apply strategies to the model: the same model instance is operated on and drawn differently depending on the mode. Design-only operations (e.g. add_radio_button) belong in a design-time strategy, not on the model.

3. Strategies applied to the model
The essence is: strategies applied to the model. Examples:





design_manager.add_radio_button(model_instance) — design-time mutation.



indexing_draw_manager.draw(painter, model_instance, value) — how Indexer draws the field.



qc_draw_manager.draw(painter, model_instance, value, qc_state) — how QC draws it (e.g. with flags/comments).

4. Strategy sets as managers
Group strategies per mode into manager-style objects:





DesignUIManager (or DesignFieldManager): design-time operations (add/remove radio buttons, etc.) and draw(painter, field, ...) for the design view (outlines, labels, no values).



IndexingDisplayManager: draw(painter, field, value, ...) for the indexing view (outlines, values, tick/cross, selection).



QcUIManager: draw(painter, field, value, qc_state, ...) for the QC view (indexing view plus QC markers/comments).

Each manager is a “strategy set” for one mode: it knows how to operate on the model (where that mode mutates) and how to draw it. Result: one family of model types, one family of mode-specific managers, clear call sites.

5. Fit with MVC/MVVM
Model = data/structure only. View = panels that display image and overlays, using the current mode’s painter. Controller/ViewModel = Designer, Indexer, QC; they own mode-specific operations and the choice of which manager/painter to use. No need to name it strictly MVC/MVVM; the split is: model = zone + type; view = display; mode behaviour and drawing = separate composable layer.



Broad implementation plan (high level)

Code will have changed by the time this is implemented; the following is intentionally high level.

Phase 1: Lean model





Remove colour from the Field hierarchy (and from serialisation). Introduce a single place for “field type → colour” (e.g. in a theme or in each manager) used only at draw time.



Ensure the model exposes only zone, type, and structural data (e.g. radio_buttons list). Any design-only mutators (e.g. add_radio_button) will be moved out in Phase 2.

Phase 2: Introduce mode managers (strategy sets)





Add DesignUIManager (or DesignFieldManager): move design-only operations (add/remove radio button, etc.) here; they take the model instance as argument. Add a draw(painter, field, ...) used by the Designer UI.



Add IndexingDisplayManager: implement draw(painter, field, value, ...) that encapsulates current Indexer drawing logic (outlines, values, tick/cross, selection). Replace inline drawing in the Indexer view with calls to this manager.



Add QcUIManager: implement draw(painter, field, value, qc_state, ...) for QC-specific overlay (reuse or extend IndexingDisplayManager as appropriate). Wire the QC view to use this manager.

Phase 3: Wire views to managers





Designer: use DesignUIManager for all field drawing and for any design-time field mutations (so the model classes no longer expose those methods).



Indexer: use IndexingDisplayManager for all field overlay drawing; keep hit-testing and value handling in the same layer or in the manager as appropriate.



QC: use QcUIManager for drawing; keep QC state and comments in existing data structures, passed into the manager where needed.

Phase 4: Clean-up and consistency





Remove any remaining mode-specific methods from the Field hierarchy. Ensure serialisation/deserialisation uses only the lean model (no colour, no UI-only state).



Optionally introduce a thin adapter or shared interface (e.g. draw(painter, field, context)) so all managers share a similar signature; keep the plan flexible so each manager can accept mode-specific context (value, qc_state, etc.) without forcing one huge context type.



Deliverable





Document: Update .cursor/future_plans/architecture_redesign.md with the rationale summary and this broad implementation plan so it can be revisited when you return to the restructuring.

