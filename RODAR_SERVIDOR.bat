@echo off
title Servidor Cantina (Python)
color 0A

echo ==========================================
echo      CONFIGURANDO SERVIDOR PYTHON
echo ==========================================
echo.

REM 1. Verificar Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    color 0C
    echo [ERRO] Python nao encontrado!
    echo Por favor, instale o Python no site python.org
    echo IMPORTANTE: Marque a opcao "Add Python to PATH" na instalacao.
    pause
    exit
)

REM 2. Criar ambiente virtual se nao existir (Pasta venv)
if not exist "venv" (
    echo Criando ambiente virtual para isolar dependencias...
    python -m venv venv
)

REM 3. Ativar ambiente e instalar dependencias
echo Ativando ambiente virtual...
call venv\Scripts\activate

echo Verificando e instalando bibliotecas (pode demorar na primeira vez)...
python -m pip install -r requirements.txt >nul

echo.
echo ==========================================
echo      SISTEMA INICIADO COM SUCESSO
echo ==========================================
echo.
echo O servidor esta rodando!
echo Abrindo o navegador automaticamente em 5 segundos...
echo.
echo [NAO FECHE ESTA JANELA PRETA ENQUANTO USAR O SISTEMA]
echo.

timeout /t 5
start http://localhost:8000
python main.py