"""
Live status strip — a thin horizontal bar at the bottom of the main window
that shows live updates for long-running operations (e.g. launcher chain
execution: "Step 2/3 — Waiting 3s before opening browser").

Unlike toast notifications which stack and auto-dismiss after a fixed time,
the status strip stays visible while work is in progress and fades after
a short period of inactivity.
"""
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QGraphicsOpacityEffect


class StatusStrip(QFrame):
    """Bottom strip showing step-by-step status of running operations."""

    AUTO_HIDE_DELAY_MS = 4500  # how long the strip lingers after the last update

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("StatusStrip")
        self.setFixedHeight(28)
        # Style: subtle accent strip; theming via QSS object-name selector
        self.setStyleSheet("""
            QFrame#StatusStrip {
                background-color: rgba(57, 199, 255, 0.10);
                border-top: 1px solid rgba(57, 199, 255, 0.30);
            }
            QFrame#StatusStrip QLabel {
                background: transparent;
                font-size: 12px;
                padding: 0 4px;
            }
            QFrame#StatusStrip QLabel#StatusIcon {
                font-size: 13px;
            }
            QFrame#StatusStrip QPushButton#StatusCloseBtn {
                background: transparent;
                border: none;
                color: rgba(127,127,127,0.7);
                font-size: 12px;
                padding: 0 8px;
            }
            QFrame#StatusStrip QPushButton#StatusCloseBtn:hover {
                color: rgba(255,255,255,0.95);
            }
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 4, 0)
        layout.setSpacing(8)

        self.icon_lbl = QLabel("▶")
        self.icon_lbl.setObjectName("StatusIcon")
        layout.addWidget(self.icon_lbl)

        self.text_lbl = QLabel("")
        layout.addWidget(self.text_lbl, 1)

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("StatusCloseBtn")
        self.close_btn.setFixedWidth(24)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setToolTip("Dismiss")
        self.close_btn.clicked.connect(self.hide_strip)
        layout.addWidget(self.close_btn)

        # Hidden by default
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)
        self.hide()

        # Auto-hide timer
        self._auto_hide = QTimer(self)
        self._auto_hide.setSingleShot(True)
        self._auto_hide.timeout.connect(self.hide_strip)

    def show_message(self, text: str, icon: str = "▶", auto_hide: bool = True):
        """Show or update the strip with a new message."""
        self.icon_lbl.setText(icon)
        self.text_lbl.setText(text)
        if not self.isVisible():
            self.show()
            self._fade(1.0, 180)
        else:
            self._opacity.setOpacity(1.0)
        if auto_hide:
            self._auto_hide.start(self.AUTO_HIDE_DELAY_MS)
        else:
            self._auto_hide.stop()

    def hide_strip(self):
        if not self.isVisible():
            return
        anim = self._fade(0.0, 220)
        anim.finished.connect(self.hide)

    def _fade(self, target: float, duration_ms: int):
        anim = QPropertyAnimation(self._opacity, b"opacity", self)
        anim.setDuration(duration_ms)
        anim.setStartValue(self._opacity.opacity())
        anim.setEndValue(target)
        anim.start()
        return anim
