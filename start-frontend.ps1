# ─────────────────────────────────────────────────────────────────────────────
# TradeMinds AI - Frontend launcher (Windows / PowerShell)
#
# Starts the Next.js dev server on http://localhost:3000.
# Keep this window OPEN. Press Ctrl+C to stop.
# ─────────────────────────────────────────────────────────────────────────────

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

# Make this window obviously the FRONTEND window (title + blue background)
$Host.UI.RawUI.WindowTitle = "[FRONTEND] localhost:3000 - DO NOT CLOSE"
try { $Host.UI.RawUI.BackgroundColor = "DarkBlue"; Clear-Host } catch { }

Write-Host ""
Write-Host "  ==============================================" -ForegroundColor Cyan
Write-Host "  ===   FRONTEND  (Next.js)                  ===" -ForegroundColor Cyan
Write-Host "  ===   http://localhost:3000                ===" -ForegroundColor Cyan
Write-Host "  ===   DO NOT CLOSE THIS WINDOW!            ===" -ForegroundColor Yellow
Write-Host "  ==============================================" -ForegroundColor Cyan
Write-Host ""

Set-Location (Join-Path $scriptDir "frontend")

if (-not (Test-Path "node_modules")) {
    Write-Host "node_modules missing. Running npm install..." -ForegroundColor Yellow
    & npm.cmd install
}

& npm.cmd run dev
