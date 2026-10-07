"""In-memory fakes of AnkiConnect (API v6) and the Anki MCP Bridge add-on, served on 127.0.0.1."""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

MODELS = {"Basic": ["Front", "Back"], "Vocab": ["Word", "Meaning", "Example sentence"]}


class FakeAnki:
    def __init__(self) -> None:
        self.decks: dict[str, int] = {"Default": 1}
        self.notes: dict[int, dict[str, Any]] = {}  # id -> {model, fields, tags, deck}
        self.next_id = 1000
        self.profile = "User 1"
        self.calls: list[str] = []

    # ---- helpers ----
    def add_deck(self, name: str) -> int:
        parts = name.split("::")
        for i in range(1, len(parts) + 1):  # like Anki, create missing parent decks
            self.decks.setdefault("::".join(parts[:i]), len(self.decks) + 1)
        return self.decks[name]

    def _dup_error(self, n: dict) -> str | None:
        first = MODELS[n["modelName"]][0]
        value = n["fields"].get(first, "")
        if not value:
            return "cannot create note because it is empty"
        if n["deckName"] not in self.decks:
            return f"deck was not found: {n['deckName']}"
        scope = n.get("options", {}).get("duplicateScope")
        for x in self.notes.values():
            if x["model"] == n["modelName"] and x["fields"][first] == value and (scope != "deck" or x["deck"] == n["deckName"]):
                return "cannot create note because it is a duplicate"
        return None

    def _find(self, query: str) -> list[int]:
        q = query.strip()
        ids = list(self.notes)
        for m in re.finditer(r'(-?)deck:"((?:[^"\\]|\\.)*)"|(-?)deck:(\S+)|nid:(\d+)|tag:(\S+)|(\w+):([^\s"]+)', q):
            neg1, deck, neg2, deck2, nid, tag, field, value = m.groups()
            neg = bool(neg1 or neg2)
            deck = deck if deck is not None else deck2
            if deck is not None:
                if deck == "*":
                    continue
                # unescaped "*" is a wildcard; "\*" a literal star
                pat = "^" + "".join(".*" if part == "*" else re.escape(part.replace("\\", ""))
                                    for part in re.split(r"(?<!\\)(\*)", deck)) + "$"
                def in_deck(name: str) -> bool:
                    return bool(re.match(pat, name)) or (not deck.endswith("*") and bool(re.match(pat[:-1] + "::", name)))
                ids = [i for i in ids if in_deck(self.notes[i]["deck"]) != neg]
            elif nid:
                ids = [i for i in ids if i == int(nid)]
            elif tag:
                ids = [i for i in ids if tag in self.notes[i]["tags"]]
            elif field:
                pat = "^" + re.escape(value).replace(r"\*", ".*") + "$"
                ids = [i for i in ids if re.match(pat, self.notes[i]["fields"].get(field, ""), re.I)]
        return sorted(ids)

    # ---- AnkiConnect ----
    def run(self, action: str, p: dict) -> Any:
        self.calls.append(action)
        if action == "version":
            return 6
        if action == "deckNames":
            return list(self.decks)
        if action == "deckNamesAndIds":
            return dict(self.decks)
        if action == "modelNamesAndIds":
            return {m: i for i, m in enumerate(MODELS)}
        if action == "modelFieldNames":
            return MODELS[p["modelName"]]
        if action == "getTags":
            return sorted({t for n in self.notes.values() for t in n["tags"]})
        if action == "createDeck":
            return self.add_deck(p["deck"])
        if action == "canAddNotesWithErrorDetail":
            return [{"canAdd": self._dup_error(n) is None, "error": self._dup_error(n)} for n in p["notes"]]
        if action == "addNote":
            n = p["note"]
            err = self._dup_error(n)
            if err:
                raise Exception(err)
            self.next_id += 1
            self.notes[self.next_id] = {"model": n["modelName"], "deck": n["deckName"], "tags": list(n["tags"]),
                                        "fields": {f: n["fields"].get(f, "") for f in MODELS[n["modelName"]]}}
            return self.next_id
        if action == "findNotes":
            return self._find(p["query"])
        if action == "findCards":
            return [i * 10 for i in self._find(p["query"])]
        if action == "notesInfo":
            out = []
            for i in p["notes"]:
                n = self.notes.get(i)
                out.append({} if n is None else {
                    "noteId": i, "modelName": n["model"], "tags": list(n["tags"]), "cards": [i * 10],
                    "fields": {k: {"value": v, "order": o} for o, (k, v) in enumerate(n["fields"].items())}})
            return out
        if action == "cardsInfo":
            return [{"cardId": c, "deckName": self.notes[c // 10]["deck"]} for c in p["cards"] if c // 10 in self.notes]
        if action == "guiBrowse":
            return [i * 10 for i in self._find(p["query"])]
        if action == "sync":
            return None
        if action == "updateNoteFields":
            n = self.notes[p["note"]["id"]]
            for k, v in p["note"]["fields"].items():
                if k in n["fields"]:
                    n["fields"][k] = v
            return None
        if action == "addTags":
            for i in p["notes"]:
                self.notes[i]["tags"] += [t for t in p["tags"].split() if t not in self.notes[i]["tags"]]
            return None
        if action == "removeTags":
            for i in p["notes"]:
                self.notes[i]["tags"] = [t for t in self.notes[i]["tags"] if t not in p["tags"].split()]
            return None
        if action == "changeDeck":
            self.add_deck(p["deck"])
            for c in p["cards"]:
                self.notes[c // 10]["deck"] = p["deck"]
            return None
        if action == "deleteNotes":
            for i in p["notes"]:
                self.notes.pop(i, None)
            return None
        if action == "deleteDecks":
            for d in p["decks"]:
                for name in [x for x in self.decks if x == d or x.startswith(d + "::")]:
                    del self.decks[name]
                    for i in [i for i, n in self.notes.items() if n["deck"] == name]:
                        del self.notes[i]
            return None
        if action == "storeMediaFile":
            self.media = getattr(self, "media", {})
            name = p["filename"]
            self.media[name] = p["data"]
            return name
        if action == "getDeckConfig":
            return {"id": 7, "name": "My preset"} if p["deck"] in self.decks else False
        if action == "setDeckConfigId":
            self.deck_conf = getattr(self, "deck_conf", {})
            for d in p["decks"]:
                self.deck_conf[d] = p["configId"]
            return True
        if action == "exportPackage":
            with open(p["path"], "wb") as f:
                f.write(b"PK fake apkg")
            return True
        if action == "multi":
            out = []
            for sub in p["actions"]:
                try:
                    out.append({"result": self.run(sub["action"], sub.get("params", {})), "error": None})
                except Exception as e:  # noqa: BLE001
                    out.append({"result": None, "error": str(e)})
            return out
        raise Exception("unsupported action")

    # ---- bridge ----
    def bridge(self, action: str, p: dict) -> Any:
        if action == "info":
            return {"bridge_version": "test", "profile": self.profile, "awesometts": None,
                    "features": ["rename_deck", "rename_profile"]}
        if action == "profile_info":
            return {"current": self.profile, "profiles": [self.profile], "last_rename": {"state": "none"}}
        if action == "rename_deck":
            old, new = p["name"], p["new_name"]
            for name in [d for d in list(self.decks) if d == old or d.startswith(old + "::")]:
                self.decks.pop(name)
                self.add_deck(new + name[len(old):])
                for n in self.notes.values():
                    if n["deck"] == name:
                        n["deck"] = new + name[len(old):]
            return {"old_name": old, "new_name": new}
        raise Exception(f"unknown action {action!r}")


def serve(fake: FakeAnki, kind: str) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a: Any) -> None:
            pass

        def do_POST(self) -> None:
            req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            try:
                if kind == "bridge":
                    if self.headers.get("X-Anki-MCP") != "1":
                        raise Exception("forbidden")
                    result = fake.bridge(req["action"], req.get("params") or {})
                else:
                    result = fake.run(req["action"], req.get("params") or {})
                body = {"result": result, "error": None}
            except Exception as e:  # noqa: BLE001
                body = {"result": None, "error": str(e)}
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
