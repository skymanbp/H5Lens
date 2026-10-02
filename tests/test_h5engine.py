"""Tests for lib.h5engine (needs h5py, numpy, Pillow; no GUI)."""

import csv
import sys
from pathlib import Path

import h5py
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.h5engine import H5Engine  # noqa: E402

CFG = {
    "viewer": {"max_preview_rows": 50, "max_preview_cols": 4,
               "max_image_pixels": 10_000, "float_precision": 6},
    "export": {"csv_separator": ","},
}


@pytest.fixture
def h5file(tmp_path):
    p = tmp_path / "sample.h5"
    with h5py.File(p, "w") as f:
        g = f.create_group("grp")
        g.attrs["units"] = "m/s"
        g.attrs["flag"] = np.bool_(True)
        g.attrs["vec"] = np.arange(3)
        f["grp/tiny"] = np.array([1.5e-12, 2.0, np.nan, np.inf, -np.inf])
        f["grp/ints"] = np.arange(100, dtype=np.int32)
        f["mat"] = np.arange(60, dtype=np.float32).reshape(6, 10)
        f["cube"] = np.arange(2 * 3 * 40).reshape(2, 3, 40)
        f["scalar"] = 3.25
        f["empty"] = np.zeros((0,))
        f["empty2d"] = np.zeros((0, 5))
        f["strs"] = np.array([b"alpha", b"beta"])
        f.create_dataset("vstr", data=["x", "yy"], dtype=h5py.string_dtype())
        f["cplx"] = np.array([1 + 2j, 3 - 4j])
        f["bools"] = np.array([True, False, True])
        f["img"] = np.array([[0, 1], [np.nan, 3]], dtype=float)
        f["rgb"] = np.full((4, 5, 3), 7, dtype=np.uint8)
        f.create_dataset("comp", data=np.array([(1, 2.5)], dtype=[("a", "i4"), ("b", "f8")]))
        f["grp/back"] = f["grp"]          # hard-link cycle
        f["dangling"] = h5py.SoftLink("/nowhere")
    return p


@pytest.fixture
def eng(h5file):
    e = H5Engine(CFG)
    res = e.open(str(h5file))
    assert res["ok"], res
    e._tree = res["tree"]
    yield e
    e.close()


def _find(node, path):
    if node["path"] == path:
        return node
    for c in node.get("children", []):
        r = _find(c, path)
        if r:
            return r
    return None


def test_tree_handles_cycles_and_dangling_links(eng):
    back = _find(eng._tree, "/grp/back")
    assert back is not None and back["type"] == "link"
    assert back["target"] == "/grp"
    assert _find(eng._tree, "/dangling")["type"] == "error"


def test_small_floats_keep_significant_digits(eng):
    res = eng.get_data("/grp/tiny")
    vals = [r[1] for r in res["rows"]]
    assert vals[0] == pytest.approx(1.5e-12)
    assert vals[2:] == ["NaN", "Inf", "-Inf"]


def test_1d_truncation(eng):
    res = eng.get_data("/grp/ints")
    assert res["truncated"] and res["shown_rows"] == 50 and res["total_rows"] == 100
    assert res["rows"][49] == [49, 49]


def test_2d_truncation(eng):
    res = eng.get_data("/mat")
    assert res["headers"][-1] == "..."
    assert res["rows"][1][:3] == [1, 10.0, 11.0]
    assert res["shown_cols"] == 4 and res["total_cols"] == 10


def test_nd_preview_reads_prefix_with_positions(eng):
    res = eng.get_data("/cube")
    assert res["mode"] == "nd" and res["shown"] == 50 and res["total_elements"] == 240
    assert res["rows"][45] == [45, "[0, 1, 5]", 45]


def test_scalar_and_strings_and_misc(eng):
    assert eng.get_data("/scalar")["value"] == 3.25
    assert [r[1] for r in eng.get_data("/strs")["rows"]] == ["alpha", "beta"]
    assert [r[1] for r in eng.get_data("/vstr")["rows"]] == ["x", "yy"]
    assert [r[1] for r in eng.get_data("/bools")["rows"]] == [True, False, True]
    assert eng.get_data("/cplx")["rows"][0][1] == "(1+2j)"
    assert eng.get_data("/empty")["rows"] == []
    assert eng.get_data("/empty2d")["rows"] == []
    assert eng.get_data("/comp")["ok"]


def test_attrs(eng):
    a = eng.get_attrs("/grp")["attrs"]
    assert a == {"units": "m/s", "flag": True, "vec": [0, 1, 2]}


def test_stats(eng):
    s = eng.get_stats("/grp/tiny")["stats"]
    assert s["min"] == pytest.approx(1.5e-12) and s["max"] == 2.0
    assert s["nan_count"] == 1 and s["inf_count"] == 2 and s["total"] == 5
    assert eng.get_stats("/grp/ints")["stats"]["unique"] == 100
    assert eng.get_stats("/cplx")["ok"] is False
    assert eng.get_stats("/strs")["ok"] is False
    assert eng.get_stats("/empty")["ok"] is False
    assert eng.get_stats("/bools")["stats"]["mean"] == pytest.approx(2 / 3)


def test_image(eng):
    assert eng.get_image_base64("/img")["ok"]           # NaN-safe
    rgb = eng.get_image_base64("/rgb")
    assert rgb["ok"] and (rgb["width"], rgb["height"]) == (5, 4)
    assert "empty" in eng.get_image_base64("/empty2d")["error"].lower()


def test_export_full_precision_and_chunked(eng, tmp_path):
    out = tmp_path / "tiny.csv"
    assert eng.export_csv("/grp/tiny", str(out))["ok"]
    rows = list(csv.reader(out.open()))
    assert rows[0] == ["index", "value"] and float(rows[1][1]) == 1.5e-12

    out = tmp_path / "mat.csv"
    eng.export_csv("/mat", str(out))
    rows = list(csv.reader(out.open()))
    assert len(rows) == 7 and len(rows[0]) == 10 and rows[2][3] == "13.0"

    out = tmp_path / "cube.csv"
    eng.export_csv("/cube", str(out))
    rows = list(csv.reader(out.open()))
    assert rows[0] == ["dim_0", "dim_1", "dim_2", "value"]
    assert len(rows) == 241 and rows[-1] == ["1", "2", "39", "239"]

    out = tmp_path / "vstr.csv"
    eng.export_csv("/vstr", str(out))
    assert list(csv.reader(out.open()))[1:] == [["0", "x"], ["1", "yy"]]


def test_not_a_dataset_and_no_file(eng):
    assert eng.get_data("/grp")["ok"] is False
    eng.close()
    assert eng.get_data("/mat")["error"] == "No file open"


def test_streaming_matches_numpy(tmp_path, monkeypatch):
    import lib.h5engine as mod
    monkeypatch.setattr(mod, "_BLOCK_ELEMENTS", 7)     # force many blocks
    rng = np.random.default_rng(0)
    data = rng.normal(5, 3, size=(37, 4))
    data[3, 1] = np.nan
    p = tmp_path / "s.h5"
    with h5py.File(p, "w") as f:
        f["d"] = data
        f["big"] = np.array([2 ** 60, 1], dtype=np.int64)
    e = H5Engine(CFG)
    e.open(str(p))
    s = e.get_stats("/d")["stats"]
    fin = data[np.isfinite(data)]
    assert s["mean"] == pytest.approx(fin.mean())
    assert s["std"] == pytest.approx(fin.std())
    assert s["median"] == pytest.approx(np.median(fin))
    assert (s["min"], s["max"], s["nan_count"]) == (fin.min(), fin.max(), 1)

    out = tmp_path / "d.csv"
    e.export_csv("/d", str(out))
    back = np.genfromtxt(out, delimiter=",", skip_header=1)
    np.testing.assert_array_equal(np.isnan(back), np.isnan(data))
    np.testing.assert_array_equal(back[~np.isnan(back)], data[~np.isnan(data)])

    assert e.get_data("/big")["rows"][0][1] == str(2 ** 60)
    e.close()


@pytest.mark.parametrize("shape", [(2, 3, 4), (1, 1, 9), (5, 2, 2, 3), (3, 0, 2)])
@pytest.mark.parametrize("n", [0, 1, 4, 5, 13, 1000])
def test_read_flat_prefix(tmp_path, shape, n):
    arr = np.arange(math_prod(shape)).reshape(shape)
    p = tmp_path / "p.h5"
    with h5py.File(p, "w") as f:
        f["a"] = arr
        n = min(n, arr.size)
        got = H5Engine._read_flat_prefix(f["a"], n)
    np.testing.assert_array_equal(got, arr.reshape(-1)[:n])


def math_prod(shape):
    out = 1
    for s in shape:
        out *= s
    return out
