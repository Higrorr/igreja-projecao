@echo off
rem Chama configurar.ps1 (que se auto-eleva com UAC). Basta dar dois cliques aqui.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0configurar.ps1"