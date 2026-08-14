' Runs the given .bat with NO console window (window style 0) -- the fix
' for scheduled tasks flashing cmd windows over the owner's screen
' (2026-08-14). Waits for completion and passes the bat's real exit code
' through to the Task Scheduler, so Last Result still tells the truth
' about failures even though nothing is ever shown on screen.
Set sh = CreateObject("WScript.Shell")
WScript.Quit sh.Run("""" & WScript.Arguments(0) & """", 0, True)
