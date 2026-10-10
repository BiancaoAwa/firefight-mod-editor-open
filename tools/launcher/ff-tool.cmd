@echo off
rem ff-tool.cmd - double-click entry point for ff-tool.ps1 (the Firefight mod editor tool).
rem No arguments -> "start" and the window stays open, with the `ff` shortcut ready.
rem Keep this file ASCII only: cmd.exe reads .cmd files in the OEM code page, and a stray
rem non-ASCII byte here silently breaks the whole script when it is double-clicked.
setlocal EnableExtensions EnableDelayedExpansion
set "SCRIPT=%~dp0ff-tool.ps1"
set "ARGS=%*"

if not exist "%SCRIPT%" (
  echo Cannot find "%SCRIPT%"
  pause
  exit /b 1
)

set "SHELL_EXE=pwsh"
where pwsh >nul 2>nul || set "SHELL_EXE=powershell"

if "%ARGS%"=="" (
  "%SHELL_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -NoExit -File "%SCRIPT%" start
) else (
  "%SHELL_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %ARGS%
  if errorlevel 1 (
    echo.
    echo ff-tool exited with a non-zero code (!ERRORLEVEL!)
    pause
  )
)
endlocal
