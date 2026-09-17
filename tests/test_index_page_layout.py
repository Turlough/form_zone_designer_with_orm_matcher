"""Centre-panel width for Indexer page fit (no widget smoke)."""

from ui.index_main_image_panel import page_fit_panel_width


def test_page_fit_uses_height_scale_without_upscaling():
    # Page 1000x2000 in a 500-tall pane: scale 0.25, width 250.
    assert page_fit_panel_width(1000, 2000, 500, 2000, 280) == 250


def test_page_fit_does_not_scale_up_when_pane_is_taller_than_page():
    assert page_fit_panel_width(400, 800, 1200, 2000, 280) == 400


def test_page_fit_reserves_trailing_panel_width():
    # Needed width 500, but only 600 available with 280 reserved for details.
    assert page_fit_panel_width(1000, 2000, 1000, 600, 280) == 320


def test_page_fit_zero_when_dimensions_invalid():
    assert page_fit_panel_width(0, 2000, 500, 1000, 280) == 0
    assert page_fit_panel_width(1000, 2000, 0, 1000, 280) == 0
