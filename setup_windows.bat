@echo off
cd /d "%~dp0"

echo Step 1 of 4: checking Python...
python --version
if errorlevel 1 goto no_python
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 goto old_python

echo.
echo Step 2 of 4: creating the virtual environment in .venv ...
python -m venv .venv
if errorlevel 1 goto failed

echo.
echo Step 3 of 4: installing Google ADK. This can take a few minutes...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed

echo.
echo Step 4 of 4: saving your Gemini API key in deadline_agent\.env
rem The agent is already in deadline_agent, so only the .env file is made here.
if not exist "deadline_agent\.env" goto ask_key
set "REPLACE="
set /p "REPLACE=deadline_agent\.env already exists. Replace it with a new key? (y/N) "
if /i not "%REPLACE%"=="y" goto keep_key

:ask_key
set "GEMINI_KEY="
set /p "GEMINI_KEY=Paste your Gemini API key and press Enter: "
if not defined GEMINI_KEY goto no_key
> "deadline_agent\.env" echo GOOGLE_GENAI_USE_ENTERPRISE=0
>> "deadline_agent\.env" echo GOOGLE_API_KEY=%GEMINI_KEY%
set "GEMINI_KEY="
if not exist "deadline_agent\.env" goto failed
echo.
echo Which Gemini model should Groot use?
echo   1. gemini-3.5-flash-lite: a much bigger free daily limit (recommended)
echo   2. gemini-3.5-flash: a little more accurate, but only about 20 requests a day
set "GROOT_CHOICE="
set /p "GROOT_CHOICE=Type 1 or 2 and press Enter (Enter alone picks 1): "
set "GROOT_PICK=gemini-3.5-flash-lite"
if "%GROOT_CHOICE%"=="2" set "GROOT_PICK=gemini-3.5-flash"
>> "deadline_agent\.env" echo GROOT_MODEL=%GROOT_PICK%
echo Saved, with %GROOT_PICK%.
echo You can change the model later on the GROOT_MODEL line of deadline_agent\.env.
goto done

:keep_key
echo Kept your existing deadline_agent\.env.

:done
echo.
echo All done. To start Groot, double-click start_groot.bat in this folder.
pause
exit /b 0

:no_key
echo.
echo No key was entered, so nothing was saved. Run this file again when you have your key.
pause
exit /b 1

:no_python
echo.
echo Python was not found. Install Python 3.11 or newer from python.org
echo and tick "Add python.exe to PATH" on the first screen, then run this file again.
pause
exit /b 1

:old_python
echo.
echo Your Python is older than 3.11. Install a newer version from python.org, then run this file again.
pause
exit /b 1

:failed
echo.
echo Something went wrong in the step above. Take a screenshot of this window and send it to Claude.
pause
exit /b 1
