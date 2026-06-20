@echo off
REM ============================================================
REM   TradeMinds AI - One-Click Launcher
REM   Cift tikla, iki pencere acilir: Backend + Frontend.
REM ============================================================

title TradeMinds Launcher

cd /d "%~dp0"

echo.
echo   TradeMinds AI baslatiliyor...
echo   Iki yeni pencere acilacak (yesil = Backend, mavi = Frontend).
echo   Bu pencere otomatik kapanacak.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File ".\start-dev.ps1"

REM start-dev.ps1 returns immediately after launching the child windows,
REM so this batch file exits right away too.
exit /b 0
