# Anki Flashcards (community plugin)

Lets Claude work with your **Anki** flashcards: create decks, add notes, import TSV/CSV files, search, edit, move, rename and delete, add pronunciation audio, and sync to AnkiWeb so the cards reach your phone. Anki is a free spaced-repetition flashcard app; this plugin connects Claude to **Anki Desktop on your own computer**.

This is an unofficial, community-maintained project. It isn't affiliated with or endorsed by Anki or Ankitects.

## What it contains

- **MCP server `anki`**: runs [`anki-mcp-server`](https://pypi.org/project/anki-mcp-server/) 0.2.0 on your computer with `uvx anki-mcp-server==0.2.0`. The bundled `uv.lock` records the exact versions, PyPI sources and hashes of the server and every dependency. It talks only to Anki on `127.0.0.1` through the AnkiConnect add-on.
- **Skill `anki-flashcards`**: tells Claude how to use the tools well. It checks your real deck and field names first, previews imports with a dry run, and asks for your approval before any edit or delete.

The server runs on your computer, so it works in **Claude Code** and in **Cowork** sessions on your computer. Regular claude.ai chat doesn't start local servers. For the Claude Desktop chat, use the one-click desktop extension or the installer from the [main README](https://github.com/MeisamHakimi/anki-mcp-server#readme).

## Requirements

1. **Anki Desktop** 23.10 or newer, from <https://apps.ankiweb.net>, opened once.
2. **The AnkiConnect add-on.** In Anki, choose Tools → Add-ons → Get Add-ons…, enter `2055492159`, and restart Anki.
3. **uv**, which runs the server and brings its own Python: <https://docs.astral.sh/uv/getting-started/installation/>.

Alternatively, run `uvx anki-mcp-server setup --skip-claude`. It checks Anki, offers to install AnkiConnect (and the optional bridge add-on), and verifies the connection, asking before every change.

## Usage

Ask Claude things like:

- "Create a deck Spanish::Verbs and add these ten verbs with example sentences."
- "Import ~/Downloads/vocab.csv into my Spanish deck. Dry run first."
- "Add Spanish audio of the Front field into the Back field for the notes I added today, then sync."
- "Find every card tagged verbs that has no example sentence."

Edits, moves, renames and deletes always show a preview first, and only run after you approve them. A backup is written to `~/.anki-mcp-server/backups/` before every change.

## Data and privacy

The plugin and server collect nothing for the author and have no telemetry. Your notes stay on your computer and are read and changed through Anki. Tool results go to Claude as part of your conversation.

External destinations are used only in these cases:

- The built-in text-to-speech sends the text being spoken to **Google's** text-to-speech service. This only happens when you add audio with the default engine.
- **AnkiWeb**, only when you sync.
- **PyPI**, to download the locked server package and its dependencies when it first starts.
- **AnkiWeb**, to download AnkiConnect, only if you run `setup` and agree.

Full policy: <https://github.com/MeisamHakimi/anki-mcp-server/blob/main/PRIVACY.md>

## Support

Report issues at <https://github.com/MeisamHakimi/anki-mcp-server/issues>. Source code, documentation and security policy: <https://github.com/MeisamHakimi/anki-mcp-server>. License: MIT.
