"""Clients for AnkiConnect and the optional Anki MCP Bridge add-on, plus auto-launching Anki."""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import shutil
import subprocess
import sys
from typing import Any
from urllib.parse import urlparse

import httpx
from mcp.server.mcpserver.exceptions import ToolError

from .config import Settings

log = logging.getLogger("anki-mcp-server")

API_VERSION = 6
LAUNCH_WAIT_SECONDS = 90

# Everything this server may ask AnkiConnect to do. Notably absent: note-type/template/media/deck-config changes,
# removeEmptyNotes, collection-wide tag replaces, import/export of whole collections, GUI automation beyond Browse.
ALLOWED_ACTIONS = frozenset({
    "version", "deckNames", "deckNamesAndIds", "modelNamesAndIds", "modelFieldNames", "getTags",
    "findNotes", "findCards", "notesInfo", "cardsInfo", "guiBrowse", "sync",
    "createDeck", "canAddNotesWithErrorDetail", "canAddNotes", "addNote", "multi",
    "updateNoteFields", "addTags", "removeTags", "changeDeck", "deleteNotes", "deleteDecks", "exportPackage",
})


async def port_open(url: str) -> bool:
    u = urlparse(url)
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(u.hostname, u.port), timeout=1.0)
    except (OSError, asyncio.TimeoutError):
        return False
    writer.close()
    return True


async def wait_for_port(url: str, seconds: float) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + seconds
    while loop.time() < deadline:
        if await port_open(url):
            return True
        await asyncio.sleep(1.0)
    return False


def launch_command(settings: Settings) -> list[str] | None:
    if settings.launch_command:
        return shlex.split(settings.launch_command)
    if sys.platform == "darwin":
        return ["/usr/bin/open", "-g", "-a", "Anki"]  # -g: don't steal focus
    if sys.platform.startswith("win"):
        for candidate in (
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Anki\anki.exe"),
            os.path.expandvars(r"%ProgramFiles%\Anki\anki.exe"),
        ):
            if os.path.isfile(candidate):
                return [candidate]
    found = shutil.which("anki")
    return [found] if found else None


class Anki:
    """AnkiConnect client. Starts Anki once if it isn't running (unless disabled)."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._launch_lock = asyncio.Lock()

    async def ensure_running(self) -> str | None:
        """'running' if AnkiConnect answers, 'launched' if we started Anki, None if auto-launch is off/unavailable."""
        if not self.settings.auto_launch:
            return None
        async with self._launch_lock:
            if await port_open(self.settings.anki_connect_url):
                return "running"
            cmd = launch_command(self.settings)
            if not cmd:
                return None
            log.info("AnkiConnect not reachable; starting Anki: %s", cmd)
            try:
                kwargs: dict[str, Any] = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                                          "stderr": subprocess.DEVNULL}
                if sys.platform.startswith("win"):
                    kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0)
                else:
                    kwargs["start_new_session"] = True
                subprocess.Popen(cmd, **kwargs)  # noqa: S603 - fixed command or user-configured one
            except OSError as e:
                raise ToolError(f"Couldn't start Anki with {cmd}: {e}. Start it manually or set ANKI_LAUNCH_COMMAND.") from None
            if not await wait_for_port(self.settings.anki_connect_url, LAUNCH_WAIT_SECONDS):
                raise ToolError(
                    f"Started Anki, but AnkiConnect didn't answer within {LAUNCH_WAIT_SECONDS}s. Anki may be waiting "
                    "at the profile picker or a dialog, or AnkiConnect isn't installed. Check the Anki window."
                )
            await asyncio.sleep(2.0)  # let the profile and add-ons finish loading
            return "launched"

    async def invoke(self, action: str, timeout: float = 30.0, _retry: bool = True, **params: Any) -> Any:
        if action not in ALLOWED_ACTIONS:
            raise ToolError(f"AnkiConnect action {action!r} is not allowed by this server.")
        if action == "multi":
            for sub in params.get("actions", []):
                if sub.get("action") not in ALLOWED_ACTIONS - {"multi"}:
                    raise ToolError(f"AnkiConnect action {sub.get('action')!r} is not allowed by this server.")
        payload: dict[str, Any] = {"action": action, "version": API_VERSION, "params": params}
        if self.settings.anki_connect_api_key:
            payload["key"] = self.settings.anki_connect_api_key
        try:
            # trust_env=False: never route localhost traffic through HTTP(S)_PROXY settings.
            async with httpx.AsyncClient(trust_env=False) as client:
                resp = await client.post(self.settings.anki_connect_url, json=payload, timeout=timeout)
        except httpx.ConnectError:
            if _retry and await self.ensure_running():
                return await self.invoke(action, timeout, _retry=False, **params)
            raise ToolError(
                f"Can't connect to AnkiConnect at {self.settings.anki_connect_url}. Make sure Anki is running and the "
                "AnkiConnect add-on (code 2055492159) is installed; restart Anki after installing it."
            ) from None
        except httpx.TimeoutException:
            raise ToolError(
                f"AnkiConnect didn't answer within {timeout:.0f}s for {action!r}. Anki may be busy or showing a dialog."
            ) from None
        except httpx.HTTPError as e:
            raise ToolError(f"HTTP error talking to AnkiConnect: {e}") from None
        try:
            body = resp.json()
        except ValueError:
            raise ToolError(f"AnkiConnect returned a non-JSON response (HTTP {resp.status_code}).") from None
        if not isinstance(body, dict) or set(body) != {"result", "error"}:
            raise ToolError(f"Unexpected AnkiConnect response for {action!r}: {body!r}")
        if body["error"] is not None:
            raise ToolError(f"AnkiConnect {action} failed: {body['error']}")
        return body["result"]


class Bridge:
    """Client for the optional Anki MCP Bridge add-on (deck/profile rename, AwesomeTTS audio)."""

    HEADER = "X-Anki-MCP"

    def __init__(self, settings: Settings, anki: Anki):
        self.settings = settings
        self.anki = anki

    async def call(self, action: str, timeout: float = 30.0, _retry: bool = True, **params: Any) -> Any:
        try:
            async with httpx.AsyncClient(trust_env=False) as client:
                resp = await client.post(self.settings.bridge_url, json={"action": action, "params": params},
                                         headers={self.HEADER: "1"}, timeout=timeout)
        except httpx.ConnectError:
            # Only worth waiting if we just started Anki; if Anki was already running, the add-on isn't installed.
            if _retry and await self.anki.ensure_running() == "launched" and await wait_for_port(self.settings.bridge_url, 20):
                return await self.call(action, timeout, _retry=False, **params)
            raise ToolError(
                f"This needs the 'Anki MCP Bridge' add-on, which isn't reachable at {self.settings.bridge_url}. "
                "Install it (see the README), then restart Anki."
            ) from None
        except httpx.TimeoutException:
            raise ToolError("The Anki MCP Bridge add-on didn't answer in time; Anki may still be working.") from None
        try:
            body = resp.json()
        except ValueError:
            raise ToolError(f"Bridge returned a non-JSON response (HTTP {resp.status_code}).") from None
        if body.get("error"):
            raise ToolError(f"Anki MCP Bridge: {body['error']}")
        return body.get("result")

    async def info(self) -> dict | None:
        """Bridge info, or None if the add-on isn't available. Never launches Anki."""
        try:
            return await self.call("info", timeout=5.0, _retry=False)
        except ToolError:
            return None
