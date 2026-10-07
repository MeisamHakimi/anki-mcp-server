# Changelog

## 0.1.0 (2026-10-07)

First release.

- Read: `anki_status`, `anki_find_notes`, `anki_list_tags`, `anki_open_browser`
- Add: `anki_create_deck`, `anki_add_notes`, `anki_import_file` (TSV/CSV, header/columns mapping, tag rules, Anki plain-text exports), `anki_sync`
- Change and delete with preview → confirm tokens and automatic backups: `anki_update_notes`, `anki_move_notes`, `anki_rename_deck`, `anki_rename_profile`, `anki_delete_notes`, `anki_delete_deck`
- AwesomeTTS audio through the optional Anki MCP Bridge add-on: `anki_generate_audio`, `anki_tts_status`
- Localhost-only, allowlisted AnkiConnect actions, read-only and no-delete modes, auto-launch of Anki
