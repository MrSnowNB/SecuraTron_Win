@echo off
set "SECURATRON_HOME=C:\Users\AMD\.securatron"
if not exist "%SECURATRON_HOME%" (
    echo Initializing SecuraTron home at %SECURATRON_HOME%...
    mkdir "%SECURATRON_HOME%"
    xcopy /E /I /Y "C:\work\SecuraTron\global" "%SECURATRON_HOME%\global"
    xcopy /E /I /Y "C:\work\SecuraTron\projects" "%SECURATRON_HOME%\projects"
    xcopy /E /I /Y "C:\work\SecuraTron\sessions" "%SECURATRON_HOME%\sessions"
    xcopy /E /I /Y "C:\work\SecuraTron\inbox" "%SECURATRON_HOME%\inbox"
    xcopy /E /I /Y "C:\work\SecuraTron\logs" "%SECURATRON_HOME%\logs"
) else (
    echo SecuraTron home already exists at %SECURATRON_HOME%.
)
