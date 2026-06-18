# ─────────────────────────────────────────────────────────────────────────────
# TradeMinds AI – Full dev launcher (Windows / PowerShell)
#
# Opens TWO new PowerShell windows:
#   • Backend  → http://localhost:8000
#   • Frontend → http://localhost:3000
#
# Each window must stay OPEN while you develop. Close a window to stop
# that side. This script itself exits immediately after launching the
# child windows.
# ─────────────────────────────────────────────────────────────────────────────

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

$backendScript  = Join-Path $scriptDir "start-backend.ps1"
$frontendScript = Join-Path $scriptDir "start-frontend.ps1"

if (-not (Test-Path $backendScript))  { Write-Host "Missing: $backendScript"  -ForegroundColor Red; exit 1 }
if (-not (Test-Path $frontendScript)) { Write-Host "Missing: $frontendScript" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "  Launching TradeMinds AI dev environment..." -ForegroundColor Cyan
Write-Host "    Backend window  → http://localhost:8000" -ForegroundColor DarkGray
Write-Host "    Frontend window → http://localhost:3000" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Login (after both are up):  dev@trademinds.io / devpass123" -ForegroundColor Yellow
Write-Host ""

# Start backend in a new window. -NoExit keeps the window open after the
# process exits so the user can read any error message before closing.
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-File", $backendScript
) | Out-Null

# Wait briefly so backend can grab port 8000 before frontend starts
# making API requests during its initial render.
Start-Sleep -Seconds 2

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-File", $frontendScript
) | Out-Null

Write-Host "  Two PowerShell windows launched. Keep them open." -ForegroundColor Green
Write-Host ""
