@echo off
cd /d "C:\Users\Macra\OneDrive\Desktop\stockscanner"
set LOGDIR=data\logs
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
set LOG=%LOGDIR%\morning_%date:~-4,4%%date:~-10,2%%date:~-7,2%.log
echo === %date% %time% === >> "%LOG%"
call ".venv\Scripts\activate.bat"
python -m stockscanner morning >> "%LOG%" 2>&1
