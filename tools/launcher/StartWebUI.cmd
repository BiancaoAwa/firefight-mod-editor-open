@echo off
rem StartWebUI.cmd - double-click entry point: serve the Firefight web UI in its own app window.
rem
rem The server runs hidden in the background, the page gets its own app window and a watchdog
rem closes the server when that window goes away. This console closes straight away; stop the
rem server from the page (the quit link there) or with StopAll.cmd.
rem
rem Options:
rem   -Scope <name>   scope to browse (default Mod, from Setting.toml; e.g. Firefight)
rem   -Port <n>       port to listen on (default: reuse the recorded instance, else a free port)
rem   -Project <dir>  serve this mod project instead (a directory with ModInformation.toml)
rem   -NoBrowser      start no page at all (hidden server, still watched)
rem   -Browser        open the page in the default browser instead of its own app window
rem   -Foreground     run the CLI in this console instead of the background launcher
rem
rem Keep this file ASCII only: cmd.exe reads .cmd files in the OEM code page, and a stray
rem non-ASCII byte here silently breaks the whole script when double-clicked.
setlocal EnableExtensions EnableDelayedExpansion
set "HERE=%~dp0"
call "%~dp0_ff-tool-path.cmd" || exit /b 1
set "SCOPE=Mod"
set "PORT="
set "MODE=window"
set "BROWSER=1"
set "PROJECT="
set "EXTRA="

rem Parse every argument first, then dispatch, so an option never skips the ones behind it.
:args
if "%~1"=="" goto dispatch
if /i "%~1"=="-Scope" (
  set "SCOPE=%~2"
  shift
) else if /i "%~1"=="-Port" (
  set "PORT=%~2"
  shift
) else if /i "%~1"=="-Project" (
  set "PROJECT=%~2"
  shift
) else if /i "%~1"=="-NoBrowser" (
  set "BROWSER=0"
) else if /i "%~1"=="-Browser" (
  set "BROWSER=2"
) else if /i "%~1"=="-Foreground" (
  set "MODE=foreground"
) else (
  set "EXTRA=!EXTRA! %~1"
)
shift
goto args

:dispatch
if "%MODE%"=="foreground" goto foreground

:window
set "PROJ_ARG="
if defined PROJECT set PROJ_ARG=-Project "%PROJECT%"
set "PORT_ARG="
if defined PORT set PORT_ARG=-Port %PORT%
set "BROWSER_ARG="
if "%BROWSER%"=="0" set "BROWSER_ARG=-NoBrowser"
if "%BROWSER%"=="2" set "BROWSER_ARG=-Browser"
"%SHELL_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%TOOL%" web -Window -Scope %SCOPE% !PORT_ARG! !PROJ_ARG! !BROWSER_ARG! !EXTRA!
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" (
  echo.
  echo ff-tool exited with code %CODE%
  pause
) else (
  rem the server is in the background now, so this window is the only place the port shows.
  echo.
  echo the editor keeps running; the address above is the one it answers on.
  echo this window closes by itself in 15 seconds.
  timeout /t 15 >nul
)
endlocal
exit /b %CODE%

:foreground
echo Firefight mod editor - web UI
echo   scope    %SCOPE%
echo   folder   %HERE%
echo.
pushd "%EDITOR%"
set "FBROWSER=1"
if "%BROWSER%"=="0" set "FBROWSER=0"
"%PYTHON%" -m core.cli %SCOPE% web "port=%PORT%" browser=%FBROWSER% %EXTRA%
set "CODE=%ERRORLEVEL%"
popd
if not "%CODE%"=="0" (
  echo.
  echo the editor CLI exited with code %CODE%
  pause
)
endlocal
exit /b %CODE%
