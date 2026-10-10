@echo off
rem One-click stop: end leftover editor processes, clean the generated output, keep the log.
call "%~dp0ff-tool.cmd" stop
echo.
pause
