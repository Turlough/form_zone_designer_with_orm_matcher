# Architecture redesign — status and plan

**Status (2026-07):** Phases 1–4 below are **not started**. The codebase still matches the pre-plan shape: `colour` on `Field` and in JSON, `RadioGroup` / `NumericRadioGroup` expose `add_radio_button` / `remove_radio_button`, and drawing plus QC overlays live inline in `ui/designer_main_image_widget.py` and `ui/index_main_image_panel.py` (no `DesignUIManager`, `IndexingDisplayManager`, or `QcUIManager`).

**Already aligned with intent (no work item):** There is a single field-type family per structure (no `DesignerNumericDataGroup` / `IndexerNumericDataGroup` style split). The remaining work is lean model, mode managers, and wiring views to them.

---

## Rationale (unchanged goals)

1. **Lean model (zone + type)** — Field types = structure and data only. Colour is presentation (Design vs Index vs QC) and belongs outside the model (e.g. type → colour at draw time) so JSON stays stable.

2. **Mode-specific behaviour without class explosion** — One field family; strategies operate on the same model instance per mode. Design-only mutations (e.g. `add_radio_button`) belong in a design-time strategy, not on the model.

3. **Strategies applied to the model** — e.g. `design_manager.add_radio_button(model)`, `indexing_draw_manager.draw(painter, model, value)`, `qc_draw_manager.draw(painter, model, value, qc_state)`.

4. **Strategy sets as managers** — `DesignUIManager` (mutate + design draw), `IndexingDisplayManager` (index draw), `QcUIManager` (QC overlay). Each mode = one manager at call sites.

5. **Fit with MVC/MVVM** — Model = zone + type; view = image/overlays; app shell chooses manager and mode operations.

---

## Implementation plan

High level only; reconcile with current files before each phase.

### Phase 1: Lean model

- Remove `colour` from the `Field` hierarchy and from serialisation.
- Introduce a single draw-time map: field type → colour (theme or per manager).
- Model exposes zone, type, and structural data only (e.g. `radio_buttons`). Defer moving mutators to Phase 2.

### Phase 2: Mode managers (strategy sets)

- **DesignUIManager** (or `DesignFieldManager`): design mutations (add/remove radio buttons, etc.) on model instances; `draw(painter, field, ...)` for Designer.
- **IndexingDisplayManager**: `draw(painter, field, value, ...)` from current Indexer overlay logic; replace inline drawing in the Indexer view.
- **QcUIManager**: `draw(painter, field, value, qc_state, ...)` — extend or compose indexing draw; wire QC overlays (today mixed into `index_main_image_panel.py`).

### Phase 3: Wire views to managers

- **Designer:** all field draw and design-time mutations via Design manager; strip those methods from model classes.
- **Indexer:** overlay drawing via Indexing manager; hit-testing / values in view or manager as fits.
- **QC:** drawing via Qc manager; existing QC comment/state structures passed in.

### Phase 4: Clean-up

- Remove any remaining mode-specific methods on `Field` subclasses.
- Serialisation/deserialisation uses lean model only (no colour, no UI-only state).
- Optional: shared `draw(painter, field, context)` shape across managers without one oversized context type.
