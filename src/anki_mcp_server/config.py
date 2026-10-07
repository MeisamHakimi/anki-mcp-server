"""Settings, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def loopback_url(url: str, what: str) -> str:
    """Only plain-HTTP URLs on the loopback interface are accepted: this server never talks to the network."""
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in LOOPBACK_HOSTS or not parsed.port:
        raise ValueError(f"{what} must look like http://127.0.0.1:<port> (localhost only), got {url!r}")
    return url


@dataclass(frozen=True)
class Settings:
    anki_connect_url: str = "http://127.0.0.1:8765"
    anki_connect_api_key: str | None = None
    bridge_url: str = "http://127.0.0.1:8766"
    auto_launch: bool = True
    launch_command: str | None = None
    backup_dir: Path = Path.home() / ".anki-mcp-server" / "backups"
    default_model: str | None = None
    read_only: bool = False
    allow_delete: bool = True

    def __post_init__(self) -> None:
        loopback_url(self.anki_connect_url, "ANKI_CONNECT_URL")
        loopback_url(self.bridge_url, "ANKI_MCP_BRIDGE_URL")

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ
        return cls(
            anki_connect_url=env.get("ANKI_CONNECT_URL") or cls.anki_connect_url,
            anki_connect_api_key=env.get("ANKI_CONNECT_API_KEY") or None,
            bridge_url=env.get("ANKI_MCP_BRIDGE_URL") or cls.bridge_url,
            auto_launch=_flag("ANKI_AUTO_LAUNCH", True),
            launch_command=env.get("ANKI_LAUNCH_COMMAND") or None,
            backup_dir=Path(env["ANKI_MCP_BACKUP_DIR"]).expanduser() if env.get("ANKI_MCP_BACKUP_DIR") else cls.backup_dir,
            default_model=env.get("ANKI_DEFAULT_MODEL") or None,
            read_only=_flag("ANKI_MCP_READ_ONLY", False),
            allow_delete=_flag("ANKI_MCP_ALLOW_DELETE", True),
        )
