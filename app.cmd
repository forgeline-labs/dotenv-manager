@echo off
setlocal
set PYTHONUTF8=1
python "%~dp0app" %*
exit /b %errorlevel%
