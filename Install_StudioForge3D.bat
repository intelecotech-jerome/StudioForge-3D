@echo off
chcp 65001 >nul
title Installation de StudioForge 3D v1.2.0
echo ============================================================================
echo    INSTALLATION AUTOMATIQUE DE STUDIOFORGE 3D (PC CLIENT / FAMILLE)
echo ============================================================================
echo.

cd /d "%~dp0"

echo [1/4] Verification et creation de l'environnement Python (.venv)...
cd /d "%~dp0backend"
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
)
call .venv\Scripts\pip.exe install --upgrade pip
call .venv\Scripts\pip.exe install -r requirements.txt

echo.
echo [2/4] Installation des modules graphiques 3D (Node.js / Three.js)...
cd /d "%~dp0frontend"
call npm install

echo.
echo [3/4] Compilation de verification de l'interface StudioForge 3D...
call npm run build

echo.
echo [4/4] Creation du raccourci "StudioForge 3D" avec icone officielle sur le Bureau Windows...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$WshShell = New-Object -ComObject WScript.Shell; $Desktop = [Environment]::GetFolderPath('Desktop'); $Shortcut = $WshShell.CreateShortcut((Join-Path $Desktop 'StudioForge 3D.lnk')); $Shortcut.TargetPath = '%~dp0Lancer_StudioForge3D.bat'; $Shortcut.WorkingDirectory = '%~dp0'; $Shortcut.IconLocation = '%~dp0frontend\public\studioforge-icon.ico'; $Shortcut.Description = 'Lancer StudioForge 3D - HueForge, Lumina 3D & SmartCut 3D'; $Shortcut.Save()"

echo.
echo ============================================================================
echo  INSTALLATION TERMINEE AVEC SUCCES !
echo  Un raccourci "StudioForge 3D" avec son icone a ete ajoute sur votre Bureau.
echo  Vous pouvez maintenant lancer StudioForge 3D et activer votre cle SF3D-...
echo ============================================================================
pause

