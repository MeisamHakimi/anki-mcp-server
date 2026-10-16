---
name: anki-flashcards
description: Work with the user's Anki flashcards through the anki tools. Use when the user mentions Anki, flashcards, a deck, spaced repetition, vocabulary cards, AnkiDroid/AnkiMobile, or asks to add, import, find, edit, move, tag, add audio to, delete, or sync cards.
---

# Working with Anki

The `anki` MCP server controls Anki Desktop on the user's computer through the AnkiConnect add-on. Follow these rules for every Anki task.

## Start of a task

1. Call `anki_status` first. It returns the decks, the note types with their exact field names, the profile, and which optional features are available. Use those real names; never guess deck, note type or field names.
2. If a tool says Anki or AnkiConnect is missing, relay its setup steps to the user in plain words: install Anki from apps.ankiweb.net, open it once, then run `uvx anki-mcp-server setup --skip-claude` in a terminal (it installs AnkiConnect and checks everything), or in Anki choose Tools > Add-ons > Get Add-ons and enter 2055492159, then restart Anki. Don't retry in a loop.

## Adding cards

- Ask for, or infer from context, the target deck. If it doesn't exist, create it with `anki_create_deck` (use `Parent::Child` for subdecks).
- Write good cards: one fact per card, the term on the front, a short clear answer on the back, plus an example sentence when the note type has a field for it. Don't pad answers.
- For more than a few notes, or any file import, call `anki_add_notes` / `anki_import_file` with `dry_run: true` first, show the user a short summary (how many will be added, which are skipped as duplicates and why, any row errors), then run it for real after they agree.
- Duplicates are skipped automatically. If the user wants a word that exists in another deck, pass `duplicate_scope: "deck"`.
- For files with a header row, columns map automatically. Otherwise pass `columns`. Use `tag_rules` and `default_tag` for per-row tags (for example, rows starting with "GRAMMAR NOTE:" tagged `grammar`, the rest `vocab`).

## Audio

- Use `anki_generate_audio` with `source_field` (the text to speak) and `dest_field` (where the sound goes). It only fills empty fields.
- Pick `lang` from the card's language (for example `es` for Spanish). For English accents use `accent` (`com`, `co.uk`, `com.au`). The built-in engine sends the text to Google; mention that once if the user seems privacy-conscious. If AwesomeTTS is installed, `engine: "auto"` uses it.
- Limit audio to the notes just added, for example `added:1` in the query, unless the user asks for more.

## Changing or deleting existing data

`anki_update_notes`, `anki_move_notes`, `anki_rename_deck`, `anki_rename_profile`, `anki_delete_notes`, `anki_delete_deck` and `anki_install_bridge` are two-step:

1. Call without `confirm_token`. Nothing changes; you get a preview and a token.
2. Show the user what will change in plain words: how many notes or cards, before → after for edits, which decks.
3. Only after the user explicitly approves **that** change, call again with the same arguments plus `confirm_token`. Never confirm on your own initiative, and never reuse an approval for a different change.

After the change, tell the user where the backup was saved.

## Finishing

- Searches use Anki syntax: `deck:"Name"`, `tag:x`, `Field:*word*`, `added:1`, `is:new`.
- Offer `anki_sync` at the end when the user studies on a phone. It needs the user to be signed in to AnkiWeb in Anki.
- Keep summaries short: what was added, skipped, changed, and anything the user needs to do.
