@echo off
title Limpeza de Arquivos Temporarios - Cantina
color 0E

echo ==========================================
echo      LIMPANDO ARQUIVOS OBSOLETOS
echo ==========================================
echo.
echo Deletando arquivos redundantes da tentativa de modularizacao...

if exist "models.py" (
    del "models.py"
    echo [OK] models.py removido.
)

if exist "database.py" (
    del "database.py"
    echo [OK] database.py removido.
)

if exist "app" (
    rmdir /s /q "app"
    echo [OK] Pasta 'app' removida.
)

echo.
echo ==========================================
echo      LIMPEZA CONCLUIDA!
echo ==========================================
echo.
echo Agora seu projeto esta limpo e organizado.
echo Pode continuar usando o RODAR_SERVIDOR.bat normalmente.
echo.
pause