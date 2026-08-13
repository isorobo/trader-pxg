@echo off
cd /d "C:\Users\Owner\Desktop\Claude Project\AI TRADRR"
"C:\Users\Owner\Desktop\Claude Project\AI TRADRR\.venv\Scripts\python.exe" -m trader.paper.daily_digest --once
exit /b %ERRORLEVEL%
