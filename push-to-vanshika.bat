@echo off
title Push Changes to vanshika Branch
cd /d "%~dp0"
echo ===================================================
echo   Pushing latest changes to remote (origin/vanshika)...
echo ===================================================
"C:\Users\thaku\AppData\Local\GitHubDesktop\app-3.6.5\resources\app\git\cmd\git.exe" push -u origin vanshika
if %ERRORLEVEL% equ 0 (
    echo.
    echo ===================================================
    echo   Push to 'vanshika' branch completed successfully!
    echo ===================================================
) else (
    echo.
    echo ===================================================
    echo Push failed or required authentication.
    echo You can open GitHub Desktop and click 'Push origin'.
    echo ===================================================
)
pause
