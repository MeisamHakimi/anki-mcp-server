# anki-mcp-server

An [MCP](https://modelcontextprotocol.io) server that lets Claude (or any MCP client) work with your **Anki** flashcards. It can create decks, add notes, import TSV/CSV files, search, edit, move, rename and delete, **add pronunciation audio**, and sync to AnkiWeb so changes reach AnkiDroid / AnkiMobile.

> "Create a deck Spanish::Verbs and add these 10 verbs with example sentences."
> "Import `~/Downloads/spanish.csv` into my Spanish deck. Do a dry run first."
> "Add Spanish pronunciation audio to the notes I added today, then sync."
> "Find every card tagged `verbs` that has no example sentence."
> "Move all notes tagged `grammar` into Spanish::Grammar."

It works on **macOS, Windows and Linux**, with Anki Desktop and the free [AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on.

---

## Quick start (about 5 minutes)

### 1. Install Anki Desktop

Download it from **<https://apps.ankiweb.net>** and install it like any other app. Open it once.

*Optional:* to get your cards on your phone, create a free [AnkiWeb](https://ankiweb.net) account and click **Sync** in Anki. Then install AnkiDroid (Android) or AnkiMobile (iPhone) and sign in with the same account.

### 2. Install the AnkiConnect add-on

1. In Anki, choose **Tools → Add-ons → Get Add-ons…**
2. Enter the code **`2055492159`** and click **OK**.
3. **Restart Anki.** Quit it completely, then open it again.

*macOS tip:* to stop macOS from slowing down Anki while it's in the background, run this once in Terminal:

```bash
defaults write net.ankiweb.dtop NSAppSleepDisabled -bool true
```

### 3. Install uv

uv runs this server without you installing Python or anything else by hand.

- **macOS / Linux:** `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Windows (PowerShell):** `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
- Or with Homebrew: `brew install uv`

Then find the full path of `uvx`; you'll need it in the next step:
- macOS/Linux: `which uvx` (usually `/Users/<you>/.local/bin/uvx` or `/opt/homebrew/bin/uvx`)
- Windows: `where uvx`

### 4. Add it to Claude

**Claude Desktop:** go to **Settings → Developer → Edit Config**, add the following (use your `uvx` path from step 3), save, and **fully quit and reopen Claude**:

```json
{
  "mcpServers": {
    "anki": {
      "command": "/Users/<you>/.local/bin/uvx",
      "args": ["--from", "git+https://github.com/MeisamHakimi/anki-mcp-server", "anki-mcp-server"]
    }
  }
}
```

If the file already has other content, add `"anki": {...}` inside the existing `"mcpServers"` (or add `"mcpServers"` next to the other top-level keys). The full path matters because desktop apps often can't see your terminal's PATH.

**Claude Code:**

```bash
claude mcp add anki --scope user -- uvx --from git+https://github.com/MeisamHakimi/anki-mcp-server anki-mcp-server
```

**Other MCP clients:** run `anki-mcp-server` (via uvx as above, or after `pip install git+https://github.com/MeisamHakimi/anki-mcp-server`) as a stdio server.

### 5. Try it

Open a new chat and say **"Check my Anki status."** You don't need to open Anki first: if it isn't running, the server starts it in the background. Claude asks permission the first time it uses each tool.

---

## Pronunciation audio (text-to-speech)

Audio works **out of the box**:

> "Add audio of the Word field into the Audio field for deck:"English" notes."
> "Add Spanish audio (lang es) of the Front field into the Back field for notes added today."

- **Built-in engine (default):** free Google Translate voices in 60+ languages (`lang`: `en`, `es`, `fr`, `de`, `ja`, `zh-CN`, …) and English accents (`accent`: `com` US, `co.uk`, `com.au`, `ca`, `co.in`). No add-on or API key is needed. It needs internet, and the text being spoken is sent to Google.
- **AwesomeTTS:** if you use the [AwesomeTTS](https://ankiweb.net/shared/info/1436550454) add-on and install the bridge add-on (below), audio uses your AwesomeTTS voice and presets automatically.
- **Nothing is overwritten:** only notes whose audio field is empty get audio. Use `dry_run` to preview.

Audio is stored as `[sound:…]` in the field you choose. If your note type has no audio field, use an existing one (e.g. `Back`), or add a field in Anki via Tools → Manage Note Types → Fields.

## Optional: the Anki MCP Bridge add-on

Everything works without it. The bridge adds three things AnkiConnect can't do:
- Rename your **Anki profile** (e.g. "User 1" → your name)
- **Exact deck renames**, which keep the deck description and allow capitalization-only changes. Without the bridge, renames move the cards to a newly named deck, which keeps the cards, review history and options.
- Use your **AwesomeTTS** voice

**Install:** ask Claude *"Install the Anki MCP bridge"*, or run `uvx --from git+https://github.com/MeisamHakimi/anki-mcp-server anki-mcp-server install-bridge`. Then restart Anki.

It listens on `127.0.0.1:8766` only, refuses requests from web browsers, and never returns AwesomeTTS settings or API keys. AwesomeTTS support relies on AwesomeTTS internals (tested with 1.89.4), so an AwesomeTTS update could break only that feature.

---

## Safety

Your collection is personal data you've built over years, so this server is cautious by default:

- **Local connections only.** It uses the stdio transport (no network listener) and only talks to Anki on `127.0.0.1`; other URLs are rejected. The one exception is built-in TTS, which sends the spoken text to Google.
- **Adding never overwrites.** Notes are added with `allowDuplicate=false`; duplicates are reported back as skipped. `dry_run` previews adds, imports and audio.
- **Changes and deletions are two-step.** A tool that edits, moves, renames or deletes first returns a **preview** and a `confirm_token`, without changing anything. The change only runs when the tool is called again with that token. The token is rejected if the arguments differ, if the notes changed since the preview, or if the server restarted. The server tells the model to get your explicit approval first.
- **Backups before every change** go to `~/.anki-mcp-server/backups/`: affected notes as JSON, and deleted decks as an `.apkg` with review history (restore it via Anki → File → Import). AnkiConnect edits bypass Anki's undo, so these backups are your undo. Anki's own automatic backups (File → Switch Profile → Open Backup) are another safety net.
- **Allowlisted actions.** Only the AnkiConnect actions this server needs are used. Note-type, template and deck-option editing are never exposed.
- **Modes.** `ANKI_MCP_READ_ONLY=1` exposes only read tools. `ANKI_MCP_ALLOW_DELETE=0` hides the delete tools.
- **Tool annotations.** Every tool is marked read-only or destructive, so MCP clients can ask for confirmation appropriately.

## Tools

| Tool | Kind | What it does |
|---|---|---|
| `anki_status` | read | AnkiConnect version, profile, decks, note types and their fields, available features |
| `anki_find_notes` | read | [Anki search syntax](https://docs.ankiweb.net/searching.html) → notes with fields, tags and decks |
| `anki_list_tags` | read | All tags |
| `anki_open_browser` | read | Opens Anki's Browse window filtered by a search |
| `anki_tts_status` | read | Available audio engines, languages and AwesomeTTS presets |
| `anki_create_deck` | add | Creates a deck (`Parent::Child` for subdecks); a no-op if it exists |
| `anki_add_notes` | add | Adds notes; duplicates skipped; `dry_run` |
| `anki_import_file` | add | Imports `.txt/.tsv/.csv`: header or `columns` mapping, a `tags` column, `tag_rules`, Anki plain-text exports, `dry_run` |
| `anki_generate_audio` | add | Text-to-speech into empty audio fields (Google built-in or AwesomeTTS) |
| `anki_sync` | add | Syncs with AnkiWeb |
| `anki_update_notes` | change | Edits fields and tags (preview → confirm, backup) |
| `anki_move_notes` | change | Moves notes to another deck (preview → confirm, backup) |
| `anki_rename_deck` | change | Renames a deck and its subdecks (preview → confirm) |
| `anki_rename_profile` | change | Renames the Anki profile (preview → confirm; bridge) |
| `anki_install_bridge` | change | Installs or updates the bridge add-on (preview → confirm) |
| `anki_delete_notes` | delete | Deletes notes (preview → confirm, JSON backup) |
| `anki_delete_deck` | delete | Deletes a deck and its cards (preview → confirm, `.apkg` + JSON backup) |

### Note types and field names

You can use friendly field names. Matching is case-insensitive, and a unique prefix works: `"example"` maps to a field called `Example sentence`. If you don't pass `model`, adds and imports use `ANKI_DEFAULT_MODEL`, else the note type most used in the target deck, else Anki's standard `Basic` (Front/Back).

### Importing files

```text
word	meaning	example
resilient	able to recover quickly	She is remarkably resilient.
GRAMMAR NOTE: present perfect	have/has + past participle	I have lived here for years.
```

> "Import `~/vocab.txt` into `English::Vocabulary`. Tag rows whose word starts with `GRAMMAR NOTE:` as `grammar` and everything else as `vocab`."

This becomes:

```json
{"path": "~/vocab.txt", "deck": "English::Vocabulary",
 "tag_rules": [{"field": "Word", "starts_with": "GRAMMAR NOTE:", "tag": "grammar"}],
 "default_tag": "vocab", "dry_run": true}
```

- **Delimiter:** tab, comma, semicolon or pipe, auto-detected. Tab-separated files are read literally; other delimiters follow CSV quoting rules. Files must be UTF-8.
- **Columns:** taken from a header row if there is one (auto-detected when it matches field names), else from `columns`, else in the note type's field order. Use `""` to skip a column and `"tags"` for a space-separated tags column.
- **Anki exports:** "Notes in Plain Text" exports work, including their `#separator:` and `#columns:` lines.
- **Tag rules:** each rule needs `field`, `tag`, and one of `starts_with`, `contains` or `regex`. They're case-insensitive unless you set `"case_sensitive": true`.

## Configuration (optional)

Set these in the `env` block of your MCP config.

| Variable | Default | Meaning |
|---|---|---|
| `ANKI_CONNECT_URL` | `http://127.0.0.1:8765` | AnkiConnect address (must be localhost) |
| `ANKI_CONNECT_API_KEY` | – | Set this if you configured `apiKey` in AnkiConnect |
| `ANKI_MCP_BRIDGE_URL` | `http://127.0.0.1:8766` | Bridge add-on address (must be localhost) |
| `ANKI_AUTO_LAUNCH` | `1` | Start Anki if it isn't running |
| `ANKI_LAUNCH_COMMAND` | per OS | Custom command to start Anki, e.g. `flatpak run net.ankiweb.Anki` |
| `ANKI_BASE` | per OS | Anki's data folder, used to install the bridge (Anki: Tools → Add-ons → View Files, one level up) |
| `ANKI_MCP_BACKUP_DIR` | `~/.anki-mcp-server/backups` | Where backups go |
| `ANKI_DEFAULT_MODEL` | – | Default note type for adds/imports |
| `ANKI_MCP_READ_ONLY` | `0` | `1` = read tools only |
| `ANKI_MCP_ALLOW_DELETE` | `1` | `0` = hide the delete tools |

```json
"anki": {
  "command": "/Users/<you>/.local/bin/uvx",
  "args": ["--from", "git+https://github.com/MeisamHakimi/anki-mcp-server", "anki-mcp-server"],
  "env": { "ANKI_MCP_ALLOW_DELETE": "0" }
}
```

## Troubleshooting

| Problem | Fix |
|---|---|
| Claude doesn't list the **anki** tools | Use the **full path** to `uvx` in the config (step 3), then fully quit and reopen Claude. Claude Desktop → Settings → Developer shows the server's error. |
| "Can't connect to AnkiConnect" | Install AnkiConnect (step 2) and restart Anki. To check, run `curl -s localhost:8765 -X POST -d '{"action":"version","version":6}'`; it should print `{"result": 6, ...}`. |
| "Anki isn't installed / couldn't be found" | Install Anki (step 1). For a non-standard install, set `ANKI_LAUNCH_COMMAND`. |
| "Started Anki, but AnkiConnect didn't answer" | Anki is waiting at the profile picker or a dialog; check its window. Otherwise AnkiConnect isn't installed. |
| Slow or timing out on macOS | Run the App Nap command from step 2, then restart Anki. |
| Audio fails | Built-in audio needs internet. If several requests fail, Google may be rate-limiting; try again later or with a smaller `limit`. |
| An edit shows `not_applied` | The note was open in Anki's editor or Browse window. Close it and retry. |
| "needs the Anki MCP Bridge add-on" | Ask Claude to install the bridge, then restart Anki. |
| Restoring something | Decks: import the `.apkg` from the backup folder (File → Import). Notes: the JSON backups contain every field and tag. Whole collection: Anki's File → Switch Profile → Open Backup. |

## Development

```bash
git clone https://github.com/MeisamHakimi/anki-mcp-server && cd anki-mcp-server
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest                 # tests use fake AnkiConnect and bridge servers; Anki isn't needed
python scripts/build_addon.py    # builds dist/anki_mcp_bridge.ankiaddon
npx @modelcontextprotocol/inspector .venv/bin/anki-mcp-server   # try the tools interactively
```

## License

MIT. Not affiliated with Anki, AnkiConnect, AwesomeTTS or Google.
