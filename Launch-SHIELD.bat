@echo off
title SHIELD — Intelligent Border Surveillance Platform
echo ===================================================
echo   Starting SHIELD Desktop Application...
echo ===================================================
cd /d "%~dp0frontend\desktop"
call npm.cmd start
