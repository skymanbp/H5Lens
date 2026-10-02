"""Tests for lib.app (the JS bridge); no window is created."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
webview = pytest.importorskip("webview")
# noqa below because lib is importable only after the sys.path entry above
from lib import app as app_mod  # noqa: E402


def make_app(tmp_path, **cfg):
    path = tmp_path / "config.json"
    return app_mod.App({"viewer": {"sidebar_width": 300}, "recent_files": [], **cfg}, str(path)), path


def test_dialog_filters_pass_pywebviews_own_validator():
    from webview.util import parse_file_type
    assert parse_file_type(app_mod.HDF5_FILTER) == ("HDF5 Files", "*.h5;*.hdf5;*.he5;*.hdf;*.nc")
    assert parse_file_type(app_mod.ALL_FILTER) == ("All Files", "*.*")
    assert parse_file_type("CSV Files (*.csv)") == ("CSV Files", "*.csv")
    with pytest.raises(ValueError):             # the v1.0.1 form, which broke Open
        parse_file_type("HDF5 Files (*.h5 *.hdf5)")


def test_sidebar_width_is_saved_to_config(tmp_path):
    app, path = make_app(tmp_path)
    app.set_sidebar_width(412)
    assert json.loads(path.read_text(encoding="utf-8"))["viewer"]["sidebar_width"] == 412
    app.set_sidebar_width("not a number")       # ignored, file unchanged
    assert json.loads(path.read_text(encoding="utf-8"))["viewer"]["sidebar_width"] == 412


def test_recent_files_and_atomic_save(tmp_path):
    app, path = make_app(tmp_path, max_recent_files=2)
    for name in ("a.h5", "b.h5", "c.h5"):
        app._add_recent(str(tmp_path / name))
    saved = json.loads(path.read_text(encoding="utf-8"))["recent_files"]
    assert saved == [str(tmp_path / "c.h5"), str(tmp_path / "b.h5")]
    assert [r["exists"] for r in app.get_recent_files()] == [False, False]
    app.remove_recent(str(tmp_path / "c.h5"))
    app.clear_recent()
    assert json.loads(path.read_text(encoding="utf-8"))["recent_files"] == []
    assert [p.name for p in tmp_path.iterdir()] == ["config.json"]   # no temp file left
