# anki-mcp-server

An [MCP](https://modelcontextprotocol.io) server that lets Claude (or any MCP client) work with your **Anki** flashcards. It can create decks, add notes, import TSV/CSV files, search, edit, move, rename and delete, **add pronunciation audio**, and sync to AnkiWeb so changes reach AnkiDroid / AnkiMobile.

> "Create a deck Spanish::Verbs and add these 10 verbs with example sentences."
> "Import `~/Downloads/spanish.csv` into my Spanish deck. Do a dry run first."
> "Add Spanish pronunciation audio to the notes I added today, then sync."
> "Find every card tagged `verbs` that has no example sentence."
> "Move all notes tagged `grammar` into Spanish::Grammar."

It works on **macOS, Windows and Linux**, with Anki Desktop and the free [AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on.

---

## Install

### 1. Install Anki Desktop (once)

Download it from **<https://apps.ankiweb.net>**, install it, and **open it once**: its first window asks for a language and creates your profile.
- **macOS:** open the `.dmg` and drag Anki to Applications. With Homebrew: `brew install --cask anki`.
- **Windows:** run the installer (`anki-…-windows.exe`).
- **Linux:** use the official package from the download page, or Flatpak: `flatpak install flathub net.ankiweb.Anki`.

Anki 23.10 or newer is required.

*Phone:* to get your cards on your phone, create a free [AnkiWeb](https://ankiweb.net) account, click **Sync** in Anki, and sign in to AnkiDroid (Android) or AnkiMobile (iPhone) with the same account.

### 2. Connect it to Claude: pick one

| You use | Easiest option |
|---|---|
| **Claude Desktop** (chat) | [A. Desktop extension](#a-claude-desktop-extension-one-click): one click, nothing else to install |
| **Claude Code** or **Cowork** | [B. Plugin](#b-claude-code--cowork-plugin) |
| Not sure, or you want everything set up for you | [C. One-line installer](#c-one-line-installer-sets-up-everything) |

Use only one of A and C for Claude Desktop; otherwise Claude sees the tools twice.

#### A. Claude Desktop extension (one click)

1. **AnkiConnect:** in Anki choose **Tools → Add-ons → Get Add-ons…**, enter **`2055492159`**, click OK, then **restart Anki**.
2. Download **[anki-mcp-server.mcpb](https://github.com/MeisamHakimi/anki-mcp-server/releases/latest/download/anki-mcp-server.mcpb)** from the latest release.
3. **Double-click** it, or in Claude Desktop go to **Settings → Extensions → Advanced settings → Install Extension…**, then click **Install**.

Claude Desktop takes care of Python and everything else. In the extension's settings you can turn on **read-only mode** or turn off deleting.

#### B. Claude Code / Cowork plugin

- **Claude Code:** run these two commands in a session:

  ```text
  /plugin marketplace add MeisamHakimi/anki-mcp-server
  /plugin install anki-flashcards@meisamhakimi
  ```

- **Claude app (Cowork):** go to **Customize → Plugins → Add → Add marketplace**, enter `MeisamHakimi/anki-mcp-server`, then add **Anki Flashcards (community)**.

The plugin adds the server and a skill that teaches Claude good Anki habits: dry runs first, and your approval before any change. It needs [uv](https://docs.astral.sh/uv/getting-started/installation/) and AnkiConnect. After installing uv, run `uvx anki-mcp-server setup --skip-claude` to check Anki and install AnkiConnect. The server runs on your computer, so the plugin works in **Claude Code and in Cowork sessions on your computer**, not in regular claude.ai chat (use option A for that).

#### C. One-line installer (sets up everything)

**macOS / Linux** (Terminal):

```bash
curl -LsSf https://raw.githubusercontent.com/MeisamHakimi/anki-mcp-server/main/install.sh | sh
```

**Windows** (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/MeisamHakimi/anki-mcp-server/main/install.ps1 | iex"
```

The installer:
1. installs [uv](https://docs.astral.sh/uv/) if it's missing. uv brings its own Python, so you don't need Python or git.
2. starts the setup wizard, which **asks before every change**:
   - checks that Anki is installed (and offers to install it with Homebrew/Flatpak, or opens the download page),
   - installs the **AnkiConnect** add-on from AnkiWeb (the same download Anki's *Get Add-ons* uses, verified before installing),
   - optionally installs the **Anki MCP Bridge** add-on (recommended if you use AwesomeTTS),
   - restarts Anki and checks the connection,
   - adds the server to **Claude Desktop** (backing up your config; an existing `anki` entry is never replaced without asking) and to **Claude Code** if it's installed.

Add `--dry-run` to see what it would do without changing anything (`… | sh -s -- --dry-run`). To read the scripts first, see [install.sh](install.sh) and [install.ps1](install.ps1).

### 3. Try it

Restart Claude Desktop **completely** (⌘Q on Mac, File → Exit on Windows) after options A or C. Then say **"Check my Anki status."**

You don't need to open Anki first: if it isn't running, the server starts it in the background. Claude asks permission the first time it uses each tool.

### Manual setup

1. **AnkiConnect:** in Anki choose **Tools → Add-ons → Get Add-ons…**, enter **`2055492159`**, click OK, then restart Anki.
2. **uv:** run `curl -LsSf https://astral.sh/uv/install.sh | sh` (macOS/Linux) or `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"` (Windows). Then find the **full path** of uvx with `which uvx` (macOS/Linux) or `where uvx` (Windows).
3. **Claude Desktop:** go to Settings → Developer → Edit Config, add the following inside the top-level `{ }`, save, and fully restart Claude. Use the full uvx path: desktop apps often can't see your terminal's PATH.

   ```json
   "mcpServers": {
     "anki": {
       "command": "/Users/<you>/.local/bin/uvx",
       "args": ["anki-mcp-server"]
     }
   }
   ```

   If `"mcpServers"` already exists, add just the `"anki": {…}` part inside it.
4. **Claude Code:**

   ```bash
   claude mcp add anki --scope user -- uvx anki-mcp-server
   ```

5. **Other MCP clients:** run `uvx anki-mcp-server` (or `pip install anki-mcp-server`, then run `anki-mcp-server`) as a stdio server.

**macOS tip:** if Anki responds slowly while it's in the background, run this once and restart Anki:

```bash
defaults write net.ankiweb.dtop NSAppSleepDisabled -bool true
```

### Updating

- **Desktop extension:** download the newer `.mcpb` from Releases and install it again.
- **Plugin:** updates arrive automatically from the marketplace.
- **Installer:** run it again, then restart Claude.

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

**Install:** say yes when the installer offers it, or ask Claude *"Install the Anki MCP bridge"*. Then restart Anki.

It listens on `127.0.0.1:8766` only, refuses requests from web browsers, and never returns AwesomeTTS settings or API keys. AwesomeTTS support relies on AwesomeTTS internals (tested with 1.89.4), so an AwesomeTTS update could break only that feature.

---

## Safety

Your collection is personal data you've built over years, so this server is cautious by default:

- **Local connections only.** It uses the stdio transport (no network listener) and only talks to Anki on `127.0.0.1`; other URLs are rejected. The one exception is built-in TTS, which sends the spoken text to Google (see [Privacy Policy](#privacy-policy)).
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
  "args": ["anki-mcp-server"],
  "env": { "ANKI_MCP_ALLOW_DELETE": "0" }
}
```

## Troubleshooting

| Problem | Fix |
|---|---|
| Claude doesn't list the **anki** tools | Fully quit and reopen Claude. Run the installer again (it fixes the config), or check that the config uses the **full path** to `uvx`. Claude Desktop → Settings → Developer shows the server's error. |
| "Can't connect to AnkiConnect" | Run the installer again, or install AnkiConnect manually and restart Anki. To check, run `curl -s localhost:8765 -X POST -d '{"action":"version","version":6}'`; it should print `{"result": 6, ...}`. |
| "Anki isn't installed / couldn't be found" | Install Anki (step 1) and open it once. For a non-standard install, set `ANKI_LAUNCH_COMMAND`. |
| "Started Anki, but AnkiConnect didn't answer" | Anki is waiting at the profile picker or a dialog; check its window. Otherwise AnkiConnect isn't installed. |
| Slow or timing out on macOS | Run the App Nap command from *Manual setup*, then restart Anki. |
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
python scripts/build_mcpb.py     # builds dist/anki-mcp-server.mcpb (needs Node.js)
claude plugin validate ./plugins/anki-flashcards   # checks the Claude plugin
.venv/bin/anki-mcp-server setup --dry-run   # try the setup wizard without changing anything
npx @modelcontextprotocol/inspector .venv/bin/anki-mcp-server   # try the tools interactively
```

## Privacy Policy

anki-mcp-server runs entirely on your computer. The author collects no data and runs no servers, and there is no telemetry.
- **Your notes** are read and changed locally through Anki/AnkiConnect on `127.0.0.1`. Tool results go to the AI app you use (e.g. Claude) under that app's privacy policy.
- **Third parties, only when you use these features:**
  - **Google** receives the text being spoken by the built-in text-to-speech.
  - **AnkiWeb** receives your collection when you sync, through Anki itself.
  - **AnkiWeb, PyPI, GitHub and astral.sh** serve the downloads during installation; these requests contain no personal data.
- **Retention:** backups stay in `~/.anki-mcp-server/backups/` on your computer until you delete them. Nothing is kept by the author.
- **Contact:** [GitHub issues](https://github.com/MeisamHakimi/anki-mcp-server/issues), or private reports through [security advisories](https://github.com/MeisamHakimi/anki-mcp-server/security/advisories/new).

Full policy: [PRIVACY.md](PRIVACY.md). Security policy: [SECURITY.md](SECURITY.md).

## License

MIT. This is an unofficial community project, not affiliated with or endorsed by Anki/Ankitects, AnkiConnect, AwesomeTTS, Google or Anthropic.
