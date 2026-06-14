@echo off
cd /d "%~dp0"
set DAS_CLOUD_MODE=0
set DAS_DEMO_MODE=1
set DAS_DB_PATH=%CD%\cloud_demo_test.db
python server.py
pause
