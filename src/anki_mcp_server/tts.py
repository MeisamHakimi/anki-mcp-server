"""Built-in text-to-speech using Google Translate's voices (via gTTS). Needs internet, no Anki add-on, no API key."""

from __future__ import annotations

import hashlib
import html
import io
import re

_SOUND = re.compile(r"\[sound:[^\]]*\]")
_BR = re.compile(r"<br\s*/?>|</div>|</p>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")

MAX_CHARS = 1000


def speakable(field_html: str) -> str:
    """Field HTML -> plain text to speak (drops [sound:...] tags, HTML tags and cloze markup)."""
    text = _SOUND.sub(" ", field_html)
    text = re.sub(r"\{\{c\d+::(.*?)(::[^}]*)?\}\}", r"\1", text)  # cloze -> answer text
    text = _TAG.sub(" ", _BR.sub(" ", text))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def languages() -> dict[str, str]:
    from gtts.lang import tts_langs
    return tts_langs()


def media_filename(text: str, lang: str, tld: str) -> str:
    digest = hashlib.sha1(f"{lang}|{tld}|{text}".encode()).hexdigest()[:16]
    return f"anki-mcp-tts-{lang}-{digest}.mp3"


def synthesize(text: str, lang: str = "en", tld: str = "com") -> bytes:
    """Return MP3 bytes. Blocking (network); call it in a thread."""
    from gtts import gTTS
    buf = io.BytesIO()
    gTTS(text=text, lang=lang, tld=tld, timeout=30).write_to_fp(buf)
    return buf.getvalue()
