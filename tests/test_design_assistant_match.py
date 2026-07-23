"""Rect association for design assistant (no live API)."""

from runtime_assistants.design_assistant.match import (
    match_fields_to_rects,
    resolve_rect,
)


def test_resolve_rect_by_id():
    cv = [(10, 20, 15, 15), (100, 200, 12, 12)]
    field = {"rect_id": 1, "answer_located": True}
    rect, rid, located = resolve_rect(field, cv)
    assert located and rid == 1 and rect == cv[1]


def test_resolve_rect_missing():
    field = {"answer_located": False}
    rect, rid, located = resolve_rect(field, [(0, 0, 10, 10)])
    assert not located and rect is None


def test_resolve_rect_page_hint_iou():
    cv = [(100, 100, 20, 20), (300, 300, 10, 10)]
    field = {
        "answer_located": True,
        "page_x": 98,
        "page_y": 102,
        "page_width": 22,
        "page_height": 18,
    }
    rect, rid, located = resolve_rect(field, cv)
    assert located and rid == 0 and rect == cv[0]


def test_match_fields_fiducial_relative():
    cv = [(50, 60, 14, 14)]
    fields = [
        {
            "_type": "Tickbox",
            "name": "A",
            "summary": "A",
            "rect_id": 0,
            "answer_located": True,
        }
    ]
    matched, warnings = match_fields_to_rects(
        fields, cv, fiducial_top_left=(10, 20)
    )
    assert not warnings
    assert matched[0]["x"] == 40
    assert matched[0]["y"] == 40
    assert matched[0]["width"] == 14
    assert matched[0]["answer_located"] is True


def test_match_radio_group_union():
    cv = [(10, 10, 10, 10), (30, 10, 10, 10)]
    fields = [
        {
            "_type": "RadioGroup",
            "name": "G",
            "radio_buttons": [
                {"name": "Y", "rect_id": 0},
                {"name": "N", "rect_id": 1},
            ],
        }
    ]
    matched, warnings = match_fields_to_rects(
        fields, cv, fiducial_top_left=None
    )
    assert not warnings
    g = matched[0]
    assert g["x"] == 10 and g["y"] == 10
    assert g["width"] == 30 and g["height"] == 10
    assert len(g["radio_buttons"]) == 2


def test_unmatched_warning():
    fields = [{"_type": "TextField", "name": "Missing", "answer_located": True}]
    matched, warnings = match_fields_to_rects(fields, [], fiducial_top_left=None)
    assert matched[0]["answer_located"] is False
    assert any("Missing" in w for w in warnings)
