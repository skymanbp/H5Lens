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
│   ├── __init__.py
│   ├── app.py         ← pywebview ↔ frontend bridge
│   ├── h5engine.py    ← HDF5 reading engine (h5py + numpy)
│   └── viewer.html    ← Frontend GUI
├── LICENSE
└── README.md
```

---

## Download

Prebuilt Windows executable: **[latest release](https://github.com/skymanbp/H5Lens/releases/latest)** — current version **v1.0.1**.

`H5Lens.exe` is a single-file PyInstaller build for Windows x64 and needs no
Python installation. Verify the download before running it:

```powershell
Get-FileHash H5Lens.exe -Algorithm SHA256
```

The SHA-256 published with v1.0.1 (`Get-FileHash` prints it uppercase; hex
comparison is case-insensitive):

```
6861a71799017ebaf3037e2d37383086c50fd66c4712050d0aae529da66b44f7
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
```

---

## Features

| Feature | Description |
|---|---|
| **Tree Explorer** | Hierarchical view of all groups and datasets with search/filter |
| **Data Table** | Tabular preview of 1D, 2D, and N-D datasets with row indices |
| **Attributes** | View HDF5 attributes on any group or dataset |
| **Dataset Details** | dtype, shape, compression, chunks, fill value, max shape |
| **Statistics** | Min, max, mean, std, median, NaN count (also counts ±Inf), unique values (only under 1M finite values) |
| **Image Preview** | Auto-renders 2D/3D numeric arrays as images (grayscale/RGB/RGBA) |
| **CSV Export** | Export any dataset to CSV via native save dialog |
| **Recent Files** | Remembers last 10 opened files |
| **Keyboard Shortcuts** | `Ctrl+O` open, `/` search, `Ctrl+E` export, `Esc` clear |
| **Resizable Sidebar** | Drag to resize the tree panel |
| **Native Window** | Proper desktop app via pywebview (no browser chrome) |

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
    "float_precision": 8,      // Decimal places for floats in the data table
    "sidebar_width": 300       // Unused
  },
  "export": {
    "csv_separator": ",",      // CSV delimiter
    "csv_line_ending": "\n",   // Unused
    "default_format": "csv"    // Unused
  },
  "recent_files": [],          // Recent-file list, rewritten by the app
  "max_recent_files": 10       // How many recent files to keep
}
```

The Image tab is offered by the frontend only when a dataset has at most
4,000,000 elements in total; that threshold is fixed and is not affected by
`max_image_pixels`, which limits the backend renderer alone. `float_precision`
applies to the data table only: statistics are shown at 8 significant digits and
CSV export always rounds to 8 decimal places.

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
