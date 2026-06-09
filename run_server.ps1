# Launch BOM Builder as a shared LAN server.
#
# Binds to all network interfaces (0.0.0.0) so other computers on the same
# network can reach it at http://<this-PC-IP>:5000/. Uses waitress (see
# requirements.txt) and runs with debug OFF. Run this on the always-on host PC.
#
# Usage:  right-click -> "Run with PowerShell", or:  .\run_server.ps1
# Override the port:  .\run_server.ps1 -Port 8080

param(
    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"

# Resolve paths relative to this script so it works from any working directory.
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Error "Python venv not found at $Python. Create it with: python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt"
    exit 1
}

& $Python (Join-Path $Root "main.py") --host 0.0.0.0 --port $Port --no-browser
