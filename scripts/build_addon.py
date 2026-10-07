"""Package anki_addon/anki_mcp_bridge as dist/anki_mcp_bridge.ankiaddon (double-click to install in Anki)."""

import json
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "anki_addon" / "anki_mcp_bridge"
OUT = ROOT / "dist" / "anki_mcp_bridge.ankiaddon"


def main() -> None:
    OUT.parent.mkdir(exist_ok=True)
    manifest = json.loads((SRC / "manifest.json").read_text())
    manifest["mod"] = int(time.time())
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(SRC.iterdir()):
            if f.name == "manifest.json" or f.name.startswith(".") or f.name == "__pycache__":
                continue
            z.write(f, f.name)
        z.writestr("manifest.json", json.dumps(manifest, indent=2))
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
