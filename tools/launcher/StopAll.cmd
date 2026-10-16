@echo off
rem StopAll.cmd - end every editor process this installation started.
rem
rem It stops the background web server and its watchdog, removes the generated output and the
rem instance record, and keeps the logs. Use it when a page was closed without quitting, or when
rem a server is still listening on the port.
rem
rem Keep this file ASCII only: cmd.exe reads .cmd files in the OEM code page, and a stray
rem non-ASCII byte here silently breaks the whole script when double-clicked.
setlocal EnableExtensions
call "%~dp0_ff-tool-path.cmd" || exit /b 1
"%SHELL_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%TOOL%" stop
set "CODE=%ERRORLEVEL%"
echo.
pause
endlocal
exit /b %CODE%
