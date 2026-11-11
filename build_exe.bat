@echo off
REM Build the Nusuk Question Automation exe (one file, console).
REM The exe does one thing: answer questions until it stops.
REM Run this from the repo folder. Needs: Python, pip install pyinstaller colorama
python make_icon.py
python -m PyInstaller --onefile --console --name nusuk_questions --icon icon.ico --hidden-import=colorama answer_questions.py
echo.
echo Done. The exe is in dist\nusuk_questions.exe
echo Double-click it to answer questions. Put it next to qa_bank.json
echo and adb.exe (+ AdbWinApi.dll, AdbWinUsbApi.dll).
pause
