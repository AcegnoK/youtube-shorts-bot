@echo off
cd /d "C:\Users\admin\Documents\Default Project\youtube-shorts-bot"
:loop
"venv\Scripts\python.exe" bot.py
timeout /t 10 >nul
goto loop
