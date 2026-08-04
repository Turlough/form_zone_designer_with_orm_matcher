"""Non-modal dialog for tuning rectangle detection sensitivity."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from util.rectangle_detection_settings import (
    DEFAULT_RECTANGLE_DETECTION_SETTINGS,
    PARAM_TOOLTIPS,
    RectangleDetectionSettings,
)

DETECT_DEBOUNCE_MS = 400
SAVE_DEBOUNCE_MS = 500


class DesignerRectangleDetectDialog(QWidget):
    """Live-tuning panel for OpenCV rectangle detection (non-modal)."""

    settings_changed = pyqtSignal(object)
    save_requested = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Rectangle detection")
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint
        )
        self.setMinimumWidth(360)
        self._block_signals = False
        self._page_number = 1
        self._detected_count = 0

        layout = QVBoxLayout(self)
        self._status_label = QLabel("Detected: —")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        form = QFormLayout()
        self._spinboxes: dict[str, QSpinBox | QDoubleSpinBox] = {}
        self._checkboxes: dict[str, QCheckBox] = {}

        int_fields = [
            ("blur_kernel_size", 3, 31, 2),
            ("dilate_iterations", 0, 30, 1),
            ("canny_low_threshold", 1, 255, 1),
            ("canny_high_threshold", 2, 255, 1),
            ("min_area", 1, 500000, 50),
            ("max_area", 100, 2000000, 100),
        ]
        float_fields = [
            ("epsilon_factor", 0.001, 0.2, 0.001, 3),
            ("overlap_threshold_value", 0.0, 1.0, 0.05, 2),
        ]

        for name, lo, hi, step in int_fields:
            spin = QSpinBox()
            spin.setRange(lo, hi)
            spin.setSingleStep(step)
            spin.setToolTip(PARAM_TOOLTIPS.get(name, ""))
            spin.valueChanged.connect(self._on_control_changed)
            self._spinboxes[name] = spin
            form.addRow(self._label_for(name), spin)

        for name, lo, hi, step, decimals in float_fields:
            spin = QDoubleSpinBox()
            spin.setRange(lo, hi)
            spin.setSingleStep(step)
            spin.setDecimals(decimals)
            spin.setToolTip(PARAM_TOOLTIPS.get(name, ""))
            spin.valueChanged.connect(self._on_control_changed)
            self._spinboxes[name] = spin
            form.addRow(self._label_for(name), spin)

        for name, label in [
            ("include_adaptive_method", "Include adaptive method"),
            ("auto_remove_inner", "Auto-remove inner rectangles"),
        ]:
            cb = QCheckBox(label)
            cb.setToolTip(PARAM_TOOLTIPS.get(name, ""))
            cb.stateChanged.connect(self._on_control_changed)
            self._checkboxes[name] = cb
            form.addRow(cb)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        reset_btn = QPushButton("Reset to defaults")
        reset_btn.setToolTip("Restore module default values (saved on next change)")
        reset_btn.clicked.connect(self._reset_to_defaults)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._detect_timer = QTimer(self)
        self._detect_timer.setSingleShot(True)
        self._detect_timer.timeout.connect(self._emit_settings_changed)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._emit_save_requested)

    @staticmethod
    def _label_for(name: str) -> str:
        return name.replace("_", " ").title()

    def set_settings(self, settings: RectangleDetectionSettings) -> None:
        self._block_signals = True
        try:
            for name, spin in self._spinboxes.items():
                value = getattr(settings, name)
                if isinstance(spin, QDoubleSpinBox):
                    spin.setValue(float(value))
                else:
                    spin.setValue(int(value))
            for name, cb in self._checkboxes.items():
                cb.setChecked(bool(getattr(settings, name)))
        finally:
            self._block_signals = False

    def current_settings(self) -> RectangleDetectionSettings:
        data = {}
        for name, spin in self._spinboxes.items():
            if isinstance(spin, QDoubleSpinBox):
                data[name] = spin.value()
            else:
                data[name] = spin.value()
        for name, cb in self._checkboxes.items():
            data[name] = cb.isChecked()
        return RectangleDetectionSettings.from_dict(data)

    def set_detection_status(self, count: int, page_number: int) -> None:
        self._detected_count = count
        self._page_number = page_number
        self._status_label.setText(
            f"Detected: {count} rectangle(s) on page {page_number}"
        )

    def _on_control_changed(self, *_args) -> None:
        if self._block_signals:
            return
        self._detect_timer.start(DETECT_DEBOUNCE_MS)
        self._save_timer.start(SAVE_DEBOUNCE_MS)

    def _emit_settings_changed(self) -> None:
        self.settings_changed.emit(self.current_settings())

    def _emit_save_requested(self) -> None:
        self.save_requested.emit(self.current_settings())

    def _reset_to_defaults(self) -> None:
        self.set_settings(DEFAULT_RECTANGLE_DETECTION_SETTINGS)
        self._on_control_changed()

    def flush_pending(self) -> None:
        """Emit any pending debounced detect/save immediately."""
        if self._detect_timer.isActive():
            self._detect_timer.stop()
            self._emit_settings_changed()
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._emit_save_requested()
