@echo off
set "SECURATRON_HOME=C:\Users\AMD\.securatron"
if not exist "%SECURATRON_HOME%" (
    echo Initializing SecuraTron home at %SECURATRON_HOME%...
    mkdir "%SECURATRON_HOME%"
    xcopy /E /I /Y "%~dp0global" "%SECURATRON_HOME%\global"
    xcopy /E /I /Y "%~dp0projects" "%SECURATRON_HOME%\projects"
    xcopy /E /I /Y "%~dp0sessions" "%SECURATRON_HOME%\sessions"
    xcopy /E /I /Y "%~dp0inbox" "%SECURATRON_HOME%\inbox"
    xcopy /E /I /Y "%~dp0logs" "%SECURATRON_HOME%\logs"
) else (
    echo SecuraTron home already exists at %SECURATRON_HOME%.
)
