"""
Reusable UI widgets shared across modules.
"""
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
    QSizePolicy, QScrollArea, QGraphicsDropShadowEffect, QToolButton,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor


class Card(QFrame):
    """A surface panel with rounded border. Subclass or compose."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setProperty("class", "Card")
        # Apply subtle drop-shadow for depth
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 25))
        self.setGraphicsEffect(shadow)


class SectionHeader(QWidget):
    """Big page header with optional action button on the right."""
    action_clicked = pyqtSignal()

    def __init__(self, title: str, subtitle: str = "", action_text: str = "", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 12)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title_lbl = QLabel(title)
        title_lbl.setProperty("class", "SectionHeader")
        text_col.addWidget(title_lbl)
        if subtitle:
            sub_lbl = QLabel(subtitle)
            sub_lbl.setProperty("class", "SectionSub")
            sub_lbl.setWordWrap(True)
            text_col.addWidget(sub_lbl)
        layout.addLayout(text_col, stretch=1)

        if action_text:
            btn = QPushButton(action_text)
            btn.setProperty("primary", True)
            btn.clicked.connect(self.action_clicked.emit)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignTop)


class TagLabel(QLabel):
    """A small pill-shaped label."""
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setProperty("class", "Tag")
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)


class IconTextButton(QPushButton):
    """Big card-style button used for one-click links/apps grid."""
    def __init__(self, icon: str, text: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self._icon = icon
        self._text = text
        self._subtitle = subtitle
        self.setMinimumHeight(72)
        self.setMinimumWidth(160)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Use plain text + a layout, not HTML — so themes apply correctly
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 18px; background: transparent;")
        text_lbl = QLabel(text)
        text_lbl.setStyleSheet("font-weight: 600; font-size: 13px; background: transparent;")
        layout.addWidget(icon_lbl)
        layout.addWidget(text_lbl)
        if subtitle:
            sub_lbl = QLabel(subtitle)
            sub_lbl.setProperty("class", "Muted")
            sub_lbl.setStyleSheet("background: transparent;")
            layout.addWidget(sub_lbl)


class ScrollContainer(QScrollArea):
    """Scrollable container with sensible defaults."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        # Inner widget
        self._inner = QWidget()
        self._inner_layout = QVBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(24, 24, 24, 24)
        self._inner_layout.setSpacing(16)
        self.setWidget(self._inner)

    def add(self, widget: QWidget):
        self._inner_layout.addWidget(widget)

    def add_stretch(self):
        self._inner_layout.addStretch()

    def layout(self):
        return self._inner_layout


class EmptyState(QFrame):
    """Friendly empty state used when a module list is empty."""
    def __init__(self, icon: str, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        # Tall, generous breathing room so the text isn't clipped when
        # placed inside grids or small cards.
        self.setMinimumHeight(220)
        from PyQt6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 32, 20, 32)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(14)

        layout.addStretch(1)

        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 48px; padding: 6px 0; background: transparent;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setMinimumHeight(60)
        layout.addWidget(icon_lbl)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 16px; font-weight: 600; padding: 4px 0; background: transparent;")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setMinimumHeight(28)
        layout.addWidget(title_lbl)

        sub_lbl = QLabel(subtitle)
        sub_lbl.setProperty("class", "Muted")
        sub_lbl.setStyleSheet("padding: 4px 0; background: transparent;")
        sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_lbl.setWordWrap(True)
        sub_lbl.setMinimumHeight(48)
        sub_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)
        layout.addWidget(sub_lbl)

        layout.addStretch(1)


class AnimatedEdge(QWidget):
    """
    A 2-pixel-tall animated gradient bar — used as the top accent on the
    main window for a JARVIS-inspired flowing color edge. Subtle, not flashy:
    a single hue cycle every ~6 seconds.
    """
    def __init__(self, color_a="#39C7FF", color_b="#1F4FD9", color_c="#7AE2FF", parent=None):
        super().__init__(parent)
        from PyQt6.QtGui import QColor
        self._a = QColor(color_a)
        self._b = QColor(color_b)
        self._c = QColor(color_c)
        self._phase = 0.0
        self.setFixedHeight(2)
        from PyQt6.QtCore import QTimer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)  # 25 fps

    def set_colors(self, a: str, b: str, c: str = None):
        from PyQt6.QtGui import QColor
        self._a = QColor(a); self._b = QColor(b)
        if c:
            self._c = QColor(c)
        self.update()

    def _tick(self):
        self._phase = (self._phase + 0.004) % 1.0
        self.update()

    def paintEvent(self, _event):
        from PyQt6.QtGui import QPainter, QLinearGradient
        if self.width() <= 0:
            return
        painter = QPainter(self)
        w = self.width()
        offset = self._phase * w * 2  # span twice the width so the gradient flows continuously
        g = QLinearGradient(offset - w * 2, 0, offset, 0)
        g.setColorAt(0.0, self._a)
        g.setColorAt(0.33, self._b)
        g.setColorAt(0.66, self._c)
        g.setColorAt(1.0, self._a)
        painter.fillRect(self.rect(), g)
        painter.end()
