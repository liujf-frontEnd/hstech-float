@echo off
REM 备用启动（一般用 .vbs 更干净）
cd /d "%~dp0"
start "" pythonw "%~dp0hstech_float.py"
