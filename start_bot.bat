@echo off
cd /d "C:\Users\admin\Documents\Default Project"
:loop
"venv\Scripts\python.exe" bot.py
timeout /t 10 >nul
goto loop