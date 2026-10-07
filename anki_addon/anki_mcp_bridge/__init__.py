"""Anki MCP Bridge: companion add-on for anki-mcp-server (https://github.com/MeisamHakimi/anki-mcp-server).

Adds what AnkiConnect can't do: rename decks, rename the profile, and generate audio with the AwesomeTTS add-on
(if installed). Listens on 127.0.0.1 only (port from the add-on config, default 8766). Requests must carry the
X-Anki-MCP header and no Origin header, so web pages can't use it.

AwesomeTTS has no public API; audio generation drives its internal batch code (tested with AwesomeTTS 1.89.4),
fills only empty fields, and never returns AwesomeTTS options or API keys.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import aqt
from aqt import gui_hooks, mw

BRIDGE_VERSION = "0.1.0"
HOST = "127.0.0.1"
DEFAULT_PORT = 8766
TESTED_AWESOMETTS_VERSION = "1.89.4"
MAX_NOTES = 300
REQUEST_TIMEOUT = 900  # seconds the HTTP thread waits for a batch to finish
REQUIRED_HEADER = "X-Anki-MCP"

_server: ThreadingHTTPServer | None = None
_busy = threading.Lock()
_profile_rename: dict[str, Any] = {"state": "none"}  # survives the bridge restart during the profile reload
_BAD_PROFILE_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


class BridgeError(Exception):
    pass


def _port() -> int:
    try:
        return int((mw.addonManager.getConfig(__name__) or {}).get("port", DEFAULT_PORT))
    except (TypeError, ValueError):
        return DEFAULT_PORT


def _find_awesometts():
    """The loaded AwesomeTTS package (installed from AnkiWeb as 1436550454, or under another folder name), or None."""
    addons_dir = mw.addonManager.addonsFolder()
    for folder in sorted(os.listdir(addons_dir)):
        if not os.path.isdir(os.path.join(addons_dir, folder, "awesometts")):
            continue
        if mw.addonManager.addonMeta(folder).get("disabled"):
            continue
        try:
            pkg = importlib.import_module(f"{folder}.awesometts")
        except Exception:
            continue
        if hasattr(pkg, "addon"):
            return pkg
    return None


def _awesometts():
    pkg = _find_awesometts()
    if pkg is None:
        raise BridgeError("AwesomeTTS isn't installed/enabled in Anki (or this version isn't compatible).")
    return pkg


def _on_main(fn, timeout: float = 30):
    """Run fn() on Anki's main thread and return its result (blocking the calling worker thread)."""
    box: dict[str, Any] = {}
    done = threading.Event()

    def run():
        try:
            box["result"] = fn()
        except Exception as e:
            box["error"] = e
        finally:
            done.set()

    mw.taskman.run_on_main(run)
    if not done.wait(timeout):
        raise BridgeError("Timed out waiting for Anki's main thread (is a dialog open?)")
    if "error" in box:
        raise box["error"]
    return box["result"]


def _info() -> dict:
    att = _find_awesometts()
    return {
        "bridge_version": BRIDGE_VERSION,
        "profile": mw.pm.name,
        "awesometts": getattr(att, "VERSION", "unknown") if att else None,
        "features": ["rename_deck", "rename_profile"] + (["generate_audio"] if att else []),
    }


def _status() -> dict:
    att = _awesometts()
    cfg = att.addon.config
    # Deliberately only non-secret values: service ids, preset/group names, field names. No options or keys.
    return {
        "awesometts_version": getattr(att, "VERSION", None),
        "tested_with": TESTED_AWESOMETTS_VERSION,
        "presets": sorted(cfg["presets"].keys()),
        "groups": sorted(cfg["groups"].keys()),
        "last_service": cfg["last_service"],
        "last_batch_source_field": cfg["last_mass_source"],
        "last_batch_dest_field": cfg["last_mass_dest"],
    }


def _resolve_service(cfg, preset: str | None) -> tuple[str, dict | None, dict | None]:
    """Returns (svc_id, options, group). preset None -> the service/options you last used in AwesomeTTS."""
    if preset:
        if preset.startswith("group:"):
            name = preset[6:]
            if name not in cfg["groups"]:
                raise BridgeError(f"No AwesomeTTS group named {name!r}. Groups: {sorted(cfg['groups'])}")
            return preset, None, cfg["groups"][name]
        if preset not in cfg["presets"]:
            raise BridgeError(f"No AwesomeTTS preset named {preset!r}. Presets: {sorted(cfg['presets'])}")
        p = dict(cfg["presets"][preset])
        svc_id = p.pop("service")
        return svc_id, p, None
    svc_id = cfg["last_service"]
    if svc_id.startswith("group:"):
        return svc_id, None, cfg["groups"].get(svc_id[6:])
    return svc_id, dict(cfg["last_options"].get(svc_id, {})), None


def _generate(params: dict) -> dict:
    note_ids = params.get("note_ids")
    source = params.get("source_field")
    dest = params.get("dest_field")
    preset = params.get("preset")
    if not isinstance(note_ids, list) or not note_ids or not all(isinstance(n, int) for n in note_ids):
        raise BridgeError("note_ids must be a non-empty list of integers")
    if len(note_ids) > MAX_NOTES:
        raise BridgeError(f"Too many notes ({len(note_ids)}); max {MAX_NOTES} per call")
    if not (isinstance(source, str) and source and isinstance(dest, str) and dest):
        raise BridgeError("source_field and dest_field are required")
    if source == dest:
        raise BridgeError("source_field and dest_field must differ")
    if preset is not None and not isinstance(preset, str):
        raise BridgeError("preset must be a string")

    if not _busy.acquire(blocking=False):
        raise BridgeError("Another audio generation batch is already running")

    finished = threading.Event()
    result: dict[str, Any] = {"generated": [], "skipped": [], "failed": []}

    def start():  # runs on the main thread
        att = _awesometts()
        addon = att.addon
        cfg = addon.config
        svc_id, options, group = _resolve_service(cfg, preset)
        result["service"] = svc_id
        result["preset"] = preset or "(last used in AwesomeTTS)"
        want_human = (cfg["filenames_human"] or "{{text}}") if cfg["filenames"] == "human" else False
        throttle = {"calls": {}, "sleep": cfg["throttle_sleep"], "threshold": cfg["throttle_threshold"]}

        queue = []
        for nid in note_ids:
            try:
                note = mw.col.get_note(nid)
            except Exception:
                result["failed"].append({"note_id": nid, "error": "note not found"})
                continue
            if source not in note or dest not in note:
                result["skipped"].append({"note_id": nid, "reason": f"note type lacks {source!r} or {dest!r} field"})
                continue
            if note[dest].strip():
                result["skipped"].append({"note_id": nid, "reason": f"{dest!r} is not empty; left unchanged"})
                continue
            text = addon.strip.from_note(note[source])
            if not text:
                result["skipped"].append({"note_id": nid, "reason": f"{source!r} has no speakable text"})
                continue
            queue.append((nid, text))

        def finish():
            _busy.release()
            finished.set()

        def next_note():
            if not queue:
                finish()
                return
            if throttle["calls"] and max(throttle["calls"].values()) >= throttle["threshold"]:
                throttle["calls"].clear()
                aqt.qt.QTimer.singleShot(throttle["sleep"] * 1000, next_note)
                return
            nid, text = queue.pop(0)
            note = mw.col.get_note(nid)

            def okay(path):
                fresh = mw.col.get_note(nid)
                if fresh[dest].strip():  # changed meanwhile; never overwrite
                    result["skipped"].append({"note_id": nid, "reason": f"{dest!r} filled meanwhile; left unchanged"})
                    return
                filename = mw.col.media.add_file(path)
                fresh[dest] = fresh[dest] + " [sound:%s]" % filename
                mw.col.update_note(fresh)
                result["generated"].append({"note_id": nid, "text": text, "file": filename})

            def fail(exception, text_=None):
                result["failed"].append({"note_id": nid, "text": text, "error": re.sub(r"\s+", " ", str(exception)).strip()})

            def miss(svc, count):
                throttle["calls"][svc] = throttle["calls"].get(svc, 0) + count

            callbacks = dict(okay=okay, fail=fail, miss=miss,
                             then=lambda: aqt.qt.QTimer.singleShot(0, next_note))
            try:
                if group is not None:
                    addon.router.group(text=text, group=group, presets=cfg["presets"],
                                       callbacks=callbacks, want_human=want_human, note=note)
                else:
                    addon.router(svc_id=svc_id, text=text, options=options,
                                 callbacks=callbacks, want_human=want_human, note=note)
            except Exception as e:  # synchronous failure: record and continue
                fail(e)
                aqt.qt.QTimer.singleShot(0, next_note)

        next_note()

    try:
        _on_main(start)
    except Exception:
        _busy.release()
        raise
    if not finished.wait(REQUEST_TIMEOUT):
        result["warning"] = "Timed out waiting; the batch is still running inside Anki. Check again later."
    result["counts"] = {k: len(result[k]) for k in ("generated", "skipped", "failed")}
    return result


def _rename_deck(params: dict) -> dict:
    old, new = params.get("name"), params.get("new_name")
    for label, v in (("name", old), ("new_name", new)):
        if not isinstance(v, str) or not v.strip() or '"' in v or any(ord(c) < 32 for c in v):
            raise BridgeError(f"{label} must be a non-empty deck name without quotes/control characters")
    old, new = old.strip(), new.strip()

    def run():
        did = mw.col.decks.id_for_name(old)
        if not did:
            raise BridgeError(f"deck {old!r} not found")
        existing = mw.col.decks.id_for_name(new)
        if existing and existing != did:  # same id = case-only rename, which is fine
            raise BridgeError(f"a deck named {new!r} already exists")
        mw.col.decks.rename(did, new)
        mw.reset()
        return {"deck_id": did, "old_name": old, "new_name": mw.col.decks.name(did)}

    return _on_main(run)


def _profile_info() -> dict:
    def run():
        return {"current": mw.pm.name, "profiles": mw.pm.profiles(), "last_rename": dict(_profile_rename)}
    return _on_main(run)


def _rename_profile(params: dict) -> dict:
    """Validate, then (after replying) close the collection, rename the profile and reopen it."""
    new = params.get("new_name")
    expected = params.get("expected_current")
    if not isinstance(new, str) or not new.strip():
        raise BridgeError("new_name must be a non-empty string")
    new = new.strip()
    if len(new) > 60 or _BAD_PROFILE_CHARS.search(new) or new.startswith(".") or new.lower() == "addons21":
        raise BridgeError('Invalid profile name: max 60 chars, no \\ / : * ? " < > | or control characters, not "addons21"')
    if _busy.locked():
        raise BridgeError("An audio generation batch is running; try again when it finishes")

    def check():
        cur = mw.pm.name
        if expected and cur != expected:
            raise BridgeError(f"Current profile is {cur!r}, not {expected!r}")
        if new == cur:
            raise BridgeError("That is already the profile name")
        if any(p.lower() == new.lower() for p in mw.pm.profiles() if p != cur):
            raise BridgeError(f"A profile named {new!r} already exists")
        target = os.path.join(mw.pm.base, new)
        if os.path.exists(target) and target.lower() != mw.pm.profileFolder(create=False).lower():
            raise BridgeError(f"Folder {target!r} already exists")
        return cur

    old = _on_main(check)
    _profile_rename.clear()
    _profile_rename.update({"state": "pending", "old": old, "new": new})

    def do_rename():  # main thread, after the HTTP reply has gone out
        def after_unload():
            try:
                mw.pm.rename(new)
                if mw.pm.name != new:
                    raise BridgeError("Anki refused the rename (see the Anki window)")
                mw.pm.load(new)
                _profile_rename.update(state="done")
            except Exception as e:
                _profile_rename.update(state="error", error=str(e))
                # Anki's pm.rename doesn't restore pm.name if the folder rename raises; reopening under the new
                # name would then create an empty profile. Go back to the old one.
                if mw.pm.name != old:
                    mw.pm.name = old
                    mw.pm.load(old)
            mw.loadProfile()  # reopen (under the new name if the rename worked)

        mw.unloadProfile(after_unload)

    mw.taskman.run_on_main(lambda: aqt.qt.QTimer.singleShot(700, do_rename))
    return {"scheduled": True, "old": old, "new": new}


class _Handler(BaseHTTPRequestHandler):
    server_version = f"AnkiMCPBridge/{BRIDGE_VERSION}"

    def log_message(self, *args):
        pass

    def _reply(self, code: int, body: dict):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        # Browsers always send Origin on cross-site POSTs and can't add custom headers without a CORS
        # preflight (which we never answer), so these two checks keep web pages out.
        if self.headers.get("Origin") or self.headers.get(REQUIRED_HEADER) != "1":
            return self._reply(403, {"result": None, "error": "forbidden"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 1_000_000:
                raise BridgeError("request too large")
            req = json.loads(self.rfile.read(length) or b"{}")
            action, params = req.get("action"), req.get("params") or {}
            if action == "info":
                res = _on_main(_info)
            elif action in ("tts_status", "status"):  # "status": older client name
                res = _on_main(_status)
            elif action == "generate":
                res = _generate(params)
            elif action == "rename_deck":
                res = _rename_deck(params)
            elif action == "profile_info":
                res = _profile_info()
            elif action == "rename_profile":
                res = _rename_profile(params)
            else:
                raise BridgeError(f"unknown action {action!r}")
            self._reply(200, {"result": res, "error": None})
        except Exception as e:
            self._reply(200, {"result": None, "error": str(e)})

    def do_GET(self):
        self._reply(405, {"result": None, "error": "use POST"})


def _start():
    global _server
    if _server is not None:
        return
    try:
        _server = ThreadingHTTPServer((HOST, _port()), _Handler)
    except OSError as e:
        print(f"[anki_mcp_bridge] could not bind {HOST}:{_port()}: {e}")
        return
    _server.daemon_threads = True
    threading.Thread(target=_server.serve_forever, name="anki-mcp-bridge", daemon=True).start()


def _stop():
    global _server
    if _server is not None:
        _server.shutdown()
        _server.server_close()
        _server = None


gui_hooks.profile_did_open.append(_start)
gui_hooks.profile_will_close.append(_stop)
