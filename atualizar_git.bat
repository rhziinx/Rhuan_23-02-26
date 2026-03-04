@echo off
title Atualizar Git - Cantina Enterprise
color 0A

echo ==========================================
echo      SALVANDO VERSAO NO GIT
echo ==========================================
echo.

REM 1. Verificar se Git existe
git --version >nul 2>&1
if %errorlevel% neq 0 (
    color 0C
    echo [ERRO] O Git nao esta instalado ou nao esta no PATH.
    echo Baixe em: https://git-scm.com/
    pause
    exit
)

REM 2. Inicializar se necessario
if not exist ".git" (
    echo Inicializando repositorio Git...
    git init
)

REM 3. Adicionar todos os arquivos
echo Adicionando arquivos ao controle de versao...
git add .

REM 4. Commit
set "DATA=%date:/=-%_%time::=-%"
set "MSG=Atualizacao automatica Cantina Enterprise %DATA%"

echo Criando commit: "%MSG%"
git commit -m "%MSG%"

echo.
echo [SUCESSO] Arquivos salvos no Git localmente!
echo.

REM 5. Push opcional
echo Se voce ja configurou um repositorio remoto (GitHub), o script tentara enviar.
echo Caso contrario, dara um aviso (que voce pode ignorar se usar apenas localmente).
echo.
git push

pause