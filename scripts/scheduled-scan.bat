@echo off
cd /d "C:\Users\Macra\OneDrive\Desktop\stockscanner"
set LOGDIR=data\logs
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
set LOG=%LOGDIR%\scan_%date:~-4,4%%date:~-10,2%%date:~-7,2%.log
echo === %date% %time% === >> "%LOG%"
".venv\Scripts\python.exe" -m stockscanner scan --alert >> "%LOG%" 2>&1
