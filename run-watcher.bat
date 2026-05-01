@echo off
set "SECURATRON_HOME=C:\Users\AMD\.securatron"
set "Path=C:\Users\AMD\.local\bin;%Path%"
cd /d "C:\work\SecuraTron"
uv run global\bin\inbox_watcher.py %*
