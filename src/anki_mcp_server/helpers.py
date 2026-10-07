"""Validation, field mapping, confirmation tokens and backups."""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import re
import secrets
import time
from pathlib import Path
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError


# ---------- validation ----------

def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def search_quote(s: str) -> str:
    """Quote a literal for an Anki search, escaping wildcard/special characters."""
    return '"' + re.sub(r'([\\"*_])', r"\\\1", s) + '"'


def validate_deck_name(name: Any) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ToolError("Deck name must be a non-empty string.")
    name = name.strip()
    if len(name) > 200:
        raise ToolError("Deck name is too long (max 200 characters).")
    if '"' in name or any(ord(c) < 32 for c in name):
        raise ToolError("Deck name must not contain double quotes or control characters.")
    if any(not part.strip() for part in name.split("::")):
        raise ToolError("Deck name has an empty component around '::'.")
    return name


def validate_tags(tags: Any) -> list[str]:
    out: list[str] = []
    if tags is None:
        return out
    if not isinstance(tags, list):
        raise ToolError("tags must be a list of strings.")
    for t in tags:
        if not isinstance(t, str) or not t.strip():
            raise ToolError("Tags must be non-empty strings.")
        t = t.strip()
        if re.search(r"\s", t) or '"' in t:
            raise ToolError(f"Tag {t!r} contains whitespace or quotes; Anki tags are single words (use _ or ::).")
        if t not in out:
            out.append(t)
    return out


def map_keys(keys: list[str], model_fields: list[str]) -> dict[str, str]:
    """Map user-supplied field keys to a note type's real field names.

    Case/punctuation-insensitive exact match wins; otherwise a unique word-prefix match
    ("Example" -> "Example sentence"). Unknown or ambiguous keys are errors.
    """
    by_norm = {norm(f): f for f in model_fields}
    mapping: dict[str, str] = {}
    for key in keys:
        nk = norm(key)
        if not nk:
            raise ToolError(f"Invalid field name {key!r}.")
        if nk in by_norm:
            mapping[key] = by_norm[nk]
            continue
        candidates = [f for n, f in by_norm.items() if n.startswith(nk + " ")]
        if len(candidates) == 1:
            mapping[key] = candidates[0]
        elif not candidates:
            raise ToolError(f"Field {key!r} doesn't match any field of this note type: {model_fields}")
        else:
            raise ToolError(f"Field {key!r} is ambiguous among {candidates}; use the exact field name.")
    targets = [v for v in mapping.values()]
    dupes = sorted({f for f in targets if targets.count(f) > 1})
    if dupes:
        raise ToolError(f"Several keys map to the same field {dupes}: {mapping}")
    return mapping


def field_value(v: Any, allow_html: bool) -> str:
    if v is None:
        return ""
    if not isinstance(v, str):
        raise ToolError(f"Field values must be strings, got {type(v).__name__}: {v!r}")
    v = v.strip()
    if not allow_html:
        v = html.escape(v, quote=False).replace("\r\n", "\n").replace("\n", "<br>")
    return v


# ---------- preview -> confirm ----------

class Confirmations:
    """Confirmation tokens bound to an operation and to the exact current state of its targets.

    A token is an HMAC over (operation, arguments, snapshot of the targets). It's only accepted if recomputing it
    now gives the same value, i.e. the request is identical and nothing changed since the preview. The key is
    random per process, so tokens don't survive a server restart.
    """

    def __init__(self) -> None:
        self._key = secrets.token_bytes(32)

    def token(self, op: str, payload: Any) -> str:
        data = json.dumps([op, payload], sort_keys=True, ensure_ascii=False, default=str).encode()
        return hmac.new(self._key, data, hashlib.sha256).hexdigest()[:16]

    def check(self, op: str, payload: Any, token: Any) -> None:
        if not isinstance(token, str) or not hmac.compare_digest(self.token(op, payload), token.strip()):
            raise ToolError(
                "confirm_token doesn't match: the targets changed since the preview, the arguments differ from the "
                "previewed call, or the server restarted. Call again without confirm_token for a fresh preview."
            )

    def preview(self, op: str, payload: Any, preview: dict) -> dict:
        preview["confirm_token"] = self.token(op, payload)
        preview["next_step"] = (
            "Nothing has been changed yet. Show this preview to the user. Only if they explicitly approve, call the "
            "same tool again with the same arguments plus confirm_token."
        )
        return preview


def write_backup(backup_dir: Path, kind: str, data: Any) -> str:
    backup_dir.mkdir(parents=True, exist_ok=True)
    path = backup_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-{kind}-{secrets.token_hex(3)}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return str(path)


def backup_path(backup_dir: Path, kind: str, name: str, suffix: str) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:80]
    return backup_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-{kind}-{safe}{suffix}"
