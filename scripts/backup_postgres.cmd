@echo off
setlocal
pushd "%~dp0.."
if errorlevel 1 exit /b 1
python scripts/backup_postgres.py backup
set "backup_status=%errorlevel%"
echo.
pause
popd
exit /b %backup_status%
