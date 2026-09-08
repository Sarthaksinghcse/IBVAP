@echo off
title Push SHIELD Changes to sarthak Branch
cd /d "%~dp0"
echo ===================================================
echo   Pushing latest changes to remote (origin/sarthak)...
echo ===================================================
"C:\Users\thaku\AppData\Local\GitHubDesktop\app-3.6.5\resources\app\git\cmd\git.exe" push -u origin sarthak
if %ERRORLEVEL% equ 0 (
    echo.
    echo ===================================================
    echo   Push to 'sarthak' branch completed successfully!
    echo ===================================================
) else (
    echo.
    echo ===================================================
    echo Push prompt required authentication.
    echo You can also open GitHub Desktop and click 'Publish branch'.
    echo ===================================================
)
pause
