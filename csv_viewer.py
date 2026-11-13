#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BrainStem CSV Viewer
=====================
Eigenstaendiger, vom BrainStem-System entkoppelter Viewer fuer GUI-Log-CSV-
Dateien (z.B. gui_log_*.csv). Zeigt beliebig viele Kennlinien in einem
gemeinsamen Fenster an, erlaubt das Ein-/Ausschalten einzelner Kurven,
Ueberlagerung mehrerer Kurven sowie unterschiedliche Skalierungen pro Wert.

Das Erscheinungsbild folgt der Designsprache der BrainStem-Admin-GUI
(ki_system/gui_theme.py): ruhiges Dunkel-Theme als Standard, helles Theme
umschaltbar, gleiche Farbwerte, Karten, Pillen und Botenstoff-Farben.

Abhaengigkeiten: PySide6, pyqtgraph, pandas, numpy  (siehe requirements.txt)

Start:
    python csv_viewer.py [optional: pfad_zur_datei.csv]

Windows-EXE-Build:
    build_exe.bat  (nutzt PyInstaller, siehe README.md)
"""

import sys
import os
import itertools
import numpy as np
import pandas as pd

from PySide6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg


APP_TITLE = "BrainStem CSV Viewer"

# Bekannte Spaltengruppen aus dem BrainStem GUI-Log (gui_log_*.csv).
# Unbekannte Spalten landen automatisch in "Sonstige".
# Die Schluessel sind nur Anzeigenamen; die Spaltennamen sind die des Loggers.
KNOWN_GROUPS = {
    "Botenstoffe": [
        "dopamine", "serotonin", "glutamate", "gaba", "noradrenaline",
        "acetylcholine", "adenosine", "endocannabinoid", "cortisol",
        "histamine", "orexin", "bdnf",
    ],
    "Regime / Zustand": [
        "sleep_state", "sleep_active", "sleep_dwell_cycles",
        "sleep_upper_threshold", "sleep_lower_threshold",
        "sleep_pressure_position", "sleep_transition_reason",
        "developmental_maturity",
        "sleep_cooperative_score", "sleep_authority",
        "auto_running", "regime_orexin", "regime_bdnf", "regime_cortisol",
        "regime_histamine", "sleep_cooperative_mode", "sleep_phase7a_mode",
        "mood_name", "mode",
    ],
    "Fortschritt / Zähler": [
        "chunks_covered", "chunks_total", "chunks_pct", "hypotheses_total",
        "documents", "chunks_stat", "facts", "relations", "ontology",
        "questions", "phase7d_survivors", "phase7d_participated",
        "phase7d_weakened", "phase7d_threshold",
    ],
}

# Textspalten, die niemals als Kennlinie geplottet werden (nur Kontext/Log-Text)
TEXT_ONLY_COLUMNS = {"stageb_experiment_summary"}

TIMESTAMP_CANDIDATES = ["timestamp_iso", "timestamp", "time", "datetime", "date"]


BOOL_MAPPING = {"true": 1.0, "false": 0.0, "wahr": 1.0, "falsch": 0.0, "ja": 1.0, "nein": 0.0}
EMPTY_MARKERS = {"", "nan", "none", "n/a", "na", "null", "-"}


# ===================================================================== Theme
# Gleiche Farbwerte wie ki_system/gui_theme.py der BrainStem-Admin-GUI.
PALETTES = {
    "dark": {
        "bg": "#1b1e23", "header": "#16191d", "surface": "#23272e", "surface2": "#2c313a",
        "hover": "#353b45", "field": "#1d2126", "border": "#363c46", "border_strong": "#4a525e",
        "text": "#dce1e7", "muted": "#a9b3be", "subtle": "#97a1ac",
        "accent": "#6aa9e0", "accent_hover": "#82b8e6", "accent_fg": "#0f1720",
        "accent_soft": "#26384a", "selection": "#2e4a66",
        "success": "#86d494", "success_soft": "#1e3325",
        "warning": "#ddb05a", "warning_soft": "#3d3320",
        "danger": "#ec7a72", "danger_soft": "#3d2526",
        "grid": "#30363f", "plot": "#1f2329", "crosshair": "#8a949f",
        # Kennlinien ausserhalb der Botenstoffe (Okabe-Ito-nah, auf dunklem
        # Grund mindestens 4.5:1 Kontrast)
        "curves": ("#6aa9e0", "#f08a4b", "#3cc9a0", "#e693c4", "#f2c14e", "#a9b6ff",
                   "#86d494", "#ec7a72", "#5fc7d6", "#d0a77e", "#c39bf0", "#b5c45a"),
    },
    "light": {
        "bg": "#e8ebef", "header": "#dde2e8", "surface": "#f5f6f8", "surface2": "#e6e9ee",
        "hover": "#d9dee5", "field": "#fafbfc", "border": "#c9d0d8", "border_strong": "#aab3bd",
        "text": "#1e2731", "muted": "#4b5765", "subtle": "#5e6a77",
        "accent": "#245f9e", "accent_hover": "#1d5089", "accent_fg": "#ffffff",
        "accent_soft": "#d6e4f3", "selection": "#c7dbf0",
        "success": "#2b7a3a", "success_soft": "#d9eedd",
        "warning": "#8a5a00", "warning_soft": "#f5e8c8",
        "danger": "#b42318", "danger_soft": "#f8dedb",
        "grid": "#dde1e6", "plot": "#fafbfc", "crosshair": "#6b7682",
        "curves": ("#245f9e", "#d55e00", "#00805c", "#a8437f", "#5b6b00", "#4c5bd4",
                   "#b42318", "#00788a", "#7a45c4", "#8a5a2b", "#3d4a57", "#c2185b"),
    },
}

THEME_LABELS = {"dark": "Dunkel", "light": "Hell"}

# Botenstoff-Farben wie in den Balken der Admin-GUI (auf beiden Paletten lesbar)
NEURO_PALETTE = {
    "dopamine": "#d9a72b", "serotonin": "#55b06a", "glutamate": "#e0803f",
    "gaba": "#4f93d6", "noradrenaline": "#9a83d4", "acetylcholine": "#3fb3bf",
    "adenosine": "#b0835f", "endocannabinoid": "#8d9aa8", "cortisol": "#e06464",
    "histamine": "#cf74b1", "orexin": "#e9a23b", "bdnf": "#38a98f",
}

MODE_HINTS = {}  # wird nach der Klassendefinition gefuellt
_CURRENT_THEME = {"name": "dark"}  # fuer den Qt-Stil (Check-Boxen)


def ui_font_family():
    families = set(QtGui.QFontDatabase.families())
    for name in ("Segoe UI", "Inter", "Noto Sans", "DejaVu Sans", "Helvetica Neue", "Arial"):
        if name in families:
            return name
    return QtWidgets.QApplication.font().family()


def build_stylesheet(p):
    """Qt-Stylesheet nach dem Muster der ttk-Styles der Admin-GUI."""
    return f"""
    QMainWindow, QWidget#Central {{ background: {p['bg']}; }}
    QWidget {{ color: {p['text']}; }}
    QToolTip {{ background: {p['surface2']}; color: {p['text']}; border: 1px solid {p['border_strong']};
                padding: 5px 8px; }}

    QWidget#AppHeader {{ background: {p['header']}; border-bottom: 1px solid {p['border']}; }}
    QLabel#AppTitle {{ font-size: 14pt; font-weight: 600; color: {p['text']}; }}
    QLabel#HeaderMuted {{ color: {p['muted']}; }}

    QFrame#Card {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 8px; }}
    QFrame#Card QLabel {{ background: transparent; }}
    QLabel#CardTitle {{ font-size: 11pt; font-weight: 600; color: {p['text']}; }}
    QLabel#CardMuted, QLabel#Hint {{ color: {p['muted']}; }}
    QLabel#Caps {{ color: {p['muted']}; font-size: 9pt; font-weight: 600; letter-spacing: 0.5px; }}
    QLabel#FileName {{ font-size: 11pt; font-weight: 600; color: {p['text']}; }}

    QLabel[pill="info"] {{ background: {p['accent_soft']}; color: {p['accent']}; border-radius: 10px;
                           padding: 2px 10px; font-weight: 600; }}
    QLabel[pill="muted"] {{ background: {p['surface2']}; color: {p['muted']}; border-radius: 10px;
                            padding: 2px 10px; font-weight: 600; }}
    QLabel[pill="warn"] {{ background: {p['warning_soft']}; color: {p['warning']}; border-radius: 10px;
                           padding: 2px 10px; font-weight: 600; }}

    QPushButton {{ background: {p['surface2']}; color: {p['text']}; border: 1px solid {p['border_strong']};
                   border-radius: 6px; padding: 6px 14px; }}
    QPushButton:hover {{ background: {p['hover']}; }}
    QPushButton:pressed {{ background: {p['border']}; }}
    QPushButton:focus {{ border: 2px solid {p['accent']}; padding: 5px 13px; }}
    QPushButton[small="true"]:focus {{ padding: 2px 9px; }}
    QPushButton:disabled {{ color: {p['subtle']}; background: {p['surface']}; border-color: {p['border']}; }}
    QPushButton[accent="true"] {{ background: {p['accent']}; color: {p['accent_fg']}; border-color: {p['accent']};
                                  font-weight: 600; }}
    QPushButton[accent="true"]:hover {{ background: {p['accent_hover']}; border-color: {p['accent_hover']}; }}
    QPushButton[accent="true"]:focus {{ border: 2px solid {p['text']}; padding: 5px 13px; }}
    QPushButton[small="true"] {{ padding: 3px 10px; }}
    QPushButton[seg="true"] {{ padding: 4px 14px; min-width: 56px; }}
    QPushButton[seg="true"]:checked {{ background: {p['accent']}; color: {p['accent_fg']};
                                       border-color: {p['accent']}; font-weight: 600; }}

    QLineEdit, QComboBox {{ background: {p['field']}; color: {p['text']}; border: 1px solid {p['border_strong']};
                            border-radius: 6px; padding: 5px 8px; selection-background-color: {p['selection']};
                            selection-color: {p['text']}; }}
    QLineEdit:focus, QComboBox:focus {{ border: 1px solid {p['accent']}; }}
    QComboBox:hover {{ border-color: {p['accent']}; }}
    QComboBox::drop-down {{ border: none; width: 26px; }}
    QComboBox QAbstractItemView {{ background: {p['surface2']}; color: {p['text']}; border: 1px solid {p['border_strong']};
                                   selection-background-color: {p['selection']}; selection-color: {p['text']};
                                   outline: 0; padding: 4px; }}

    QTreeWidget {{ background: {p['surface']}; border: none; outline: 0; }}
    QTreeWidget::item {{ padding: 3px 2px; border: none; }}
    QTreeWidget::item:hover {{ background: {p['hover']}; }}
    QTreeWidget::item:selected {{ background: {p['selection']}; color: {p['text']}; }}

    QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
    QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
    QScrollBar::handle {{ background: {p['border_strong']}; border-radius: 4px; min-height: 28px; min-width: 28px; }}
    QScrollBar::handle:hover {{ background: {p['subtle']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    QMenuBar {{ background: {p['header']}; color: {p['text']}; padding: 2px 6px; }}
    QMenuBar::item {{ padding: 4px 10px; border-radius: 4px; background: transparent; }}
    QMenuBar::item:selected {{ background: {p['hover']}; }}
    QMenu {{ background: {p['surface2']}; color: {p['text']}; border: 1px solid {p['border_strong']}; padding: 4px; }}
    QMenu::item {{ padding: 6px 28px 6px 24px; border-radius: 4px; }}
    QMenu::item:selected {{ background: {p['selection']}; }}
    QMenu::item:disabled {{ color: {p['subtle']}; }}
    QMenu::separator {{ height: 1px; background: {p['border']}; margin: 4px 8px; }}

    QStatusBar {{ background: {p['header']}; color: {p['muted']}; border-top: 1px solid {p['border']}; }}
    QStatusBar QLabel {{ color: {p['muted']}; padding: 0 6px; }}
    QStatusBar::item {{ border: none; }}

    QFrame#SidePanel {{ background: {p['plot']}; border: 1px solid {p['border']}; border-radius: 6px; }}
    QFrame#SidePanel QScrollArea, QWidget#LegendInner {{ background: transparent; border: none; }}
    QLabel#CursorTime {{ color: {p['text']}; font-weight: 600; }}
    QLabel#LegendRange {{ color: {p['muted']}; font-size: 9pt; }}
    QLabel#LegendValue {{ color: {p['text']}; font-weight: 600; }}
    QLabel#EmptyState {{ color: {p['muted']}; background: transparent; }}
    """


def build_palette(p):
    pal = QtGui.QPalette()
    c = QtGui.QColor
    roles = {
        QtGui.QPalette.Window: p["bg"], QtGui.QPalette.WindowText: p["text"],
        QtGui.QPalette.Base: p["field"], QtGui.QPalette.AlternateBase: p["surface2"],
        QtGui.QPalette.Text: p["text"], QtGui.QPalette.Button: p["surface2"],
        QtGui.QPalette.ButtonText: p["text"], QtGui.QPalette.Highlight: p["selection"],
        QtGui.QPalette.HighlightedText: p["text"], QtGui.QPalette.ToolTipBase: p["surface2"],
        QtGui.QPalette.ToolTipText: p["text"], QtGui.QPalette.PlaceholderText: p["subtle"],
        QtGui.QPalette.Link: p["accent"], QtGui.QPalette.Light: p["hover"],
        QtGui.QPalette.Midlight: p["border"], QtGui.QPalette.Mid: p["border_strong"],
        QtGui.QPalette.Dark: p["border_strong"], QtGui.QPalette.Shadow: p["header"],
    }
    for role, color in roles.items():
        pal.setColor(role, c(color))
    for role in (QtGui.QPalette.Text, QtGui.QPalette.WindowText, QtGui.QPalette.ButtonText):
        pal.setColor(QtGui.QPalette.Disabled, role, c(p["subtle"]))
    return pal


class BrainStemStyle(QtWidgets.QProxyStyle):
    """Fusion mit eigenen Check-Boxen (wie die Bild-Indikatoren der Admin-GUI):
    leer mit kraeftigem Rand, angehakt als Akzentflaeche mit Haken."""

    def __init__(self, palette_ref):
        super().__init__("Fusion")
        self._p = palette_ref  # callable -> aktuelles Paletten-Dict

    def drawPrimitive(self, element, option, painter, widget=None):
        if element in (QtWidgets.QStyle.PE_IndicatorItemViewItemCheck, QtWidgets.QStyle.PE_IndicatorCheckBox):
            p = self._p()
            r = QtCore.QRectF(option.rect)
            side = min(r.width(), r.height(), 16.0)
            box = QtCore.QRectF(r.center().x() - side / 2 + 0.5, r.center().y() - side / 2 + 0.5, side - 1, side - 1)
            on = bool(option.state & QtWidgets.QStyle.State_On)
            hover = bool(option.state & QtWidgets.QStyle.State_MouseOver)
            enabled = bool(option.state & QtWidgets.QStyle.State_Enabled)
            painter.save()
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            if on:
                fill = QtGui.QColor(p["accent"] if enabled else p["border"])
                painter.setPen(QtGui.QPen(fill, 1))
                painter.setBrush(fill)
            else:
                painter.setPen(QtGui.QPen(QtGui.QColor(p["accent"] if hover else p["border_strong"]), 1.2))
                painter.setBrush(QtGui.QColor(p["field"]))
            painter.drawRoundedRect(box, 3.5, 3.5)
            if on:
                pen = QtGui.QPen(QtGui.QColor(p["accent_fg"]), 2.0, QtCore.Qt.SolidLine,
                                 QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)
                painter.setPen(pen)
                x, y, s = box.x(), box.y(), box.width()
                path = QtGui.QPainterPath(QtCore.QPointF(x + s * 0.24, y + s * 0.52))
                path.lineTo(x + s * 0.43, y + s * 0.70)
                path.lineTo(x + s * 0.77, y + s * 0.32)
                painter.setBrush(QtCore.Qt.NoBrush)
                painter.drawPath(path)
            painter.restore()
            return
        super().drawPrimitive(element, option, painter, widget)


def set_dark_title_bar(widget, dark):
    """Windows 10/11: Titelleiste passend zum Farbschema (DWM). Ohne Wirkung
    auf anderen Systemen oder aelteren Windows-Versionen."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        value = ctypes.c_int(1 if dark else 0)
        hwnd = int(widget.winId())
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (neu, alt)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                break
    except Exception:
        pass


def swatch_icon(color, size=14):
    """Kleines abgerundetes Farbfeld als Legende in der Kennlinienliste."""
    screen = QtGui.QGuiApplication.primaryScreen()
    dpr = screen.devicePixelRatio() if screen else 1.0
    pix = QtGui.QPixmap(int(size * dpr), int(size * dpr))
    pix.setDevicePixelRatio(dpr)
    pix.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pix)
    painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
    painter.setPen(QtCore.Qt.NoPen)
    painter.setBrush(QtGui.QColor(color))
    painter.drawRoundedRect(QtCore.QRectF(1, 1, size - 2, size - 2), 3, 3)
    painter.end()
    return QtGui.QIcon(pix)


def format_value(val):
    """Zahl fuer die Werteanzeige: ganze Zahlen ab 1000 mit Leerzeichen als
    Tausendertrenner (162 400), sonst 4 signifikante Stellen."""
    if val is None or not np.isfinite(val):
        return "–"
    if abs(val) >= 1000 and float(val).is_integer():
        return f"{val:,.0f}".replace(",", " ")
    if abs(val) >= 100000:
        return f"{val:,.1f}".replace(",", " ")
    return f"{val:.4g}"


def make_card(title=None, subtitle=None):
    """Karte wie gui_theme.card(): Flaeche mit Rand, Titelzeile, Inhalt."""
    frame = QtWidgets.QFrame()
    frame.setObjectName("Card")
    outer = QtWidgets.QVBoxLayout(frame)
    outer.setContentsMargins(16, 12, 16, 14)
    outer.setSpacing(8)
    header = QtWidgets.QHBoxLayout()
    header.setSpacing(8)
    frame.header = header
    if title:
        titles = QtWidgets.QVBoxLayout()
        titles.setSpacing(1)
        t = QtWidgets.QLabel(title)
        t.setObjectName("CardTitle")
        titles.addWidget(t)
        frame.subtitle = None
        if subtitle is not None:
            s = QtWidgets.QLabel(subtitle)
            s.setObjectName("CardMuted")
            s.setWordWrap(True)
            titles.addWidget(s)
            frame.subtitle = s
        header.addLayout(titles, 1)
        outer.addLayout(header)
    frame.body = outer
    return frame


def tab_focus_only(*buttons):
    """Knoepfe bekommen den Fokus nur per Tabulator (Fokusrahmen bleibt nach
    einem Mausklick nicht stehen, ist per Tastatur aber sichtbar)."""
    for b in buttons:
        b.setFocusPolicy(QtCore.Qt.TabFocus)


# ================================================================ Daten
def to_numeric_values(series: pd.Series) -> np.ndarray:
    """Wandelt eine Spalte in Float-Werte: Zahlen bleiben Zahlen, True/False
    (auch als Text) wird 1/0, leere Zellen und Platzhalter wie "n/a" werden
    NaN (Luecke in der Kurve)."""
    if pd.api.types.is_bool_dtype(series):
        return series.astype(float).to_numpy()
    if pd.api.types.is_numeric_dtype(series):
        return series.to_numpy(dtype=float, na_value=np.nan)
    text = series.astype("string").str.strip().str.lower()
    mapped = text.map(BOOL_MAPPING)
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.fillna(mapped).to_numpy(dtype=float, na_value=np.nan)


def is_plottable(series: pd.Series) -> bool:
    """Zeichenbar ist eine Spalte, wenn sie mindestens einen Wert hat und alle
    nicht leeren Zellen als Zahl oder Wahrheitswert lesbar sind."""
    values = to_numeric_values(series)
    if not np.isfinite(values).any():
        return False
    text = series.astype("string").str.strip().str.lower()
    filled = ~(series.isna() | text.isin(EMPTY_MARKERS))
    return bool(np.isfinite(values[filled.to_numpy()]).all())


def to_epoch_seconds(series: pd.Series):
    """Zeitspalte -> Sekunden seit 1970 (float, NaN fuer unlesbare Zeilen).
    Unabhaengig von der internen Zeitaufloesung (pandas 3 speichert z.B.
    Mikrosekunden statt Nanosekunden). Zahlen werden als Unix-Sekunden
    gelesen. Gibt (sekunden, datetimes) zurueck oder None."""
    if pd.api.types.is_numeric_dtype(series):
        parsed = pd.to_datetime(series, unit="s", errors="coerce")
    else:
        parsed = pd.to_datetime(series, errors="coerce")
    if getattr(parsed.dt, "tz", None) is not None:
        parsed = parsed.dt.tz_convert(None)
    if parsed.notna().sum() == 0:
        return None
    seconds = (parsed - pd.Timestamp("1970-01-01")) / pd.Timedelta(seconds=1)
    return seconds.astype(float), parsed


class CurveEntry:
    """Haelt Metadaten + Plot-Objekte fuer eine Kennlinie."""

    def __init__(self, name, color, group):
        self.name = name
        self.color = color
        self.group = group
        self.color_index = 0     # Position in der Themen-Farbfolge (Nicht-Botenstoffe)
        self.checked = False
        self.tree_item = None
        self.curve_item = None   # pg.PlotDataItem
        self.norm_range = None   # (min, max) im normalisierten Modus
        self.view_box = None     # eigene ViewBox (nur im Multi-Achsen-Modus)
        self.axis_item = None    # eigene AxisItem (nur im Multi-Achsen-Modus)


# ================================================================ Fenster
class CsvViewerWindow(QtWidgets.QMainWindow):
    MODE_ORIGINAL = "Original (gemeinsame Achse)"
    MODE_NORMALIZED = "Überlagert, normalisiert (0–1)"
    MODE_MULTI_AXIS = "Eigene Achse je Kurve"

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1500, 900)
        self.setMinimumSize(1100, 680)
        self.setAcceptDrops(True)

        self.settings = QtCore.QSettings("BrainStem", "BrainStem CSV Viewer")
        theme = str(self.settings.value("theme", "dark"))
        self.theme_name = theme if theme in PALETTES else "dark"
        self.p = PALETTES[self.theme_name]

        self.df = None
        self.x_raw = None          # datetime64 Series (oder Zyklusindex)
        self.x_seconds = None      # float epoch seconds fuer pg.DateAxisItem
        self.is_time_axis = False
        self.curves = {}           # name -> CurveEntry
        self.color_cycle = itertools.count()
        self.extra_view_boxes = []  # aktive zusaetzliche ViewBoxes (Multi-Achse)
        self._extra_axis_items = []
        self._update_extra_views_ref = None
        self._values_cache = {}     # Spaltenname -> Float-Array
        self.ts_col = None
        self.current_path = None

        self._build_ui()
        self._connect_signals()
        self.set_theme(self.theme_name, persist=False)
        self._update_empty_state()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        pg.setConfigOptions(antialias=True, background=self.p["plot"], foreground=self.p["muted"])

        central = QtWidgets.QWidget()
        central.setObjectName("Central")
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        body = QtWidgets.QHBoxLayout()
        body.setContentsMargins(14, 14, 14, 14)
        body.setSpacing(14)
        root.addLayout(body, 1)

        # ---------- linkes Panel: Datei, Darstellung, Kennlinien ----------
        left_panel = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)
        left_panel.setMinimumWidth(320)
        left_panel.setMaximumWidth(360)

        file_card = make_card("Datei")
        self.reload_btn = QtWidgets.QPushButton("Neu laden")
        self.reload_btn.setProperty("small", True)
        self.reload_btn.setToolTip("Datei erneut einlesen (F5). Auswahl und Modus bleiben erhalten.")
        self.reload_btn.clicked.connect(self.reload_csv)
        self.reload_btn.setEnabled(False)
        file_card.header.addWidget(self.reload_btn, 0, QtCore.Qt.AlignTop)
        self.file_label = QtWidgets.QLabel("Keine Datei geladen")
        self.file_label.setObjectName("FileName")
        self.file_label.setWordWrap(True)
        self.file_meta = QtWidgets.QLabel("CSV öffnen oder eine gui_log_*.csv in das Fenster ziehen.")
        self.file_meta.setObjectName("CardMuted")
        self.file_meta.setWordWrap(True)
        open_btn = QtWidgets.QPushButton("CSV öffnen …")
        open_btn.setProperty("accent", True)
        open_btn.setToolTip("CSV-Datei auswählen (Strg+O)")
        open_btn.clicked.connect(self.open_csv_dialog)
        file_card.body.addWidget(self.file_label)
        file_card.body.addWidget(self.file_meta)
        file_card.body.addSpacing(2)
        file_card.body.addWidget(open_btn)
        left_layout.addWidget(file_card)

        mode_card = make_card("Darstellung")
        caps = QtWidgets.QLabel("MODUS")
        caps.setObjectName("Caps")
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItems([
            self.MODE_MULTI_AXIS,
            self.MODE_NORMALIZED,
            self.MODE_ORIGINAL,
        ])
        self.mode_combo.setToolTip("Wie die aktiven Kennlinien skaliert werden")
        self.mode_hint = QtWidgets.QLabel("")
        self.mode_hint.setObjectName("Hint")
        self.mode_hint.setWordWrap(True)
        mode_card.body.addWidget(caps)
        mode_card.body.addWidget(self.mode_combo)
        mode_card.body.addWidget(self.mode_hint)
        left_layout.addWidget(mode_card)

        curves_card = make_card("Kennlinien")
        self.active_pill = QtWidgets.QLabel("0 aktiv")
        self.active_pill.setProperty("pill", "muted")
        curves_card.header.addWidget(self.active_pill, 0, QtCore.Qt.AlignVCenter)
        # Suchfilter fuer die Kennlinienliste
        self.filter_edit = QtWidgets.QLineEdit()
        self.filter_edit.setPlaceholderText("Kennlinien filtern …")
        self.filter_edit.setClearButtonEnabled(True)
        curves_card.body.addWidget(self.filter_edit)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(8)
        select_all_btn = QtWidgets.QPushButton("Alle an")
        select_none_btn = QtWidgets.QPushButton("Alle aus")
        for b, tip in ((select_all_btn, "Alle sichtbaren Kennlinien einschalten (Filter beachten)"),
                       (select_none_btn, "Alle sichtbaren Kennlinien ausschalten")):
            b.setProperty("small", True)
            b.setToolTip(tip)
        self.select_buttons = (select_all_btn, select_none_btn)
        select_all_btn.clicked.connect(lambda: self._set_all_checked(True))
        select_none_btn.clicked.connect(lambda: self._set_all_checked(False))
        btn_row.addWidget(select_all_btn)
        btn_row.addWidget(select_none_btn)
        btn_row.addStretch(1)
        curves_card.body.addLayout(btn_row)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(2)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.tree.setIndentation(14)
        self.tree.setIconSize(QtCore.QSize(14, 14))
        self.tree.setUniformRowHeights(True)
        self.tree.setMouseTracking(True)
        self.tree.itemChanged.connect(self._on_item_changed)
        curves_card.body.addWidget(self.tree, stretch=1)

        self.info_label = QtWidgets.QLabel("")
        self.info_label.setObjectName("Hint")
        self.info_label.setWordWrap(True)
        curves_card.body.addWidget(self.info_label)
        left_layout.addWidget(curves_card, stretch=1)

        # ---------- rechtes Panel: Plot ----------
        plot_card = make_card("Verlauf", "")
        self.plot_subtitle = plot_card.subtitle
        self.fit_btn = QtWidgets.QPushButton("Ansicht anpassen")
        self.fit_btn.setProperty("small", True)
        self.fit_btn.setToolTip("Alle Achsen wieder auf den vollen Datenbereich setzen (Strg+0)")
        self.fit_btn.clicked.connect(self.fit_view)
        plot_card.header.addWidget(self.fit_btn, 0, QtCore.Qt.AlignTop)
        plot_card.body.setContentsMargins(12, 12, 12, 12)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.plot_item = self.plot_widget.getPlotItem()
        self.plot_item.showGrid(x=True, y=True, alpha=0.55)
        # Keine automatische SI-Skalierung: Werte 0..1 sonst als "0..700 (x0.001)"
        for side in ("left", "right"):
            self.plot_item.getAxis(side).enableAutoSIPrefix(False)
        # Keine Legende im Diagramm: Legende und Werte stehen in einer
        # eigenen Spalte rechts daneben und verdecken keine Kurve.
        self.view_box = self.plot_item.vb

        # Crosshair + Readout
        self.vline = pg.InfiniteLine(angle=90, movable=False)
        self.hline = pg.InfiniteLine(angle=0, movable=False)
        self.plot_item.addItem(self.vline, ignoreBounds=True)
        self.plot_item.addItem(self.hline, ignoreBounds=True)
        self.vline.hide()
        self.hline.hide()

        # Legende + Werte am Zeiger: eigene Spalte neben dem Diagramm
        self.side_panel = QtWidgets.QFrame()
        self.side_panel.setObjectName("SidePanel")
        self.side_panel.setFixedWidth(256)
        side = QtWidgets.QVBoxLayout(self.side_panel)
        side.setContentsMargins(12, 10, 10, 10)
        side.setSpacing(4)
        side_caps = QtWidgets.QLabel("LEGENDE UND WERTE AM ZEIGER")
        side_caps.setObjectName("Caps")
        self.cursor_label = QtWidgets.QLabel("")
        self.cursor_label.setTextFormat(QtCore.Qt.RichText)
        self.cursor_label.setObjectName("CursorTime")
        self.cursor_label.setWordWrap(True)
        side.addWidget(side_caps)
        side.addWidget(self.cursor_label)
        side.addSpacing(4)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        inner = QtWidgets.QWidget()
        inner.setObjectName("LegendInner")
        self.legend_grid = QtWidgets.QGridLayout(inner)
        self.legend_grid.setContentsMargins(0, 0, 4, 0)
        self.legend_grid.setHorizontalSpacing(8)
        self.legend_grid.setVerticalSpacing(2)
        self.legend_grid.setColumnStretch(1, 1)
        scroll.setWidget(inner)
        side.addWidget(scroll, 1)
        self._legend_values = {}

        self.empty_label = QtWidgets.QLabel("")
        self.empty_label.setObjectName("EmptyState")
        self.empty_label.setTextFormat(QtCore.Qt.RichText)
        self.empty_label.setAlignment(QtCore.Qt.AlignCenter)
        self.empty_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)

        plot_row = QtWidgets.QHBoxLayout()
        plot_row.setSpacing(12)
        plot_row.addWidget(self.plot_widget, 1)
        plot_row.addWidget(self.side_panel)
        plot_card.body.addLayout(plot_row, 1)

        body.addWidget(left_panel)
        body.addWidget(plot_card, stretch=1)

        # Leerzustand ueber dem (dann leeren) Plot
        self.empty_label.setParent(self.plot_widget)
        self.plot_widget.installEventFilter(self)

        self.status = self.statusBar()
        self.status.setSizeGripEnabled(False)
        self.status_caps = QtWidgets.QLabel("LETZTE AKTION")
        self.status_caps.setStyleSheet("font-size: 9pt; font-weight: 600;")
        self.status.addWidget(self.status_caps)
        self.status_text = QtWidgets.QLabel("Bereit. Noch keine Datei geladen.")
        self.status.addWidget(self.status_text, 1)

        # Menu
        file_menu = self.menuBar().addMenu("&Datei")
        open_action = QtGui.QAction("CSV öffnen …", self)
        open_action.setShortcut(QtGui.QKeySequence.Open)
        open_action.triggered.connect(self.open_csv_dialog)
        file_menu.addAction(open_action)
        reload_action = QtGui.QAction("Neu laden", self)
        reload_action.setShortcut(QtGui.QKeySequence(QtCore.Qt.Key_F5))
        reload_action.triggered.connect(self.reload_csv)
        file_menu.addAction(reload_action)
        file_menu.addSeparator()
        exit_action = QtGui.QAction("Beenden", self)
        exit_action.setShortcut(QtGui.QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        view_menu = self.menuBar().addMenu("&Ansicht")
        fit_action = QtGui.QAction("Ansicht anpassen", self)
        fit_action.setShortcut(QtGui.QKeySequence("Ctrl+0"))
        fit_action.triggered.connect(self.fit_view)
        view_menu.addAction(fit_action)
        view_menu.addSeparator()
        self.theme_actions = {}
        group = QtGui.QActionGroup(self)
        for key in ("dark", "light"):
            act = QtGui.QAction(f"Farbschema {THEME_LABELS[key]}", self, checkable=True)
            act.triggered.connect(lambda checked=False, k=key: self.set_theme(k))
            group.addAction(act)
            view_menu.addAction(act)
            self.theme_actions[key] = act

        tab_focus_only(open_btn, self.reload_btn, select_all_btn, select_none_btn, self.fit_btn)

    def _build_header(self):
        """Kopfzeile wie gui_theme.app_header(): Titel, Untertitel und der
        Farbschema-Schalter Dunkel | Hell."""
        bar = QtWidgets.QWidget()
        bar.setObjectName("AppHeader")
        bar.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        lay = QtWidgets.QHBoxLayout(bar)
        lay.setContentsMargins(18, 10, 14, 10)
        lay.setSpacing(12)
        title = QtWidgets.QLabel(APP_TITLE)
        title.setObjectName("AppTitle")
        sub = QtWidgets.QLabel("Kennlinien aus den GUI-Logs der Admin-GUI")
        sub.setObjectName("HeaderMuted")
        lay.addWidget(title)
        lay.addWidget(sub, 0, QtCore.Qt.AlignBottom)
        lay.addStretch(1)
        cap = QtWidgets.QLabel("Farbschema")
        cap.setObjectName("HeaderMuted")
        lay.addWidget(cap)
        self.theme_buttons = {}
        seg = QtWidgets.QHBoxLayout()
        seg.setSpacing(2)
        group = QtWidgets.QButtonGroup(bar)
        group.setExclusive(True)
        for key in ("dark", "light"):
            b = QtWidgets.QPushButton(THEME_LABELS[key])
            b.setProperty("seg", True)
            b.setCheckable(True)
            b.clicked.connect(lambda checked=False, k=key: self.set_theme(k))
            group.addButton(b)
            seg.addWidget(b)
            self.theme_buttons[key] = b
        tab_focus_only(*self.theme_buttons.values())
        lay.addLayout(seg)
        return bar

    def _connect_signals(self):
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.filter_edit.textChanged.connect(self._apply_filter)
        proxy = pg.SignalProxy(
            self.plot_widget.scene().sigMouseMoved, rateLimit=60, slot=self._on_mouse_moved
        )
        self._mouse_proxy = proxy  # Referenz halten, sonst wird proxy garbage-collected

    # -------------------------------------------------------------- Theme
    def set_theme(self, name, persist=True):
        if name not in PALETTES:
            return
        self.theme_name = name
        self.p = p = PALETTES[name]
        _CURRENT_THEME["name"] = name
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.setPalette(build_palette(p))
            app.setStyleSheet(build_stylesheet(p))
        for key, b in self.theme_buttons.items():
            b.setChecked(key == name)
        for key, act in self.theme_actions.items():
            act.setChecked(key == name)
        set_dark_title_bar(self, name == "dark")
        if persist:
            self.settings.setValue("theme", name)

        self.plot_widget.setBackground(p["plot"])
        for side in ("left", "bottom", "right"):
            self._style_axis(self.plot_item.getAxis(side))
        cross = pg.mkPen(p["crosshair"], width=1, style=QtCore.Qt.DashLine)
        self.vline.setPen(cross)
        self.hline.setPen(cross)
        legend = self.plot_item.legend
        if legend is not None:
            fill = QtGui.QColor(p["surface2"])
            fill.setAlpha(225)
            legend.setBrush(pg.mkBrush(fill))
            legend.setPen(pg.mkPen(p["border_strong"]))
            legend.setLabelTextColor(p["text"])

        # Kurvenfarben haengen vom Farbschema ab (Botenstoffe bleiben fest)
        for entry in self.curves.values():
            entry.color = self._color_for(entry.name, entry.color_index)
            if entry.tree_item is not None:
                entry.tree_item.setIcon(0, swatch_icon(entry.color))
        self._style_group_items()
        self._update_empty_state()
        if self.df is not None and any(e.checked for e in self.curves.values()):
            self._rebuild_plot()

    def _color_for(self, name, index):
        if name in NEURO_PALETTE:
            return NEURO_PALETTE[name]
        cols = self.p["curves"]
        return cols[index % len(cols)]

    def _style_axis(self, axis, color=None):
        """Achsen in den Theme-Farben; color faerbt Beschriftung und Zahlen
        (Multi-Achsen-Modus: Farbe der Kurve)."""
        if axis is None:
            return
        font = QtGui.QFont(ui_font_family(), 9)
        axis.setPen(pg.mkPen(self.p["border_strong"]))
        axis.setTextPen(pg.mkPen(color or self.p["muted"]))
        axis.setStyle(tickFont=font, tickTextOffset=6)
        label_text = axis.labelText
        if label_text:
            axis.setLabel(label_text, color=color or self.p["muted"], **{"font-size": "9pt"})

    def _axis_label(self, side, text, color=None):
        self.plot_item.setLabel(side, text, color=color or self.p["muted"], **{"font-size": "9pt"})

    def _style_group_items(self):
        p = self.p
        font = QtGui.QFont(self.tree.font())
        font.setWeight(QtGui.QFont.DemiBold)
        for i in range(self.tree.topLevelItemCount()):
            g = self.tree.topLevelItem(i)
            g.setFont(0, font)
            g.setForeground(0, QtGui.QBrush(QtGui.QColor(p["text"])))
            g.setForeground(1, QtGui.QBrush(QtGui.QColor(p["muted"])))
            g.setTextAlignment(1, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

    def _update_group_counts(self):
        self.tree.blockSignals(True)
        for i in range(self.tree.topLevelItemCount()):
            g = self.tree.topLevelItem(i)
            total = g.childCount()
            on = sum(1 for j in range(total) if g.child(j).checkState(0) == QtCore.Qt.Checked)
            g.setText(1, f"{on} / {total}")
        self.tree.blockSignals(False)
        n = sum(1 for e in self.curves.values() if e.checked)
        self.active_pill.setText(f"{n} aktiv")
        self.active_pill.setProperty("pill", "info" if n else "muted")
        self.active_pill.style().unpolish(self.active_pill)
        self.active_pill.style().polish(self.active_pill)

    # ------------------------------------------------------- Leerzustand
    def eventFilter(self, obj, event):
        if obj is self.plot_widget and event.type() == QtCore.QEvent.Resize:
            self._place_empty_label()
        return super().eventFilter(obj, event)

    def _place_empty_label(self):
        self.empty_label.setGeometry(0, 0, self.plot_widget.width(), self.plot_widget.height())

    def _update_empty_state(self):
        p = self.p
        if self.df is None:
            title, hint = "Keine Datei geladen", \
                "CSV öffnen (Strg+O) oder eine gui_log_*.csv in das Fenster ziehen."
        elif not any(e.checked for e in self.curves.values()):
            title, hint = "Keine Kennlinie ausgewählt", \
                "Links in der Liste Kennlinien anhaken oder „Alle an“ wählen."
        else:
            self.empty_label.hide()
            self._set_plot_chrome(True)
            self._update_mode_texts()
            return
        self._set_plot_chrome(False)
        self.empty_label.setText(
            f"<div style='font-size:13pt; font-weight:600; color:{p['text']};'>{title}</div>"
            f"<div style='margin-top:6px; color:{p['muted']};'>{hint}</div>")
        self._place_empty_label()
        self.empty_label.show()
        self.empty_label.raise_()
        self._update_mode_texts()

    def _set_plot_chrome(self, visible):
        """Achsen, Gitter und Legende nur zeigen, wenn Kurven da sind."""
        self.fit_btn.setEnabled(visible)
        for b in self.select_buttons:
            b.setEnabled(self.df is not None)
        for side in ("left", "bottom"):
            if visible:
                self.plot_item.showAxis(side)
            else:
                self.plot_item.hideAxis(side)
        if not visible:
            self.plot_item.hideAxis("right")
        if self.plot_item.legend is not None:
            self.plot_item.legend.setVisible(visible)
        self.side_panel.setVisible(visible)

    def _update_mode_texts(self):
        mode = self.mode_combo.currentText()
        self.mode_hint.setText(MODE_HINTS.get(mode, ""))
        if self.plot_subtitle is not None:
            if self.df is None:
                self.plot_subtitle.setText("Noch keine Daten")
            else:
                n = sum(1 for e in self.curves.values() if e.checked)
                x = "Zeit (" + self.ts_col + ")" if self.ts_col else "Zeilennummer"
                self.plot_subtitle.setText(f"{mode}  ·  {n} Kennlinie{'n' if n != 1 else ''}  ·  X-Achse: {x}")

    # -------------------------------------------------------- Drag & Drop
    def dragEnterEvent(self, event):
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if any(u.isLocalFile() and os.path.isfile(u.toLocalFile()) for u in urls):
            event.acceptProposedAction()

    def dropEvent(self, event):
        for u in event.mimeData().urls():
            if u.isLocalFile() and os.path.isfile(u.toLocalFile()):
                self.load_csv(u.toLocalFile())
                break

    # -------------------------------------------------------------- Laden
    def open_csv_dialog(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "CSV-Datei öffnen", "", "CSV-Dateien (*.csv);;Alle Dateien (*)"
        )
        if path:
            self.load_csv(path)

    def reload_csv(self):
        if self.current_path:
            self.load_csv(self.current_path, keep_selection=True)

    @staticmethod
    def _read_csv(path):
        """Liest das Log robust: zuerst als Komma-CSV (Format der BrainStem-GUI),
        sonst mit automatischer Trennzeichen-Erkennung. Unvollstaendige Zeilen
        (z.B. die letzte Zeile, waehrend der Logger noch schreibt) werden
        uebersprungen und gezaehlt."""
        skipped = []
        def on_bad(line):
            skipped.append(line)
            return None
        try:
            df = pd.read_csv(path, sep=",", engine="python", on_bad_lines=on_bad,
                             encoding="utf-8-sig")
            if len(df.columns) > 1:
                return df, len(skipped)
        except (pd.errors.ParserError, UnicodeDecodeError, ValueError):
            pass
        skipped.clear()
        df = pd.read_csv(path, sep=None, engine="python", on_bad_lines=on_bad,
                         encoding="utf-8-sig")
        return df, len(skipped)

    @staticmethod
    def _ends_with_newline(path):
        try:
            with open(path, "rb") as fh:
                fh.seek(0, os.SEEK_END)
                if fh.tell() == 0:
                    return True
                fh.seek(-1, os.SEEK_END)
                return fh.read(1) in (b"\n", b"\r")
        except OSError:
            return True

    def load_csv(self, path, keep_selection=False):
        try:
            df, skipped = self._read_csv(path)
            if len(df) and not self._ends_with_newline(path):
                # letzte Zeile wird gerade noch geschrieben (Logger aktiv):
                # sie kann abgeschnittene Zahlen enthalten
                df = df.iloc[:-1]
                skipped += 1
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Fehler beim Laden", str(exc))
            return

        # Spaltennamen bereinigen (Backslash-Escapes aus manchen Exporten entfernen)
        df.columns = [str(c).replace("\\", "").strip() for c in df.columns]

        selected = set()
        if keep_selection:
            selected = {name for name, entry in self.curves.items() if entry.checked}

        self.current_path = path
        self.df = df
        self._values_cache = {}
        self.file_label.setText(os.path.basename(path))
        self.file_label.setToolTip(path)
        self.setWindowTitle(f"{APP_TITLE} - {os.path.basename(path)}")
        self.reload_btn.setEnabled(True)
        self._prepare_axes()
        self._populate_tree(selected)
        self._update_file_meta(skipped)
        if any(entry.checked for entry in self.curves.values()):
            self._rebuild_plot()
        else:
            self._clear_plot()
            self.info_label.setText("")
        self._update_group_counts()
        self._update_empty_state()
        msg = f"{len(self.df)} Zeilen, {len(self.df.columns)} Spalten geladen aus {path}"
        if skipped:
            msg += f" ({skipped} unvollständige Zeile(n) übersprungen)"
        self.status_text.setText(msg)
        self.status_text.setToolTip(msg)

    def _update_file_meta(self, skipped):
        parts = [f"{len(self.df):,} Zeilen".replace(",", " "), f"{len(self.df.columns)} Spalten",
                 f"{len(self.curves)} Kennlinien"]
        lines = ["  ·  ".join(parts)]
        if self.is_time_axis:
            valid = self.x_raw.dropna()
            if len(valid):
                a, b = pd.to_datetime(valid.iloc[0]), pd.to_datetime(valid.iloc[-1])
                same_day = a.date() == b.date()
                span = (f"{a:%d.%m.%Y}, {a:%H:%M} bis {b:%H:%M} Uhr" if same_day
                        else f"{a:%d.%m.%Y %H:%M} bis {b:%d.%m.%Y %H:%M}")
                lines.append(span)
        else:
            lines.append("Keine Zeitspalte, X-Achse ist die Zeilennummer")
        if skipped:
            lines.append(f"{skipped} unvollständige Zeile(n) übersprungen")
        self.file_meta.setText("\n".join(lines))

    def _prepare_axes(self):
        df = self.df
        ts_col = None
        for cand in TIMESTAMP_CANDIDATES:
            if cand in df.columns:
                ts_col = cand
                break
        if ts_col is None:
            for c in df.columns:
                if "time" in c.lower() or "date" in c.lower():
                    ts_col = c
                    break

        if ts_col is not None and len(df):
            converted = to_epoch_seconds(df[ts_col])
            if converted is not None:
                seconds, parsed = converted
                if not seconds.dropna().is_monotonic_increasing:
                    # z.B. zusammengefuegte Logs: zeitlich sortieren, damit
                    # Kurven nicht hin- und herspringen
                    order = np.argsort(seconds.to_numpy(), kind="stable")
                    df = df.iloc[order].reset_index(drop=True)
                    self.df = df
                    seconds = seconds.iloc[order].reset_index(drop=True)
                    parsed = parsed.iloc[order].reset_index(drop=True)
                self.x_raw = parsed
                self.x_seconds = seconds
                self.is_time_axis = True
                self.ts_col = ts_col
                return

        # Fallback: Zeilenindex als X-Achse
        self.x_raw = pd.Series(np.arange(len(df)))
        self.x_seconds = self.x_raw.astype(float)
        self.is_time_axis = False
        self.ts_col = None

    def _populate_tree(self, selected=frozenset()):
        self._selected_on_load = set(selected)
        self.tree.blockSignals(True)
        self.tree.clear()
        self.curves = {}
        self.color_cycle = itertools.count()

        df = self.df
        assigned = set()
        if self.ts_col:
            assigned.add(self.ts_col)

        # 1) bekannte Gruppen zuerst, in fester Reihenfolge
        for group_name, cols in KNOWN_GROUPS.items():
            existing = [c for c in cols if c in df.columns and c not in assigned]
            if not existing:
                continue
            group_item = QtWidgets.QTreeWidgetItem([group_name, ""])
            group_item.setFlags(group_item.flags() & ~QtCore.Qt.ItemIsUserCheckable)
            self.tree.addTopLevelItem(group_item)
            for col in existing:
                if col in TEXT_ONLY_COLUMNS:
                    continue
                if not self._is_plottable(df[col]):
                    continue
                self._add_curve_item(group_item, col, group_name)
                assigned.add(col)
            group_item.setExpanded(True)

        # 2) Rest -> "Sonstige"
        remaining = [c for c in df.columns if c not in assigned and c not in TEXT_ONLY_COLUMNS]
        remaining = [c for c in remaining if self._is_plottable(df[c])]
        if remaining:
            other_item = QtWidgets.QTreeWidgetItem(["Sonstige", ""])
            other_item.setFlags(other_item.flags() & ~QtCore.Qt.ItemIsUserCheckable)
            self.tree.addTopLevelItem(other_item)
            for col in remaining:
                self._add_curve_item(other_item, col, "Sonstige")
            other_item.setExpanded(False)

        self._style_group_items()
        self.tree.blockSignals(False)

    def _is_plottable(self, series: pd.Series) -> bool:
        return is_plottable(series)

    def _add_curve_item(self, parent_item, col_name, group_name):
        index = 0 if col_name in NEURO_PALETTE else next(self.color_cycle)
        color = self._color_for(col_name, index)
        entry = CurveEntry(col_name, color, group_name)
        entry.color_index = index
        entry.checked = col_name in self._selected_on_load
        self.curves[col_name] = entry

        item = QtWidgets.QTreeWidgetItem([col_name, ""])
        item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
        item.setCheckState(0, QtCore.Qt.Checked if entry.checked else QtCore.Qt.Unchecked)
        item.setIcon(0, swatch_icon(color))
        item.setToolTip(0, f"{col_name}  ({group_name})")
        item.setData(0, QtCore.Qt.UserRole, col_name)
        entry.tree_item = item
        parent_item.addChild(item)

    def _set_all_checked(self, checked: bool):
        state = QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked
        self.tree.blockSignals(True)
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            for j in range(group.childCount()):
                child = group.child(j)
                if not child.isHidden():
                    child.setCheckState(0, state)
                    # Signale sind blockiert: Zustand direkt uebernehmen
                    col_name = child.data(0, QtCore.Qt.UserRole)
                    if col_name in self.curves:
                        self.curves[col_name].checked = checked
        self.tree.blockSignals(False)
        self._update_group_counts()
        self._rebuild_plot()

    def _apply_filter(self, text):
        text = text.lower().strip()
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            any_visible = False
            for j in range(group.childCount()):
                child = group.child(j)
                match = text in child.text(0).lower()
                child.setHidden(not match)
                any_visible = any_visible or match
            group.setHidden(not any_visible)
            if text and any_visible:
                group.setExpanded(True)

    def _on_item_changed(self, item, column):
        col_name = item.data(0, QtCore.Qt.UserRole)
        if col_name is None:
            return
        self.curves[col_name].checked = item.checkState(0) == QtCore.Qt.Checked
        self._update_group_counts()
        self._rebuild_plot()

    def _on_mode_changed(self):
        self._rebuild_plot()
        self._update_mode_texts()

    def fit_view(self):
        """Alle ViewBoxes wieder auf den vollen Datenbereich."""
        self.view_box.enableAutoRange()
        for vb in self.extra_view_boxes:
            vb.enableAutoRange(axis=pg.ViewBox.YAxis)
        self._pad_constant_ranges()

    # -------------------------------------------------------------- Plot
    def _clear_plot(self):
        self.plot_item.clear()
        for entry in self.curves.values():
            entry.curve_item = None
            entry.view_box = None
            entry.axis_item = None
        for vb in self.extra_view_boxes:
            vb.setXLink(None)
            vb.clear()
            if vb.scene() is not None:
                vb.scene().removeItem(vb)
        self.extra_view_boxes = []
        if self._update_extra_views_ref is not None:
            try:
                self.plot_item.vb.sigResized.disconnect(self._update_extra_views_ref)
            except (TypeError, RuntimeError):
                pass
            self._update_extra_views_ref = None
        # zusaetzliche rechte Achsen entfernen; die erste ersetzt die rechte
        # Standardachse und wird beim naechsten setAxisItems() von pyqtgraph
        # selbst entfernt, die weiteren haengen frei im Layout
        right_axis = self.plot_item.getAxis("right")
        for axis_item in self._extra_axis_items:
            axis_item.unlinkFromView()
            if axis_item is right_axis:
                continue
            self.plot_item.layout.removeItem(axis_item)
            if axis_item.scene() is not None:
                axis_item.scene().removeItem(axis_item)
        self._extra_axis_items = []
        self.plot_item.getAxis("left").setTextPen(pg.mkPen(self.p["muted"]))
        self.plot_item.setLabel("left", "")
        self.plot_item.hideAxis("right")
        self.plot_item.addItem(self.vline, ignoreBounds=True)
        self.plot_item.addItem(self.hline, ignoreBounds=True)
        self.vline.hide()
        self.hline.hide()
        self._clear_legend()
        legend = self.plot_item.legend
        if legend is not None:
            legend.clear()
        # Die BrainStem-Zeitstempel sind lokale Uhrzeit ohne Zeitzone; mit
        # utcOffset=0 zeigt die Achse sie unveraendert an (sonst wuerde die
        # Achse um den Abstand zur UTC-Zeit verschoben).
        bottom = self.plot_item.getAxis("bottom")
        if self.is_time_axis and not isinstance(bottom, pg.DateAxisItem):
            self.plot_item.setAxisItems({"bottom": pg.DateAxisItem(orientation="bottom", utcOffset=0)})
        elif not self.is_time_axis and isinstance(bottom, pg.DateAxisItem):
            self.plot_item.setAxisItems({"bottom": pg.AxisItem(orientation="bottom")})
        self._style_axis(self.plot_item.getAxis("bottom"))
        self._style_axis(self.plot_item.getAxis("left"))
        self._axis_label("bottom", self.ts_col if self.ts_col else "Zyklus / Zeile")

    def _get_series_values(self, col_name):
        values = self._values_cache.get(col_name)
        if values is None:
            values = to_numeric_values(self.df[col_name])
            self._values_cache[col_name] = values
        return values

    def _pen(self, entry):
        return pg.mkPen(entry.color, width=2)

    def _rebuild_plot(self):
        if self.df is None:
            return
        self._clear_plot()

        mode = self.mode_combo.currentText()
        active = [c for c in self.curves.values() if c.checked]
        x = self.x_seconds.to_numpy(dtype=float)

        if not active:
            self.info_label.setText("Keine Kennlinie ausgewählt.")
            self._update_empty_state()
            return

        if mode == self.MODE_MULTI_AXIS:
            self._plot_multi_axis(active, x)
        elif mode == self.MODE_NORMALIZED:
            self._plot_normalized(active, x)
        else:
            self._plot_original(active, x)
        self._pad_constant_ranges()
        self._build_legend(active, mode)

        hint = ""
        if mode == self.MODE_MULTI_AXIS and len(active) > 6:
            hint = " Bei mehr als 6 Kurven ist „Überlagert, normalisiert“ meist besser lesbar."
        self.info_label.setText(
            f"{len(active)} Kennlinie{'n' if len(active) != 1 else ''} aktiv. "
            f"Legende und Werte am Mauszeiger stehen rechts neben dem Diagramm.{hint}")
        self._update_empty_state()

    def _pad_constant_ranges(self):
        """Konstante Kurven (z.B. chunks_total) bekommen einen kleinen
        Wertebereich, sonst zeigt die Achse nur denselben Wert in Serie."""
        def pad(vb, values):
            finite = values[np.isfinite(values)]
            if finite.size and float(finite.max() - finite.min()) <= 1e-12:
                v = float(finite[0])
                d = max(abs(v) * 0.05, 1.0 if abs(v) >= 1 else 0.05)
                vb.setYRange(v - d, v + d, padding=0)
        mode = self.mode_combo.currentText()
        if mode == self.MODE_MULTI_AXIS:
            for entry in self.curves.values():
                if entry.checked and entry.curve_item is not None:
                    vb = entry.view_box or self.plot_item.vb
                    pad(vb, self._get_series_values(entry.name))
        elif mode == self.MODE_ORIGINAL:
            active = [e for e in self.curves.values() if e.checked]
            if active:
                pad(self.plot_item.vb, np.concatenate([self._get_series_values(e.name) for e in active]))

    def _plot_original(self, active, x):
        self._axis_label("left", "Wert (Original)")
        legend = self.plot_item.legend
        for entry in active:
            y = self._get_series_values(entry.name)
            # FIX: clipToView NICHT als Konstruktor-Kwarg uebergeben - siehe
            # Kommentar in _plot_multi_axis fuer die vollstaendige Erklaerung
            # (bekannter pyqtgraph-Bug, GitHub-Issue #1854).
            curve = self.plot_item.plot(
                x, y, pen=self._pen(entry),
                name=entry.name, autoDownsample=True,
            )
            curve.setClipToView(True)
            entry.curve_item = curve
        self.view_box.enableAutoRange()

    def _plot_normalized(self, active, x):
        self._axis_label("left", "Normalisiert (0–1)")
        for entry in active:
            y = self._get_series_values(entry.name)
            finite = y[np.isfinite(y)]
            if finite.size == 0:
                continue
            y_min, y_max = float(finite.min()), float(finite.max())
            if y_max - y_min > 1e-12:
                y_norm = (y - y_min) / (y_max - y_min)
            else:
                y_norm = np.zeros_like(y)
            entry.norm_range = (y_min, y_max)
            curve = self.plot_item.plot(
                x, y_norm, pen=self._pen(entry),
                name=f"{entry.name}  [{format_value(y_min)} … {format_value(y_max)}]",
                autoDownsample=True,
            )
            curve.setClipToView(True)
            entry.curve_item = curve
        self.view_box.enableAutoRange()

    def _plot_multi_axis(self, active, x):
        # FIX: DAS war die eigentliche Ursache fuer den kompletten Absturz
        # "Error calling Python override of QGraphicsObject::itemChange():
        # autoRangeEnabled" - unabhaengig von der genauen PySide6-Version.
        # Bekannter pyqtgraph-Bug (GitHub-Issue #1854, seit 2021 offen):
        # wird clipToView=True DIREKT IM KONSTRUKTOR von PlotDataItem bzw.
        # PlotItem.plot() uebergeben, kann pyqtgraphs interne
        # GraphicsItem.getViewBox() beim ersten "Parent geaendert"-Ereignis
        # faelschlich das PlotWidget statt die eigentliche ViewBox
        # zurueckgeben. Das PlotWidget besitzt aber kein autoRangeEnabled(),
        # daher der Absturz - BEVOR ueberhaupt eine Linie gezeichnet wird.
        # Offizieller Workaround aus dem Issue: clipToView erst NACH dem
        # Hinzufuegen zum Plot per setClipToView(True) setzen, nie als
        # Konstruktor-Kwarg. Das wird jetzt in allen drei Zeichenmodi so
        # gehandhabt.
        # Erste Kurve bekommt die linke Standardachse
        first = active[0]
        y0 = self._get_series_values(first.name)
        curve0 = self.plot_item.plot(
            x, y0, pen=self._pen(first), name=first.name,
            autoDownsample=True,
        )
        curve0.setClipToView(True)
        first.curve_item = curve0
        self.plot_item.getAxis("left").setTextPen(first.color)
        self._axis_label("left", first.name, color=first.color)
        self.plot_item.vb.enableAutoRange(axis=pg.ViewBox.YAxis)

        self._extra_axis_items = []
        self.plot_item.showAxis("right")
        n_extra = len(active) - 1

        for idx, entry in enumerate(active[1:]):
            y = self._get_series_values(entry.name)

            vb = pg.ViewBox()
            self.plot_item.scene().addItem(vb)
            vb.setXLink(self.plot_item.vb)

            axis = pg.AxisItem("right")
            axis.enableAutoSIPrefix(False)
            axis.setLabel(entry.name)
            self._style_axis(axis, color=entry.color)
            axis.linkToView(vb)

            if idx == 0:
                self.plot_item.setAxisItems({"right": axis})
                self.plot_item.showAxis("right")
            else:
                # weitere Achsen als zusaetzliche Spalten direkt rechts neben
                # der rechten Standardachse (Spalte 2) anhaengen
                col = 2 + idx
                self.plot_item.layout.addItem(axis, 2, col)
            self._extra_axis_items.append(axis)

            curve = pg.PlotDataItem(
                x, y, pen=self._pen(entry), name=entry.name,
                autoDownsample=True,
            )
            vb.addItem(curve)
            # FIX: siehe Kommentar oben - erst NACH vb.addItem(curve) setzen.
            curve.setClipToView(True)
            entry.curve_item = curve
            entry.view_box = vb
            entry.axis_item = axis
            vb.enableAutoRange(axis=pg.ViewBox.YAxis)

            legend = self.plot_item.legend
            if legend is not None:
                legend.addItem(curve, entry.name)

            self.extra_view_boxes.append(vb)

        def update_extra_views():
            for vb in self.extra_view_boxes:
                vb.setGeometry(self.plot_item.vb.sceneBoundingRect())
                vb.linkedViewChanged(self.plot_item.vb, vb.XAxis)

        update_extra_views()
        if self.extra_view_boxes:
            self._update_extra_views_ref = update_extra_views
            self.plot_item.vb.sigResized.connect(self._update_extra_views_ref)
        else:
            self.plot_item.hideAxis("right")

    # -------------------------------------------------------------- Hover
    # ------------------------------------------------------------ Legende
    CURSOR_HINT = "Maus über das Diagramm bewegen, um die Werte zu sehen."

    def _clear_legend(self):
        while self.legend_grid.count():
            w = self.legend_grid.takeAt(0).widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        for r in range(self.legend_grid.rowCount()):
            self.legend_grid.setRowStretch(r, 0)  # Reste frueherer Legenden
        self._legend_values = {}
        self.cursor_label.setText(self._cursor_hint())

    def _cursor_hint(self):
        return f"<span style='color:{self.p['muted']}; font-weight:400;'>{self.CURSOR_HINT}</span>"

    def _build_legend(self, active, mode):
        """Eine Zeile je aktiver Kurve: Farbfeld, Name, Wert am Zeiger.
        Im normalisierten Modus darunter der Originalbereich."""
        self._clear_legend()
        row = 0
        name_width = 150
        for entry in active:
            if entry.curve_item is None:
                continue
            sw = QtWidgets.QLabel()
            sw.setPixmap(swatch_icon(entry.color, 12).pixmap(12, 12))
            name = QtWidgets.QLabel()
            fm = name.fontMetrics()
            name.setText(fm.elidedText(entry.name, QtCore.Qt.ElideMiddle, name_width))
            name.setToolTip(entry.name)
            val = QtWidgets.QLabel("–")
            val.setObjectName("LegendValue")
            val.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            self.legend_grid.addWidget(sw, row, 0)
            self.legend_grid.addWidget(name, row, 1)
            self.legend_grid.addWidget(val, row, 2)
            self._legend_values[entry.name] = val
            row += 1
            if mode == self.MODE_NORMALIZED and entry.norm_range is not None:
                lo, hi = entry.norm_range
                rng = QtWidgets.QLabel(f"Bereich {format_value(lo)} … {format_value(hi)}")
                rng.setObjectName("LegendRange")
                self.legend_grid.addWidget(rng, row, 1, 1, 2)
                row += 1
        self.legend_grid.setRowStretch(row, 1)

    def _reset_cursor_values(self):
        for label in self._legend_values.values():
            label.setText("–")
        self.cursor_label.setText(self._cursor_hint())

    # -------------------------------------------------------------- Hover
    def _on_mouse_moved(self, evt):
        pos = evt[0]
        if self.df is None or not self.plot_item.sceneBoundingRect().contains(pos):
            self.vline.hide()
            self.hline.hide()
            self._reset_cursor_values()
            return
        if not any(e.checked and e.curve_item is not None for e in self.curves.values()):
            return

        mouse_point = self.view_box.mapSceneToView(pos)
        x_val = mouse_point.x()

        x_arr = self.x_seconds.to_numpy(dtype=float)
        if not np.isfinite(x_arr).any():
            self._reset_cursor_values()
            return
        # naechstgelegener Datenpunkt (statt erster Punkt rechts vom Zeiger)
        idx = int(np.nanargmin(np.abs(x_arr - x_val)))

        self.vline.setPos(x_arr[idx])
        self.hline.setPos(mouse_point.y())
        self.vline.show()
        self.hline.show()

        if self.is_time_axis:
            x_label = pd.to_datetime(self.x_raw.iloc[idx]).strftime("%d.%m.%Y  %H:%M:%S")
        else:
            x_label = f"Zeile {idx}"
        self.cursor_label.setText(x_label)

        # immer die Originalwerte, unabhaengig vom Darstellungsmodus
        for entry in self.curves.values():
            label = self._legend_values.get(entry.name)
            if label is not None and entry.checked and entry.curve_item is not None:
                label.setText(format_value(self._get_series_values(entry.name)[idx]))

MODE_HINTS.update({
    CsvViewerWindow.MODE_MULTI_AXIS: "Jede Kurve hat eine eigene, unabhängig skalierte Y-Achse "
                                     "(erste links, weitere rechts). Gut lesbar bis etwa 6 Kurven.",
    CsvViewerWindow.MODE_NORMALIZED: "Alle Kurven auf 0 bis 1 skaliert und überlagert. "
                                     "Die Legende nennt den Originalbereich jeder Kurve.",
    CsvViewerWindow.MODE_ORIGINAL: "Alle Kurven in Originalwerten auf einer gemeinsamen Achse. "
                                   "Sinnvoll bei ähnlichen Wertebereichen.",
})


def setup_application(app):
    """Grundschrift und Stil wie die Admin-GUI (Segoe UI 10, Fusion-Basis)."""
    app.setStyle(BrainStemStyle(lambda: PALETTES[_CURRENT_THEME["name"]]))
    app.setFont(QtGui.QFont(ui_font_family(), 10))
    app.setApplicationName(APP_TITLE)


def main():
    app = QtWidgets.QApplication(sys.argv)
    setup_application(app)
    win = CsvViewerWindow()
    win.show()

    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        win.load_csv(sys.argv[1])

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
