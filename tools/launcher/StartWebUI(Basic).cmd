@echo off
rem StartWebUI(Basic).cmd - serve the Firefight web UI in this console.
rem
rem The basic entry keeps everything in the window it was started from: no background server, no
rem app window and no watchdog, so closing the console stops the server. Use StartWebUI.cmd for
rem the windowed form, or StopAll.cmd to end anything left behind.
rem
rem Options:
rem   -Scope <name>   scope to browse (default Mod, from Setting.toml; e.g. Firefight)
rem   -Port <n>       port to listen on (default: reuse the recorded instance, else a free port)
rem   -Project <dir>  serve this mod project instead (a directory with ModInformation.toml)
rem   -NoBrowser      print the address instead of opening a page
rem
rem Keep this file ASCII only: cmd.exe reads .cmd files in the OEM code page, and a stray
rem non-ASCII byte here silently breaks the whole script when double-clicked.
setlocal EnableExtensions EnableDelayedExpansion
set "HERE=%~dp0"
call "%~dp0_ff-tool-path.cmd" || exit /b 1
set "SCOPE=Mod"
set "PORT="
set "BROWSER=1"
set "PROJECT="

:args
if "%~1"=="" goto run
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
)
shift
goto args

:run
echo Firefight mod editor - web UI (basic)
echo   scope    %SCOPE%
echo   folder   %EDITOR%
echo.
set "PROJ_ARG="
if defined PROJECT set PROJ_ARG=-Project "%PROJECT%"
set "PORT_ARG="
if defined PORT set PORT_ARG=-Port %PORT%
set "BROWSER_ARG=-Browser"
if "%BROWSER%"=="0" set "BROWSER_ARG=-NoBrowser"
"%SHELL_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%TOOL%" web -Scope %SCOPE% !PORT_ARG! !PROJ_ARG! !BROWSER_ARG!
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" (
  echo.
  echo ff-tool exited with code %CODE%
  pause
)
endlocal
exit /b %CODE%
