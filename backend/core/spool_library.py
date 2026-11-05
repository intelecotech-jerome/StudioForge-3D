"""
Module: Persistent Filament Spool Library & AI Filament/Color Assistant
Stores user's real-world 3D printing spools (Deeplee, Creality, Sunlu, eSUN, Bambu, etc.)
with Hex color, HueForge Transmission Distance (TD in mm), Temperatures, Reference/SKU,
and Quick-Shortcut favorite flags.
Includes an AI Natural Language Assistant to auto-fill spool parameters and synthesize
exact Hex colors from French/English descriptions (e.g. "Deeplee PLA+ Blanc", "Bleu nuit profond").
"""
from __future__ import annotations

import json
import pathlib
import re
import unicodedata
import uuid
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/spools", tags=["Spool Library & AI Assistant"])

import sys

if getattr(sys, "frozen", False):
    DATA_DIR = pathlib.Path(sys.executable).resolve().parent / "data"
else:
    DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SPOOLS_JSON_PATH = DATA_DIR / "spools_library.json"


# ---------------------------------------------------------------------------
# Starter Catalog (18 Rich Spools + Quick Swatches)
# ---------------------------------------------------------------------------

DEFAULT_SPOOLS_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "spool-sunlu-pla-black",
        "brand": "Sunlu",
        "material": "PLA+",
        "color_name": "Noir Profond",
        "hex_color": "#0a0c10",
        "td_mm": 0.6,
        "nozzle_temp_c": 210,
        "bed_temp_c": 60,
        "reference_sku": "SUNLU-PLAPLUS-BK",
        "notes": "Idéal en couche de base HueForge (très opaque, bloque la lumière).",
        "is_favorite": True,
    },
    {
        "id": "spool-creality-hyper-charcoal",
        "brand": "Creality",
        "material": "Hyper PLA",
        "color_name": "Gris Anthracite",
        "hex_color": "#262b36",
        "td_mm": 1.0,
        "nozzle_temp_c": 215,
        "bed_temp_c": 60,
        "reference_sku": "CR-HYPER-CHARCOAL",
        "notes": "Transition ombres douces.",
        "is_favorite": True,
    },
    {
        "id": "spool-deeplee-pla-navy",
        "brand": "Deeplee",
        "material": "PLA+",
        "color_name": "Bleu Nuit",
        "hex_color": "#112454",
        "td_mm": 1.3,
        "nozzle_temp_c": 210,
        "bed_temp_c": 60,
        "reference_sku": "DEEPLEE-PLAP-NAVY",
        "notes": "Ombres froides pour mangas et armures.",
        "is_favorite": True,
    },
    {
        "id": "spool-creality-hyper-blue",
        "brand": "Creality",
        "material": "Hyper PLA",
        "color_name": "Bleu Royal",
        "hex_color": "#1d5dec",
        "td_mm": 2.0,
        "nozzle_temp_c": 215,
        "bed_temp_c": 60,
        "reference_sku": "CR-HYPER-BLUE",
        "notes": "Bleu saturé haute vitesse Creality Hi / K1 Max.",
        "is_favorite": True,
    },
    {
        "id": "spool-sunlu-pla-cyan",
        "brand": "Sunlu",
        "material": "PLA+",
        "color_name": "Cyan Glace",
        "hex_color": "#00d8ff",
        "td_mm": 2.4,
        "nozzle_temp_c": 210,
        "bed_temp_c": 60,
        "reference_sku": "SUNLU-PLAP-CYAN",
        "notes": "Parfait pour les auras énergétiques (Goku, halos bleus).",
        "is_favorite": True,
    },
    {
        "id": "spool-esun-pla-purple",
        "brand": "eSUN",
        "material": "PLA+",
        "color_name": "Violet Électrique",
        "hex_color": "#6d28d9",
        "td_mm": 1.8,
        "nozzle_temp_c": 215,
        "bed_temp_c": 60,
        "reference_sku": "ESUN-PLAP-PURPLE",
        "notes": "Violet intense pour effets Ultra Instinct / magie.",
        "is_favorite": True,
    },
    {
        "id": "spool-bambu-pla-magenta",
        "brand": "Bambu",
        "material": "PLA Basic",
        "color_name": "Rose Magenta",
        "hex_color": "#ec4899",
        "td_mm": 2.3,
        "nozzle_temp_c": 215,
        "bed_temp_c": 60,
        "reference_sku": "BL-PLA-MAGENTA",
        "notes": "Halos roses et néons cyberpunk.",
        "is_favorite": True,
    },
    {
        "id": "spool-creality-pla-crimson",
        "brand": "Creality",
        "material": "PLA",
        "color_name": "Rouge Bordeaux",
        "hex_color": "#7f1d1d",
        "td_mm": 1.4,
        "nozzle_temp_c": 205,
        "bed_temp_c": 60,
        "reference_sku": "CR-PLA-BURGUNDY",
        "notes": "Ombres chaudes / sang sombre.",
        "is_favorite": True,
    },
    {
        "id": "spool-creality-pla-red",
        "brand": "Creality",
        "material": "Hyper PLA",
        "color_name": "Rouge Vif",
        "hex_color": "#dc2626",
        "td_mm": 2.0,
        "nozzle_temp_c": 215,
        "bed_temp_c": 60,
        "reference_sku": "CR-HYPER-RED",
        "notes": "Rouge franc standard Creality.",
        "is_favorite": True,
    },
    {
        "id": "spool-sunlu-pla-orange",
        "brand": "Sunlu",
        "material": "PLA+",
        "color_name": "Orange Feu",
        "hex_color": "#f97316",
        "td_mm": 2.6,
        "nozzle_temp_c": 210,
        "bed_temp_c": 60,
        "reference_sku": "SUNLU-PLAP-ORANGE",
        "notes": "Tenues Dragon Ball, flammes et couchers de soleil.",
        "is_favorite": True,
    },
    {
        "id": "spool-bambu-pla-gold",
        "brand": "Bambu",
        "material": "PLA Basic",
        "color_name": "Jaune Or",
        "hex_color": "#facc15",
        "td_mm": 3.0,
        "nozzle_temp_c": 215,
        "bed_temp_c": 60,
        "reference_sku": "BL-PLA-YELLOW",
        "notes": "Cheveux Super Saiyan et effets lumineux dorés.",
        "is_favorite": True,
    },
    {
        "id": "spool-esun-pla-brown",
        "brand": "eSUN",
        "material": "PLA+",
        "color_name": "Marron Chocolat",
        "hex_color": "#5c3317",
        "td_mm": 1.2,
        "nozzle_temp_c": 215,
        "bed_temp_c": 60,
        "reference_sku": "ESUN-PLAP-BROWN",
        "notes": "Cuir, bois, ombres de peau.",
        "is_favorite": True,
    },
    {
        "id": "spool-deeplee-pla-skin",
        "brand": "Deeplee",
        "material": "PLA+",
        "color_name": "Beige Chair / Peau",
        "hex_color": "#f3c6a5",
        "td_mm": 2.7,
        "nozzle_temp_c": 210,
        "bed_temp_c": 60,
        "reference_sku": "DEEPLEE-PLAP-SKIN",
        "notes": "Visages et carnations mangas/portraits.",
        "is_favorite": True,
    },
    {
        "id": "spool-polymaker-pla-forest",
        "brand": "Polymaker",
        "material": "PolyTerra PLA",
        "color_name": "Vert Forêt",
        "hex_color": "#14532d",
        "td_mm": 1.3,
        "nozzle_temp_c": 205,
        "bed_temp_c": 60,
        "reference_sku": "PM-TERRA-FOREST",
        "notes": "Fonds naturels sombres.",
        "is_favorite": True,
    },
    {
        "id": "spool-sunlu-pla-emerald",
        "brand": "Sunlu",
        "material": "PLA+",
        "color_name": "Vert Émeraude",
        "hex_color": "#10b981",
        "td_mm": 2.2,
        "nozzle_temp_c": 210,
        "bed_temp_c": 60,
        "reference_sku": "SUNLU-PLAP-GREEN",
        "notes": "Vert lumineux.",
        "is_favorite": True,
    },
    {
        "id": "spool-sunlu-pla-silver",
        "brand": "Sunlu",
        "material": "PLA+",
        "color_name": "Gris Argent",
        "hex_color": "#94a3b8",
        "td_mm": 1.9,
        "nozzle_temp_c": 210,
        "bed_temp_c": 60,
        "reference_sku": "SUNLU-PLAP-SILVER",
        "notes": "Demi-teintes neutres et reflets métalliques.",
        "is_favorite": True,
    },
    {
        "id": "spool-creality-pla-ivory",
        "brand": "Creality",
        "material": "Hyper PLA",
        "color_name": "Blanc Chaud / Ivoire",
        "hex_color": "#fef08a",
        "td_mm": 3.2,
        "nozzle_temp_c": 215,
        "bed_temp_c": 60,
        "reference_sku": "CR-HYPER-IVORY",
        "notes": "Haute lumière douce et chaude.",
        "is_favorite": True,
    },
    {
        "id": "spool-deeplee-pla-white",
        "brand": "Deeplee",
        "material": "PLA+",
        "color_name": "Blanc Pur",
        "hex_color": "#ffffff",
        "td_mm": 2.8,
        "nozzle_temp_c": 210,
        "bed_temp_c": 60,
        "reference_sku": "DEEPLEE-PLAP-WHITE",
        "notes": "Couche finale d'éclat blanc HueForge.",
        "is_favorite": True,
    },
]


def _ensure_spool_defaults(sp: Dict[str, Any]) -> bool:
    changed = False
    defaults = {
        "in_stock": True,
        "is_favorite": True,
        "surface_finish": "Standard",
        "flow_ratio": 0.98 if "Hyper" in sp.get("material", "") else 0.96,
        "max_volumetric_flow": 20.0 if "Hyper" in sp.get("material", "") else 12.0,
        "drying_temp_c": 48,
        "drying_hours": 6,
        "hdt_c": 52,
        "tensile_z_mpa": 23.8,
    }
    for k, v in defaults.items():
        if k not in sp or sp[k] is None:
            sp[k] = v
            changed = True
    return changed


def load_spools_library() -> List[Dict[str, Any]]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not SPOOLS_JSON_PATH.exists():
        for sp in DEFAULT_SPOOLS_CATALOG:
            _ensure_spool_defaults(sp)
        save_spools_library(DEFAULT_SPOOLS_CATALOG)
        return list(DEFAULT_SPOOLS_CATALOG)
    try:
        data = json.loads(SPOOLS_JSON_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list) and len(data) > 0:
            changed = False
            for sp in data:
                if _ensure_spool_defaults(sp):
                    changed = True
            if changed:
                save_spools_library(data)
            return data
    except Exception:
        pass
    for sp in DEFAULT_SPOOLS_CATALOG:
        _ensure_spool_defaults(sp)
    save_spools_library(DEFAULT_SPOOLS_CATALOG)
    return list(DEFAULT_SPOOLS_CATALOG)


def save_spools_library(spools: List[Dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SPOOLS_JSON_PATH.write_text(
        json.dumps(spools, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# AI Natural Language Spool & Color Assistant
# ---------------------------------------------------------------------------

KNOWN_BRANDS = {
    "deeplee": ("Deeplee", "DEEPLEE"),
    "creality": ("Creality", "CR"),
    "ender": ("Creality Ender", "CR-END"),
    "sunlu": ("Sunlu", "SUNLU"),
    "esun": ("eSUN", "ESUN"),
    "bambu": ("Bambu Lab", "BL"),
    "bambulab": ("Bambu Lab", "BL"),
    "polymaker": ("Polymaker", "PM"),
    "polyterra": ("Polymaker", "PM-TERRA"),
    "polylite": ("Polymaker", "PM-LITE"),
    "eryone": ("Eryone", "ERY"),
    "elegoo": ("Elegoo", "ELG"),
    "anycubic": ("Anycubic", "ANY"),
    "prusament": ("Prusament", "PRUSA"),
    "overture": ("Overture", "OVT"),
    "jayo": ("Jayo", "JAYO"),
    "geeetech": ("Geeetech", "GEE"),
    "hatchbox": ("Hatchbox", "HBX"),
    "arianeplast": ("Arianeplast", "ARI"),
    "francofil": ("Francofil", "FRF"),
    "rosa3d": ("Rosa3D", "ROSA"),
    "wanhao": ("Wanhao", "WAN"),
}

MATERIAL_RULES = [
    (r"hyper\s*pla", "Hyper PLA", 215, 60, 1.05),
    (r"pla\s*\+|pla\s*plus|pla\s*pro", "PLA+", 212, 60, 1.0),
    (r"pla\s*mat(?:te)?|mat(?:te)?\s*pla|polyterra", "PLA Matte", 205, 60, 0.72),
    (r"silk\s*pla|pla\s*silk|pla\s*soie|soie", "PLA Silk", 215, 60, 0.78),
    (r"petg", "PETG", 235, 75, 1.35),
    (r"abs", "ABS", 250, 95, 0.85),
    (r"asa", "ASA", 255, 95, 0.85),
    (r"tpu", "TPU 95A", 220, 50, 1.40),
    (r"pla", "PLA", 205, 60, 1.0),
]

# Base Color Dictionary: normalized keyword -> (Display Name FR, (R, G, B), Base TD in mm)
COLOR_LEXICON: List[tuple] = [
    # Multi-word specific shades first
    ("blanc froid", "Blanc Froid", (250, 253, 255), 2.8),
    ("blanc chaud", "Blanc Chaud", (255, 246, 224), 3.1),
    ("blanc casse", "Blanc Cassé", (245, 242, 232), 2.9),
    ("blanc pur", "Blanc Pur", (255, 255, 255), 2.8),
    ("noir carbone", "Noir Carbone", (14, 16, 20), 0.5),
    ("noir mat", "Noir Mat", (12, 13, 16), 0.5),
    ("noir profond", "Noir Profond", (8, 10, 15), 0.6),
    ("bleu nuit", "Bleu Nuit", (16, 36, 84), 1.3),
    ("bleu marine", "Bleu Marine", (18, 42, 98), 1.3),
    ("bleu roi", "Bleu Roi", (29, 93, 236), 2.0),
    ("bleu royal", "Bleu Royal", (29, 93, 236), 2.0),
    ("bleu ciel", "Bleu Ciel", (56, 189, 248), 2.5),
    ("bleu glace", "Bleu Glace", (0, 216, 255), 2.5),
    ("bleu glacier", "Bleu Glacier", (103, 232, 249), 2.7),
    ("bleu electrique", "Bleu Électrique", (0, 112, 255), 2.1),
    ("bleu cobalt", "Bleu Cobalt", (30, 64, 175), 1.6),
    ("bleu petrole", "Bleu Pétrole", (15, 76, 92), 1.4),
    ("cyan glace", "Cyan Glace", (0, 216, 255), 2.4),
    ("rouge sang", "Rouge Sang", (185, 28, 28), 1.7),
    ("rouge cerise", "Rouge Cerise", (210, 20, 58), 1.9),
    ("rouge feu", "Rouge Feu", (239, 68, 68), 2.2),
    ("rouge bordeaux", "Rouge Bordeaux", (127, 29, 29), 1.4),
    ("rouge carmin", "Rouge Carmin", (153, 27, 27), 1.6),
    ("orange feu", "Orange Feu", (249, 115, 22), 2.6),
    ("jaune or", "Jaune Or", (250, 204, 21), 3.0),
    ("jaune citron", "Jaune Citron", (253, 224, 71), 3.3),
    ("vert foret", "Vert Forêt", (20, 83, 45), 1.3),
    ("vert sapin", "Vert Sapin", (6, 78, 59), 1.3),
    ("vert emeraude", "Vert Émeraude", (16, 185, 129), 2.2),
    ("vert olive", "Vert Olive", (101, 119, 43), 1.5),
    ("vert militaire", "Vert Militaire", (75, 83, 32), 1.3),
    ("vert menthe", "Vert Menthe", (110, 231, 183), 2.6),
    ("vert sauge", "Vert Sauge", (132, 169, 140), 2.0),
    ("vert pomme", "Vert Pomme", (132, 204, 22), 2.5),
    ("gris argent", "Gris Argent", (148, 163, 184), 1.9),
    ("gris anthracite", "Gris Anthracite", (38, 43, 54), 1.0),
    ("gris souris", "Gris Souris", (100, 116, 139), 1.5),
    ("gris perle", "Gris Perle", (203, 213, 225), 2.3),
    ("violet electrique", "Violet Électrique", (109, 40, 217), 1.8),
    ("rose bonbon", "Rose Bonbon", (244, 114, 182), 2.5),
    ("rose pastel", "Rose Pastel", (249, 168, 212), 2.8),
    ("marron chocolat", "Marron Chocolat", (92, 51, 23), 1.2),
    # Single-word core colors
    ("blanc", "Blanc", (255, 255, 255), 2.8),
    ("white", "Blanc", (255, 255, 255), 2.8),
    ("ivoire", "Ivoire", (254, 243, 199), 3.1),
    ("ivory", "Ivoire", (254, 243, 199), 3.1),
    ("creme", "Crème", (253, 230, 188), 3.0),
    ("noir", "Noir", (10, 12, 16), 0.6),
    ("black", "Noir", (10, 12, 16), 0.6),
    ("anthracite", "Anthracite", (38, 43, 54), 1.0),
    ("charcoal", "Anthracite", (38, 43, 54), 1.0),
    ("gris", "Gris", (120, 132, 150), 1.6),
    ("grey", "Gris", (120, 132, 150), 1.6),
    ("gray", "Gris", (120, 132, 150), 1.6),
    ("argent", "Argent", (160, 174, 192), 1.9),
    ("silver", "Argent", (160, 174, 192), 1.9),
    ("rouge", "Rouge", (220, 38, 38), 2.0),
    ("red", "Rouge", (220, 38, 38), 2.0),
    ("bordeaux", "Bordeaux", (127, 29, 29), 1.4),
    ("rubis", "Rubis", (185, 28, 60), 1.8),
    ("corail", "Corail", (251, 113, 133), 2.4),
    ("orange", "Orange", (249, 115, 22), 2.6),
    ("cuivre", "Cuivre", (184, 115, 51), 1.5),
    ("bronze", "Bronze", (161, 98, 7), 1.5),
    ("jaune", "Jaune", (250, 204, 21), 3.0),
    ("yellow", "Jaune", (250, 204, 21), 3.0),
    ("or", "Or Doré", (234, 179, 8), 2.2),
    ("dore", "Or Doré", (234, 179, 8), 2.2),
    ("gold", "Or Doré", (234, 179, 8), 2.2),
    ("beige", "Beige", (230, 198, 168), 2.6),
    ("sable", "Sable", (214, 185, 140), 2.4),
    ("chair", "Beige Chair", (243, 198, 165), 2.7),
    ("peau", "Beige Peau", (243, 198, 165), 2.7),
    ("skin", "Beige Chair", (243, 198, 165), 2.7),
    ("peche", "Pêche", (253, 186, 140), 2.8),
    ("marron", "Marron", (110, 62, 32), 1.2),
    ("brun", "Brun", (95, 55, 30), 1.2),
    ("brown", "Marron", (110, 62, 32), 1.2),
    ("chocolat", "Chocolat", (82, 45, 20), 1.1),
    ("bois", "Bois", (166, 123, 91), 1.6),
    ("vert", "Vert", (22, 163, 74), 2.0),
    ("green", "Vert", (22, 163, 74), 2.0),
    ("emeraude", "Émeraude", (16, 185, 129), 2.2),
    ("kaki", "Kaki", (101, 115, 65), 1.4),
    ("turquoise", "Turquoise", (20, 184, 166), 2.3),
    ("cyan", "Cyan", (0, 216, 255), 2.4),
    ("bleu", "Bleu", (37, 99, 235), 2.0),
    ("blue", "Bleu", (37, 99, 235), 2.0),
    ("azur", "Bleu Azur", (14, 165, 233), 2.3),
    ("violet", "Violet", (124, 58, 237), 1.8),
    ("purple", "Violet", (124, 58, 237), 1.8),
    ("pourpre", "Pourpre", (147, 51, 234), 1.8),
    ("lavande", "Lavande", (196, 181, 253), 2.6),
    ("lilas", "Lilas", (216, 180, 254), 2.7),
    ("magenta", "Magenta", (236, 72, 153), 2.3),
    ("fuchsia", "Fuchsia", (217, 70, 239), 2.3),
    ("rose", "Rose", (244, 114, 182), 2.5),
    ("pink", "Rose", (244, 114, 182), 2.5),
]


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text.lower())
        if unicodedata.category(c) != "Mn"
    )


def _rgb_to_hex(rgb: tuple) -> str:
    r = max(0, min(255, int(round(rgb[0]))))
    g = max(0, min(255, int(round(rgb[1]))))
    b = max(0, min(255, int(round(rgb[2]))))
    return f"#{r:02x}{g:02x}{b:02x}"


def ai_parse_spool_prompt(prompt: str) -> Dict[str, Any]:
    """
    AI Assistant that parses a natural-language description such as:
    - "Deeplee PLA+ Blanc"
    - "Creality Hyper PLA Rouge Cerise"
    - "Sunlu PETG Bleu nuit foncé"
    - "Vert émeraude clair"
    and returns pre-filled brand, material, color_name, hex_color, td_mm, nozzle_temp_c, bed_temp_c, reference_sku.
    """
    raw = prompt.strip()
    norm = _strip_accents(raw)

    # 1. Detect Brand
    brand = "Générique"
    brand_code = "GEN"
    for key, (b_name, b_code) in KNOWN_BRANDS.items():
        if re.search(rf"\b{re.escape(key)}\b", norm):
            brand = b_name
            brand_code = b_code
            break

    # 2. Detect Material & Thermal/Optical/Mechanical Multipliers
    material = "PLA+"
    nozzle_temp_c = 210
    bed_temp_c = 60
    td_mult = 1.0
    surface_finish = "Standard"
    flow_ratio = 0.96
    max_volumetric_flow = 12.0
    drying_temp_c = 48
    drying_hours = 6
    hdt_c = 52
    tensile_z_mpa = 23.8

    for pattern, mat_name, n_temp, b_temp, mult in MATERIAL_RULES:
        if re.search(pattern, norm):
            material = mat_name
            nozzle_temp_c = n_temp
            bed_temp_c = b_temp
            td_mult = mult
            break

    if "matte" in material.lower() or re.search(r"\b(mat|matte)\b", norm):
        surface_finish = "Matte"
        flow_ratio = 0.97
        max_volumetric_flow = 14.0
        tensile_z_mpa = 19.5
    elif "silk" in material.lower() or re.search(r"\b(silk|soie|brillant|metallise)\b", norm):
        surface_finish = "Silk"
        flow_ratio = 0.95
        max_volumetric_flow = 10.0
        tensile_z_mpa = 18.0
    elif re.search(r"\b(translucide|transparent|clear|cristal|verre)\b", norm):
        surface_finish = "Translucide"
        td_mult = 1.65
        flow_ratio = 0.98
    elif re.search(r"\b(paillete|galaxy|glitter|marbre|marble)\b", norm):
        surface_finish = "Pailleté / Effet"
        flow_ratio = 0.97

    if "hyper" in material.lower() or brand in ("Creality", "Bambu Lab"):
        max_volumetric_flow = 21.0 if "hyper" in material.lower() else 18.0
        flow_ratio = 0.98
    elif brand == "Anycubic":
        # Calibrated on Anycubic PLA+ TDS V3.0
        nozzle_temp_c = 210
        bed_temp_c = 60
        flow_ratio = 0.96
        max_volumetric_flow = 12.0
        drying_temp_c = 48
        drying_hours = 6
        hdt_c = 52
        tensile_z_mpa = 23.8
    elif material == "PETG":
        drying_temp_c = 60
        drying_hours = 6
        hdt_c = 68
        tensile_z_mpa = 28.0
        max_volumetric_flow = 11.0
    elif material in ("ABS", "ASA"):
        drying_temp_c = 70
        drying_hours = 8
        hdt_c = 88
        tensile_z_mpa = 30.0
        max_volumetric_flow = 15.0

    # 3. Check if user explicitly typed a hex code (#rrggbb)
    hex_match = re.search(r"#([0-9a-f]{6})\b", norm)

    color_name = "Couleur Personnalisée"
    rgb = (37, 99, 235)
    base_td = 2.0

    for kw, c_label, c_rgb, c_td in COLOR_LEXICON:
        # Match whole words so 'or' doesn't match inside 'noir' or 'foret'
        if re.search(rf"\b{re.escape(kw)}\b", norm):
            color_name = c_label
            rgb = c_rgb
            base_td = c_td
            break

    r, g, b = float(rgb[0]), float(rgb[1]), float(rgb[2])

    # 4. Apply shade modifiers ("clair", "pastel", "fonce", "sombre", "profond", "vif", "fluo")
    if re.search(r"\b(clair|claire|pale|pastel)\b", norm) and "clair" not in _strip_accents(color_name):
        r = r + (255.0 - r) * 0.38
        g = g + (255.0 - g) * 0.38
        b = b + (255.0 - b) * 0.38
        base_td += 0.4
        color_name = f"{color_name} Clair"
    elif re.search(r"\b(fonce|foncee|sombre|profond|nuit)\b", norm) and "nuit" not in _strip_accents(color_name) and "profond" not in _strip_accents(color_name):
        r *= 0.58
        g *= 0.58
        b *= 0.58
        base_td = max(0.5, base_td - 0.5)
        color_name = f"{color_name} Foncé"
    elif re.search(r"\b(vif|intense|fluo|neon)\b", norm):
        # Boost saturation
        mx = max(r, g, b)
        if mx > 10:
            scale = min(1.25, 255.0 / mx)
            r = min(255.0, r * scale)
            g = min(255.0, g * scale)
            b = min(255.0, b * scale)
        color_name = f"{color_name} Vif"

    if hex_match:
        hex_color = f"#{hex_match.group(1)}"
    else:
        hex_color = _rgb_to_hex((r, g, b))

    td_mm = round(max(0.4, min(5.0, base_td * td_mult)), 1)
    color_slug = re.sub(r"[^A-Z0-9]+", "", _strip_accents(color_name).upper())[:8] or "COL"
    mat_slug = re.sub(r"[^A-Z0-9+]+", "", material.upper())
    reference_sku = f"{brand_code}-{mat_slug}-{color_slug}"

    return {
        "brand": brand,
        "material": material,
        "color_name": color_name,
        "hex_color": hex_color,
        "surface_finish": surface_finish,
        "td_mm": td_mm,
        "nozzle_temp_c": nozzle_temp_c,
        "bed_temp_c": bed_temp_c,
        "flow_ratio": flow_ratio,
        "max_volumetric_flow": max_volumetric_flow,
        "drying_temp_c": drying_temp_c,
        "drying_hours": drying_hours,
        "hdt_c": hdt_c,
        "tensile_z_mpa": tensile_z_mpa,
        "reference_sku": reference_sku,
        "notes": f"Pré-encodé par Assistant IA à partir de : « {raw} »",
        "is_favorite": True,
        "in_stock": True,
    }


def _hex_to_rgb_tuple(hx: str) -> tuple:
    h = hx.strip().lstrip("#")
    if len(h) != 6:
        return (128, 128, 128)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _rgb_luma(rgb: tuple) -> float:
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def match_palette_to_in_stock_spools(target_hex_list: List[str]) -> List[Dict[str, Any]]:
    """
    Given a list of K ideal target hex colors (ordered from darkest to brightest),
    selects the K best matching spools from the user's `in_stock == True` spool inventory
    (without duplicating the same spool on two adjacent layers if enough spools exist),
    and returns the matched spool dicts sorted by luminance from darkest to brightest.
    """
    all_spools = load_spools_library()
    stock_spools = [s for s in all_spools if s.get("in_stock", True)]
    if not stock_spools:
        stock_spools = all_spools

    used_ids = set()
    matched: List[Dict[str, Any]] = []

    for idx, t_hex in enumerate(target_hex_list):
        t_rgb = _hex_to_rgb_tuple(t_hex)
        t_luma = _rgb_luma(t_rgb)

        best_sp = None
        best_score = 1e12

        candidates = [s for s in stock_spools if s["id"] not in used_ids] or stock_spools
        for sp in candidates:
            s_rgb = _hex_to_rgb_tuple(sp.get("hex_color", "#888888"))
            s_luma = _rgb_luma(s_rgb)

            # Perceptual redmean RGB distance + luminance preservation weight
            rmean = 0.5 * (t_rgb[0] + s_rgb[0])
            dr = t_rgb[0] - s_rgb[0]
            dg = t_rgb[1] - s_rgb[1]
            db = t_rgb[2] - s_rgb[2]
            c_dist = ((2.0 + rmean / 256.0) * dr * dr + 4.0 * dg * dg + (2.0 + (255.0 - rmean) / 256.0) * db * db) ** 0.5
            l_dist = abs(t_luma - s_luma) * 1.35

            # Extra anchor weight for layer 0 (darkest base) and last layer (brightest highlight)
            anchor_penalty = 0.0
            if idx == 0:
                anchor_penalty = s_luma * 1.5
            elif idx == len(target_hex_list) - 1:
                anchor_penalty = (255.0 - s_luma) * 1.5

            score = c_dist + l_dist + anchor_penalty
            # Prevent matching a neutral grey/silver target to a highly saturated spool (like Magenta/Orange), and vice versa
            t_max, t_min = max(t_rgb), min(t_rgb)
            s_max, s_min = max(s_rgb), min(s_rgb)
            t_sat = (t_max - t_min) / max(1.0, float(t_max))
            s_sat = (s_max - s_min) / max(1.0, float(s_max))
            if t_sat < 0.15 and s_sat > 0.24:
                score += 380.0 * s_sat
            elif t_sat >= 0.28 and s_sat < 0.15:
                score += 240.0 * t_sat

            if score < best_score:
                best_score = score
                best_sp = sp

        if best_sp is not None:
            used_ids.add(best_sp["id"])
            matched.append(best_sp)

    # Preserve the exact Contiguous Family-Ramp order of `target_hex_list`!
    return matched


# ---------------------------------------------------------------------------
# Pydantic Schemas & API Routes
# ---------------------------------------------------------------------------

class SpoolCreateOrUpdate(BaseModel):
    brand: str = Field(default="Deeplee", min_length=1)
    material: str = Field(default="PLA+", min_length=1)
    color_name: str = Field(default="Blanc Pur", min_length=1)
    hex_color: str = Field(default="#ffffff")
    surface_finish: str = Field(default="Standard")
    td_mm: float = Field(default=2.0, ge=0.3, le=6.0)
    nozzle_temp_c: int = Field(default=210, ge=170, le=300)
    bed_temp_c: int = Field(default=60, ge=0, le=120)
    flow_ratio: float = Field(default=0.96, ge=0.80, le=1.15)
    max_volumetric_flow: float = Field(default=12.0, ge=2.0, le=40.0)
    drying_temp_c: int = Field(default=48, ge=35, le=90)
    drying_hours: int = Field(default=6, ge=1, le=24)
    hdt_c: int = Field(default=52, ge=40, le=150)
    tensile_z_mpa: float = Field(default=23.8, ge=5.0, le=80.0)
    reference_sku: str = Field(default="")
    notes: str = Field(default="")
    is_favorite: bool = True
    in_stock: bool = True


class AiSpoolPromptRequest(BaseModel):
    prompt: str = Field(..., min_length=2, description="Ex: 'Deeplee PLA+ Blanc' ou 'Bleu glacier métallisé'")


@router.get("")
async def get_all_spools():
    spools = load_spools_library()
    return {
        "spools": spools,
        "favorites": [s for s in spools if s.get("is_favorite", True)],
        "in_stock": [s for s in spools if s.get("in_stock", True)],
    }


@router.post("/ai-assist")
async def suggest_spool_from_ai(req: AiSpoolPromptRequest):
    """
    AI Assistant that converts a natural language description (e.g., 'Deeplee PLA+ Blanc' or
    'Creality Hyper PLA Rouge Cerise') into a complete spool configuration + accurate Hex color + TD.
    """
    suggestion = ai_parse_spool_prompt(req.prompt)
    return {"suggestion": suggestion}


@router.post("")
async def create_spool(payload: SpoolCreateOrUpdate):
    spools = load_spools_library()
    new_spool = {
        "id": f"spool-{uuid.uuid4().hex[:8]}",
        **payload.model_dump(),
    }
    spools.append(new_spool)
    save_spools_library(spools)
    return {
        "spool": new_spool,
        "spools": spools,
        "favorites": [s for s in spools if s.get("is_favorite", True)],
        "in_stock": [s for s in spools if s.get("in_stock", True)],
    }


@router.put("/{spool_id}")
async def update_spool(spool_id: str, payload: SpoolCreateOrUpdate):
    spools = load_spools_library()
    found = False
    for idx, s in enumerate(spools):
        if s.get("id") == spool_id:
            spools[idx] = {"id": spool_id, **payload.model_dump()}
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail=f"Bobine '{spool_id}' introuvable.")
    save_spools_library(spools)
    return {
        "spools": spools,
        "favorites": [s for s in spools if s.get("is_favorite", True)],
        "in_stock": [s for s in spools if s.get("in_stock", True)],
    }


@router.post("/{spool_id}/toggle-favorite")
async def toggle_spool_favorite(spool_id: str):
    spools = load_spools_library()
    for s in spools:
        if s.get("id") == spool_id:
            s["is_favorite"] = not bool(s.get("is_favorite", True))
            break
    save_spools_library(spools)
    return {
        "spools": spools,
        "favorites": [s for s in spools if s.get("is_favorite", True)],
        "in_stock": [s for s in spools if s.get("in_stock", True)],
    }


@router.post("/{spool_id}/toggle-stock")
async def toggle_spool_stock(spool_id: str):
    spools = load_spools_library()
    for s in spools:
        if s.get("id") == spool_id:
            s["in_stock"] = not bool(s.get("in_stock", True))
            break
    save_spools_library(spools)
    return {
        "spools": spools,
        "favorites": [s for s in spools if s.get("is_favorite", True)],
        "in_stock": [s for s in spools if s.get("in_stock", True)],
    }


@router.post("/{spool_id}/move/{direction}")
async def move_spool_order(spool_id: str, direction: str):
    spools = load_spools_library()
    idx = next((i for i, s in enumerate(spools) if s.get("id") == spool_id), None)
    if idx is not None:
        if direction == "up" and idx > 0:
            spools[idx - 1], spools[idx] = spools[idx], spools[idx - 1]
            save_spools_library(spools)
        elif direction == "down" and idx < len(spools) - 1:
            spools[idx + 1], spools[idx] = spools[idx], spools[idx + 1]
            save_spools_library(spools)
    return {
        "spools": spools,
        "favorites": [s for s in spools if s.get("is_favorite", True)],
        "in_stock": [s for s in spools if s.get("in_stock", True)],
    }


@router.post("/sort/{sort_by}")
async def sort_spools_library(sort_by: str):
    spools = load_spools_library()
    if sort_by == "luminance":
        spools.sort(key=lambda s: _rgb_luma(_hex_to_rgb_tuple(s.get("hex_color", "#888888"))))
    elif sort_by == "brand":
        spools.sort(key=lambda s: (s.get("brand", "").lower(), s.get("color_name", "").lower()))
    save_spools_library(spools)
    return {
        "spools": spools,
        "favorites": [s for s in spools if s.get("is_favorite", True)],
        "in_stock": [s for s in spools if s.get("in_stock", True)],
    }


@router.delete("/{spool_id}")
async def delete_spool(spool_id: str):
    spools = load_spools_library()
    spools = [s for s in spools if s.get("id") != spool_id]
    save_spools_library(spools)
    return {
        "spools": spools,
        "favorites": [s for s in spools if s.get("is_favorite", True)],
        "in_stock": [s for s in spools if s.get("in_stock", True)],
    }


# ---------------------------------------------------------------------------
# Persistent Printer Fleet Library & Per-Module Filtering
# ---------------------------------------------------------------------------

printers_router = APIRouter(prefix="/api/printers", tags=["Printer Fleet & Module Permissions"])
PRINTERS_JSON_PATH = DATA_DIR / "printers_library.json"

DEFAULT_PRINTERS_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "creality_hi",
        "name": "Creality Hi (Combo 2× CFS)",
        "brand": "Creality",
        "bed_x_mm": 260.0,
        "bed_y_mm": 260.0,
        "bed_z_mm": 300.0,
        "max_colors": 8,
        "use_cosplay": True,
        "use_hueforge": True,
        "use_lithophane": True,
        "notes": "Multi-couleurs automatique (2× CFS = jusqu'à 8 bobines). Idéale pour HueForge & Multi-Frame.",
    },
    {
        "id": "k1_max",
        "name": "Creality K1 Max",
        "brand": "Creality",
        "bed_x_mm": 300.0,
        "bed_y_mm": 300.0,
        "bed_z_mm": 300.0,
        "max_colors": 1,
        "use_cosplay": True,
        "use_hueforge": False,
        "use_lithophane": True,
        "notes": "CoreXY grand volume 300×300×300 mm (Mono-couleur, désactivée par défaut dans HueForge).",
    },
]

KNOWN_PRINTER_SPECS: List[tuple] = [
    ("k2 plus", "Creality K2 Plus (CFS)", "Creality", 350.0, 350.0, 350.0, 16),
    ("creality hi", "Creality Hi (Combo CFS)", "Creality", 260.0, 260.0, 300.0, 8),
    ("k1 max", "Creality K1 Max", "Creality", 300.0, 300.0, 300.0, 1),
    ("k1c", "Creality K1C", "Creality", 220.0, 220.0, 250.0, 1),
    ("k1", "Creality K1", "Creality", 220.0, 220.0, 250.0, 1),
    ("ender 3 v3 plus", "Creality Ender-3 V3 Plus", "Creality", 300.0, 300.0, 330.0, 1),
    ("ender 3 v3", "Creality Ender-3 V3", "Creality", 220.0, 220.0, 250.0, 1),
    ("x1c", "Bambu Lab X1 Carbon (AMS)", "Bambu Lab", 256.0, 256.0, 256.0, 16),
    ("x1 carbon", "Bambu Lab X1 Carbon (AMS)", "Bambu Lab", 256.0, 256.0, 256.0, 16),
    ("p1s", "Bambu Lab P1S (AMS)", "Bambu Lab", 256.0, 256.0, 256.0, 16),
    ("p1p", "Bambu Lab P1P", "Bambu Lab", 256.0, 256.0, 256.0, 4),
    ("a1 mini", "Bambu Lab A1 Mini (AMS Lite)", "Bambu Lab", 180.0, 180.0, 180.0, 4),
    ("a1", "Bambu Lab A1 (AMS Lite)", "Bambu Lab", 256.0, 256.0, 256.0, 4),
    ("h2d", "Bambu Lab H2D", "Bambu Lab", 350.0, 320.0, 325.0, 16),
    ("kobra 3 max", "Anycubic Kobra 3 Max (ACE Pro)", "Anycubic", 420.0, 420.0, 500.0, 8),
    ("kobra 3", "Anycubic Kobra 3 (ACE Pro)", "Anycubic", 250.0, 250.0, 260.0, 8),
    ("kobra 2 max", "Anycubic Kobra 2 Max", "Anycubic", 420.0, 420.0, 500.0, 1),
    ("neptune 4 max", "Elegoo Neptune 4 Max", "Elegoo", 420.0, 420.0, 480.0, 1),
    ("neptune 4 plus", "Elegoo Neptune 4 Plus", "Elegoo", 320.0, 320.0, 385.0, 1),
    ("prusa xl", "Original Prusa XL (5 Têtes)", "Prusa", 360.0, 360.0, 360.0, 5),
    ("mk4", "Original Prusa MK4S", "Prusa", 250.0, 210.0, 220.0, 1),
    ("voron 2.4 350", "Voron 2.4 (350mm)", "Voron", 350.0, 350.0, 340.0, 1),
    ("voron 2.4", "Voron 2.4 (300mm)", "Voron", 300.0, 300.0, 290.0, 1),
]


def load_printers_library() -> List[Dict[str, Any]]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not PRINTERS_JSON_PATH.exists():
        save_printers_library(DEFAULT_PRINTERS_CATALOG)
        return list(DEFAULT_PRINTERS_CATALOG)
    try:
        data = json.loads(PRINTERS_JSON_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list) and len(data) > 0:
            return data
    except Exception:
        pass
    save_printers_library(DEFAULT_PRINTERS_CATALOG)
    return list(DEFAULT_PRINTERS_CATALOG)


def save_printers_library(printers: List[Dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PRINTERS_JSON_PATH.write_text(
        json.dumps(printers, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


class PrinterCreateOrUpdate(BaseModel):
    name: str = Field(..., min_length=1)
    brand: str = Field(default="Creality")
    bed_x_mm: float = Field(default=260.0, ge=50.0, le=1200.0)
    bed_y_mm: float = Field(default=260.0, ge=50.0, le=1200.0)
    bed_z_mm: float = Field(default=300.0, ge=50.0, le=1500.0)
    max_colors: int = Field(default=1, ge=1, le=16)
    use_cosplay: bool = True
    use_hueforge: bool = True
    use_lithophane: bool = True
    notes: str = ""


class PrinterAIPromptRequest(BaseModel):
    prompt: str


@printers_router.get("")
async def get_all_printers():
    printers = load_printers_library()
    return {"printers": printers}


@printers_router.post("/ai-suggest")
async def suggest_printer_from_ai_prompt(req: PrinterAIPromptRequest):
    raw = req.prompt.strip()
    norm = _normalize_text(raw)
    matched = None
    for kw, name, brand, bx, by, bz, mcols in KNOWN_PRINTER_SPECS:
        if kw in norm:
            matched = {
                "name": name,
                "brand": brand,
                "bed_x_mm": bx,
                "bed_y_mm": by,
                "bed_z_mm": bz,
                "max_colors": mcols,
            }
            break

    # Check if user explicitly mentioned CFS / AMS / ACE or number of colors
    m_col = re.search(r"(\d+)\s*(?:couleur|color|bobine)", norm)
    m_cfs = re.search(r"(\d+)\s*(?:x\s*)?(?:cfs|ams|ace)", norm)

    # Check if user explicitly typed dimensions like 300x300x300 or 260x260
    m_dim = re.search(r"(\d{2,4})\s*[x×*]\s*(\d{2,4})(?:\s*[x×*]\s*(\d{2,4}))?", norm)

    if not matched:
        brand = "Custom"
        for b_key, (b_label, _) in KNOWN_BRANDS.items():
            if b_key in norm:
                brand = b_label
                break
        bx, by, bz = (260.0, 260.0, 300.0)
        if m_dim:
            bx = float(m_dim.group(1))
            by = float(m_dim.group(2))
            bz = float(m_dim.group(3)) if m_dim.group(3) else bx
        mcols = 4 if ("cfs" in norm or "ams" in norm or "multi" in norm) else 1
        matched = {
            "name": raw if len(raw) >= 2 else "Imprimante Personnalisée",
            "brand": brand,
            "bed_x_mm": bx,
            "bed_y_mm": by,
            "bed_z_mm": bz,
            "max_colors": mcols,
        }
    else:
        if m_dim:
            matched["bed_x_mm"] = float(m_dim.group(1))
            matched["bed_y_mm"] = float(m_dim.group(2))
            if m_dim.group(3):
                matched["bed_z_mm"] = float(m_dim.group(3))

    if m_cfs:
        matched["max_colors"] = min(16, int(m_cfs.group(1)) * 4)
    elif m_col:
        matched["max_colors"] = min(16, max(1, int(m_col.group(1))))

    is_multi = matched["max_colors"] > 1
    return {
        "suggestion": {
            **matched,
            "use_cosplay": True,
            "use_hueforge": is_multi,
            "use_lithophane": True,
            "notes": (
                f"Plateau {int(matched['bed_x_mm'])}×{int(matched['bed_y_mm'])}×{int(matched['bed_z_mm'])} mm — "
                + (f"Multi-couleurs ({matched['max_colors']} bobines max)." if is_multi else "Mono-couleur (HueForge décoché par défaut).")
            ),
        }
    }


@printers_router.post("")
async def create_printer(payload: PrinterCreateOrUpdate):
    printers = load_printers_library()
    new_printer = {
        "id": f"printer-{uuid.uuid4().hex[:6]}",
        **payload.model_dump(),
    }
    printers.append(new_printer)
    save_printers_library(printers)
    return {"printer": new_printer, "printers": printers}


@printers_router.put("/{printer_id}")
async def update_printer(printer_id: str, payload: PrinterCreateOrUpdate):
    printers = load_printers_library()
    found = False
    for idx, p in enumerate(printers):
        if p.get("id") == printer_id:
            printers[idx] = {"id": printer_id, **payload.model_dump()}
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail=f"Imprimante '{printer_id}' introuvable.")
    save_printers_library(printers)
    return {"printers": printers}


@printers_router.post("/{printer_id}/toggle-module/{mod_key}")
async def toggle_printer_module_permission(printer_id: str, mod_key: str):
    printers = load_printers_library()
    field_map = {
        "cosplay": "use_cosplay",
        "hueforge": "use_hueforge",
        "lithophane": "use_lithophane",
    }
    target_field = field_map.get(mod_key)
    if not target_field:
        raise HTTPException(status_code=400, detail="Module inconnu.")
    for p in printers:
        if p.get("id") == printer_id:
            p[target_field] = not bool(p.get(target_field, True))
            break
    save_printers_library(printers)
    return {"printers": printers}


@printers_router.delete("/{printer_id}")
async def delete_printer(printer_id: str):
    printers = load_printers_library()
    if len(printers) <= 1:
        raise HTTPException(status_code=400, detail="Vous devez conserver au moins une imprimante configurée.")
    printers = [p for p in printers if p.get("id") != printer_id]
    save_printers_library(printers)
    return {"printers": printers}

