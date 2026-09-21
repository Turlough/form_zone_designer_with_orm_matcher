"""Centre-panel width for Indexer page fit (no widget smoke)."""

from ui.index_main_image_panel import PAGE_FIT_RIGHT_PADDING_RATIO, page_fit_panel_width


def test_page_fit_uses_height_scale_without_upscaling():
    # Page 1000x2000 in a 500-tall pane: scale 0.25, fitted 250, +10% right pad.
    assert PAGE_FIT_RIGHT_PADDING_RATIO == 0.10
    assert page_fit_panel_width(1000, 2000, 500, 2000, 280) == 275


def test_page_fit_does_not_scale_up_when_pane_is_taller_than_page():
    # Native 400-wide page plus 10% right pad.
    assert page_fit_panel_width(400, 800, 1200, 2000, 280) == 440


def test_page_fit_reserves_trailing_panel_width():
    # Fitted 500 + 10% = 550, but only 600 available with 280 reserved for details.
    assert page_fit_panel_width(1000, 2000, 1000, 600, 280) == 320


def test_page_fit_zero_when_dimensions_invalid():
    assert page_fit_panel_width(0, 2000, 500, 1000, 280) == 0
    assert page_fit_panel_width(1000, 2000, 0, 1000, 280) == 0
