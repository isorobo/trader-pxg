@echo off
cd /d "C:\Users\Owner\Desktop\Claude Project\AI TRADRR"
"C:\Users\Owner\Desktop\Claude Project\AI TRADRR\.venv\Scripts\python.exe" -m trader.ground_truth.poll --once
exit /b %ERRORLEVEL%
