#!/usr/bin/env python3
"""Check README.md and CHANGELOG.md against the code they describe.

Standard library only (CI runs it before installing anything). Exits 1 and
lists every finding when a document has drifted:

  paths      every repository path in README's tree exists, and every tracked
             top-level entry is in the tree
  links      relative links and #anchors in README / CHANGELOG resolve
  config     README's config block, launch.py's defaults and config.json have
             the same keys and default values
  formats    the HDF5 extensions agree in README, the welcome screen, the
             Open-dialog filter and register.bat
  shortcuts  the Ctrl shortcuts README lists are the ones viewer.html handles
  flags      the launch.py flags README shows exist, and every flag is shown
  bridge     every API method viewer.html calls exists on lib.app.App, and
             every public App method is called by the page
  requires   README's requirement list matches requirements.txt
  fonts      fonts.css names files that exist; build.py bundles lib/fonts
  version    lib/__init__.py's version heads CHANGELOG; README's current
             version and SHA-256 belong to the latest v* tag (the release
             CI builds from it), when tags are available
"""
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
findings = []


def find(check, msg):
    findings.append(f"[{check}] {msg}")


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


README = read("README.md")
CHANGELOG = read("CHANGELOG.md")
VIEWER = read("lib/viewer.html")
LAUNCH = read("launch.py")


def git(*args):
    try:
        out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    except OSError:
        return None
    return out.stdout if out.returncode == 0 else None


# -- paths ---------------------------------------------------------------
def check_paths():
    tree = re.search(r"```\nH5Lens/\n(.*?)```", README, re.S)
    if not tree:
        return find("paths", "README has no H5Lens/ tree block")
    stack, listed = [], set()
    for line in tree.group(1).splitlines():
        m = re.match(r"^((?:│   |    )*)(?:├── |└── )(\S+)", line)
        if not m:
            continue
        depth = len(m.group(1)) // 4
        name = m.group(2)
        stack[depth:] = [name.rstrip("/")]
        rel = "/".join(stack)
        listed.add(rel)
        if not (ROOT / rel).exists():
            find("paths", f"README tree lists {rel}, which does not exist")
    tracked = git("ls-files")
    if tracked is not None:
        tops = {p.split("/")[0] for p in tracked.splitlines() if p}
        for top in sorted(tops - {".gitignore"} - {p.split("/")[0] for p in listed}):
            find("paths", f"tracked {top} is missing from README's tree")


# -- links -----------------------------------------------------------------
def anchors(text):
    out = set()
    for h in re.findall(r"^#+ (.+)$", text, re.M):
        slug = re.sub(r"[^\w\- ]", "", h.strip().lower()).replace(" ", "-")
        out.add(slug)
    return out


def check_links():
    for doc, text in (("README.md", README), ("CHANGELOG.md", CHANGELOG)):
        for target in re.findall(r"\]\(([^)\s]+)\)", text):
            if re.match(r"https?://", target):
                continue
            path, _, frag = target.partition("#")
            dest = ROOT / path if path else ROOT / doc
            if not dest.exists():
                find("links", f"{doc} links to {target}: no such file")
            elif frag and dest.suffix == ".md" and frag not in anchors(dest.read_text(encoding="utf-8")):
                find("links", f"{doc} links to {target}: no such heading")


# -- config ----------------------------------------------------------------
def flatten(d, prefix=""):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(flatten(v, prefix + k + "."))
        else:
            out[prefix + k] = v
    return out


def check_config():
    block = re.search(r"```jsonc\n(.*?)```", README, re.S)
    if not block:
        return find("config", "README has no jsonc config block")
    text = re.sub(r"//[^\n]*", "", block.group(1))
    readme_cfg = flatten(json.loads(text))
    tree = ast.parse(LAUNCH)
    default = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "default_config" for t in node.targets):
            default = flatten(ast.literal_eval(node.value))
    if default is None:
        return find("config", "launch.py has no default_config")
    shipped = flatten(json.loads(read("config.json")))
    for name, cfg in (("README", readme_cfg), ("config.json", shipped)):
        for k in sorted(set(default) ^ set(cfg)):
            find("config", f"key {k} is in {'launch.py' if k in default else name} only")
        for k in sorted(set(default) & set(cfg)):
            if default[k] != cfg[k]:
                find("config", f"{k}: launch.py default {default[k]!r}, {name} {cfg[k]!r}")
    for k in default:
        if k.startswith(("viewer.", "export.")) and k.split(".")[1] not in README.split("```jsonc")[1]:
            find("config", f"{k} is not explained in README")


# -- formats ---------------------------------------------------------------
def check_formats():
    exts = {}
    app = read("lib/app.py")
    m = re.search(r'HDF5_FILTER = "[^(]*\(([^)]*)\)"', app)
    exts["Open-dialog filter"] = set(re.findall(r"\*(\.\w+)", m.group(1))) if m else set()
    m = re.search(r'class="drop-fmts">(.*?)</div>', VIEWER)
    exts["welcome screen"] = set(re.findall(r"<span>(\.\w+)</span>", m.group(1))) if m else set()
    m = re.search(r"for %%x in \(([^)]*)\)", read("register.bat"))
    exts["register.bat"] = set(m.group(1).split()) if m else set()
    m = re.search(r"register\.bat\s+← Register (\S+) associations", README)
    exts["README tree"] = set(m.group(1).split("/")) if m else set()
    ref = exts["Open-dialog filter"]
    for where, got in exts.items():
        if got != ref:
            find("formats", f"{where} lists {sorted(got)}, the Open-dialog filter {sorted(ref)}")


# -- shortcuts ---------------------------------------------------------------
def check_shortcuts():
    handled = set(re.findall(r"mod && k === '(\w)'", VIEWER))
    row = re.search(r"\| \*\*Keyboard Shortcuts\*\* \|(.*)\|", README)
    documented = set(re.findall(r"`Ctrl\+(\w)`", row.group(1))) if row else set()
    for k in sorted(handled - {c.upper() for c in documented} - {c.lower() for c in documented}):
        find("shortcuts", f"viewer.html handles Ctrl+{k.upper()}, README does not list it")
    for k in sorted({c.lower() for c in documented} - handled):
        find("shortcuts", f"README lists Ctrl+{k.upper()}, viewer.html does not handle it")


# -- flags -------------------------------------------------------------------
def check_flags():
    in_code = set(re.findall(r'"(--[a-z][\w-]*)"', LAUNCH)) | set(re.findall(r"'(--[a-z][\w-]*)'", LAUNCH))
    in_readme = set(re.findall(r"launch\.py (--[a-z][\w-]*)", README)) | \
        set(re.findall(r"H5Lens\.exe (--[a-z][\w-]*)", README))
    for f in sorted(in_readme - in_code):
        find("flags", f"README shows {f}, launch.py does not accept it")
    for f in sorted(in_code - in_readme):
        find("flags", f"launch.py accepts {f}, README does not show it")


# -- bridge ------------------------------------------------------------------
def check_bridge():
    tree = ast.parse(read("lib/app.py"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "App")
    public = {f.name for f in cls.body if isinstance(f, ast.FunctionDef) and not f.name.startswith("_")}
    public -= {"set_window"}                  # called from launch.py, not the page
    called = set(re.findall(r"(?:\ba|\bapi|\(await apiReady\))\.(\w+)\(", VIEWER))
    called |= set(re.findall(r"typeof a\.(\w+) === 'function'", VIEWER))
    for m in sorted(called - public):
        find("bridge", f"viewer.html calls api.{m}, which App does not define")
    for m in sorted(public - called):
        find("bridge", f"App.{m} is never called by viewer.html")


# -- requires ----------------------------------------------------------------
def check_requires():
    reqs = {}
    for line in read("requirements.txt").splitlines():
        m = re.match(r"([\w-]+)>=([\d.]+)", line.strip())
        if m:
            reqs[m.group(1).lower()] = m.group(2)
    section = README.split("## Requirements", 1)[-1].split("\n## ", 1)[0]
    listed = {m.group(1).lower(): m.group(2) for m in re.finditer(r"^- (\w+) ≥ ([\d.]+)", section, re.M)}
    for k in sorted(set(reqs) | set(listed)):
        if reqs.get(k) != listed.get(k):
            find("requires", f"{k}: requirements.txt {reqs.get(k)}, README {listed.get(k)}")


# -- fonts -------------------------------------------------------------------
def check_fonts():
    css = read("lib/fonts/fonts.css")
    for name in re.findall(r"url\('([^']+)'\)", css):
        if not (ROOT / "lib" / "fonts" / name).is_file():
            find("fonts", f"fonts.css names {name}, which is missing")
    if "@import url('fonts/fonts.css')" not in VIEWER:
        find("fonts", "viewer.html does not import fonts/fonts.css")
    if "googleapis" in VIEWER:
        find("fonts", "viewer.html still loads fonts from Google")
    if "'lib' / 'fonts'" not in read("build.py"):
        find("fonts", "build.py does not bundle lib/fonts")


# -- version -----------------------------------------------------------------
def check_version():
    m = re.search(r'__version__ = "([\d.]+)"', read("lib/__init__.py"))
    version = m.group(1) if m else None
    head = re.search(r"^## \[([\d.]+)\] — (\S+)", CHANGELOG, re.M)
    if not head or head.group(1) != version:
        find("version", f"CHANGELOG's first section is {head and head.group(1)}, lib/__init__.py says {version}")
    tags = git("tag", "--list", "v*", "--sort=-v:refname")
    if not tags:
        return                                 # no tags fetched: nothing to compare against
    latest = tags.split()[0]
    cur = re.search(r"current version \*\*(v[\d.]+)\*\*", README)
    if not cur or cur.group(1) != latest:
        find("version", f"README's current version is {cur and cur.group(1)}, the latest tag is {latest}")
    sha = re.search(r"SHA-256 published with (v[\d.]+)", README)
    if not sha or sha.group(1) != latest:
        find("version", f"README's SHA-256 is for {sha and sha.group(1)}, the latest tag is {latest}")
    if head and f"v{head.group(1)}" == latest and head.group(2) == "Unreleased":
        find("version", f"{latest} is tagged but CHANGELOG still says Unreleased")


for fn in (check_paths, check_links, check_config, check_formats, check_shortcuts,
           check_flags, check_bridge, check_requires, check_fonts, check_version):
    fn()

if findings:
    print("\n".join(findings))
    print(f"\ncheck_doc_drift: {len(findings)} finding(s)")
    sys.exit(1)
print("check_doc_drift: 0 findings (paths, links, config, formats, shortcuts, flags, bridge, requires, fonts, version)")
