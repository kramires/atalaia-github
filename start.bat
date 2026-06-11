@echo off
REM ATALAIA ComSoc — Starter Windows (2 clics, sem terminal)
REM Duplo clique neste arquivo = sistema inicia + navegador abre

echo ════════════════════════════════════════════════════════
echo   ATALAIA ComSoc — Sistema de Monitoramento de Mídia
echo ════════════════════════════════════════════════════════
echo.

cd /d "%~dp0"

echo Aguardando servidor iniciar...
timeout /t 5 /nobreak > nul

REM Inicia servidor em background
start "" python start.py

REM Aguarda servidor ficar pronto
timeout /t 5 /nobreak > nul

REM Abre navegador
start http://127.0.0.1:9001

echo ✓ Sistema iniciado!
echo ✓ Navegador abrindo...
echo.

exit
