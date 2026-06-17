@echo off
cd /d "C:\Users\Macra\OneDrive\Desktop\stockscanner"
start "StockScannerWeb" /MIN cmd /c ".venv\Scripts\python.exe -m stockscanner web"
