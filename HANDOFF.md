# Handoff — v1.1.0 debug / polish pass

Work done in a cloud session (Linux, no GUI). This file lists what was done,
how it was verified, and what is still open, so a local (Windows) session can
pick it up. Delete this file once the items below are closed.

## Done (commit `d481880`)

See the commit message for the full list. In short:

- **Bugs:** Open dialog filter string (`;` not spaces, broke Open on
  pywebview 5/6); float rounding to 8 decimals (tiny values became 0 in the
  table and in CSV); hard-link cycles; whole-dataset reads for N-D previews;
  NaN/uint8/empty handling in the image renderer; NaN vs Inf counts and
  complex/bool data in stats; engine access across pywebview's parallel call
  threads (now locked); CLI file opened before the JS bridge was ready;
  frontend tab, stale-render and stats races; "1 values" for empty datasets.
- **Performance:** vectorized JSON conversion, block-streamed stats and CSV
  export, lazy tree rendering.
- **Polish:** keyboard tree navigation, drag and drop, close button, window
  title, recent-file management, image fit/actual toggle, copy path,
  readable dtypes, `sidebar_width` / `csv_line_ending` honoured, atomic
  config writes, `--debug`, `tests/`.

## How it was verified

- `python -m pytest tests` — 36 engine tests pass (h5py 3.16, numpy 2.4,
  Pillow 12.3).
- `viewer.html` driven in headless Chromium against the real `App` class
  through a mocked `window.pywebview.api` (HTTP shim): open, tree, every tab,
  stats, image, filter, keyboard navigation, race clicks, export, close,
  recent files, open via dialog. No JS errors.
- Not verified: the real pywebview window. pywebview could not be installed
  in the cloud container (the `proxy_tools` build failed), and Windows was not available.

## Open items for the local session

1. **Smoke-test in the real window (Windows, pywebview ≥ 5):**
   - Open button / Ctrl+O shows the dialog with the HDF5 filter
     (the main bug fixed here).
   - `python launch.py some.h5` opens the file on start.
   - **Drag and drop** — needs pywebview's Python-side drop handler
     (`launch.py: enable_file_drop`, uses `pywebviewFullPath`). If the path is
     not delivered, the page shows a toast "Could not get the dropped file's
     path". Untested in a real window.
   - Window title changes to `<file> — H5 Lens` and back on close.
   - Ctrl+W / Ctrl+I / Ctrl+F are not swallowed by WebView2.
   - Copy path: `navigator.clipboard` may be blocked on `file://`; there is
     an `execCommand('copy')` fallback. Check that one of them works.
   - Sidebar width persists via `localStorage` (WebView2 may not keep it
     across runs; then `sidebar_width` from config applies).
2. **Rebuild and release v1.1.0:** `lib/__init__.py` says 1.1.0, but the
   README Download section still points to the v1.0.1 exe and its SHA-256.
   Run `python build.py` on Windows, smoke-test `dist/H5Lens.exe`, publish
   the release, and update the version + SHA-256 in README.
   - `build.py` was only lint-cleaned (unused import / variable, a
     placeholder-less f-string); its hiddenimports still list
     `numpy.core.*`, which are `numpy._core.*` on numpy 2. They are only
     warnings today, but check the build log.
3. **Decide on CSV format changes** (behaviour change vs v1.0.1):
   - N-D datasets now export `dim_0, dim_1, …, value` instead of a flat
     `index, value`.
   - Non-finite floats are written as Python's `nan` / `inf` / `-inf`
     (before: `NaN` / `Inf` / `-Inf`). pandas/numpy read both.
   Revert in `H5Engine.export_csv` if downstream scripts depend on the old
   form.
4. **Optional follow-ups (not started):**
   - Slice selector for N-D datasets (choose the 2-D plane to view / image).
   - Bundle the DM Sans / JetBrains Mono fonts locally; `viewer.html` loads
     them from Google Fonts, which fails offline (falls back to system
     fonts).
   - CSV export speed: about 13 s per 10M floats, dominated by `repr`; could use
     `np.savetxt(fmt="%.17g")` for pure-float 2-D data.

## Test harness (not committed)

The browser harness lived in the session scratchpad. To recreate it, run a small
HTTP server that stubs the `webview` module (`FileDialog` enum, `Window`),
instantiates `lib.app.App`, and maps `POST /api/<method>` to `App` methods with
`json.dumps(..., allow_nan=False)`. Then inject a `window.pywebview.api` proxy
plus a `pywebviewready` event via Playwright `addInitScript`.
