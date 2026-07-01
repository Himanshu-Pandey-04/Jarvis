"""
Neural network background — an animated, low-opacity holographic backdrop
used by the JARVIS HUD theme.

Renders:
  - Scattered glowing nodes (subtle pulse on each)
  - Lines connecting near-neighbors (faint cyan)
  - Light pulses traveling along each line cyclically

Lightweight: nodes/lines are computed once, only the per-frame animation
state advances. QTimer at 25 FPS keeps it smooth without burning CPU.
"""
import math
import random
from PyQt6.QtCore import Qt, QPointF, QTimer
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QRadialGradient
from PyQt6.QtWidgets import QWidget


class NeuralBackground(QWidget):
    def __init__(self, parent=None, palette=None):
        super().__init__(parent)
        # Make sure mouse events pass through to the real UI on top
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        # Don't fight the layout — we get sized by the parent
        self._palette = palette or {
            "accent": "#39C7FF",
            "bg": "#040A14",
        }
        self._nodes: list[tuple[float, float, float]] = []   # x_ratio, y_ratio, pulse_phase
        self._edges: list[tuple[int, int, float]] = []        # i, j, phase
        self._t = 0.0
        self._initialized = False

        # 25 FPS animation
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)

    def set_palette(self, palette: dict):
        self._palette = palette
        self.update()

    def _ensure_initialized(self):
        if self._initialized:
            return
        if self.width() < 50 or self.height() < 50:
            return
        # Generate nodes scattered in normalized coords
        random.seed(11)
        n_nodes = 26
        self._nodes = []
        for _ in range(n_nodes):
            self._nodes.append((random.random(), random.random(), random.random() * math.tau))

        # Connect each node to its 2 nearest neighbors (max), pruning duplicates
        edges = set()
        for i, (xi, yi, _) in enumerate(self._nodes):
            dists = []
            for j, (xj, yj, _) in enumerate(self._nodes):
                if i == j: continue
                d = (xi - xj) ** 2 + (yi - yj) ** 2
                dists.append((d, j))
            dists.sort()
            for _, j in dists[:2]:
                a, b = sorted((i, j))
                edges.add((a, b))
        self._edges = [(a, b, random.random() * math.tau) for (a, b) in edges]
        self._initialized = True

    def _tick(self):
        self._t += 0.035  # was 0.05 — slower pulse cycle
        self.update()

    def resizeEvent(self, e):
        # Keep position-ratios; just trigger repaint
        self._initialized = False  # let it re-evaluate node positions on new size
        self._ensure_initialized()
        return super().resizeEvent(e)

    def paintEvent(self, _e):
        self._ensure_initialized()
        if not self._initialized or not self._nodes:
            return

        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Don't paint our own background — let the underlying widget show through.

        accent = QColor(self._palette.get("accent", "#39C7FF"))
        # Faint version for lines — slightly brighter so they read at thicker stroke
        line_color = QColor(accent); line_color.setAlphaF(0.14)
        # Lit version for pulses
        pulse_color = QColor(accent); pulse_color.setAlphaF(0.65)

        # Draw edges first (lines) — thicker than before
        pen = QPen(line_color)
        pen.setWidthF(1.6)
        p.setPen(pen)
        # Cache absolute node positions
        positions = [(nx * w, ny * h) for (nx, ny, _) in self._nodes]
        for (a, b, phase) in self._edges:
            xa, ya = positions[a]
            xb, yb = positions[b]
            p.drawLine(QPointF(xa, ya), QPointF(xb, yb))

        # Draw traveling pulses on each edge — slower (0.18 vs 0.35 per second-ish)
        for (a, b, phase) in self._edges:
            xa, ya = positions[a]
            xb, yb = positions[b]
            # Position along edge: 0..1 cycling — slower travel speed
            t_local = ((self._t * 0.18) + phase / math.tau) % 1.0
            px = xa + (xb - xa) * t_local
            py = ya + (yb - ya) * t_local
            # Soft glow
            grad = QRadialGradient(QPointF(px, py), 7.0)
            bright = QColor(accent); bright.setAlphaF(0.55)
            faded  = QColor(accent); faded.setAlphaF(0.0)
            grad.setColorAt(0.0, bright)
            grad.setColorAt(1.0, faded)
            p.setBrush(QBrush(grad)); p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(px, py), 7.0, 7.0)
            # Tiny core
            core = QColor(accent); core.setAlphaF(0.85)
            p.setBrush(QBrush(core))
            p.drawEllipse(QPointF(px, py), 1.6, 1.6)

        # Draw nodes (with soft pulse)
        for i, (nx, ny, phase) in enumerate(self._nodes):
            x = nx * w
            y = ny * h
            pulse = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(self._t + phase))
            node_color = QColor(accent); node_color.setAlphaF(0.25 * pulse)
            # Halo
            grad = QRadialGradient(QPointF(x, y), 9.0)
            grad.setColorAt(0.0, node_color)
            grad.setColorAt(1.0, QColor(accent.red(), accent.green(), accent.blue(), 0))
            p.setBrush(QBrush(grad)); p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(x, y), 9.0, 9.0)
            # Solid
            core = QColor(accent); core.setAlphaF(0.6 * pulse)
            p.setBrush(QBrush(core))
            p.drawEllipse(QPointF(x, y), 2.0, 2.0)

        p.end()
