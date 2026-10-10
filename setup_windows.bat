@echo off
cd /d "%~dp0"

echo Step 1 of 4: checking Python...
python --version
if errorlevel 1 goto no_python
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
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
echo Step 4 of 4: creating the agent project.
echo When asked to choose a backend, type 1 for Google AI and press Enter.
echo Then paste your Gemini API key and press Enter.
".venv\Scripts\adk.exe" create deadline_agent --model gemini-3.5-flash
if errorlevel 1 goto failed

echo.
echo All done. You can close this window.
pause
exit /b 0

:no_python
echo.
echo Python was not found. Install Python 3.10 or newer from python.org
echo and tick "Add python.exe to PATH" on the first screen, then run this file again.
pause
exit /b 1

:old_python
echo.
echo Your Python is older than 3.10. Install a newer version from python.org, then run this file again.
pause
exit /b 1

:failed
echo.
echo Something went wrong in the step above. Take a screenshot of this window and send it to Claude.
pause
exit /b 1
