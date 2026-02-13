# H5 Lens — Elegant HDF5 Viewer

A lightweight, fast desktop application for exploring `.h5` / `.hdf5` files with a clean GUI.

```
H5Lens/
├── launch.py          ← Entry point (becomes the .exe)
├── config.json        ← User-editable configuration
├── requirements.txt   ← Python dependencies
├── build.py           ← PyInstaller build script
├── lib/               ← Core library
│   ├── __init__.py
│   ├── app.py         ← pywebview ↔ frontend bridge
│   ├── h5engine.py    ← HDF5 reading engine (h5py + numpy)
│   └── viewer.html    ← Frontend GUI
└── README.md
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run

```bash
python launch.py                # Opens with file picker
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
| **Statistics** | Min, max, mean, std, median, NaN count, unique values |
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
    "on_top": false            // Always-on-top
  },
  "viewer": {
    "max_preview_rows": 5000,  // Max rows shown in data table
    "max_preview_cols": 200,   // Max columns shown for 2D data
    "max_image_pixels": 4000000, // Max pixels for image preview
    "float_precision": 8       // Decimal places for floats
  },
  "export": {
    "csv_separator": ","       // CSV delimiter
  }
}
```

---

## Requirements

- Python 3.10+
- h5py ≥ 3.8
- numpy ≥ 1.24
- pywebview ≥ 5.0
- Pillow ≥ 10.0 (optional, for image preview)
