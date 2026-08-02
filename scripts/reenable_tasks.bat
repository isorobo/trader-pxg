@echo off
rem One-shot: re-enables all Trader AI scheduled tasks after a temporary
rem owner-requested pause (2026-08-01), then removes the trigger task itself.
schtasks /Change /TN "TraderGroundTruthPoll" /ENABLE
schtasks /Change /TN "TraderPaperEntry" /ENABLE
schtasks /Change /TN "TraderPaperGuardian" /ENABLE
schtasks /Change /TN "TraderPaperReconcile" /ENABLE
schtasks /Change /TN "TraderCryptoEntry" /ENABLE
schtasks /Change /TN "TraderAITournament" /ENABLE
schtasks /Delete /TN "TraderReenableOneShot" /F
exit /b 0
