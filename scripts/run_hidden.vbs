' Runs the given .bat with NO console window (window style 0) -- the fix
' for scheduled tasks flashing cmd windows over the owner's screen
' (2026-08-14). Fire-and-forget: the task scheduler still records the
' bat's exit via wscript, and all output continues to land in the ops
' log / DB exactly as before.
Set sh = CreateObject("WScript.Shell")
sh.Run """" & WScript.Arguments(0) & """", 0, False
