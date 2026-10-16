"""`anki-mcp-server setup`: guided, mostly automatic setup.

Checks Anki, installs the AnkiConnect add-on from AnkiWeb (optional bridge too), restarts Anki, verifies the
connection, and registers this server with Claude Desktop and Claude Code. Every change asks first
(unless --yes) and files it edits are backed up.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import time
import webbrowser
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import httpx

from . import __version__, bridge_install

ANKICONNECT_ID = "2055492159"
ANKICONNECT_URL = "https://ankiweb.net/shared/download/{id}?v=2.1&p={point}"
ANKI_DOWNLOAD_PAGE = "https://apps.ankiweb.net"
REPO = "https://github.com/MeisamHakimi/anki-mcp-server"
SERVER_NAME = "anki"


def package_source() -> str:
    """What uvx should run: this exact release from PyPI. ANKI_MCP_SOURCE overrides it (e.g. a local checkout)."""
    return os.environ.get("ANKI_MCP_SOURCE") or f"anki-mcp-server=={__version__}"


# ---------- detection ----------

def find_anki_app() -> str | None:
    if sys.platform == "darwin":
        for p in (Path("/Applications/Anki.app"), Path.home() / "Applications" / "Anki.app"):
            if p.exists():
                return str(p)
        try:
            out = subprocess.run(["mdfind", "kMDItemCFBundleIdentifier == 'net.ankiweb.dtop'"],
                                 capture_output=True, text=True, timeout=10).stdout.split("\n")
            return next((l for l in out if l.endswith(".app")), None)
        except (OSError, subprocess.SubprocessError):
            return None
    if sys.platform.startswith("win"):
        for c in (os.path.expandvars(r"%LOCALAPPDATA%\Programs\Anki\anki.exe"),
                  os.path.expandvars(r"%ProgramFiles%\Anki\anki.exe")):
            if os.path.isfile(c):
                return c
        return shutil.which("anki")
    if shutil.which("anki"):
        return shutil.which("anki")
    if shutil.which("flatpak"):
        try:
            if subprocess.run(["flatpak", "info", "net.ankiweb.Anki"], capture_output=True, timeout=20).returncode == 0:
                return "flatpak:net.ankiweb.Anki"
        except (OSError, subprocess.SubprocessError):
            pass
    return None


def anki_install_command() -> list[str] | None:
    """A trusted package-manager command that installs Anki, if one is available."""
    if sys.platform == "darwin" and shutil.which("brew"):
        return ["brew", "install", "--cask", "anki"]
    if sys.platform.startswith("linux") and shutil.which("flatpak"):
        return ["flatpak", "install", "-y", "flathub", "net.ankiweb.Anki"]
    return None


def claude_desktop_config_path() -> Path | None:
    if os.environ.get("CLAUDE_DESKTOP_CONFIG"):
        return Path(os.environ["CLAUDE_DESKTOP_CONFIG"]).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Claude" / "claude_desktop_config.json"
    return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def find_uvx() -> str | None:
    found = shutil.which("uvx")
    if found:
        return found
    for p in (Path.home() / ".local" / "bin" / "uvx", Path.home() / ".local" / "bin" / "uvx.exe",
              Path.home() / ".cargo" / "bin" / "uvx", Path("/opt/homebrew/bin/uvx"), Path("/usr/local/bin/uvx")):
        if p.is_file():
            return str(p)
    return None


def server_command() -> list[str]:
    """Absolute command Claude should run (desktop apps don't see the terminal's PATH)."""
    uvx = find_uvx()
    if uvx:
        return [uvx, "--from", package_source(), "anki-mcp-server"]
    script = shutil.which("anki-mcp-server")
    if script:
        return [str(Path(script).resolve())]
    return [sys.executable, "-m", "anki_mcp_server"]


# ---------- actions ----------

def install_ankiconnect(addons_dir: Path, download: Callable[[str], bytes] | None = None) -> Path:
    """Download AnkiConnect from AnkiWeb (the same source as Anki's Get Add-ons), verify it, and install it."""
    url = ANKICONNECT_URL.format(id=ANKICONNECT_ID, point=250900)
    data = (download or _download)(url)
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise RuntimeError("AnkiWeb didn't return an add-on package; try again later.") from None
    names = z.namelist()
    if "__init__.py" not in names or "config.json" not in names or any("/" in n or "\\" in n or ".." in n for n in names):
        raise RuntimeError(f"Unexpected AnkiConnect package contents: {names}")
    if b"class AnkiConnect" not in z.read("__init__.py"):
        raise RuntimeError("The downloaded package doesn't look like AnkiConnect; not installing it.")
    target = addons_dir / ANKICONNECT_ID
    target.mkdir(parents=True, exist_ok=True)
    for n in names:
        (target / n).write_bytes(z.read(n))
    meta = {"name": "AnkiConnect", "mod": int(time.time()), "disabled": False}
    (target / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return target


def _download(url: str) -> bytes:
    with httpx.Client(follow_redirects=True, timeout=60) as c:
        r = c.get(url)
        r.raise_for_status()
        if len(r.content) > 5 * 1024 * 1024:
            raise RuntimeError("Download unexpectedly large; not installing it.")
        return r.content


def add_to_claude_desktop(config: Path, command: list[str], name: str = SERVER_NAME,
                          replace: bool = False, write: bool = True) -> tuple[str, Path | None]:
    """Add/replace the server entry, keeping everything else. Returns (status, backup path).
    status: "unchanged" | "exists" (not replaced) | "added" | "replaced" (with write=False: what would happen)."""
    data: dict = {}
    if config.is_file():
        text = config.read_text(encoding="utf-8").strip()
        if text:
            try:
                data = json.loads(text)
            except ValueError:
                raise RuntimeError(f"{config} isn't valid JSON; fix or remove it, then run setup again.") from None
    if not isinstance(data, dict):
        raise RuntimeError(f"{config} has an unexpected format.")
    servers = data.setdefault("mcpServers", {})
    entry = {"command": command[0], "args": command[1:]}
    existing = servers.get(name)
    if existing == entry:
        return "unchanged", None
    if existing is not None and not replace:
        return "exists", None
    if not write:
        return ("replaced" if existing is not None else "added"), None
    backup = None
    if config.is_file():
        backup = config.with_name(f"{config.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(config, backup)
    servers[name] = entry
    config.parent.mkdir(parents=True, exist_ok=True)
    tmp = config.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, config)
    return ("replaced" if existing is not None else "added"), backup


def anki_connect_ok(url: str = "http://127.0.0.1:8765") -> bool:
    try:
        r = httpx.post(url, json={"action": "version", "version": 6}, timeout=3, trust_env=False)
        return r.json().get("result") == 6
    except (httpx.HTTPError, ValueError):
        return False


def anki_running() -> bool:
    return anki_connect_ok() or _process_running()


def _process_running() -> bool:
    try:
        if sys.platform.startswith("win"):
            out = subprocess.run(["tasklist"], capture_output=True, text=True, timeout=10).stdout.lower()
            return "anki.exe" in out
        return subprocess.run(["pgrep", "-f", "aqt"], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


# ---------- wizard ----------

@dataclass
class Wizard:
    yes: bool = False
    dry_run: bool = False
    bridge: bool | None = None  # None = ask (default yes if AwesomeTTS is installed)
    skip_claude: bool = False  # e.g. when the Claude plugin already provides the server
    out: Callable[[str], None] = print
    ask_fn: Callable[[str], str] = input
    notes: list[str] = field(default_factory=list)

    def ask(self, question: str, default: bool = True) -> bool:
        if self.yes:
            return default
        suffix = " [Y/n] " if default else " [y/N] "
        try:
            ans = self.ask_fn(question + suffix).strip().lower()
        except EOFError:
            return default
        return default if not ans else ans in ("y", "yes")

    def step(self, title: str) -> None:
        self.out(f"\n== {title}")

    def run(self) -> int:
        self.out(f"anki-mcp-server {__version__} setup" + (" (dry run: nothing will be changed)" if self.dry_run else ""))

        # 1. Anki itself
        self.step("1/5 Anki Desktop")
        app = find_anki_app()
        if app:
            self.out(f"found: {app}")
        else:
            self.out("Anki Desktop isn't installed.")
            cmd = anki_install_command()
            if cmd and self.ask(f"Install it now with `{' '.join(cmd)}`?"):
                if self.dry_run:
                    self.out(f"[dry run] would run: {' '.join(cmd)}")
                elif subprocess.run(cmd).returncode != 0:
                    self.out("Installation failed.")
            app = find_anki_app() if not self.dry_run else app
            if not app:
                self.out(f"Download and install Anki from {ANKI_DOWNLOAD_PAGE}, open it once, then run setup again.")
                if not self.yes and self.ask("Open the download page in your browser?"):
                    webbrowser.open(ANKI_DOWNLOAD_PAGE)
                return 1

        base = bridge_install.anki_base_dir()
        addons = base / "addons21"
        if not addons.is_dir():
            self.out(f"Anki's data folder ({addons}) doesn't exist yet: open Anki once, finish its first-run "
                     "window (language/profile), then run setup again.")
            return 1

        # 2. AnkiConnect
        self.step("2/5 AnkiConnect add-on")
        changed_addons = False
        if (addons / ANKICONNECT_ID / "__init__.py").is_file():
            self.out("installed")
        elif self.ask("AnkiConnect (add-on 2055492159) is required. Download it from AnkiWeb and install it?"):
            if self.dry_run:
                self.out(f"[dry run] would install AnkiConnect into {addons / ANKICONNECT_ID}")
            else:
                try:
                    self.out(f"installed into {install_ankiconnect(addons)}")
                    changed_addons = True
                except (RuntimeError, OSError, httpx.HTTPError) as e:
                    self.out(f"Couldn't install it automatically ({e}). In Anki: Tools > Add-ons > Get Add-ons..., "
                             "enter 2055492159, click OK, restart Anki.")
                    return 1
        else:
            self.out("Skipped. In Anki: Tools > Add-ons > Get Add-ons..., enter 2055492159, then restart Anki.")

        # 3. Optional bridge
        self.step("3/5 Anki MCP Bridge add-on (optional)")
        plan = bridge_install.plan()
        has_awesometts = any((d / "awesometts").is_dir() for d in addons.iterdir() if d.is_dir())
        self.out("Enables renaming your Anki profile and using AwesomeTTS voices"
                 + (" (AwesomeTTS detected)." if has_awesometts else "."))
        if plan["conflicting_addons"]:
            self.out(f"Skipped: these add-ons already use the bridge's port: {plan['conflicting_addons']}. Remove them "
                     "in Anki (Tools > Add-ons), then run setup again to install the bridge.")
            self.notes.append(f"Optional: remove {plan['conflicting_addons']} in Anki and re-run setup for the bridge.")
        elif plan["installed_version"] == plan["bundled_version"]:
            self.out(f"installed (v{plan['installed_version']})")
        else:
            want = self.bridge if self.bridge is not None else self.ask(
                "Install/update it?" if plan["installed_version"] is None else
                f"Update it from v{plan['installed_version']} to v{plan['bundled_version']}?", default=has_awesometts)
            if want:
                if self.dry_run:
                    self.out(f"[dry run] would install the bridge into {plan['target']}")
                else:
                    bridge_install.install()
                    self.out(f"installed into {plan['target']}")
                    changed_addons = True

        # 4. Restart Anki and check the connection
        self.step("4/5 Connection to Anki")
        if changed_addons and anki_running():
            self.restart_anki()
        if self.dry_run:
            self.out("[dry run] skipping the connection check" + ("" if anki_connect_ok() else " (AnkiConnect isn't answering right now)"))
        elif anki_connect_ok() or self.start_anki_and_wait():
            self.out("AnkiConnect is answering. ✓")
        else:
            self.out("AnkiConnect isn't answering yet. Make sure Anki is open (and was restarted after installing "
                     "add-ons). The server will also start Anki by itself when needed.")
            self.notes.append("Open Anki and check that AnkiConnect is installed (Tools > Add-ons).")

        # 5. Claude
        self.step("5/5 Connect to Claude")
        if self.skip_claude:
            self.out("Skipped (--skip-claude).")
            self.out("\nDone." if not self.notes else "\nDone, with a few things left for you:")
            for n in self.notes:
                self.out(f"  - {n}")
            return 0
        command = server_command()
        if not find_uvx():
            self.notes.append("uvx wasn't found, so Claude will run this installation directly: " + command[0])
        self.out("server command: " + " ".join(command))
        self.configure_claude_desktop(command)
        self.configure_claude_code(command)

        self.out("\nDone." if not self.notes else "\nDone, with a few things left for you:")
        for n in self.notes:
            self.out(f"  - {n}")
        self.out('Then open Claude and say: "Check my Anki status".')
        return 0

    def restart_anki(self) -> None:
        if sys.platform == "darwin" and self.ask("Restart Anki now to load the new add-ons?"):
            if self.dry_run:
                self.out("[dry run] would restart Anki")
                return
            subprocess.run(["osascript", "-e", 'tell application "Anki" to quit'], capture_output=True, timeout=60)
            for _ in range(30):
                if not _process_running():
                    break
                time.sleep(1)
            subprocess.run(["/usr/bin/open", "-g", "-a", "Anki"], capture_output=True, timeout=30)
        else:
            self.out("Please quit Anki completely and open it again so it loads the new add-ons.")
            if not self.yes:
                self.ask_fn("Press Enter once Anki is open again... ")

    def start_anki_and_wait(self) -> bool:
        from .anki import launch_command
        from .config import Settings
        cmd = launch_command(Settings())
        if not cmd:
            return False
        self.out("starting Anki...")
        try:
            subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=not sys.platform.startswith("win"))
        except OSError:
            return False
        for _ in range(60):
            if anki_connect_ok():
                return True
            time.sleep(1.5)
        return False

    def configure_claude_desktop(self, command: list[str]) -> None:
        config = claude_desktop_config_path()
        if config is None:
            return
        if not config.parent.is_dir():
            self.out(f"Claude Desktop: not found ({config.parent} doesn't exist). Install it from https://claude.ai/download "
                     "and run setup again, or see the README for manual setup.")
            return
        try:
            status, _ = add_to_claude_desktop(config, command, replace=False, write=not self.dry_run)
        except RuntimeError as e:
            self.out(f"Claude Desktop: {e}")
            return
        if self.dry_run:
            self.out(f"[dry run] Claude Desktop config {config}: " + {
                "unchanged": "already configured",
                "exists": f"already has a different '{SERVER_NAME}' server; would ask before replacing it",
                "added": f"would add the '{SERVER_NAME}' server (keeping a backup)"}[status])
            return
        if status == "exists":
            if self.ask(f"Claude Desktop already has an MCP server named '{SERVER_NAME}'. Replace it (a backup is kept)?",
                        default=False):
                status, backup = add_to_claude_desktop(config, command, replace=True)
                self.out(f"Claude Desktop: replaced (backup: {backup})")
            else:
                self.out("Claude Desktop: left unchanged.")
                return
        elif status == "unchanged":
            self.out("Claude Desktop: already configured.")
            return
        else:
            self.out(f"Claude Desktop: {status} in {config}")
        self.notes.append("Quit Claude Desktop completely (Cmd+Q / File > Exit) and reopen it.")

    def configure_claude_code(self, command: list[str]) -> None:
        claude = shutil.which("claude")
        if not claude:
            return
        try:
            exists = subprocess.run([claude, "mcp", "get", SERVER_NAME], capture_output=True, timeout=60).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return
        if exists:
            self.out(f"Claude Code: an MCP server named '{SERVER_NAME}' already exists; left unchanged.")
            return
        if not self.ask("Claude Code is installed. Add the server there too?"):
            return
        cmd = [claude, "mcp", "add", SERVER_NAME, "--scope", "user", "--", *command]
        if self.dry_run:
            self.out("[dry run] would run: " + " ".join(cmd))
            return
        ok = subprocess.run(cmd, capture_output=True, timeout=60).returncode == 0
        self.out("Claude Code: added." if ok else "Claude Code: couldn't add it; see the README for the manual command.")


def main(argv: list[str]) -> int:
    if "-h" in argv or "--help" in argv:
        print("usage: anki-mcp-server setup [--yes] [--dry-run] [--bridge | --no-bridge] [--skip-claude]")
        return 0
    bridge = True if "--bridge" in argv else (False if "--no-bridge" in argv else None)
    return Wizard(yes="--yes" in argv, dry_run="--dry-run" in argv, bridge=bridge,
                  skip_claude="--skip-claude" in argv).run()
