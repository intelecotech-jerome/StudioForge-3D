"""
MakerStudio 3D — Lithophane Globes, Planets, Lamp Standards & Multi-Shape Helpers
=================================================================================
Provides:
1. Built-in & Custom LED Lamp Standards registry (Bambu Lab LED Kit 001, USB Puck 38mm, E14, E27, Custom).
2. Procedural High-Resolution Planetary & Lunar Equirectangular Heightmaps (Moon, Earth, Mars, Jupiter, DeathStar/SciFi).
3. Watertight 3D Lithophane Sphere / Globe generator with bottom lamp opening + seating collar.
4. 4 Interchangeable Lamp Stands / Socles (`ring_bambu`, `tripod_modern`, `pedestal_fluted`, `crown_gothic`)
   with raised LED puck/socket mount and cable notch.
5. Raised Lamp Bridge on Support Bars for Framed Lightbox & 4-Face Cube Lightbox.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import manifold3d as m3d
import numpy as np
import shapely.geometry as sg
import trimesh
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter

from core.mesh_repair import manifold_to_trimesh


import sys

if getattr(sys, "frozen", False):
    _exe_data = Path(sys.executable).resolve().parent / "data"
    _internal_data = Path(getattr(sys, "_MEIPASS", _exe_data)) / "data"
    DATA_DIR = _exe_data if (_exe_data / "planet_maps").exists() else (_internal_data if (_internal_data / "planet_maps").exists() else _exe_data)
else:
    DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
LAMP_STANDARDS_FILE = DATA_DIR / "lamp_standards.json"
PLANET_MAPS_DIR = DATA_DIR / "planet_maps"
PLANET_STANDS_DIR = DATA_DIR / "planet_stands"

OFFICIAL_PLANET_CATALOG: List[Dict[str, str]] = [
    {"id": "planet_moon", "label": "🌕 Lune NASA (Cratères & Mers HD)", "file": "planet_moon.png"},
    {"id": "planet_earth", "label": "🌍 Terre Politique (Pays & Frontières)", "file": "planet_earth.png"},
    {"id": "planet_earth_topo", "label": "🏔️ Terre Topographique (Relief & Montagnes)", "file": "planet_earth_topo.png"},
    {"id": "planet_earth_day", "label": "🌎 Terre Satellite Jour (Continents)", "file": "planet_earth_day.png"},
    {"id": "planet_earth_bathy", "label": "🌊 Terre & Bathymétrie des Océans", "file": "planet_earth_bathy.png"},
    {"id": "planet_death_star", "label": "🪐 Étoile de la Mort (Star Wars HD)", "file": "planet_death_star.png"},
    {"id": "planet_mars", "label": "🔴 Mars (Olympus Mons & Valles Marineris)", "file": "planet_mars.png"},
    {"id": "planet_jupiter", "label": "🟠 Jupiter (Bandes & Grande Tache Rouge)", "file": "planet_jupiter.png"},
    {"id": "planet_saturn", "label": "🪐 Saturne (Atmosphère Planétaire)", "file": "planet_saturn.png"},
    {"id": "planet_sun", "label": "☀️ Le Soleil (Granulation & Éruptions)", "file": "planet_sun.png"},
    {"id": "planet_mercury", "label": "☿️ Mercure (Cratères Solaires)", "file": "planet_mercury.png"},
    {"id": "planet_venus", "label": "♀️ Vénus (Surface Volcanique Radar)", "file": "planet_venus.png"},
    {"id": "planet_venus_atmo", "label": "☁️ Vénus (Atmosphère Nuageuse)", "file": "planet_venus_atmo.png"},
    {"id": "planet_uranus", "label": "🔵 Uranus (Géante de Glace)", "file": "planet_uranus.png"},
    {"id": "planet_neptune", "label": "🔷 Neptune (Tempêtes Australes)", "file": "planet_neptune.png"},
    {"id": "planet_pluto", "label": "❄️ Pluton (Cœur Tombaugh Regio)", "file": "planet_pluto.png"},
    {"id": "planet_europa", "label": "🧊 Europe (Lune Glacée de Jupiter)", "file": "planet_europa.png"},
    {"id": "planet_callisto", "label": "🌑 Callisto (Lune Cratérisée)", "file": "planet_callisto.png"},
    {"id": "planet_universe", "label": "🌌 Fond Cosmologique de l'Univers", "file": "planet_universe.png"},
]

DEFAULT_LAMP_STANDARDS: List[Dict[str, Any]] = [
    {
        "id": "bambu_led_001",
        "name": "Bambu Lab — LED Lamp Kit 001 (Ø59.5 mm)",
        "puck_diameter_mm": 60.0,       # 59.5mm nominal + 0.5mm print clearance
        "inner_ledge_diameter_mm": 54.0,
        "recess_depth_mm": 9.0,
        "elevation_mm": 8.0,            # Slightly raised above table/bottom
        "cable_notch_width_mm": 8.5,
        "cable_notch_height_mm": 6.5,
        "is_builtin": True,
        "description": "Galet LED standard Bambu Lab (Ø59.5×8.5mm) avec réhausse et encoche fil USB.",
    },
    {
        "id": "usb_puck_38",
        "name": "Galet LED USB / Bougie LED (Ø38 mm)",
        "puck_diameter_mm": 38.6,
        "inner_ledge_diameter_mm": 33.0,
        "recess_depth_mm": 7.5,
        "elevation_mm": 7.0,
        "cable_notch_width_mm": 7.5,
        "cable_notch_height_mm": 5.5,
        "is_builtin": True,
        "description": "Petit galet LED USB ou bougie LED standard Ø38 mm.",
    },
    {
        "id": "socket_e14",
        "name": "Douille Ampoule Européenne E14 (Ø28 mm)",
        "puck_diameter_mm": 28.6,
        "inner_ledge_diameter_mm": 28.6,
        "recess_depth_mm": 10.0,
        "elevation_mm": 14.0,
        "cable_notch_width_mm": 8.5,
        "cable_notch_height_mm": 7.5,
        "is_builtin": True,
        "description": "Collerette standard pour douille filetée E14 avec bague de serrage.",
    },
    {
        "id": "socket_e27",
        "name": "Douille Ampoule Standard E27 (Ø40 mm)",
        "puck_diameter_mm": 40.6,
        "inner_ledge_diameter_mm": 40.6,
        "recess_depth_mm": 12.0,
        "elevation_mm": 15.0,
        "cable_notch_width_mm": 9.0,
        "cable_notch_height_mm": 8.0,
        "is_builtin": True,
        "description": "Collerette standard pour douille d'ampoule E27 Ø40 mm.",
    },
]


def load_lamp_standards() -> List[Dict[str, Any]]:
    """Loads built-in + user-saved custom LED lamp standards."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    custom_list: List[Dict[str, Any]] = []
    if LAMP_STANDARDS_FILE.exists():
        try:
            raw = json.loads(LAMP_STANDARDS_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                custom_list = [item for item in raw if not item.get("is_builtin", False)]
        except Exception:
            custom_list = []
    return DEFAULT_LAMP_STANDARDS + custom_list


def save_custom_lamp_standard(new_std: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Saves or updates a user-defined LED lamp standard."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    all_stds = load_lamp_standards()
    custom_stds = [s for s in all_stds if not s.get("is_builtin", False)]
    std_id = new_std.get("id") or f"custom_{len(custom_stds) + 1}"
    entry = {
        "id": std_id,
        "name": str(new_std.get("name", "Standard Lampe Personnalisé")),
        "puck_diameter_mm": float(new_std.get("puck_diameter_mm", 60.0)),
        "inner_ledge_diameter_mm": float(new_std.get("inner_ledge_diameter_mm", 54.0)),
        "recess_depth_mm": float(new_std.get("recess_depth_mm", 9.0)),
        "elevation_mm": float(new_std.get("elevation_mm", 8.0)),
        "cable_notch_width_mm": float(new_std.get("cable_notch_width_mm", 8.5)),
        "cable_notch_height_mm": float(new_std.get("cable_notch_height_mm", 6.5)),
        "is_builtin": False,
        "description": str(new_std.get("description", "Standard personnalisé encodé par l'utilisateur.")),
    }
    custom_stds = [s for s in custom_stds if s["id"] != std_id] + [entry]
    LAMP_STANDARDS_FILE.write_text(json.dumps(custom_stds, indent=2, ensure_ascii=False), encoding="utf-8")
    return DEFAULT_LAMP_STANDARDS + custom_stds


def delete_custom_lamp_standard(std_id: str) -> List[Dict[str, Any]]:
    all_stds = load_lamp_standards()
    custom_stds = [s for s in all_stds if not s.get("is_builtin", False) and s["id"] != std_id]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LAMP_STANDARDS_FILE.write_text(json.dumps(custom_stds, indent=2, ensure_ascii=False), encoding="utf-8")
    return DEFAULT_LAMP_STANDARDS + custom_stds


def resolve_lamp_spec(
    preset_id: str,
    custom_diameter_mm: Optional[float] = None,
    custom_elevation_mm: Optional[float] = None,
    custom_recess_mm: Optional[float] = None,
    custom_notch_w_mm: Optional[float] = None,
    custom_notch_h_mm: Optional[float] = None,
) -> Dict[str, float]:
    """Resolves exact mechanical dimensions (mm) for the chosen lamp standard."""
    stds = load_lamp_standards()
    found = next((s for s in stds if s["id"] == preset_id), DEFAULT_LAMP_STANDARDS[0])
    puck_d = float(custom_diameter_mm if custom_diameter_mm and custom_diameter_mm > 10 else found["puck_diameter_mm"])
    ledge_d = min(puck_d - 4.0, float(found.get("inner_ledge_diameter_mm", puck_d - 5.0)))
    if custom_diameter_mm and abs(custom_diameter_mm - found["puck_diameter_mm"]) > 1.0:
        ledge_d = max(12.0, puck_d - 5.5)
    return {
        "puck_diameter_mm": puck_d,
        "inner_ledge_diameter_mm": max(10.0, ledge_d),
        "recess_depth_mm": float(custom_recess_mm if custom_recess_mm is not None else found["recess_depth_mm"]),
        "elevation_mm": float(custom_elevation_mm if custom_elevation_mm is not None else found["elevation_mm"]),
        "cable_notch_width_mm": float(custom_notch_w_mm if custom_notch_w_mm is not None else found["cable_notch_width_mm"]),
        "cable_notch_height_mm": float(custom_notch_h_mm if custom_notch_h_mm is not None else found["cable_notch_height_mm"]),
    }


# ---------------------------------------------------------------------------
# Procedural Planetary & Lunar Equirectangular Maps (Luminance [0..1])
# ---------------------------------------------------------------------------

def generate_planetary_luminance_map(
    planet_mode: str,
    width: int = 1080,
    height: int = 540,
) -> Image.Image:
    """
    Loads the authentic high-resolution planetary/lunar relief map extracted from the user's
    official NASA/Political/DeathStar STL collection in `backend/data/planet_maps/`.
    Falls back to procedural generation only if the map file is absent.
    """
    map_path = PLANET_MAPS_DIR / f"{planet_mode}.png"
    if map_path.exists():
        try:
            pil_map = Image.open(map_path).convert("RGB")
            if pil_map.size != (width, height):
                pil_map = pil_map.resize((width, height), Image.Resampling.LANCZOS)
            return pil_map
        except Exception:
            pass

    rng = np.random.default_rng(seed={
        "planet_moon": 1969,
        "planet_earth": 2026,
        "planet_mars": 2035,
        "planet_jupiter": 1610,
        "planet_saturn": 1655,
    }.get(planet_mode, 42))

    # Normalized spherical coordinates: lon in [-pi, pi], lat in [-pi/2, pi/2]
    lon = np.linspace(-math.pi, math.pi, width, endpoint=False)[None, :]
    lat = np.linspace(math.pi / 2.0, -math.pi / 2.0, height)[:, None]
    cos_lat = np.cos(lat)
    sin_lat = np.sin(lat)

    # 3D unit vectors on the sphere for seamless 3D noise (no seam at lon = +/- pi!)
    ux = cos_lat * np.cos(lon)
    uy = cos_lat * np.sin(lon)
    uz = np.broadcast_to(sin_lat, (height, width))

    def spherical_fbm(freqs: List[float], weights: List[float]) -> np.ndarray:
        acc = np.zeros((height, width), dtype=np.float32)
        for f, w in zip(freqs, weights):
            # Random wave directions in 3D
            for _ in range(5):
                kx, ky, kz = rng.normal(0, 1, 3)
                norm = max(1e-5, math.hypot(kx, ky, kz))
                kx, ky, kz = kx / norm * f, ky / norm * f, kz / norm * f
                phase = rng.uniform(0, 2 * math.pi)
                acc += w * np.sin(ux * kx + uy * ky + uz * kz + phase)
        acc = (acc - acc.min()) / max(1e-6, acc.max() - acc.min())
        return acc

    if planet_mode == "planet_moon":
        # Base lunar highlands (bright) + dark basaltic Maria (Oceanus Procellarum, Mare Tranquillitatis, Imbrium...)
        base = 0.68 + 0.16 * spherical_fbm([2.2, 5.0, 11.0], [0.55, 0.30, 0.15])

        # Major Lunar Maria (dark plains in lithophane = thicker wall, craters/highlands = brighter)
        maria_centers = [
            (0.45, -0.35, 0.52, 0.34),   # Mare Imbrium
            (0.15, 0.50, 0.42, 0.28),    # Mare Serenitatis
            (-0.05, 0.65, 0.40, 0.26),   # Mare Tranquillitatis
            (0.20, -0.95, 0.65, 0.32),   # Oceanus Procellarum
            (-0.35, -0.25, 0.38, 0.24),  # Mare Nubium
            (0.28, 1.02, 0.28, 0.26),    # Mare Crisium
        ]
        for m_lat, m_lon, rad, depth in maria_centers:
            mx = math.cos(m_lat) * math.cos(m_lon)
            my = math.cos(m_lat) * math.sin(m_lon)
            mz = math.sin(m_lat)
            ang_dist = np.arccos(np.clip(ux * mx + uy * my + uz * mz, -1.0, 1.0))
            mask = np.clip(1.0 - (ang_dist / rad) ** 2, 0.0, 1.0) ** 1.5
            base -= depth * mask

        # Add 260 multi-scale impact craters with depressed bowls, bright raised rims, and ejecta rays
        n_craters = 260
        for idx in range(n_craters):
            # Uniform point on sphere
            cz = rng.uniform(-0.95, 0.95)
            clon = rng.uniform(-math.pi, math.pi)
            clat_cos = math.sqrt(max(0.0, 1.0 - cz * cz))
            cx = clat_cos * math.cos(clon)
            cy = clat_cos * math.sin(clon)

            # Power-law radius distribution
            r_crater = float(rng.pareto(2.3) * 0.025 + 0.014)
            r_crater = min(r_crater, 0.26)

            ang = np.arccos(np.clip(ux * cx + uy * cy + uz * cz, -1.0, 1.0))
            norm_r = ang / r_crater

            # Bowl + Rim profile
            in_crater = norm_r < 1.65
            if not np.any(in_crater):
                continue
            nr = norm_r[in_crater]
            # Bright crater floor + bright sharp rim + dark inner shadow ring
            rim = 0.22 * np.exp(-((nr - 1.0) / 0.16) ** 2)
            bowl = -0.14 * np.clip(1.0 - nr ** 2, 0.0, 1.0)
            central_peak = (0.16 * np.exp(-(nr / 0.20) ** 2)) if r_crater > 0.08 else 0.0
            base[in_crater] += rim + bowl + central_peak

        # Fine regolith micro-texture
        fine = spherical_fbm([24.0, 48.0], [0.6, 0.4])
        lum = np.clip(base + (fine - 0.5) * 0.09, 0.05, 0.98)

    elif planet_mode == "planet_earth":
        # Continents vs Oceans
        macro = spherical_fbm([1.8, 3.8, 8.5, 18.0], [0.50, 0.26, 0.15, 0.09])
        # Ocean mask (threshold around 0.48)
        is_land = macro > 0.47
        lum = np.where(
            is_land,
            0.25 + 0.55 * ((macro - 0.47) / 0.53),  # Darker/thicker continents with mountain relief
            0.82 + 0.12 * (macro / 0.47),            # Bright glowing oceans
        )
        # Bright polar ice caps
        polar = np.clip((np.abs(sin_lat) - 0.78) / 0.22, 0.0, 1.0) ** 1.4
        lum = np.clip(lum * (1.0 - polar) + 0.96 * polar, 0.05, 0.98)

    elif planet_mode == "planet_mars":
        base = 0.45 + 0.35 * spherical_fbm([1.6, 4.2, 10.0, 22.0], [0.45, 0.28, 0.17, 0.10])
        # Valles Marineris equatorial canyon (bright glowing rift)
        canyon = np.exp(-((lat + 0.12) / 0.09) ** 2) * np.exp(-((lon - 0.3) / 0.65) ** 2)
        base += 0.32 * canyon
        # Olympus Mons + Tharsis shield volcanoes (dark high-relief peaks)
        for v_lat, v_lon, v_r in [(0.32, -1.2, 0.16), (0.15, -0.95, 0.11), (0.02, -0.85, 0.11), (-0.12, -0.75, 0.11)]:
            vx = math.cos(v_lat) * math.cos(v_lon)
            vy = math.cos(v_lat) * math.sin(v_lon)
            vz = math.sin(v_lat)
            ang = np.arccos(np.clip(ux * vx + uy * vy + uz * vz, -1.0, 1.0))
            cone = np.clip(1.0 - ang / v_r, 0.0, 1.0) ** 1.5
            caldera = 0.25 * np.exp(-((ang / (v_r * 0.22)) ** 2))
            base -= 0.34 * cone - caldera
        lum = np.clip(base, 0.06, 0.96)

    elif planet_mode == "planet_jupiter":
        # Zonal turbulent cloud belts + Great Red Spot
        turbulence = spherical_fbm([3.5, 8.0, 16.0], [0.5, 0.3, 0.2])
        lat_perturbed = lat + 0.08 * (turbulence - 0.5)
        bands = 0.52 + 0.32 * np.cos(lat_perturbed * 14.0) + 0.12 * np.sin(lat_perturbed * 29.0)
        # Great Red Spot at lat = -22 deg (-0.38 rad), lon = 0.4 rad
        d_lat = (lat + 0.38) / 0.16
        d_lon = (lon - 0.40) / 0.30
        grs_r = np.hypot(d_lat, d_lon)
        grs_mask = np.clip(1.0 - grs_r ** 2, 0.0, 1.0)
        grs_swirl = -0.35 * grs_mask + 0.18 * np.exp(-((grs_r - 0.85) / 0.15) ** 2)
        lum = np.clip(bands + grs_swirl, 0.08, 0.96)

    else:
        # Sci-Fi Death Star / Cyber Globe with Equatorial Trench & Superlaser Dish
        base = 0.62 + 0.15 * spherical_fbm([6.0, 16.0], [0.6, 0.4])
        # Grid panel lines
        lat_grid = (np.abs(np.sin(lat * 18.0)) > 0.96).astype(np.float32) * 0.18
        lon_grid = (np.abs(np.sin(lon * 24.0)) > 0.96).astype(np.float32) * 0.18
        # Equatorial trench
        trench = (np.abs(lat) < 0.045).astype(np.float32) * 0.30
        # Superlaser dish in northern hemisphere
        dish_lat, dish_lon = 0.48, 0.0
        dx = math.cos(dish_lat) * math.cos(dish_lon)
        dy = math.cos(dish_lat) * math.sin(dish_lon)
        dz = math.sin(dish_lat)
        ang = np.arccos(np.clip(ux * dx + uy * dy + uz * dz, -1.0, 1.0))
        dish = np.where(ang < 0.36, 0.25 * np.cos(ang / 0.36 * math.pi * 3.0), 0.0)
        lum = np.clip(base + lat_grid + lon_grid + trench + dish, 0.08, 0.96)

    arr_u8 = (np.clip(lum, 0.0, 1.0) * 255.0).astype(np.uint8)
    return Image.fromarray(arr_u8, mode="L").convert("RGB")


# ---------------------------------------------------------------------------
# 3D Lithophane Sphere / Globe Mesh Generator (with Bottom Opening & Collar)
# ---------------------------------------------------------------------------

def build_sphere_globe_lithophane_mesh(
    t_grid: np.ndarray,
    outer_diameter_mm: float = 140.0,
    min_thickness_mm: float = 0.8,
    max_thickness_mm: float = 3.0,
    lamp_spec: Dict[str, float] = None,
) -> Tuple[trimesh.Trimesh, Dict[str, float]]:
    """
    Builds a 100% watertight hollow 3D Lithophane Sphere/Globe with:
    - Smooth Inner Spherical Wall (`R_in = outer_diameter_mm / 2 - max_thickness_mm`)
    - Modulated Outer Spherical Wall (`R_out(theta, phi) = R_in + t_grid(theta, phi)`)
    - Bottom Circular Opening calibrated to the lamp standard (`hole_diameter_mm`)
    - Vertical cylindrical seating lip / collar at the bottom so the globe sits securely on any Socle!
    Returns `(globe_mesh, geometry_info)`.
    """
    if lamp_spec is None:
        lamp_spec = resolve_lamp_spec("bambu_led_001")

    ny, nx = t_grid.shape  # ny = latitude steps (from North Pole to South Cutoff), nx = longitude steps
    r_nom_outer = max(35.0, outer_diameter_mm * 0.5)
    r_in = max(25.0, r_nom_outer - max_thickness_mm)

    # Bottom opening radius: allows the LED puck light (or bulb) to enter/illuminate from the base
    puck_r = lamp_spec["puck_diameter_mm"] * 0.5
    # Keep opening radius at most 62% of sphere inner radius so the sphere remains a true globe
    open_r_in = min(r_in * 0.62, max(18.0, puck_r * 0.88))
    collar_wall = 2.6
    open_r_out = open_r_in + collar_wall
    collar_drop_mm = 6.0

    # Cutoff latitude angle from North Pole (phi = 0 at North Pole, phi_max near South Pole)
    sin_cutoff = min(0.85, open_r_in / r_in)
    phi_max = math.pi - math.asin(sin_cutoff)

    # Polar feathering near North Pole (first 6% of rows) and South Cutoff (last 5% of rows)
    t_work = t_grid.astype(np.float64).copy()
    north_rows = max(3, int(ny * 0.06))
    for r_idx in range(north_rows):
        alpha = r_idx / float(north_rows)
        row_mean = float(np.mean(t_work[r_idx, :]))
        t_work[r_idx, :] = row_mean * (1.0 - alpha) + t_work[r_idx, :] * alpha

    south_rows = max(3, int(ny * 0.06))
    for s_idx in range(south_rows):
        r_idx = ny - 1 - s_idx
        alpha = s_idx / float(south_rows)
        t_work[r_idx, :] = collar_wall * (1.0 - alpha) + t_work[r_idx, :] * alpha

    # Sphere center Z so the bottom of the collar sits at Z = 0
    z_cutoff_rel = r_in * math.cos(phi_max)  # negative value
    sphere_center_z = -z_cutoff_rel + collar_drop_mm

    phis = np.linspace(0.025, phi_max, ny)  # start slightly off exact 0 to form clean polar cap ring
    thetas = np.linspace(0.0, 2.0 * math.pi, nx, endpoint=False)

    sin_p = np.sin(phis)[:, None]
    cos_p = np.cos(phis)[:, None]
    cos_t = np.cos(thetas)[None, :]
    sin_t = np.sin(thetas)[None, :]

    r_out_grid = r_in + t_work

    # Outer surface vertices: (ny, nx, 3)
    xo = (r_out_grid * sin_p) * cos_t
    yo = (r_out_grid * sin_p) * sin_t
    zo = (r_out_grid * cos_p) + sphere_center_z
    v_out = np.stack([xo, yo, np.broadcast_to(zo, (ny, nx))], axis=-1).reshape(-1, 3)

    # Inner surface vertices: (ny, nx, 3)
    xi = (r_in * sin_p) * cos_t
    yi = (r_in * sin_p) * sin_t
    zi = (r_in * cos_p) + sphere_center_z
    v_in = np.stack([xi, yi, np.broadcast_to(zi, (ny, nx))], axis=-1).reshape(-1, 3)

    # Bottom collar bottom ring (at Z = 0)
    xc_out = open_r_out * np.cos(thetas)
    yc_out = open_r_out * np.sin(thetas)
    zc_out = np.zeros_like(thetas)
    v_collar_out = np.stack([xc_out, yc_out, zc_out], axis=-1)

    xc_in = open_r_in * np.cos(thetas)
    yc_in = open_r_in * np.sin(thetas)
    zc_in = np.zeros_like(thetas)
    v_collar_in = np.stack([xc_in, yc_in, zc_in], axis=-1)

    # North pole center vertices (top outer and top inner)
    z_north_out = float(np.mean(r_out_grid[0, :])) + sphere_center_z
    z_north_in = float(r_in) + sphere_center_z
    v_poles = np.array([
        [0.0, 0.0, z_north_out],
        [0.0, 0.0, z_north_in],
    ], dtype=np.float64)

    n_surf = ny * nx
    idx_collar_out = 2 * n_surf
    idx_collar_in = idx_collar_out + nx
    idx_pole_out = idx_collar_in + nx
    idx_pole_in = idx_pole_out + 1

    all_verts = np.vstack([v_out, v_in, v_collar_out, v_collar_in, v_poles])
    faces_list: List[np.ndarray] = []

    # 1. Outer & Inner spherical quad strips
    rr = np.arange(ny - 1)[:, None]
    cc = np.arange(nx)[None, :]
    cc_next = (cc + 1) % nx

    p00 = rr * nx + cc
    p10 = rr * nx + cc_next
    p01 = (rr + 1) * nx + cc
    p11 = (rr + 1) * nx + cc_next

    # Outer normal points outward
    f_out_1 = np.stack([p00, p01, p11], axis=-1).reshape(-1, 3)
    f_out_2 = np.stack([p00, p11, p10], axis=-1).reshape(-1, 3)
    faces_list.extend([f_out_1, f_out_2])

    # Inner normal points inward
    i00 = n_surf + p00
    i10 = n_surf + p10
    i01 = n_surf + p01
    i11 = n_surf + p11
    f_in_1 = np.stack([i00, i11, i01], axis=-1).reshape(-1, 3)
    f_in_2 = np.stack([i00, i10, i11], axis=-1).reshape(-1, 3)
    faces_list.extend([f_in_1, f_in_2])

    # 2. North Pole cap fans (Outer & Inner)
    c_idx = np.arange(nx)
    c_next = (c_idx + 1) % nx
    f_north_out = np.stack([np.full(nx, idx_pole_out), c_idx, c_next], axis=-1)
    f_north_in = np.stack([np.full(nx, idx_pole_in), n_surf + c_next, n_surf + c_idx], axis=-1)
    faces_list.extend([f_north_out, f_north_in])

    # 3. South Cutoff to Bottom Collar walls + Bottom Annular Rim
    last_out = (ny - 1) * nx + c_idx
    last_out_next = (ny - 1) * nx + c_next
    co_curr = idx_collar_out + c_idx
    co_next = idx_collar_out + c_next

    f_col_out_1 = np.stack([last_out, co_curr, co_next], axis=-1)
    f_col_out_2 = np.stack([last_out, co_next, last_out_next], axis=-1)

    last_in = n_surf + (ny - 1) * nx + c_idx
    last_in_next = n_surf + (ny - 1) * nx + c_next
    ci_curr = idx_collar_in + c_idx
    ci_next = idx_collar_in + c_next

    f_col_in_1 = np.stack([last_in, ci_next, ci_curr], axis=-1)
    f_col_in_2 = np.stack([last_in, last_in_next, ci_next], axis=-1)

    # Bottom flat rim connecting collar_out to collar_in
    f_rim_1 = np.stack([co_curr, ci_curr, ci_next], axis=-1)
    f_rim_2 = np.stack([co_curr, ci_next, co_next], axis=-1)

    faces_list.extend([f_col_out_1, f_col_out_2, f_col_in_1, f_col_in_2, f_rim_1, f_rim_2])

    all_faces = np.vstack(faces_list).astype(np.int64)
    mesh = trimesh.Trimesh(vertices=all_verts, faces=all_faces, process=True)
    trimesh.repair.fix_normals(mesh)

    geom_info = {
        "outer_diameter_mm": round(outer_diameter_mm, 2),
        "sphere_center_z_mm": round(sphere_center_z, 2),
        "open_r_in_mm": round(open_r_in, 2),
        "open_r_out_mm": round(open_r_out, 2),
        "collar_drop_mm": round(collar_drop_mm, 2),
    }
    return mesh, geom_info


# ---------------------------------------------------------------------------
# 4 Interchangeable Lamp Stands (Socles) for Spherical Globes
# ---------------------------------------------------------------------------

def _build_annular_ring_with_cable_notch(
    r_inner: float,
    r_outer: float,
    z_bottom: float,
    z_top: float,
    notch_width_mm: float = 0.0,
    notch_height_mm: float = 0.0,
    n_seg: int = 96,
) -> trimesh.Trimesh:
    """Builds a solid cylindrical ring (or disk if r_inner <= 0.1) with an optional rear cable notch."""
    cyl_out = trimesh.creation.cylinder(radius=r_outer, height=z_top - z_bottom, sections=n_seg)
    cyl_out.apply_translation([0.0, 0.0, (z_bottom + z_top) * 0.5])
    parts = [cyl_out]
    # We use direct radial vertex construction so it is 100% fast & watertight without slow boolean ops
    thetas = np.linspace(0.0, 2.0 * math.pi, n_seg, endpoint=False)
    cos_t = np.cos(thetas)
    sin_t = np.sin(thetas)

    # Modulate z_bottom around +Y (theta = pi/2) if cable notch is requested
    z_bot_arr = np.full(n_seg, z_bottom, dtype=np.float64)
    if notch_width_mm > 0.5 and notch_height_mm > 0.5:
        notch_h = min(notch_height_mm, (z_top - z_bottom) * 0.72)
        for i in range(n_seg):
            # Rear of stand is Y > 0, |X| <= notch_width_mm / 2
            x_val = r_outer * cos_t[i]
            y_val = r_outer * sin_t[i]
            if y_val > 0 and abs(x_val) <= notch_width_mm * 0.55:
                z_bot_arr[i] = z_bottom + notch_h

    r_in = max(0.5, r_inner)
    v_bot_out = np.stack([r_outer * cos_t, r_outer * sin_t, z_bot_arr], axis=-1)
    v_top_out = np.stack([r_outer * cos_t, r_outer * sin_t, np.full(n_seg, z_top)], axis=-1)
    v_bot_in = np.stack([r_in * cos_t, r_in * sin_t, z_bot_arr], axis=-1)
    v_top_in = np.stack([r_in * cos_t, r_in * sin_t, np.full(n_seg, z_top)], axis=-1)

    verts = np.vstack([v_bot_out, v_top_out, v_bot_in, v_top_in])
    idx = np.arange(n_seg)
    nxt = (idx + 1) % n_seg

    bo = idx
    bo_n = nxt
    to = n_seg + idx
    to_n = n_seg + nxt
    bi = 2 * n_seg + idx
    bi_n = 2 * n_seg + nxt
    ti = 3 * n_seg + idx
    ti_n = 3 * n_seg + nxt

    f_out1 = np.stack([bo, bo_n, to_n], axis=-1)
    f_out2 = np.stack([bo, to_n, to], axis=-1)
    f_in1 = np.stack([bi, ti_n, bi_n], axis=-1)
    f_in2 = np.stack([bi, ti, ti_n], axis=-1)
    f_top1 = np.stack([to, to_n, ti_n], axis=-1)
    f_top2 = np.stack([to, ti_n, ti], axis=-1)
    f_bot1 = np.stack([bo, bi_n, bo_n], axis=-1)
    f_bot2 = np.stack([bo, bi, bi_n], axis=-1)

    faces = np.vstack([f_out1, f_out2, f_in1, f_in2, f_top1, f_top2, f_bot1, f_bot2])
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    trimesh.repair.fix_normals(mesh)
    return mesh


def build_globe_lamp_stand_mesh(
    stand_style: str,
    globe_info: Dict[str, float],
    lamp_spec: Dict[str, float],
) -> trimesh.Trimesh:
    """
    Builds or loads the chosen Lamp Stand (Socle) for the Lithophane Globe:
    Supports the 5 official STL stands from the user's collection:
    - `stand_bambu_official` (`04_bambu_base.stl`)
    - `stand_rock_lunar` (`05_rock_base.stl` — Socle Rocheux Lunaire)
    - `stand_wavy_moon` (`Moon Lamp - Wavy Stand.stl` — Socle Ondulé Design)
    - `stand_legacy_smooth` (`02_legacy_base_no_threads.stl`)
    - `stand_legacy_threaded` (`02_legacy_base_threaded.stl`)
    Plus the 4 parametric stands (`ring_bambu`, `tripod_modern`, `pedestal_fluted`, `crown_gothic`).
    """
    official_stl_map = {
        "stand_bambu_official": "stand_bambu_official.stl",
        "stand_rock_lunar": "stand_rock_lunar.stl",
        "stand_wavy_moon": "stand_wavy_moon.stl",
        "stand_legacy_smooth": "stand_legacy_smooth.stl",
        "stand_legacy_threaded": "stand_legacy_threaded.stl",
    }
    if stand_style in official_stl_map:
        stl_path = PLANET_STANDS_DIR / official_stl_map[stand_style]
        if stl_path.exists():
            try:
                loaded = trimesh.load(stl_path, force="mesh")
                bmin, bmax = loaded.bounds
                cx = 0.5 * (bmin[0] + bmax[0])
                cy = 0.5 * (bmin[1] + bmax[1])
                loaded.apply_translation([-cx, -cy, -bmin[2]])
                return loaded
            except Exception:
                pass

    puck_r = lamp_spec["puck_diameter_mm"] * 0.5
    ledge_r = lamp_spec["inner_ledge_diameter_mm"] * 0.5
    recess_h = lamp_spec["recess_depth_mm"]
    elev_h = max(6.0, lamp_spec["elevation_mm"])
    notch_w = lamp_spec["cable_notch_width_mm"]
    notch_h = lamp_spec["cable_notch_height_mm"]

    collar_r_out = globe_info.get("open_r_out_mm", puck_r + 3.0)
    seat_r_inner = max(puck_r + 0.4, collar_r_out + 0.45)
    seat_wall = 4.2
    seat_r_outer = seat_r_inner + seat_wall

    total_lamp_h = elev_h + recess_h
    seat_lip_h = 6.5

    parts: List[trimesh.Trimesh] = []

    # 1. Central Raised Lamp Puck / Socket Housing (present in all stands)
    # Lower support ring (from z=0 to z=elev_h) with cable notch and inner ledge
    lower_ring = _build_annular_ring_with_cable_notch(
        r_inner=ledge_r,
        r_outer=puck_r + 3.2,
        z_bottom=0.0,
        z_top=elev_h,
        notch_width_mm=notch_w,
        notch_height_mm=notch_h,
    )
    parts.append(lower_ring)

    # Upper lamp recess collar (holds the LED puck laterally from z=elev_h to z=total_lamp_h)
    puck_collar = _build_annular_ring_with_cable_notch(
        r_inner=puck_r,
        r_outer=puck_r + 3.2,
        z_bottom=elev_h - 0.5,
        z_top=total_lamp_h,
        notch_width_mm=notch_w * 0.85,
        notch_height_mm=min(3.5, recess_h * 0.45),
    )
    parts.append(puck_collar)

    # 2. Globe Seating Ring (where the globe's bottom collar rests)
    seat_z_base = total_lamp_h - 2.0
    globe_seat = _build_annular_ring_with_cable_notch(
        r_inner=seat_r_inner,
        r_outer=seat_r_outer,
        z_bottom=seat_z_base,
        z_top=seat_z_base + seat_lip_h,
        notch_width_mm=0.0,
        notch_height_mm=0.0,
    )
    parts.append(globe_seat)

    # Bridge floor connecting the lamp collar (`puck_r + 3.2`) to the globe seat (`seat_r_outer`)
    bridge_ring = _build_annular_ring_with_cable_notch(
        r_inner=min(puck_r, seat_r_inner) - 0.5,
        r_outer=seat_r_outer,
        z_bottom=max(0.0, seat_z_base - 3.5),
        z_top=seat_z_base + 0.5,
        notch_width_mm=0.0,
        notch_height_mm=0.0,
    )
    parts.append(bridge_ring)

    # 3. Outer Stand Architecture according to `stand_style`
    if stand_style == "ring_bambu":
        # Sleek wide chamfered ring base from z=0 to seat_z_base + seat_lip_h
        outer_skirt = _build_annular_ring_with_cable_notch(
            r_inner=puck_r + 2.0,
            r_outer=seat_r_outer + 4.5,
            z_bottom=0.0,
            z_top=seat_z_base + seat_lip_h * 0.65,
            notch_width_mm=notch_w,
            notch_height_mm=notch_h,
        )
        parts.append(outer_skirt)

    elif stand_style == "tripod_modern":
        # 3 sculpted tripod legs extending outward and curving up to cradle the globe
        n_legs = 3
        leg_reach = seat_r_outer + 18.0
        for k in range(n_legs):
            ang = k * (2.0 * math.pi / n_legs) - math.pi / 6.0
            ca, sa = math.cos(ang), math.sin(ang)
            # Horizontal strut from central lamp housing to foot pad
            strut_len = leg_reach - (puck_r * 0.8)
            strut = trimesh.creation.box(extents=[strut_len, 9.0, 6.5])
            strut.apply_translation([(puck_r * 0.8 + leg_reach) * 0.5, 0.0, 3.25])
            rot_z = trimesh.transformations.rotation_matrix(ang, [0, 0, 1])
            strut.apply_transform(rot_z)
            parts.append(strut)

            # Upward angled leg pillar supporting the globe seat & lower hemisphere
            pillar_h = seat_z_base + seat_lip_h + 14.0
            pillar = trimesh.creation.cylinder(radius=5.2, height=pillar_h, sections=24)
            # Tilt inward slightly
            tilt = trimesh.transformations.rotation_matrix(-0.26, [0, 1, 0])
            pillar.apply_transform(tilt)
            pillar.apply_translation([seat_r_outer + 4.5, 0.0, pillar_h * 0.46])
            pillar.apply_transform(rot_z)
            parts.append(pillar)

            # Rounded foot pad at z=0
            foot = trimesh.creation.cylinder(radius=7.5, height=4.0, sections=24)
            foot.apply_translation([leg_reach - 3.0, 0.0, 2.0])
            foot.apply_transform(rot_z)
            parts.append(foot)

    elif stand_style == "pedestal_fluted":
        # Classical fluted architectural column base with 16 vertical flutes
        ped_r = seat_r_outer + 5.0
        base_plinth = _build_annular_ring_with_cable_notch(
            r_inner=puck_r + 2.0,
            r_outer=ped_r + 5.5,
            z_bottom=0.0,
            z_top=5.0,
            notch_width_mm=notch_w,
            notch_height_mm=notch_h,
        )
        parts.append(base_plinth)

        col_body = _build_annular_ring_with_cable_notch(
            r_inner=puck_r + 2.0,
            r_outer=ped_r,
            z_bottom=4.5,
            z_top=seat_z_base + seat_lip_h * 0.8,
            notch_width_mm=notch_w,
            notch_height_mm=max(0.0, notch_h - 4.5),
        )
        parts.append(col_body)

        # 16 decorative vertical ribs around the column
        n_ribs = 16
        rib_h = max(6.0, seat_z_base + seat_lip_h * 0.7 - 4.5)
        for k in range(n_ribs):
            ang = k * (2.0 * math.pi / n_ribs)
            # Skip rib right on the rear cable notch
            if math.sin(ang) > 0.85 and abs(math.cos(ang) * ped_r) < notch_w:
                continue
            rib = trimesh.creation.cylinder(radius=2.2, height=rib_h, sections=16)
            rib.apply_translation([
                ped_r * math.cos(ang),
                ped_r * math.sin(ang),
                4.5 + rib_h * 0.5,
            ])
            parts.append(rib)

    else:  # crown_gothic (4 royal claws cradling the globe)
        outer_base = _build_annular_ring_with_cable_notch(
            r_inner=puck_r + 2.0,
            r_outer=seat_r_outer + 6.0,
            z_bottom=0.0,
            z_top=6.0,
            notch_width_mm=notch_w,
            notch_height_mm=notch_h,
        )
        parts.append(outer_base)

        n_claws = 4
        claw_h = seat_z_base + seat_lip_h + 18.0
        for k in range(n_claws):
            ang = k * (math.pi / 2.0) + math.pi / 4.0  # 45°, 135°, 225°, 315° (clears rear cable notch at 90°!)
            rot_z = trimesh.transformations.rotation_matrix(ang, [0, 0, 1])
            # Lower buttress
            buttress = trimesh.creation.box(extents=[12.0, 7.0, 10.0])
            buttress.apply_translation([seat_r_outer + 3.0, 0.0, 5.0])
            buttress.apply_transform(rot_z)
            parts.append(buttress)

            # Upper tapered claw finger
            claw = trimesh.creation.cone(radius=5.5, height=claw_h, sections=20)
            tilt = trimesh.transformations.rotation_matrix(-0.18, [0, 1, 0])
            claw.apply_transform(tilt)
            claw.apply_translation([seat_r_outer + 4.8, 0.0, 2.0])
            claw.apply_transform(rot_z)
            parts.append(claw)

    stand_mesh = trimesh.util.concatenate(parts)
    stand_mesh.merge_vertices()
    trimesh.repair.fix_normals(stand_mesh)
    return stand_mesh


# ---------------------------------------------------------------------------
# Internal Lamp Holder on Support Bars (for Framed Lightbox & 4-Face Cube)
# ---------------------------------------------------------------------------

def build_suspended_lamp_holder_bars(
    inner_span_x: float,
    inner_span_y: float,
    z_base: float,
    lamp_spec: Dict[str, float],
) -> List[trimesh.Trimesh]:
    """
    Builds a central raised LED lamp ring/cradle held by 4 sturdy horizontal/diagonal
    support bars attached to the inner walls of a Lightbox or 4-Face Cube.
    This leaves the bottom open for airflow and cable routing while holding the lamp
    securely at the center!
    """
    puck_r = lamp_spec["puck_diameter_mm"] * 0.5
    ledge_r = lamp_spec["inner_ledge_diameter_mm"] * 0.5
    recess_h = lamp_spec["recess_depth_mm"]
    elev_h = max(6.0, lamp_spec["elevation_mm"])
    notch_w = lamp_spec["cable_notch_width_mm"]
    notch_h = lamp_spec["cable_notch_height_mm"]

    # Ensure lamp ring fits inside inner_span
    max_allowed_r = min(inner_span_x, inner_span_y) * 0.42
    if puck_r > max_allowed_r:
        puck_r = max_allowed_r
        ledge_r = max(8.0, puck_r - 4.5)

    holder_parts: List[trimesh.Trimesh] = []

    # 1. Central elevated lamp ring with inner ledge & cable notch
    ring_base = _build_annular_ring_with_cable_notch(
        r_inner=ledge_r,
        r_outer=puck_r + 3.2,
        z_bottom=z_base,
        z_top=z_base + elev_h,
        notch_width_mm=notch_w,
        notch_height_mm=notch_h,
    )
    holder_parts.append(ring_base)

    ring_collar = _build_annular_ring_with_cable_notch(
        r_inner=puck_r,
        r_outer=puck_r + 3.2,
        z_bottom=z_base + elev_h - 0.5,
        z_top=z_base + elev_h + recess_h,
        notch_width_mm=notch_w * 0.85,
        notch_height_mm=min(3.5, recess_h * 0.45),
    )
    holder_parts.append(ring_collar)

    # 2. 4 Support Bars connecting the central lamp ring to the 4 outer walls
    bar_h = min(7.0, elev_h)
    bar_w = 7.5

    # X-axis bar (Left wall to Right wall, split around inner ledge hole)
    half_x_len = max(4.0, (inner_span_x * 0.5) - ledge_r + 1.5)
    for sign_x in (-1.0, 1.0):
        bx = trimesh.creation.box(extents=[half_x_len, bar_w, bar_h])
        bx.apply_translation([
            sign_x * (ledge_r + half_x_len * 0.5 - 0.75),
            0.0,
            z_base + bar_h * 0.5,
        ])
        holder_parts.append(bx)

    # Y-axis bar (Front wall to Back wall, with rear bar raised above cable notch if needed)
    half_y_len = max(4.0, (inner_span_y * 0.5) - ledge_r + 1.5)
    for sign_y in (-1.0, 1.0):
        by = trimesh.creation.box(extents=[bar_w, half_y_len, bar_h])
        by.apply_translation([
            0.0,
            sign_y * (ledge_r + half_y_len * 0.5 - 0.75),
            z_base + bar_h * 0.5,
        ])
        holder_parts.append(by)

    return holder_parts


# ---------------------------------------------------------------------------
# 6 New Lithophane 3D Architectures (Dual, Polygon, Cone, Balloon, Vase, Stencil)
# ---------------------------------------------------------------------------

def build_accordion_dual_lithophane_mesh(
    t_grid: np.ndarray,
    total_width_mm: float,
    height_mm: float,
    num_panels: int = 3,
    fold_angle_deg: float = 34.0,
    border_width_mm: float = 4.0,
    frame_thickness_mm: float = 3.8,
) -> trimesh.Trimesh:
    """
    Builds a self-standing Accordion / Zig-Zag ("Dual") Lithophane Screen (`num_panels = 2, 3, or 4`).
    Each panel folds at `+fold_angle_deg` / `-fold_angle_deg` alternately with reinforced vertical
    hinge pillars and top/bottom frames so it stands upright on a desk with zero supports!
    """
    n_p = max(2, min(4, int(num_panels)))
    grid = t_grid.copy()
    ny, nx = grid.shape
    by = max(1, int(round((border_width_mm / max(1.0, height_mm)) * ny)))
    bx = max(1, int(round((border_width_mm / max(1.0, total_width_mm)) * nx)))
    if border_width_mm > 0.1:
        grid[:by, :] = frame_thickness_mm
        grid[ny - by :, :] = frame_thickness_mm
        grid[:, :bx] = frame_thickness_mm
        grid[:, nx - bx :] = frame_thickness_mm
        # Reinforce vertical fold seams between panels
        for p_i in range(1, n_p):
            seam_c = int(round((p_i / float(n_p)) * (nx - 1)))
            half_s = max(1, bx // 2)
            c0 = max(0, seam_c - half_s)
            c1 = min(nx, seam_c + half_s + 1)
            grid[:, c0:c1] = frame_thickness_mm

    grid_flipped = np.flipud(grid).astype(np.float64)

    # Compute 2D zig-zag centerline (x_c(c), y_c(c)) and outward normal (nx_c(c), ny_c(c))
    ang_rad = math.radians(max(18.0, min(55.0, float(fold_angle_deg))))
    u_norm = np.linspace(0.0, float(n_p), nx, dtype=np.float64)
    panel_w = float(total_width_mm) / float(n_p)

    x_center = np.zeros(nx, dtype=np.float64)
    y_center = np.zeros(nx, dtype=np.float64)
    norm_x = np.zeros(nx, dtype=np.float64)
    norm_y = np.zeros(nx, dtype=np.float64)

    cur_x = 0.0
    cur_y = 0.0
    panel_starts_x = []
    panel_starts_y = []
    panel_dirs = []
    for p_i in range(n_p):
        sign = 1.0 if (p_i % 2 == 0) else -1.0
        theta_p = sign * ang_rad
        dx = math.cos(theta_p)
        dy = math.sin(theta_p)
        panel_starts_x.append(cur_x)
        panel_starts_y.append(cur_y)
        panel_dirs.append((dx, dy))
        cur_x += panel_w * dx
        cur_y += panel_w * dy

    for c_i in range(nx):
        u_val = u_norm[c_i]
        p_idx = min(n_p - 1, int(math.floor(u_val)))
        local_t = (u_val - p_idx) * panel_w
        dx, dy = panel_dirs[p_idx]
        x_center[c_i] = panel_starts_x[p_idx] + local_t * dx
        y_center[c_i] = panel_starts_y[p_idx] + local_t * dy
        # Front normal points toward -Y (viewer)
        norm_x[c_i] = dy
        norm_y[c_i] = -dx

    # Smooth normals slightly at fold vertices so outer surface doesn't self-intersect
    norm_x = gaussian_filter(norm_x, sigma=2.2)
    norm_y = gaussian_filter(norm_y, sigma=2.2)
    n_len = np.hypot(norm_x, norm_y) + 1e-8
    norm_x /= n_len
    norm_y /= n_len

    # Center X/Y around origin
    x_center -= 0.5 * (np.min(x_center) + np.max(x_center))
    y_center -= 0.5 * (np.min(y_center) + np.max(y_center))

    zs = np.linspace(0.0, float(height_mm), ny, dtype=np.float64)
    zv = np.broadcast_to(zs[:, None], (ny, nx))

    x_out = (x_center[None, :] + grid_flipped * norm_x[None, :]).ravel()
    y_out = (y_center[None, :] + grid_flipped * norm_y[None, :]).ravel()
    z_out = zv.ravel()

    x_in = np.broadcast_to(x_center[None, :], (ny, nx)).ravel()
    y_in = np.broadcast_to(y_center[None, :], (ny, nx)).ravel()
    z_in = zv.ravel()

    n_pts = nx * ny
    all_verts = np.vstack([
        np.column_stack([x_out, y_out, z_out]),
        np.column_stack([x_in, y_in, z_in]),
    ])

    r = np.arange(ny - 1, dtype=np.int64)[:, None]
    c = np.arange(nx - 1, dtype=np.int64)[None, :]
    p00 = (r * nx + c).ravel()
    p10 = p00 + 1
    p01 = p00 + nx
    p11 = p01 + 1

    f_out1 = np.column_stack([p00, p10, p11])
    f_out2 = np.column_stack([p00, p11, p01])

    b00, b10, b01, b11 = p00 + n_pts, p10 + n_pts, p01 + n_pts, p11 + n_pts
    f_in1 = np.column_stack([b00, b11, b10])
    f_in2 = np.column_stack([b00, b01, b11])

    c_idx = np.arange(nx - 1, dtype=np.int64)
    t_bot = c_idx
    b_bot = t_bot + n_pts
    w_bot1 = np.column_stack([b_bot, b_bot + 1, t_bot + 1])
    w_bot2 = np.column_stack([b_bot, t_bot + 1, t_bot])

    t_top = (ny - 1) * nx + c_idx
    b_top = t_top + n_pts
    w_top1 = np.column_stack([b_top + 1, b_top, t_top])
    w_top2 = np.column_stack([b_top + 1, t_top, t_top + 1])

    r_idx = np.arange(ny - 1, dtype=np.int64)
    t_left = r_idx * nx
    b_left = t_left + n_pts
    w_left1 = np.column_stack([b_left + nx, b_left, t_left])
    w_left2 = np.column_stack([b_left + nx, t_left, t_left + nx])

    t_right = r_idx * nx + (nx - 1)
    b_right = t_right + n_pts
    w_right1 = np.column_stack([b_right, b_right + nx, t_right + nx])
    w_right2 = np.column_stack([b_right, t_right + nx, t_right])

    all_faces = np.vstack([f_out1, f_out2, f_in1, f_in2, w_bot1, w_bot2, w_top1, w_top2, w_left1, w_left2, w_right1, w_right2])
    mesh = trimesh.Trimesh(vertices=all_verts, faces=all_faces, process=True)
    trimesh.repair.fix_normals(mesh)
    return mesh


def build_polygon_lantern_lithophane_mesh(
    t_grid: np.ndarray,
    diameter_mm: float,
    height_mm: float,
    num_sides: int = 6,
    border_width_mm: float = 4.0,
    frame_thickness_mm: float = 3.8,
    lamp_spec: Optional[Dict[str, float]] = None,
    add_hanging_loops: bool = True,
) -> trimesh.Trimesh:
    """
    Builds a Multi-Faceted Polygon Lantern (`num_sides = 5, 6, or 8`) with:
    - Flat framed lithophane facets around a regular N-gon perimeter
    - Reinforced corner pillars between each facet
    - Integrated top hanging loops/eyelets (like classic Asian/Victorian lanterns)
    - Integrated bottom raised LED lamp holder + support bars!
    """
    if lamp_spec is None:
        lamp_spec = resolve_lamp_spec("bambu_led_001")

    n_sides = max(5, min(8, int(num_sides)))
    grid = t_grid.copy()
    ny, nx = grid.shape
    by = max(1, int(round((border_width_mm / max(1.0, height_mm)) * ny)))
    bx = max(1, int(round((border_width_mm / max(1.0, math.pi * diameter_mm)) * nx)))
    if border_width_mm > 0.1:
        grid[:by, :] = frame_thickness_mm
        grid[ny - by :, :] = frame_thickness_mm
        for s_i in range(n_sides):
            seam_c = int(round((s_i / float(n_sides)) * nx)) % nx
            for dc in range(-bx, bx + 1):
                grid[:, (seam_c + dc) % nx] = frame_thickness_mm

    grid_flipped = np.flipud(grid).astype(np.float64)
    r_circum = max(25.0, float(diameter_mm) * 0.5)

    # Regular polygon vertices in XY plane
    poly_angles = [k * (2.0 * math.pi / n_sides) for k in range(n_sides + 1)]
    vx = [r_circum * math.cos(a) for a in poly_angles]
    vy = [r_circum * math.sin(a) for a in poly_angles]

    u_norm = np.linspace(0.0, float(n_sides), nx, endpoint=False, dtype=np.float64)
    x_in_col = np.zeros(nx, dtype=np.float64)
    y_in_col = np.zeros(nx, dtype=np.float64)
    nx_col = np.zeros(nx, dtype=np.float64)
    ny_col = np.zeros(nx, dtype=np.float64)

    for c_i in range(nx):
        u_val = u_norm[c_i]
        s_idx = min(n_sides - 1, int(math.floor(u_val)))
        frac = u_val - s_idx
        x_in_col[c_i] = (1.0 - frac) * vx[s_idx] + frac * vx[s_idx + 1]
        y_in_col[c_i] = (1.0 - frac) * vy[s_idx] + frac * vy[s_idx + 1]
        mid_ang = (s_idx + 0.5) * (2.0 * math.pi / n_sides)
        nx_col[c_i] = math.cos(mid_ang)
        ny_col[c_i] = math.sin(mid_ang)

    # Smooth normals slightly across polygon corners for clean mitered outer edges
    nx_col = np.roll(gaussian_filter(np.tile(nx_col, 3), sigma=1.8)[nx : 2 * nx], 0)
    ny_col = np.roll(gaussian_filter(np.tile(ny_col, 3), sigma=1.8)[nx : 2 * nx], 0)
    n_len = np.hypot(nx_col, ny_col) + 1e-8
    nx_col /= n_len
    ny_col /= n_len

    zs = np.linspace(0.0, float(height_mm), ny, dtype=np.float64)
    zv = np.broadcast_to(zs[:, None], (ny, nx)).copy()

    # Rear cable notch on bottom rim
    notch_w = lamp_spec["cable_notch_width_mm"]
    notch_h = min(lamp_spec["cable_notch_height_mm"], height_mm * 0.15)
    if notch_w > 0.5 and notch_h > 0.5:
        for c_i in range(nx):
            if y_in_col[c_i] > 0 and abs(x_in_col[c_i]) <= notch_w * 0.55:
                zv[zv[:, c_i] < notch_h, c_i] = notch_h

    x_out = (x_in_col[None, :] + grid_flipped * nx_col[None, :]).ravel()
    y_out = (y_in_col[None, :] + grid_flipped * ny_col[None, :]).ravel()
    z_out = zv.ravel()

    x_in = np.broadcast_to(x_in_col[None, :], (ny, nx)).ravel()
    y_in = np.broadcast_to(y_in_col[None, :], (ny, nx)).ravel()
    z_in = zv.ravel()

    n_pts = nx * ny
    all_verts = np.vstack([
        np.column_stack([x_out, y_out, z_out]),
        np.column_stack([x_in, y_in, z_in]),
    ])

    r = np.arange(ny - 1, dtype=np.int64)[:, None]
    c = np.arange(nx, dtype=np.int64)[None, :]
    c_next = (c + 1) % nx

    p00 = (r * nx + c).ravel()
    p10 = (r * nx + c_next).ravel()
    p01 = ((r + 1) * nx + c).ravel()
    p11 = ((r + 1) * nx + c_next).ravel()

    f_out1 = np.column_stack([p00, p10, p11])
    f_out2 = np.column_stack([p00, p11, p01])
    b00, b10, b01, b11 = p00 + n_pts, p10 + n_pts, p01 + n_pts, p11 + n_pts
    f_in1 = np.column_stack([b00, b11, b10])
    f_in2 = np.column_stack([b00, b01, b11])

    c_all = np.arange(nx, dtype=np.int64)
    c_all_next = (c_all + 1) % nx
    t_bot = c_all
    t_bot_n = c_all_next
    b_bot = t_bot + n_pts
    b_bot_n = t_bot_n + n_pts
    w_bot1 = np.column_stack([b_bot, b_bot_n, t_bot_n])
    w_bot2 = np.column_stack([b_bot, t_bot_n, t_bot])

    t_top = (ny - 1) * nx + c_all
    t_top_n = (ny - 1) * nx + c_all_next
    b_top = t_top + n_pts
    b_top_n = t_top_n + n_pts
    w_top1 = np.column_stack([b_top_n, b_top, t_top])
    w_top2 = np.column_stack([b_top_n, t_top, t_top_n])

    all_faces = np.vstack([f_out1, f_out2, f_in1, f_in2, w_bot1, w_bot2, w_top1, w_top2])
    lantern_mesh = trimesh.Trimesh(vertices=all_verts, faces=all_faces, process=True)
    trimesh.repair.fix_normals(lantern_mesh)

    parts = [lantern_mesh]

    # Top hanging loops (3 eyelets around the top rim as shown in the Polygon photo)
    if add_hanging_loops:
        r_apothem = r_circum * math.cos(math.pi / n_sides) + frame_thickness_mm * 0.5
        n_loops = 3 if n_sides % 3 == 0 else 2
        for k in range(n_loops):
            s_idx = int(round(k * (n_sides / float(n_loops)))) % n_sides
            mid_ang = (s_idx + 0.5) * (2.0 * math.pi / n_sides)
            # Build upright eyelet tab with hole
            tab_outer = sg.Point(0.0, 0.0).buffer(6.5, resolution=32)
            tab_hole = sg.Point(0.0, 2.2).buffer(2.6, resolution=24)
            tab_2d = tab_outer.difference(tab_hole)
            ext_c = np.array(tab_2d.exterior.coords[:-1], dtype=np.float64)
            if not sg.LinearRing(ext_c).is_ccw:
                ext_c = ext_c[::-1]
            polys = [ext_c.tolist()]
            for h_ring in tab_2d.interiors:
                hc = np.array(h_ring.coords[:-1], dtype=np.float64)
                if sg.LinearRing(hc).is_ccw:
                    hc = hc[::-1]
                polys.append(hc.tolist())
            cs = m3d.CrossSection(polys)
            tab_m = m3d.Manifold.extrude(cs, height=frame_thickness_mm)
            tab_tm = manifold_to_trimesh(tab_m)
            tab_tm.apply_translation([0.0, 0.0, -frame_thickness_mm * 0.5])
            # Rotate so tab stands in Z and faces outward along mid_ang
            rot_x = trimesh.transformations.rotation_matrix(math.pi * 0.5, [1.0, 0.0, 0.0])
            rot_z = trimesh.transformations.rotation_matrix(mid_ang + math.pi * 0.5, [0.0, 0.0, 1.0])
            tab_tm.apply_transform(rot_x)
            tab_tm.apply_transform(rot_z)
            tab_tm.apply_translation([
                r_apothem * math.cos(mid_ang),
                r_apothem * math.sin(mid_ang),
                float(height_mm) + 1.5,
            ])
            parts.append(tab_tm)

    # Raised Lamp Holder + Support Bars at the bottom
    r_in_min = r_circum * math.cos(math.pi / n_sides)
    if lamp_spec["puck_diameter_mm"] * 0.5 < r_in_min + 1.0:
        holder_parts = build_suspended_lamp_holder_bars(
            inner_span_x=r_in_min * 2.0,
            inner_span_y=r_in_min * 2.0,
            z_base=0.0,
            lamp_spec=lamp_spec,
        )
        parts.extend(holder_parts)

    combined = trimesh.util.concatenate(parts)
    combined.merge_vertices()
    return combined


def build_cone_lampshade_lithophane_mesh(
    t_grid: np.ndarray,
    bottom_diameter_mm: float,
    height_mm: float,
    top_ratio: float = 0.52,
    border_width_mm: float = 4.5,
    frame_thickness_mm: float = 3.8,
    lamp_spec: Optional[Dict[str, float]] = None,
) -> trimesh.Trimesh:
    """
    Builds a 100% watertight Tapered Conical Lampshade (Frustum 360°) Lithophane with:
    - Wide bottom diameter (`bottom_diameter_mm`) tapering up to `top_diameter = bottom_diameter_mm * top_ratio`
    - Thickened top and bottom collar rims
    - Integrated bottom raised LED lamp mount + 4 support bars + rear cable notch!
    """
    if lamp_spec is None:
        lamp_spec = resolve_lamp_spec("bambu_led_001")

    grid = t_grid.copy()
    ny, nx = grid.shape
    by = max(1, int(round((border_width_mm / max(1.0, height_mm)) * ny)))
    if border_width_mm > 0.1:
        grid[:by, :] = frame_thickness_mm
        grid[ny - by :, :] = frame_thickness_mm

    blend_cols = min(6, nx // 20)
    if blend_cols >= 2:
        for k in range(blend_cols):
            w = (k + 1) / float(blend_cols + 1)
            avg_col = 0.5 * (grid[:, k] + grid[:, nx - 1 - k])
            grid[:, k] = w * grid[:, k] + (1.0 - w) * avg_col
            grid[:, nx - 1 - k] = w * grid[:, nx - 1 - k] + (1.0 - w) * avg_col

    grid_flipped = np.flipud(grid).astype(np.float64)
    r_bot = max(28.0, float(bottom_diameter_mm) * 0.5)
    r_top = max(18.0, r_bot * max(0.35, min(0.85, float(top_ratio))))

    thetas = np.linspace(0.0, 2.0 * math.pi, nx, endpoint=False, dtype=np.float64)
    zs = np.linspace(0.0, float(height_mm), ny, dtype=np.float64)
    v_frac = np.linspace(0.0, 1.0, ny, dtype=np.float64)[:, None]

    r_in_profile = (1.0 - v_frac) * r_bot + v_frac * r_top
    cos_t = np.cos(thetas)[None, :]
    sin_t = np.sin(thetas)[None, :]
    zv = np.broadcast_to(zs[:, None], (ny, nx)).copy()

    # Rear cable notch at base
    notch_w = lamp_spec["cable_notch_width_mm"]
    notch_h = min(lamp_spec["cable_notch_height_mm"], height_mm * 0.15)
    if notch_w > 0.5 and notch_h > 0.5:
        for c_i in range(nx):
            x_c = r_bot * math.cos(thetas[c_i])
            y_c = r_bot * math.sin(thetas[c_i])
            if y_c > 0 and abs(x_c) <= notch_w * 0.55:
                zv[zv[:, c_i] < notch_h, c_i] = notch_h

    # Displace outward along cone surface normal
    slope = (r_bot - r_top) / max(1.0, float(height_mm))
    norm_rad = 1.0 / math.hypot(1.0, slope)
    norm_z = slope / math.hypot(1.0, slope)

    r_outer = r_in_profile + grid_flipped * norm_rad
    z_outer = zv + grid_flipped * norm_z

    x_out = (r_outer * cos_t).ravel()
    y_out = (r_outer * sin_t).ravel()
    z_out = z_outer.ravel()

    x_in = (r_in_profile * cos_t).ravel()
    y_in = (r_in_profile * sin_t).ravel()
    z_in = zv.ravel()

    n_pts = nx * ny
    all_verts = np.vstack([
        np.column_stack([x_out, y_out, z_out]),
        np.column_stack([x_in, y_in, z_in]),
    ])

    r = np.arange(ny - 1, dtype=np.int64)[:, None]
    c = np.arange(nx, dtype=np.int64)[None, :]
    c_next = (c + 1) % nx

    p00 = (r * nx + c).ravel()
    p10 = (r * nx + c_next).ravel()
    p01 = ((r + 1) * nx + c).ravel()
    p11 = ((r + 1) * nx + c_next).ravel()

    f_out1 = np.column_stack([p00, p10, p11])
    f_out2 = np.column_stack([p00, p11, p01])
    b00, b10, b01, b11 = p00 + n_pts, p10 + n_pts, p01 + n_pts, p11 + n_pts
    f_in1 = np.column_stack([b00, b11, b10])
    f_in2 = np.column_stack([b00, b01, b11])

    c_all = np.arange(nx, dtype=np.int64)
    c_all_next = (c_all + 1) % nx
    t_bot = c_all
    t_bot_n = c_all_next
    b_bot = t_bot + n_pts
    b_bot_n = t_bot_n + n_pts
    w_bot1 = np.column_stack([b_bot, b_bot_n, t_bot_n])
    w_bot2 = np.column_stack([b_bot, t_bot_n, t_bot])

    t_top = (ny - 1) * nx + c_all
    t_top_n = (ny - 1) * nx + c_all_next
    b_top = t_top + n_pts
    b_top_n = t_top_n + n_pts
    w_top1 = np.column_stack([b_top_n, b_top, t_top])
    w_top2 = np.column_stack([b_top_n, t_top, t_top_n])

    all_faces = np.vstack([f_out1, f_out2, f_in1, f_in2, w_bot1, w_bot2, w_top1, w_top2])
    cone_mesh = trimesh.Trimesh(vertices=all_verts, faces=all_faces, process=True)
    trimesh.repair.fix_normals(cone_mesh)

    parts = [cone_mesh]
    if lamp_spec["puck_diameter_mm"] * 0.5 < r_bot + 1.0:
        holder_parts = build_suspended_lamp_holder_bars(
            inner_span_x=r_bot * 2.0,
            inner_span_y=r_bot * 2.0,
            z_base=0.0,
            lamp_spec=lamp_spec,
        )
        parts.extend(holder_parts)

    combined = trimesh.util.concatenate(parts)
    combined.merge_vertices()
    return combined


def build_vase_lumina_lithophane_mesh(
    t_grid: np.ndarray,
    diameter_mm: float,
    height_mm: float,
    border_width_mm: float = 4.0,
    frame_thickness_mm: float = 3.8,
    lamp_spec: Optional[Dict[str, float]] = None,
) -> trimesh.Trimesh:
    """
    Builds a 360° Curved Amphora / Vase Lithophane ("Vase") with:
    - Classical bulbous belly, tapered waist/neck, and flared lip
    - Seamless 360° photo wrap around the vase body
    - Integrated bottom LED lamp mount + rear cable notch!
    """
    if lamp_spec is None:
        lamp_spec = resolve_lamp_spec("bambu_led_001")

    grid = t_grid.copy()
    ny, nx = grid.shape
    by = max(1, int(round((border_width_mm / max(1.0, height_mm)) * ny)))
    if border_width_mm > 0.1:
        grid[:by, :] = frame_thickness_mm
        grid[ny - by :, :] = frame_thickness_mm

    blend_cols = min(6, nx // 20)
    if blend_cols >= 2:
        for k in range(blend_cols):
            w = (k + 1) / float(blend_cols + 1)
            avg_col = 0.5 * (grid[:, k] + grid[:, nx - 1 - k])
            grid[:, k] = w * grid[:, k] + (1.0 - w) * avg_col
            grid[:, nx - 1 - k] = w * grid[:, nx - 1 - k] + (1.0 - w) * avg_col

    grid_flipped = np.flipud(grid).astype(np.float64)
    r_max = max(32.0, float(diameter_mm) * 0.5)

    # Smooth amphora / porcelain vase radial profile R(v) for v in [0..1]
    v = np.linspace(0.0, 1.0, ny, dtype=np.float64)
    # Foot at v=0 (0.64), wide belly at v=0.38 (1.00), narrow neck at v=0.82 (0.44), flared lip at v=1.0 (0.54)
    belly = np.exp(-((v - 0.36) / 0.28) ** 2)
    neck_dip = np.exp(-((v - 0.82) / 0.14) ** 2)
    lip_flare = np.exp(-((v - 1.0) / 0.09) ** 2)
    profile_norm = 0.58 + 0.44 * belly - 0.22 * neck_dip + 0.14 * lip_flare
    profile_norm = profile_norm / np.max(profile_norm)
    r_in_profile = (r_max * profile_norm)[:, None]

    # Compute dR/dz for surface normal
    dz = float(height_mm) / max(1, ny - 1)
    dr_dz = np.gradient(r_in_profile[:, 0], dz)[:, None]
    norm_rad = 1.0 / np.hypot(1.0, dr_dz)
    norm_z = -dr_dz / np.hypot(1.0, dr_dz)

    thetas = np.linspace(0.0, 2.0 * math.pi, nx, endpoint=False, dtype=np.float64)
    zs = np.linspace(0.0, float(height_mm), ny, dtype=np.float64)
    cos_t = np.cos(thetas)[None, :]
    sin_t = np.sin(thetas)[None, :]
    zv = np.broadcast_to(zs[:, None], (ny, nx)).copy()

    r_bot = float(r_in_profile[0, 0])
    notch_w = lamp_spec["cable_notch_width_mm"]
    notch_h = min(lamp_spec["cable_notch_height_mm"], height_mm * 0.12)
    if notch_w > 0.5 and notch_h > 0.5:
        for c_i in range(nx):
            x_c = r_bot * math.cos(thetas[c_i])
            y_c = r_bot * math.sin(thetas[c_i])
            if y_c > 0 and abs(x_c) <= notch_w * 0.55:
                zv[zv[:, c_i] < notch_h, c_i] = notch_h

    r_outer = r_in_profile + grid_flipped * norm_rad
    z_outer = np.clip(zv + grid_flipped * norm_z, 0.0, float(height_mm))

    x_out = (r_outer * cos_t).ravel()
    y_out = (r_outer * sin_t).ravel()
    z_out = z_outer.ravel()

    x_in = (r_in_profile * cos_t).ravel()
    y_in = (r_in_profile * sin_t).ravel()
    z_in = zv.ravel()

    n_pts = nx * ny
    all_verts = np.vstack([
        np.column_stack([x_out, y_out, z_out]),
        np.column_stack([x_in, y_in, z_in]),
    ])

    r = np.arange(ny - 1, dtype=np.int64)[:, None]
    c = np.arange(nx, dtype=np.int64)[None, :]
    c_next = (c + 1) % nx

    p00 = (r * nx + c).ravel()
    p10 = (r * nx + c_next).ravel()
    p01 = ((r + 1) * nx + c).ravel()
    p11 = ((r + 1) * nx + c_next).ravel()

    f_out1 = np.column_stack([p00, p10, p11])
    f_out2 = np.column_stack([p00, p11, p01])
    b00, b10, b01, b11 = p00 + n_pts, p10 + n_pts, p01 + n_pts, p11 + n_pts
    f_in1 = np.column_stack([b00, b11, b10])
    f_in2 = np.column_stack([b00, b01, b11])

    c_all = np.arange(nx, dtype=np.int64)
    c_all_next = (c_all + 1) % nx
    t_bot = c_all
    t_bot_n = c_all_next
    b_bot = t_bot + n_pts
    b_bot_n = t_bot_n + n_pts
    w_bot1 = np.column_stack([b_bot, b_bot_n, t_bot_n])
    w_bot2 = np.column_stack([b_bot, t_bot_n, t_bot])

    t_top = (ny - 1) * nx + c_all
    t_top_n = (ny - 1) * nx + c_all_next
    b_top = t_top + n_pts
    b_top_n = t_top_n + n_pts
    w_top1 = np.column_stack([b_top_n, b_top, t_top])
    w_top2 = np.column_stack([b_top_n, t_top, t_top_n])

    all_faces = np.vstack([f_out1, f_out2, f_in1, f_in2, w_bot1, w_bot2, w_top1, w_top2])
    vase_mesh = trimesh.Trimesh(vertices=all_verts, faces=all_faces, process=True)
    trimesh.repair.fix_normals(vase_mesh)

    parts = [vase_mesh]
    if lamp_spec["puck_diameter_mm"] * 0.5 < r_bot + 2.0:
        holder_parts = build_suspended_lamp_holder_bars(
            inner_span_x=r_bot * 2.0,
            inner_span_y=r_bot * 2.0,
            z_base=0.0,
            lamp_spec=lamp_spec,
        )
        parts.extend(holder_parts)

    combined = trimesh.util.concatenate(parts)
    combined.merge_vertices()
    return combined


def build_balloon_heart_lithophane_mesh(
    t_grid: np.ndarray,
    width_mm: float,
    frame_thickness_mm: float = 3.6,
) -> trimesh.Trimesh:
    """
    Builds a 3D Inflated Heart Cushion ("Balloon") Lithophane (`width_mm`):
    - Smooth 3D puffed heart geometry (`dome_profile = sqrt(dist_to_boundary)`) on both Front (-Y) and Back (+Y)
    - Hollow interior shell so an LED string or tea-light illuminates the entire 3D heart
    - Flat bottom pedestal base with LED insertion hole so the 3D Heart stands upright on a table!
    """
    from modules_futurs.hueforge_tiler import build_layout_polygons

    heart_tiles = build_layout_polygons("single_heart", size_mm=width_mm, aspect_ratio=1.0)
    heart_poly = heart_tiles[0][1]
    minx, miny, maxx, maxy = heart_poly.bounds
    w_span = maxx - minx
    h_span = maxy - miny

    grid_flipped = np.flipud(t_grid).astype(np.float64)
    ny, nx = grid_flipped.shape

    # Rasterize heart mask and compute smooth 3D balloon inflation dome
    from PIL import ImageDraw
    from scipy.ndimage import distance_transform_edt

    mask_img = Image.new("L", (nx, ny), 0)
    draw = ImageDraw.Draw(mask_img)
    ext_coords = np.array(heart_poly.exterior.coords, dtype=np.float64)
    px = (ext_coords[:, 0] - minx) / max(1e-5, w_span) * (nx - 1)
    py = (ext_coords[:, 1] - miny) / max(1e-5, h_span) * (ny - 1)
    pts_px = list(zip(px.tolist(), py.tolist()))
    draw.polygon(pts_px, fill=255)
    inside = np.asarray(mask_img) > 127

    dist_px = distance_transform_edt(inside).astype(np.float64)
    max_dist = max(1.0, float(np.max(dist_px)))
    u_dist = np.clip(dist_px / max_dist, 0.0, 1.0)
    # Ellipsoidal balloon puff profile: steep near edge, smooth dome across the heart
    dome_norm = np.power(u_dist, 0.48)
    dome_norm = gaussian_filter(dome_norm, sigma=2.0) * inside
    max_puff_mm = max(14.0, float(width_mm) * 0.16)
    puff_mm = dome_norm * max_puff_mm

    # Build front relief thickness (only inside heart; outside is clipped by manifold intersection)
    edge_band = inside & (dist_px <= 3.5)
    t_eff = np.where(edge_band, frame_thickness_mm, grid_flipped)

    pad = 2.0
    xs = np.linspace(minx - pad, maxx + pad, nx, dtype=np.float32)
    ys = np.linspace(miny - pad, maxy + pad, ny, dtype=np.float32)
    xv, yv = np.meshgrid(xs, ys)

    # Front surface: z_front = puff_mm + t_eff; Back surface: z_back = -puff_mm * 0.55
    z_top = (puff_mm + t_eff).astype(np.float32)
    z_bot = (-puff_mm * 0.45).astype(np.float32)

    n_pts = nx * ny
    top_verts = np.column_stack([xv.ravel(), yv.ravel(), z_top.ravel()])
    bot_verts = np.column_stack([xv.ravel(), yv.ravel(), z_bot.ravel()])
    all_verts = np.ascontiguousarray(np.vstack([top_verts, bot_verts]), dtype=np.float32)

    r = np.arange(ny - 1, dtype=np.uint32)[:, None]
    c = np.arange(nx - 1, dtype=np.uint32)[None, :]
    p00 = (r * nx + c).ravel()
    p10 = p00 + 1
    p01 = p00 + nx
    p11 = p01 + 1

    top_t1 = np.column_stack([p00, p10, p11])
    top_t2 = np.column_stack([p00, p11, p01])
    b00, b10, b01, b11 = p00 + n_pts, p10 + n_pts, p01 + n_pts, p11 + n_pts
    bot_t1 = np.column_stack([b00, b11, b10])
    bot_t2 = np.column_stack([b00, b01, b11])

    c_idx = np.arange(nx - 1, dtype=np.uint32)
    t_south = c_idx
    b_south = t_south + n_pts
    w_south1 = np.column_stack([b_south, b_south + 1, t_south + 1])
    w_south2 = np.column_stack([b_south, t_south + 1, t_south])

    t_north = (ny - 1) * nx + c_idx
    b_north = t_north + n_pts
    w_north1 = np.column_stack([b_north + 1, b_north, t_north])
    w_north2 = np.column_stack([b_north + 1, t_north, t_north + 1])

    r_idx = np.arange(ny - 1, dtype=np.uint32)
    t_west = r_idx * nx
    b_west = t_west + n_pts
    w_west1 = np.column_stack([b_west + nx, b_west, t_west])
    w_west2 = np.column_stack([b_west + nx, t_west, t_west + nx])

    t_east = r_idx * nx + (nx - 1)
    b_east = t_east + n_pts
    w_east1 = np.column_stack([b_east, b_east + nx, t_east + nx])
    w_east2 = np.column_stack([b_east, t_east + nx, t_east])

    all_faces = np.ascontiguousarray(
        np.vstack([top_t1, top_t2, bot_t1, bot_t2, w_south1, w_south2, w_north1, w_north2, w_west1, w_west2, w_east1, w_east2]),
        dtype=np.uint32,
    )
    slab_mani = m3d.Manifold(m3d.Mesh(vert_properties=all_verts, tri_verts=all_faces))

    # Clip strictly to the Heart polygon
    ext_c = np.array(heart_poly.exterior.coords[:-1], dtype=np.float64)
    if not sg.LinearRing(ext_c).is_ccw:
        ext_c = ext_c[::-1]
    cs_heart = m3d.CrossSection([ext_c.tolist()])
    clip_mani = m3d.Manifold.extrude(cs_heart, height=max_puff_mm * 3.0 + 20.0).translate([0.0, 0.0, -max_puff_mm - 5.0])
    balloon_mani = slab_mani ^ clip_mani

    mesh = manifold_to_trimesh(balloon_mani)
    # Stand upright on X-Z plane with flat pedestal base so it prints vertically
    rot = trimesh.transformations.rotation_matrix(math.pi / 2.0, [1.0, 0.0, 0.0])
    mesh.apply_transform(rot)
    min_z = float(mesh.bounds[0][2])
    mesh.apply_translation([0.0, 0.0, -min_z + 2.0])

    # Add a sleek oval pedestal stand at the bottom tip of the heart
    base_cyl = trimesh.creation.cylinder(radius=width_mm * 0.24, height=4.0, sections=48)
    base_cyl.apply_scale([1.15, 0.75, 1.0])
    base_cyl.apply_translation([0.0, 0.0, 2.0])
    combined = trimesh.util.concatenate([mesh, base_cyl])
    combined.merge_vertices()
    return combined


def extract_stencil_silhouette_mask(img: Image.Image, width_px: int, height_px: int) -> Tuple[np.ndarray, np.ndarray]:
    """
    Automatically segments the foreground subject silhouette from the background corner color
    (like the giraffe in the "Stencil" example) and returns `(inside_mask, rim_mask)`.
    """
    from scipy.ndimage import binary_closing, binary_dilation, binary_erosion, binary_fill_holes, label

    resized = img.resize((width_px, height_px), Image.Resampling.LANCZOS).convert("RGB")
    arr = np.asarray(resized, dtype=np.float32)

    # Sample border pixels to estimate background color
    b_strip = max(3, min(width_px, height_px) // 25)
    border_pixels = np.concatenate([
        arr[:b_strip, :, :].reshape(-1, 3),
        arr[-b_strip:, :, :].reshape(-1, 3),
        arr[:, :b_strip, :].reshape(-1, 3),
        arr[:, -b_strip:, :].reshape(-1, 3),
    ], axis=0)
    bg_color = np.median(border_pixels, axis=0)

    color_dist = np.linalg.norm(arr - bg_color[None, None, :], axis=-1)
    # Adaptive threshold
    thresh = max(24.0, float(np.percentile(color_dist, 30)) * 1.35)
    fg = color_dist > thresh

    # If background wasn't uniform (e.g. full photo), fall back to Otsu-like central object mask
    fg_ratio = float(np.mean(fg))
    if fg_ratio < 0.06 or fg_ratio > 0.92:
        luma = 0.2126 * arr[:, :, 0] + 0.7152 * arr[:, :, 1] + 0.0722 * arr[:, :, 2]
        med_border = float(np.median(np.concatenate([luma[0, :], luma[-1, :], luma[:, 0], luma[:, -1]])))
        fg = np.abs(luma - med_border) > 28.0

    # Morphological cleanup + hole filling + keep largest connected component(s)
    fg = binary_closing(fg, structure=np.ones((7, 7)))
    fg = binary_fill_holes(fg)
    labeled, n_comp = label(fg)
    if n_comp > 1:
        sizes = np.bincount(labeled.ravel())
        sizes[0] = 0
        max_sz = int(np.max(sizes))
        # Keep components at least 12% of the main subject
        keep_labels = np.where(sizes >= max_sz * 0.12)[0]
        fg = np.isin(labeled, keep_labels)

    # Smooth silhouette boundary
    fg_smooth = gaussian_filter(fg.astype(np.float32), sigma=2.0) > 0.42
    fg_smooth = binary_dilation(fg_smooth, iterations=2)

    if float(np.mean(fg_smooth)) < 0.05:
        # Safe fallback: rounded oval portrait silhouette
        yy, xx = np.ogrid[:height_px, :width_px]
        ny_c = (yy - height_px * 0.5) / (height_px * 0.44)
        nx_c = (xx - width_px * 0.5) / (width_px * 0.42)
        fg_smooth = (nx_c ** 2 + ny_c ** 2) <= 1.0

    eroded = binary_erosion(fg_smooth, iterations=max(2, min(width_px, height_px) // 75))
    rim_mask = fg_smooth & (~eroded)
    return fg_smooth, rim_mask


def build_stencil_cutout_lithophane_mesh(
    img: Image.Image,
    t_grid: np.ndarray,
    width_mm: float,
    height_mm: float,
    frame_thickness_mm: float = 3.6,
    stand_vertical_for_print: bool = True,
) -> trimesh.Trimesh:
    """
    Builds a Silhouette Cutout ("Stencil") Lithophane:
    - Background is completely cut away around the subject's organic silhouette
    - A protective contour rim (`frame_thickness_mm`) follows the silhouette perimeter
    - Integrated flat standing pedestal base at the bottom so the cutout stands upright!
    """
    grid_flipped = np.flipud(t_grid).astype(np.float32)
    ny, nx = grid_flipped.shape

    inside_mask, rim_mask = extract_stencil_silhouette_mask(img, width_px=nx, height_px=ny)
    inside_flipped = np.flipud(inside_mask)
    rim_flipped = np.flipud(rim_mask)

    # Apply protective contour rim
    grid_work = np.where(rim_flipped, float(frame_thickness_mm), grid_flipped)

    # Extract Shapely polygon from inside_flipped using matplotlib contour or marching squares via raster
    # Even simpler and 100% watertight: build polygons from horizontal run-length strips of inside_flipped!
    xs = np.linspace(-width_mm * 0.5, width_mm * 0.5, nx, dtype=np.float64)
    ys = np.linspace(-height_mm * 0.5, height_mm * 0.5, ny, dtype=np.float64)
    dx = float(width_mm) / max(1, nx - 1)
    dy = float(height_mm) / max(1, ny - 1)

    boxes = []
    # Downsample mask to ~140 rows for fast exact Shapely union + smoothing
    step_r = max(1, ny // 140)
    step_c = max(1, nx // 140)
    for r_i in range(0, ny, step_r):
        row_m = inside_flipped[r_i, ::step_c]
        if not np.any(row_m):
            continue
        y0 = ys[r_i] - dy * 0.6
        y1 = ys[min(ny - 1, r_i + step_r)] + dy * 0.6
        # Find contiguous True runs
        padded = np.concatenate([[False], row_m, [False]])
        starts = np.where(padded[1:] & ~padded[:-1])[0]
        ends = np.where(~padded[1:] & padded[:-1])[0]
        for s_c, e_c in zip(starts, ends):
            x0 = xs[min(nx - 1, s_c * step_c)] - dx * 0.6
            x1 = xs[min(nx - 1, min(nx - 1, (e_c - 1) * step_c))] + dx * 0.6
            boxes.append(sg.box(x0, y0, x1, y1))

    from shapely.ops import unary_union
    silhouette_poly = unary_union(boxes).buffer(dx * 1.5, resolution=16).buffer(-dx * 0.8, resolution=16).simplify(dx * 0.45)

    xv, yv = np.meshgrid(xs.astype(np.float32), ys.astype(np.float32))
    n_pts = nx * ny
    top_verts = np.column_stack([xv.ravel(), yv.ravel(), grid_work.ravel()])
    bot_verts = np.column_stack([xv.ravel(), yv.ravel(), np.zeros(n_pts, dtype=np.float32)])
    all_verts = np.ascontiguousarray(np.vstack([top_verts, bot_verts]), dtype=np.float32)

    r = np.arange(ny - 1, dtype=np.uint32)[:, None]
    c = np.arange(nx - 1, dtype=np.uint32)[None, :]
    p00 = (r * nx + c).ravel()
    p10 = p00 + 1
    p01 = p00 + nx
    p11 = p01 + 1

    top_t1 = np.column_stack([p00, p10, p11])
    top_t2 = np.column_stack([p00, p11, p01])
    b00, b10, b01, b11 = p00 + n_pts, p10 + n_pts, p01 + n_pts, p11 + n_pts
    bot_t1 = np.column_stack([b00, b11, b10])
    bot_t2 = np.column_stack([b00, b01, b11])

    c_idx = np.arange(nx - 1, dtype=np.uint32)
    t_south = c_idx
    b_south = t_south + n_pts
    w_south1 = np.column_stack([b_south, b_south + 1, t_south + 1])
    w_south2 = np.column_stack([b_south, t_south + 1, t_south])

    t_north = (ny - 1) * nx + c_idx
    b_north = t_north + n_pts
    w_north1 = np.column_stack([b_north + 1, b_north, t_north])
    w_north2 = np.column_stack([b_north + 1, t_north, t_north + 1])

    r_idx = np.arange(ny - 1, dtype=np.uint32)
    t_west = r_idx * nx
    b_west = t_west + n_pts
    w_west1 = np.column_stack([b_west + nx, b_west, t_west])
    w_west2 = np.column_stack([b_west + nx, t_west, t_west + nx])

    t_east = r_idx * nx + (nx - 1)
    b_east = t_east + n_pts
    w_east1 = np.column_stack([b_east, b_east + nx, t_east + nx])
    w_east2 = np.column_stack([b_east, t_east + nx, t_east])

    all_faces = np.ascontiguousarray(
        np.vstack([top_t1, top_t2, bot_t1, bot_t2, w_south1, w_south2, w_north1, w_north2, w_west1, w_west2, w_east1, w_east2]),
        dtype=np.uint32,
    )
    slab_mani = m3d.Manifold(m3d.Mesh(vert_properties=all_verts, tri_verts=all_faces))

    # Build CrossSection from silhouette_poly (Polygon or MultiPolygon)
    geoms = [silhouette_poly] if isinstance(silhouette_poly, sg.Polygon) else list( getattr(silhouette_poly, "geoms", []))
    polys_cs = []
    for g in geoms:
        if g.area < 8.0:
            continue
        ext_c = np.array(g.exterior.coords[:-1], dtype=np.float64)
        if not sg.LinearRing(ext_c).is_ccw:
            ext_c = ext_c[::-1]
        polys_cs.append(ext_c.tolist())
        for h_ring in g.interiors:
            if sg.Polygon(h_ring).area < 6.0:
                continue
            hc = np.array(h_ring.coords[:-1], dtype=np.float64)
            if sg.LinearRing(hc).is_ccw:
                hc = hc[::-1]
            polys_cs.append(hc.tolist())

    if polys_cs:
        cs = m3d.CrossSection(polys_cs)
        clip_m = m3d.Manifold.extrude(cs, height=frame_thickness_mm + 10.0).translate([0.0, 0.0, -2.0])
        stencil_mani = slab_mani ^ clip_m
        mesh = manifold_to_trimesh(stencil_mani)
    else:
        mesh = manifold_to_trimesh(slab_mani)

    if stand_vertical_for_print:
        rot = trimesh.transformations.rotation_matrix(math.pi / 2.0, [1.0, 0.0, 0.0])
        mesh.apply_transform(rot)
        min_z = float(mesh.bounds[0][2])
        mesh.apply_translation([0.0, 0.0, -min_z + 2.5])
        # Add a sleek standing base bar connecting the bottom of the silhouette (e.g. giraffe legs!)
        b_min, b_max = mesh.bounds
        span_x = max(35.0, float(b_max[0] - b_min[0]) * 0.82)
        cx = 0.5 * float(b_min[0] + b_max[0])
        stand_bar = trimesh.creation.box(extents=[span_x, 18.0, 3.2])
        stand_bar.apply_translation([cx, 0.0, 1.6])
        mesh = trimesh.util.concatenate([mesh, stand_bar])
        mesh.merge_vertices()

    return mesh


