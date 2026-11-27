@echo off
rem Double-click me: installs everything TV Hub needs on Windows (asks for administrator rights).
rem Add -Check to only report what is missing, -Yes for unattended mode, -Tasks to add the Tasks app (pop-ups).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Setup-TVHub.ps1" %*
pause
