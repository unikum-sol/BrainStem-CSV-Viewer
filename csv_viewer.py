#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BrainStem CSV Viewer
=====================
Eigenstaendiger, vom BrainStem-System entkoppelter Viewer fuer GUI-Log-CSV-
Dateien (z.B. gui_log_*.csv). Zeigt beliebig viele Kennlinien in einem
gemeinsamen Fenster an, erlaubt das Ein-/Ausschalten einzelner Kurven,
Ueberlagerung mehrerer Kurven sowie unterschiedliche Skalierungen pro Wert.

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
    "Fortschritt / Zaehler": [
        "chunks_covered", "chunks_total", "chunks_pct", "hypotheses_total",
        "documents", "chunks_stat", "facts", "relations", "ontology",
        "questions", "phase7d_survivors", "phase7d_participated",
        "phase7d_weakened", "phase7d_threshold",
    ],
}

# Textspalten, die niemals als Kennlinie geplottet werden (nur Kontext/Log-Text)
TEXT_ONLY_COLUMNS = {"stageb_experiment_summary"}

TIMESTAMP_CANDIDATES = ["timestamp_iso", "timestamp", "time", "datetime", "date"]

COLOR_PALETTE = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    "#aec7e8", "#ffbb78", "#98df8a", "#ff9896", "#c5b0d5",
    "#c49c94", "#f7b6d2", "#c7c7c7", "#dbdb8d", "#9edae5",
]


BOOL_MAPPING = {"true": 1.0, "false": 0.0, "wahr": 1.0, "falsch": 0.0, "ja": 1.0, "nein": 0.0}
EMPTY_MARKERS = {"", "nan", "none", "n/a", "na", "null", "-"}


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
        self.checked = False
        self.curve_item = None   # pg.PlotDataItem
        self.view_box = None     # eigene ViewBox (nur im Multi-Achsen-Modus)
        self.axis_item = None    # eigene AxisItem (nur im Multi-Achsen-Modus)


class CsvViewerWindow(QtWidgets.QMainWindow):
    MODE_ORIGINAL = "Original (gemeinsame Achse)"
    MODE_NORMALIZED = "Ueberlagert, normalisiert (0-1)"
    MODE_MULTI_AXIS = "Eigene Achse je Kurve (Multi-Achsen)"

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1500, 900)

        self.df = None
        self.x_raw = None          # datetime64 Series (oder Zyklusindex)
        self.x_seconds = None      # float epoch seconds fuer pg.DateAxisItem
        self.is_time_axis = False
        self.curves = {}           # name -> CurveEntry
        self.color_cycle = itertools.cycle(COLOR_PALETTE)
        self.extra_view_boxes = []  # aktive zusaetzliche ViewBoxes (Multi-Achse)
        self._extra_axis_items = []
        self._update_extra_views_ref = None
        self._values_cache = {}     # Spaltenname -> Float-Array
        self.ts_col = None
        self.current_path = None

        self._build_ui()
        self._connect_signals()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        pg.setConfigOptions(antialias=True, background="w", foreground="k")

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main_layout = QtWidgets.QHBoxLayout(central)

        # ---------- linkes Panel: Steuerung + Kennlinien-Auswahl ----------
        left_panel = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        left_panel.setMaximumWidth(340)
        left_panel.setMinimumWidth(300)

        self.file_label = QtWidgets.QLabel("Keine Datei geladen")
        self.file_label.setWordWrap(True)
        self.file_label.setStyleSheet("font-weight: bold;")
        left_layout.addWidget(self.file_label)

        open_btn = QtWidgets.QPushButton("CSV oeffnen...")
        open_btn.clicked.connect(self.open_csv_dialog)
        left_layout.addWidget(open_btn)

        left_layout.addWidget(QtWidgets.QLabel("Darstellungsmodus:"))
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItems([
            self.MODE_MULTI_AXIS,
            self.MODE_NORMALIZED,
            self.MODE_ORIGINAL,
        ])
        left_layout.addWidget(self.mode_combo)

        # Suchfilter fuer die Kennlinienliste
        self.filter_edit = QtWidgets.QLineEdit()
        self.filter_edit.setPlaceholderText("Kennlinien filtern...")
        left_layout.addWidget(self.filter_edit)

        btn_row = QtWidgets.QHBoxLayout()
        select_all_btn = QtWidgets.QPushButton("Alle an")
        select_none_btn = QtWidgets.QPushButton("Alle aus")
        select_all_btn.clicked.connect(lambda: self._set_all_checked(True))
        select_none_btn.clicked.connect(lambda: self._set_all_checked(False))
        btn_row.addWidget(select_all_btn)
        btn_row.addWidget(select_none_btn)
        left_layout.addLayout(btn_row)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemChanged.connect(self._on_item_changed)
        left_layout.addWidget(self.tree, stretch=1)

        self.info_label = QtWidgets.QLabel("")
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("color: #444;")
        left_layout.addWidget(self.info_label)

        # ---------- rechtes Panel: Plot ----------
        right_panel = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_panel)

        self.plot_widget = pg.PlotWidget()
        self.plot_item = self.plot_widget.getPlotItem()
        self.plot_item.showGrid(x=True, y=True, alpha=0.3)
        # Keine automatische SI-Skalierung: Werte 0..1 sonst als "0..700 (x0.001)"
        for side in ("left", "right"):
            self.plot_item.getAxis(side).enableAutoSIPrefix(False)
        self.plot_item.addLegend(offset=(10, 10))
        self.view_box = self.plot_item.vb

        # Crosshair + Readout
        self.vline = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#888", width=1))
        self.hline = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen("#888", width=1))
        self.plot_item.addItem(self.vline, ignoreBounds=True)
        self.plot_item.addItem(self.hline, ignoreBounds=True)
        self.vline.hide()
        self.hline.hide()

        self.readout_label = QtWidgets.QLabel("")
        self.readout_label.setStyleSheet(
            "background-color: rgba(255,255,255,220); border: 1px solid #999; padding: 6px;"
        )
        self.readout_label.setTextFormat(QtCore.Qt.RichText)
        self.readout_label.setVisible(False)

        right_layout.addWidget(self.plot_widget, stretch=1)

        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel, stretch=1)

        # Readout-Label ueber dem Plot schweben lassen
        self.readout_label.setParent(self.plot_widget)
        self.readout_label.move(10, 10)

        self.status = self.statusBar()

        # Menu
        file_menu = self.menuBar().addMenu("&Datei")
        open_action = QtGui.QAction("CSV oeffnen...", self)
        open_action.triggered.connect(self.open_csv_dialog)
        file_menu.addAction(open_action)
        reload_action = QtGui.QAction("Neu laden", self)
        reload_action.triggered.connect(self.reload_csv)
        file_menu.addAction(reload_action)
        file_menu.addSeparator()
        exit_action = QtGui.QAction("Beenden", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

    def _connect_signals(self):
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.filter_edit.textChanged.connect(self._apply_filter)
        proxy = pg.SignalProxy(
            self.plot_widget.scene().sigMouseMoved, rateLimit=60, slot=self._on_mouse_moved
        )
        self._mouse_proxy = proxy  # Referenz halten, sonst wird proxy garbage-collected

    # -------------------------------------------------------------- Laden
    def open_csv_dialog(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "CSV-Datei oeffnen", "", "CSV-Dateien (*.csv);;Alle Dateien (*)"
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
        self.setWindowTitle(f"{APP_TITLE} - {os.path.basename(path)}")
        self._prepare_axes()
        self._populate_tree(selected)
        if any(entry.checked for entry in self.curves.values()):
            self._rebuild_plot()
        else:
            self._clear_plot()
        msg = f"{len(self.df)} Zeilen, {len(self.df.columns)} Spalten geladen aus {path}"
        if skipped:
            msg += f" ({skipped} unvollstaendige Zeile(n) uebersprungen)"
        self.status.showMessage(msg)

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
        self.color_cycle = itertools.cycle(COLOR_PALETTE)

        df = self.df
        assigned = set()
        if self.ts_col:
            assigned.add(self.ts_col)

        # 1) bekannte Gruppen zuerst, in fester Reihenfolge
        for group_name, cols in KNOWN_GROUPS.items():
            existing = [c for c in cols if c in df.columns and c not in assigned]
            if not existing:
                continue
            group_item = QtWidgets.QTreeWidgetItem([group_name])
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
            other_item = QtWidgets.QTreeWidgetItem(["Sonstige"])
            other_item.setFlags(other_item.flags() & ~QtCore.Qt.ItemIsUserCheckable)
            self.tree.addTopLevelItem(other_item)
            for col in remaining:
                self._add_curve_item(other_item, col, "Sonstige")
            other_item.setExpanded(False)

        self.tree.blockSignals(False)

    def _is_plottable(self, series: pd.Series) -> bool:
        return is_plottable(series)

    def _add_curve_item(self, parent_item, col_name, group_name):
        color = next(self.color_cycle)
        entry = CurveEntry(col_name, color, group_name)
        entry.checked = col_name in self._selected_on_load
        self.curves[col_name] = entry

        item = QtWidgets.QTreeWidgetItem([col_name])
        item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
        item.setCheckState(0, QtCore.Qt.Checked if entry.checked else QtCore.Qt.Unchecked)
        item.setForeground(0, QtGui.QBrush(QtGui.QColor(color)))
        pix = QtGui.QPixmap(12, 12)
        pix.fill(QtGui.QColor(color))
        item.setIcon(0, QtGui.QIcon(pix))
        item.setData(0, QtCore.Qt.UserRole, col_name)
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

    def _on_item_changed(self, item, column):
        col_name = item.data(0, QtCore.Qt.UserRole)
        if col_name is None:
            return
        self.curves[col_name].checked = item.checkState(0) == QtCore.Qt.Checked
        self._rebuild_plot()

    def _on_mode_changed(self):
        self._rebuild_plot()

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
        self.plot_item.getAxis("left").setTextPen(pg.mkPen("k"))
        self.plot_item.setLabel("left", "")
        self.plot_item.hideAxis("right")
        self.plot_item.addItem(self.vline, ignoreBounds=True)
        self.plot_item.addItem(self.hline, ignoreBounds=True)
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
        self.plot_item.setLabel("bottom", self.ts_col if self.ts_col else "Zyklus / Zeile")

    def _get_series_values(self, col_name):
        values = self._values_cache.get(col_name)
        if values is None:
            values = to_numeric_values(self.df[col_name])
            self._values_cache[col_name] = values
        return values

    def _rebuild_plot(self):
        if self.df is None:
            return
        self._clear_plot()

        mode = self.mode_combo.currentText()
        active = [c for c in self.curves.values() if c.checked]
        x = self.x_seconds.to_numpy(dtype=float)

        if not active:
            self.info_label.setText("Keine Kennlinie ausgewaehlt.")
            return

        if mode == self.MODE_MULTI_AXIS:
            self._plot_multi_axis(active, x)
        elif mode == self.MODE_NORMALIZED:
            self._plot_normalized(active, x)
        else:
            self._plot_original(active, x)

        self.info_label.setText(f"{len(active)} Kennlinie(n) aktiv | Modus: {mode}")

    def _plot_original(self, active, x):
        self.plot_item.setLabel("left", "Wert (Original)")
        legend = self.plot_item.legend
        for entry in active:
            y = self._get_series_values(entry.name)
            # FIX: clipToView NICHT als Konstruktor-Kwarg uebergeben - siehe
            # Kommentar in _plot_multi_axis fuer die vollstaendige Erklaerung
            # (bekannter pyqtgraph-Bug, GitHub-Issue #1854).
            curve = self.plot_item.plot(
                x, y, pen=pg.mkPen(entry.color, width=2),
                name=entry.name, autoDownsample=True,
            )
            curve.setClipToView(True)
            entry.curve_item = curve
        self.view_box.enableAutoRange()

    def _plot_normalized(self, active, x):
        self.plot_item.setLabel("left", "Normalisiert (0-1)")
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
            curve = self.plot_item.plot(
                x, y_norm, pen=pg.mkPen(entry.color, width=2),
                name=f"{entry.name} [{y_min:.3g}..{y_max:.3g}]",
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
            x, y0, pen=pg.mkPen(first.color, width=2), name=first.name,
            autoDownsample=True,
        )
        curve0.setClipToView(True)
        first.curve_item = curve0
        self.plot_item.getAxis("left").setTextPen(first.color)
        self.plot_item.setLabel("left", first.name, color=first.color)
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
            axis.setLabel(entry.name, color=entry.color)
            axis.setTextPen(entry.color)
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
                x, y, pen=pg.mkPen(entry.color, width=2), name=entry.name,
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
    def _on_mouse_moved(self, evt):
        pos = evt[0]
        if self.df is None or not self.plot_item.sceneBoundingRect().contains(pos):
            self.vline.hide()
            self.hline.hide()
            self.readout_label.setVisible(False)
            return

        mouse_point = self.view_box.mapSceneToView(pos)
        x_val = mouse_point.x()

        x_arr = self.x_seconds.to_numpy(dtype=float)
        if not np.isfinite(x_arr).any():
            self.readout_label.setVisible(False)
            return
        # naechstgelegener Datenpunkt (statt erster Punkt rechts vom Zeiger)
        idx = int(np.nanargmin(np.abs(x_arr - x_val)))

        self.vline.setPos(x_arr[idx])
        self.hline.setPos(mouse_point.y())
        self.vline.show()
        self.hline.show()

        if self.is_time_axis:
            x_label = pd.to_datetime(self.x_raw.iloc[idx]).strftime("%Y-%m-%d %H:%M:%S")
        else:
            x_label = f"Zeile {idx}"

        lines = [f"<b>{x_label}</b>"]
        for entry in self.curves.values():
            if entry.checked and entry.curve_item is not None:
                val = self._get_series_values(entry.name)[idx]
                lines.append(f"<span style='color:{entry.color}'>&#9632;</span> {entry.name}: {val:.4g}")

        self.readout_label.setText("<br>".join(lines))
        self.readout_label.setVisible(True)
        self.readout_label.adjustSize()
        # oben rechts im Plot, damit die Legende oben links frei bleibt
        x_pos = max(10, self.plot_widget.width() - self.readout_label.width() - 70)
        self.readout_label.move(x_pos, 10)


def main():
    app = QtWidgets.QApplication(sys.argv)
    win = CsvViewerWindow()
    win.show()

    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        win.load_csv(sys.argv[1])

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
