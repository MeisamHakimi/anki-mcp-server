# Privacy Policy

*Last updated: 2026-10-16. Applies to anki-mcp-server, its Claude plugin ("Anki Flashcards"), its Claude Desktop extension, and the Anki MCP Bridge add-on.*

anki-mcp-server is free, open-source software that runs **on your own computer**. The author does not operate any server for it and does not collect, receive, store or sell any of your data. There is no analytics, telemetry or tracking.

## What data it handles and where it goes

| Data | Where it goes | When |
|---|---|---|
| Your Anki notes, decks, tags and profile name | Read and changed **locally** through Anki and the AnkiConnect add-on on `127.0.0.1`. Tool results are returned to the AI app you use (e.g. Claude), which processes them under **that** app's privacy policy (for Claude: <https://www.anthropic.com/legal/privacy>) | Whenever you or the AI use a tool |
| Text you turn into audio with the **built-in** text-to-speech engine | Sent to **Google's** Translate text-to-speech service to create the MP3 file ([Google Privacy Policy](https://policies.google.com/privacy)) | Only when `anki_generate_audio` runs with the `google` engine (the default when AwesomeTTS isn't installed) |
| Text you turn into audio with **AwesomeTTS** | Handled by the AwesomeTTS add-on and the voice service *you* configured in it | Only when `anki_generate_audio` uses the `awesometts` engine |
| Your whole collection, when you sync | Sent by Anki itself to **AnkiWeb** ([AnkiWeb privacy](https://ankiweb.net/account/privacy)) | Only when `anki_sync` runs or you sync in Anki |
| Nothing personal: software downloads | The installer and setup download uv (astral.sh), this package (PyPI / GitHub) and, if you agree, the AnkiConnect add-on (ankiweb.net). These requests contain no personal data | Only during installation / setup |

## Storage and retention

- **Backups:** before editing, moving, renaming or deleting, the affected notes are saved as JSON (and deleted decks as `.apkg`) in `~/.anki-mcp-server/backups/` (or `ANKI_MCP_BACKUP_DIR`). They stay on your computer until **you** delete them.
- **Audio files** are stored in your Anki collection's media folder like any other Anki media.
- **Configuration:** setup writes the server entry into your Claude Desktop configuration (after asking, with a backup) and installs add-ons into Anki's add-ons folder.
- Nothing else is stored, and nothing is kept by the author.

## Third-party sharing

The author shares no data with anyone. Data only reaches the third parties listed above (Google, AnkiWeb, your AI app, your AwesomeTTS voice service), and only through the actions described there.

## Your choices

- Use `ANKI_MCP_READ_ONLY=1` (read-only) or `ANKI_MCP_ALLOW_DELETE=0` (no delete tools).
- Avoid sending text to Google by using AwesomeTTS with a local voice, or by not using the audio tool.
- Uninstall at any time: remove the server from your Claude configuration, delete `~/.anki-mcp-server/`, and remove the add-ons in Anki (Tools → Add-ons).

## Children

The software is not directed at children under 13 and collects no personal information from anyone.

## Changes and contact

Changes to this policy are published in this file with a new date. Questions or requests: open an issue at <https://github.com/MeisamHakimi/anki-mcp-server/issues>, or report privately via <https://github.com/MeisamHakimi/anki-mcp-server/security/advisories/new>.
