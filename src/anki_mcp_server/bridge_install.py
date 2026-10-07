"""Install the bundled Anki MCP Bridge add-on into Anki's add-ons folder."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

ADDON_FOLDER = "anki_mcp_bridge"
BUNDLED = Path(__file__).resolve().parent / "bridge_addon" / ADDON_FOLDER
_VERSION_RE = re.compile(r'^BRIDGE_VERSION = "([^"]+)"', re.MULTILINE)


def anki_base_dir() -> Path:
    """Anki's data folder (contains addons21/ and one folder per profile). ANKI_BASE overrides it."""
    if os.environ.get("ANKI_BASE"):
        return Path(os.environ["ANKI_BASE"]).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Anki2"
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Anki2"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "Anki2"


def _version(addon_dir: Path) -> str | None:
    try:
        m = _VERSION_RE.search((addon_dir / "__init__.py").read_text(encoding="utf-8"))
    except OSError:
        return None
    return m.group(1) if m else None


def plan() -> dict:
    base = anki_base_dir()
    addons = base / "addons21"
    target = addons / ADDON_FOLDER
    conflicts = []
    if addons.is_dir():
        # Other add-ons speaking the same protocol (e.g. an older copy under another name) would fight over the port.
        for d in sorted(addons.iterdir()):
            init = d / "__init__.py"
            if d.name != ADDON_FOLDER and init.is_file():
                try:
                    if 'REQUIRED_HEADER = "X-Anki-MCP"' in init.read_text(encoding="utf-8", errors="ignore"):
                        conflicts.append(d.name)
                except OSError:
                    pass
    return {
        "anki_folder": str(base),
        "anki_folder_found": addons.is_dir(),
        "target": str(target),
        "installed_version": _version(target) if target.is_dir() else None,
        "bundled_version": _version(BUNDLED),
        "conflicting_addons": conflicts,
    }


def install() -> dict:
    p = plan()
    if not p["anki_folder_found"]:
        raise RuntimeError(
            f"Anki's add-ons folder wasn't found at {p['anki_folder']}/addons21. Open Anki once first, or set ANKI_BASE "
            "to your Anki data folder (Anki: Tools > Add-ons > View Files shows it)."
        )
    target = Path(p["target"])
    old_meta: dict = {}
    if (target / "meta.json").is_file():
        try:
            old_meta = json.loads((target / "meta.json").read_text(encoding="utf-8"))
        except ValueError:
            pass
    target.mkdir(exist_ok=True)
    for f in BUNDLED.iterdir():
        if f.is_file() and f.name != "manifest.json":
            shutil.copy2(f, target / f.name)
    meta = {"name": "Anki MCP Bridge", "mod": int(time.time()), "disabled": False}
    if isinstance(old_meta.get("config"), dict):
        meta["config"] = old_meta["config"]  # keep the user's port setting
    (target / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {**p, "installed": True, "installed_version": p["bundled_version"]}
