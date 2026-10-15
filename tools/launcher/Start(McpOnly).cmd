@echo off
rem Start(McpOnly).cmd - run the editor as an MCP server on stdio, with no web UI and no window.
rem
rem The server speaks the Model Context Protocol over stdin/stdout, so an AI host starts it and
rem talks to it; a double-click only shows the startup lines and waits on stdin. Pass --write to
rem register the tools that write (set, add, remove, index, convert, settings, undo, redo, init,
rem pack, export); without it the server registers the read-only tools only.
rem
rem Usage:
rem   Start(McpOnly).cmd [--write] [root=<dir>] [workspace=<dir>]
rem
rem Keep this file ASCII only: cmd.exe reads .cmd files in the OEM code page, and a stray
rem non-ASCII byte here silently breaks the whole script when double-clicked.
setlocal EnableExtensions EnableDelayedExpansion
call "%~dp0_ff-tool-path.cmd" || exit /b 1
pushd "%EDITOR%"
"%PYTHON%" -m core.mcp %*
set "CODE=%ERRORLEVEL%"
popd
endlocal
exit /b %CODE%
