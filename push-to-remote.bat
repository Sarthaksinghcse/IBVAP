@echo off
title Push IBVAP Changes to Remote
cd /d "%~dp0"
echo ===================================================
echo   Pushing latest changes to remote (origin/main)...
echo ===================================================
"C:\Users\thaku\AppData\Local\GitHubDesktop\app-3.6.5\resources\app\git\cmd\git.exe" push origin main
if %ERRORLEVEL% equ 0 (
    echo.
    echo ===================================================
    echo   Push completed successfully!
    echo ===================================================
) else (
    echo.
    echo Push encountered an issue. You can also open GitHub Desktop and click 'Push origin'.
)
pause
