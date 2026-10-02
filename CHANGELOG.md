# Changelog

Each release's section here is also its GitHub release text.

## [1.1.0] — 2026-10-02

### Fixed

- **Open did nothing on pywebview 5 and 6.** The file-dialog filter used
  spaces between patterns; pywebview requires `;` and raised on every Open
  click and `Ctrl+O`.
- **Small floats were shown and exported as 0.** Values were rounded to 8
  decimal places before they left Python. They now travel at full
  precision: `float_precision` sets significant digits on screen, and CSV
  export is lossless.
- **Hard-link cycles** recursed about 1000 levels deep; a group reached a
  second time is now a link node. Null-dataspace datasets no longer become
  error nodes.
- **Image preview:** NaN/Inf no longer produce garbage pixels, `uint8` RGB is
  no longer re-stretched, and an empty dataset no longer reports
  "Image too large (0 pixels)".
- **Statistics:** NaN and Inf are counted separately, complex data no longer
  crashes, booleans are accepted.
- **Races:** engine access is locked (pywebview runs each JS call on its own
  thread); a file given on the command line is no longer dropped when the
  page loads before the bridge; the tab, selection and statistics races in
  the page are gone; empty datasets no longer show "1 values".
- **The sidebar width was not remembered across restarts.** pywebview runs
  WebView2 in private mode, which discards the page's local storage; the
  width is now saved as `sidebar_width` in `config.json`.

### Added

- **N-D datasets are shown one 2-D plane at a time.** A bar above the table
  has one control per axis: choose which axis runs down the rows, which
  across the columns, and an index for every other axis. The Image tab
  renders the same plane. (Before, the table listed the first 5000 elements
  in storage order.)
- **The fonts ship with the app** (`lib/fonts/`, SIL Open Font License), so
  the window looks the same offline.
- Keyboard tree navigation, `Ctrl+W` close, `Ctrl+I` statistics, `Ctrl+F`
  filter; drag and drop to open; a close button; the window title shows the
  open file; recent files mark missing entries and can be removed or
  cleared; image fit / actual-size toggle; copy path; selectable table
  cells; readable dtype names; on-disk size.
- `csv_line_ending` is honoured; `config.json` is written atomically and a
  malformed section falls back to its defaults; `--debug` opens the
  developer tools.
- `H5Lens.exe --self-test <report.json>` checks a build without opening a
  window; CI runs it on every build.
- Tests (`tests/`) and CI: the tests, a documentation drift check
  (`scripts/check_doc_drift.py`) and a build with its self-test on every
  push; tagged releases are built by CI.

### Changed

- **CSV export is faster** (about 1.2–1.8× on 10 million values) and its
  format changed: datasets with three or more axes export as
  `dim_0, dim_1, …, value` instead of a flat `index, value`; non-finite
  floats are written `nan` / `inf` / `-inf` (before: `NaN` / `Inf` /
  `-Inf`); `float32` values are written in their own shortest form
  (`0.1`, not `0.10000000149011612`), which still reads back exactly.
  Statistics and CSV export stream in blocks, so they work on datasets
  larger than memory.

## [1.0.1] — 2026-09-03

Patch release. No new features.

- The Image tab is offered for a 3-D dataset only when the last axis is 1, 3
  or 4; a 2-channel array no longer produces a broken preview.
- The welcome screen drops the "drag and drop" hint (never implemented) and
  lists `.hdf` alongside `.h5` / `.hdf5` / `.he5` / `.nc`, matching
  `register.bat`.
- README corrected against the code: statistics behaviour, the full
  `config.json` key set, the Pillow requirement, `register.bat` /
  `unregister.bat`, and a License line.

## [1.0.0] — 2026-02-13

First release.
