@echo off
rem _ff-tool-path.cmd - locate the launcher engine, the interpreter and the editor root.
rem
rem Sets SHELL_EXE, TOOL, EDITOR and PYTHON for the entry points in this folder, so they work in
rem both shapes: the repository (tools\launcher\ with core\ two levels up) and the installed
rem editor (the entry points at the editor root, launcher\ beside them).
rem
rem Keep this file ASCII only: cmd.exe reads .cmd files in the OEM code page, and a stray
rem non-ASCII byte here silently breaks the whole script when double-clicked.
set "SHELL_EXE=pwsh"
where pwsh >nul 2>nul || set "SHELL_EXE=powershell"

set "TOOL="
set "EDITOR="
for %%D in ("%~dp0." "%~dp0.." "%~dp0..\..") do (
  if not defined TOOL if exist "%%~fD\ff-tool.ps1" set "TOOL=%%~fD\ff-tool.ps1"
  if not defined TOOL if exist "%%~fD\launcher\ff-tool.ps1" set "TOOL=%%~fD\launcher\ff-tool.ps1"
  if not defined EDITOR if exist "%%~fD\core\cli\__main__.py" set "EDITOR=%%~fD"
)
if not defined TOOL (
  echo Cannot find ff-tool.ps1 next to this launcher.
  exit /b 1
)
if not defined EDITOR (
  echo Cannot find core\cli\__main__.py - this launcher needs the editor core next to it.
  exit /b 1
)

rem The interpreter is a machine fact: FF_PYTHON names it, else the DSH copy, else PATH.
set "PYTHON=%FF_PYTHON%"
if not defined PYTHON if defined DSH_HOME set "PYTHON=%DSH_HOME%\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if not defined PYTHON set "PYTHON=python"
if not exist "%PYTHON%" set "PYTHON=python"
exit /b 0
