"""Caret goes to the close-up value box when a text field is opened."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import QApplication

from fields import DecimalField, IntegerField, TextField
from ui.index_details_panel import IndexDetailPanel
from ui.index_text_dialog import IndexTextDialog


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _show_panel(field, value: str) -> IndexDetailPanel:
    panel = IndexDetailPanel()
    panel.set_current_field(field, field_values={field.name: value})
    panel.show()
    return panel


def test_value_editor_takes_focus_when_text_dialog_is_shown(qapp):
    field = TextField((0, 0, 0), "Name", 0, 0, 40, 12)
    panel = _show_panel(field, "ada")
    dialog = IndexTextDialog()
    try:
        dialog.set_field(field.name, "ada", field=field)
        dialog.show_under_rect(QPoint(10, 10), 80)
        assert dialog.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        panel.focus_value_editor()
        qapp.processEvents()
        assert qapp.focusWidget() is panel.value_text_edit
        assert panel.value_text_edit.textCursor().hasSelection()
        assert not dialog._line_edit.hasFocus()
    finally:
        dialog.close()
        panel.close()


def test_integer_and_decimal_use_the_same_value_editor(qapp):
    integer = IntegerField((0, 0, 0), "Qty", 0, 0, 40, 12)
    decimal = DecimalField((0, 0, 0), "Amount", 0, 0, 40, 12)
    panel = _show_panel(integer, "12")
    dialog = IndexTextDialog()
    try:
        panel.focus_value_editor()
        qapp.processEvents()
        assert qapp.focusWidget() is panel.value_text_edit

        panel.set_current_field(decimal, field_values={"Amount": "1.5"})
        dialog.set_field(decimal.name, "1.5", field=decimal)
        dialog.show_under_rect(QPoint(0, 0), 100)
        qapp.processEvents()
        panel.focus_value_editor()
        qapp.processEvents()
        assert qapp.focusWidget() is panel.value_text_edit
        assert panel.value_text_edit.toPlainText() == "1.5"
        assert not dialog._line_edit.hasFocus()
    finally:
        dialog.close()
        panel.close()
