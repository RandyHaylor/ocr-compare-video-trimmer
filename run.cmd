@echo off
rem Windows launcher for double-clicking or cmd.exe; runs run.ps1 without changing the script policy.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
