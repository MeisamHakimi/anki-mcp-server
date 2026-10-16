# One-line setup for anki-mcp-server on Windows (PowerShell):
#   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/MeisamHakimi/anki-mcp-server/main/install.ps1 | iex"
# Installs uv if needed (https://docs.astral.sh/uv/), then runs the interactive setup wizard, which asks
# before every change.
$ErrorActionPreference = "Stop"
$Source = if ($env:ANKI_MCP_SOURCE) { $env:ANKI_MCP_SOURCE } else { "anki-mcp-server" }

$uvx = Get-Command uvx -ErrorAction SilentlyContinue
if (-not $uvx) {
    $candidate = Join-Path $env:USERPROFILE ".local\bin\uvx.exe"
    if (-not (Test-Path $candidate)) {
        Write-Host "Installing uv (a small tool that runs Python apps; https://docs.astral.sh/uv/)..."
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    }
    $env:Path = "$(Join-Path $env:USERPROFILE '.local\bin');$env:Path"
    $uvx = Get-Command uvx -ErrorAction Stop
}

& $uvx.Source --refresh-package anki-mcp-server --from $Source anki-mcp-server setup @args
exit $LASTEXITCODE
