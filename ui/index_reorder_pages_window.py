"""Indexer window: reorder scanned pages in the current document."""

from __future__ import annotations

import logging

import numpy as np
from PIL import Image
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from util.document_reorder import move_page_after
from util.lazy_document_pages import LazyDocumentPages

logger = logging.getLogger(__name__)

_BG = "#2b2b2b"


class _AutofitPageView(QWidget):
    """Single page image scaled to fit the widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self.setMinimumSize(240, 320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_pixmap(self, pixmap: QPixmap | None) -> None:
        self._pixmap = pixmap
        self.update()

    def paintEvent(self, event) -> None:
        from PyQt6.QtGui import QColor, QPainter

        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(_BG))
        if self._pixmap is None or self._pixmap.isNull():
            return
        img_w = max(1, self._pixmap.width())
        img_h = max(1, self._pixmap.height())
        avail_w = max(1, self.width())
        avail_h = max(1, self.height())
        scale = min(avail_w / img_w, avail_h / img_h)
        if scale <= 0:
            scale = 1.0
        draw_w = int(round(img_w * scale))
        draw_h = int(round(img_h * scale))
        ox = int((avail_w - draw_w) / 2)
        oy = int((avail_h - draw_h) / 2)
        painter.drawPixmap(ox, oy, draw_w, draw_h, self._pixmap)


def _pil_to_pixmap(image: Image.Image) -> QPixmap:
    rgb = image.convert("RGB")
    arr = np.array(rgb)
    height, width, _channel = arr.shape
    q_image = QImage(
        arr.data, width, height, 3 * width, QImage.Format.Format_RGB888
    )
    return QPixmap.fromImage(q_image.copy())


class _PagePanel(QWidget):
    """Label, prev/next controls, and autofit page view."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._title = QLabel(title, self)
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._title)

        self._page_label = QLabel("", self)
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._page_label)

        nav = QHBoxLayout()
        self.prev_button = QPushButton("◀ Previous", self)
        self.prev_button.setStyleSheet("background-color: #555555; color: white;")
        self.next_button = QPushButton("Next ▶", self)
        self.next_button.setStyleSheet("background-color: #555555; color: white;")
        nav.addWidget(self.prev_button, 1)
        nav.addWidget(self.next_button, 1)
        layout.addLayout(nav)

        self.view = _AutofitPageView(self)
        layout.addWidget(self.view, stretch=1)

    def set_page_text(self, text: str) -> None:
        self._page_label.setText(text)


class IndexReorderPagesWindow(QDialog):
    """
    Two-pane page reorder UI.

    Left panel is the anchor (last good page). Right panel selects a later page to
    insert after the anchor. Changing the left page resynchronises both panels.
    """

    def __init__(
        self,
        parent,
        document_path: str,
        initial_page_index: int,
    ):
        super().__init__(parent)
        self._document_path = document_path
        self._pages = LazyDocumentPages(document_path)
        self._page_count = self._pages.page_count()
        self._left = max(0, min(initial_page_index, self._page_count - 1))
        self._right = self._left
        self._exit_left = self._left

        self.setWindowTitle("Reorder pages")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowState(Qt.WindowState.WindowMaximized)
        self._asked_maximize = False

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        hint = QLabel(
            "On the left, go to the last page that is already in the correct order. "
            "On the right, go to the page that should come next and choose Move page. "
            "Changing the left page keeps both panels on the same page; you can then "
            "advance the right panel only forward.",
            self,
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        panes = QHBoxLayout()
        self._left_panel = _PagePanel("Last good page", self)
        self._right_panel = _PagePanel("Page to move after it", self)
        panes.addWidget(self._left_panel, 1)
        panes.addWidget(self._right_panel, 1)
        root.addLayout(panes, stretch=1)

        actions = QHBoxLayout()
        self._move_button = QPushButton("Move page", self)
        self._move_button.setStyleSheet("background-color: #0066aa; color: white;")
        self._move_button.clicked.connect(self._on_move_clicked)
        close_button = QPushButton("Close", self)
        close_button.clicked.connect(self.accept)
        actions.addStretch(1)
        actions.addWidget(self._move_button)
        actions.addWidget(close_button)
        root.addLayout(actions)

        self._left_panel.prev_button.clicked.connect(self._left_prev)
        self._left_panel.next_button.clicked.connect(self._left_next)
        self._right_panel.prev_button.clicked.connect(self._right_prev)
        self._right_panel.next_button.clicked.connect(self._right_next)

        self._refresh_all()

    def left_page_index(self) -> int:
        return self._exit_left

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._asked_maximize or self.isMaximized():
            return
        self._asked_maximize = True
        QTimer.singleShot(0, self.showMaximized)

    def _page_label(self, index: int) -> str:
        return f"Page {index + 1} of {self._page_count}"

    def _load_pixmap(self, index: int) -> QPixmap:
        return _pil_to_pixmap(self._pages.get_page(index))

    def _refresh_all(self) -> None:
        self._exit_left = self._left
        self._left_panel.set_page_text(self._page_label(self._left))
        self._right_panel.set_page_text(self._page_label(self._right))
        self._left_panel.view.set_pixmap(self._load_pixmap(self._left))
        self._right_panel.view.set_pixmap(self._load_pixmap(self._right))

        self._left_panel.prev_button.setEnabled(self._left > 0)
        self._left_panel.next_button.setEnabled(self._left < self._page_count - 1)
        self._right_panel.prev_button.setEnabled(self._right > self._left)
        self._right_panel.next_button.setEnabled(self._right < self._page_count - 1)
        can_move = self._right > self._left and self._right != self._left + 1
        self._move_button.setEnabled(can_move)

    def _sync_right_to_left(self) -> None:
        self._right = self._left

    def _left_prev(self) -> None:
        if self._left > 0:
            self._left -= 1
            self._sync_right_to_left()
            self._refresh_all()

    def _left_next(self) -> None:
        if self._left < self._page_count - 1:
            self._left += 1
            self._sync_right_to_left()
            self._refresh_all()

    def _right_prev(self) -> None:
        if self._right > self._left:
            self._right -= 1
            self._refresh_all()

    def _right_next(self) -> None:
        if self._right < self._page_count - 1:
            self._right += 1
            self._refresh_all()

    def _reload_document(self) -> None:
        self._pages = LazyDocumentPages(self._document_path)
        self._page_count = self._pages.page_count()
        self._left = max(0, min(self._left, self._page_count - 1))
        self._right = max(self._left, min(self._right, self._page_count - 1))

    def _on_move_clicked(self) -> None:
        if self._right <= self._left:
            return
        try:
            moved = move_page_after(self._document_path, self._left, self._right)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to reorder pages in %s", self._document_path)
            QMessageBox.critical(
                self,
                "Reorder pages",
                f"Could not move the page:\n{exc}",
            )
            return
        self._reload_document()
        if moved:
            self._right = self._left + 1
        self._refresh_all()
