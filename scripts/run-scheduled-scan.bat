@echo off
cd /d "C:\Users\Macra\OneDrive\Desktop\stockscanner"
if not exist "data\logs" mkdir "data\logs"
set LOG=data\logs\scan_%date:~-4,4%%date:~-10,2%%date:~-7,2%.log
echo === %date% %time% === >> "%LOG%"
call ".venv\Scripts\python.exe" -m stockscanner scan --alert >> "%LOG%" 2>&1
