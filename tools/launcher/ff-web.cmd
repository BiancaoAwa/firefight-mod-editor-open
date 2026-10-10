@echo off
rem ff-web.cmd - double-click entry point: serve the read-only Firefight web UI.
rem The server runs hidden in the background (browser opens on the address) and the page gets
rem its own app window; this console closes, nothing is left open. Stop it from the page
rem (the quit link there) or with "ff-tool.cmd stop". Use "ff-tool.cmd web" to serve it in this
rem window instead. Keep this file ASCII only: cmd.exe reads .cmd files in the OEM code page,
rem and a stray non-ASCII byte here silently breaks the whole script when double-clicked.
setlocal EnableExtensions
set "SCRIPT=%~dp0ff-tool.ps1"
set "SHELL_EXE=pwsh"
where pwsh >nul 2>nul || set "SHELL_EXE=powershell"

if not exist "%SCRIPT%" (
  echo Cannot find "%SCRIPT%"
  pause
  exit /b 1
)

"%SHELL_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" web -Window %*
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" (
  echo.
  echo ff-tool exited with code %CODE%
  pause
)
endlocal
