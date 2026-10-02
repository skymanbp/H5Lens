#!/usr/bin/env python3
"""
H5 Lens - Elegant HDF5 Viewer
"""

import sys
import json
import os
import traceback
from pathlib import Path


def get_resource_dir():
    """Where bundled resources (viewer.html) live.
    - Frozen onefile: sys._MEIPASS (temp extract dir)
    - Frozen onedir:  same as exe dir
    - Script mode:    same as script dir
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).parent


def get_app_dir():
    """Directory next to the exe/script - for writable files (config.json)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def load_config():
    app_dir = get_app_dir()
    config_path = app_dir / "config.json"

    default_config = {
        "window": {
            "title": "H5 Lens",
            "width": 1280,
            "height": 800,
            "min_width": 800,
            "min_height": 500,
            "resizable": True,
            "on_top": False,
        },
        "viewer": {
            "max_preview_rows": 5000,
            "max_preview_cols": 200,
            "max_image_pixels": 4000000,
            "float_precision": 8,
            "sidebar_width": 300,
        },
        "export": {
            "csv_separator": ",",
            "csv_line_ending": "\n",
            "default_format": "csv",
        },
        "recent_files": [],
        "max_recent_files": 10,
    }

    # Try to read bundled config first (inside _MEIPASS), then app dir
    for cp in [config_path, get_resource_dir() / "config.json"]:
        if cp.exists():
            try:
                with open(cp, "r", encoding="utf-8") as f:
                    config = json.load(f)
                if not isinstance(config, dict):
                    continue
                for key, val in default_config.items():
                    cur = config.get(key)
                    if cur is None or type(cur) is not type(val):
                        # Missing or wrong type (e.g. "viewer": null) -> default
                        config[key] = val
                    elif isinstance(val, dict):
                        for k, v in val.items():
                            cur.setdefault(k, v)
                config["recent_files"] = [p for p in config["recent_files"] if isinstance(p, str)]
                return config, str(config_path)  # always write to app_dir
            except Exception:
                continue

    # Write defaults to app dir
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    return default_config, str(config_path)


def show_error(title, msg):
    """Show error via GUI dialog."""
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, msg)
        root.destroy()
    except Exception:
        print(f"[{title}] {msg}")


def write_crash_log(error_msg):
    """Write crash info next to exe so users can report issues."""
    try:
        log_path = get_app_dir() / "h5lens_crash.log"
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("H5 Lens Crash Log\n")
            f.write("=" * 50 + "\n")
            f.write(f"Python:       {sys.version}\n")
            f.write(f"Frozen:       {getattr(sys, 'frozen', False)}\n")
            f.write(f"Executable:   {sys.executable}\n")
            f.write(f"Resource dir: {get_resource_dir()}\n")
            f.write(f"App dir:      {get_app_dir()}\n")
            if getattr(sys, "frozen", False):
                f.write(f"_MEIPASS:     {getattr(sys, '_MEIPASS', 'N/A')}\n")
                # List what's actually in _MEIPASS/lib
                mei = Path(getattr(sys, "_MEIPASS", ""))
                lib_dir = mei / "lib"
                if lib_dir.exists():
                    f.write(f"lib/ contents: {list(lib_dir.iterdir())}\n")
                else:
                    f.write("lib/ directory NOT found in _MEIPASS\n")
            f.write("=" * 50 + "\n\n")
            f.write(error_msg)
    except Exception:
        pass


def check_dependencies():
    missing = []
    try:
        import webview  # noqa: F401
    except ImportError:
        missing.append("pywebview")
    try:
        import h5py  # noqa: F401
    except ImportError:
        missing.append("h5py")
    try:
        import numpy  # noqa: F401
    except ImportError:
        missing.append("numpy")

    if missing:
        msg = (
            "Missing required packages:\n\n"
            + "\n".join(f"  - {p}" for p in missing)
            + "\n\nInstall with:\n"
            + f"  pip install {' '.join(missing)}"
        )
        show_error("H5 Lens - Missing Dependencies", msg)
        sys.exit(1)


def main():
    check_dependencies()

    import webview
    from lib.app import App

    resource_dir = get_resource_dir()
    config, config_path = load_config()
    win_cfg = config.get("window", {})

    # Find viewer.html - check multiple locations
    viewer_path = None
    candidates = [
        resource_dir / "lib" / "viewer.html",   # bundled (--add-data to "lib")
        resource_dir / "viewer.html",            # bundled (flat)
        get_app_dir() / "lib" / "viewer.html",   # next to exe
        Path(__file__).parent / "lib" / "viewer.html",  # script mode
    ]
    for c in candidates:
        if c.exists():
            viewer_path = c
            break

    if not viewer_path:
        msg = "Could not find viewer.html\n\nSearched:\n" + "\n".join(f"  {c}" for c in candidates)
        write_crash_log(msg)
        show_error("H5 Lens", msg)
        sys.exit(1)

    app = App(config, config_path)

    window = webview.create_window(
        title=win_cfg.get("title", "H5 Lens"),
        url=str(viewer_path),
        js_api=app,
        width=win_cfg.get("width", 1280),
        height=win_cfg.get("height", 800),
        min_size=(win_cfg.get("min_width", 800), win_cfg.get("min_height", 500)),
        resizable=win_cfg.get("resizable", True),
        on_top=win_cfg.get("on_top", False),
        text_select=True,
    )

    app.set_window(window)

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    debug = "--debug" in sys.argv[1:] or bool(os.environ.get("H5LENS_DEBUG"))
    file_arg = os.path.abspath(args[0]) if args else None

    def on_loaded():
        enable_file_drop(window)
        if file_arg:
            # openFile() waits for the JS bridge itself, so this is safe even
            # if the page loads before window.pywebview is injected.
            window.evaluate_js(f"openFile({json.dumps(file_arg)})")

    window.events.loaded += on_loaded
    webview.start(debug=debug)


def enable_file_drop(window):
    """Open files dropped onto the window.

    Browsers hide a dropped file's real path from page scripts; pywebview
    (>= 5) reveals it as `pywebviewFullPath` to a Python-side drop handler.
    """
    try:
        from webview.dom import DOMEventHandler
    except ImportError:
        return

    def on_drop(event):
        files = (event.get("dataTransfer") or {}).get("files") or []
        for f in files:
            path = f.get("pywebviewFullPath")
            if path:
                window.evaluate_js(f"openFile({json.dumps(path)})")
                return

    try:
        window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)
    except Exception:
        pass


def self_test(report_path):
    """Check a build without opening a window; write a JSON report.

    A windowed exe has no console, so the result goes to a file. Covers
    what a frozen bundle can miss: the packages, viewer.html and the
    bundled fonts, and one pass through the engine on a temporary file.
    Returns the process exit code (0 = every check passed).
    """
    import tempfile
    checks = {}

    def run(name, fn):
        try:
            res = fn()
            checks[name] = {"ok": res is not False, "detail": "" if res in (None, True, False) else str(res)}
        except Exception as e:
            checks[name] = {"ok": False, "detail": f"{type(e).__name__}: {e}"}

    from lib import __version__
    run("import webview", lambda: __import__("webview").__name__)
    run("import webview.dom", lambda: __import__("webview.dom").__name__)
    if sys.platform == "win32":
        run("import winforms backend", lambda: __import__("webview.platforms.winforms").__name__)
    lib_dir = get_resource_dir() / "lib"
    run("viewer.html", lambda: (lib_dir / "viewer.html").is_file())
    run("fonts", lambda: len(list((lib_dir / "fonts").glob("*.woff2"))) == 6
        and (lib_dir / "fonts" / "fonts.css").is_file())

    def engine_pass():
        import h5py
        import numpy as np
        from lib.h5engine import H5Engine
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.h5")
            with h5py.File(p, "w") as f:
                f["cube"] = np.arange(24.0).reshape(2, 3, 4)
            eng = H5Engine({})
            assert eng.open(p)["ok"]
            assert eng.get_data("/cube", ["row", 1, "col"])["rows"][1][1:3] == [16.0, 17.0]
            assert eng.get_image_base64("/cube", [0, "row", "col"])["ok"]
            assert eng.export_csv("/cube", os.path.join(d, "t.csv"))["ok"]
            eng.close()
    run("engine", engine_pass)

    ok = all(c["ok"] for c in checks.values())
    report = {"version": __version__, "frozen": bool(getattr(sys, "frozen", False)),
              "python": sys.version.split()[0], "ok": ok, "checks": checks}
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        sys.exit(self_test(sys.argv[2]))
    try:
        main()
    except Exception as e:
        tb = traceback.format_exc()
        write_crash_log(tb)
        show_error(
            "H5 Lens - Startup Error",
            f"Failed to start:\n\n{e}\n\nSee h5lens_crash.log for details."
        )
        sys.exit(1)
