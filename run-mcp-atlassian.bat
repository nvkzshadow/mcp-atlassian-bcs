@echo off
REM Wrapper to run mcp-atlassian from this project (for Cursor MCP with local code).
REM Use this script as "command" in Cursor MCP config when workspace is not mcp-atlassian-bcs.
cd /d "%~dp0"
uv run mcp-atlassian %*
