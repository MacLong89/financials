@echo off
title Stock Scanner Web
cd /d "C:\Users\Macra\OneDrive\Desktop\stockscanner"
call ".venv\Scripts\activate.bat"
echo Starting web dashboard at http://127.0.0.1:8787
echo Auto-scan: Mon-Fri 7:30 AM Mountain
python -m stockscanner web
pause
