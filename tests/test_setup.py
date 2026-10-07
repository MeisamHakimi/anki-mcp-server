from __future__ import annotations

import io
import json
import zipfile

import pytest

from anki_mcp_server import setup_wizard as sw


def _zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for k, v in files.items():
            z.writestr(k, v)
    return buf.getvalue()


GOOD = _zip({"__init__.py": b"class AnkiConnect:\n    pass\n", "config.json": b"{}", "web.py": b""})


def test_install_ankiconnect_verifies_package(tmp_path):
    target = sw.install_ankiconnect(tmp_path, download=lambda url: GOOD)
    assert (target / "__init__.py").is_file() and json.loads((target / "meta.json").read_text())["name"] == "AnkiConnect"
    assert "ankiweb.net/shared/download/2055492159" in sw.ANKICONNECT_URL.format(id=sw.ANKICONNECT_ID, point=1)
    with pytest.raises(RuntimeError, match="doesn't look like AnkiConnect"):
        sw.install_ankiconnect(tmp_path, download=lambda url: _zip({"__init__.py": b"evil", "config.json": b"{}"}))
    with pytest.raises(RuntimeError, match="Unexpected"):
        sw.install_ankiconnect(tmp_path, download=lambda url: _zip({"../x.py": b"", "__init__.py": b"class AnkiConnect", "config.json": b""}))
    with pytest.raises(RuntimeError, match="add-on package"):
        sw.install_ankiconnect(tmp_path, download=lambda url: b"<html>error</html>")


def test_claude_desktop_config_merge_and_backup(tmp_path):
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({"preferences": {"x": 1}, "mcpServers": {"other": {"command": "foo"}}}))
    cmd = ["/u/bin/uvx", "--from", "pkg", "anki-mcp-server"]
    assert sw.add_to_claude_desktop(cfg, cmd, write=False) == ("added", None)
    assert "anki" not in json.loads(cfg.read_text())["mcpServers"]  # write=False changes nothing
    status, backup = sw.add_to_claude_desktop(cfg, cmd)
    data = json.loads(cfg.read_text())
    assert status == "added" and backup.is_file()
    assert data["preferences"] == {"x": 1} and data["mcpServers"]["other"] == {"command": "foo"}
    assert data["mcpServers"]["anki"] == {"command": "/u/bin/uvx", "args": ["--from", "pkg", "anki-mcp-server"]}
    assert sw.add_to_claude_desktop(cfg, cmd)[0] == "unchanged"
    assert sw.add_to_claude_desktop(cfg, ["/other"])[0] == "exists"
    assert sw.add_to_claude_desktop(cfg, ["/other"], replace=True)[0] == "replaced"


def test_claude_desktop_config_created_and_invalid(tmp_path):
    cfg = tmp_path / "new" / "claude_desktop_config.json"
    assert sw.add_to_claude_desktop(cfg, ["/x"])[0] == "added" and cfg.is_file()
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(RuntimeError, match="isn't valid JSON"):
        sw.add_to_claude_desktop(bad, ["/x"])


def test_package_source_is_a_zip_without_git(monkeypatch):
    monkeypatch.delenv("ANKI_MCP_SOURCE", raising=False)
    src = sw.package_source()
    assert src.startswith("anki-mcp-server @ https://github.com/") and src.endswith(".zip") and "git+" not in src


def test_wizard_end_to_end(tmp_path, monkeypatch):
    base = tmp_path / "Anki2"
    (base / "addons21" / "1436550454" / "awesometts").mkdir(parents=True)  # AwesomeTTS present
    cfg_dir = tmp_path / "Claude"
    cfg_dir.mkdir()
    monkeypatch.setenv("ANKI_BASE", str(base))
    monkeypatch.setenv("CLAUDE_DESKTOP_CONFIG", str(cfg_dir / "claude_desktop_config.json"))
    monkeypatch.setattr(sw, "find_anki_app", lambda: "/Applications/Anki.app")
    monkeypatch.setattr(sw, "_download", lambda url: GOOD)
    monkeypatch.setattr(sw, "anki_running", lambda: False)
    monkeypatch.setattr(sw, "anki_connect_ok", lambda url="": True)
    monkeypatch.setattr(sw, "find_uvx", lambda: "/u/bin/uvx")
    monkeypatch.setattr(sw.shutil, "which", lambda name: None)  # no Claude Code CLI
    lines: list[str] = []

    # dry run changes nothing
    assert sw.Wizard(yes=True, dry_run=True, out=lines.append).run() == 0
    assert not (base / "addons21" / "2055492159").exists() and not (cfg_dir / "claude_desktop_config.json").exists()

    assert sw.Wizard(yes=True, out=lines.append).run() == 0
    assert (base / "addons21" / "2055492159" / "__init__.py").is_file()
    assert (base / "addons21" / "anki_mcp_bridge" / "__init__.py").is_file()  # default yes: AwesomeTTS detected
    entry = json.loads((cfg_dir / "claude_desktop_config.json").read_text())["mcpServers"]["anki"]
    assert entry["command"] == "/u/bin/uvx" and entry["args"][-1] == "anki-mcp-server"


def test_wizard_stops_with_instructions_when_anki_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(sw, "find_anki_app", lambda: None)
    monkeypatch.setattr(sw, "anki_install_command", lambda: None)
    lines: list[str] = []
    assert sw.Wizard(yes=True, out=lines.append).run() == 1
    assert any("apps.ankiweb.net" in l for l in lines)
