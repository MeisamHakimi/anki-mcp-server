"""Reading delimited text files (TSV/CSV, including Anki's own "Notes in Plain Text" exports)."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

MAX_FILE_BYTES = 10 * 1024 * 1024
SUFFIXES = {".txt", ".tsv", ".csv", ".tab"}
DELIMITERS = {"tab": "\t", "comma": ",", "semicolon": ";", "pipe": "|"}
_ANKI_SEPARATORS = {"tab": "\t", "comma": ",", "semicolon": ";", "pipe": "|", "space": " ", "colon": ":"}


@dataclass
class ParsedFile:
    delimiter: str
    rows: list[tuple[int, list[str]]] = field(default_factory=list)  # (line number, cells)
    directives: dict[str, str] = field(default_factory=dict)


def resolve_path(path: Any) -> Path:
    if not isinstance(path, str) or not path.strip():
        raise ToolError("path must be a non-empty string.")
    p = Path(path.strip()).expanduser().resolve()
    if not p.is_file():
        raise ToolError(f"File not found: {p}")
    if p.suffix.lower() not in SUFFIXES:
        raise ToolError(f"Expected one of {sorted(SUFFIXES)}, got {p.name!r}.")
    if p.stat().st_size > MAX_FILE_BYTES:
        raise ToolError(f"File is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB; split it up.")
    return p


def parse_file(path: Path, delimiter: str = "auto") -> ParsedFile:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        raise ToolError(f"{path.name} is not valid UTF-8 text.") from None
    lines = text.splitlines()

    # Anki "Notes in Plain Text" headers: #separator:tab, #html:true, #columns:..., #tags column:3, ...
    directives: dict[str, str] = {}
    start = 0
    while start < len(lines) and re.match(r"^#[a-z ]+:", lines[start]):
        k, _, v = lines[start][1:].partition(":")
        directives[k.strip().lower()] = v.strip()
        start += 1

    if delimiter != "auto":
        if delimiter not in DELIMITERS:
            raise ToolError(f"delimiter must be 'auto' or one of {sorted(DELIMITERS)}.")
        delim = DELIMITERS[delimiter]
    elif directives.get("separator", "").lower() in _ANKI_SEPARATORS:
        delim = _ANKI_SEPARATORS[directives["separator"].lower()]
    else:
        sample = "\n".join(l for l in lines[start:start + 20] if l.strip())
        if "\t" in sample:
            delim = "\t"
        else:
            try:
                delim = csv.Sniffer().sniff(sample, delimiters=",;|").delimiter
            except csv.Error:
                delim = ","

    parsed = ParsedFile(delimiter=delim, directives=directives)
    body = "\n".join(lines[start:])
    if delim == "\t":
        # TSV: no quoting, a tab always separates (Anki's own behaviour for tab-separated text).
        for i, line in enumerate(lines[start:], start=start + 1):
            if line.strip():
                parsed.rows.append((i, [c.strip() for c in line.split("\t")]))
    else:
        reader = csv.reader(io.StringIO(body), delimiter=delim)
        try:
            for cells in reader:
                if any(c.strip() for c in cells):
                    parsed.rows.append((reader.line_num + start, [c.strip() for c in cells]))
        except csv.Error as e:
            raise ToolError(f"Couldn't parse {path.name} as delimited text: {e}") from None
    return parsed


def match_rule(rule: dict, value: str) -> bool:
    flags = 0 if rule.get("case_sensitive") else re.IGNORECASE
    if "starts_with" in rule:
        return re.match(re.escape(rule["starts_with"]), value, flags) is not None
    if "contains" in rule:
        return re.search(re.escape(rule["contains"]), value, flags) is not None
    return re.search(rule["regex"], value, flags) is not None


def validate_tag_rules(rules: Any) -> list[dict]:
    if rules is None:
        return []
    if not isinstance(rules, list):
        raise ToolError("tag_rules must be a list of objects.")
    out = []
    for i, r in enumerate(rules):
        if not isinstance(r, dict) or not isinstance(r.get("field"), str) or not isinstance(r.get("tag"), str):
            raise ToolError(f"tag_rules[{i}] needs 'field' and 'tag' strings.")
        kinds = [k for k in ("starts_with", "contains", "regex") if k in r]
        if len(kinds) != 1 or not isinstance(r[kinds[0]], str) or not r[kinds[0]]:
            raise ToolError(f"tag_rules[{i}] needs exactly one of starts_with / contains / regex (non-empty string).")
        if kinds[0] == "regex":
            try:
                re.compile(r["regex"])
            except re.error as e:
                raise ToolError(f"tag_rules[{i}] has an invalid regex: {e}") from None
        unknown = set(r) - {"field", "tag", "starts_with", "contains", "regex", "case_sensitive"}
        if unknown:
            raise ToolError(f"tag_rules[{i}] has unknown keys {sorted(unknown)}.")
        out.append(r)
    return out
