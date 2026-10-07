"""Anki MCP server: tools for adding, importing, searching, editing and organizing Anki notes and decks.

Safety model
- Talks only to AnkiConnect (and the optional bridge add-on) on localhost; stdio transport, so no network listener.
- Only an allowlist of AnkiConnect actions is used (see anki.ALLOWED_ACTIONS).
- Adding never overwrites: allowDuplicate=false, duplicates are reported as skipped.
- Anything that changes or removes existing data is two-step (preview -> confirm_token) and backed up first.
- ANKI_MCP_READ_ONLY=1 exposes only read tools; ANKI_MCP_ALLOW_DELETE=0 hides the delete tools.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from collections import Counter
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import __version__
from .anki import API_VERSION, Anki, Bridge
from .config import Settings
from .helpers import (
    Confirmations, backup_path, field_value, map_keys, search_quote, validate_deck_name, validate_tags, write_backup,
)
from .importing import match_rule, parse_file, resolve_path, validate_tag_rules

log = logging.getLogger("anki-mcp-server")

MAX_NOTES_PER_CALL = 2000
MAX_EDIT_NOTES = 500
MAX_AUDIO_NOTES = 300

READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
ADD = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
CHANGE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
DELETE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)

INSTRUCTIONS = """\
Tools for the user's local Anki collection (via the AnkiConnect add-on). Start with anki_status to see decks and
note types. Use dry_run=true to preview adds/imports. Tools that change or delete existing data first return a
preview and a confirm_token: show the preview to the user and only call again with confirm_token after they
explicitly approve that exact change. Call anki_sync after changes if the user wants them on other devices."""


def create_server(settings: Settings | None = None) -> MCPServer:
    settings = settings or Settings.from_env()
    anki = Anki(settings)
    bridge = Bridge(settings, anki)
    confirm = Confirmations()
    mcp = MCPServer(name="anki", version=__version__, instructions=INSTRUCTIONS)

    def tool(annotations: ToolAnnotations, kind: Literal["read", "add", "change", "delete"]):
        def register(fn):
            if settings.read_only and kind != "read":
                return fn
            if not settings.allow_delete and kind == "delete":
                return fn
            return mcp.tool(annotations=annotations)(fn)
        return register

    # ---------- shared helpers ----------

    async def deck_names() -> list[str]:
        return await anki.invoke("deckNames")

    async def require_deck(deck: Any) -> str:
        deck = validate_deck_name(deck)
        if deck not in await deck_names():
            raise ToolError(f"Deck {deck!r} does not exist. Create it first with anki_create_deck.")
        return deck

    async def resolve_model(model: str | None, deck: str | None) -> tuple[str, list[str]]:
        models = await anki.invoke("modelNamesAndIds")
        if model is None or not str(model).strip():
            model = settings.default_model
        if (model is None or not str(model).strip()) and deck:
            # Default to the note type most used in the target deck.
            ids = await anki.invoke("findNotes", query=f"deck:{search_quote(deck)}")
            if ids:
                infos = await anki.invoke("notesInfo", notes=ids[:200])
                common = Counter(n["modelName"] for n in infos if n).most_common(1)
                model = common[0][0] if common else None
        if model is None or not str(model).strip():
            raise ToolError(f"Pass `model` (note type). Available: {sorted(models)}")
        model = str(model).strip()
        if model not in models:
            raise ToolError(f"Note type {model!r} not found. Available: {sorted(models)}")
        return model, await anki.invoke("modelFieldNames", modelName=model)

    async def resolve_note_ids(note_ids: list[int] | None, query: str | None) -> list[int]:
        has_query = isinstance(query, str) and query.strip() != ""
        if (note_ids is not None) == has_query:
            raise ToolError("Give exactly one of note_ids or query.")
        if note_ids is not None:
            if not isinstance(note_ids, list) or not note_ids or not all(
                    isinstance(n, int) and not isinstance(n, bool) for n in note_ids):
                raise ToolError("note_ids must be a non-empty list of integers.")
            ids = sorted(set(note_ids))
        else:
            if len(query) > 1000:
                raise ToolError("query is too long (max 1000 characters).")
            ids = sorted(await anki.invoke("findNotes", query=query.strip()))
            if not ids:
                raise ToolError(f"No notes match {query!r}.")
        if len(ids) > MAX_EDIT_NOTES:
            raise ToolError(f"{len(ids)} notes targeted; max {MAX_EDIT_NOTES} per call. Narrow it down.")
        return ids

    async def snapshot(ids: list[int]) -> list[dict]:
        """Current state of notes: fields (in order), tags, note type, cards and their decks."""
        if not ids:
            return []
        infos = await anki.invoke("notesInfo", notes=ids)
        missing = [i for i, n in zip(ids, infos) if not n]
        if missing:
            raise ToolError(f"Notes not found: {missing[:20]}")
        card_ids = [c for n in infos for c in n["cards"]]
        deck_of = {c["cardId"]: c["deckName"] for c in (await anki.invoke("cardsInfo", cards=card_ids) if card_ids else [])}
        out = []
        for n in infos:
            fields = sorted(n["fields"].items(), key=lambda kv: kv[1]["order"])
            out.append({
                "note_id": n["noteId"], "model": n["modelName"], "tags": sorted(n["tags"]),
                "fields": {k: v["value"] for k, v in fields},
                "cards": {str(c): deck_of.get(c) for c in sorted(n["cards"])},
            })
        return out

    def brief(snap: dict) -> dict:
        first = next(iter(snap["fields"].values()), "")
        return {"note_id": snap["note_id"], "first_field": first[:80], "decks": sorted(set(snap["cards"].values())),
                "tags": snap["tags"]}

    async def deck_tree(name: str) -> tuple[list[str], list[int], int]:
        decks = await deck_names()
        tree = sorted(d for d in decks if d == name or d.startswith(name + "::"))
        q = f"deck:{search_quote(name)}"
        return tree, sorted(await anki.invoke("findNotes", query=q)), len(await anki.invoke("findCards", query=q))

    async def add_items(
        deck: str, model: str | None, items: list[tuple[str, dict[str, Any], list[str]]],
        allow_html: bool, duplicate_scope: str, dry_run: bool,
    ) -> dict[str, Any]:
        """items: (label, {field key: value}, tags)."""
        if not items:
            raise ToolError("No notes to add.")
        if len(items) > MAX_NOTES_PER_CALL:
            raise ToolError(f"Too many notes in one call ({len(items)}); max is {MAX_NOTES_PER_CALL}.")
        if duplicate_scope not in ("collection", "deck"):
            raise ToolError("duplicate_scope must be 'collection' or 'deck'.")
        deck = await require_deck(deck)
        model, model_fields = await resolve_model(model, deck)
        mapping = map_keys(list(dict.fromkeys(k for _, f, _ in items for k in f)), model_fields)
        first_field = model_fields[0]
        options = {
            "allowDuplicate": False,
            "duplicateScope": duplicate_scope,
            "duplicateScopeOptions": {"deckName": deck, "checkChildren": False, "checkAllModels": False},
        }
        result: dict[str, Any] = {"deck": deck, "model": model, "field_mapping": mapping,
                                  "duplicate_scope": duplicate_scope, "dry_run": dry_run,
                                  "added": [], "skipped_duplicates": [], "failed": []}
        candidates: list[tuple[str, dict]] = []
        seen: dict[str, str] = {}
        for label, fields, tags in items:
            anki_fields = {mapping[k]: field_value(v, allow_html) for k, v in fields.items()}
            key = anki_fields.get(first_field, "")
            if not key:
                result["failed"].append({"note": label, "error": f"First field {first_field!r} is empty."})
                continue
            if key in seen:
                result["skipped_duplicates"].append({"note": label, "reason": f"duplicate within this batch ({seen[key]})"})
                continue
            seen[key] = label
            candidates.append((label, {"deckName": deck, "modelName": model, "fields": anki_fields,
                                       "tags": validate_tags(tags), "options": options}))
        if candidates:
            notes = [n for _, n in candidates]
            try:
                checks = await anki.invoke("canAddNotesWithErrorDetail", notes=notes)
            except ToolError as e:
                if "unsupported action" not in str(e).lower():
                    raise
                checks = [{"canAdd": ok, "error": None if ok else "cannot create note (probably a duplicate)"}
                          for ok in await anki.invoke("canAddNotes", notes=notes)]
            addable = []
            for (label, note), check in zip(candidates, checks):
                if check.get("canAdd"):
                    addable.append((label, note))
                elif "duplicate" in (check.get("error") or "").lower():
                    result["skipped_duplicates"].append({"note": label, "reason": check.get("error")})
                else:
                    result["failed"].append({"note": label, "error": check.get("error")})
            if dry_run:
                result["would_add"] = [{"note": l, "fields": n["fields"], "tags": n["tags"]} for l, n in addable]
            elif addable:
                actions = [{"action": "addNote", "version": API_VERSION, "params": {"note": n}} for _, n in addable]
                for (label, note), r in zip(addable, await anki.invoke("multi", timeout=120.0, actions=actions)):
                    err = r.get("error") if isinstance(r, dict) else None
                    if err and "duplicate" in err.lower():
                        result["skipped_duplicates"].append({"note": label, "reason": err})
                    elif err:
                        result["failed"].append({"note": label, "error": err})
                    else:
                        note_id = r.get("result") if isinstance(r, dict) else r
                        result["added"].append({"note": label, "note_id": note_id, "tags": note["tags"]})
        result["counts"] = {"skipped_duplicates": len(result["skipped_duplicates"]), "failed": len(result["failed"])}
        if dry_run:
            result["counts"]["would_add"] = len(result.get("would_add", []))
        else:
            result["counts"]["added"] = len(result["added"])
        return result

    # ---------- read ----------

    @tool(READ, "read")
    async def anki_status() -> dict[str, Any]:
        """Check the connection. Returns the AnkiConnect version, current profile (if the bridge add-on is installed),
        decks, note types with their fields, and which optional features are available."""
        version = await anki.invoke("version")
        decks = sorted(await deck_names())
        names = sorted(await anki.invoke("modelNamesAndIds"))
        field_lists = await anki.invoke("multi", actions=[
            {"action": "modelFieldNames", "version": API_VERSION, "params": {"modelName": m}} for m in names])
        info = await bridge.info()
        return {
            "connected": True,
            "anki_connect_version": version,
            "profile": info.get("profile") if info else None,
            "decks": decks,
            "note_types": {m: (r.get("result") if isinstance(r, dict) else r) for m, r in zip(names, field_lists)},
            "bridge_addon": info or "not installed (deck/profile rename and AwesomeTTS audio unavailable)",
            "mode": "read-only" if settings.read_only else ("no-delete" if not settings.allow_delete else "full"),
        }

    @tool(READ, "read")
    async def anki_find_notes(query: str, limit: int = 50) -> dict[str, Any]:
        """Search notes with Anki search syntax, e.g. 'deck:"Spanish"', 'tag:verbs', 'Front:*hola*', 'added:1',
        'is:due'. Returns each note's id, note type, deck(s), tags and fields."""
        if not isinstance(query, str) or not query.strip():
            raise ToolError("query must be a non-empty Anki search string.")
        if len(query) > 1000:
            raise ToolError("query is too long (max 1000 characters).")
        if not 1 <= limit <= 500:
            raise ToolError("limit must be between 1 and 500.")
        ids = await anki.invoke("findNotes", query=query.strip())
        snaps = await snapshot(ids[:limit])
        notes = [{"note_id": s["note_id"], "model": s["model"], "decks": sorted(set(s["cards"].values())),
                  "tags": s["tags"], "fields": s["fields"]} for s in snaps]
        return {"query": query, "total_matches": len(ids), "returned": len(notes), "notes": notes}

    @tool(READ, "read")
    async def anki_list_tags() -> dict[str, Any]:
        """List all tags in the collection."""
        tags = await anki.invoke("getTags")
        return {"count": len(tags), "tags": sorted(tags)}

    @tool(READ, "read")
    async def anki_open_browser(query: str) -> dict[str, Any]:
        """Open Anki's Browse window filtered by an Anki search, so the user can look at or act on those cards."""
        if not isinstance(query, str) or not query.strip() or len(query) > 1000:
            raise ToolError("query must be a non-empty Anki search string (max 1000 characters).")
        cards = await anki.invoke("guiBrowse", query=query.strip())
        return {"opened": True, "cards_shown": len(cards or [])}

    # ---------- add ----------

    @tool(ADD, "add")
    async def anki_create_deck(name: str) -> dict[str, Any]:
        """Create a deck. Use "Parent::Child" for subdecks. Does nothing if it already exists."""
        name = validate_deck_name(name)
        existing = await anki.invoke("deckNamesAndIds")
        if name in existing:
            return {"deck": name, "deck_id": existing[name], "created": False, "note": "Already existed; unchanged."}
        return {"deck": name, "deck_id": await anki.invoke("createDeck", deck=name), "created": True}

    @tool(ADD, "add")
    async def anki_add_notes(
        deck: str,
        notes: list[dict[str, str]],
        model: str | None = None,
        tags: list[str] | None = None,
        duplicate_scope: Literal["collection", "deck"] = "collection",
        allow_html: bool = False,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Add notes to an existing deck. Existing notes are never overwritten; duplicates are skipped and reported.

        notes: list of {field: value}, e.g. [{"Front": "hola", "Back": "hello"}]. Field names are matched to the
          note type case-insensitively, and a unique prefix works ("Example" -> "Example sentence").
        model: note type. Default: ANKI_DEFAULT_MODEL, else the note type most used in that deck.
        tags: tags for every note.
        duplicate_scope: "collection" (Anki's default: same first field + same note type anywhere) or "deck".
        allow_html: if false (default), text is HTML-escaped and newlines become <br>.
        dry_run: report what would be added/skipped without writing.
        """
        if not isinstance(notes, list) or not notes:
            raise ToolError("notes must be a non-empty list of {field: value} objects.")
        common = validate_tags(tags)
        items = []
        for i, n in enumerate(notes, start=1):
            if not isinstance(n, dict) or not n:
                raise ToolError(f"notes[{i - 1}] must be a non-empty object of field -> value.")
            first = str(next(iter(n.values())) or "")
            items.append((f"#{i} {first[:60]!r}", n, common))
        return await add_items(deck, model, items, allow_html, duplicate_scope, dry_run)

    @tool(ADD, "add")
    async def anki_import_file(
        path: str,
        deck: str,
        model: str | None = None,
        columns: list[str] | None = None,
        has_header: bool | None = None,
        delimiter: Literal["auto", "tab", "comma", "semicolon", "pipe"] = "auto",
        tags: list[str] | None = None,
        tag_rules: list[dict[str, Any]] | None = None,
        default_tag: str | None = None,
        duplicate_scope: Literal["collection", "deck"] = "collection",
        allow_html: bool = False,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Import a .txt/.tsv/.csv file into an existing deck, one note per row.

        Columns map to fields: from `columns` (e.g. ["Front", "Back", "tags"]; "" skips a column, "tags" means
        space-separated tags), else from a header row, else in the note type's field order. has_header: None = auto
        (first row equals field names). Anki "Notes in Plain Text" exports (#separator:/#columns: lines) work.
        tags: added to every row. tag_rules: per-row tags, e.g.
          [{"field": "Front", "starts_with": "GRAMMAR:", "tag": "grammar"}] (also "contains" or "regex";
          "case_sensitive": false by default). default_tag: tag for rows that match no rule.
        Duplicate handling, model default and dry_run work like anki_add_notes.
        """
        p = resolve_path(path)
        parsed = parse_file(p, delimiter)
        rules = validate_tag_rules(tag_rules)
        extra = validate_tags(tags)
        default = validate_tags([default_tag])[0] if default_tag else None
        for r in rules:
            validate_tags([r["tag"]])
        deck_name = await require_deck(deck)
        model_name, model_fields = await resolve_model(model, deck_name)

        rows = parsed.rows
        if columns is None and parsed.directives.get("columns"):
            columns = [c.strip() for c in parsed.directives["columns"].split(parsed.delimiter)]
        if has_header is None and rows:
            header_cells = [c for c in rows[0][1] if c and c.lower() != "tags"]
            try:
                has_header = bool(header_cells) and bool(map_keys(header_cells, model_fields))
            except ToolError:
                has_header = False
        if has_header:
            if columns is None:
                columns = rows[0][1]
            rows = rows[1:]
        if columns is None:
            columns = list(model_fields)
        if not isinstance(columns, list) or not all(isinstance(c, str) for c in columns):
            raise ToolError("columns must be a list of strings.")
        field_cols = [c for c in columns if c.strip() and c.strip().lower() != "tags"]
        mapping = map_keys(field_cols, model_fields)
        rule_fields = []  # each rule's field, resolved to the note type's real field name
        for r in rules:
            target = map_keys([r["field"]], model_fields)[r["field"]]
            if target not in mapping.values():
                raise ToolError(f"tag_rules field {r['field']!r} isn't one of the imported columns {field_cols}.")
            rule_fields.append(target)

        items, row_errors = [], []
        for lineno, cells in rows:
            while len(cells) > len(columns) and not cells[-1]:
                cells = cells[:-1]
            if len(cells) > len(columns):
                row_errors.append({"line": lineno, "error": f"{len(cells)} columns, expected at most {len(columns)}"})
                continue
            cells = cells + [""] * (len(columns) - len(cells))
            fields: dict[str, str] = {}
            row_tags = list(extra)
            for col, val in zip(columns, cells):
                c = col.strip()
                if not c:
                    continue
                if c.lower() == "tags" and "tags" not in {f.lower() for f in model_fields}:
                    row_tags += [t for t in val.split() if t]
                elif val:
                    fields[c] = val
            by_field = {mapping[k]: v for k, v in fields.items()}
            matched = [r["tag"] for r, f in zip(rules, rule_fields) if match_rule(r, by_field.get(f, ""))]
            row_tags += matched or ([default] if default else [])
            if not fields:
                row_errors.append({"line": lineno, "error": "empty row"})
                continue
            first = next(iter(fields.values()))
            items.append((f"line {lineno} {first[:60]!r}", fields, list(dict.fromkeys(row_tags))))
        if not items:
            raise ToolError(f"No usable rows in {p.name}. Row errors: {row_errors[:20]}")
        result = await add_items(deck_name, model_name, items, allow_html, duplicate_scope, dry_run)
        result.update(file=str(p), delimiter={"\t": "tab"}.get(parsed.delimiter, parsed.delimiter),
                      header_row=bool(has_header), columns=columns, rows_read=len(rows), row_errors=row_errors)
        return result

    @tool(ADD, "add")
    async def anki_generate_audio(
        query: str,
        source_field: str,
        dest_field: str,
        preset: str | None = None,
        limit: int = 100,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Generate text-to-speech audio with the AwesomeTTS add-on for notes matching an Anki search.
        Only notes whose dest_field is empty are processed; nothing is overwritten. Needs the bridge add-on.

        source_field: field whose text is spoken. dest_field: field that receives [sound:...].
        preset: an AwesomeTTS preset name (or "group:<name>"); default = the voice last used in AwesomeTTS.
        Uses your AwesomeTTS service, so paid services count against your quota.
        """
        if not isinstance(query, str) or not query.strip():
            raise ToolError("query must be a non-empty Anki search string.")
        if not 1 <= limit <= MAX_AUDIO_NOTES:
            raise ToolError(f"limit must be between 1 and {MAX_AUDIO_NOTES}.")
        for label, val in (("source_field", source_field), ("dest_field", dest_field)):
            if not isinstance(val, str) or not val.strip():
                raise ToolError(f"{label} must be a non-empty field name.")
        if source_field == dest_field:
            raise ToolError("source_field and dest_field must differ.")
        ids = await anki.invoke("findNotes", query=query.strip())
        infos = [n for n in (await anki.invoke("notesInfo", notes=ids) if ids else []) if n]
        eligible, skipped = [], []
        for n in infos:
            f = n["fields"]
            if source_field not in f or dest_field not in f:
                skipped.append({"note_id": n["noteId"], "reason": f"note type {n['modelName']!r} lacks those fields"})
            elif f[dest_field]["value"].strip():
                skipped.append({"note_id": n["noteId"], "reason": f"{dest_field!r} already filled"})
            elif not f[source_field]["value"].strip():
                skipped.append({"note_id": n["noteId"], "reason": f"{source_field!r} is empty"})
            else:
                eligible.append({"note_id": n["noteId"], "text": f[source_field]["value"]})
        summary: dict[str, Any] = {"query": query, "matched": len(ids), "eligible": len(eligible[:limit]),
                                   "over_limit": max(0, len(eligible) - limit), "skipped": skipped,
                                   "source_field": source_field, "dest_field": dest_field, "dry_run": dry_run}
        eligible = eligible[:limit]
        if dry_run or not eligible:
            summary["would_generate" if dry_run else "generated"] = eligible
            return summary
        summary["result"] = await bridge.call(
            "generate", timeout=min(60.0 + 15.0 * len(eligible), 1000.0), note_ids=[e["note_id"] for e in eligible],
            source_field=source_field, dest_field=dest_field, preset=preset)
        return summary

    @tool(READ, "read")
    async def anki_tts_status() -> dict[str, Any]:
        """AwesomeTTS details via the bridge add-on: version, preset/group names, last used service and fields.
        (Never returns voice options or API keys.)"""
        return await bridge.call("tts_status")

    @tool(ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True), "add")
    async def anki_sync() -> dict[str, Any]:
        """Sync the collection with AnkiWeb (requires being logged in to AnkiWeb in Anki)."""
        await anki.invoke("sync", timeout=300.0)
        return {"synced": True, "note": "Sync finished. Sync your other devices to pull the changes."}

    # ---------- change (preview -> confirm) ----------

    @tool(CHANGE, "change")
    async def anki_update_notes(
        updates: list[dict[str, Any]],
        allow_html: bool = False,
        confirm_token: str | None = None,
    ) -> dict[str, Any]:
        """Edit existing notes' fields and/or tags. Two-step: without confirm_token it returns a before/after
        preview and a token; call again with the same arguments + confirm_token to apply (notes are backed up first).

        updates: [{"note_id": 123, "fields": {"Back": "new text"}, "add_tags": ["x"], "remove_tags": ["y"]}]
          Only the listed fields change; "" clears a field (except the first field).
        """
        if not isinstance(updates, list) or not updates:
            raise ToolError("updates must be a non-empty list.")
        if len(updates) > MAX_EDIT_NOTES:
            raise ToolError(f"Too many updates; max {MAX_EDIT_NOTES}.")
        ids = []
        for i, u in enumerate(updates):
            if not isinstance(u, dict) or not isinstance(u.get("note_id"), int):
                raise ToolError(f"updates[{i}] needs an integer note_id.")
            unknown = set(u) - {"note_id", "fields", "add_tags", "remove_tags"}
            if unknown:
                raise ToolError(f"updates[{i}] has unknown keys {sorted(unknown)}.")
            ids.append(u["note_id"])
        if len(set(ids)) != len(ids):
            raise ToolError("Each note_id may appear only once.")
        snaps = {s["note_id"]: s for s in await snapshot(ids)}
        plan = []
        for u in updates:
            snap = snaps[u["note_id"]]
            fields_in = u.get("fields") or {}
            if not isinstance(fields_in, dict):
                raise ToolError(f"note {u['note_id']}: fields must be an object.")
            mapping = map_keys(list(fields_in), list(snap["fields"])) if fields_in else {}
            first = list(snap["fields"])[0]
            changes = {}
            for key, val in fields_in.items():
                new, old = field_value(val, allow_html), snap["fields"][mapping[key]]
                if new != old:
                    changes[mapping[key]] = {"before": old, "after": new}
            if first in changes and not changes[first]["after"]:
                raise ToolError(f"note {u['note_id']}: the first field ({first!r}) can't be empty.")
            add = [t for t in validate_tags(u.get("add_tags")) if t not in snap["tags"]]
            remove = [t for t in validate_tags(u.get("remove_tags")) if t in snap["tags"]]
            if changes or add or remove:
                plan.append({**brief(snap), "field_changes": changes, "add_tags": add, "remove_tags": remove})
        if not plan:
            return {"changed": 0, "note": "Nothing to change: the notes already have these values."}
        payload = {"plan": plan, "before": [snaps[p["note_id"]] for p in plan]}
        if confirm_token is None:
            return confirm.preview("update_notes", payload, {"preview": plan, "notes_to_change": len(plan)})
        confirm.check("update_notes", payload, confirm_token)

        backup = write_backup(settings.backup_dir, "update-notes", payload)
        actions = []
        for p in plan:
            if p["field_changes"]:
                actions.append({"action": "updateNoteFields", "version": API_VERSION, "params": {
                    "note": {"id": p["note_id"], "fields": {f: c["after"] for f, c in p["field_changes"].items()}}}})
            for act, key in (("addTags", "add_tags"), ("removeTags", "remove_tags")):
                if p[key]:
                    actions.append({"action": act, "version": API_VERSION,
                                    "params": {"notes": [p["note_id"]], "tags": " ".join(p[key])}})
        results = await anki.invoke("multi", timeout=120.0, actions=actions)
        errors = [r["error"] for r in results if isinstance(r, dict) and r.get("error")]
        after = {s["note_id"]: s for s in await snapshot([p["note_id"] for p in plan])}
        not_applied = []
        for p in plan:
            a = after[p["note_id"]]
            bad = [f for f, c in p["field_changes"].items() if a["fields"][f] != c["after"]]
            bad += [f"+{t}" for t in p["add_tags"] if t not in a["tags"]] + [f"-{t}" for t in p["remove_tags"] if t in a["tags"]]
            if bad:
                not_applied.append({"note_id": p["note_id"], "not_applied": bad})
        reply = {"changed": len(plan) - len(not_applied), "backup": backup, "errors": errors, "not_applied": not_applied}
        if not_applied:
            reply["hint"] = "Close the note in Anki's Browse window/editor and try again."
        return reply

    @tool(CHANGE, "change")
    async def anki_move_notes(
        target_deck: str,
        note_ids: list[int] | None = None,
        query: str | None = None,
        confirm_token: str | None = None,
    ) -> dict[str, Any]:
        """Move notes (all their cards, keeping review history) to another existing deck. Give note_ids OR an
        Anki search query. Two-step: preview + token, then call again with confirm_token."""
        target = await require_deck(target_deck)
        ids = await resolve_note_ids(note_ids, query)
        snaps = await snapshot(ids)
        moving = {c: d for s in snaps for c, d in s["cards"].items() if d != target}
        if not moving:
            return {"moved_cards": 0, "note": f"All cards are already in {target!r}."}
        payload = {"target": target, "ids": ids, "cards": moving}
        if confirm_token is None:
            return confirm.preview("move_notes", payload, {
                "target_deck": target, "notes": len(ids), "cards_to_move": len(moving),
                "from_decks": dict(Counter(moving.values())),
                "preview": [brief(s) for s in snaps[:100]], "preview_truncated": len(snaps) > 100})
        confirm.check("move_notes", payload, confirm_token)
        backup = write_backup(settings.backup_dir, "move-notes", payload)
        await anki.invoke("changeDeck", cards=[int(c) for c in moving], deck=target)
        return {"moved_cards": len(moving), "target_deck": target, "backup": backup}

    @tool(CHANGE, "change")
    async def anki_rename_deck(name: str, new_name: str, confirm_token: str | None = None) -> dict[str, Any]:
        """Rename a deck (subdecks follow; cards, history and options are kept). "A::B" nests it under A.
        Two-step: preview + token, then call again with confirm_token. Needs the bridge add-on."""
        name = await require_deck(name)
        new_name = validate_deck_name(new_name)
        if new_name == name:
            return {"renamed": False, "note": "Same name; nothing to do."}
        if new_name in await deck_names() and new_name.lower() != name.lower():
            raise ToolError(f"A deck named {new_name!r} already exists.")
        if new_name.startswith(name + "::"):
            raise ToolError("Can't move a deck inside itself.")
        tree, note_ids, n_cards = await deck_tree(name)
        payload = {"name": name, "new_name": new_name, "tree": tree}
        if confirm_token is None:
            return confirm.preview("rename_deck", payload, {
                "rename": {d: new_name + d[len(name):] for d in tree}, "notes": len(note_ids), "cards": n_cards})
        confirm.check("rename_deck", payload, confirm_token)
        write_backup(settings.backup_dir, "rename-deck", payload)
        return {"renamed": True, **await bridge.call("rename_deck", name=name, new_name=new_name)}

    @tool(CHANGE, "change")
    async def anki_rename_profile(new_name: str, confirm_token: str | None = None) -> dict[str, Any]:
        """Rename the current Anki profile (e.g. the default "User 1"). Anki briefly closes and reopens the
        collection, like File -> Switch Profile, and syncs if sync-on-open/close is enabled. Cards, history,
        add-ons and the AnkiWeb login are kept. Two-step: preview + token. Needs the bridge add-on."""
        if not isinstance(new_name, str) or not new_name.strip():
            raise ToolError("new_name must be a non-empty string.")
        new_name = new_name.strip()
        if len(new_name) > 60 or any(c in new_name for c in '\\/:*?"<>|') or any(ord(c) < 32 for c in new_name) \
                or new_name.startswith(".") or new_name.lower() == "addons21":
            raise ToolError('Invalid profile name: max 60 characters, no \\ / : * ? " < > | or control characters.')
        info = await bridge.call("profile_info")
        current = info["current"]
        if new_name == current:
            return {"renamed": False, "note": f"The profile is already called {current!r}."}
        if any(p.lower() == new_name.lower() for p in info["profiles"] if p != current):
            raise ToolError(f"A profile named {new_name!r} already exists.")
        payload = {"current": current, "new_name": new_name}
        if confirm_token is None:
            return confirm.preview("rename_profile", payload, {
                "current_profile": current, "new_profile_name": new_name, "all_profiles": info["profiles"],
                "what_happens": "Anki closes the collection, renames the profile, and reopens it (a few seconds). "
                                "Close Anki's Browse/editing windows first."})
        confirm.check("rename_profile", payload, confirm_token)
        await bridge.call("rename_profile", new_name=new_name, expected_current=current)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 120
        await asyncio.sleep(2.0)
        state = None
        while loop.time() < deadline:
            try:
                info = await bridge.call("profile_info", timeout=5.0, _retry=False)
                state = info["last_rename"].get("state")
                if state in ("done", "error"):
                    await anki.invoke("version", timeout=5.0, _retry=False)
                    break
            except ToolError:
                pass  # Anki is reloading
            await asyncio.sleep(1.5)
        else:
            raise ToolError("Anki didn't finish reopening within 120s. Check the Anki window, then run anki_status.")
        if state == "error":
            raise ToolError(f"Profile rename failed: {info['last_rename'].get('error')}. "
                            f"Anki reopened profile {info['current']!r}; nothing was lost.")
        return {"renamed": True, "old_name": current, "new_name": info["current"]}

    # ---------- delete (preview -> confirm) ----------

    @tool(DELETE, "delete")
    async def anki_delete_notes(
        note_ids: list[int] | None = None,
        query: str | None = None,
        confirm_token: str | None = None,
    ) -> dict[str, Any]:
        """Delete notes with all their cards and review history. Give note_ids OR an Anki search query.
        Two-step: preview + token, then call again with confirm_token. A JSON backup is written first."""
        ids = await resolve_note_ids(note_ids, query)
        snaps = await snapshot(ids)
        payload = {"ids": ids, "before": snaps}
        if confirm_token is None:
            return confirm.preview("delete_notes", payload, {
                "notes_to_delete": len(ids), "cards_to_delete": sum(len(s["cards"]) for s in snaps),
                "preview": [brief(s) for s in snaps[:100]], "preview_truncated": len(snaps) > 100})
        confirm.check("delete_notes", payload, confirm_token)
        backup = write_backup(settings.backup_dir, "delete-notes", payload)
        await anki.invoke("deleteNotes", notes=ids)
        remaining = [n["noteId"] for n in await anki.invoke("notesInfo", notes=ids) if n]
        return {"deleted": len(ids) - len(remaining), "still_present": remaining, "backup": backup}

    @tool(DELETE, "delete")
    async def anki_delete_deck(name: str, confirm_token: str | None = None) -> dict[str, Any]:
        """Delete a deck, its subdecks and all their cards. Two-step: preview + token, then call again with
        confirm_token. The deck is first exported (with review history) to an .apkg in the backup folder, which
        can be re-imported via Anki's File -> Import."""
        name = await require_deck(name)
        if name == "Default":
            raise ToolError("The Default deck can't be deleted.")
        tree, note_ids, n_cards = await deck_tree(name)
        payload = {"name": name, "tree": tree, "note_ids": note_ids, "cards": n_cards}
        if confirm_token is None:
            return confirm.preview("delete_deck", payload, {
                "decks_to_delete": tree, "notes_affected": len(note_ids), "cards_to_delete": n_cards,
                "sample_notes": [brief(s) for s in await snapshot(note_ids[:30])]})
        confirm.check("delete_deck", payload, confirm_token)
        apkg = None
        if note_ids:
            apkg = backup_path(settings.backup_dir, "deck", name, ".apkg")
            ok = await anki.invoke("exportPackage", timeout=300.0, deck=name, path=str(apkg), includeSched=True)
            if not ok or not apkg.is_file() or apkg.stat().st_size == 0:
                raise ToolError(f"Backup export to {apkg} failed, so the deck was NOT deleted.")
        json_backup = write_backup(settings.backup_dir, "delete-deck", {**payload, "notes": await snapshot(note_ids)})
        await anki.invoke("deleteDecks", decks=[name], cardsToo=True)
        still = [d for d in await deck_names() if d in tree]
        return {"deleted_decks": [d for d in tree if d not in still], "still_present": still, "cards_deleted": n_cards,
                "backup_apkg": str(apkg) if apkg else None, "backup_json": json_backup}

    return mcp


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s anki-mcp-server: %(message)s")
    try:
        settings = Settings.from_env()
    except ValueError as e:
        sys.exit(f"anki-mcp-server: {e}")
    create_server(settings).run("stdio")


if __name__ == "__main__":
    main()
