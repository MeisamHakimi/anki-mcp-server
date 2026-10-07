# Changelog

## 0.1.0 (2026-10-07)

First release.

- Read: `anki_status`, `anki_find_notes`, `anki_list_tags`, `anki_open_browser`, `anki_tts_status`
- Add: `anki_create_deck`, `anki_add_notes`, `anki_import_file` (TSV/CSV, header/columns mapping, tag rules, Anki plain-text exports), `anki_sync`
- Audio: `anki_generate_audio` with built-in Google Translate voices (no add-on needed) or AwesomeTTS via the bridge add-on; only fills empty fields
- Change and delete with preview → confirm tokens and automatic backups: `anki_update_notes`, `anki_move_notes`, `anki_rename_deck` (works without the bridge), `anki_rename_profile`, `anki_delete_notes`, `anki_delete_deck`
- `anki_install_bridge` tool and `anki-mcp-server install-bridge` command to install the bundled bridge add-on
- Localhost-only Anki connections, allowlisted AnkiConnect actions, read-only and no-delete modes, auto-launch of Anki with clear setup hints when Anki or AnkiConnect is missing
