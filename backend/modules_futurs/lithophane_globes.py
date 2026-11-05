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

import numpy as np
import trimesh
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LAMP_STANDARDS_FILE = DATA_DIR / "lamp_standards.json"

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
    width: int = 720,
    height: int = 360,
) -> Image.Image:
    """
    Generates a detailed equirectangular grayscale image (0..255) for:
    - `planet_moon`: Lunar Maria (dark basalt plains) + multi-scale impact craters with bright rays & rims
    - `planet_earth`: Realistic continents, mountain ranges, oceans & polar caps
    - `planet_mars`: Tharsis bulge, Olympus Mons, Valles Marineris canyon & southern cratered highlands
    - `planet_jupiter`: Zonal turbulent cloud bands, festoons & the Great Red Spot
    - `planet_saturn`: Banded gas giant with equatorial storm hex & sci-fi orbital ring line
    """
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
    Builds one of the 4 interchangeable Lamp Stands (Socles) for the Lithophane Globe:
    - `ring_bambu`: Socle Anneau Minimaliste (Standard Bambu LED)
    - `tripod_modern`: Socle Trépied Design (3 Pieds Courbés + Berceau Lampe Central)
    - `pedestal_fluted`: Socle Piédestal Architectural Cannelé
    - `crown_gothic`: Socle Couronne / 4 Griffes Royal
    All stands include:
    - Raised LED lamp puck/socket recess (`puck_diameter_mm`, `recess_depth_mm`, `elevation_mm`)
    - Inner support ledge (`inner_ledge_diameter_mm`)
    - Rear cable exit notch (`cable_notch_width_mm` x `cable_notch_height_mm`)
    - Upper seating groove matched to the Globe's bottom collar (`open_r_out_mm` + 0.45mm clearance).
    """
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

