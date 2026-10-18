@echo off
cd /d "%~dp0"
python game.py
if errorlevel 1 pause
