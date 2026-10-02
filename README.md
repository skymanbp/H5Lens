# H5 Lens — Elegant HDF5 Viewer

A lightweight, fast desktop application for exploring `.h5` / `.hdf5` files with a clean GUI.

```
H5Lens/
├── launch.py          ← Entry point (becomes the .exe)
├── config.json        ← User-editable configuration
├── requirements.txt   ← Python dependencies
├── build.py           ← PyInstaller build script
├── register.bat       ← Register .h5/.hdf5/.hdf/.he5/.nc associations (HKCU)
├── unregister.bat     ← Remove those associations
├── lib/               ← Core library
│   ├── __init__.py    ← Version
│   ├── app.py         ← pywebview ↔ frontend bridge
│   ├── h5engine.py    ← HDF5 reading engine (h5py + numpy)
│   ├── viewer.html    ← Frontend GUI
│   └── fonts/         ← DM Sans + JetBrains Mono (SIL OFL), so the GUI looks the same offline
├── tests/             ← Engine and bridge tests (pytest, no window opened)
├── scripts/
│   └── check_doc_drift.py ← Checks these docs against the code (run by CI)
├── .github/workflows/ ← CI (tests, doc check, build + self-test) and the release build
├── CHANGELOG.md
├── LICENSE
└── README.md
```

---

## Download

Prebuilt Windows executable: **[latest release](https://github.com/skymanbp/H5Lens/releases/latest)** — current version **v1.1.0**.

`H5Lens.exe` is a single-file PyInstaller build for Windows x64 and needs no
Python installation. Verify the download before running it:

```powershell
Get-FileHash H5Lens.exe -Algorithm SHA256
```

The SHA-256 published with v1.1.0 (also in the release's `SHA256SUMS.txt`;
`Get-FileHash` prints it uppercase, and hex comparison is case-insensitive):

```
d526e1e488cfbcfa4de2487e61dc6aba1f4e761d30dcc451750359fc5cb60769
```

Place `config.json` next to the exe to change the defaults, and run
`register.bat` to associate `.h5` / `.hdf5` / `.hdf` / `.he5` / `.nc` with it
(`unregister.bat` removes the associations).

To compile the exe yourself instead, see
[Build as Standalone .exe](#build-as-standalone-exe).

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run

```bash
python launch.py                # Opens the welcome screen (click it or Ctrl+O to browse)
python launch.py mydata.h5      # Opens a specific file directly
python launch.py --debug        # Enables the webview developer tools
python launch.py --self-test report.json   # Checks the install without opening a window
```

`H5Lens.exe --self-test report.json` does the same for the exe: it checks the
bundled packages, page and fonts and reads a temporary file, then writes the
result to `report.json` (exit code 0 when every check passes).

You can also drag a file onto the window to open it.

---

## Features

| Feature | Description |
|---|---|
| **Tree Explorer** | Hierarchical view of all groups and datasets with filter (by name, or by path when the filter contains `/`) and keyboard navigation; hard links that point back to an already shown group (including cycles) appear as link nodes; unreadable objects (e.g. dangling soft links) are shown in red with the reason |
| **Data Table** | Preview of the first rows (and columns) of 1D and 2D datasets; only the previewed part is read from disk; cells are selectable for copying |
| **N-D Planes** | A dataset with three or more axes is shown one 2-D plane at a time: a bar above the table picks the axis for rows, the axis for columns and an index on every other axis; the Image tab shows the same plane |
| **Attributes** | View HDF5 attributes on any group or dataset |
| **Dataset Details** | dtype (string, compound, enum and vlen types shown readably), shape, raw and on-disk size, compression, chunks, shuffle, fletcher32, scale-offset, fill value, max shape |
| **Statistics** | Min, max, mean, std, NaN and ±Inf counts, computed block by block so large datasets need not fit in memory; median (up to 20M values) and unique count (under 1M finite values) |
| **Image Preview** | Renders 2D and H×W×1/3/4 arrays as grayscale/RGB/RGBA, and the chosen plane of other N-D arrays as grayscale; `uint8` data is shown as is, other types are scaled linearly from min to max (NaN/Inf drawn black); click to toggle fit / actual size |
| **CSV Export** | Export any dataset to CSV at full precision via the native save dialog, streamed in blocks (see [CSV format](#csv-format)) |
| **Recent Files** | Remembers recently opened files, marks ones that no longer exist, single entries can be removed |
| **Drag and Drop** | Drop a file onto the window to open it |
| **Keyboard Shortcuts** | `Ctrl+O` open, `Ctrl+W` close, `/` or `Ctrl+F` filter, `↑ ↓ ← → Home End Enter` navigate the tree, `Ctrl+E` export, `Ctrl+I` statistics, `Esc` clear filter |
| **Resizable Sidebar** | Drag to resize the tree panel; the width is saved as `sidebar_width` in `config.json` |
| **Native Window** | Proper desktop app via pywebview (no browser chrome); the title shows the open file; fonts are bundled, so it looks the same offline |

Files are opened read-only and without HDF5 file locking (where h5py
supports it), so a file that another program is writing can still be viewed.

### CSV format

- 1D: `index, value`; 2D: `col_0, col_1, …` with one CSV row per array row;
  three or more axes: `dim_0, dim_1, …, value`, one line per element; a
  scalar: `value`.
- Numbers are written so they read back exactly: `float64` and integers as
  Python prints them, narrower floats in their own shortest form (`0.1`,
  not `0.10000000149011612`); non-finite floats as `nan`, `inf`, `-inf`.
- Strings are UTF-8 (undecodable bytes as hex). The separator and line
  ending come from `config.json`.

---

## Build as Standalone .exe

```bash
pip install pyinstaller
python build.py            # Single-file .exe (slower startup, portable)
python build.py --onedir   # Directory bundle (faster startup)
```

The output goes to `dist/H5Lens.exe` (or `dist/H5Lens/` for onedir).
Place `config.json` next to the exe for user-editable settings.

---

## Configuration

Edit `config.json` to customize:

```jsonc
{
  "window": {
    "title": "H5 Lens",       // Window title
    "width": 1280,             // Initial width
    "height": 800,             // Initial height
    "min_width": 800,          // Minimum width
    "min_height": 500,         // Minimum height
    "resizable": true,         // Allow the window to be resized
    "on_top": false            // Always-on-top
  },
  "viewer": {
    "max_preview_rows": 5000,  // Max rows shown in data table
    "max_preview_cols": 200,   // Max columns shown for 2D data
    "max_image_pixels": 4000000, // Max rows × cols the backend will render
    "float_precision": 8,      // Significant digits for floats on screen (1-17)
    "sidebar_width": 300       // Tree panel width in px; dragging the sidebar updates it
  },
  "export": {
    "csv_separator": ",",      // CSV delimiter
    "csv_line_ending": "\n",   // CSV line ending, e.g. "\r\n" for Excel on Windows
    "default_format": "csv"    // Reserved: CSV is the only export format
  },
  "recent_files": [],          // Recent-file list, rewritten by the app
  "max_recent_files": 10       // How many recent files to keep
}
```

The Image tab is offered when a dataset's height × width is at most
`max_image_pixels`. `float_precision` applies to everything shown on screen
(table, attributes, statistics); CSV export always writes full precision.

---

## Tests and checks

```bash
pip install pytest
python -m pytest tests                 # engine and bridge tests; no window is opened
python scripts/check_doc_drift.py      # README / CHANGELOG / config against the code
```

CI runs both on every push, then builds the exe and runs its `--self-test`.
Releases are built by CI from a `v*` tag; see [CHANGELOG.md](CHANGELOG.md).

---

## Requirements

- Python 3.10+
- h5py ≥ 3.8
- numpy ≥ 1.24
- pywebview ≥ 5.0
- Pillow ≥ 10.0 (for image preview; installed by `requirements.txt`, and only the Image tab fails without it)

---

## License

MIT — see [LICENSE](LICENSE).
