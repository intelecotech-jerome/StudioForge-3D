@echo off
chcp 65001 >nul
title Compilation de StudioForge3D.exe (Version Client Sans Python ni Node.js)
echo ============================================================================
echo   COMPILATION DE STUDIOFORGE 3D EN EXECUTABLE WINDOWS AUTONOME (.EXE)
echo   (Aucun prérequis Python ni Node.js nécessaire chez vos clients / fille)
echo ============================================================================
echo.

cd /d "%~dp0"

echo [1/4] Compilation de l'interface graphique 3D (React / Three.js)...
cd /d "%~dp0frontend"
call npm run build

echo.
echo [2/4] Verification de PyInstaller dans l'environnement Python...
cd /d "%~dp0backend"
call .venv\Scripts\pip.exe install pyinstaller

echo.
echo [3/4] Generation de StudioForge3D.exe avec l'icone officielle...
echo       (Securite : la cle privee .admin_private_key.json n'est JAMAIS incluse)
call .venv\Scripts\pyinstaller.exe --noconfirm --clean ^
    --onedir ^
    --name "StudioForge3D" ^
    --icon "%~dp0frontend\public\studioforge-icon.ico" ^
    --add-data "%~dp0frontend\dist;frontend_dist" ^
    --collect-all trimesh ^
    --collect-all shapely ^
    --collect-all scipy ^
    studioforge_desktop.py

echo.
echo [4/4] Creation de l'archive prete a publier sur GitHub Releases...
if not exist "%~dp0Release_Client_GitHub" mkdir "%~dp0Release_Client_GitHub"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path '%~dp0backend\dist\StudioForge3D\*' -DestinationPath '%~dp0Release_Client_GitHub\StudioForge3D_Windows_x64_v1.2.0.zip' -Force"

echo.
echo ============================================================================
echo  TERMINE AVEC SUCCES !
echo  1) Dossier executable autonome : backend\dist\StudioForge3D\StudioForge3D.exe
echo  2) Archive ZIP pour GitHub Releases : Release_Client_GitHub\StudioForge3D_Windows_x64_v1.2.0.zip
echo  Votre fille ou vos clients n'ont qu'a lancer StudioForge3D.exe (0 installation !)
echo ============================================================================
pause

