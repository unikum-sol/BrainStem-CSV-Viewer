# BrainStem CSV Viewer

Standalone desktop application for viewing the log files written by the admin GUI of **[BrainStem](https://github.com/unikum-sol/brainstem)** (`gui_log_*.csv`). The viewer plots any number of curves over time in one window (neuromodulators, sleep state, maturity, learning progress), with selectable scaling and a value readout under the mouse cursor.

The viewer is fully decoupled from the BrainStem system: it neither imports the `ki_system` package nor touches the database, it only reads exported CSV files. It can therefore run on a different machine than BrainStem itself.

---

## About BrainStem

[BrainStem](https://github.com/unikum-sol/brainstem) is a biologically inspired, neuro-symbolic architecture for lifelong learning. It starts as a tabula rasa, learns from raw text without prior knowledge, and regulates itself through twelve digital neuromodulators, sleep and consolidation. This viewer makes those internal dynamics visible: how adenosine rises to the sleep threshold, how histamine falls during sleep, or how wake episodes lengthen as the system matures.

---

## Where the CSV files come from

The BrainStem admin GUI (`python main.py --gui`) has a logger row:

- **Logger aktiv** (logger on): starts a new file `gui_log_YYYY-MM-DD_HHMMSS.csv` in the working directory the GUI was started from.
- **Nur bei Änderung loggen** (log on change only, default): a row is written only when a value has changed, plus a heartbeat row at least every 10 minutes.

Each row holds a timestamp (`timestamp_iso`) and every value the GUI currently displays.

---

## Features

- **Same look as the BrainStem admin GUI:** a calm dark color scheme by default and a light one for bright rooms, switched with **Farbschema: Dunkel / Hell** (color scheme: dark / light) in the header or the **Ansicht** (view) menu. The choice is remembered. Colors, cards and typography match the admin GUI (`ki_system/gui_theme.py`), and the twelve neuromodulators keep the same colors as in its bar display. On Windows 10 and 11 the title bar follows the color scheme.
- **Automatic time axis:** the column `timestamp_iso` (or `timestamp`, `time`, `datetime`, `date`, or any column with "time" or "date" in its name) becomes the X axis. Without a time column, the row number is used. The axis shows the clock time exactly as written in the log.
- **Automatic column grouping:** numeric columns are detected and sorted into topic groups (see below). True/false values (`True`/`False`, also German `wahr`/`falsch`) are plotted as 1 and 0. Pure text columns are not plotted.
- **Per-curve toggles:** every curve has a checkbox; the color swatch in front of its name serves as the legend. Each group shows how many of its curves are active (for example `2 / 12`). "Alle an" / "Alle aus" (all on / all off) act on the curves the filter field currently shows.
- **Three display modes** (selector on the left):
  - **Eigene Achse je Kurve (one axis per curve):** every active curve gets its own, independently scaled Y axis on the right. Ideal when values such as `dopamine` (0 to 1) and `chunks_total` (over 160,000) should be readable at the same time.
  - **Überlagert, normalisiert (normalized overlay, 0 to 1):** all active curves are scaled to 0 to 1 and overlaid; the legend shows the original range of each curve. Good for comparing shapes, for example adenosine against histamine.
  - **Original (shared axis):** all curves in their original values on one axis; useful for similar value ranges.
- **Legend and value readout beside the plot:** a column to the right of the plot lists every active curve with its color and, while the mouse is over the plot, the time and the original value of each curve at the crosshair, independent of the display mode. Nothing is drawn on top of the curves. Large whole numbers are grouped (`162 400`).
- **File overview:** the "Datei" (file) card shows the file name, rows, columns, plottable curves and the time span of the log.
- **Ansicht anpassen** (fit view, Ctrl+0) resets all axes to the full data range after zooming. Constant curves such as `chunks_total` get a small value range instead of an axis that repeats one number.
- **Drag and drop:** a CSV file dragged onto the window is opened.
- **Built for long logs:** curves are downsampled automatically and only the visible range is drawn, so logs with many thousands of rows stay responsive.
- **"Datei" (file) menu:** open CSV (Ctrl+O), reload (F5) and quit (Ctrl+Q). Reload keeps the selected curves and the display mode, so it can be used to follow a log that the BrainStem logger is still writing. An incomplete last line is skipped.
- **Robust against messy data:** empty cells and placeholders such as `n/a` appear as gaps in the curve without making the whole column unusable. Rows out of time order (for example concatenated logs) are sorted by time.

The user interface labels are in German, matching the BrainStem admin GUI.

---

## Column groups

| Group | Columns (selection) |
|---|---|
| **Botenstoffe** (neuromodulators) | `dopamine`, `serotonin`, `glutamate`, `gaba`, `noradrenaline`, `acetylcholine`, `adenosine`, `endocannabinoid`, `cortisol`, `histamine`, `orexin`, `bdnf` |
| **Regime / Zustand** (regime / state) | `sleep_active`, `sleep_dwell_cycles`, `sleep_upper_threshold`, `sleep_lower_threshold`, `sleep_pressure_position`, `developmental_maturity`, `auto_running` |
| **Fortschritt / Zähler** (progress / counters) | `chunks_covered`, `chunks_total`, `chunks_pct`, `hypotheses_total`, `facts`, `relations`, `ontology`, `questions`, `phase7d_survivors`, `phase7d_participated`, `phase7d_weakened`, `phase7d_threshold` |
| **Sonstige** (other) | all remaining plottable columns, collapsed |

Meaning of the sleep columns (BrainStem has a single sleep/wake switch):

| Column | Meaning |
|---|---|
| `sleep_active` | 1 while asleep, 0 while awake |
| `sleep_dwell_cycles` | learning cycles since the last transition |
| `sleep_upper_threshold` / `sleep_lower_threshold` | adenosine level at which the system falls asleep or wakes up (both shifted by the wake and sleep drives) |
| `sleep_pressure_position` | position of adenosine between the two thresholds (0 = lower, 1 = upper) |
| `developmental_maturity` | maturity derived from consolidated knowledge; an immature system sleeps more |

Text columns such as `sleep_state`, `sleep_transition_reason`, the regime names or `mood_name` are not plotted. Older logs with the former columns `sleep_cooperative_score`, `sleep_authority`, `sleep_cooperative_mode` and `sleep_phase7a_mode` can still be opened.

New columns from future BrainStem versions appear under "Sonstige" automatically. To assign them to a group, add them to `KNOWN_GROUPS` at the top of `csv_viewer.py`.

---

## Installation and start (with Python)

Requirement: Python 3.9 or newer.

```bash
pip install -r requirements.txt
python csv_viewer.py
```

Start directly with a file:

```bash
python csv_viewer.py gui_log_2026-11-12_131600.csv
```

**Note on versions:** PySide6 6.9.1 contains a bug that crashes plotting with pyqtgraph. `requirements.txt` therefore excludes that version (`PySide6>=6.9.2,!=6.9.1`). Details are in the comments of `requirements.txt`.

---

## Building the Windows EXE

Requirement: Python installed and on the PATH.

1. Run `build_exe.bat` in this project folder (double-click or from a command prompt).
2. The script creates a virtual environment `venv` if needed, installs the dependencies and builds a single file with PyInstaller. It calls the Python of the venv directly, so it keeps working after the project folder has been moved.
3. Result: `dist\BrainStemCSVViewer.exe`, a portable file that needs no separate Python on the target machine.

## Linux build

PyInstaller does not cross-compile; an EXE built on Windows does not run on Linux. On a Linux machine:

```bash
chmod +x build_linux.sh
./build_linux.sh
```

Result: `dist/BrainStemCSVViewer`. Alternatively, on Linux it is enough to run `python3 csv_viewer.py` after `pip install -r requirements.txt` in a virtual environment.

---

## Files

| File | Purpose |
|---|---|
| `csv_viewer.py` | main application (PySide6 and pyqtgraph) |
| `requirements.txt` | Python dependencies with version notes |
| `build_exe.bat` | Windows build (virtual environment and PyInstaller) |
| `build_linux.sh` | Linux build (virtual environment and PyInstaller) |
| `.gitignore` | keeps the virtual environment and build output out of the repository |
| `README.md` | this description |

The virtual environment (`venv/`) and the build output (`build/`, `dist/`, `*.spec`) are created locally by the build scripts and are not part of the repository.

---

## Limitations and possible next steps

- Very large CSV files (several million rows) have not been tested.
- In the one-axis-per-curve mode, every active curve adds an axis; with more than six to eight curves the normalized mode is easier to read.
- Views (active curves and mode) cannot be saved yet; a JSON profile would be an obvious extension.
- Text columns such as `sleep_state` could be shown as colored background bands in the future (for example sleep phases shaded in gray).

---

## Related project

- **BrainStem:** [https://github.com/unikum-sol/brainstem](https://github.com/unikum-sol/brainstem)
