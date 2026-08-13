@echo off
cd /d "C:\Users\Owner\Desktop\Claude Project\AI TRADRR"
"C:\Users\Owner\Desktop\Claude Project\AI TRADRR\.venv\Scripts\python.exe" -m trader.paper.gateway_watchdog --once
exit /b %ERRORLEVEL%
