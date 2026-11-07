"""
StudioForge 3D — Standalone Windows Executable Entrypoint (`StudioForge3D.exe`)
Starts the embedded FastAPI + Three.js/React static server on http://127.0.0.1:8000,
automatically creates the "StudioForge 3D" shortcut on the Windows Desktop on first run,
and opens a native-style Desktop App window (Edge/Chrome --app mode or default browser).
Requires ZERO Python and ZERO Node.js installation on the client's machine.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import threading
import time
import webbrowser
import uvicorn

from main import app


def _ensure_desktop_shortcut() -> None:
    """Creates a 'StudioForge 3D' shortcut on the Windows Desktop pointing to StudioForge3D.exe."""
    if not getattr(sys, "frozen", False):
        return
    try:
        exe_path = pathlib.Path(sys.executable).resolve()
        exe_dir = exe_path.parent
        icon_path = exe_dir / "_internal" / "frontend_dist" / "studioforge-icon.ico"
        if not icon_path.exists():
            icon_path = exe_path
        ps_cmd = (
            "$WshShell = New-Object -ComObject WScript.Shell; "
            "$Desktop = [Environment]::GetFolderPath('Desktop'); "
            "$lnk = Join-Path $Desktop 'StudioForge 3D.lnk'; "
            "if (-not (Test-Path $lnk)) { "
            "$s = $WshShell.CreateShortcut($lnk); "
            f"$s.TargetPath = '{exe_path}'; "
            f"$s.WorkingDirectory = '{exe_dir}'; "
            f"$s.IconLocation = '{icon_path}'; "
            "$s.Description = 'StudioForge 3D - HueForge Studio, Lumina 3D & SmartCut 3D'; "
            "$s.Save() }"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
            capture_output=True,
            timeout=5,
        )
    except Exception:
        pass


def _open_desktop_window(url: str) -> None:
    time.sleep(1.5)
    edge_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for ep in edge_paths:
        if os.path.exists(ep):
            try:
                subprocess.Popen([ep, f"--app={url}", "--start-maximized"])
                return
            except Exception:
                pass
    webbrowser.open(url)


if __name__ == "__main__":
    _ensure_desktop_shortcut()
    url = "http://127.0.0.1:8000"
    print("==================================================================")
    print("  STUDIOFORGE 3D v1.3.0 - APPLICATION DESKTOP AUTONOME (.EXE)")
    print(f"  Ouverture de l'interface sur {url} ...")
    print("  (Un raccourci 'StudioForge 3D' a ete ajoute sur votre Bureau)")
    print("  (Gardez cette fenetre reduite pendant votre session de travail)")
    print("==================================================================")
    threading.Thread(target=_open_desktop_window, args=(url,), daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
