"""
H5 Lens - Application Bridge
Exposes H5Engine to the pywebview frontend via JS-Python API bridge.
"""

import json
import os
import webview
from pathlib import Path
from .h5engine import H5Engine


class App:
    """pywebview JS API - every public method is callable from JavaScript."""

    def __init__(self, config: dict, config_path: str):
        self.config = config
        self.config_path = config_path
        self.engine = H5Engine(config)
        self._window: webview.Window | None = None

    def set_window(self, window: webview.Window):
        self._window = window

    # -- File Operations ----------------------------------------------

    def open_file_dialog(self) -> dict:
        """Open a native file picker and load the selected HDF5 file."""
        if not self._window:
            return {"ok": False, "error": "No window"}

        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=("HDF5 Files (*.h5 *.hdf5 *.he5 *.hdf *.nc)", "All Files (*.*)"),
        )
        if not result or len(result) == 0:
            return {"ok": False, "error": "cancelled"}

        filepath = result[0]
        return self.open_file(filepath)

    def open_file(self, filepath: str) -> dict:
        """Open an HDF5 file by path."""
        res = self.engine.open(filepath)
        if res.get("ok"):
            self._add_recent(filepath)
        return res

    def close_file(self) -> dict:
        self.engine.close()
        return {"ok": True}

    # -- Data Access --------------------------------------------------

    def get_data(self, path: str) -> dict:
        return self.engine.get_data(path)

    def get_attrs(self, path: str) -> dict:
        return self.engine.get_attrs(path)

    def get_details(self, path: str) -> dict:
        return self.engine.get_details(path)

    def get_stats(self, path: str) -> dict:
        return self.engine.get_stats(path)

    def get_image(self, path: str) -> dict:
        return self.engine.get_image_base64(path)

    # -- Export --------------------------------------------------------

    def export_csv_dialog(self, dataset_path: str) -> dict:
        """Open save dialog and export dataset as CSV."""
        if not self._window:
            return {"ok": False, "error": "No window"}

        name = dataset_path.rsplit("/", 1)[-1]
        safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)

        result = self._window.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=f"{safe_name}.csv",
            file_types=("CSV Files (*.csv)", "All Files (*.*)"),
        )
        if not result:
            return {"ok": False, "error": "cancelled"}

        save_path = result if isinstance(result, str) else result[0]
        return self.engine.export_csv(dataset_path, save_path)

    # -- Config / Recent Files ----------------------------------------

    def get_recent_files(self) -> list:
        return self.config.get("recent_files", [])

    def get_config(self) -> dict:
        return self.config

    def _add_recent(self, filepath: str):
        recent = self.config.get("recent_files", [])
        filepath = os.path.abspath(filepath)
        # Remove duplicates
        recent = [r for r in recent if r != filepath]
        recent.insert(0, filepath)
        max_n = self.config.get("max_recent_files", 10)
        self.config["recent_files"] = recent[:max_n]
        self._save_config()

    def clear_recent(self):
        self.config["recent_files"] = []
        self._save_config()

    def _save_config(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
