@echo off
title IBVAP — Intelligent Border Video Analytics Platform
echo ===================================================
echo   Starting IBVAP Desktop Application...
echo ===================================================
cd /d "%~dp0frontend\desktop"
call npm.cmd start
