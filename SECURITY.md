# Security Policy

## Reporting a vulnerability

Please report security issues **privately** through GitHub: <https://github.com/MeisamHakimi/anki-mcp-server/security/advisories/new>. Please don't open a public issue for them.

You can expect an acknowledgement within a few days. Fixes are released as a new version on PyPI and GitHub, and noted in the [changelog](CHANGELOG.md).

## Supported versions

Only the latest release receives security fixes.

## Design

- The server uses the stdio transport and only connects to `127.0.0.1` (AnkiConnect and the optional bridge add-on). Other addresses are rejected.
- Only an allowlist of AnkiConnect actions is used.
- Changes to existing data require a preview → confirmation token, and are backed up first.
- The bridge add-on listens on `127.0.0.1` only and rejects browser requests (any `Origin` header, or a missing `X-Anki-MCP` header).
