from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QListWidget,
    QListWidgetItem,
    QTextEdit,
    QDialogButtonBox,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QTimer
from PyQt6.QtGui import QGuiApplication


MARGIN = 8
MIN_DIALOG_HEIGHT = 200
FRAME_EXTRA_ESTIMATE = 40
COMMENT_EDIT_MAX_HEIGHT = 100


def pos_left_of_rect(
    rect_left: int,
    rect_top: int,
    rect_height: int,
    dialog_w: int,
    dialog_h: int,
    margin: int = MARGIN,
) -> tuple[int, int]:
    """Preferred top-left: left of the rect, vertically centered on it."""
    x = rect_left - dialog_w - margin
    y = rect_top + (rect_height - dialog_h) // 2
    return x, y


def clamp_window_to_available(
    x: int,
    y: int,
    width: int,
    height: int,
    avail_x: int,
    avail_y: int,
    avail_w: int,
    avail_h: int,
) -> tuple[int, int]:
    """Keep a window of the given size fully inside available screen geometry."""
    max_x = avail_x + avail_w - width
    max_y = avail_y + avail_h - height
    if max_x < avail_x:
        x = avail_x
    else:
        x = min(max(x, avail_x), max_x)
    if max_y < avail_y:
        y = avail_y
    else:
        y = min(max(y, avail_y), max_y)
    return x, y


def capped_dialog_height(
    desired: int,
    available: int,
    frame_extra: int = FRAME_EXTRA_ESTIMATE,
    min_h: int = MIN_DIALOG_HEIGHT,
) -> int:
    """Cap client height so the framed window can fit on the available screen."""
    max_h = max(min_h, available - frame_extra)
    return max(min_h, min(desired, max_h))


class IndexCommentDialog(QDialog):
    """
    Dialog for adding or editing QC comments for a field.

    - Shows a list of preset comments loaded from qc_comments.txt.
    - Selecting a preset populates the editable text box.
    - Submit confirms the comment; Cancel closes without changes.
    - Positioned to the left of the field row; kept fully on the available screen.
    """

    # Emitted when the user submits a comment.
    # Payload: (field_name: str, comment: str)
    comment_submitted = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)
        self._field_name: str = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Preset comments list (scrolls when the dialog is capped to the screen)
        self._preset_list = QListWidget()
        self._preset_list.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._preset_list.itemClicked.connect(self._on_preset_clicked)
        layout.addWidget(self._preset_list, stretch=1)

        # Editable comment box
        self._comment_edit = QTextEdit()
        self._comment_edit.setPlaceholderText("Enter comment...")
        self._comment_edit.setMaximumHeight(COMMENT_EDIT_MAX_HEIGHT)
        layout.addWidget(self._comment_edit)

        # Buttons (Submit default, Cancel)
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Submit")
        button_box.button(QDialogButtonBox.StandardButton.Ok).setDefault(True)
        button_box.accepted.connect(self._on_submit)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def set_field(self, field_name: str, initial_comment: str, presets: list[str]):
        """Set the target field, initial comment text, and preset list."""
        self._field_name = field_name or ""
        self.setWindowTitle(self._field_name or "Field Comment")

        # Populate presets list
        self._preset_list.clear()
        for text in presets or []:
            text = (text or "").strip()
            if not text:
                continue
            self._preset_list.addItem(QListWidgetItem(text))

        # Set initial comment text
        self._comment_edit.blockSignals(True)
        self._comment_edit.setPlainText(initial_comment or "")
        self._comment_edit.blockSignals(False)

    def show_left_of_rect(self, global_rect: QRect):
        """
        Position the dialog to the left of the given global QRect representing
        the field on screen, vertically centered relative to the field, then
        clamp so the full window (including Submit/Cancel) stays on screen.
        """
        geo = self._available_geometry(global_rect.center())
        self.adjustSize()
        hint = self.sizeHint()
        width = max(self.minimumWidth(), hint.width())
        height = capped_dialog_height(hint.height(), geo.height())
        self.resize(width, height)

        x, y = pos_left_of_rect(
            global_rect.left(),
            global_rect.top(),
            global_rect.height(),
            width,
            height,
        )
        x, y = clamp_window_to_available(
            x, y, width, height, geo.x(), geo.y(), geo.width(), geo.height()
        )
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        QTimer.singleShot(0, self._finalize_on_screen)

    def _available_geometry(self, point=None) -> QRect:
        screen = None
        if point is not None:
            screen = QGuiApplication.screenAt(point)
        if screen is None and self.isVisible():
            screen = self.screen()
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return QRect(0, 0, 1920, 1080)
        return screen.availableGeometry()

    def _finalize_on_screen(self) -> None:
        """Shrink and clamp after the window frame (title bar) is known."""
        geo = self._available_geometry()
        frame = self.frameGeometry()
        extra = max(0, frame.height() - self.height())
        if frame.height() > geo.height():
            self.resize(self.width(), max(MIN_DIALOG_HEIGHT, geo.height() - extra))
            frame = self.frameGeometry()
        x, y = clamp_window_to_available(
            frame.x(),
            frame.y(),
            frame.width(),
            frame.height(),
            geo.x(),
            geo.y(),
            geo.width(),
            geo.height(),
        )
        self.move(x, y)

    def _on_preset_clicked(self, item: QListWidgetItem):
        """Populate the comment edit box when a preset is selected."""
        if not item:
            return
        text = item.text() or ""
        self._comment_edit.blockSignals(True)
        self._comment_edit.setPlainText(text)
        self._comment_edit.blockSignals(False)

    def _on_submit(self):
        """Emit the submitted comment and close the dialog."""
        if not self._field_name:
            self.accept()
            return
        comment = self._comment_edit.toPlainText().strip()
        self.comment_submitted.emit(self._field_name, comment)
        self.accept()
