"""
H5 Lens - Application Bridge
Exposes H5Engine to the pywebview frontend via JS-Python API bridge.
"""

import json
import os
import tempfile
import threading

import webview

from . import __version__
from .h5engine import H5Engine

# pywebview validates filters as "Description (*.ext;*.ext)" - semicolons, not spaces.
HDF5_FILTER = "HDF5 Files (*.h5;*.hdf5;*.he5;*.hdf;*.nc)"
ALL_FILTER = "All Files (*.*)"

# pywebview >= 5.1 has FileDialog; the old constants are deprecated.
_FileDialog = getattr(webview, "FileDialog", None)
OPEN_DIALOG = _FileDialog.OPEN if _FileDialog else webview.OPEN_DIALOG
SAVE_DIALOG = _FileDialog.SAVE if _FileDialog else webview.SAVE_DIALOG


class App:
    """pywebview JS API - every public method is callable from JavaScript.

    pywebview runs each JS call on its own thread, so access to the engine
    (one open h5py file) is serialized with a lock.
    """

    def __init__(self, config: dict, config_path: str):
        self.config = config
        self.config_path = config_path
        self.engine = H5Engine(config)
        self._window: webview.Window | None = None
        self._lock = threading.RLock()

    def set_window(self, window: webview.Window):
        self._window = window

    # -- File Operations ----------------------------------------------

    def open_file_dialog(self) -> dict:
        """Open a native file picker and load the selected HDF5 file."""
        if not self._window:
            return {"ok": False, "error": "No window"}

        directory = ""
        recent = self.config.get("recent_files") or []
        if recent:
            directory = os.path.dirname(recent[0])
        result = self._window.create_file_dialog(
            OPEN_DIALOG, directory=directory, file_types=(HDF5_FILTER, ALL_FILTER)
        )
        if not result:
            return {"ok": False, "error": "cancelled"}

        filepath = result if isinstance(result, str) else result[0]
        return self.open_file(filepath)

    def open_file(self, filepath: str) -> dict:
        """Open an HDF5 file by path."""
        filepath = os.path.abspath(filepath)
        with self._lock:
            res = self.engine.open(filepath)
        if res.get("ok"):
            self._add_recent(filepath)
            self._set_title(f"{res['filename']} — {self._base_title()}")
        return res

    def _base_title(self) -> str:
        return self.config.get("window", {}).get("title", "H5 Lens")

    def _set_title(self, title: str):
        try:
            if self._window:
                self._window.set_title(title)
        except Exception:
            pass

    def close_file(self) -> dict:
        with self._lock:
            self.engine.close()
        self._set_title(self._base_title())
        return {"ok": True}

    # -- Data Access --------------------------------------------------

    def get_data(self, path: str) -> dict:
        with self._lock:
            return self.engine.get_data(path)

    def get_attrs(self, path: str) -> dict:
        with self._lock:
            return self.engine.get_attrs(path)

    def get_details(self, path: str) -> dict:
        with self._lock:
            return self.engine.get_details(path)

    def get_stats(self, path: str) -> dict:
        with self._lock:
            return self.engine.get_stats(path)

    def get_image(self, path: str) -> dict:
        with self._lock:
            return self.engine.get_image_base64(path)

    # -- Export --------------------------------------------------------

    def export_csv_dialog(self, dataset_path: str) -> dict:
        """Open save dialog and export dataset as CSV."""
        if not self._window:
            return {"ok": False, "error": "No window"}

        name = dataset_path.rsplit("/", 1)[-1]
        safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in name) or "dataset"

        result = self._window.create_file_dialog(
            SAVE_DIALOG,
            save_filename=f"{safe_name}.csv",
            file_types=("CSV Files (*.csv)", ALL_FILTER),
        )
        if not result:
            return {"ok": False, "error": "cancelled"}

        save_path = result if isinstance(result, str) else result[0]
        with self._lock:
            return self.engine.export_csv(dataset_path, save_path)

    # -- Config / Recent Files ----------------------------------------

    def get_recent_files(self) -> list:
        """Recent files, newest first, flagged with whether they still exist."""
        return [
            {"path": p, "exists": os.path.isfile(p)}
            for p in self.config.get("recent_files", [])
        ]

    def get_config(self) -> dict:
        return {**self.config, "version": __version__}

    def _add_recent(self, filepath: str):
        recent = [r for r in self.config.get("recent_files", []) if r != filepath]
        recent.insert(0, filepath)
        max_n = self.config.get("max_recent_files", 10)
        self.config["recent_files"] = recent[:max_n]
        self._save_config()

    def remove_recent(self, filepath: str):
        self.config["recent_files"] = [r for r in self.config.get("recent_files", []) if r != filepath]
        self._save_config()

    def clear_recent(self):
        self.config["recent_files"] = []
        self._save_config()

    def _save_config(self):
        """Write config atomically so a crash never leaves a truncated file."""
        try:
            directory = os.path.dirname(self.config_path) or "."
            fd, tmp = tempfile.mkstemp(prefix=".config-", suffix=".json", dir=directory)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self.config, f, indent=2, ensure_ascii=False)
                os.replace(tmp, self.config_path)
            except Exception:
                os.unlink(tmp)
                raise
        except Exception:
            pass
