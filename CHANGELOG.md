# Changelog

## 0.2.0 (2026-10-16)

- **Claude plugin** "Anki Flashcards (community)" in `plugins/anki-flashcards` (MCP server and a workflow skill), with a marketplace file so it can be added with `/plugin marketplace add MeisamHakimi/anki-mcp-server`
- **Claude Desktop extension** (`anki-mcp-server.mcpb`) for one-click installs; Claude Desktop manages Python itself. Settings for read-only mode and deleting
- Published on **PyPI** (`uvx anki-mcp-server`), released automatically by GitHub Actions with trusted publishing
- Every tool now has a `title`; the audio tool is marked as reaching an outside service
- `setup --skip-claude` for plugin users
- The plugin ships a `uv.lock` (exact versions and hashes for every dependency) next to its `uvx anki-mcp-server==0.2.0` launcher
- Privacy policy (`PRIVACY.md`), security policy (`SECURITY.md`) and an icon

## 0.1.0 (2026-10-07)

First release.

- Read: `anki_status`, `anki_find_notes`, `anki_list_tags`, `anki_open_browser`, `anki_tts_status`
- Add: `anki_create_deck`, `anki_add_notes`, `anki_import_file` (TSV/CSV, header/columns mapping, tag rules, Anki plain-text exports), `anki_sync`
- Audio: `anki_generate_audio` with built-in Google Translate voices (no add-on needed) or AwesomeTTS via the bridge add-on; only fills empty fields
- Change and delete with preview → confirm tokens and automatic backups: `anki_update_notes`, `anki_move_notes`, `anki_rename_deck` (works without the bridge), `anki_rename_profile`, `anki_delete_notes`, `anki_delete_deck`
- `anki_install_bridge` tool and `anki-mcp-server install-bridge` command to install the bundled bridge add-on
- One-line installers (`install.sh`, `install.ps1`) and an `anki-mcp-server setup` wizard: installs uv, checks Anki (offers Homebrew/Flatpak install), installs and verifies AnkiConnect from AnkiWeb, optionally installs the bridge, restarts Anki, and configures Claude Desktop / Claude Code with backups; `--dry-run` supported
- Installs from GitHub zip archives, so git isn't required
- Localhost-only Anki connections, allowlisted AnkiConnect actions, read-only and no-delete modes, auto-launch of Anki with clear setup hints when Anki or AnkiConnect is missing
