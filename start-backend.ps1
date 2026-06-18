# ─────────────────────────────────────────────────────────────────────────────
# TradeMinds AI - Backend launcher (Windows / PowerShell)
#
# Starts the FastAPI backend on http://localhost:8000 using the project's
# bundled venv. Keep this window OPEN. Press Ctrl+C to stop the backend.
# ─────────────────────────────────────────────────────────────────────────────

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

# Make this window obviously the BACKEND window (title + green background)
$Host.UI.RawUI.WindowTitle = "[BACKEND] localhost:8000 - DO NOT CLOSE"
try { $Host.UI.RawUI.BackgroundColor = "DarkGreen"; Clear-Host } catch { }

Write-Host ""
Write-Host "  ==============================================" -ForegroundColor Green
Write-Host "  ===   BACKEND  (FastAPI + uvicorn)         ===" -ForegroundColor Green
Write-Host "  ===   http://localhost:8000  /  /docs      ===" -ForegroundColor Green
Write-Host "  ===   DO NOT CLOSE THIS WINDOW!            ===" -ForegroundColor Yellow
Write-Host "  ==============================================" -ForegroundColor Green
Write-Host ""

Set-Location (Join-Path $scriptDir "backend")

$python = ".\venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "ERROR: $python not found." -ForegroundColor Red
    Write-Host "Create the venv first:  py -m venv venv  ;  .\venv\Scripts\pip install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}

& $python -m uvicorn app.main:app --reload --port 8000
