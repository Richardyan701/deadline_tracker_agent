@echo off
rem Starts Agent Groot on Windows and opens its home page in your browser.
rem Double click this file, or run it from Command Prompt. Press Ctrl+C to stop Groot.
cd /d "%~dp0"
rem This file also runs a second copy of itself in the background, to open the browser (see below)
if "%~1"=="open_browser" goto open_browser

if not exist ".venv\Scripts\python.exe" goto not_set_up
if not exist "deadline_agent\.env" goto not_set_up

rem The background copy waits for the server, then opens the browser. The server itself must
rem run here in the front, because a program started with "start /b" ignores Ctrl+C.
start "" /b cmd /c ""%~f0" open_browser"

echo Starting Groot. This can take a few seconds...
rem Groot's web app: its pages and the chat, on one server. Started through Python,
rem because some antivirus programs block the programs that pip puts in .venv\Scripts.
".venv\Scripts\python.exe" -m web
echo.
echo Groot has stopped.
pause
exit /b 0

:open_browser
rem curl (built into Windows 10 and 11) asks once a second, for up to a minute, until Groot's home page answers.
rem --fail counts an error page as no answer, so a different program on port 8000 never opens in the browser.
curl.exe --silent --fail --noproxy "*" --output nul --retry 60 --retry-delay 1 --retry-connrefused http://127.0.0.1:8000/groot
if errorlevel 1 (
    echo Groot did not answer, so your browser was not opened. Read the messages above.
    exit /b 1
)
start "" http://127.0.0.1:8000/groot
echo.
echo Groot is running at http://127.0.0.1:8000/groot
echo Press Ctrl+C in this window to stop it.
exit /b 0

:not_set_up
echo Groot is not set up yet, so please run setup_windows.bat first.
pause
exit /b 1
