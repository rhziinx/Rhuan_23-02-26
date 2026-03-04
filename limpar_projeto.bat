@echo off
title Limpeza do Projeto Cantina
color 0C

echo ==========================================
echo      LIMPANDO ARQUIVOS DESNECESSARIOS
echo ==========================================
echo.

if exist "saas-admin-preview.html" del "saas-admin-preview.html"
if exist "test-animations.html" del "test-animations.html"
if exist "separar_projetos.bat" del "separar_projetos.bat"
if exist "baixar_node_portatil.bat" del "baixar_node_portatil.bat"

echo.
echo [SUCESSO] Projeto limpo! Apenas os arquivos essenciais restaram.
echo Pode apagar este arquivo (limpar_projeto.bat) agora.
pause