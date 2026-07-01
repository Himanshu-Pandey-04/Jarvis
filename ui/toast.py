"""
In-app toast notifications — theme-aware popups that slide in from the
bottom-right of the main window. Unlike OS tray balloons, these inherit
the app's QSS so they match the active theme (including JARVIS HUD with
its cyan glow).

Multiple toasts stack vertically. Auto-dismiss after a few seconds; click
to dismiss immediately.
"""
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, pyqtSignal,
)
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsOpacityEffect,
    QPushButton, QWidget,
)


TOAST_WIDTH = 360
TOAST_HEIGHT_MIN = 64
TOAST_SPACING = 8
TOAST_MARGIN = 16
TOAST_DURATION_MS = 4200


class Toast(QFrame):
    """One toast — title + body, dismiss button, fades out after timeout."""
    closed = pyqtSignal(object)

    def __init__(self, parent, title: str, body: str = "", kind: str = "info"):
        super().__init__(parent)
        self.setObjectName("Toast")
        # Make it borderless and ignore the parent's layout
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMinimumWidth(TOAST_WIDTH)
        self.setMaximumWidth(TOAST_WIDTH)
        self.setMinimumHeight(TOAST_HEIGHT_MIN)
        # Style based on kind — accent color comes from QSS, but the left strip
        # is overridden inline to use a kind-specific color
        kind_color = {
            "info":    "#39C7FF",
            "success": "#34D399",
            "warning": "#FBBF24",
            "error":   "#F87171",
        }.get(kind, "#39C7FF")
        self.setStyleSheet(f"""
            QFrame#Toast {{
                background-color: palette(window);
                border: 1px solid rgba(127,127,127,0.30);
                border-left: 4px solid {kind_color};
                border-radius: 8px;
            }}
            QFrame#Toast QLabel#ToastTitle {{
                background: transparent;
                font-weight: 600;
                font-size: 13px;
            }}
            QFrame#Toast QLabel#ToastBody {{
                background: transparent;
                font-size: 12px;
            }}
            QFrame#Toast QPushButton#ToastClose {{
                background: transparent;
                border: none;
                padding: 0;
                color: rgba(127,127,127,0.7);
                font-size: 14px;
            }}
            QFrame#Toast QPushButton#ToastClose:hover {{
                color: rgba(255,255,255,0.95);
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 12, 10)
        layout.setSpacing(2)

        head = QHBoxLayout()
        head.setSpacing(8)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("ToastTitle")
        title_lbl.setWordWrap(True)
        head.addWidget(title_lbl, 1)
        close_btn = QPushButton("✕")
        close_btn.setObjectName("ToastClose")
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Dismiss")
        close_btn.clicked.connect(self._dismiss)
        head.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(head)

        if body:
            body_lbl = QLabel(body)
            body_lbl.setObjectName("ToastBody")
            body_lbl.setWordWrap(True)
            body_lbl.setProperty("class", "Muted")
            layout.addWidget(body_lbl)

        # Fade opacity effect
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)
        self._fade_in = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade_in.setDuration(180)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._fade_out = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade_out.setDuration(220)
        self._fade_out.setStartValue(1.0)
        self._fade_out.setEndValue(0.0)
        self._fade_out.setEasingCurve(QEasingCurve.Type.InCubic)
        self._fade_out.finished.connect(self._finalize)

        self._auto_close_timer = QTimer(self)
        self._auto_close_timer.setSingleShot(True)
        self._auto_close_timer.timeout.connect(self._dismiss)

    def show_animated(self):
        self.show()
        self._fade_in.start()
        self._auto_close_timer.start(TOAST_DURATION_MS)

    def _dismiss(self):
        if self._auto_close_timer.isActive():
            self._auto_close_timer.stop()
        self._fade_out.start()

    def _finalize(self):
        self.closed.emit(self)
        self.deleteLater()

    def mousePressEvent(self, e):
        # Click anywhere on the body to dismiss
        if e.button() == Qt.MouseButton.LeftButton:
            self._dismiss()
        super().mousePressEvent(e)


class ToastManager:
    """Owns the toast stack and positions toasts relative to the main window."""
    def __init__(self, main_window):
        self.win = main_window
        self._toasts: list[Toast] = []

    def show(self, title: str, body: str = "", kind: str = "info"):
        # Cap to 4 visible at a time — drop oldest
        while len(self._toasts) >= 4:
            self._toasts[0]._dismiss()
            # Optimistically drop from our list; closed signal will also remove
            self._toasts.pop(0)

        t = Toast(self.win, title, body, kind)
        t.closed.connect(self._on_closed)
        self._toasts.append(t)
        self._reposition()
        t.show_animated()

    def _on_closed(self, toast):
        if toast in self._toasts:
            self._toasts.remove(toast)
        self._reposition()

    def _reposition(self):
        # Stack toasts upward from bottom-right of the main window
        if not self.win or not self.win.isVisible():
            return
        win_rect = self.win.rect()
        x = win_rect.right() - TOAST_WIDTH - TOAST_MARGIN
        y = win_rect.bottom() - TOAST_MARGIN
        for t in reversed(self._toasts):
            t.adjustSize()
            h = max(TOAST_HEIGHT_MIN, t.sizeHint().height())
            y -= h
            t.setGeometry(x, y, TOAST_WIDTH, h)
            y -= TOAST_SPACING
            t.raise_()
