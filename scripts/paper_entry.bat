@echo off
cd /d "C:\Users\Owner\Desktop\Claude Project\AI TRADRR"
"C:\Users\Owner\Desktop\Claude Project\AI TRADRR\.venv\Scripts\python.exe" -m trader.paper.entry_pipeline --once
exit /b %ERRORLEVEL%
