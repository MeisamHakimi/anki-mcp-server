"""Assemble build/mcpb/ (a uv-type MCP Bundle for Claude Desktop) and pack it to dist/anki-mcp-server.mcpb.

Claude Desktop installs uv-type bundles itself: it provides Python and installs the dependencies listed in the
bundle's pyproject.toml, so users need nothing else. Requires Node.js (for `npx @anthropic-ai/mcpb`).
Usage: python scripts/build_mcpb.py [--no-pack]
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "mcpb"
OUT = ROOT / "dist" / "anki-mcp-server.mcpb"
MCPB_CLI = "@anthropic-ai/mcpb@2.1.2"
REPO = "https://github.com/MeisamHakimi/anki-mcp-server"

sys.path.insert(0, str(ROOT / "src"))
from anki_mcp_server import __version__  # noqa: E402
from anki_mcp_server.config import Settings  # noqa: E402
from anki_mcp_server.server import create_server  # noqa: E402

LAUNCHER = '''"""Entry point for the Claude Desktop extension: runs the bundled anki_mcp_server package."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from anki_mcp_server.server import main  # noqa: E402

main()
'''


def tool_list() -> list[dict]:
    tools = asyncio.run(create_server(Settings()).list_tools())
    return [{"name": t.name, "description": (t.description or "").strip().split("\n\n")[0].replace("\n", " ")}
            for t in tools]


def main() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    if project["version"] != __version__:
        sys.exit(f"pyproject version {project['version']} != package version {__version__}")

    shutil.rmtree(BUILD, ignore_errors=True)
    (BUILD / "server").mkdir(parents=True)
    shutil.copytree(ROOT / "src" / "anki_mcp_server", BUILD / "src" / "anki_mcp_server",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (BUILD / "server" / "main.py").write_text(LAUNCHER)
    for f in ("LICENSE", "README.md", "PRIVACY.md"):
        shutil.copy2(ROOT / f, BUILD / f)
    shutil.copy2(ROOT / "assets" / "icon.png", BUILD / "icon.png")
    # Dependencies only; the code itself is bundled, so the project isn't built or installed.
    deps = ",\n".join(f'    "{d}"' for d in project["dependencies"])
    (BUILD / "pyproject.toml").write_text(
        f'[project]\nname = "anki-mcp-server-bundle"\nversion = "{__version__}"\n'
        f'requires-python = "{project["requires-python"]}"\ndependencies = [\n{deps},\n]\n\n'
        "[tool.uv]\npackage = false\n")
    (BUILD / ".mcpbignore").write_text(".venv/\n__pycache__/\n*.pyc\nuv.lock\n")

    manifest = {
        "manifest_version": "0.4",
        "name": "anki-mcp-server",
        "display_name": "Anki Flashcards (community)",
        "version": __version__,
        "description": "Create, import, search, edit and organize Anki flashcards, add pronunciation audio, and sync to your phone.",
        "long_description": (
            "Lets Claude work with Anki Desktop on your computer through the AnkiConnect add-on (code 2055492159): "
            "create decks, add notes, import TSV/CSV files, search, edit, move, rename and delete (always with a "
            "preview and your approval, plus automatic backups), add pronunciation audio in 60+ languages, and sync "
            "to AnkiWeb. Requires Anki Desktop 23.10+ with AnkiConnect installed. Unofficial community project, not "
            "affiliated with Anki."),
        "author": {"name": "MeisamHakimi", "url": "https://github.com/MeisamHakimi"},
        "repository": {"type": "git", "url": f"{REPO}.git"},
        "homepage": REPO,
        "documentation": f"{REPO}#readme",
        "support": f"{REPO}/issues",
        "icon": "icon.png",
        "server": {
            "type": "uv",
            "entry_point": "server/main.py",
            "mcp_config": {
                "command": "uv",
                "args": ["run", "--directory", "${__dirname}", "server/main.py"],
                "env": {
                    "ANKI_MCP_READ_ONLY": "${user_config.read_only}",
                    "ANKI_MCP_ALLOW_DELETE": "${user_config.allow_delete}",
                },
            },
        },
        "tools": tool_list(),
        "keywords": ["anki", "flashcards", "spaced-repetition", "language-learning", "vocabulary", "study"],
        "license": "MIT",
        "privacy_policies": [f"{REPO}/blob/main/PRIVACY.md"],
        "compatibility": {"platforms": ["darwin", "win32", "linux"], "runtimes": {"python": ">=3.10"}},
        "user_config": {
            "read_only": {
                "type": "boolean",
                "title": "Read-only mode",
                "description": "Only allow reading and searching; no adding, editing or deleting.",
                "default": False,
            },
            "allow_delete": {
                "type": "boolean",
                "title": "Allow deleting notes and decks",
                "description": "Deletions always need a preview and your approval, and are backed up first.",
                "default": True,
            },
        },
    }
    (BUILD / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"assembled {BUILD.relative_to(ROOT)} ({len(manifest['tools'])} tools)")

    if "--no-pack" in sys.argv:
        return
    npx = shutil.which("npx")
    if not npx:
        sys.exit("npx (Node.js) is needed to pack the bundle; or run with --no-pack.")
    OUT.parent.mkdir(exist_ok=True)
    subprocess.run([npx, "-y", MCPB_CLI, "validate", str(BUILD / "manifest.json")], check=True)
    subprocess.run([npx, "-y", MCPB_CLI, "pack", str(BUILD), str(OUT)], check=True)
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
