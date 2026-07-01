"""
News & Weather

Top of page: live weather card (Open-Meteo API, no key needed) +
top headlines panel (RSS from BBC + Times of India, no key needed).

Below: a curated, slim link-set to major aggregators. Users can add their
own. If network access is blocked (corp firewall), the live cards fall
back gracefully with a friendly message and the curated links still work.
"""
import json
import re
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
from collections import OrderedDict
from datetime import datetime
from html import unescape

from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QFrame, QLineEdit,
    QDialog, QDialogButtonBox, QFormLayout, QComboBox, QMessageBox, QInputDialog,
    QMenu, QWidget,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QPointF, QByteArray
from PyQt6.QtGui import QAction, QPainter, QBrush, QColor, QPixmap

from modules.base import Module
from ui.widgets import SectionHeader, Card, EmptyState, ScrollContainer
from core.search import SearchResult, fuzzy_score


# Curated defaults — slimmed per user request
DEFAULT_SOURCES = [
    {"name": "Google Weather", "url": "https://www.google.com/search?q=weather",
     "icon": "☀️", "category": "Weather", "notes": "Detailed forecast"},

    {"name": "Times of India", "url": "https://timesofindia.indiatimes.com/",
     "icon": "📰", "category": "India News", "notes": ""},
    {"name": "The Hindu", "url": "https://www.thehindu.com/",
     "icon": "📰", "category": "India News", "notes": ""},
    {"name": "Economic Times", "url": "https://economictimes.indiatimes.com/",
     "icon": "💼", "category": "India News", "notes": "Business + markets"},

    {"name": "BBC News", "url": "https://www.bbc.com/news",
     "icon": "🌍", "category": "World News", "notes": ""},
    {"name": "Reuters", "url": "https://www.reuters.com/",
     "icon": "🌍", "category": "World News", "notes": "Wire service"},
    {"name": "Bloomberg", "url": "https://www.bloomberg.com/",
     "icon": "💹", "category": "World News", "notes": "Markets + finance"},

    {"name": "Hacker News", "url": "https://news.ycombinator.com/",
     "icon": "🧑‍💻", "category": "Tech", "notes": "Tech community"},
    {"name": "TechCrunch", "url": "https://techcrunch.com/",
     "icon": "🚀", "category": "Tech", "notes": "Startups + launches"},
]


# ----------------------------------------------------------------------------
# Network helpers — stdlib only, short timeouts
# ----------------------------------------------------------------------------
NET_TIMEOUT = 6  # seconds

def _http_get(url: str, timeout: int = NET_TIMEOUT) -> str | None:
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (JARVIS desktop)",
            "Accept": "*/*",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.decode("latin-1", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, socket.timeout, OSError):
        return None


def _http_get_bytes(url: str, timeout: int = NET_TIMEOUT) -> bytes | None:
    """HTTP GET returning raw bytes — for image thumbnails."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (JARVIS desktop)",
            "Accept": "image/*,*/*",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, socket.timeout, OSError):
        return None


def _wmo_to_emoji(code: int) -> tuple[str, str]:
    table = {
        0: ("☀️", "Clear"),
        1: ("🌤", "Mostly clear"),
        2: ("⛅", "Partly cloudy"),
        3: ("☁️", "Overcast"),
        45: ("🌫", "Fog"),
        48: ("🌫", "Fog"),
        51: ("🌦", "Light drizzle"),
        53: ("🌦", "Drizzle"),
        55: ("🌧", "Heavy drizzle"),
        61: ("🌧", "Light rain"),
        63: ("🌧", "Rain"),
        65: ("🌧", "Heavy rain"),
        71: ("🌨", "Light snow"),
        73: ("🌨", "Snow"),
        75: ("❄️", "Heavy snow"),
        80: ("🌦", "Rain showers"),
        81: ("🌧", "Showers"),
        82: ("⛈", "Violent showers"),
        95: ("⛈", "Thunderstorm"),
        96: ("⛈", "Thunderstorm w/ hail"),
        99: ("⛈", "Severe thunderstorm"),
    }
    return table.get(code, ("🌡", "Weather"))


def fetch_weather(lat: float, lon: float) -> dict | None:
    url = ("https://api.open-meteo.com/v1/forecast"
           f"?latitude={lat}&longitude={lon}"
           "&current=temperature_2m,relative_humidity_2m,weather_code,"
           "wind_speed_10m,apparent_temperature,pressure_msl,uv_index,"
           "precipitation,cloud_cover,wind_direction_10m"
           "&daily=temperature_2m_max,temperature_2m_min,sunrise,sunset,"
           "precipitation_probability_max,uv_index_max"
           "&forecast_days=1"
           "&temperature_unit=celsius&wind_speed_unit=kmh&timezone=auto")
    body = _http_get(url)
    if not body:
        return None
    try:
        data = json.loads(body)
        cur = data.get("current", {})
        daily = data.get("daily", {}) or {}
        def _first(k, default=None):
            v = daily.get(k, []) or []
            return v[0] if v else default
        return {
            "temp": cur.get("temperature_2m"),
            "feels_like": cur.get("apparent_temperature"),
            "humidity": cur.get("relative_humidity_2m"),
            "wind": cur.get("wind_speed_10m"),
            "wind_dir": cur.get("wind_direction_10m"),
            "pressure": cur.get("pressure_msl"),
            "uv": cur.get("uv_index"),
            "precip": cur.get("precipitation"),
            "clouds": cur.get("cloud_cover"),
            "code": cur.get("weather_code", 0),
            "temp_max": _first("temperature_2m_max"),
            "temp_min": _first("temperature_2m_min"),
            "sunrise": _first("sunrise"),
            "sunset": _first("sunset"),
            "rain_chance": _first("precipitation_probability_max"),
            "uv_max": _first("uv_index_max"),
        }
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def geocode_city(city: str) -> dict | None:
    """Resolve a city name to lat/lon using Open-Meteo's free geocoding API.
    Returns {city, country, lat, lon} or None."""
    if not city or not city.strip():
        return None
    url = (f"https://geocoding-api.open-meteo.com/v1/search"
           f"?name={urllib.parse.quote(city.strip())}&count=1&language=en&format=json")
    body = _http_get(url)
    if not body:
        return None
    try:
        data = json.loads(body)
        results = data.get("results") or []
        if not results:
            return None
        r = results[0]
        return {
            "lat": r.get("latitude"),
            "lon": r.get("longitude"),
            "city": r.get("name", city.strip()),
            "country": r.get("country", ""),
        }
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def fetch_geolocation() -> dict | None:
    """IP-based geolocation. Often blocked by corporate firewalls."""
    body = _http_get("https://ipapi.co/json/")
    if not body:
        return None
    try:
        data = json.loads(body)
        if data.get("latitude") is not None:
            return {
                "lat": data["latitude"],
                "lon": data["longitude"],
                "city": data.get("city", "Unknown"),
                "country": data.get("country_name", ""),
            }
    except (json.JSONDecodeError, KeyError, TypeError):
        pass
    return None


def _strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s or "")
    return unescape(s).strip()


def fetch_rss_headlines(url: str, limit: int = 5) -> list[dict]:
    body = _http_get(url)
    if not body:
        return []
    try:
        body = body.lstrip("\ufeff").lstrip()
        root = ET.fromstring(body)
    except ET.ParseError:
        return []

    def _extract_image(item) -> str:
        """Try several common RSS variants for a thumbnail URL."""
        # 1) <media:thumbnail url="..."/> or <media:content url="..."/>
        for child in item.iter():
            ctag = child.tag.split("}")[-1]
            if ctag in ("thumbnail", "content"):
                u = child.attrib.get("url", "").strip()
                if u and u.startswith(("http://", "https://")):
                    return u
        # 2) <enclosure url="..." type="image/..."/>
        for child in item.iter():
            ctag = child.tag.split("}")[-1]
            if ctag == "enclosure":
                u = child.attrib.get("url", "").strip()
                if u and u.startswith(("http://", "https://")):
                    return u
        # 3) <description>...<img src="..."/></description>
        for child in item.iter():
            ctag = child.tag.split("}")[-1]
            if ctag in ("description", "summary"):
                text = child.text or ""
                m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', text, re.IGNORECASE)
                if m and m.group(1).startswith(("http://", "https://")):
                    return m.group(1)
        return ""

    def _extract_category(item) -> str:
        for child in item:
            ctag = child.tag.split("}")[-1]
            if ctag == "category":
                txt = (child.text or "").strip()
                if txt: return txt
        return ""

    items = []
    for it in root.iter():
        tag = it.tag.split("}")[-1]
        if tag != "item":
            continue
        title = ""; link = ""
        for child in it:
            ctag = child.tag.split("}")[-1]
            if ctag == "title": title = _strip_html(child.text or "")
            elif ctag == "link": link = (child.text or "").strip()
        if title and link:
            items.append({
                "title": title,
                "link": link,
                "image": _extract_image(it),
                "category": _extract_category(it),
            })
            if len(items) >= limit: break
    if not items:
        for it in root.iter():
            tag = it.tag.split("}")[-1]
            if tag != "entry":
                continue
            title = ""; link = ""
            for child in it:
                ctag = child.tag.split("}")[-1]
                if ctag == "title": title = _strip_html(child.text or "")
                elif ctag == "link": link = child.attrib.get("href", (child.text or "").strip())
            if title and link:
                items.append({
                    "title": title,
                    "link": link,
                    "image": _extract_image(it),
                    "category": _extract_category(it),
                })
                if len(items) >= limit: break
    return items


# ----------------------------------------------------------------------------
# Pulsing dot — a small animated circle indicating "live" data per headline.
# ----------------------------------------------------------------------------
class PulsingDot(QWidget):
    """A small dot whose alpha softly pulses to look live. Color picked by
    importance/source."""
    def __init__(self, color="#39C7FF", size=10, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._size = size
        self._phase = 0.0
        self.setFixedSize(size + 8, size + 8)
        # Light timer — every 80ms is enough for smooth pulse
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self._timer.start(80)

    def _step(self):
        self._phase = (self._phase + 0.12) % (2 * 3.14159)
        self.update()

    def paintEvent(self, _e):
        import math
        from PyQt6.QtGui import QPainter, QRadialGradient
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Pulse alpha between 0.3 and 1.0
        pulse = 0.3 + 0.7 * (0.5 + 0.5 * math.sin(self._phase))
        cx = self.width() / 2
        cy = self.height() / 2

        # Outer glow halo
        halo = QColor(self._color)
        halo.setAlphaF(0.20 * pulse)
        grad = QRadialGradient(QPointF(cx, cy), self._size)
        grad.setColorAt(0.0, halo)
        end = QColor(self._color); end.setAlphaF(0)
        grad.setColorAt(1.0, end)
        p.setBrush(QBrush(grad)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), self._size, self._size)

        # Solid core
        core = QColor(self._color); core.setAlphaF(pulse)
        p.setBrush(QBrush(core))
        p.drawEllipse(QPointF(cx, cy), self._size * 0.35, self._size * 0.35)
        p.end()


# ----------------------------------------------------------------------------
# Background-fetch signals (thread → UI thread)
# ----------------------------------------------------------------------------
class _NewsSignals(QObject):
    weather_ready = pyqtSignal(dict)
    weather_failed = pyqtSignal(str)
    headlines_ready = pyqtSignal(str, list)
    headlines_failed = pyqtSignal(str, str)
    image_ready = pyqtSignal(str, bytes)  # url, raw bytes


# ----------------------------------------------------------------------------
# Source edit dialog
# ----------------------------------------------------------------------------
class NewsSourceDialog(QDialog):
    DEFAULT_CATS = ["Weather", "India News", "World News", "Tech", "Business", "Sports", "Science"]

    def __init__(self, parent=None, item=None, groups=None):
        super().__init__(parent)
        self.setWindowTitle("Edit source" if item else "Add news source")
        self.setMinimumWidth(440)
        form = QFormLayout(self)
        self.name_in = QLineEdit(item["name"] if item else "")
        self.url_in  = QLineEdit(item["url"] if item else "")
        self.icon_in = QLineEdit(item.get("icon", "📰") if item else "📰"); self.icon_in.setMaxLength(4)
        self.cat_in  = QComboBox(); self.cat_in.setEditable(True)
        self.cat_in.addItems(groups or self.DEFAULT_CATS)
        if item: self.cat_in.setCurrentText(item.get("category", "World News"))
        self.notes_in = QLineEdit(item.get("notes", "") if item else "")
        form.addRow("Name", self.name_in)
        form.addRow("URL", self.url_in)
        form.addRow("Icon", self.icon_in)
        form.addRow("Group", self.cat_in)
        form.addRow("Notes", self.notes_in)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("primary", True)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def value(self):
        url = self.url_in.text().strip()
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        return {
            "name": self.name_in.text().strip() or "Untitled",
            "url": url,
            "icon": self.icon_in.text().strip() or "📰",
            "category": self.cat_in.currentText().strip() or "World News",
            "notes": self.notes_in.text().strip(),
        }


class SourceTile(QFrame):
    def __init__(self, item, on_open, on_edit, on_delete, on_move, parent=None):
        super().__init__(parent)
        self.setObjectName("PinTile")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(88)
        self.item = item; self.on_open = on_open
        # Whole-tile tooltip with name + URL + notes
        _tip = item["name"]
        if item.get("url"): _tip += f"\n{item['url']}"
        if item.get("notes"): _tip += f"\n\n{item['notes']}"
        self.setToolTip(_tip)

        layout = QVBoxLayout(self); layout.setContentsMargins(12, 10, 12, 10); layout.setSpacing(2)
        top = QHBoxLayout()
        icon = QLabel(item.get("icon", "📰")); icon.setObjectName("PinTileIcon")
        top.addWidget(icon); top.addStretch()
        more = QPushButton("⋯"); more.setProperty("ghost", True); more.setFixedWidth(24)
        more.setCursor(Qt.CursorShape.PointingHandCursor)
        menu = QMenu(self)
        a_edit = QAction("Edit…", self); a_edit.triggered.connect(lambda: on_edit(item))
        a_move = QAction("Move to group…", self); a_move.triggered.connect(lambda: on_move(item))
        a_del  = QAction("Delete", self); a_del.triggered.connect(lambda: on_delete(item))
        menu.addAction(a_edit); menu.addAction(a_move); menu.addSeparator(); menu.addAction(a_del)
        more.setMenu(menu)
        top.addWidget(more)
        layout.addLayout(top)
        name = QLabel(item["name"]); name.setObjectName("PinTileName")
        name.setToolTip(item.get("url", ""))
        layout.addWidget(name)
        if item.get("notes"):
            n = QLabel(item["notes"]); n.setObjectName("PinTileKind"); n.setWordWrap(True)
            layout.addWidget(n)
        layout.addStretch()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.on_open(self.item)
        super().mousePressEvent(event)


RSS_FEEDS = [
    ("Times of India", "https://timesofindia.indiatimes.com/rssfeedstopstories.cms"),
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
]


class NewsModule(Module):
    MODULE_ID = "news"
    NAME = "News & Weather"
    ICON = "📰"
    SECTION = "Tools"
    DESCRIPTION = "Live weather, top headlines, and major news links."

    def setup_ui(self):
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollContainer(self)

        header = SectionHeader(
            "News & Weather",
            "Live weather and headlines fetched in-app. "
            "Major source links below — corporate firewalls may block live fetches.",
            action_text="+  Add source",
        )
        header.action_clicked.connect(self.add_source)
        scroll.add(header)

        # Top: weather + headlines side by side
        self.live_host = QWidget()
        live_layout = QHBoxLayout(self.live_host)
        live_layout.setContentsMargins(0, 0, 0, 0); live_layout.setSpacing(14)
        self.weather_card = self._build_weather_card()
        live_layout.addWidget(self.weather_card, 1)
        self.headlines_card = self._build_headlines_card()
        live_layout.addWidget(self.headlines_card, 2)
        scroll.add(self.live_host)

        # Refresh button
        refresh_row = QHBoxLayout()
        refresh_row.addStretch()
        self.refresh_btn = QPushButton("↻  Refresh live data")
        self.refresh_btn.setProperty("ghost", True)
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.clicked.connect(self._refresh_live)
        refresh_row.addWidget(self.refresh_btn)
        refresh_host = QWidget(); refresh_host.setLayout(refresh_row)
        scroll.add(refresh_host)

        # Curated sources filter + tiles
        filter_card = Card()
        fl = QHBoxLayout(filter_card); fl.setContentsMargins(14, 10, 14, 10); fl.setSpacing(8)
        self.filter_in = QLineEdit(); self.filter_in.setPlaceholderText("Filter sources…")
        self.filter_in.textChanged.connect(self._refresh)
        fl.addWidget(self.filter_in, 1)
        scroll.add(filter_card)

        self.cards_host = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_host)
        self.cards_layout.setContentsMargins(0, 0, 0, 0); self.cards_layout.setSpacing(14)
        scroll.add(self.cards_host)

        scroll.add_stretch()
        outer.addWidget(scroll)

        # Wire background-fetch signals
        self.signals = _NewsSignals()
        self.signals.weather_ready.connect(self._on_weather_ready)
        self.signals.weather_failed.connect(self._on_weather_failed)
        self.signals.headlines_ready.connect(self._on_headlines_ready)
        self.signals.headlines_failed.connect(self._on_headlines_failed)
        self.signals.image_ready.connect(self._on_image_ready)
        # Track which QLabel each lazy-loaded image URL belongs to
        self._image_targets: dict[str, QLabel] = {}

        self._ensure_defaults()
        self._refresh()

        # Kick off live fetch shortly after UI appears
        QTimer.singleShot(800, self._refresh_live)

    # ---------- Live data UI ----------
    def _build_weather_card(self) -> Card:
        card = Card()
        l = QVBoxLayout(card); l.setContentsMargins(18, 12, 18, 12); l.setSpacing(8)
        title_row = QHBoxLayout()
        title = QLabel("Weather"); title.setStyleSheet("font-size:13px; font-weight:600; background:transparent;")
        title.setProperty("class", "Muted")
        title_row.addWidget(title); title_row.addStretch()
        self.set_city_btn = QPushButton("📍 Set city")
        self.set_city_btn.setProperty("ghost", True)
        self.set_city_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_city_btn.setToolTip("Manually set the city used for weather. "
                                      "Useful when IP-based geolocation is blocked.")
        self.set_city_btn.clicked.connect(self._on_set_city)
        title_row.addWidget(self.set_city_btn)
        l.addLayout(title_row)

        # Big top row: icon + temp + description
        big_row = QHBoxLayout()
        big_row.setSpacing(14)
        self.weather_icon_lbl = QLabel("🌡")
        self.weather_icon_lbl.setStyleSheet("font-size:54px; background:transparent;")
        big_row.addWidget(self.weather_icon_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)
        col = QVBoxLayout(); col.setSpacing(0)
        self.weather_temp_lbl = QLabel("—")
        self.weather_temp_lbl.setStyleSheet("font-size:32px; font-weight:700; background:transparent;")
        col.addWidget(self.weather_temp_lbl)
        self.weather_desc_lbl = QLabel("Loading…")
        self.weather_desc_lbl.setStyleSheet("font-size:13px; background:transparent;")
        col.addWidget(self.weather_desc_lbl)
        self.weather_feels_lbl = QLabel("")
        self.weather_feels_lbl.setStyleSheet("font-size:11px; background:transparent;")
        self.weather_feels_lbl.setProperty("class", "Muted")
        col.addWidget(self.weather_feels_lbl)
        big_row.addLayout(col, 1)
        l.addLayout(big_row)

        # Location pin line
        self.weather_loc_lbl = QLabel("")
        self.weather_loc_lbl.setStyleSheet("font-size:12px; background:transparent; padding-top:2px;")
        l.addWidget(self.weather_loc_lbl)

        # 2-column detail grid (8 fields)
        from PyQt6.QtWidgets import QGridLayout
        grid = QGridLayout(); grid.setHorizontalSpacing(14); grid.setVerticalSpacing(4)
        # Pairs: (label_field_name, default_text)
        self.weather_detail_labels = {}
        rows = [
            ("high_low", "🔺 — / 🔻 —"),
            ("rain",     "🌧 —%"),
            ("humidity", "💧 —%"),
            ("wind",     "💨 — km/h"),
            ("uv",       "☀ UV —"),
            ("pressure", "🔵 — hPa"),
            ("sunrise",  "🌅 —"),
            ("sunset",   "🌇 —"),
        ]
        for i, (key, txt) in enumerate(rows):
            lbl = QLabel(txt)
            lbl.setStyleSheet("font-size:11.5px; background:transparent;")
            lbl.setProperty("class", "Muted")
            self.weather_detail_labels[key] = lbl
            grid.addWidget(lbl, i // 2, i % 2)
        l.addLayout(grid)

        self.weather_updated_lbl = QLabel("")
        self.weather_updated_lbl.setStyleSheet("font-size:10.5px; background:transparent; padding-top:4px;")
        self.weather_updated_lbl.setProperty("class", "Muted")
        l.addWidget(self.weather_updated_lbl)
        # Card sizes itself to fit content
        return card

    def _on_set_city(self):
        prefs = self.ctx.storage.load("preferences", {}) or {}
        current = prefs.get("weather_city", "")
        text, ok = QInputDialog.getText(self, "Set city for weather",
                                         "Enter city name (e.g. ‘Mumbai’, ‘London’, ‘Pune, India’):",
                                         text=current)
        if not ok:
            return
        text = text.strip()
        prefs["weather_city"] = text
        self.ctx.storage.save("preferences", prefs)
        if text:
            self.ctx.notify("Setting city…", f"Looking up '{text}'",
                            sound="click", source="News", user_initiated=True)
        else:
            self.ctx.notify("City cleared", "Falling back to IP geolocation.",
                            sound="click", source="News", user_initiated=True)
        # Refresh immediately
        self._refresh_live()

    def _build_headlines_card(self) -> Card:
        card = Card()
        l = QVBoxLayout(card); l.setContentsMargins(20, 14, 20, 14); l.setSpacing(6)
        title = QLabel("Top headlines"); title.setStyleSheet("font-size:13px; font-weight:600;")
        title.setProperty("class", "Muted")
        l.addWidget(title)
        self.headlines_layout = QVBoxLayout()
        self.headlines_layout.setSpacing(4)
        l.addLayout(self.headlines_layout)
        self.headlines_status = QLabel("Loading…")
        self.headlines_status.setProperty("class", "Muted")
        l.addWidget(self.headlines_status)
        return card

    def _refresh_live(self):
        # Reset UI to loading state
        self.weather_temp_lbl.setText("—")
        self.weather_desc_lbl.setText("Loading…")
        self.weather_feels_lbl.setText("")
        self.weather_loc_lbl.setText("")
        self.weather_icon_lbl.setText("🌡")
        for lbl in getattr(self, "weather_detail_labels", {}).values():
            lbl.setText("—")
        self.weather_updated_lbl.setText("")
        while self.headlines_layout.count():
            it = self.headlines_layout.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        self.headlines_status.setText("Loading…")
        self.headlines_status.show()
        # Stale image callbacks would target dead labels — clear tracking
        if hasattr(self, "_image_targets"):
            self._image_targets.clear()
        # Reset per-cycle dedup so each source can render exactly once
        self._rendered_sources_this_cycle = set()

        threading.Thread(target=self._fetch_weather_worker, daemon=True).start()
        for src, url in RSS_FEEDS:
            threading.Thread(target=self._fetch_headlines_worker,
                             args=(src, url), daemon=True).start()

    def _fetch_weather_worker(self):
        try:
            # Prefer manually-saved city (most corp firewalls block ipapi but
            # allow open-meteo)
            prefs = self.ctx.storage.load("preferences", {}) or {}
            saved_city = (prefs.get("weather_city") or "").strip()
            loc = None
            if saved_city:
                loc = geocode_city(saved_city)
                if not loc:
                    self.signals.weather_failed.emit(
                        f"Couldn't geocode '{saved_city}'. Try a different spelling.")
                    return
            else:
                # No saved city — try IP geolocation
                loc = fetch_geolocation()
                if not loc:
                    self.signals.weather_failed.emit(
                        "Couldn't auto-detect location. Click 'Set city' to enter manually.")
                    return
            w = fetch_weather(loc["lat"], loc["lon"])
            if not w:
                self.signals.weather_failed.emit("Weather service unreachable.")
                return
            self.signals.weather_ready.emit({**w, **loc})
        except Exception as e:
            self.signals.weather_failed.emit(str(e)[:80])

    def _fetch_headlines_worker(self, source: str, url: str):
        try:
            items = fetch_rss_headlines(url, limit=4)
            if not items:
                self.signals.headlines_failed.emit(source, "feed unreachable")
                return
            self.signals.headlines_ready.emit(source, items)
        except Exception as e:
            self.signals.headlines_failed.emit(source, str(e)[:80])

    def _on_weather_ready(self, data: dict):
        emoji, desc = _wmo_to_emoji(int(data.get("code") or 0))
        self.weather_icon_lbl.setText(emoji)
        temp = data.get("temp")
        if temp is not None:
            self.weather_temp_lbl.setText(f"{round(temp)}°C")
        self.weather_desc_lbl.setText(desc)
        # Feels-like
        feels = data.get("feels_like")
        if feels is not None:
            self.weather_feels_lbl.setText(f"Feels like {round(feels)}°C")
        self.weather_loc_lbl.setText(f"📍 {data.get('city', '')}, {data.get('country', '')}")

        # Fill detail grid
        D = self.weather_detail_labels
        tmax, tmin = data.get("temp_max"), data.get("temp_min")
        if tmax is not None and tmin is not None:
            D["high_low"].setText(f"🔺 {round(tmax)}° / 🔻 {round(tmin)}°")
        rain = data.get("rain_chance")
        D["rain"].setText(f"🌧 {rain}% chance" if rain is not None else "🌧 —")
        hum = data.get("humidity")
        D["humidity"].setText(f"💧 {round(hum)}% humidity" if hum is not None else "💧 —")
        wind = data.get("wind")
        D["wind"].setText(f"💨 {round(wind)} km/h" if wind is not None else "💨 —")
        uv = data.get("uv") if data.get("uv") is not None else data.get("uv_max")
        if uv is not None:
            uv_label = "low" if uv < 3 else "moderate" if uv < 6 else "high" if uv < 8 else "very high"
            D["uv"].setText(f"☀ UV {round(uv)} ({uv_label})")
        else:
            D["uv"].setText("☀ UV —")
        pres = data.get("pressure")
        D["pressure"].setText(f"🔵 {round(pres)} hPa" if pres is not None else "🔵 —")
        sr = data.get("sunrise"); ss = data.get("sunset")

        def _t(iso: str | None) -> str:
            if not iso: return "—"
            try:
                return datetime.fromisoformat(iso).strftime("%H:%M")
            except Exception:
                return iso[-5:] if len(iso) >= 5 else iso
        D["sunrise"].setText(f"🌅 {_t(sr)}")
        D["sunset"].setText(f"🌇 {_t(ss)}")

        self.weather_updated_lbl.setText(f"Updated {datetime.now().strftime('%H:%M')}")

    def _on_weather_failed(self, msg: str):
        self.weather_icon_lbl.setText("📡")
        self.weather_temp_lbl.setText("—")
        self.weather_desc_lbl.setText("Weather offline")
        self.weather_feels_lbl.setText("")
        self.weather_loc_lbl.setText(msg[:80])
        for lbl in self.weather_detail_labels.values():
            lbl.setText("—")
        self.weather_updated_lbl.setText("Click Google Weather below to view in browser.")

    # Internal category classifier — scans title for keywords to assign a
    # category, which maps to a colored pulsing dot. Higher priority = more
    # important.
    _CATEGORIES = [
        # (label, color, keywords)
        ("breaking",  "#EF4444", ["breaking", "urgent", "killed", "attack", "death",
                                    "dead", "explosion", "crash", "war", "strike",
                                    "fire", "shooting", "missile", "blast"]),
        ("health",    "#EC4899", ["covid", "vaccine", "hospital", "doctor", "virus",
                                    "outbreak", "cancer", "disease", "epidemic",
                                    "pandemic"]),
        ("entertainment", "#A855F7", ["movie", "film", "bollywood", "hollywood",
                                       "actor", "actress", "trailer", "song",
                                       "album", "concert", "celebrity"]),
        ("sport",     "#F59E0B", ["cricket", "football", "soccer", "tennis", "ipl",
                                    "match", "tournament", "olympic", "fifa", "nba",
                                    "wimbledon", "csk", "rcb", "mi", "champion"]),
        ("politics",  "#9333EA", ["election", "minister", "parliament", "congress",
                                    "senator", "president", "vote", "cabinet", "bjp",
                                    "modi", "rahul", "biden", "trump", "putin",
                                    "policy", "bill", "law"]),
        ("business",  "#10B981", ["market", "stock", "ipo", "earnings", "revenue",
                                    "profit", "billion", "trillion", "rupee", "dollar",
                                    "sensex", "nifty", "nasdaq", "trade", "tariff",
                                    "deal", "merger", "acquisition", "fund", "bank"]),
        ("tech",      "#06B6D4", ["ai", "openai", "chatgpt", "google", "microsoft",
                                    "tesla", "tech", "iphone", "android", "chip",
                                    "semiconductor", "software", "startup", "crypto",
                                    "bitcoin", "blockchain", "robot"]),
        ("world",     "#3B82F6", ["ukraine", "russia", "china", "israel", "gaza",
                                    "iran", "nato", "un", "summit", "treaty",
                                    "diplomat", "ambassador", "embassy"]),
    ]

    def _classify_headline(self, item: dict) -> tuple[str, str]:
        """Return (category_label, color) by scanning title keywords with
        word-boundary matching (so 'war' doesn't match 'warns')."""
        import re
        title_lower = (item.get("title") or "").lower()
        for label, color, keywords in self._CATEGORIES:
            for kw in keywords:
                # \b before a multi-word keyword still works; we need word-edge
                pattern = r"\b" + re.escape(kw) + r"(s|es|ed|ing)?\b"
                if re.search(pattern, title_lower):
                    return label, color
        # 2. Honor RSS-provided category if recognizable
        rss_cat = (item.get("category") or "").lower()
        for label, color, _kws in self._CATEGORIES:
            if label in rss_cat:
                return label, color
        # 3. Default
        return "news", self.ctx.theme.palette["accent"]

    def _dot_color_for(self, source: str, item: dict) -> str:
        """Pick the dot color for a headline — classifier-driven, not source-driven."""
        _label, color = self._classify_headline(item)
        return color

    def _on_headlines_ready(self, source: str, items: list):
        self.headlines_status.hide()
        # Track which sources have already been rendered in this refresh
        # cycle, so a second response for the same source (e.g. user clicked
        # Refresh while one was already in-flight) doesn't duplicate the
        # section.
        if not hasattr(self, "_rendered_sources_this_cycle"):
            self._rendered_sources_this_cycle = set()
        if source in self._rendered_sources_this_cycle:
            return  # ignore duplicate emission for this source
        self._rendered_sources_this_cycle.add(source)

        section_lbl = QLabel(f"From {source}:")
        section_lbl.setProperty("class", "Muted")
        section_lbl.setStyleSheet("font-size:11px; font-weight:600; padding-top:6px;")
        self.headlines_layout.addWidget(section_lbl)
        for it in items[:4]:
            row = self._build_headline_row(it, source)
            self.headlines_layout.addWidget(row)

    def _on_headlines_failed(self, source: str, _msg: str):
        if self.headlines_layout.count() == 0:
            self.headlines_status.setText(
                "📡 Live headlines couldn't load. Click a source below to read in browser.")

    def _build_headline_row(self, item: dict, source: str) -> QFrame:
        title = item.get("title", "")
        url = item.get("link", "")
        image_url = item.get("image", "")
        # Use the classifier — same source as the dot color, so badge + dot match
        cat_label, dot_color = self._classify_headline(item)

        f = QFrame(); f.setObjectName("HeadlineRow")
        f.setCursor(Qt.CursorShape.PointingHandCursor)
        # Style with hover for interactivity feel
        f.setStyleSheet("""
            QFrame#HeadlineRow {
                border-radius: 6px;
                padding: 0;
            }
            QFrame#HeadlineRow:hover {
                background-color: rgba(127,127,127,0.08);
            }
        """)
        rl = QHBoxLayout(f); rl.setContentsMargins(8, 6, 8, 6); rl.setSpacing(10)

        # Pulsing dot — color-coded by classifier
        dot = PulsingDot(color=dot_color, size=10)
        dot.setToolTip(f"{cat_label.title()} · from {source}")
        rl.addWidget(dot, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Thumbnail (placeholder if no image, will be replaced async if URL exists)
        thumb = QLabel()
        thumb.setFixedSize(60, 40)
        thumb.setStyleSheet("background:transparent;")
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Show category badge as initial placeholder
        self._set_thumb_placeholder(thumb, cat_label, dot_color)
        if image_url:
            # Kick off lazy fetch
            self._image_targets[image_url] = thumb
            threading.Thread(target=self._fetch_image_worker,
                             args=(image_url,), daemon=True).start()
        rl.addWidget(thumb, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Title
        lbl = QLabel(title); lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size:12.5px; padding:2px 0;")
        lbl.setToolTip(f"{title}\n\nClick to open in browser:\n{url}")
        rl.addWidget(lbl, 1)

        def open_it(_e=None, u=url, t=title):
            try: webbrowser.open(u)
            except Exception: pass
            self.ctx.notify("Opening article", t[:80], sound="click",
                            source="News", user_initiated=True)
        f.mousePressEvent = lambda e: open_it()
        return f

    def _fallback_category(self, source: str) -> str:
        m = {"Times of India": "India", "BBC World": "World"}
        return m.get(source, "News")

    def _set_thumb_placeholder(self, label: QLabel, category: str, color: str):
        """Render a small colored category badge into the QLabel as fallback."""
        pix = QPixmap(60, 40)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Gradient fill
        from PyQt6.QtGui import QLinearGradient, QPen, QFont
        bg = QColor(color); bg.setAlphaF(0.18)
        p.setBrush(QBrush(bg)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, 60, 40, 5, 5)
        # Border
        border = QColor(color); border.setAlphaF(0.55)
        pen = QPen(border); pen.setWidthF(1.2)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(0, 0, 60, 40, 5, 5)
        # Centered short label
        short = (category[:8] or "News").upper()
        text_col = QColor(color); text_col.setAlphaF(0.95)
        p.setPen(text_col)
        f = QFont(); f.setPointSize(7); f.setBold(True)
        p.setFont(f)
        p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, short)
        p.end()
        label.setPixmap(pix)

    def _fetch_image_worker(self, url: str):
        data = _http_get_bytes(url)
        if data:
            self.signals.image_ready.emit(url, data)

    def _on_image_ready(self, url: str, data: bytes):
        target = self._image_targets.pop(url, None)
        if target is None:
            return
        try:
            pix = QPixmap()
            pix.loadFromData(QByteArray(data))
            if pix.isNull():
                return
            scaled = pix.scaled(60, 40, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                 Qt.TransformationMode.SmoothTransformation)
            # Crop to 60x40
            if scaled.width() > 60 or scaled.height() > 40:
                x = max(0, (scaled.width() - 60) // 2)
                y = max(0, (scaled.height() - 40) // 2)
                scaled = scaled.copy(x, y, 60, 40)
            # Apply rounded corners using a mask
            rounded = QPixmap(60, 40)
            rounded.fill(Qt.GlobalColor.transparent)
            p = QPainter(rounded)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            from PyQt6.QtGui import QPainterPath
            path = QPainterPath()
            path.addRoundedRect(0, 0, 60, 40, 5, 5)
            p.setClipPath(path)
            p.drawPixmap(0, 0, scaled)
            p.end()
            target.setPixmap(rounded)
        except Exception:
            pass

    # ---------- Curated sources ----------
    def _data(self): return self.ctx.storage.load("module_news", [])
    def _save(self, items): self.ctx.storage.save("module_news", items)

    def _ensure_defaults(self):
        def _slug(s: str) -> str:
            out = []
            for ch in (s or "").lower():
                if ch.isalnum(): out.append(ch)
                elif ch in " -_": out.append("-")
            return "".join(out).strip("-") or "untitled"

        existing = self._data()
        # Identifiers user has "claimed" by editing a default
        claimed = {e.get("default_key") for e in existing
                   if e.get("default_key") and not e.get("from_defaults")}
        # Drop the from_defaults entries — we'll re-add the fresh set
        kept = [e for e in existing if not e.get("from_defaults")]
        existing_urls = {it.get("url") for it in kept}
        for d in DEFAULT_SOURCES:
            dkey = f"news:{_slug(d['name'])}"
            if dkey in claimed:
                continue  # user has a renamed version — don't re-add original
            if d["url"] in existing_urls:
                continue  # user has same URL under different name
            new = dict(d)
            new["from_defaults"] = True
            new["default_key"] = dkey
            kept.append(new)
        self._save(kept)

    def _all_groups(self):
        used = sorted({i.get("category", "World News") for i in self._data()})
        return list(dict.fromkeys(used + NewsSourceDialog.DEFAULT_CATS))

    def _refresh(self):
        while self.cards_layout.count():
            it = self.cards_layout.takeAt(0)
            if it.widget(): it.widget().deleteLater()

        items = self._data()
        q = self.filter_in.text().lower().strip()
        if q:
            items = [it for it in items
                     if q in it["name"].lower()
                     or q in it.get("category", "").lower()
                     or q in it.get("notes", "").lower()]

        if not items:
            self.cards_layout.addWidget(EmptyState(
                "📰", "No sources yet",
                "Click ‘Add source’ to add a news or weather site."))
            return

        groups = OrderedDict()
        order = ["Weather", "India News", "World News", "Tech", "Business", "Sports", "Science"]
        for cat in order:
            for it in items:
                if it.get("category") == cat:
                    groups.setdefault(cat, []).append(it)
        for it in items:
            cat = it.get("category", "Other")
            if cat not in groups:
                groups.setdefault(cat, []).append(it)

        for group_name, group_items in groups.items():
            self.cards_layout.addWidget(self._build_group_card(group_name, group_items))

    def _build_group_card(self, group, items):
        card = QFrame(); card.setObjectName("GroupCard")
        layout = QVBoxLayout(card); layout.setContentsMargins(16, 14, 16, 14); layout.setSpacing(10)
        head = QHBoxLayout()
        title = QLabel(group); title.setObjectName("GroupTitle"); head.addWidget(title)
        count = QLabel(f"{len(items)}"); count.setObjectName("GroupCount"); head.addWidget(count)
        head.addStretch()
        layout.addLayout(head)

        grid_host = QWidget()
        grid = QGridLayout(grid_host); grid.setSpacing(10); grid.setContentsMargins(0, 0, 0, 0)
        cols = 3
        for i, it in enumerate(items):
            grid.addWidget(SourceTile(
                it, self._open, self.edit_source, self.delete_source, self._move_to_group
            ), i // cols, i % cols)
        for c in range(cols):
            grid.setColumnStretch(c, 1)
        layout.addWidget(grid_host)
        return card

    def _open(self, item):
        self.ctx.play_sound("click")
        try:
            webbrowser.open(item["url"])
        except Exception as e:
            self.ctx.notify("Couldn't open", str(e)[:120], sound="error", source="News")

    def add_source(self):
        dlg = NewsSourceDialog(self, groups=self._all_groups())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = self._data(); data.append(dlg.value()); self._save(data); self._refresh()

    def edit_source(self, item):
        dlg = NewsSourceDialog(self, item=item, groups=self._all_groups())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = self._data()
            for i, it in enumerate(data):
                if it.get("url") == item.get("url") and it.get("name") == item.get("name"):
                    new = dlg.value()
                    # Preserve identity but mark as user-owned now
                    if it.get("default_key"):
                        new["default_key"] = it["default_key"]
                    new["from_defaults"] = False
                    data[i] = new; break
            self._save(data); self._refresh()

    def delete_source(self, item):
        if QMessageBox.question(self, "Delete source", f"Remove '{item['name']}'?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) \
                == QMessageBox.StandardButton.Yes:
            data = [i for i in self._data()
                    if not (i.get("url") == item.get("url") and i.get("name") == item.get("name"))]
            self._save(data); self._refresh()

    def _move_to_group(self, item):
        groups = self._all_groups()
        choice, ok = QInputDialog.getItem(self, "Move to group",
                                          f"Move '{item['name']}' to:",
                                          groups + ["+ New group…"], 0, False)
        if not ok: return
        if choice == "+ New group…":
            new_name, ok = QInputDialog.getText(self, "New group", "Group name:")
            if not ok or not new_name.strip(): return
            choice = new_name.strip()
        data = self._data()
        for it in data:
            if it.get("url") == item.get("url") and it.get("name") == item.get("name"):
                it["category"] = choice; break
        self._save(data); self._refresh()

    def register_search(self):
        def provider(query: str):
            results = []
            for it in self._data():
                score = max(fuzzy_score(query, it.get("name", "")),
                            fuzzy_score(query, it.get("category", "")) * 0.6)
                if score > 0.25:
                    item_ref = it
                    results.append(SearchResult(
                        title=it["name"], subtitle=it.get("category", ""), category="News",
                        icon=it.get("icon", "📰"),
                        action=lambda x=item_ref: self._open(x),
                        score=score,
                    ))
            return results
        self.ctx.search.register("news", provider)

    def on_show(self): self._refresh()
