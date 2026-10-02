"""
H5 Lens - HDF5 Engine
Handles all HDF5 file reading, tree building, data extraction, and export.

Values handed to the frontend are JSON-safe: floats are sent at full
precision (the frontend formats them), non-finite floats become the strings
"NaN" / "Inf" / "-Inf", and integers beyond JavaScript's exact range are sent
as strings.
"""

import base64
import csv
import io
import math
import os
from pathlib import Path

import h5py
import numpy as np

# Largest integer a JavaScript number represents exactly.
_JS_MAX_INT = 2 ** 53
# Elements read per block when streaming statistics / CSV export.
_BLOCK_ELEMENTS = 1 << 22
# Median and unique count need all finite values in memory at once.
_MEDIAN_MAX_ELEMENTS = 20_000_000
_UNIQUE_MAX_ELEMENTS = 1_000_000


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
            if not os.path.isfile(filepath):
                return {"ok": False, "error": f"File not found: {filepath}"}
            if not h5py.is_hdf5(filepath):
                return {"ok": False, "error": "Not an HDF5 file (NetCDF-3 .nc files are not HDF5)"}
            self.file = self._open_readonly(filepath)
            self.filepath = filepath
            tree = self._build_tree(self.file, "/", {})
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
            self.close()
            return {"ok": False, "error": str(e)}

    @staticmethod
    def _open_readonly(filepath: str) -> h5py.File:
        # Without file locking a file that another process is writing can still
        # be viewed; older h5py/HDF5 builds lack the option.
        try:
            return h5py.File(filepath, "r", locking=False)
        except (TypeError, ValueError):
            return h5py.File(filepath, "r")

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

    @staticmethod
    def _object_key(obj):
        try:
            info = h5py.h5o.get_info(obj.id)
            return (info.fileno, info.addr)
        except Exception:
            return hash(obj.id)

    def _build_tree(self, obj, path: str, seen: dict) -> dict:
        """Build a JSON-serializable tree from an HDF5 group.

        `seen` maps already-visited groups to their first path, so hard links
        that point back up the hierarchy (cycles) or to a group shown elsewhere
        become "link" nodes instead of being expanded again.
        """
        name = "/" if path == "/" else path.rsplit("/", 1)[-1]
        node = {"name": name, "path": path, "type": "group", "children": [], "attr_count": 0}
        seen[self._object_key(obj)] = path

        try:
            node["attr_count"] = len(obj.attrs)
        except Exception:
            pass

        try:
            keys = list(obj.keys())
        except Exception as e:
            node["error"] = str(e)
            keys = []

        for key in keys:
            child_path = f"{path.rstrip('/')}/{key}"
            try:
                child = obj[key]
                if isinstance(child, h5py.Group):
                    target = seen.get(self._object_key(child))
                    if target is not None:
                        node["children"].append({
                            "name": key, "path": child_path, "type": "link",
                            "target": target, "children": [],
                        })
                    else:
                        node["children"].append(self._build_tree(child, child_path, seen))
                elif isinstance(child, h5py.Dataset):
                    node["children"].append(self._dataset_node(key, child_path, child))
                else:
                    node["children"].append({
                        "name": key, "path": child_path, "type": "unknown",
                        "kind": type(child).__name__, "children": [],
                    })
            except Exception as e:
                node["children"].append({
                    "name": key, "path": child_path, "type": "error",
                    "error": str(e) or type(e).__name__, "children": [],
                })

        # Groups first, then by name
        node["children"].sort(key=lambda c: (0 if c["type"] == "group" else 1, c["name"]))
        return node

    def _dataset_node(self, key: str, path: str, ds: h5py.Dataset) -> dict:
        shape = ds.shape
        node = {
            "name": key,
            "path": path,
            "type": "dataset",
            "shape": list(shape) if shape is not None else [],
            "null": shape is None,
            "dtype": self._fmt_dtype(ds.dtype),
            "size": self._numel(shape),
            "nbytes": int(ds.nbytes or 0),
            "attr_count": len(ds.attrs),
            "children": [],
        }
        if ds.compression:
            node["compression"] = ds.compression
            if ds.compression_opts is not None:
                node["compression_opts"] = str(ds.compression_opts)
        if ds.chunks:
            node["chunks"] = list(ds.chunks)
        return node

    # -- Data Reading -------------------------------------------------

    def _dataset(self, path: str):
        """Return (dataset, None) or (None, error-response)."""
        if not self.file:
            return None, {"ok": False, "error": "No file open"}
        obj = self.file[path]
        if not isinstance(obj, h5py.Dataset):
            return None, {"ok": False, "error": "Not a dataset"}
        return obj, None

    def get_data(self, path: str) -> dict:
        """Read the start of a dataset for display as a table."""
        try:
            obj, err = self._dataset(path)
            if err:
                return err

            cfg = self.config.get("viewer", {})
            max_rows = max(1, int(cfg.get("max_preview_rows", 5000)))
            max_cols = max(1, int(cfg.get("max_preview_cols", 200)))
            shape = obj.shape

            if shape is None:
                return {"ok": True, "mode": "scalar", "value": "(empty: null dataspace)"}

            if len(shape) == 0:
                return {"ok": True, "mode": "scalar", "value": self._to_json_val(obj[()])}

            if len(shape) == 1:
                n = min(shape[0], max_rows)
                values = self._array_to_json(obj[:n]) if n else []
                return {
                    "ok": True,
                    "mode": "1d",
                    "headers": ["Index", "Value"],
                    "rows": [[i, v] for i, v in enumerate(values)],
                    "total_rows": shape[0],
                    "shown_rows": n,
                    "truncated": shape[0] > n,
                }

            if len(shape) == 2:
                nr = min(shape[0], max_rows)
                nc = min(shape[1], max_cols)
                more_cols = shape[1] > nc
                values = self._array_to_json(obj[:nr, :nc]) if nr and nc else [[] for _ in range(nr)]
                headers = ["Row"] + [str(c) for c in range(nc)] + (["..."] if more_cols else [])
                tail = ["..."] if more_cols else []
                return {
                    "ok": True,
                    "mode": "2d",
                    "headers": headers,
                    "rows": [[r] + row + tail for r, row in enumerate(values)],
                    "total_rows": shape[0],
                    "total_cols": shape[1],
                    "shown_rows": nr,
                    "shown_cols": nc,
                    "truncated": shape[0] > nr or more_cols,
                }

            # 3D+: the first elements in C order, read as one small hyperslab
            total = self._numel(shape)
            n = min(total, max_rows)
            flat = self._read_flat_prefix(obj, n)
            values = self._array_to_json(flat)
            positions = np.unravel_index(np.arange(n), shape) if n else [[] for _ in shape]
            rows = [
                [i, "[" + ", ".join(str(int(p[i])) for p in positions) + "]", values[i]]
                for i in range(n)
            ]
            return {
                "ok": True,
                "mode": "nd",
                "headers": ["Index", "Position", "Value"],
                "rows": rows,
                "total_elements": total,
                "shown": n,
                "truncated": total > n,
            }

        except Exception as e:
            return {"ok": False, "error": str(e)}

    @staticmethod
    def _read_flat_prefix(obj, n: int) -> np.ndarray:
        """Read the first n elements (C order) of an N-D dataset.

        Indexes 0 along leading axes while n fits inside a single slice, then
        takes just enough of the next axis, so at most ~2n elements are read
        instead of the whole dataset.
        """
        if n == 0:
            return np.empty((0,), dtype=obj.dtype)
        shape = obj.shape
        sel = []
        for axis in range(len(shape)):
            inner = math.prod(shape[axis + 1:])
            if n > inner or axis == len(shape) - 1:
                sel.append(slice(0, min(shape[axis], -(-n // inner))))
                break
            sel.append(0)
        return np.asarray(obj[tuple(sel)]).reshape(-1)[:n]

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
                    attrs[key] = self._to_json_val(obj.attrs[key])
                except Exception:
                    attrs[key] = "(unreadable)"
            return {"ok": True, "attrs": attrs}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # -- Dataset Details ----------------------------------------------

    def get_details(self, path: str) -> dict:
        """Get detailed metadata for a dataset."""
        try:
            obj, err = self._dataset(path)
            if err:
                return err

            shape = obj.shape
            if shape is None:
                shape_str = "Null (no data)"
            elif shape:
                shape_str = f"({', '.join(str(s) for s in shape)})"
            else:
                shape_str = "Scalar"
            info = {
                "path": path,
                "type": "Dataset",
                "dtype": self._fmt_dtype(obj.dtype),
                "shape": shape_str,
                "ndim": len(shape) if shape is not None else 0,
                "total_elements": self._numel(shape),
                "raw_size": self._fmt_bytes(int(obj.nbytes or 0)),
                "storage_size": self._fmt_bytes(int(obj.id.get_storage_size())),
                "compression": obj.compression or "None",
                "compression_opts": str(obj.compression_opts) if obj.compression_opts is not None else "-",
                "chunks": str(obj.chunks) if obj.chunks else "Contiguous",
                "shuffle": str(obj.shuffle),
                "fletcher32": str(obj.fletcher32),
                "scaleoffset": str(obj.scaleoffset) if obj.scaleoffset is not None else "-",
                "fillvalue": str(obj.fillvalue) if obj.fillvalue is not None else "-",
                "maxshape": str(obj.maxshape) if obj.maxshape else "-",
            }
            return {"ok": True, "details": info}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # -- Statistics ---------------------------------------------------

    def get_stats(self, path: str) -> dict:
        """Compute statistics for a numeric or boolean dataset.

        Min / max / mean / std are streamed block by block, so they work for
        datasets larger than memory; median and the unique count need all
        values at once and are skipped (null / -1) beyond a size limit.
        """
        try:
            obj, err = self._dataset(path)
            if err:
                return err
            dt = obj.dtype
            if dt.kind == "c":
                return {"ok": False, "error": "Statistics are not supported for complex data"}
            if dt.kind not in "biuf":
                return {"ok": False, "error": f"Non-numeric dataset ({self._fmt_dtype(dt)})"}
            if obj.shape is None:
                return {"ok": False, "error": "Dataset has no data (null dataspace)"}

            total = self._numel(obj.shape)
            is_float = dt.kind == "f"
            keep_values = total <= _MEDIAN_MAX_ELEMENTS
            kept = []
            count = 0
            mean = 0.0
            m2 = 0.0
            vmin = vmax = None
            nan_count = inf_count = 0

            for block in self._iter_blocks(obj):
                block = block.reshape(-1)
                if dt.kind == "b":
                    block = block.astype(np.uint8)
                if is_float:
                    nan_mask = np.isnan(block)
                    nan_count += int(np.count_nonzero(nan_mask))
                    fin_mask = np.isfinite(block)
                    inf_count += int(block.size - np.count_nonzero(fin_mask)) - int(np.count_nonzero(nan_mask))
                    block = block[fin_mask]
                if block.size == 0:
                    continue
                b = block.astype(np.float64)
                bn = b.size
                bmean = float(b.mean())
                bm2 = float(((b - bmean) ** 2).sum())
                # Chan et al. parallel combination of mean / variance
                delta = bmean - mean
                tot = count + bn
                mean += delta * bn / tot
                m2 += bm2 + delta * delta * count * bn / tot
                count = tot
                bmin, bmax = block.min(), block.max()
                vmin = bmin if vmin is None or bmin < vmin else vmin
                vmax = bmax if vmax is None or bmax > vmax else vmax
                if keep_values:
                    kept.append(block)

            if count == 0:
                return {"ok": False, "error": "No finite values" if total else "Dataset is empty"}

            median = None
            unique = -1
            if keep_values:
                allv = np.concatenate(kept)
                median = float(np.median(allv))
                if allv.size < _UNIQUE_MAX_ELEMENTS:
                    unique = int(np.unique(allv).size)

            stats = {
                "min": self._to_json_val(vmin),
                "max": self._to_json_val(vmax),
                "mean": mean,
                "std": math.sqrt(m2 / count),
                "median": median,
                "total": total,
                "finite": count,
                "nan_count": nan_count,
                "inf_count": inf_count,
                "unique": unique,
            }
            return {"ok": True, "stats": stats}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @staticmethod
    def _iter_blocks(obj):
        """Yield the dataset as consecutive blocks along axis 0."""
        shape = obj.shape
        if not shape:
            yield np.asarray(obj[()])
            return
        if shape[0] == 0:
            return
        row = max(1, math.prod(shape[1:]))
        step = max(1, _BLOCK_ELEMENTS // row)
        for start in range(0, shape[0], step):
            yield np.asarray(obj[start:start + step])

    # -- Image Rendering ----------------------------------------------

    def get_image_base64(self, path: str) -> dict:
        """Render a 2D/3D dataset as a PNG image, return as base64 data URI."""
        try:
            obj, err = self._dataset(path)
            if err:
                return err

            shape = obj.shape
            ok_shape = shape is not None and (
                len(shape) == 2 or (len(shape) == 3 and shape[2] in (1, 3, 4))
            )
            if not ok_shape:
                return {"ok": False, "error": f"Unsupported shape for image: {shape}"}
            if obj.dtype.kind not in "biufc":
                return {"ok": False, "error": f"Cannot render {self._fmt_dtype(obj.dtype)} data as an image"}

            pixels = shape[0] * shape[1]
            max_px = int(self.config.get("viewer", {}).get("max_image_pixels", 4_000_000))
            if pixels == 0:
                return {"ok": False, "error": "Dataset is empty"}
            if pixels > max_px:
                return {"ok": False, "error": f"Image too large ({pixels:,} pixels, max {max_px:,})"}

            from PIL import Image

            data = np.asarray(obj[()])
            if data.ndim == 3 and data.shape[2] == 1:
                data = data[:, :, 0]

            normalized = False
            if data.dtype == np.uint8:
                img_arr = data
            elif data.dtype.kind == "b":
                img_arr = data.astype(np.uint8) * 255
            else:
                if data.dtype.kind == "c":
                    data = np.abs(data)
                data = data.astype(np.float64)
                finite = np.isfinite(data)
                if finite.any():
                    dmin = float(data[finite].min())
                    dmax = float(data[finite].max())
                else:
                    dmin = dmax = 0.0
                rng = dmax - dmin if dmax > dmin else 1.0
                scaled = np.where(finite, (data - dmin) / rng * 255.0, 0.0)
                img_arr = np.clip(np.rint(scaled), 0, 255).astype(np.uint8)
                normalized = True

            img = Image.fromarray(np.ascontiguousarray(img_arr))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            return {
                "ok": True,
                "data_uri": f"data:image/png;base64,{b64}",
                "width": img.width,
                "height": img.height,
                "normalized": normalized,
            }
        except ImportError:
            return {"ok": False, "error": "Pillow not installed - run: pip install Pillow"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # -- Export --------------------------------------------------------

    def export_csv(self, path: str, save_path: str) -> dict:
        """Export a dataset to CSV at full precision, streaming large datasets."""
        try:
            obj, err = self._dataset(path)
            if err:
                return err
            shape = obj.shape
            if shape is None:
                return {"ok": False, "error": "Dataset has no data (null dataspace)"}

            exp = self.config.get("export", {})
            sep = exp.get("csv_separator", ",") or ","
            line_end = exp.get("csv_line_ending", "\n") or "\n"
            conv = self._csv_converter(obj.dtype)

            with open(save_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f, delimiter=sep, lineterminator=line_end)

                if len(shape) == 0:
                    writer.writerow(["value"])
                    writer.writerow([conv(np.asarray(obj[()]).reshape(1))[0]])
                elif len(shape) == 1:
                    writer.writerow(["index", "value"])
                    i = 0
                    for block in self._iter_blocks(obj):
                        vals = conv(block)
                        writer.writerows(zip(range(i, i + len(vals)), vals))
                        i += len(vals)
                elif len(shape) == 2:
                    writer.writerow([f"col_{c}" for c in range(shape[1])])
                    for block in self._iter_blocks(obj):
                        writer.writerows(conv(block))
                else:
                    writer.writerow([f"dim_{d}" for d in range(len(shape))] + ["value"])
                    inner = shape[1:]
                    r0 = 0
                    for block in self._iter_blocks(obj):
                        vals = conv(block.reshape(-1))
                        idx = np.unravel_index(np.arange(len(vals)), (block.shape[0],) + inner)
                        idx = np.stack(idx, axis=1)
                        idx[:, 0] += r0
                        writer.writerows(i + [v] for i, v in zip(idx.tolist(), vals))
                        r0 += block.shape[0]

            return {"ok": True, "path": save_path}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _csv_converter(self, dtype):
        """Return a function mapping an array to (nested) lists of CSV cells."""
        if dtype.kind in "biuf":
            return lambda a: a.tolist()       # floats keep full precision (repr)

        def conv(a):
            return np.vectorize(self._csv_cell, otypes=[object])(a).tolist() if a.size else a.tolist()
        return conv

    def _csv_cell(self, v):
        if isinstance(v, (bytes, np.bytes_)):
            return self._decode(v)
        if isinstance(v, np.ndarray):
            return str(v.tolist())
        return str(v)

    # -- Helpers -------------------------------------------------------

    def _array_to_json(self, arr) -> list:
        """Convert an array to (nested) JSON-safe lists, vectorized where possible."""
        arr = np.asarray(arr)
        kind = arr.dtype.kind
        if kind == "f":
            out = arr.tolist()
            bad = ~np.isfinite(arr)
            if bad.any():
                for idx in zip(*np.nonzero(bad)):
                    self._set_nested(out, idx, self._to_json_val(arr[idx]))
            return out
        if kind in "iu":
            if arr.size and (int(arr.max()) >= _JS_MAX_INT or int(arr.min()) <= -_JS_MAX_INT):
                return arr.astype(str).tolist()
            return arr.tolist()
        if kind == "b":
            return arr.tolist()
        if arr.size == 0:
            return arr.tolist()
        return np.vectorize(self._to_json_val, otypes=[object])(arr).tolist()

    @staticmethod
    def _set_nested(lst, idx, value):
        for i in idx[:-1]:
            lst = lst[i]
        lst[idx[-1]] = value

    def _to_json_val(self, val):
        """Convert a numpy/HDF5 value to a JSON-friendly Python type."""
        if isinstance(val, (bytes, np.bytes_)):
            return self._decode(val)
        if isinstance(val, np.ndarray):
            if val.ndim == 0:
                return self._to_json_val(val[()])
            return [self._to_json_val(v) for v in val.flat[:100]]
        if isinstance(val, (bool, np.bool_)):
            return bool(val)
        if isinstance(val, (int, np.integer)):
            v = int(val)
            return v if -_JS_MAX_INT < v < _JS_MAX_INT else str(v)
        if isinstance(val, (float, np.floating)):
            v = float(val)
            if math.isnan(v):
                return "NaN"
            if math.isinf(v):
                return "Inf" if v > 0 else "-Inf"
            return v
        if isinstance(val, str):
            return val
        if isinstance(val, h5py.Empty):
            return "(empty)"
        if isinstance(val, np.void) and val.dtype.names:
            return "(" + ", ".join(str(self._to_json_val(val[n])) for n in val.dtype.names) + ")"
        return str(val)

    @staticmethod
    def _decode(b) -> str:
        try:
            return bytes(b).decode("utf-8")
        except UnicodeDecodeError:
            return bytes(b).hex()

    @staticmethod
    def _numel(shape) -> int:
        if shape is None:
            return 0
        return math.prod(shape)

    @staticmethod
    def _fmt_dtype(dtype) -> str:
        """Readable dtype name, e.g. 'string (utf-8)' instead of 'object'."""
        info = h5py.check_string_dtype(dtype)
        if info is not None:
            enc = info.encoding
            return f"string ({enc})" if info.length is None else f"string[{info.length}] ({enc})"
        vlen = h5py.check_vlen_dtype(dtype)
        if vlen is not None:
            return f"vlen<{vlen}>"
        if h5py.check_ref_dtype(dtype) is not None:
            return "reference"
        if h5py.check_enum_dtype(dtype) is not None:
            return f"enum<{dtype}>"
        if dtype.names:
            return "compound{" + ", ".join(f"{n}: {dtype.fields[n][0]}" for n in dtype.names) + "}"
        return str(dtype)

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
