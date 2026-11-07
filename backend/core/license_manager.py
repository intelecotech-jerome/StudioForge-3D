"""
StudioForge 3D — Asymmetric RSA License Manager & GitHub Update Service
- Public Key (N, e=65537) is embedded in client distributions for offline/online verification.
- Private Key (d) resides ONLY in `backend/data/.admin_private_key.json` (git-ignored, never shipped to clients).
- Supports modular unlocking:
    * Base Pack (20 €): HueForge Studio + Lumina 3D
    * Add-on Module (+5 €): SmartCut 3D
    * Add-on Module (+5 €): Puzzle & Cryptex 3D
    * Full Pack: All modules unlocked
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import json
import os
import platform
import secrets
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/license", tags=["License & Updates"])

APP_NAME = "StudioForge 3D"
APP_VERSION = "1.3.0"
APP_RELEASE_DATE = "2026-11-07"

# ---------------------------------------------------------------------------
# RSA-512 Public Key for Offline Signature with Message Recovery
# (Safe to distribute on GitHub — cannot sign or forge keys without Private d)
# ---------------------------------------------------------------------------
PUBLIC_MODULUS_HEX = (
    "9c35931b4d8e31fdd9b448544f2fac1a39e35f7b398bb7019a29415777865f16"
    "952b942d68d52d29f2f56098a6112d2cdc1d5baa0dd8296be7e221e6b9eee2df"
)
PUBLIC_MODULUS = int(PUBLIC_MODULUS_HEX, 16)
PUBLIC_EXP = 65537

import sys

if getattr(sys, "frozen", False):
    DATA_DIR = Path(sys.executable).resolve().parent / "data"
else:
    DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
ADMIN_PRIVATE_KEY_PATH = DATA_DIR / ".admin_private_key.json"
LICENSE_STATE_PATH = DATA_DIR / "license_state.json"
VERSION_MANIFEST_PATH = DATA_DIR / "version_manifest.json"

# Bitmask mapping for StudioForge 3D modules
MODULE_BITS: Dict[str, int] = {
    "hueforge": 1 << 0,    # 🎨 HueForge Studio
    "lithophane": 1 << 1,  # 💡 Lumina 3D
    "smartcut": 1 << 2,    # ✂️ SmartCut 3D
    "puzzles": 1 << 3,     # 🧩 Puzzle & Cryptex 3D
    "wirepress": 1 << 4,   # 👕 WirePress 3D (Transfert Textile à Chaud)
    "makerlab": 1 << 5,    # 🛠️ MakerLab 3D (8 Outils Créatifs)
}

MODULE_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "hueforge",
        "name": "HueForge Studio",
        "icon": "🎨",
        "tagline": "Peinture par couches de filaments (2 à 8 couleurs CFS), Puzzle & Pop-Out 3D",
        "price_label": "Inclus Pack Base (20 €)",
        "addon_price_eur": 20,
        "highlights": [
            "Moteurs Rampe Manga HSV & Solveur Optique CIELAB ΔE",
            "Extension 3D Pop-Out (.STL ou Sujet 2D Gonflé 3D) & Socle Incliné",
            "6 styles artistiques 3D, Puzzle 3D & export direct .3MF / .STL",
        ],
    },
    {
        "id": "lithophane",
        "name": "Lumina 3D",
        "icon": "💡",
        "tagline": "Lithophanies plates, cylindres 360°, cubes LED, puzzles & globes planétaires",
        "price_label": "Inclus Pack Base (20 €)",
        "addon_price_eur": 20,
        "highlights": [
            "Plaques multi-formes, Cylindres 360°, Caissons, Cubes & Puzzles Lightbox",
            "Globes sphériques 360° (Photo sur mesure ou 11 Planètes & Lune NASA)",
            "Simulation rétro-éclairage LED RGB & standards de socles Bambu / E14 / GU10",
        ],
    },
    {
        "id": "wirepress",
        "name": "WirePress 3D",
        "icon": "👕",
        "tagline": "Structures filaires 3D & Grille Cell à presser à chaud sur T-Shirt & Pull",
        "price_label": "Extension +5 €",
        "addon_price_eur": 5,
        "highlights": [
            "Conversion Photo/Portrait/Logo ➔ Structure Filaire 3D & Grille Tramée Cell",
            "Simulateur d'essayage textile en direct (T-Shirt, Hoodie, Tote Bag & Bobines Stock)",
            "Calibrage pressage à chaud (PLA+ / TPU) & ponts anti-îlots automatiques",
        ],
    },
    {
        "id": "makerlab",
        "name": "MakerLab 3D",
        "icon": "🛠️",
        "tagline": "8 générateurs créatifs : Emporte-pièce, Boîte 3D, Flexi, Bas-Relief & IA 3D",
        "price_label": "Extension +5 € (Bêta)",
        "addon_price_eur": 5,
        "highlights": [
            "Emporte-Pièces & Tampons, Boîtes 3D, Flexi Articulés & Mandala Multi-Couches",
            "Conversion .STL ➔ Bas-Relief encadré & Sculpture IA Photo/Texte ➔ 3D (Style Meshy)",
            "Illusion Lenticulaire 2-Angles & Morphing 3D Dual-90°",
        ],
    },
    {
        "id": "smartcut",
        "name": "SmartCut 3D",
        "icon": "✂️",
        "tagline": "Découpe grands formats, tiges de renfort Brico & connecteurs numérotés",
        "price_label": "Extension +5 €",
        "addon_price_eur": 5,
        "highlights": [
            "Découpe planaire automatique (Auto-Grid) calibrée Creality K1 Max / Hi",
            "Tunnel de renfort Brico 1 mètre & alignement vertical automatique PCA",
            "Tenons coniques hexagonaux/carrés auto-bloquants & numérotation 3D gravée",
        ],
    },
    {
        "id": "puzzles",
        "name": "Puzzle & Cryptex 3D",
        "icon": "🧩",
        "tagline": "Boîtes secrètes, puzzles géométriques 3D & mécanismes à combinaison",
        "price_label": "Extension +5 € (Bientôt)",
        "addon_price_eur": 5,
        "coming_soon": True,
        "highlights": [
            "Découpe de modèles 3D en puzzles autobloquants à tolérance paramétrique",
            "Cylindres Cryptex à bagues rotatives personnalisables",
            "Boîtes à labyrinthe interne caché",
        ],
    },
]


def _get_machine_fingerprint() -> str:
    raw = f"{platform.node()}|{platform.machine()}|{platform.processor()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12].upper()


def _is_admin_machine() -> bool:
    return ADMIN_PRIVATE_KEY_PATH.is_file()


def _sign_license_payload(holder: str, modules: List[str], max_machines: int = 3) -> str:
    """
    Signs a 53-byte license message using the private RSA exponent `d` stored ONLY on the Admin PC.
    Returns a formatted key: `SF3D-<TAG>-<BASE32_CHUNKS>`.
    """
    if not _is_admin_machine():
        raise HTTPException(
            status_code=403,
            detail="Clé privée administrateur introuvable sur ce poste. La génération de clés est réservée au créateur.",
        )
    priv_data = json.loads(ADMIN_PRIVATE_KEY_PATH.read_text(encoding="utf-8"))
    d = int(priv_data["d_hex"], 16)
    n = int(priv_data["n_hex"], 16)

    mask = 0
    for m in modules:
        mask |= MODULE_BITS.get(m, 0)

    epoch_2025 = datetime.date(2025, 1, 1)
    days_since = max(0, min(65535, (datetime.date.today() - epoch_2025).days))

    clean_holder = (holder.strip() or "Client StudioForge 3D").encode("utf-8")[:24]
    holder_padded = clean_holder.ljust(24, b"\x00")
    salt = secrets.token_bytes(4)

    # 37-byte body: 4B magic + 1B ver + 1B mask + 1B max_machines + 2B days + 24B holder + 4B salt
    body = (
        b"SF3D"
        + bytes([1, mask & 0xFF, max(1, min(25, max_machines))])
        + days_since.to_bytes(2, "big")
        + holder_padded
        + salt
    )
    checksum = hashlib.sha256(body).digest()[:16]
    payload = body + checksum  # 53 bytes (424 bits < 512 bits)

    m_int = int.from_bytes(payload, "big")
    sig_int = pow(m_int, d, n)
    sig_bytes = sig_int.to_bytes(64, "big")
    b32 = base64.b32encode(sig_bytes).decode("ascii").rstrip("=")

    # Human-readable tag indicating the pack type
    if mask == 0x0F or (mask & 0x07) == 0x07:
        tag = "FULL"
    elif (mask & 0x03) == 0x03 and not (mask & 0x04):
        tag = "BASE20"
    elif mask == 0x04:
        tag = "ADDCUT"
    elif mask == 0x08:
        tag = "ADDPUZ"
    else:
        tag = f"MOD{mask:02X}"

    chunks = [b32[i : i + 6] for i in range(0, len(b32), 6)]
    return f"SF3D-{tag}-" + "-".join(chunks)


def verify_license_key(key_str: str) -> Dict[str, Any]:
    """
    Verifies a `SF3D-...` license key using ONLY the embedded RSA Public Key `(PUBLIC_MODULUS, PUBLIC_EXP)`.
    Recovers the signed payload and validates its 128-bit SHA-256 integrity signature.
    """
    cleaned = key_str.strip().upper().replace(" ", "")
    if not cleaned.startswith("SF3D-"):
        raise ValueError("Format de clé invalide (doit commencer par SF3D-).")

    parts = cleaned.split("-")
    if len(parts) < 4:
        raise ValueError("Clé de licence incomplète.")

    b32_body = "".join(parts[2:])
    pad_len = (8 - (len(b32_body) % 8)) % 8
    try:
        sig_bytes = base64.b32decode(b32_body + ("=" * pad_len))
    except Exception as exc:
        raise ValueError("Caractères invalides dans la clé de licence.") from exc

    if len(sig_bytes) != 64:
        raise ValueError("Longueur cryptographique de la clé invalide.")

    sig_int = int.from_bytes(sig_bytes, "big")
    if sig_int <= 0 or sig_int >= PUBLIC_MODULUS:
        raise ValueError("Signature hors domaine RSA.")

    m_int = pow(sig_int, PUBLIC_EXP, PUBLIC_MODULUS)
    try:
        payload = m_int.to_bytes(53, "big")
    except OverflowError as exc:
        raise ValueError("Signature RSA invalide (clé altérée ou non officielle).") from exc

    if payload[:4] != b"SF3D" or payload[4] != 1:
        raise ValueError("Clé de licence non reconnue par StudioForge 3D.")

    body = payload[:37]
    expected_chk = payload[37:53]
    actual_chk = hashlib.sha256(body).digest()[:16]
    if actual_chk != expected_chk:
        raise ValueError("Signature cryptographique invalide (clé corrompue).")

    mask = payload[5]
    max_machines = payload[6]
    days_since = int.from_bytes(payload[7:9], "big")
    holder = payload[9:33].rstrip(b"\x00").decode("utf-8", errors="replace")
    issued_date = (datetime.date(2025, 1, 1) + datetime.timedelta(days=days_since)).isoformat()

    unlocked = [mod_id for mod_id, bit in MODULE_BITS.items() if (mask & bit) != 0]
    return {
        "valid": True,
        "holder": holder,
        "unlocked_modules": unlocked,
        "max_machines": max_machines,
        "issued_date": issued_date,
        "key_ normalized": cleaned,
    }


def _load_license_state() -> Dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if LICENSE_STATE_PATH.is_file():
        try:
            data = json.loads(LICENSE_STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                if _is_admin_machine():
                    changed = False
                    for req_m in ("wirepress", "makerlab"):
                        if req_m not in data.get("unlocked_modules", []):
                            data.setdefault("unlocked_modules", []).append(req_m)
                            changed = True
                    if changed:
                        _save_license_state(data)
                return data
        except Exception:
            pass

    # Default initial state:
    # If running on the Creator's Admin PC (`.admin_private_key.json` present), unlock all modules by default
    if _is_admin_machine():
        default_state = {
            "holder": "Créateur / Administrateur StudioForge 3D",
            "unlocked_modules": ["hueforge", "lithophane", "wirepress", "makerlab", "smartcut", "puzzles"],
            "activated_keys": [],
            "client_simulation_mode": None,  # Optional override to preview what a client sees
        }
    else:
        # On a fresh client installation (before entering a license key), no paid modules are unlocked yet
        default_state = {
            "holder": "Version Non Activée (En attente de clé)",
            "unlocked_modules": [],
            "activated_keys": [],
            "client_simulation_mode": None,
        }
    _save_license_state(default_state)
    return default_state


def _save_license_state(state: Dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LICENSE_STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _build_status_response(state: Dict[str, Any]) -> Dict[str, Any]:
    is_admin = _is_admin_machine()
    sim_mode = state.get("client_simulation_mode") if is_admin else None

    if sim_mode == "unlicensed":
        effective_modules: List[str] = []
        effective_holder = "Simulation Client : Non Activé (0 €)"
    elif sim_mode == "pack_20":
        effective_modules = ["hueforge", "lithophane"]
        effective_holder = "Simulation Client : Pack Base 20 € (HueForge + Lumina)"
    elif sim_mode == "pack_25_smartcut":
        effective_modules = ["hueforge", "lithophane", "smartcut"]
        effective_holder = "Simulation Client : Pack 20 € + SmartCut (+5 €)"
    elif sim_mode == "full":
        effective_modules = ["hueforge", "lithophane", "smartcut", "puzzles"]
        effective_holder = "Simulation Client : Pack Intégral"
    else:
        effective_modules = list(state.get("unlocked_modules", []))
        effective_holder = state.get("holder", "Utilisateur StudioForge 3D")

    return {
        "app_name": APP_NAME,
        "app_version": APP_VERSION,
        "release_date": APP_RELEASE_DATE,
        "machine_id": _get_machine_fingerprint(),
        "is_admin_machine": is_admin,
        "holder": effective_holder,
        "unlocked_modules": effective_modules,
        "real_unlocked_modules": state.get("unlocked_modules", []),
        "activated_keys_count": len(state.get("activated_keys", [])),
        "activated_keys": state.get("activated_keys", []),
        "client_simulation_mode": sim_mode,
        "catalog": MODULE_CATALOG,
    }


# ---------------------------------------------------------------------------
# API Schemas & Endpoints
# ---------------------------------------------------------------------------

class ActivateKeyRequest(BaseModel):
    license_key: str = Field(..., description="Clé de licence au format SF3D-...")


class AdminGenerateKeyRequest(BaseModel):
    holder: str = Field(default="Ma Fille - PC Maison", description="Nom du client ou bénéficiaire")
    modules: List[str] = Field(default=["hueforge", "lithophane"], description="Liste des IDs de modules à débloquer")
    max_machines: int = Field(default=3, ge=1, le=25)


class AdminSimulationRequest(BaseModel):
    mode: Optional[str] = Field(
        default=None,
        description="None (réel), 'unlicensed', 'pack_20', 'pack_25_smartcut', ou 'full'",
    )


@router.get("/status")
async def get_license_status():
    """Returns current license state, unlocked modules, version info, and whether this is the Admin PC."""
    state = _load_license_state()
    return _build_status_response(state)


@router.post("/activate")
async def activate_license_key_endpoint(req: ActivateKeyRequest):
    """
    Verifies a cryptographic license key (`SF3D-...`) and unlocks its modules.
    Supports additive module keys: activating a `+5 €` SmartCut add-on key adds `smartcut`
    to the already-unlocked `hueforge` + `lithophane` modules!
    """
    try:
        info = verify_license_key(req.license_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    state = _load_license_state()
    existing_mods = set(state.get("unlocked_modules", []))
    new_mods = set(info["unlocked_modules"])
    merged_mods = sorted(existing_mods | new_mods)

    keys_list = list(state.get("activated_keys", []))
    norm_k = info["key_ normalized"]
    if not any(k.get("key") == norm_k for k in keys_list):
        keys_list.append({
            "key": norm_k,
            "holder": info["holder"],
            "modules": info["unlocked_modules"],
            "issued_date": info["issued_date"],
            "activated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        })

    state["holder"] = info["holder"]
    state["unlocked_modules"] = merged_mods
    state["activated_keys"] = keys_list
    state["client_simulation_mode"] = None
    _save_license_state(state)

    resp = _build_status_response(state)
    resp["message"] = (
        f"Licence activée avec succès pour « {info['holder']} » ! "
        f"Modules débloqués : {', '.join(info['unlocked_modules'])}."
    )
    return resp


@router.post("/deactivate-all")
async def reset_client_licenses_endpoint():
    """Allows resetting activated keys on the current machine (for testing the unlicensed flow)."""
    state = {
        "holder": "Version Non Activée (En attente de clé)",
        "unlocked_modules": [],
        "activated_keys": [],
        "client_simulation_mode": None,
    }
    _save_license_state(state)
    return _build_status_response(state)


@router.post("/admin/generate")
async def admin_generate_license_key_endpoint(req: AdminGenerateKeyRequest):
    """
    [ADMIN PC ONLY] Generates a cryptographically signed `SF3D-...` license key.
    Strictly requires `backend/data/.admin_private_key.json` on disk (never shipped on GitHub).
    """
    if not _is_admin_machine():
        raise HTTPException(
            status_code=403,
            detail="Accès refusé : le générateur de clés n'est disponible que sur le poste Administrateur.",
        )
    valid_mods = [m for m in req.modules if m in MODULE_BITS]
    if not valid_mods:
        raise HTTPException(status_code=400, detail="Veuillez sélectionner au moins un module à inclure dans la clé.")

    key_str = _sign_license_payload(holder=req.holder, modules=valid_mods, max_machines=req.max_machines)
    verified = verify_license_key(key_str)
    return {
        "license_key": key_str,
        "holder": verified["holder"],
        "unlocked_modules": verified["unlocked_modules"],
        "max_machines": verified["max_machines"],
        "issued_date": verified["issued_date"],
    }


@router.post("/admin/simulate-view")
async def admin_set_simulation_mode(req: AdminSimulationRequest):
    """
    [ADMIN PC ONLY] Lets the creator preview the exact UI a customer sees (`unlicensed`, `pack_20`, `pack_25_smartcut`, `full`).
    """
    if not _is_admin_machine():
        raise HTTPException(status_code=403, detail="Réservé au poste Administrateur.")
    state = _load_license_state()
    state["client_simulation_mode"] = req.mode
    _save_license_state(state)
    return _build_status_response(state)


@router.get("/updates/check")
async def check_for_github_updates(repo_url: Optional[str] = None):
    """
    Checks for software & spool catalog updates from GitHub (or returns local release manifest status).
    """
    manifest = {
        "current_version": APP_VERSION,
        "latest_version": APP_VERSION,
        "release_date": APP_RELEASE_DATE,
        "update_available": False,
        "catalog_version": "2026.11.05",
        "changelog": [
            "v1.2.0 : Nouveau Hub d'Accueil StudioForge 3D & Identité visuelle officielle",
            "v1.2.0 : Tour de Couches Stratigraphique Interactive & Loupe de Couche dans HueForge Studio",
            "v1.2.0 : Cadrage 60 FPS à forme géométrique 100 % fixe & séparation Multi-Or anti-doublons",
            "v1.2.0 : Système de Licences Modulaires RSA (Pack Base 20 € + Extensions +5 €)",
        ],
    }
    if repo_url and repo_url.startswith("https://"):
        try:
            req = urllib.request.Request(repo_url, headers={"User-Agent": "StudioForge3D-Updater/1.2"})
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                remote = json.loads(resp.read().decode("utf-8"))
                latest_v = str(remote.get("version", APP_VERSION))
                manifest["latest_version"] = latest_v
                manifest["update_available"] = latest_v != APP_VERSION
                if remote.get("changelog"):
                    manifest["changelog"] = remote["changelog"]
        except Exception:
            pass
    return manifest
