"""
Module 2B — Générateur de Lithophanies & Caissons Lumineux (Lightbox LED) V2
============================================================================
Architecture géométrique complète :
1. **7 Architectures 3D** :
   - `flat_plate` : Lithophanie Plate (Classique + **toutes les formes géométriques & grilles Multi-Tuiles de HueForge** :
     Hexagone, Rond, Carré, Triangle, Losange, Cœur, Étoile 5 branches, Blason, Grille L×H sur mesure, Ruche 7 Hexagones, etc.).
   - `curved_arc` : Lithophanie Courbée Autoportante (Arc 60° à 160° + Socle).
   - `half_cylinder` : Demi-Cylindre Applique / Veilleuse 180°.
   - `cylinder_lamp` : Abat-jour Cylindrique 360° **Auto-Adaptatif au ratio de l'image (1 à 4 photos)** avec **support lampe standard surélevé (Bambu Lab LED Kit 001 Ø59.5mm, Galet USB Ø38mm, E14, E27 ou Sur-mesure) + encoche câble**.
   - `sphere_globe` : **Boule / Globe Lithophanie 360°** avec ouverture basse + collerette d'assise, compatible **Photo perso (1 à 4 images)**, **Lune & Planètes pré-définies (Lune, Terre, Mars, Jupiter, Sci-Fi)** ou **Import STL externe**, et **4 Socles au choix** (`ring_bambu`, `tripod_modern`, `pedestal_fluted`, `crown_gothic`).
   - `framed_lightbox` : Caisson Lightbox Complet (Façade Lithophanie + Boîtier avec **support lampe surélevé tenu par 4 barres** + encoche câble + **Vue 3D Assemblée Complète**).
   - `cube_lightbox` : **Cube Lightbox 4 Faces (Multi-Images : 1 à 4 photos différentes par face)** + Structure Cube avec **support lampe surélevé tenu par barres** + **Vue 3D Assemblée Complète des 4 faces montées**.
2. **Simulation Rétro-Éclairage LED RGB Complète** :
   - 11 teintes de lampes LED (Blancs Chaud/Neutre/Bougie + Rouge, Orange, Or, Émeraude, Cyan, Bleu Royal, Violet, Rose Magenta) + **Couleur LED RGB Sur-Mesure (`custom_color_hex`)**.
"""
from __future__ import annotations

import base64
import io
import math
import uuid
import zipfile
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, Literal

import manifold3d as m3d
import numpy as np
import shapely.geometry as sg
import trimesh
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import Response
from PIL import Image, ImageOps
from pydantic import BaseModel, Field
from scipy.ndimage import gaussian_filter

from core.mesh_repair import compute_mesh_stats, export_mesh_stl_bytes, manifold_to_trimesh, load_and_repair_stl
from modules_futurs.hueforge_tiler import (
    build_layout_polygons,
    compute_max_tile_extents_mm,
    _rasterize_layout_masks,
    _polygon_to_prism_manifold,
    _create_back_bowtie_socket_and_clip,
    find_shared_edges_midpoints,
)
from modules_futurs.lithophane_globes import (
    load_lamp_standards,
    save_custom_lamp_standard,
    delete_custom_lamp_standard,
    resolve_lamp_spec,
    generate_planetary_luminance_map,
    build_sphere_globe_lithophane_mesh,
    build_globe_lamp_stand_mesh,
    build_suspended_lamp_holder_bars,
    _build_annular_ring_with_cable_notch,
)

router = APIRouter(prefix="/api/lithophane", tags=["Module 2B - Lithophanies & Lightbox LED"])


ShapeMode = Literal[
    "flat_plate",
    "curved_arc",
    "half_cylinder",
    "cylinder_lamp",
    "sphere_globe",
    "framed_lightbox",
    "cube_lightbox",
]

LedTintMode = Literal[
    "warm_3000k",
    "neutral_5500k",
    "candle_2200k",
    "cyan_cyber",
    "red_crimson",
    "orange_sunset",
    "gold_amber",
    "emerald_green",
    "royal_blue",
    "violet_purple",
    "magenta_pink",
    "custom_rgb",
    "plastic_off",
]

GlobeSourceMode = Literal[
    "custom_photo",
    "planet_moon",
    "planet_earth",
    "planet_mars",
    "planet_jupiter",
    "planet_saturn",
    "external_stl",
]

GlobeStandStyle = Literal[
    "ring_bambu",
    "tripod_modern",
    "pedestal_fluted",
    "crown_gothic",
]


@dataclass
class LithophanePart:
    part_index: int
    filename: str
    label: str
    extents_mm: Tuple[float, float, float]
    faces_count: int
    stl_bytes: bytes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "part_index": self.part_index,
            "filename": self.filename,
            "label": self.label,
            "extents_mm": list(self.extents_mm),
            "faces_count": self.faces_count,
        }


@dataclass
class LithophaneSessionState:
    session_id: str
    filename: str
    original_image: Image.Image
    aspect_ratio: float
    extra_images: Dict[int, Tuple[str, Image.Image]] = field(default_factory=dict)  # slots 1, 2, 3
    external_globe_stl_bytes: Optional[bytes] = None
    external_globe_filename: Optional[str] = None
    last_assembly_stl_bytes: Optional[bytes] = None
    last_preview_stl_bytes: Optional[bytes] = None
    last_parts_stl_bytes: Dict[int, bytes] = field(default_factory=dict)
    last_zip_bytes: Optional[bytes] = None
    last_parts_meta: List[Dict[str, Any]] = field(default_factory=list)
    last_mesh_stats: Optional[Dict[str, Any]] = None


LITHO_SESSIONS: Dict[str, LithophaneSessionState] = {}


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class LithoPreviewRequest(BaseModel):
    shape_mode: ShapeMode = "flat_plate"
    width_mm: float = Field(default=140.0, ge=40.0, le=285.0)
    height_mm: float = Field(default=0.0, ge=0.0, le=285.0, description="0 = auto from aspect ratio")
    min_thickness_mm: float = Field(default=0.8, ge=0.4, le=2.4)
    max_thickness_mm: float = Field(default=3.2, ge=1.6, le=6.0)
    border_width_mm: float = Field(default=4.0, ge=0.0, le=15.0)
    border_extra_mm: float = Field(default=0.8, ge=0.0, le=4.0)

    # Flat Plate Geometric Shapes & Multi-Tile Layouts (like HueForge)
    flat_layout_mode: str = Field(default="single_original")
    grid_cols: int = Field(default=2, ge=1, le=10)
    grid_rows: int = Field(default=2, ge=1, le=10)

    # Optical & Image Controls
    negative_invert: bool = False
    flip_horizontal: bool = False
    contrast: float = Field(default=1.15, ge=0.4, le=2.5)
    gamma: float = Field(default=1.0, ge=0.4, le=2.5)
    detail_boost: float = Field(default=1.2, ge=0.0, le=3.5)
    smoothing_sigma: float = Field(default=0.45, ge=0.0, le=2.5)
    td_mm: float = Field(default=2.8, ge=0.8, le=6.0, description="Filament Transmission Distance (mm)")
    led_tint: LedTintMode = "warm_3000k"
    custom_led_hex: str = Field(default="#ff9d00", description="Custom RGB LED hex color")

    # Shape-specific parameters
    curve_angle_deg: float = Field(default=90.0, ge=30.0, le=180.0)
    cylinder_diameter_mm: float = Field(default=90.0, ge=40.0, le=240.0)
    auto_adapt_cylinder: bool = True
    lightbox_depth_mm: float = Field(default=42.0, ge=25.0, le=120.0)

    # Standard & Custom LED Lamp Mount Parameters
    lamp_standard_id: str = Field(default="bambu_led_001")
    led_socket_diameter_mm: float = Field(default=60.0, ge=12.0, le=120.0)
    lamp_elevation_mm: float = Field(default=8.0, ge=2.0, le=35.0)
    lamp_recess_depth_mm: float = Field(default=9.0, ge=2.0, le=25.0)
    cable_notch_width_mm: float = Field(default=8.5, ge=0.0, le=25.0)
    cable_notch_height_mm: float = Field(default=6.5, ge=0.0, le=20.0)

    # Sphere / Globe Lithophane Parameters
    globe_source_mode: GlobeSourceMode = "custom_photo"
    globe_stand_style: GlobeStandStyle = "ring_bambu"
    sphere_diameter_mm: float = Field(default=140.0, ge=60.0, le=250.0)

    add_hanging_ring: bool = False
    add_stand_feet: bool = False
    stand_vertical_for_print: bool = True
    grid_resolution: int = Field(default=280, ge=100, le=520)


class CustomLampStandardRequest(BaseModel):
    id: Optional[str] = None
    name: str
    puck_diameter_mm: float = Field(default=60.0, ge=10.0, le=160.0)
    inner_ledge_diameter_mm: float = Field(default=54.0, ge=8.0, le=155.0)
    recess_depth_mm: float = Field(default=9.0, ge=2.0, le=35.0)
    elevation_mm: float = Field(default=8.0, ge=2.0, le=45.0)
    cable_notch_width_mm: float = Field(default=8.5, ge=0.0, le=30.0)
    cable_notch_height_mm: float = Field(default=6.5, ge=0.0, le=25.0)
    description: Optional[str] = "Standard personnalisé encodé par l'utilisateur."


# ---------------------------------------------------------------------------
# 1. Image Processing, Multi-Image Stitching & Optical Simulation
# ---------------------------------------------------------------------------

def _get_litho_session(session_id: str) -> LithophaneSessionState:
    if session_id not in LITHO_SESSIONS:
        raise HTTPException(status_code=404, detail=f"Session Lithophanie '{session_id}' introuvable ou expirée.")
    return LITHO_SESSIONS[session_id]


def _hex_to_rgb_norm(hex_str: str) -> Tuple[float, float, float]:
    h = (hex_str or "#ffaa44").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return (1.0, 0.85, 0.55)
    try:
        r = int(h[0:2], 16) / 255.0
        g = int(h[2:4], 16) / 255.0
        b = int(h[4:6], 16) / 255.0
        return (r, g, b)
    except Exception:
        return (1.0, 0.85, 0.55)


def _build_stitched_panorama(state: LithophaneSessionState) -> Image.Image:
    """
    If extra images (slots 1, 2, 3) are uploaded, stitches all active images horizontally
    with the same height to wrap around a Cylinder or Sphere/Globe!
    """
    imgs = [state.original_image]
    for slot in sorted(state.extra_images.keys()):
        imgs.append(state.extra_images[slot][1])
    if len(imgs) == 1:
        return imgs[0]

    target_h = 600
    resized_list = []
    for im in imgs:
        asp = im.width / max(1.0, float(im.height))
        w = max(120, int(round(target_h * asp)))
        resized_list.append(im.resize((w, target_h), Image.Resampling.LANCZOS))

    total_w = sum(im.width for im in resized_list)
    pano = Image.new("RGB", (total_w, target_h))
    x_off = 0
    for im in resized_list:
        pano.paste(im, (x_off, 0))
        x_off += im.width
    return pano


def _get_source_image_for_request(state: LithophaneSessionState, req: LithoPreviewRequest) -> Image.Image:
    """Selects either planetary map, stitched multi-image panorama, or single image."""
    if req.shape_mode == "sphere_globe" and req.globe_source_mode in (
        "planet_moon",
        "planet_earth",
        "planet_mars",
        "planet_jupiter",
        "planet_saturn",
    ):
        return generate_planetary_luminance_map(req.globe_source_mode, width=720, height=360)

    if req.shape_mode in ("cylinder_lamp", "sphere_globe") and len(state.extra_images) > 0:
        return _build_stitched_panorama(state)

    return state.original_image


def _resolve_dimensions_mm(state: LithophaneSessionState, req: LithoPreviewRequest) -> Tuple[float, float]:
    """Computes effective (width_mm, height_mm) according to shape_mode, multi-image aspect, and auto_adapt_cylinder."""
    src_img = _get_source_image_for_request(state, req)
    eff_aspect = float(src_img.width) / max(1.0, float(src_img.height))

    w = float(req.width_mm)
    if req.shape_mode == "cube_lightbox":
        return (w, w)

    if req.shape_mode == "sphere_globe":
        d = float(req.sphere_diameter_mm)
        return (round(math.pi * d, 1), round(d, 1))

    if req.shape_mode == "cylinder_lamp":
        d = float(req.cylinder_diameter_mm)
        circumf = math.pi * d
        if req.auto_adapt_cylinder:
            # Automatically adapt cylinder height to match exact image/panorama aspect ratio around 360°!
            h_auto = circumf / max(0.25, eff_aspect)
            h_clamped = max(45.0, min(255.0, h_auto))
            return (round(circumf, 1), round(h_clamped, 1))
        h = float(req.height_mm) if req.height_mm > 10.0 else (w / max(0.15, eff_aspect))
        h = max(35.0, min(285.0, h))
        return (round(circumf, 1), round(h, 1))

    h = float(req.height_mm) if req.height_mm > 10.0 else (w / max(0.15, eff_aspect))
    h = max(35.0, min(285.0, h))
    return (round(w, 1), round(h, 1))


def compute_lithophane_thickness_grid(
    img: Image.Image,
    nx: int,
    ny: int,
    min_thickness_mm: float = 0.8,
    max_thickness_mm: float = 3.2,
    negative_invert: bool = False,
    flip_horizontal: bool = False,
    contrast: float = 1.15,
    gamma: float = 1.0,
    detail_boost: float = 1.2,
    smoothing_sigma: float = 0.45,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Resamples `img` to `(ny, nx)`, computes detail-enhanced luminance `L in [0..1]`,
    and maps to physical wall thickness `T(x, y) in [min_thickness_mm .. max_thickness_mm]`.
    """
    work_img = ImageOps.mirror(img) if flip_horizontal else img
    resized = work_img.resize((nx, ny), Image.Resampling.LANCZOS)
    arr = np.asarray(resized, dtype=np.float32)

    luma = (0.2126 * arr[:, :, 0] + 0.7152 * arr[:, :, 1] + 0.0722 * arr[:, :, 2]) / 255.0

    if abs(contrast - 1.0) > 1e-3:
        luma = np.clip((luma - 0.5) * float(contrast) + 0.5, 0.0, 1.0)

    if abs(gamma - 1.0) > 1e-3:
        luma = np.power(np.clip(luma, 1e-5, 1.0), float(gamma))

    if detail_boost > 0.01:
        blurred = gaussian_filter(luma, sigma=1.6)
        high_freq = luma - blurred
        luma = np.clip(luma + float(detail_boost) * 0.45 * high_freq, 0.0, 1.0)

    if smoothing_sigma > 0.05:
        luma = gaussian_filter(luma, sigma=float(smoothing_sigma))
        luma = np.clip(luma, 0.0, 1.0)

    norm_depth = luma if negative_invert else (1.0 - luma)
    t_grid = float(min_thickness_mm) + norm_depth * float(max_thickness_mm - min_thickness_mm)
    return t_grid.astype(np.float32), luma.astype(np.float32)


def simulate_backlight_rgb(
    t_grid: np.ndarray,
    min_thickness_mm: float,
    max_thickness_mm: float,
    td_mm: float = 2.8,
    led_tint: LedTintMode = "warm_3000k",
    custom_led_hex: str = "#ff9d00",
    inside_mask: Optional[np.ndarray] = None,
    rim_mask: Optional[np.ndarray] = None,
) -> str:
    """
    Simulates transmitted light intensity `I(x, y)` through thickness `t_grid(x, y)`
    using Beer-Lambert optical attenuation + surface relief shading when `plastic_off`.
    Supports all 11 LED color presets + `custom_rgb` (`custom_led_hex`) + geometric shape cutout!
    """
    span = max(0.2, float(max_thickness_mm - min_thickness_mm))
    norm_t = np.clip((t_grid - min_thickness_mm) / span, 0.0, 1.0)

    if led_tint == "plastic_off":
        gy, gx = np.gradient(norm_t)
        shade = np.clip(0.84 + 0.95 * (-gx - gy), 0.52, 0.98)
        base_white = np.stack([shade * 238.0, shade * 241.0, shade * 246.0], axis=-1)
        out = base_white
    else:
        atten_coeff = 2.65 * (2.6 / max(0.6, float(td_mm)))
        trans = np.exp(-atten_coeff * norm_t)
        trans = (trans - math.exp(-atten_coeff)) / max(1e-5, 1.0 - math.exp(-atten_coeff))
        trans = np.clip(trans, 0.03, 1.0)

        tints = {
            "warm_3000k": ((255.0, 244.0, 214.0), (24.0, 15.0, 9.0)),
            "neutral_5500k": ((252.0, 254.0, 255.0), (16.0, 20.0, 28.0)),
            "candle_2200k": ((255.0, 198.0, 115.0), (32.0, 12.0, 5.0)),
            "cyan_cyber": ((185.0, 250.0, 255.0), (8.0, 22.0, 36.0)),
            "red_crimson": ((255.0, 72.0, 72.0), (36.0, 5.0, 5.0)),
            "orange_sunset": ((255.0, 148.0, 50.0), (36.0, 12.0, 3.0)),
            "gold_amber": ((255.0, 225.0, 72.0), (32.0, 22.0, 5.0)),
            "emerald_green": ((90.0, 255.0, 140.0), (5.0, 28.0, 10.0)),
            "royal_blue": ((95.0, 165.0, 255.0), (5.0, 14.0, 38.0)),
            "violet_purple": ((198.0, 108.0, 255.0), (20.0, 5.0, 36.0)),
            "magenta_pink": ((255.0, 105.0, 210.0), (34.0, 5.0, 24.0)),
        }
        if led_tint == "custom_rgb":
            cr, cg, cb = _hex_to_rgb_norm(custom_led_hex)
            bright_rgb = np.array([
                min(255.0, cr * 255.0 * 1.08 + 25.0),
                min(255.0, cg * 255.0 * 1.08 + 25.0),
                min(255.0, cb * 255.0 * 1.08 + 25.0),
            ], dtype=np.float32)
            dark_rgb = np.array([cr * 28.0, cg * 28.0, cb * 28.0], dtype=np.float32)
        else:
            bright_t, dark_t = tints.get(led_tint, tints["warm_3000k"])
            bright_rgb = np.array(bright_t, dtype=np.float32)
            dark_rgb = np.array(dark_t, dtype=np.float32)

        t3 = trans[:, :, None]
        out = dark_rgb[None, None, :] + t3 * (bright_rgb[None, None, :] - dark_rgb[None, None, :])

    if rim_mask is not None and np.any(rim_mask):
        # Opaque border rim blocks more light (renders as dark frame around the shape)
        out[rim_mask] = out[rim_mask] * 0.35

    if inside_mask is not None:
        bg_studio = np.array([7.0, 10.0, 16.0], dtype=np.float32)
        glow = gaussian_filter(inside_mask.astype(np.float32), sigma=4.0)[:, :, None]
        bg_with_glow = bg_studio * (1.0 - 0.35 * glow) + np.array([0.0, 180.0, 220.0], dtype=np.float32) * (0.14 * glow)
        out = np.where(inside_mask[:, :, None], out, bg_with_glow)

    out_u8 = np.clip(out, 0, 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(out_u8).save(buf, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"


# ---------------------------------------------------------------------------
# 2. 3D Watertight Lithophane Mesh Generators
# ---------------------------------------------------------------------------

def _apply_rectangular_border_frame_to_grid(
    t_grid: np.ndarray,
    width_mm: float,
    height_mm: float,
    border_width_mm: float,
    frame_thickness_mm: float,
) -> np.ndarray:
    """Applies a flat thickened light-blocking frame around the 4 outer edges of `t_grid`."""
    if border_width_mm <= 0.1:
        return t_grid
    ny, nx = t_grid.shape
    bx = max(1, int(round((border_width_mm / max(1.0, width_mm)) * nx)))
    by = max(1, int(round((border_width_mm / max(1.0, height_mm)) * ny)))
    out = t_grid.copy()
    out[:by, :] = frame_thickness_mm
    out[ny - by :, :] = frame_thickness_mm
    out[:, :bx] = frame_thickness_mm
    out[:, nx - bx :] = frame_thickness_mm
    return out


def build_flat_lithophane_mesh(
    t_grid: np.ndarray,
    width_mm: float,
    height_mm: float,
    border_width_mm: float = 4.0,
    frame_thickness_mm: float = 4.0,
    add_hanging_ring: bool = False,
    add_stand_feet: bool = False,
    stand_vertical_for_print: bool = False,
) -> trimesh.Trimesh:
    """Builds a 100% watertight rectangular Flat Lithophane mesh."""
    grid = _apply_rectangular_border_frame_to_grid(t_grid, width_mm, height_mm, border_width_mm, frame_thickness_mm)
    grid_flipped = np.flipud(grid)
    ny, nx = grid_flipped.shape

    xs = np.linspace(-width_mm / 2.0, width_mm / 2.0, nx, dtype=np.float32)
    ys = np.linspace(-height_mm / 2.0, height_mm / 2.0, ny, dtype=np.float32)
    xv, yv = np.meshgrid(xs, ys)

    n_pts = nx * ny
    top_verts = np.column_stack([xv.ravel(), yv.ravel(), grid_flipped.ravel()])
    bot_verts = np.column_stack([xv.ravel(), yv.ravel(), np.zeros(n_pts, dtype=np.float32)])
    all_verts = np.ascontiguousarray(np.vstack([top_verts, bot_verts]), dtype=np.float64)

    r = np.arange(ny - 1, dtype=np.int64)[:, None]
    c = np.arange(nx - 1, dtype=np.int64)[None, :]
    p00 = (r * nx + c).ravel()
    p10 = p00 + 1
    p01 = p00 + nx
    p11 = p01 + 1

    top_t1 = np.column_stack([p00, p10, p11])
    top_t2 = np.column_stack([p00, p11, p01])

    b00 = p00 + n_pts
    b10 = p10 + n_pts
    b01 = p01 + n_pts
    b11 = p11 + n_pts
    bot_t1 = np.column_stack([b00, b11, b10])
    bot_t2 = np.column_stack([b00, b01, b11])

    c_idx = np.arange(nx - 1, dtype=np.int64)
    t_south = c_idx
    b_south = t_south + n_pts
    w_south1 = np.column_stack([b_south, b_south + 1, t_south + 1])
    w_south2 = np.column_stack([b_south, t_south + 1, t_south])

    t_north = (ny - 1) * nx + c_idx
    b_north = t_north + n_pts
    w_north1 = np.column_stack([b_north + 1, b_north, t_north])
    w_north2 = np.column_stack([b_north + 1, t_north, t_north + 1])

    r_idx = np.arange(ny - 1, dtype=np.int64)
    t_west = r_idx * nx
    b_west = t_west + n_pts
    w_west1 = np.column_stack([b_west + nx, b_west, t_west])
    w_west2 = np.column_stack([b_west + nx, t_west, t_west + nx])

    t_east = r_idx * nx + (nx - 1)
    b_east = t_east + n_pts
    w_east1 = np.column_stack([b_east, b_east + nx, t_east + nx])
    w_east2 = np.column_stack([b_east, t_east + nx, t_east])

    all_faces = np.vstack([
        top_t1, top_t2,
        bot_t1, bot_t2,
        w_south1, w_south2,
        w_north1, w_north2,
        w_west1, w_west2,
        w_east1, w_east2,
    ])
    plate_mesh = trimesh.Trimesh(vertices=all_verts, faces=all_faces, process=True)

    extras: List[trimesh.Trimesh] = [plate_mesh]

    if add_hanging_ring:
        outer_r = 7.5
        inner_r = 4.0
        ring_2d = sg.Point(0.0, height_mm / 2.0 + outer_r * 0.45).buffer(outer_r, resolution=48).difference(
            sg.Point(0.0, height_mm / 2.0 + outer_r * 0.45).buffer(inner_r, resolution=48)
        )
        ext_coords = np.array(ring_2d.exterior.coords[:-1], dtype=np.float64)
        if not sg.LinearRing(ext_coords).is_ccw:
            ext_coords = ext_coords[::-1]
        polys = [ext_coords.tolist()]
        for hole in ring_2d.interiors:
            hc = np.array(hole.coords[:-1], dtype=np.float64)
            if sg.LinearRing(hc).is_ccw:
                hc = hc[::-1]
            polys.append(hc.tolist())
        cs = m3d.CrossSection(polys)
        ring_mani = m3d.Manifold.extrude(cs, height=frame_thickness_mm)
        extras.append(manifold_to_trimesh(ring_mani))

    if add_stand_feet:
        foot_w = 10.0
        foot_depth = 26.0
        foot_h = max(3.6, frame_thickness_mm)
        for sign_x in (-1.0, 1.0):
            fx = sign_x * (width_mm * 0.34)
            fy = -height_mm / 2.0 + 3.0
            foot_box = trimesh.creation.box(extents=[foot_w, 6.0, foot_depth])
            foot_box.apply_translation([fx, fy, foot_depth / 2.0 - foot_h / 2.0])
            extras.append(foot_box)

    combined = trimesh.util.concatenate(extras) if len(extras) > 1 else plate_mesh

    if stand_vertical_for_print:
        rot = trimesh.transformations.rotation_matrix(math.pi / 2.0, [1.0, 0.0, 0.0])
        combined.apply_transform(rot)
        min_z = float(combined.bounds[0][2])
        combined.apply_translation([0.0, 0.0, -min_z])

    return combined


def build_shaped_or_multitile_flat_lithophanes(
    t_grid: np.ndarray,
    flat_layout_mode: str,
    width_mm: float,
    aspect_ratio: float,
    grid_cols: int,
    grid_rows: int,
    border_width_mm: float,
    frame_thickness_mm: float,
    add_hanging_ring: bool = False,
) -> Tuple[List[LithophanePart], trimesh.Trimesh]:
    """
    Builds single-shape (Heart, Star-5, Hexagon, Circle, Triangle, Diamond, Shield, etc.)
    or Multi-Tile (Grid L×H, 2×2 Squares, 7 Hexagons, 4 Triangles, 6 Triangles) flat lithophanes
    with an opaque light-blocking border rim around each tile + back bowtie connectors for multi-tile!
    Returns `(parts_list, combined_assembly_mesh)`.
    """
    tiles = build_layout_polygons(
        flat_layout_mode,
        size_mm=width_mm,
        aspect_ratio=aspect_ratio,
        grid_cols=grid_cols,
        grid_rows=grid_rows,
    )
    all_union = sg.MultiPolygon([p for _, p in tiles])
    minx, miny, maxx, maxy = all_union.bounds
    pad = 1.5
    b_minx, b_miny, b_maxx, b_maxy = minx - pad, miny - pad, maxx + pad, maxy + pad

    grid_flipped = np.flipud(t_grid)
    ny, nx = grid_flipped.shape
    xs = np.linspace(b_minx, b_maxx, nx, dtype=np.float32)
    ys = np.linspace(b_miny, b_maxy, ny, dtype=np.float32)
    xv, yv = np.meshgrid(xs, ys)

    n_pts = nx * ny
    top_verts = np.column_stack([xv.ravel(), yv.ravel(), grid_flipped.ravel()])
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
    hf_mani = m3d.Manifold(m3d.Mesh(vert_properties=all_verts, tri_verts=all_faces))

    shared_midpoints = find_shared_edges_midpoints(tiles)
    female_socket_mani, male_clip_mesh = _create_back_bowtie_socket_and_clip(clearance_mm=0.15, socket_depth_mm=0.55)

    parts_out: List[LithophanePart] = []
    assembly_meshes: List[trimesh.Trimesh] = []

    for idx, (raw_fname, poly) in enumerate(tiles):
        fname = raw_fname.replace("HueForge_", "Lithophane_")
        clip_prism = _polygon_to_prism_manifold(poly, height=frame_thickness_mm + 10.0, z_offset=-1.0)
        tile_mani = hf_mani ^ clip_prism

        # Add light-blocking border rim around the tile perimeter
        if border_width_mm > 0.2:
            inner_poly = poly.buffer(-float(border_width_mm), join_style=2)
            if not inner_poly.is_empty and isinstance(inner_poly, sg.Polygon) and inner_poly.area > 10.0:
                rim_poly = sg.Polygon(poly.exterior.coords, [inner_poly.exterior.coords])
                rim_mani = _polygon_to_prism_manifold(rim_poly, height=frame_thickness_mm, z_offset=0.0)
                tile_mani = tile_mani + rim_mani

        # Optional hanging ring on single tile
        if len(tiles) == 1 and add_hanging_ring:
            _, _, _, p_maxy = poly.bounds
            outer_r, inner_r = 7.5, 4.0
            ring_2d = sg.Point(0.0, p_maxy + outer_r * 0.35).buffer(outer_r, resolution=48).difference(
                sg.Point(0.0, p_maxy + outer_r * 0.35).buffer(inner_r, resolution=48)
            )
            ring_mani = _polygon_to_prism_manifold(ring_2d, height=frame_thickness_mm, z_offset=0.0)
            tile_mani = tile_mani + ring_mani

        # Subtract bowtie sockets on shared edges for multi-tile
        if len(shared_midpoints) > 0:
            poly_buf = poly.buffer(2.0)
            for mx, my, ang_deg in shared_midpoints:
                if poly_buf.contains(sg.Point(mx, my)):
                    sock = female_socket_mani.rotate([0.0, 0.0, ang_deg + 90.0]).translate([mx, my, 0.0])
                    tile_mani = tile_mani - sock

        t_mesh_world = manifold_to_trimesh(tile_mani)
        assembly_meshes.append(t_mesh_world.copy())

        # Center individual tile at (0, 0, 0) for printing
        t_mesh_local = t_mesh_world.copy()
        bounds = t_mesh_local.bounds
        cx = 0.5 * (bounds[0][0] + bounds[1][0])
        cy = 0.5 * (bounds[0][1] + bounds[1][1])
        t_mesh_local.apply_translation([-cx, -cy, -bounds[0][2]])
        ext = tuple(round(float(v), 2) for v in t_mesh_local.extents)

        parts_out.append(
            LithophanePart(
                part_index=idx + 1,
                filename=f"{idx+1:02d}_{fname}",
                label=f"Tuile Lithophanie #{idx+1} ({fname.replace('.stl', '')})",
                extents_mm=ext,
                faces_count=int(len(t_mesh_local.faces)),
                stl_bytes=export_mesh_stl_bytes(t_mesh_local),
            )
        )

    if len(shared_midpoints) > 0:
        n_clips = min(16, len(shared_midpoints))
        clips_list = []
        for c_i in range(n_clips):
            row = c_i // 4
            col = c_i % 4
            cm = male_clip_mesh.copy()
            cm.apply_translation([(col - 1.5) * 32.0, (row - 1.0) * 18.0, 0.0])
            clips_list.append(cm)
        clips_combined = trimesh.util.concatenate(clips_list)
        ext_c = tuple(round(float(v), 2) for v in clips_combined.extents)
        parts_out.append(
            LithophanePart(
                part_index=len(parts_out) + 1,
                filename=f"{len(parts_out)+1:02d}_Connecteurs_Papillon_x{len(shared_midpoints)}.stl",
                label=f"Clips d'Assemblage Dos (×{len(shared_midpoints)} joints)",
                extents_mm=ext_c,
                faces_count=int(len(clips_combined.faces)),
                stl_bytes=export_mesh_stl_bytes(clips_combined),
            )
        )

    combined_assembly = trimesh.util.concatenate(assembly_meshes) if len(assembly_meshes) > 1 else assembly_meshes[0]
    return parts_out, combined_assembly


def build_curved_lithophane_mesh(
    t_grid: np.ndarray,
    arc_width_mm: float,
    height_mm: float,
    curve_angle_deg: float = 90.0,
    border_width_mm: float = 4.0,
    frame_thickness_mm: float = 4.0,
) -> trimesh.Trimesh:
    """Builds a self-standing curved lithophane (Arc 30°..180°) printed vertically."""
    grid = _apply_rectangular_border_frame_to_grid(t_grid, arc_width_mm, height_mm, border_width_mm, frame_thickness_mm)
    grid_flipped = np.flipud(grid)
    ny, nx = grid_flipped.shape

    theta_span = math.radians(max(25.0, min(180.0, float(curve_angle_deg))))
    r_inner = float(arc_width_mm) / theta_span

    thetas = np.linspace(-theta_span / 2.0, theta_span / 2.0, nx, dtype=np.float64)
    zs = np.linspace(0.0, float(height_mm), ny, dtype=np.float64)

    sin_t = np.sin(thetas)[None, :]
    cos_t = np.cos(thetas)[None, :]
    zv = np.broadcast_to(zs[:, None], (ny, nx))

    r_outer = r_inner + grid_flipped.astype(np.float64)
    y_center_offset = r_inner * math.cos(theta_span / 2.0)

    x_out = (r_outer * sin_t).ravel()
    y_out = (r_outer * cos_t - y_center_offset).ravel()
    z_out = zv.ravel()

    x_in = np.broadcast_to(r_inner * sin_t, (ny, nx)).ravel()
    y_in = np.broadcast_to(r_inner * cos_t - y_center_offset, (ny, nx)).ravel()
    z_in = zv.ravel()

    n_pts = nx * ny
    outer_verts = np.column_stack([x_out, y_out, z_out])
    inner_verts = np.column_stack([x_in, y_in, z_in])
    all_verts = np.vstack([outer_verts, inner_verts])

    r = np.arange(ny - 1, dtype=np.int64)[:, None]
    c = np.arange(nx - 1, dtype=np.int64)[None, :]
    p00 = (r * nx + c).ravel()
    p10 = p00 + 1
    p01 = p00 + nx
    p11 = p01 + 1

    f_out1 = np.column_stack([p00, p10, p11])
    f_out2 = np.column_stack([p00, p11, p01])

    b00 = p00 + n_pts
    b10 = p10 + n_pts
    b01 = p01 + n_pts
    b11 = p11 + n_pts
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

    all_faces = np.vstack([
        f_out1, f_out2,
        f_in1, f_in2,
        w_bot1, w_bot2,
        w_top1, w_top2,
        w_left1, w_left2,
        w_right1, w_right2,
    ])
    mesh = trimesh.Trimesh(vertices=all_verts, faces=all_faces, process=True)
    trimesh.repair.fix_normals(mesh)
    return mesh


def build_cylinder_lamp_lithophane_mesh(
    t_grid: np.ndarray,
    diameter_mm: float,
    height_mm: float,
    border_width_mm: float = 4.0,
    frame_thickness_mm: float = 3.6,
    lamp_spec: Optional[Dict[str, float]] = None,
) -> trimesh.Trimesh:
    """
    Builds a 100% watertight 360° Cylindrical Lithophane Lamp Shade with:
    - Seamless wrap around 360° (with 5-column seam feathering)
    - Top and bottom solid rim bands (`border_width_mm`) with a rear **cable notch** cut into the bottom rim
    - Integrated **Raised Standard Lamp Mount** at the base (e.g. Bambu Lab LED Kit 001 Ø60mm recess,
      inner support ledge, raised collar `elevation_mm`, and 4 radial support arms)!
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
    r_inner = max(20.0, float(diameter_mm) / 2.0)

    thetas = np.linspace(0.0, 2.0 * math.pi, nx, endpoint=False, dtype=np.float64)
    zs = np.linspace(0.0, float(height_mm), ny, dtype=np.float64)

    cos_t = np.cos(thetas)[None, :]
    sin_t = np.sin(thetas)[None, :]
    zv = np.broadcast_to(zs[:, None], (ny, nx)).copy()

    # Carve rear cable notch into bottom row (row 0) around theta = pi/2 (+Y rear)
    notch_w = lamp_spec["cable_notch_width_mm"]
    notch_h = min(lamp_spec["cable_notch_height_mm"], height_mm * 0.15)
    if notch_w > 0.5 and notch_h > 0.5:
        for c_i in range(nx):
            x_c = r_inner * math.cos(thetas[c_i])
            y_c = r_inner * math.sin(thetas[c_i])
            if y_c > 0 and abs(x_c) <= notch_w * 0.55:
                # Elevate bottom rows in the cable notch zone so the wire passes underneath cleanly
                for r_i in range(ny):
                    if zv[r_i, c_i] < notch_h:
                        zv[r_i, c_i] = notch_h

    r_outer = r_inner + grid_flipped

    x_out = (r_outer * cos_t).ravel()
    y_out = (r_outer * sin_t).ravel()
    z_out = zv.ravel()

    x_in = np.broadcast_to(r_inner * cos_t, (ny, nx)).ravel()
    y_in = np.broadcast_to(r_inner * sin_t, (ny, nx)).ravel()
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

    b00 = p00 + n_pts
    b10 = p10 + n_pts
    b01 = p01 + n_pts
    b11 = p11 + n_pts
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
    cyl_mesh = trimesh.Trimesh(vertices=all_verts, faces=all_faces, process=True)
    trimesh.repair.fix_normals(cyl_mesh)

    parts = [cyl_mesh]

    # Add the Raised Standard Lamp Mount + 4 Radial Support Bars at the base of the Cylinder
    puck_r = lamp_spec["puck_diameter_mm"] * 0.5
    if puck_r < r_inner + 1.0:
        holder_parts = build_suspended_lamp_holder_bars(
            inner_span_x=r_inner * 2.0,
            inner_span_y=r_inner * 2.0,
            z_base=0.0,
            lamp_spec=lamp_spec,
        )
        parts.extend(holder_parts)

    combined = trimesh.util.concatenate(parts)
    combined.merge_vertices()
    return combined


# ---------------------------------------------------------------------------
# 3. Lightbox Enclosures (Framed Lightbox & 4-Face Cube Lightbox with Lamp Bridge)
# ---------------------------------------------------------------------------

def build_framed_lightbox_enclosure(
    width_mm: float,
    height_mm: float,
    depth_mm: float = 42.0,
    plate_thickness_mm: float = 4.0,
    lamp_spec: Optional[Dict[str, float]] = None,
) -> Tuple[trimesh.Trimesh, float]:
    """
    Builds a shadowbox enclosure for a flat lithophane (`width_mm x height_mm`):
    - Outer frame walls (`wall_t = 3.2 mm`) with front groove + retaining lip for the lithophane plate
    - Open at the bottom (with rear cable notch) and equipped with a **Raised LED Lamp Holder held by
      4 internal support bars** (`build_suspended_lamp_holder_bars`) so the lamp is centered at the base!
    Returns `(enclosure_mesh_flat_for_print, groove_y_offset)`.
    """
    if lamp_spec is None:
        lamp_spec = resolve_lamp_spec("bambu_led_001")

    clearance = 0.40
    inner_w = float(width_mm) + 2.0 * clearance
    inner_h = float(height_mm) + 2.0 * clearance
    wall_t = 3.4
    outer_w = inner_w + 2.0 * wall_t
    outer_h = inner_h + 2.0 * wall_t
    d = max(28.0, float(depth_mm))

    # Build standing box (X = width, Y = depth, Z = height from 0 to outer_h)
    # Wait: let's build it directly in upright standing coordinates (X in [-outer_w/2, outer_w/2],
    # Y in [-d/2, d/2], Z in [0, outer_h]) so the lamp holder bars sit at Z = 0!
    lip_inset = 3.2
    front_win_w = inner_w - 2.0 * lip_inset
    front_win_h = inner_h - 2.0 * lip_inset
    lip_depth = 2.4
    slot_depth = float(plate_thickness_mm) + 0.6

    parts: List[trimesh.Trimesh] = []

    # Left, Right, Top walls
    left_wall = trimesh.creation.box(extents=[wall_t, d, outer_h])
    left_wall.apply_translation([-outer_w / 2.0 + wall_t / 2.0, 0.0, outer_h / 2.0])
    right_wall = trimesh.creation.box(extents=[wall_t, d, outer_h])
    right_wall.apply_translation([outer_w / 2.0 - wall_t / 2.0, 0.0, outer_h / 2.0])
    top_wall = trimesh.creation.box(extents=[outer_w, d, wall_t])
    top_wall.apply_translation([0.0, 0.0, outer_h - wall_t / 2.0])
    parts.extend([left_wall, right_wall, top_wall])

    # Bottom front & back retaining rails (leaving center open for airflow + lamp bridge bars!)
    rail_h = wall_t + lip_inset
    front_bot_rail = trimesh.creation.box(extents=[outer_w, lip_depth + slot_depth + 3.0, rail_h])
    front_bot_rail.apply_translation([0.0, -d / 2.0 + (lip_depth + slot_depth + 3.0) / 2.0, rail_h / 2.0])
    parts.append(front_bot_rail)

    # Front retaining lip around Left, Right, Top edges (at Y = -d/2 .. -d/2 + lip_depth)
    for sign_x in (-1.0, 1.0):
        side_lip = trimesh.creation.box(extents=[wall_t + lip_inset, lip_depth, outer_h])
        side_lip.apply_translation([
            sign_x * (outer_w / 2.0 - (wall_t + lip_inset) / 2.0),
            -d / 2.0 + lip_depth / 2.0,
            outer_h / 2.0,
        ])
        parts.append(side_lip)
    top_lip = trimesh.creation.box(extents=[outer_w, lip_depth, wall_t + lip_inset])
    top_lip.apply_translation([0.0, -d / 2.0 + lip_depth / 2.0, outer_h - (wall_t + lip_inset) / 2.0])
    parts.append(top_lip)

    # Internal back stop ribs behind the lithophane slot (at Y = -d/2 + lip_depth + slot_depth)
    stop_y = -d / 2.0 + lip_depth + slot_depth + 1.2
    for sign_x in (-1.0, 1.0):
        stop_rib = trimesh.creation.box(extents=[wall_t + 2.4, 2.4, inner_h])
        stop_rib.apply_translation([
            sign_x * (outer_w / 2.0 - (wall_t + 2.4) / 2.0),
            stop_y,
            outer_h / 2.0,
        ])
        parts.append(stop_rib)

    # Rear reflector wall (with bottom cable pass-through arch)
    back_t = 2.6
    notch_h = max(8.0, lamp_spec["cable_notch_height_mm"] + 2.0)
    back_wall = trimesh.creation.box(extents=[outer_w, back_t, outer_h - notch_h])
    back_wall.apply_translation([0.0, d / 2.0 - back_t / 2.0, notch_h + (outer_h - notch_h) / 2.0])
    parts.append(back_wall)

    # Suspended Raised Lamp Mount held by 4 bars at the base (Z = 0)
    lamp_bars = build_suspended_lamp_holder_bars(
        inner_span_x=inner_w,
        inner_span_y=d - 6.0,
        z_base=0.0,
        lamp_spec=lamp_spec,
    )
    parts.extend(lamp_bars)

    enclosure = trimesh.util.concatenate(parts)
    enclosure.merge_vertices()
    trimesh.repair.fix_normals(enclosure)
    front_plate_y = -d / 2.0 + lip_depth + plate_thickness_mm * 0.5
    return enclosure, front_plate_y


def build_cube_lightbox_body(
    panel_width_mm: float,
    plate_thickness_mm: float = 4.0,
    lamp_spec: Optional[Dict[str, float]] = None,
) -> Tuple[trimesh.Trimesh, float, float]:
    """
    Builds a 4-Sided Cube Lightbox structural frame:
    - 4 slotted corner pillars to slide 4 vertical lithophane panels from the top
    - Bottom retaining frame open underneath + **Raised Central LED Lamp Holder suspended on 4 support bars**
      (`build_suspended_lamp_holder_bars`) with cable notch!
    Returns `(cube_frame_mesh, outer_w, total_h)`.
    """
    if lamp_spec is None:
        lamp_spec = resolve_lamp_spec("bambu_led_001")

    clearance = 0.45
    w_in = float(panel_width_mm) + 2.0 * clearance
    pillar_t = 8.0
    outer_w = w_in + 2.0 * pillar_t
    total_h = w_in + 10.0

    parts: List[trimesh.Trimesh] = []

    # 1. Bottom open retaining frame (4 bottom perimeter beams of height 6mm)
    base_h = 6.0
    beam_w = pillar_t + 3.0
    for sign_y in (-1.0, 1.0):
        bm_x = trimesh.creation.box(extents=[outer_w, beam_w, base_h])
        bm_x.apply_translation([0.0, sign_y * (outer_w / 2.0 - beam_w / 2.0), base_h / 2.0])
        parts.append(bm_x)
    for sign_x in (-1.0, 1.0):
        bm_y = trimesh.creation.box(extents=[beam_w, outer_w, base_h])
        bm_y.apply_translation([sign_x * (outer_w / 2.0 - beam_w / 2.0), 0.0, base_h / 2.0])
        parts.append(bm_y)

    # 2. Central Raised Lamp Holder held by 4 support bars attached to the bottom perimeter beams!
    lamp_bars = build_suspended_lamp_holder_bars(
        inner_span_x=outer_w - 4.0,
        inner_span_y=outer_w - 4.0,
        z_base=0.0,
        lamp_spec=lamp_spec,
    )
    parts.extend(lamp_bars)

    # 3. 4 Slotted Corner Pillars (L-shaped outer corner + inner guide post leaving a groove for the 4 lithophane plates)
    slot_t = float(plate_thickness_mm) + 0.65
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            cx = sx * (outer_w / 2.0 - pillar_t / 2.0)
            cy = sy * (outer_w / 2.0 - pillar_t / 2.0)
            p_out = trimesh.creation.box(extents=[pillar_t, pillar_t, total_h])
            p_out.apply_translation([cx, cy, total_h / 2.0])
            parts.append(p_out)

            in_t = 3.2
            ix = sx * (outer_w / 2.0 - pillar_t - slot_t - in_t / 2.0)
            iy = sy * (outer_w / 2.0 - pillar_t - slot_t - in_t / 2.0)
            p_in = trimesh.creation.box(extents=[in_t, in_t, total_h - 4.0])
            p_in.apply_translation([ix, iy, (total_h - 4.0) / 2.0])
            parts.append(p_in)

    body = trimesh.util.concatenate(parts)
    body.merge_vertices()
    trimesh.repair.fix_normals(body)
    return body, outer_w, total_h


# ---------------------------------------------------------------------------
# 4. API Endpoints
# ---------------------------------------------------------------------------

@router.get("/status")
async def get_status():
    return {
        "module": "lithophane_gen",
        "status": "ready",
        "features": [
            "flat_plate_all_hueforge_shapes_and_multitile",
            "curved_arc",
            "half_cylinder",
            "cylinder_lamp_auto_adapt_and_raised_lamp_mount",
            "sphere_globe_photos_moon_planets_and_4_stands",
            "framed_lightbox_full_assembly_and_bar_lamp_mount",
            "cube_lightbox_4_images_full_assembly",
            "custom_rgb_led_backlight_simulation",
            "custom_lamp_standards_manager",
        ],
    }


@router.get("/lamp-standards")
async def get_lamp_standards():
    """Returns built-in + custom LED lamp standards (Bambu Lab LED Kit 001, USB Puck, E14, E27, Custom)."""
    return {"lamp_standards": load_lamp_standards()}


@router.post("/lamp-standards")
async def create_or_update_lamp_standard(req: CustomLampStandardRequest):
    """Saves a new custom LED lamp standard for future reuse."""
    updated = save_custom_lamp_standard(req.model_dump())
    return {"lamp_standards": updated}


@router.delete("/lamp-standards/{std_id}")
async def remove_lamp_standard(std_id: str):
    updated = delete_custom_lamp_standard(std_id)
    return {"lamp_standards": updated}


@router.post("/init-planet-session")
async def init_planet_lithophane_session(planet_mode: str = Query(default="planet_moon")):
    """Initializes a Lithophane Globe session directly from a built-in Planetary/Lunar map without needing an image upload."""
    pil_img = generate_planetary_luminance_map(planet_mode, width=720, height=360)
    w, h = pil_img.size
    aspect = round(float(w) / float(h), 4)
    session_id = str(uuid.uuid4())

    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    src_b64 = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"

    planet_names = {
        "planet_moon": "Lune_Cratères_HD.png",
        "planet_earth": "Terre_Continents_HD.png",
        "planet_mars": "Mars_Olympus_Mons.png",
        "planet_jupiter": "Jupiter_Grande_Tache.png",
        "planet_saturn": "Planete_SciFi_Anneaux.png",
    }
    state = LithophaneSessionState(
        session_id=session_id,
        filename=planet_names.get(planet_mode, "Globe_Planete.png"),
        original_image=pil_img,
        aspect_ratio=aspect,
    )
    LITHO_SESSIONS[session_id] = state

    t_grid, _ = compute_lithophane_thickness_grid(
        pil_img,
        nx=440,
        ny=220,
        min_thickness_mm=0.8,
        max_thickness_mm=3.0,
        contrast=1.15,
    )
    backlight_b64 = simulate_backlight_rgb(
        t_grid,
        min_thickness_mm=0.8,
        max_thickness_mm=3.0,
        td_mm=2.8,
        led_tint="warm_3000k",
    )

    return {
        "session_id": session_id,
        "filename": state.filename,
        "image_size": [w, h],
        "aspect_ratio": aspect,
        "effective_width_mm": round(math.pi * 140.0, 1),
        "effective_height_mm": 140.0,
        "source_preview_b64": src_b64,
        "backlight_preview_b64": backlight_b64,
        "extra_images_slots": [],
    }


@router.post("/upload-image")
async def upload_lithophane_image(file: UploadFile = File(...)):
    """Uploads the primary image (Slot 0) and initializes a Lithophane Studio session."""
    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Le fichier image est vide.")

    try:
        pil_img = Image.open(io.BytesIO(raw_bytes))
        pil_img = ImageOps.exif_transpose(pil_img).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Impossible de lire l'image: {exc}") from exc

    w, h = pil_img.size
    if w < 16 or h < 16:
        raise HTTPException(status_code=400, detail="L'image est trop petite (min 16x16 px).")

    aspect = round(float(w) / float(h), 4)
    session_id = str(uuid.uuid4())

    src_preview = pil_img.copy()
    src_preview.thumbnail((540, 540), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    src_preview.save(buf, format="PNG")
    src_b64 = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"

    state = LithophaneSessionState(
        session_id=session_id,
        filename=file.filename or "photo.png",
        original_image=pil_img,
        aspect_ratio=aspect,
    )
    LITHO_SESSIONS[session_id] = state

    default_req = LithoPreviewRequest()
    eff_w, eff_h = _resolve_dimensions_mm(state, default_req)
    pw = 440
    ph = max(140, int(round(pw * (eff_h / max(1.0, eff_w)))))
    if ph > 480:
        ph = 480
        pw = max(140, int(round(ph * (eff_w / max(1.0, eff_h)))))

    t_grid, _ = compute_lithophane_thickness_grid(
        pil_img,
        nx=pw,
        ny=ph,
        min_thickness_mm=default_req.min_thickness_mm,
        max_thickness_mm=default_req.max_thickness_mm,
        contrast=default_req.contrast,
    )
    backlight_b64 = simulate_backlight_rgb(
        t_grid,
        min_thickness_mm=default_req.min_thickness_mm,
        max_thickness_mm=default_req.max_thickness_mm,
        td_mm=default_req.td_mm,
        led_tint=default_req.led_tint,
        custom_led_hex=default_req.custom_led_hex,
    )

    return {
        "session_id": session_id,
        "filename": state.filename,
        "image_size": [w, h],
        "aspect_ratio": aspect,
        "effective_width_mm": eff_w,
        "effective_height_mm": eff_h,
        "source_preview_b64": src_b64,
        "backlight_preview_b64": backlight_b64,
        "extra_images_slots": [],
    }


@router.post("/{session_id}/upload-extra-image")
async def upload_extra_lithophane_image(
    session_id: str,
    slot: int = Query(default=1, ge=1, le=3),
    file: UploadFile = File(...),
):
    """Uploads an additional image (Slots 1, 2, or 3) for Cube 4-Faces or Multi-Photo Cylinder/Globe."""
    state = _get_litho_session(session_id)
    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Le fichier image est vide.")
    try:
        pil_img = Image.open(io.BytesIO(raw_bytes))
        pil_img = ImageOps.exif_transpose(pil_img).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Impossible de lire l'image: {exc}") from exc

    state.extra_images[int(slot)] = (file.filename or f"photo_face_{slot+1}.png", pil_img)

    # Build small thumbnail for UI slot badge
    thumb = pil_img.copy()
    thumb.thumbnail((160, 160), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    thumb.save(buf, format="PNG")
    thumb_b64 = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"

    return {
        "session_id": session_id,
        "slot": int(slot),
        "filename": state.extra_images[int(slot)][0],
        "thumb_b64": thumb_b64,
        "active_slots": sorted(list(state.extra_images.keys())),
    }


@router.delete("/{session_id}/extra-image/{slot}")
async def delete_extra_lithophane_image(session_id: str, slot: int):
    state = _get_litho_session(session_id)
    state.extra_images.pop(int(slot), None)
    return {
        "session_id": session_id,
        "active_slots": sorted(list(state.extra_images.keys())),
    }


@router.post("/{session_id}/upload-globe-stl")
async def upload_external_globe_stl(session_id: str, file: UploadFile = File(...)):
    """Allows the user to upload their own pre-made Planet or Moon `.STL` file for the Globe mode."""
    state = _get_litho_session(session_id)
    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Fichier STL vide.")
    state.external_globe_stl_bytes = raw_bytes
    state.external_globe_filename = file.filename or "planete_externe.stl"
    return {
        "session_id": session_id,
        "external_globe_filename": state.external_globe_filename,
        "size_kb": round(len(raw_bytes) / 1024.0, 1),
    }


@router.post("/{session_id}/preview-2d")
async def preview_lithophane_2d(session_id: str, req: LithoPreviewRequest):
    """
    Recomputes the 2D LED Backlight Simulation (`backlight_preview_b64`) in real time,
    including flat geometric shape cutouts / multi-tile grids, planetary maps, or multi-image panoramas.
    """
    state = _get_litho_session(session_id)
    src_img = _get_source_image_for_request(state, req)
    eff_w, eff_h = _resolve_dimensions_mm(state, req)

    inside_mask: Optional[np.ndarray] = None
    rim_mask: Optional[np.ndarray] = None
    max_tile_extents = [eff_w, eff_h]
    tiles_count = 1

    if req.shape_mode == "flat_plate" and req.flat_layout_mode != "single_original":
        tiles = build_layout_polygons(
            req.flat_layout_mode,
            size_mm=req.width_mm,
            aspect_ratio=state.aspect_ratio,
            grid_cols=req.grid_cols,
            grid_rows=req.grid_rows,
        )
        tiles_count = len(tiles)
        max_tile_extents = list(compute_max_tile_extents_mm(tiles))
        all_union = sg.MultiPolygon([p for _, p in tiles])
        minx, miny, maxx, maxy = all_union.bounds
        eff_w = round(float(maxx - minx), 1)
        eff_h = round(float(maxy - miny), 1)

        pw = 440
        ph = max(140, int(round(pw * (eff_h / max(1.0, eff_w)))))
        if ph > 480:
            ph = 480
            pw = max(140, int(round(ph * (eff_w / max(1.0, eff_h)))))

        inside_mask, rim_mask = _rasterize_layout_masks(
            tiles,
            border_style="raised_top" if req.border_width_mm > 0.1 else "none",
            border_width_mm=req.border_width_mm,
            width_px=pw,
            height_px=ph,
        )
    else:
        pw = 440
        ph = max(140, int(round(pw * (eff_h / max(1.0, eff_w)))))
        if ph > 480:
            ph = 480
            pw = max(140, int(round(ph * (eff_w / max(1.0, eff_h)))))

    # For Cube 4-Faces with multiple images, show a 2x2 collage of the 4 faces in the 2D preview!
    if req.shape_mode == "cube_lightbox" and len(state.extra_images) > 0:
        face_imgs = [
            state.original_image,
            state.extra_images.get(1, ("", state.original_image))[1],
            state.extra_images.get(2, ("", state.original_image))[1],
            state.extra_images.get(3, ("", state.original_image))[1],
        ]
        sub_w = pw // 2
        sub_h = sub_w
        pw, ph = sub_w * 2, sub_h * 2
        t_grid = np.zeros((ph, pw), dtype=np.float32)
        for idx_f, f_im in enumerate(face_imgs):
            r_i = idx_f // 2
            c_i = idx_f % 2
            tg_sub, _ = compute_lithophane_thickness_grid(
                f_im,
                nx=sub_w,
                ny=sub_h,
                min_thickness_mm=req.min_thickness_mm,
                max_thickness_mm=req.max_thickness_mm,
                negative_invert=req.negative_invert,
                flip_horizontal=req.flip_horizontal,
                contrast=req.contrast,
                gamma=req.gamma,
                detail_boost=req.detail_boost,
                smoothing_sigma=req.smoothing_sigma,
            )
            frame_t = req.max_thickness_mm + req.border_extra_mm
            tg_sub = _apply_rectangular_border_frame_to_grid(tg_sub, req.width_mm, req.width_mm, req.border_width_mm, frame_t)
            t_grid[r_i * sub_h : (r_i + 1) * sub_h, c_i * sub_w : (c_i + 1) * sub_w] = tg_sub
    else:
        t_grid, _ = compute_lithophane_thickness_grid(
            src_img,
            nx=pw,
            ny=ph,
            min_thickness_mm=req.min_thickness_mm,
            max_thickness_mm=req.max_thickness_mm,
            negative_invert=req.negative_invert,
            flip_horizontal=req.flip_horizontal,
            contrast=req.contrast,
            gamma=req.gamma,
            detail_boost=req.detail_boost,
            smoothing_sigma=req.smoothing_sigma,
        )

    backlight_b64 = simulate_backlight_rgb(
        t_grid,
        min_thickness_mm=req.min_thickness_mm,
        max_thickness_mm=req.max_thickness_mm,
        td_mm=req.td_mm,
        led_tint=req.led_tint,
        custom_led_hex=req.custom_led_hex,
        inside_mask=inside_mask,
        rim_mask=rim_mask,
    )

    # Also return updated source preview when planetary map or stitched panorama is active
    src_prev = src_img.copy()
    src_prev.thumbnail((520, 520), Image.Resampling.LANCZOS)
    buf_s = io.BytesIO()
    src_prev.save(buf_s, format="PNG")
    src_b64 = f"data:image/png;base64,{base64.b64encode(buf_s.getvalue()).decode('ascii')}"

    return {
        "session_id": session_id,
        "shape_mode": req.shape_mode,
        "effective_width_mm": eff_w,
        "effective_height_mm": eff_h,
        "max_tile_extents_mm": max_tile_extents,
        "tiles_count": tiles_count,
        "source_preview_b64": src_b64,
        "backlight_preview_b64": backlight_b64,
    }


@router.post("/{session_id}/generate-stl")
async def generate_lithophane_3d_stl(session_id: str, req: LithoPreviewRequest):
    """
    Generates the watertight 3D `.STL` meshes for the chosen Lithophane / Lightbox / Globe architecture,
    creates a Complete 3D Assembly Preview (`00_Assemble_Complet_Preview.stl`) so the user sees the full
    3D object (Cube with 4 faces, Lightbox with frame & lamp holder, Globe on its Stand, or Multi-Tile),
    and packages all individual printable STL parts + guide into a `.ZIP` archive.
    """
    state = _get_litho_session(session_id)
    src_img = _get_source_image_for_request(state, req)
    eff_w, eff_h = _resolve_dimensions_mm(state, req)

    lamp_spec = resolve_lamp_spec(
        req.lamp_standard_id,
        custom_diameter_mm=req.led_socket_diameter_mm,
        custom_elevation_mm=req.lamp_elevation_mm,
        custom_recess_mm=req.lamp_recess_depth_mm,
        custom_notch_w_mm=req.cable_notch_width_mm,
        custom_notch_h_mm=req.cable_notch_height_mm,
    )

    frame_t = round(float(req.max_thickness_mm + req.border_extra_mm), 2)
    parts: List[LithophanePart] = []
    assembly_preview_mesh: Optional[trimesh.Trimesh] = None

    # Helper to compute resolution
    def _calc_grid_res(w_val: float, h_val: float) -> Tuple[int, int]:
        if w_val >= h_val:
            nx_v = int(req.grid_resolution)
            ny_v = max(64, int(round(req.grid_resolution * (h_val / max(1.0, w_val)))))
        else:
            ny_v = int(req.grid_resolution)
            nx_v = max(64, int(round(req.grid_resolution * (w_val / max(1.0, h_val)))))
        return nx_v, ny_v

    try:
        if req.shape_mode == "flat_plate":
            if req.flat_layout_mode != "single_original":
                nx, ny = _calc_grid_res(eff_w, eff_h)
                t_grid, _ = compute_lithophane_thickness_grid(
                    src_img,
                    nx=nx,
                    ny=ny,
                    min_thickness_mm=req.min_thickness_mm,
                    max_thickness_mm=req.max_thickness_mm,
                    negative_invert=req.negative_invert,
                    flip_horizontal=req.flip_horizontal,
                    contrast=req.contrast,
                    gamma=req.gamma,
                    detail_boost=req.detail_boost,
                    smoothing_sigma=req.smoothing_sigma,
                )
                parts, assembly_preview_mesh = build_shaped_or_multitile_flat_lithophanes(
                    t_grid=t_grid,
                    flat_layout_mode=req.flat_layout_mode,
                    width_mm=req.width_mm,
                    aspect_ratio=state.aspect_ratio,
                    grid_cols=req.grid_cols,
                    grid_rows=req.grid_rows,
                    border_width_mm=req.border_width_mm,
                    frame_thickness_mm=frame_t,
                    add_hanging_ring=req.add_hanging_ring,
                )
            else:
                nx, ny = _calc_grid_res(eff_w, eff_h)
                t_grid, _ = compute_lithophane_thickness_grid(
                    src_img,
                    nx=nx,
                    ny=ny,
                    min_thickness_mm=req.min_thickness_mm,
                    max_thickness_mm=req.max_thickness_mm,
                    negative_invert=req.negative_invert,
                    flip_horizontal=req.flip_horizontal,
                    contrast=req.contrast,
                    gamma=req.gamma,
                    detail_boost=req.detail_boost,
                    smoothing_sigma=req.smoothing_sigma,
                )
                mesh = build_flat_lithophane_mesh(
                    t_grid,
                    width_mm=eff_w,
                    height_mm=eff_h,
                    border_width_mm=req.border_width_mm,
                    frame_thickness_mm=frame_t,
                    add_hanging_ring=req.add_hanging_ring,
                    add_stand_feet=req.add_stand_feet,
                    stand_vertical_for_print=req.stand_vertical_for_print,
                )
                ext = tuple(round(float(v), 2) for v in mesh.extents)
                parts.append(
                    LithophanePart(
                        part_index=1,
                        filename="01_Lithophane_Flat_Panel.stl",
                        label="Plaque Lithophanie HD",
                        extents_mm=ext,
                        faces_count=int(len(mesh.faces)),
                        stl_bytes=export_mesh_stl_bytes(mesh),
                    )
                )
                assembly_preview_mesh = mesh

        elif req.shape_mode in ("curved_arc", "half_cylinder"):
            nx, ny = _calc_grid_res(eff_w, eff_h)
            t_grid, _ = compute_lithophane_thickness_grid(
                src_img,
                nx=nx,
                ny=ny,
                min_thickness_mm=req.min_thickness_mm,
                max_thickness_mm=req.max_thickness_mm,
                negative_invert=req.negative_invert,
                flip_horizontal=req.flip_horizontal,
                contrast=req.contrast,
                gamma=req.gamma,
                detail_boost=req.detail_boost,
                smoothing_sigma=req.smoothing_sigma,
            )
            angle = 180.0 if req.shape_mode == "half_cylinder" else float(req.curve_angle_deg)
            mesh = build_curved_lithophane_mesh(
                t_grid,
                arc_width_mm=eff_w,
                height_mm=eff_h,
                curve_angle_deg=angle,
                border_width_mm=req.border_width_mm,
                frame_thickness_mm=frame_t,
            )
            ext = tuple(round(float(v), 2) for v in mesh.extents)
            lbl = "Demi-Cylindre Veilleuse 180°" if req.shape_mode == "half_cylinder" else f"Lithophanie Courbée ({int(angle)}°)"
            parts.append(
                LithophanePart(
                    part_index=1,
                    filename="01_Lithophane_Curved_Stand.stl",
                    label=lbl,
                    extents_mm=ext,
                    faces_count=int(len(mesh.faces)),
                    stl_bytes=export_mesh_stl_bytes(mesh),
                )
            )
            assembly_preview_mesh = mesh

        elif req.shape_mode == "cylinder_lamp":
            nx = max(320, int(req.grid_resolution * 1.25))
            ny = max(120, int(round(nx * (eff_h / max(1.0, eff_w)))))
            t_grid, _ = compute_lithophane_thickness_grid(
                src_img,
                nx=nx,
                ny=ny,
                min_thickness_mm=req.min_thickness_mm,
                max_thickness_mm=req.max_thickness_mm,
                negative_invert=req.negative_invert,
                flip_horizontal=req.flip_horizontal,
                contrast=req.contrast,
                gamma=req.gamma,
                detail_boost=req.detail_boost,
                smoothing_sigma=req.smoothing_sigma,
            )
            mesh = build_cylinder_lamp_lithophane_mesh(
                t_grid,
                diameter_mm=req.cylinder_diameter_mm,
                height_mm=eff_h,
                border_width_mm=req.border_width_mm,
                frame_thickness_mm=frame_t,
                lamp_spec=lamp_spec,
            )
            ext = tuple(round(float(v), 2) for v in mesh.extents)
            parts.append(
                LithophanePart(
                    part_index=1,
                    filename="01_Lithophane_Cylinder_360_Lamp.stl",
                    label=f"Abat-Jour Cylindre 360° (Ø{int(req.cylinder_diameter_mm)}×{int(eff_h)}mm + Support Lampe)",
                    extents_mm=ext,
                    faces_count=int(len(mesh.faces)),
                    stl_bytes=export_mesh_stl_bytes(mesh),
                )
            )
            assembly_preview_mesh = mesh

        elif req.shape_mode == "sphere_globe":
            # 1. Build or load the 3D Lithophane Globe
            if req.globe_source_mode == "external_stl" and state.external_globe_stl_bytes:
                ext_mesh, _ = load_and_repair_stl(state.external_globe_stl_bytes, auto_center=True)
                # Scale external STL to match requested sphere_diameter_mm
                cur_max = max(1.0, float(max(ext_mesh.extents[0], ext_mesh.extents[1])))
                scale_f = float(req.sphere_diameter_mm) / cur_max
                ext_mesh.apply_scale(scale_f)
                min_z = float(ext_mesh.bounds[0][2])
                ext_mesh.apply_translation([0.0, 0.0, -min_z])
                globe_mesh = ext_mesh
                puck_r = lamp_spec["puck_diameter_mm"] * 0.5
                r_in = max(25.0, req.sphere_diameter_mm * 0.5 - req.max_thickness_mm)
                open_r_in = min(r_in * 0.62, max(18.0, puck_r * 0.88))
                globe_info = {
                    "outer_diameter_mm": req.sphere_diameter_mm,
                    "open_r_in_mm": open_r_in,
                    "open_r_out_mm": open_r_in + 2.6,
                    "collar_drop_mm": 6.0,
                }
            else:
                nx_s = max(280, int(req.grid_resolution * 1.15))
                ny_s = max(140, nx_s // 2)
                t_grid, _ = compute_lithophane_thickness_grid(
                    src_img,
                    nx=nx_s,
                    ny=ny_s,
                    min_thickness_mm=req.min_thickness_mm,
                    max_thickness_mm=req.max_thickness_mm,
                    negative_invert=req.negative_invert,
                    flip_horizontal=req.flip_horizontal,
                    contrast=req.contrast,
                    gamma=req.gamma,
                    detail_boost=req.detail_boost,
                    smoothing_sigma=req.smoothing_sigma,
                )
                globe_mesh, globe_info = build_sphere_globe_lithophane_mesh(
                    t_grid=t_grid,
                    outer_diameter_mm=req.sphere_diameter_mm,
                    min_thickness_mm=req.min_thickness_mm,
                    max_thickness_mm=req.max_thickness_mm,
                    lamp_spec=lamp_spec,
                )

            # 2. Build the chosen Lamp Stand (Socle)
            stand_mesh = build_globe_lamp_stand_mesh(
                stand_style=req.globe_stand_style,
                globe_info=globe_info,
                lamp_spec=lamp_spec,
            )

            ext_g = tuple(round(float(v), 2) for v in globe_mesh.extents)
            ext_s = tuple(round(float(v), 2) for v in stand_mesh.extents)

            globe_labels = {
                "custom_photo": "Boule Lithophanie Photo",
                "planet_moon": "Boule Lithophanie — La Lune (Cratères HD)",
                "planet_earth": "Boule Lithophanie — La Terre",
                "planet_mars": "Boule Lithophanie — Mars",
                "planet_jupiter": "Boule Lithophanie — Jupiter",
                "planet_saturn": "Boule Lithophanie — Sci-Fi / Saturne",
                "external_stl": f"Boule Import STL ({state.external_globe_filename or 'Planète'})",
            }
            stand_labels = {
                "ring_bambu": "Socle Anneau Minimaliste (Standard Lampe)",
                "tripod_modern": "Socle Trépied Design 3 Pieds",
                "pedestal_fluted": "Socle Piédestal Architectural Cannelé",
                "crown_gothic": "Socle Couronne 4 Griffes",
            }

            parts.append(
                LithophanePart(
                    part_index=1,
                    filename="01_Boule_Lithophanie_Globe.stl",
                    label=f"{globe_labels.get(req.globe_source_mode, 'Globe')} (Ø{int(req.sphere_diameter_mm)}mm)",
                    extents_mm=ext_g,
                    faces_count=int(len(globe_mesh.faces)),
                    stl_bytes=export_mesh_stl_bytes(globe_mesh),
                )
            )
            parts.append(
                LithophanePart(
                    part_index=2,
                    filename=f"02_Socle_{req.globe_stand_style}_Support_Lampe.stl",
                    label=stand_labels.get(req.globe_stand_style, "Socle Support Lampe"),
                    extents_mm=ext_s,
                    faces_count=int(len(stand_mesh.faces)),
                    stl_bytes=export_mesh_stl_bytes(stand_mesh),
                )
            )

            # 3. Build Complete 3D Assembly Preview (Globe seated on top of its Lamp Stand!)
            globe_placed = globe_mesh.copy()
            seat_z = max(6.0, lamp_spec["elevation_mm"]) + lamp_spec["recess_depth_mm"] - 2.0
            globe_placed.apply_translation([0.0, 0.0, seat_z])
            assembly_preview_mesh = trimesh.util.concatenate([stand_mesh.copy(), globe_placed])

        elif req.shape_mode == "framed_lightbox":
            nx, ny = _calc_grid_res(eff_w, eff_h)
            t_grid, _ = compute_lithophane_thickness_grid(
                src_img,
                nx=nx,
                ny=ny,
                min_thickness_mm=req.min_thickness_mm,
                max_thickness_mm=req.max_thickness_mm,
                negative_invert=req.negative_invert,
                flip_horizontal=req.flip_horizontal,
                contrast=req.contrast,
                gamma=req.gamma,
                detail_boost=req.detail_boost,
                smoothing_sigma=req.smoothing_sigma,
            )
            plate_flat = build_flat_lithophane_mesh(
                t_grid,
                width_mm=eff_w,
                height_mm=eff_h,
                border_width_mm=req.border_width_mm,
                frame_thickness_mm=frame_t,
                add_hanging_ring=False,
                add_stand_feet=False,
                stand_vertical_for_print=False,
            )
            plate_for_print = (
                build_flat_lithophane_mesh(
                    t_grid,
                    width_mm=eff_w,
                    height_mm=eff_h,
                    border_width_mm=req.border_width_mm,
                    frame_thickness_mm=frame_t,
                    stand_vertical_for_print=True,
                )
                if req.stand_vertical_for_print
                else plate_flat
            )

            box_mesh, front_plate_y = build_framed_lightbox_enclosure(
                width_mm=eff_w,
                height_mm=eff_h,
                depth_mm=req.lightbox_depth_mm,
                plate_thickness_mm=frame_t,
                lamp_spec=lamp_spec,
            )
            ext_p = tuple(round(float(v), 2) for v in plate_for_print.extents)
            ext_b = tuple(round(float(v), 2) for v in box_mesh.extents)
            parts.append(
                LithophanePart(
                    part_index=1,
                    filename="01_Lithophane_Facade_Avant.stl",
                    label="Façade Lithophanie Amovible",
                    extents_mm=ext_p,
                    faces_count=int(len(plate_for_print.faces)),
                    stl_bytes=export_mesh_stl_bytes(plate_for_print),
                )
            )
            parts.append(
                LithophanePart(
                    part_index=2,
                    filename="02_Caisson_Lightbox_Support_Lampe_Barres.stl",
                    label="Caisson Lightbox + Support Lampe sur Barres",
                    extents_mm=ext_b,
                    faces_count=int(len(box_mesh.faces)),
                    stl_bytes=export_mesh_stl_bytes(box_mesh),
                )
            )

            # Build Complete Standing 3D Assembly Preview (Box + Upright Front Lithophane Plate mounted in front slot!)
            plate_upright = plate_flat.copy()
            # Rotate flat plate (XY, relief on +Z) by +90° around X so relief points toward -Y (front of lightbox!)
            rot_x = trimesh.transformations.rotation_matrix(math.pi / 2.0, [1.0, 0.0, 0.0])
            plate_upright.apply_transform(rot_x)
            box_center_z = float(box_mesh.bounds[1][2] + box_mesh.bounds[0][2]) * 0.5
            plate_upright.apply_translation([0.0, front_plate_y, box_center_z])
            assembly_preview_mesh = trimesh.util.concatenate([box_mesh.copy(), plate_upright])

        elif req.shape_mode == "cube_lightbox":
            # Support 1 to 4 distinct images on the 4 faces of the Cube!
            face_defs = [
                (0, "01_Lithophane_Face_1_Avant.stl", "Panneau Cube #1 — Face Avant", state.original_image),
                (1, "02_Lithophane_Face_2_Droite.stl", "Panneau Cube #2 — Face Droite", state.extra_images.get(1, ("", state.original_image))[1]),
                (2, "03_Lithophane_Face_3_Arriere.stl", "Panneau Cube #3 — Face Arrière", state.extra_images.get(2, ("", state.original_image))[1]),
                (3, "04_Lithophane_Face_4_Gauche.stl", "Panneau Cube #4 — Face Gauche", state.extra_images.get(3, ("", state.original_image))[1]),
            ]
            nx_c = int(req.grid_resolution)
            ny_c = nx_c

            cube_body, outer_w, total_h = build_cube_lightbox_body(
                panel_width_mm=eff_w,
                plate_thickness_mm=frame_t,
                lamp_spec=lamp_spec,
            )

            assembled_cube_parts: List[trimesh.Trimesh] = [cube_body.copy()]
            panel_offset_dist = (eff_w * 0.5) - frame_t * 0.5
            panel_center_z = 6.0 + eff_w * 0.5

            for f_idx, fname, flabel, f_img in face_defs:
                t_grid_f, _ = compute_lithophane_thickness_grid(
                    f_img,
                    nx=nx_c,
                    ny=ny_c,
                    min_thickness_mm=req.min_thickness_mm,
                    max_thickness_mm=req.max_thickness_mm,
                    negative_invert=req.negative_invert,
                    flip_horizontal=req.flip_horizontal,
                    contrast=req.contrast,
                    gamma=req.gamma,
                    detail_boost=req.detail_boost,
                    smoothing_sigma=req.smoothing_sigma,
                )
                flat_panel = build_flat_lithophane_mesh(
                    t_grid_f,
                    width_mm=eff_w,
                    height_mm=eff_w,
                    border_width_mm=req.border_width_mm,
                    frame_thickness_mm=frame_t,
                    stand_vertical_for_print=False,
                )
                print_panel = (
                    build_flat_lithophane_mesh(
                        t_grid_f,
                        width_mm=eff_w,
                        height_mm=eff_w,
                        border_width_mm=req.border_width_mm,
                        frame_thickness_mm=frame_t,
                        stand_vertical_for_print=True,
                    )
                    if req.stand_vertical_for_print
                    else flat_panel
                )
                ext_p = tuple(round(float(v), 2) for v in print_panel.extents)
                parts.append(
                    LithophanePart(
                        part_index=f_idx + 1,
                        filename=fname,
                        label=flabel,
                        extents_mm=ext_p,
                        faces_count=int(len(print_panel.faces)),
                        stl_bytes=export_mesh_stl_bytes(print_panel),
                    )
                )

                # Position upright panel onto its side of the 3D assembled Cube!
                # First stand upright facing -Y (Front)
                up_p = flat_panel.copy()
                rot_up = trimesh.transformations.rotation_matrix(math.pi / 2.0, [1.0, 0.0, 0.0])
                up_p.apply_transform(rot_up)
                up_p.apply_translation([0.0, -panel_offset_dist, panel_center_z])
                # Then rotate around Z by f_idx * 90° (0°=Front -Y, 90°=Right +X, 180°=Back +Y, 270°=Left -X)
                if f_idx > 0:
                    rot_z = trimesh.transformations.rotation_matrix(f_idx * (math.pi / 2.0), [0.0, 0.0, 1.0])
                    up_p.apply_transform(rot_z)
                assembled_cube_parts.append(up_p)

            ext_c = tuple(round(float(v), 2) for v in cube_body.extents)
            parts.append(
                LithophanePart(
                    part_index=5,
                    filename="05_Cube_Structure_Support_Lampe_Barres.stl",
                    label="Structure Cube 4-Faces + Support Lampe sur Barres",
                    extents_mm=ext_c,
                    faces_count=int(len(cube_body.faces)),
                    stl_bytes=export_mesh_stl_bytes(cube_body),
                )
            )
            assembly_preview_mesh = trimesh.util.concatenate(assembled_cube_parts)

    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Erreur lors de la génération 3D Lithophanie: {exc}") from exc

    # Package ZIP with slicer guide
    guide_lines = [
        "======================================================================",
        "  MAKERSTUDIO 3D — FICHE D'IMPRESSION LITHOPHANIE & LIGHTBOX LED V2   ",
        "======================================================================",
        f"Fichier image source : {state.filename}",
        f"Architecture 3D      : {req.shape_mode}",
        f"Dimensions panneau   : {eff_w} x {eff_h} mm",
        f"Épaisseur min (clair): {req.min_thickness_mm} mm",
        f"Épaisseur max (sombre): {req.max_thickness_mm} mm (Bordure: {frame_t} mm)",
        f"Standard Lampe LED   : {req.lamp_standard_id} (Ø{lamp_spec['puck_diameter_mm']} mm, Réhausse {lamp_spec['elevation_mm']} mm)",
        "",
        "--- PARAMÈTRES SLICER CRITIQUES (CREALITY PRINT / ORCASLICER) ---",
        "1. Filament recommandé : PLA+ Blanc Pur ou Blanc Chaud (TD ~ 2.5 à 3.5 mm)",
        "2. Hauteur de couche   : 0.12 mm (ou 0.16 mm) — 1ère couche à 0.20 mm",
        "3. Parois (Walls)      : 6 à 8 périmètres OU Remplissage 100% Rectiligne",
        "   >>> JAMAIS de remplissage Grille/Gyroïde à 15% dans une lithophanie ! <<<",
        "4. Vitesse parois ext. : 45 à 60 mm/s pour une netteté photographique maximale",
        "5. Bordure (Brim)      : Activer un Brim extérieur de 5 à 8 mm si impression verticale.",
        "",
        "--- PIÈCES STL GÉNÉRÉES DANS CETTE ARCHIVE ---",
    ]
    for p in parts:
        guide_lines.append(
            f"  [{p.part_index}] {p.filename} ({p.label}) — {p.extents_mm[0]} x {p.extents_mm[1]} x {p.extents_mm[2]} mm ({p.faces_count} faces)"
        )

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in parts:
            zf.writestr(p.filename, p.stl_bytes)
        zf.writestr("GUIDE_SLICER_LITHOPHANIE_CREALITY.txt", "\n".join(guide_lines))

    state.last_zip_bytes = zip_buf.getvalue()
    state.last_parts_stl_bytes = {p.part_index: p.stl_bytes for p in parts}

    if assembly_preview_mesh is not None:
        state.last_assembly_stl_bytes = export_mesh_stl_bytes(assembly_preview_mesh)
        state.last_preview_stl_bytes = state.last_assembly_stl_bytes
        stats_mesh = assembly_preview_mesh
    else:
        state.last_assembly_stl_bytes = parts[0].stl_bytes
        state.last_preview_stl_bytes = parts[0].stl_bytes
        stats_mesh, _ = load_and_repair_stl(parts[0].stl_bytes, auto_center=False)

    state.last_parts_meta = [p.to_dict() for p in parts]
    state.last_mesh_stats = {
        "vertices_count": int(len(stats_mesh.vertices)),
        "faces_count": int(len(stats_mesh.faces)),
        "is_watertight": True,
        "repair_method": "Manifold Lithophane Generator V2",
        "extents": [round(float(v), 2) for v in stats_mesh.extents],
    }

    return {
        "session_id": session_id,
        "shape_mode": req.shape_mode,
        "parts_count": len(parts),
        "parts": state.last_parts_meta,
        "stats": state.last_mesh_stats,
        "has_assembly_preview": len(parts) > 1,
        "preview_stl_url": f"/api/lithophane/{session_id}/preview-stl",
        "download_stl_url": f"/api/lithophane/{session_id}/download-stl",
        "download_zip_url": f"/api/lithophane/{session_id}/download-zip",
    }


@router.get("/{session_id}/preview-stl")
async def get_lithophane_preview_stl(session_id: str, part_index: int = Query(default=0)):
    """
    Returns the binary `.STL` for the 3D Three.js viewport:
    - `part_index = 0` (default): Complete 3D Assembled Model (Cube with 4 faces, Lightbox with plate, Globe on Stand, or Multi-Tile).
    - `part_index = 1..N`: Individual printable STL part `#part_index`.
    """
    state = _get_litho_session(session_id)
    if part_index > 0 and part_index in state.last_parts_stl_bytes:
        content = state.last_parts_stl_bytes[part_index]
        fname = f"part_{part_index}.stl"
    elif state.last_assembly_stl_bytes:
        content = state.last_assembly_stl_bytes
        fname = "lithophane_assembly_preview.stl"
    elif state.last_preview_stl_bytes:
        content = state.last_preview_stl_bytes
        fname = "lithophane_preview.stl"
    else:
        raise HTTPException(status_code=404, detail="Aucun maillage 3D généré pour cette session.")

    return Response(
        content=content,
        media_type="model/stl",
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
    )


@router.get("/{session_id}/download-stl")
async def download_lithophane_single_stl(session_id: str, part_index: int = Query(default=1)):
    """Downloads a specific printable `.STL` part (default part 1)."""
    state = _get_litho_session(session_id)
    content = state.last_parts_stl_bytes.get(part_index) or state.last_preview_stl_bytes
    if not content:
        raise HTTPException(status_code=404, detail="Aucun fichier STL généré pour cette session.")
    base_name = state.filename.rsplit(".", 1)[0]
    return Response(
        content=content,
        media_type="model/stl",
        headers={"Content-Disposition": f'attachment; filename="{base_name}_Lithophanie_P{part_index}.stl"'},
    )


@router.get("/{session_id}/download-zip")
async def download_lithophane_zip(session_id: str):
    """Downloads the complete `.ZIP` archive (all STL parts + Slicer Guide)."""
    state = _get_litho_session(session_id)
    if not state.last_zip_bytes:
        raise HTTPException(status_code=404, detail="Aucune archive ZIP générée pour cette session.")
    base_name = state.filename.rsplit(".", 1)[0]
    return Response(
        content=state.last_zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{base_name}_Lithophanie_Lightbox_Kit.zip"'},
    )
