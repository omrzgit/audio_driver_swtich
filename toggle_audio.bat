@echo off
:: Audio Config Switcher — double-click to toggle
:: Place this .bat file in the same folder as audio_switcher.py

cd /d "%~dp0"
python audio_switcher.py %*
if errorlevel 1 (
    echo.
    echo [error] Script failed. See above for details.
    pause
)
