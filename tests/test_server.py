from __future__ import annotations

import json

import pytest
from mcp.client.client import Client

from anki_mcp_server.config import Settings
from anki_mcp_server.server import create_server

from .mock_anki import FakeAnki, serve

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def fake():
    return FakeAnki()


@pytest.fixture
def settings(fake, tmp_path):
    a, b = serve(fake, "anki"), serve(fake, "bridge")
    yield Settings(
        anki_connect_url=f"http://127.0.0.1:{a.server_port}",
        bridge_url=f"http://127.0.0.1:{b.server_port}",
        auto_launch=False,
        backup_dir=tmp_path / "backups",
    )
    a.shutdown()
    b.shutdown()


class Session:
    def __init__(self, client: Client):
        self.client = client

    async def call(self, tool: str, /, **args):
        res = await self.client.call_tool(tool, args)
        text = res.content[0].text if res.content else ""
        try:
            data = json.loads(text)
        except ValueError:
            data = text
        return res.is_error, data

    async def ok(self, tool: str, /, **args):
        is_error, data = await self.call(tool, **args)
        assert not is_error, data
        return data

    async def err(self, tool: str, /, **args) -> str:
        is_error, data = await self.call(tool, **args)
        assert is_error, data
        return str(data)


@pytest.fixture
async def s(settings):
    async with Client(create_server(settings)) as client:
        yield Session(client)


async def seed(s: Session, deck="Spanish"):
    await s.ok("anki_create_deck", name=deck)
    return await s.ok("anki_add_notes", deck=deck, model="Basic",
                      notes=[{"Front": "hola", "Back": "hello"}, {"Front": "adiós", "Back": "bye"}], tags=["es"])


# ---------- read / add ----------

async def test_status(s):
    st = await s.ok("anki_status")
    assert st["connected"] and st["anki_connect_version"] == 6
    assert st["note_types"]["Vocab"] == ["Word", "Meaning", "Example sentence"]
    assert st["profile"] == "User 1" and st["mode"] == "full"


async def test_create_deck_idempotent(s):
    assert (await s.ok("anki_create_deck", name="A::B"))["created"] is True
    assert (await s.ok("anki_create_deck", name="A::B"))["created"] is False
    assert "empty component" in await s.err("anki_create_deck", name="A::")


async def test_add_notes_duplicates_and_html(s, fake):
    r = await seed(s)
    assert r["counts"] == {"added": 2, "skipped_duplicates": 0, "failed": 0}
    r = await s.ok("anki_add_notes", deck="Spanish", notes=[
        {"Front": "hola", "Back": "again"},            # duplicate in collection
        {"Front": "gato", "Back": "cat <b>&</b>\nline2"},
        {"Front": "gato", "Back": "same batch"},       # duplicate in batch
    ])
    assert r["model"] == "Basic"  # inferred from the deck
    assert r["counts"] == {"added": 1, "skipped_duplicates": 2, "failed": 0}
    gato = next(n for n in fake.notes.values() if n["fields"]["Front"] == "gato")
    assert gato["fields"]["Back"] == "cat &lt;b&gt;&amp;&lt;/b&gt;<br>line2"


async def test_add_notes_dry_run_writes_nothing(s, fake):
    await s.ok("anki_create_deck", name="Spanish")
    r = await s.ok("anki_add_notes", deck="Spanish", model="Basic", notes=[{"Front": "x", "Back": "y"}], dry_run=True)
    assert r["counts"]["would_add"] == 1 and not fake.notes


async def test_add_notes_validation(s):
    await s.ok("anki_create_deck", name="Spanish")
    assert "does not exist" in await s.err("anki_add_notes", deck="Nope", model="Basic", notes=[{"Front": "x"}])
    assert "doesn't match any field" in await s.err("anki_add_notes", deck="Spanish", model="Basic", notes=[{"Bogus": "x"}])
    assert "single words" in await s.err("anki_add_notes", deck="Spanish", model="Basic", notes=[{"Front": "x"}], tags=["two words"])
    assert "Pass `model`" in await s.err("anki_add_notes", deck="Spanish", notes=[{"Front": "x"}])  # empty deck, no default


async def test_import_tsv_with_header_rules_and_prefix_fields(s, fake, tmp_path):
    await s.ok("anki_create_deck", name="IELTS")
    f = tmp_path / "vocab.txt"
    f.write_text("Word\tMeaning\tExample\n"
                 "resilient\table to recover\tShe is resilient.\n"
                 "GRAMMAR NOTE: present perfect\thave + pp\tI have lived here.\n"
                 "too\tmany\tcolumns\there\n"
                 "flip side\tother aspect\t\n", encoding="utf-8")
    rules = [{"field": "Word", "starts_with": "grammar note:", "tag": "grammar"}]
    r = await s.ok("anki_import_file", path=str(f), deck="IELTS", model="Vocab", tag_rules=rules, default_tag="vocab", tags=["ielts"])
    assert r["header_row"] is True and r["delimiter"] == "tab"
    assert r["field_mapping"]["Example"] == "Example sentence"
    assert r["counts"]["added"] == 3 and len(r["row_errors"]) == 1 and r["row_errors"][0]["line"] == 4
    tags = {n["fields"]["Word"]: n["tags"] for n in fake.notes.values()}
    assert tags["GRAMMAR NOTE: present perfect"] == ["ielts", "grammar"]
    assert tags["resilient"] == ["ielts", "vocab"]


async def test_import_csv_quoted_with_tags_column(s, fake, tmp_path):
    await s.ok("anki_create_deck", name="Spanish")
    f = tmp_path / "cards.csv"
    f.write_text('hola,"hello, hi",greeting es\nperro,dog,animal\n', encoding="utf-8")
    r = await s.ok("anki_import_file", path=str(f), deck="Spanish", model="Basic", columns=["Front", "Back", "tags"])
    assert r["header_row"] is False and r["delimiter"] == ","
    assert r["counts"]["added"] == 2
    hola = next(n for n in fake.notes.values() if n["fields"]["Front"] == "hola")
    assert hola["fields"]["Back"] == "hello, hi" and hola["tags"] == ["greeting", "es"]


async def test_import_anki_plain_text_export(s, fake, tmp_path):
    await s.ok("anki_create_deck", name="Spanish")
    f = tmp_path / "export.txt"
    f.write_text("#separator:tab\n#html:false\nuno\tone\ndos\ttwo\n", encoding="utf-8")
    r = await s.ok("anki_import_file", path=str(f), deck="Spanish", model="Basic")
    assert r["counts"]["added"] == 2 and r["columns"] == ["Front", "Back"]


async def test_import_rejects_bad_paths(s, tmp_path):
    assert "File not found" in await s.err("anki_import_file", path=str(tmp_path / "nope.txt"), deck="Default")
    (tmp_path / "x.pdf").write_text("x")
    assert "Expected one of" in await s.err("anki_import_file", path=str(tmp_path / "x.pdf"), deck="Default")


async def test_find_and_tags(s):
    await seed(s)
    r = await s.ok("anki_find_notes", query='deck:"Spanish"')
    assert r["total_matches"] == 2 and r["notes"][0]["decks"] == ["Spanish"]
    assert (await s.ok("anki_list_tags"))["tags"] == ["es"]
    assert (await s.ok("anki_open_browser", query="tag:es"))["cards_shown"] == 2


# ---------- preview -> confirm ----------

async def test_update_notes_preview_confirm_and_stale_token(s, fake, settings):
    await seed(s)
    nid = next(i for i, n in fake.notes.items() if n["fields"]["Front"] == "hola")
    upd = [{"note_id": nid, "fields": {"back": "hello!"}, "add_tags": ["edited"]}]
    p = await s.ok("anki_update_notes", updates=upd)
    assert p["preview"][0]["field_changes"] == {"Back": {"before": "hello", "after": "hello!"}}
    assert fake.notes[nid]["fields"]["Back"] == "hello"  # preview changed nothing

    assert "doesn't match" in await s.err("anki_update_notes", updates=upd, confirm_token="0" * 16)
    other = [{"note_id": nid, "fields": {"Back": "something else"}}]
    assert "doesn't match" in await s.err("anki_update_notes", updates=other, confirm_token=p["confirm_token"])

    fake.notes[nid]["fields"]["Back"] = "changed meanwhile"  # stale preview
    assert "doesn't match" in await s.err("anki_update_notes", updates=upd, confirm_token=p["confirm_token"])

    p = await s.ok("anki_update_notes", updates=upd)
    r = await s.ok("anki_update_notes", updates=upd, confirm_token=p["confirm_token"])
    assert r["changed"] == 1 and r["not_applied"] == []
    assert fake.notes[nid]["fields"]["Back"] == "hello!" and "edited" in fake.notes[nid]["tags"]
    backup = json.loads(open(r["backup"]).read())
    assert backup["before"][0]["fields"]["Back"] == "changed meanwhile"
    assert (await s.ok("anki_update_notes", updates=upd))["changed"] == 0


async def test_move_rename_delete_flow(s, fake):
    await seed(s)
    await s.ok("anki_create_deck", name="Archive")
    p = await s.ok("anki_move_notes", target_deck="Archive", query="Front:hola")
    assert p["cards_to_move"] == 1 and p["from_decks"] == {"Spanish": 1}
    await s.ok("anki_move_notes", target_deck="Archive", query="Front:hola", confirm_token=p["confirm_token"])
    assert {n["fields"]["Front"]: n["deck"] for n in fake.notes.values()} == {"hola": "Archive", "adiós": "Spanish"}

    p = await s.ok("anki_rename_deck", name="Archive", new_name="Old::Archive")
    assert p["rename"] == {"Archive": "Old::Archive"}
    await s.ok("anki_rename_deck", name="Archive", new_name="Old::Archive", confirm_token=p["confirm_token"])
    assert "Old::Archive" in fake.decks and "Archive" not in fake.decks

    p = await s.ok("anki_delete_notes", query="Front:adiós")
    assert p["notes_to_delete"] == 1
    r = await s.ok("anki_delete_notes", query="Front:adiós", confirm_token=p["confirm_token"])
    assert r["deleted"] == 1 and len(fake.notes) == 1

    p = await s.ok("anki_delete_deck", name="Old")
    assert p["decks_to_delete"] == ["Old", "Old::Archive"] and p["cards_to_delete"] == 1
    r = await s.ok("anki_delete_deck", name="Old", confirm_token=p["confirm_token"])
    assert r["deleted_decks"] == ["Old", "Old::Archive"] and r["backup_apkg"].endswith(".apkg")
    assert not fake.notes
    assert "Default deck can't be deleted" in await s.err("anki_delete_deck", name="Default")


async def test_rename_profile_validation(s):
    assert "Invalid profile name" in await s.err("anki_rename_profile", new_name="a/b")
    assert (await s.ok("anki_rename_profile", new_name="User 1"))["renamed"] is False
    p = await s.ok("anki_rename_profile", new_name="Alex")
    assert p["current_profile"] == "User 1" and "confirm_token" in p


# ---------- modes / config ----------

async def test_read_only_and_no_delete_modes(settings):
    from dataclasses import replace
    async with Client(create_server(replace(settings, read_only=True))) as c:
        names = {t.name for t in (await c.list_tools()).tools}
    assert names == {"anki_status", "anki_find_notes", "anki_list_tags", "anki_open_browser", "anki_tts_status"}
    async with Client(create_server(replace(settings, allow_delete=False))) as c:
        names = {t.name for t in (await c.list_tools()).tools}
    assert "anki_update_notes" in names and not names & {"anki_delete_notes", "anki_delete_deck"}


async def test_tool_annotations(s):
    tools = {t.name: t for t in (await s.client.list_tools()).tools}
    assert tools["anki_find_notes"].annotations.read_only_hint is True
    assert tools["anki_delete_deck"].annotations.destructive_hint is True
    assert tools["anki_add_notes"].annotations.destructive_hint is False


async def test_connection_refused_message(tmp_path):
    st = Settings(anki_connect_url="http://127.0.0.1:9", bridge_url="http://127.0.0.1:9", auto_launch=False,
                  backup_dir=tmp_path)
    async with Client(create_server(st)) as c:
        res = await c.call_tool("anki_status", {})
    assert res.is_error and "AnkiConnect add-on (code 2055492159)" in res.content[0].text


def test_only_loopback_urls_allowed():
    with pytest.raises(ValueError):
        Settings(anki_connect_url="http://example.com:8765")
    with pytest.raises(ValueError):
        Settings(bridge_url="http://192.168.1.5:8766")
