@echo off
chcp 65001 >nul
title StudioForge 3D - Demarrage en cours...
echo ============================================================================
echo    STUDIOFORGE 3D v1.2.0 - SUITE DE GEOMETRIE COMPUTATIONNELLE ^& CFS
echo ============================================================================
echo.

cd /d "%~dp0"

:: 1. Demarrer le serveur Backend Python FastAPI (Port 8000)
echo [1/3] Demarrage du moteur geometrique Python (Port 8000)...
start "StudioForge 3D - Moteur Backend" /min cmd /c "cd /d "%~dp0backend" && .venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000"

:: 2. Demarrer le serveur Frontend React/Three.js (Port 5173)
echo [2/3] Demarrage de l'interface graphique StudioForge 3D (Port 5173)...
start "StudioForge 3D - Interface Web" /min cmd /c "cd /d "%~dp0frontend" && npm run dev"

:: 3. Attendre 3 secondes puis ouvrir le navigateur
echo [3/3] Ouverture de StudioForge 3D dans votre navigateur...
timeout /t 3 /nobreak >nul
start http://localhost:5173

echo.
echo StudioForge 3D est lance ! Vous pouvez reduire ces fenetres pendant votre travail.
exit

