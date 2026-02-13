"""
H5 Lens - HDF5 Engine
Handles all HDF5 file reading, tree building, data extraction, and export.
"""

import h5py
import numpy as np
import json
import os
import csv
import io
import base64
from pathlib import Path


class H5Engine:
    """Core HDF5 reading engine."""

    def __init__(self, config: dict):
        self.config = config
        self.file: h5py.File | None = None
        self.filepath: str = ""

    # -- File Operations ----------------------------------------------

    def open(self, filepath: str) -> dict:
        """Open an HDF5 file and return its tree structure."""
        self.close()
        try:
            self.file = h5py.File(filepath, "r")
            self.filepath = filepath
            tree = self._build_tree(self.file, "/")
            size = os.path.getsize(filepath)
            return {
                "ok": True,
                "tree": tree,
                "filename": Path(filepath).name,
                "filepath": filepath,
                "size": size,
                "size_fmt": self._fmt_bytes(size),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def close(self):
        """Close the current file."""
        if self.file:
            try:
                self.file.close()
            except Exception:
                pass
            self.file = None
            self.filepath = ""

    def is_open(self) -> bool:
        return self.file is not None

    # -- Tree Building ------------------------------------------------

    def _build_tree(self, obj, path: str) -> dict:
        """Recursively build a JSON-serializable tree from an HDF5 group."""
        name = "/" if path == "/" else path.rsplit("/", 1)[-1]
        node = {
            "name": name,
            "path": path,
            "type": "group",
            "children": [],
            "attr_count": 0,
        }

        # Attributes
        try:
            node["attr_count"] = len(obj.attrs)
        except Exception:
            pass

        # Iterate children
        try:
            keys = list(obj.keys())
        except Exception:
            keys = []

        for key in sorted(keys):
            child_path = f"{path.rstrip('/')}/{key}"
            try:
                child = obj[key]
                if isinstance(child, h5py.Group):
                    node["children"].append(self._build_tree(child, child_path))
                elif isinstance(child, h5py.Dataset):
                    ds_node = {
                        "name": key,
                        "path": child_path,
                        "type": "dataset",
                        "shape": list(child.shape),
                        "dtype": str(child.dtype),
                        "size": int(np.prod(child.shape)) if child.shape else 1,
                        "nbytes": int(child.nbytes) if hasattr(child, "nbytes") else 0,
                        "attr_count": len(child.attrs),
                        "children": [],
                    }
                    # Check compression
                    if child.compression:
                        ds_node["compression"] = child.compression
                        if child.compression_opts is not None:
                            ds_node["compression_opts"] = str(child.compression_opts)
                    if child.chunks:
                        ds_node["chunks"] = list(child.chunks)
                    node["children"].append(ds_node)
                else:
                    node["children"].append({
                        "name": key,
                        "path": child_path,
                        "type": "unknown",
                        "children": [],
                    })
            except Exception as e:
                node["children"].append({
                    "name": key,
                    "path": child_path,
                    "type": "error",
                    "error": str(e),
                    "children": [],
                })

        # Sort: groups first, then by name
        node["children"].sort(key=lambda c: (0 if c["type"] == "group" else 1, c["name"]))
        return node

    # -- Data Reading -------------------------------------------------

    def get_data(self, path: str) -> dict:
        """Read dataset data for display. Returns a table-friendly structure."""
        if not self.file:
            return {"ok": False, "error": "No file open"}

        try:
            obj = self.file[path]
            if not isinstance(obj, h5py.Dataset):
                return {"ok": False, "error": "Not a dataset"}

            cfg = self.config.get("viewer", {})
            max_rows = cfg.get("max_preview_rows", 5000)
            max_cols = cfg.get("max_preview_cols", 200)
            precision = cfg.get("float_precision", 8)

            shape = obj.shape
            dtype = obj.dtype
            total = int(np.prod(shape)) if shape else 1

            # Scalar
            if not shape or (len(shape) == 0):
                val = obj[()]
                return {
                    "ok": True,
                    "mode": "scalar",
                    "value": self._to_json_val(val, precision),
                    "dtype": str(dtype),
                }

            # 1D
            if len(shape) == 1:
                n = min(shape[0], max_rows)
                data = obj[:n]
                rows = []
                for i in range(n):
                    rows.append([i, self._to_json_val(data[i], precision)])
                return {
                    "ok": True,
                    "mode": "1d",
                    "headers": ["Index", "Value"],
                    "rows": rows,
                    "total_rows": shape[0],
                    "shown_rows": n,
                    "truncated": shape[0] > max_rows,
                }

            # 2D
            if len(shape) == 2:
                nr = min(shape[0], max_rows)
                nc = min(shape[1], max_cols)
                data = obj[:nr, :nc]
                headers = ["Row"] + [str(c) for c in range(nc)]
                if nc < shape[1]:
                    headers.append("...")
                rows = []
                for r in range(nr):
                    row = [r]
                    for c in range(nc):
                        row.append(self._to_json_val(data[r, c], precision))
                    if nc < shape[1]:
                        row.append("...")
                    rows.append(row)
                return {
                    "ok": True,
                    "mode": "2d",
                    "headers": headers,
                    "rows": rows,
                    "total_rows": shape[0],
                    "total_cols": shape[1],
                    "shown_rows": nr,
                    "shown_cols": nc,
                    "truncated": shape[0] > max_rows or shape[1] > max_cols,
                }

            # 3D+ - flatten to index,value
            flat = obj[()].flatten()
            n = min(len(flat), max_rows)
            rows = []
            for i in range(n):
                rows.append([i, self._to_json_val(flat[i], precision)])
            return {
                "ok": True,
                "mode": "nd",
                "headers": ["Index", "Value"],
                "rows": rows,
                "total_elements": total,
                "shown": n,
                "truncated": total > max_rows,
            }

        except Exception as e:
            return {"ok": False, "error": str(e)}

    # -- Attributes ---------------------------------------------------

    def get_attrs(self, path: str) -> dict:
        """Get attributes for a group or dataset."""
        if not self.file:
            return {"ok": False, "error": "No file open"}
        try:
            obj = self.file[path]
            attrs = {}
            for key in obj.attrs:
                try:
                    val = obj.attrs[key]
                    attrs[key] = self._to_json_val(val)
                except Exception:
                    attrs[key] = "(unreadable)"
            return {"ok": True, "attrs": attrs}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # -- Dataset Details ----------------------------------------------

    def get_details(self, path: str) -> dict:
        """Get detailed metadata for a dataset."""
        if not self.file:
            return {"ok": False, "error": "No file open"}
        try:
            obj = self.file[path]
            if not isinstance(obj, h5py.Dataset):
                return {"ok": False, "error": "Not a dataset"}

            total = int(np.prod(obj.shape)) if obj.shape else 1
            info = {
                "path": path,
                "type": "Dataset",
                "dtype": str(obj.dtype),
                "shape": f"({', '.join(str(s) for s in obj.shape)})" if obj.shape else "Scalar",
                "ndim": len(obj.shape),
                "total_elements": total,
                "raw_size": self._fmt_bytes(int(obj.nbytes)) if hasattr(obj, "nbytes") else "-",
                "compression": obj.compression or "None",
                "compression_opts": str(obj.compression_opts) if obj.compression_opts else "-",
                "chunks": str(obj.chunks) if obj.chunks else "Contiguous",
                "shuffle": str(obj.shuffle) if hasattr(obj, "shuffle") else "-",
                "fletcher32": str(obj.fletcher32) if hasattr(obj, "fletcher32") else "-",
                "fillvalue": str(obj.fillvalue) if obj.fillvalue is not None else "-",
                "maxshape": str(obj.maxshape) if obj.maxshape else "-",
            }
            return {"ok": True, "details": info}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # -- Statistics ---------------------------------------------------

    def get_stats(self, path: str) -> dict:
        """Compute basic statistics for a numeric dataset."""
        if not self.file:
            return {"ok": False, "error": "No file open"}
        try:
            obj = self.file[path]
            if not isinstance(obj, h5py.Dataset):
                return {"ok": False, "error": "Not a dataset"}

            if not np.issubdtype(obj.dtype, np.number):
                return {"ok": False, "error": "Non-numeric dataset"}

            data = obj[()]
            finite = data[np.isfinite(data)] if np.issubdtype(obj.dtype, np.floating) else data.flatten()

            if len(finite) == 0:
                return {"ok": False, "error": "No finite values"}

            stats = {
                "min": float(np.min(finite)),
                "max": float(np.max(finite)),
                "mean": float(np.mean(finite)),
                "std": float(np.std(finite)),
                "median": float(np.median(finite)),
                "total": int(np.prod(data.shape)),
                "nan_count": int(np.count_nonzero(~np.isfinite(data))) if np.issubdtype(obj.dtype, np.floating) else 0,
                "unique": int(len(np.unique(finite))) if len(finite) < 1_000_000 else -1,
            }
            return {"ok": True, "stats": stats}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # -- Image Rendering ----------------------------------------------

    def get_image_base64(self, path: str) -> dict:
        """Render a 2D/3D dataset as a PNG image, return as base64 data URI."""
        if not self.file:
            return {"ok": False, "error": "No file open"}
        try:
            obj = self.file[path]
            if not isinstance(obj, h5py.Dataset):
                return {"ok": False, "error": "Not a dataset"}

            shape = obj.shape
            max_px = self.config.get("viewer", {}).get("max_image_pixels", 4_000_000)
            total = int(np.prod(shape[:2])) if len(shape) >= 2 else 0

            if total == 0 or total > max_px:
                return {"ok": False, "error": f"Image too large ({total} pixels, max {max_px})"}

            data = obj[()].astype(np.float64)

            # Normalize to 0-255
            dmin, dmax = np.nanmin(data), np.nanmax(data)
            rng = dmax - dmin if dmax != dmin else 1.0
            normed = ((data - dmin) / rng * 255).clip(0, 255).astype(np.uint8)

            from PIL import Image

            if len(shape) == 2:
                img = Image.fromarray(normed, mode="L")
            elif len(shape) == 3 and shape[2] == 3:
                img = Image.fromarray(normed, mode="RGB")
            elif len(shape) == 3 and shape[2] == 4:
                img = Image.fromarray(normed, mode="RGBA")
            elif len(shape) == 3 and shape[2] == 1:
                img = Image.fromarray(normed[:, :, 0], mode="L")
            else:
                return {"ok": False, "error": f"Unsupported shape for image: {shape}"}

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            return {
                "ok": True,
                "data_uri": f"data:image/png;base64,{b64}",
                "width": img.width,
                "height": img.height,
            }
        except ImportError:
            return {"ok": False, "error": "Pillow not installed - run: pip install Pillow"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # -- Export --------------------------------------------------------

    def export_csv(self, path: str, save_path: str) -> dict:
        """Export a dataset to CSV."""
        if not self.file:
            return {"ok": False, "error": "No file open"}
        try:
            obj = self.file[path]
            if not isinstance(obj, h5py.Dataset):
                return {"ok": False, "error": "Not a dataset"}

            sep = self.config.get("export", {}).get("csv_separator", ",")
            data = obj[()]

            with open(save_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f, delimiter=sep)
                shape = obj.shape

                if not shape:
                    writer.writerow(["value"])
                    writer.writerow([self._to_json_val(data)])
                elif len(shape) == 1:
                    writer.writerow(["index", "value"])
                    for i, v in enumerate(data):
                        writer.writerow([i, self._to_json_val(v)])
                elif len(shape) == 2:
                    writer.writerow([f"col_{c}" for c in range(shape[1])])
                    for r in range(shape[0]):
                        writer.writerow([self._to_json_val(data[r, c]) for c in range(shape[1])])
                else:
                    flat = data.flatten()
                    writer.writerow(["index", "value"])
                    for i, v in enumerate(flat):
                        writer.writerow([i, self._to_json_val(v)])

            return {"ok": True, "path": save_path}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # -- Helpers -------------------------------------------------------

    def _to_json_val(self, val, precision: int = 8):
        """Convert a numpy/HDF5 value to a JSON-friendly Python type."""
        if isinstance(val, (bytes, np.bytes_)):
            try:
                return val.decode("utf-8")
            except Exception:
                return val.hex()
        if isinstance(val, np.ndarray):
            if val.ndim == 0:
                return self._to_json_val(val.item(), precision)
            return [self._to_json_val(v, precision) for v in val.flat[:100]]
        if isinstance(val, (np.integer, int)):
            return int(val)
        if isinstance(val, (np.floating, float)):
            v = float(val)
            if np.isnan(v):
                return "NaN"
            if np.isinf(v):
                return "Inf" if v > 0 else "-Inf"
            return round(v, precision)
        if isinstance(val, (np.bool_, bool)):
            return bool(val)
        if isinstance(val, np.void):
            return str(val)
        return str(val)

    @staticmethod
    def _fmt_bytes(b: int) -> str:
        if b == 0:
            return "0 B"
        units = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        fb = float(b)
        while fb >= 1024 and i < len(units) - 1:
            fb /= 1024
            i += 1
        return f"{fb:.1f} {units[i]}" if i > 0 else f"{b} B"
