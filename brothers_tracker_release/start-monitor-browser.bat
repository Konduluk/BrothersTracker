@echo off
set "PROFILE=%LOCALAPPDATA%\BrothersTracker\chrome-profile"
set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" (
  echo Chrome not found. Install Google Chrome or adjust the path in this file.
  pause
  exit /b 1
)
start "" "%CHROME%" --remote-debugging-address=127.0.0.1 --remote-debugging-port=9222 --user-data-dir="%PROFILE%" "http://87.228.3.220/brotherhood/warriors"
