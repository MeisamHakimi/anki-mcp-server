# anki-mcp-server

An [MCP](https://modelcontextprotocol.io) server that lets Claude (or any MCP client) work with your **Anki** flashcards: create decks, add notes, import TSV/CSV files, search, edit, move, rename and delete, and sync to AnkiWeb so the changes reach AnkiDroid / AnkiMobile.

It talks to Anki Desktop through the [AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on. An optional companion add-on adds deck/profile renaming and text-to-speech audio via [AwesomeTTS](https://ankiweb.net/shared/info/1436550454).

> "Import `~/Downloads/spanish.csv` into my Spanish deck. Do a dry run first."
> "Find every card tagged `verbs` that has no example sentence."
> "Move all notes tagged `grammar` into a deck called Spanish::Grammar."
> "Add pronunciation audio to the notes I added today, then sync."

## Safety

Your collection is personal data you've built over years, so this server is cautious by default:

- **Local only.** It uses the stdio transport (no network listener) and only talks to `127.0.0.1`. URLs pointing anywhere else are rejected, and proxy environment variables are ignored.
- **Adding never overwrites.** Notes are added with `allowDuplicate=false`. Duplicates are reported back as skipped, and `dry_run` previews any add or import.
- **Changes and deletions are two-step.** A tool that edits, moves, renames or deletes first returns a **preview** and a `confirm_token`, without changing anything. The change only runs when the tool is called again with that token. The token is rejected if the arguments differ, if the notes changed since the preview, or if the server restarted. The server instructs the model to get your explicit approval before confirming.
- **Backups before every change.** Affected notes are written as JSON to `~/.anki-mcp-server/backups/`. A deck is exported as an `.apkg` with review history before it's deleted; restore it with Anki → File → Import. (AnkiConnect edits bypass Anki's undo, so these backups are your undo.)
- **Allowlisted actions.** Only the AnkiConnect actions this server needs are used. Note-type, template, media and deck-option changes are never exposed.
- **Modes.** `ANKI_MCP_READ_ONLY=1` exposes only read tools. `ANKI_MCP_ALLOW_DELETE=0` hides the delete tools.
- **Tool annotations.** Every tool is marked read-only or destructive, so MCP clients can ask for confirmation appropriately.

## Requirements

- [Anki Desktop](https://apps.ankiweb.net) 23.10 or newer
- The [AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on: in Anki, go to Tools → Add-ons → Get Add-ons…, enter `2055492159`, then restart Anki
- Python 3.10 or newer, or [uv](https://docs.astral.sh/uv/)

If Anki isn't running, the server starts it in the background and waits for AnkiConnect (macOS, Windows and Linux; see `ANKI_LAUNCH_COMMAND`).

## Install

With uv (no manual install needed; the MCP client runs it on demand):

```bash
uvx --from git+https://github.com/MeisamHakimi/anki-mcp-server anki-mcp-server
```

Or with pip:

```bash
pip install git+https://github.com/MeisamHakimi/anki-mcp-server
```

### Claude Desktop

Settings → Developer → Edit Config, then add the following to `claude_desktop_config.json` and restart Claude:

```json
{
  "mcpServers": {
    "anki": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/MeisamHakimi/anki-mcp-server", "anki-mcp-server"]
    }
  }
}
```

If you installed with pip, use `"command": "anki-mcp-server"` with no args. Use the full path if Claude can't find it; `which anki-mcp-server` shows it.

### Claude Code

```bash
claude mcp add anki --scope user -- uvx --from git+https://github.com/MeisamHakimi/anki-mcp-server anki-mcp-server
```

### Other MCP clients

Run `anki-mcp-server` as a stdio server. Environment variables (below) go in the client's `env` block.

## Optional: Anki MCP Bridge add-on

AnkiConnect can't rename decks or profiles, and AwesomeTTS has no API. The small companion add-on in [`anki_addon/anki_mcp_bridge`](anki_addon/anki_mcp_bridge) adds these features:

| Feature | Tools |
|---|---|
| Rename decks (subdecks, cards and history kept) | `anki_rename_deck` |
| Rename the Anki profile (e.g. "User 1") | `anki_rename_profile` |
| Generate audio with your AwesomeTTS voice; only fills empty fields | `anki_generate_audio`, `anki_tts_status` |

It listens on `127.0.0.1:8766` only and rejects browser requests. It never returns AwesomeTTS settings or API keys.

**Install:**
1. Download `anki_mcp_bridge.ankiaddon` from the [Releases](https://github.com/MeisamHakimi/anki-mcp-server/releases) page, or build it with `python scripts/build_addon.py`.
2. Double-click the file, or use Anki → Tools → Add-ons → Install from file.
3. Restart Anki.

AwesomeTTS support relies on AwesomeTTS internals (tested with 1.89.4), so an AwesomeTTS update can break the audio tools. Everything else is unaffected.

## Tools

| Tool | Kind | What it does |
|---|---|---|
| `anki_status` | read | AnkiConnect version, profile, decks, note types and their fields, available features |
| `anki_find_notes` | read | [Anki search syntax](https://docs.ankiweb.net/searching.html) → notes with fields, tags and decks |
| `anki_list_tags` | read | All tags |
| `anki_open_browser` | read | Opens Anki's Browse window filtered by a search |
| `anki_create_deck` | add | Creates a deck (`Parent::Child` for subdecks); a no-op if it exists |
| `anki_add_notes` | add | Adds notes; duplicates skipped; `dry_run` |
| `anki_import_file` | add | Imports `.txt/.tsv/.csv`: header or `columns` mapping, a `tags` column, `tag_rules`, Anki plain-text exports, `dry_run` |
| `anki_generate_audio` | add | AwesomeTTS audio for notes with an empty audio field (bridge) |
| `anki_tts_status` | read | AwesomeTTS presets and last used voice (bridge) |
| `anki_sync` | add | Syncs with AnkiWeb |
| `anki_update_notes` | change | Edits fields and tags (preview → confirm, backup) |
| `anki_move_notes` | change | Moves notes to another deck (preview → confirm, backup) |
| `anki_rename_deck` | change | Renames a deck (preview → confirm; bridge) |
| `anki_rename_profile` | change | Renames the Anki profile (preview → confirm; bridge) |
| `anki_delete_notes` | delete | Deletes notes (preview → confirm, JSON backup) |
| `anki_delete_deck` | delete | Deletes a deck and its cards (preview → confirm, `.apkg` + JSON backup) |

### Field matching

You can use friendly field names. Matching is case-insensitive, and a unique prefix works: `"example"` maps to a field called `Example sentence`. If you don't pass `model`, adds and imports use `ANKI_DEFAULT_MODEL` or, failing that, the note type most used in the target deck.

### Importing files

```text
word	meaning	example
resilient	able to recover quickly	She is remarkably resilient.
GRAMMAR NOTE: present perfect	have/has + past participle	I have lived here for years.
```

> "Import `~/vocab.txt` into `English::Vocabulary`, tag rows whose word starts with `GRAMMAR NOTE:` as `grammar` and everything else as `vocab`."

This becomes:

```json
{"path": "~/vocab.txt", "deck": "English::Vocabulary",
 "tag_rules": [{"field": "Word", "starts_with": "GRAMMAR NOTE:", "tag": "grammar"}],
 "default_tag": "vocab", "dry_run": true}
```

- **Delimiter:** tab, comma, semicolon or pipe, auto-detected. Tab-separated files are read literally; other delimiters follow CSV quoting rules.
- **Columns:** taken from a header row if there is one (auto-detected when it matches field names), else from `columns`, else in the note type's field order. Use `""` to skip a column and `"tags"` for a space-separated tags column.
- **Anki exports:** "Notes in Plain Text" exports work, including their `#separator:` and `#columns:` lines.
- **Tag rules:** each rule needs `field`, `tag`, and one of `starts_with`, `contains` or `regex`. They're case-insensitive unless you set `"case_sensitive": true`.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `ANKI_CONNECT_URL` | `http://127.0.0.1:8765` | AnkiConnect address (must be localhost) |
| `ANKI_CONNECT_API_KEY` | – | Set this if you configured `apiKey` in AnkiConnect |
| `ANKI_MCP_BRIDGE_URL` | `http://127.0.0.1:8766` | Bridge add-on address (must be localhost) |
| `ANKI_AUTO_LAUNCH` | `1` | Start Anki if it isn't running |
| `ANKI_LAUNCH_COMMAND` | per OS | Custom command to start Anki, e.g. `flatpak run net.ankiweb.Anki` |
| `ANKI_MCP_BACKUP_DIR` | `~/.anki-mcp-server/backups` | Where backups go |
| `ANKI_DEFAULT_MODEL` | – | Default note type for adds/imports |
| `ANKI_MCP_READ_ONLY` | `0` | `1` = read tools only |
| `ANKI_MCP_ALLOW_DELETE` | `1` | `0` = hide the delete tools |

Example (Claude Desktop):

```json
"anki": {
  "command": "uvx",
  "args": ["--from", "git+https://github.com/MeisamHakimi/anki-mcp-server", "anki-mcp-server"],
  "env": { "ANKI_MCP_ALLOW_DELETE": "0", "ANKI_DEFAULT_MODEL": "Basic" }
}
```

## Troubleshooting

- **"Can't connect to AnkiConnect"**: Anki isn't running or AnkiConnect isn't installed. Install it, restart Anki, and check that `curl -s localhost:8765 -X POST -d '{"action":"version","version":6}'` returns `{"result": 6, ...}`.
- **"Started Anki, but AnkiConnect didn't answer"**: Anki is probably waiting at the profile picker or a dialog. Check its window.
- **An edit shows `not_applied`**: the note was open in Anki's editor or Browse window. Close it and retry.
- **"needs the Anki MCP Bridge add-on"**: install the bridge (see above) and restart Anki.
- **Restoring:** decks are restored from the `.apkg` in the backup folder (File → Import). Edited or deleted notes can be restored from the JSON backups, which contain every field and tag.

## Development

```bash
git clone https://github.com/MeisamHakimi/anki-mcp-server && cd anki-mcp-server
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest                 # tests use fake AnkiConnect and bridge servers; Anki isn't needed
python scripts/build_addon.py    # builds dist/anki_mcp_bridge.ankiaddon
```

To try it interactively, use [MCP Inspector](https://github.com/modelcontextprotocol/inspector):

```bash
npx @modelcontextprotocol/inspector .venv/bin/anki-mcp-server
```

## License

MIT. Not affiliated with Anki, AnkiConnect or AwesomeTTS.
