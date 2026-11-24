"""Build Groot's website into one folder, ready for GitHub Pages.

    python website/build.py [OUTPUT_FOLDER]      (the default is _site)

It copies:
- website/: the page, its script, the app manifest and the icons
- the home page's script, helpers and styles from web/static/
- the Python files listed in PY_FILES in web/browser.py, plus py-files.json
  listing them, so app.js knows what to load

Only those files are copied, so a .env file or deadlines.json can never end
up on the website. It uses only the standard library, so it runs anywhere.
"""

import ast
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEBSITE_FILES = ["index.html", "app.js", "manifest.webmanifest"]
ICONS = ["icon-32.png", "icon-192.png", "icon-512.png", "icon-maskable-512.png", "apple-touch-icon.png"]
STATIC_FILES = ["home.js", "common.js", "groot.css"]


def py_files() -> list[str]:
    """PY_FILES from web/browser.py, read without running it (the build machine has no packages installed)."""
    tree = ast.parse((ROOT / "web" / "browser.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(target, "id", None) == "PY_FILES" for target in node.targets):
            return ast.literal_eval(node.value)
    raise SystemExit("PY_FILES was not found in web/browser.py")


def build(out: Path) -> list[Path]:
    """Make the website in out, replacing what was there. Returns every file written."""
    if out.exists():
        shutil.rmtree(out)
    copies = [(ROOT / "website" / name, out / name) for name in WEBSITE_FILES]
    copies += [(ROOT / "website" / "icons" / name, out / "icons" / name) for name in ICONS]
    copies += [(ROOT / "web" / "static" / name, out / "static" / name) for name in STATIC_FILES]
    paths = py_files()
    copies += [(ROOT / path, out / "py" / path) for path in paths]
    written = []
    for source, target in copies:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        written.append(target)
    listing = out / "py-files.json"
    listing.write_text(json.dumps(paths, indent=2) + "\n", encoding="utf-8")
    written.append(listing)
    return written


if __name__ == "__main__":
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "_site"
    files = build(folder)
    print(f"Built Groot's website in {folder}: {len(files)} files.")
