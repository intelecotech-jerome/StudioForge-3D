"""
Module 2A : HueForge Pro Auto-Studio & Multi-Frame Geometric Tiler (`modules_futurs/hueforge_tiler.py`)
Calibrated for Creality Hi (260x260 mm + Double CFS 8 colors) & Creality K1 Max (300x300 mm).

Pro Features:
1. Perceptual Image Analysis + Vivid Spool Boosting:
   - Avoids muddy K-Means grey/brown averages by boosting chroma on saturated bands, enforcing deep darks
     for layer 1 and crisp highlights for top layer.
   - Supports interactive per-layer Z height / Layer# sliders and Transmission Distance (TD) optical blending.
2. Manga / Line-Art Edge Enhancer + High-Definition Relief (up to 520x520 grid = ~540k triangles):
   - Unsharp mask & dark line-art trench preservation so eyes, hair, and outlines print razor-sharp.
3. Image Framing Controls (Zoom %, Offset X %, Offset Y %) inside any geometric shape or multi-frame mosaic.
4. Integrated Perimeter Frame / Border (Rim):
   - Optional outer border (e.g. 2.5 mm wide) around each tile, either `raised` (top color) or `base` (black base color).
5. Single & Multi-Frame Tiling + Back-side Female Bowtie Sockets + Male Clips STL + 3D Back Numbering + ZIP Export.
"""
from __future__ import annotations

import base64
import colorsys
import io
import math
import uuid
import zipfile
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Tuple, Optional, Literal

import numpy as np
from PIL import Image, ImageDraw
from scipy.cluster.vq import kmeans2
from scipy.ndimage import gaussian_filter, distance_transform_edt
import shapely.geometry as sg
import trimesh
import manifold3d as m3d
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.mesh_repair import manifold_to_trimesh, export_mesh_stl_bytes
from core.connectors import create_3d_number_stamp_manifold
from core.spool_library import match_palette_to_in_stock_spools


router = APIRouter(prefix="/api/hueforge", tags=["Module 2A - HueForge Pro Auto-Studio & Multi-Frame Tiler"])


LayoutMode = Literal[
    "single_original",
    "single_circle",
    "single_square",
    "single_hexagon",
    "single_octagon",
    "single_triangle",
    "single_diamond",
    "single_heart",
    "single_star5",
    "single_shield",
    "single_arch",
    "multi_4_squares",
    "multi_grid_squares",
    "multi_15_squares",
    "multi_7_hexagons",
    "multi_6_triangles",
    "multi_4_triangles",
]

BorderStyle = Literal["none", "raised_top", "recessed_base"]
FillMode = Literal["smart_aura", "edge_stretch", "mirror_blend", "solid_edge", "none_preview"]
ArtStyle = Literal[
    "standard",
    "intaglio_splash",
    "stained_glass_ink",
    "papercut_terraced",
    "halftone_manga",
    "cyber_neon",
]

CFS_SLOTS = ["CFS1-A", "CFS1-B", "CFS1-C", "CFS1-D", "CFS2-A", "CFS2-B", "CFS2-C", "CFS2-D"]

# Standard Vivid Filament Spools Catalog for 1-click assignment
STANDARD_FILAMENT_SPOOLS = [
    {"name": "Noir Profond", "hex": "#101216"},
    {"name": "Bleu Nuit", "hex": "#1b2a4a"},
    {"name": "Bleu Royal", "hex": "#1d4ed8"},
    {"name": "Cyan Glace", "hex": "#06b6d4"},
    {"name": "Violet Électrique", "hex": "#7c3aed"},
    {"name": "Rouge Sang", "hex": "#dc2626"},
    {"name": "Orange Feu (Goku)", "hex": "#f97316"},
    {"name": "Jaune Or", "hex": "#facc15"},
    {"name": "Vert Émeraude", "hex": "#10b981"},
    {"name": "Gris Argent", "hex": "#94a3b8"},
    {"name": "Ivoire / Peau", "hex": "#fde68a"},
    {"name": "Blanc Pur", "hex": "#ffffff"},
]


@dataclass
class ColorLayerSpec:
    layer_index: int
    cfs_slot: str
    hex_color: str
    rgb: Tuple[int, int, int]
    luminance: float
    start_mm: float
    end_mm: float
    start_layer_num: int
    end_layer_num: int
    td_mm: float = 2.0
    spool_id: Optional[str] = None
    spool_label: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HueForgeSession:
    session_id: str
    filename: str
    image_rgb: np.ndarray        # Active (H, W, 3) uint8
    aspect_ratio: float          # W / H
    recommended_colors: int
    palettes_by_k: Dict[int, List[Dict[str, Any]]]
    stock_palettes_by_k: Dict[int, List[Dict[str, Any]]]
    original_image_rgb: Optional[np.ndarray] = None
    has_validated_outpaint: bool = False
    last_zip_bytes: Optional[bytes] = None
    last_3mf_bytes: Optional[bytes] = None
    last_preview_mesh: Optional[trimesh.Trimesh] = None


HUEFORGE_SESSIONS: Dict[str, HueForgeSession] = {}


# ---------------------------------------------------------------------------
# 1. Color Analysis & Anti-Hallucination Hue-Stratified Palette Proposal
# ---------------------------------------------------------------------------

def _rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    return f"#{int(rgb[0]):02x}{int(rgb[1]):02x}{int(rgb[2]):02x}"


def _hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
    h = hex_str.lstrip("#")
    if len(h) != 6:
        return (255, 255, 255)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _rgb_array_to_hsv_deg(rgb_arr: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Vectorized RGB [0..255] -> (hue_deg [0..360), sat [0..1], val [0..1]).
    Works on both (N, 3) and (H, W, 3) float32 arrays.
    """
    r = rgb_arr[..., 0]
    g = rgb_arr[..., 1]
    b = rgb_arr[..., 2]
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    span = mx - mn
    sat = span / np.maximum(1.0, mx)
    val = mx / 255.0

    hue = np.zeros_like(mx, dtype=np.float32)
    valid = span > 1e-3
    safe_span = np.where(valid, span, 1.0)

    m_r = valid & (mx == r)
    m_g = valid & (~m_r) & (mx == g)
    m_b = valid & (~m_r) & (~m_g)

    hue = np.where(m_r, (60.0 * ((g - b) / safe_span)) % 360.0, hue)
    hue = np.where(m_g, 60.0 * ((b - r) / safe_span) + 120.0, hue)
    hue = np.where(m_b, 60.0 * ((r - g) / safe_span) + 240.0, hue)
    return hue, sat, val


def _boost_spool_vividness(rgb: Tuple[int, int, int], rank_idx: int, total_k: int) -> Tuple[int, int, int]:
    """
    Calibrates a cluster RGB into a clean, vivid 3D filament spool color matching real HueForge prints
    across all 5 chromatic families (Warm Red/Orange/Peach, Gold/Yellow, Green/Emerald, Cool Blue/Cyan, Purple/Mauve):
    - Rank 0 (bottom base): deep black / midnight shadow.
    - Rank K-1 (top highlight): pure crisp white / ivory.
    """
    r, g, b = [c / 255.0 for c in rgb]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    h_deg = h * 360.0

    if rank_idx == 0:
        v = min(v, 0.08)
        s = min(s, 0.35)
    elif rank_idx == total_k - 1:
        v = max(v, 0.99)
        s = min(s * 0.10, 0.04)
    else:
        if s < 0.14:
            # Neutral Silver / Mid-Grey filament (never boost to >0.68 near-white so it never duplicates Top White!)
            s = s * 0.50
            v = float(np.clip(v * 0.95, 0.44, 0.66))
        elif (40.0 <= h_deg < 65.0) or (33.0 <= h_deg < 40.0 and s >= 0.46 and v >= 0.62):
            # Gold / Yellow / Champagne-Cream family (horns, Super Saiyan aura & hair, dragon belly, Golden Armor):
            # Preserve distinction between Rich Amber-Gold (lower gold band: v < 0.68), Vivid Yellow-Gold, and Pale Champagne-Gold (upper armor band)!
            if v < 0.68:
                # Rich Amber-Gold / Metallic Gold (armor bevels, golden wings & warm aura)
                h = float(np.clip(h, 40.5 / 360.0, 43.5 / 360.0))
                s = float(np.clip(s * 1.18 + 0.06, 0.82, 0.92))
                v = float(np.clip(v * 1.24 + 0.04, 0.80, 0.85))
            elif v >= 0.84 and s < 0.50:
                # Pale Champagne-Gold / Ivory-Yellow (bright metallic armor plates)
                h = float(np.clip(max(h, 48.0 / 360.0), 48.0 / 360.0, 54.0 / 360.0))
                s = float(np.clip(s * 1.05 + 0.04, 0.40, 0.52))
                v = float(np.clip(v * 1.08 + 0.04, 0.96, 0.99))
            else:
                # Standard Vivid Golden-Yellow
                h = float(np.clip(max(h, 43.0 / 360.0), 43.0 / 360.0, 54.0 / 360.0))
                s = float(np.clip(s * 1.15 + 0.05, 0.58, 0.88))
                v = float(np.clip(v * 1.10 + 0.05, 0.92, 0.98))
        elif h_deg < 40.0 or h_deg >= 332.0:
            # Warm family: distinguish 3 physical sub-types:
            # 1) Warm Peach Skin / Flesh tone (pastel tint: high G/R, significant B/R >= 0.36, moderate sat < 0.52)
            # 2) Vibrant Orange / Crimson Red (pure spectral hue: high V >= 0.56, high sat >= 0.48, low B/R)
            # 3) Deep Terracotta / Dark Brown (shadow warm: V < 0.56)
            if v >= 0.58 and g >= 0.52 * r and b >= 0.36 * r and s < 0.52 and (r - g) < 0.38:
                # Warm Peach Skin / Flesh tone
                h = 25.0 / 360.0
                s = float(np.clip(max(s * 1.25, 0.36), 0.36, 0.52))
                v = float(np.clip(v * 1.08 + 0.04, 0.88, 0.97))
            elif v >= 0.56 and s >= 0.48:
                # Vibrant Orange / Fiery Coral / Crimson Red (Goku's Orange Gi/Pants, Red Sun)
                if h_deg >= 332.0:
                    h = 8.0 / 360.0
                elif h_deg >= 13.0:
                    h = float(np.clip(h, 16.0 / 360.0, 24.0 / 360.0))
                s = float(np.clip(s * 1.18 + 0.06, 0.76, 0.92))
                v = float(np.clip(v * 1.10 + 0.05, 0.82, 0.94))
            else:
                # Deep Terracotta / Dark Brown (Shenron scales, dark chest/cape shadows)
                if h_deg >= 332.0:
                    h = 8.0 / 360.0
                s = float(np.clip(s * 1.22 + 0.06, 0.64, 0.88))
                v = float(np.clip(v * 1.06 + 0.03, 0.48, 0.68))
        elif 65.0 <= h_deg < 168.0:
            # Green / Lime / Emerald family
            h = float(np.clip(h, 82.0 / 360.0, 145.0 / 360.0))
            s = float(np.clip(s * 1.22 + 0.06, 0.58, 0.88))
            v = float(np.clip(v * 1.08 + 0.04, 0.36, 0.86))
        elif 252.0 <= h_deg < 332.0:
            # Purple / Mauve / Violet / Magenta family
            h = float(np.clip(h, 268.0 / 360.0, 316.0 / 360.0))
            s = float(np.clip(s * 1.25 + 0.08, 0.62, 0.90))
            v = float(np.clip(v * 1.10 + 0.05, 0.58, 0.92))
        else:
            # Cool family (Teal-Cyan / Sky Blue / Royal Blue / Deep Navy: 168°..252°)
            s = float(np.clip(s * 1.28 + 0.08, 0.58, 0.92))
            if h_deg < 208.0:
                # Teal / Cyan / Turquoise (belts, lightning, energy sparks, cyan aura): ensure luminous cyan visibility
                if v >= 0.72:
                    h = float(min(h, 193.0 / 360.0))
                v = float(np.clip(v * 1.24 + 0.08, 0.60, 0.93))
            else:
                # Navy / Royal / Sky Blue: ensure dark blue belts/wristbands boost to a visible Navy/Royal Blue (>= 0.46)
                v = float(np.clip(v * 1.25 + 0.12, 0.46, 0.93))

    nr, ng, nb = colorsys.hsv_to_rgb(h, s, v)
    return (
        int(np.clip(round(nr * 255), 0, 255)),
        int(np.clip(round(ng * 255), 0, 255)),
        int(np.clip(round(nb * 255), 0, 255)),
    )


def _vivid_family_representative(fp: np.ndarray, luma_weights: np.ndarray, is_warm_bright: bool = False) -> np.ndarray:
    """
    Extracts a clean filament color from a pixel cluster `fp`:
    - For standard bands: focuses on the top 45% most chromatic pixels to avoid muddy grey averages.
    - For the upper/bright band of the Warm family (`is_warm_bright=True`): prioritizes Golden Peach / Skin / Bright Coral
      pixels (where Green channel is strong: G >= 0.52 * R) over dark red/magenta edges!
    """
    if len(fp) == 0:
        return np.array([128.0, 128.0, 128.0], dtype=np.float32)
    if len(fp) < 8:
        return np.median(fp, axis=0)

    if is_warm_bright:
        r_c, g_c, b_c = fp[:, 0], fp[:, 1], fp[:, 2]
        max_w = np.maximum(1.0, np.max(fp, axis=1))
        min_w = np.min(fp, axis=1)
        sat_w = (max_w - min_w) / max_w
        peach_gold_mask = (g_c >= 0.52 * r_c) & (b_c >= 0.32 * r_c) & ((r_c - b_c) >= 12.0) & (sat_w < 0.64)
        if np.sum(peach_gold_mask) >= max(4, int(0.06 * len(fp))):
            sub = fp[peach_gold_mask]
            sub_l = sub @ luma_weights
            hi_l = sub[sub_l >= np.percentile(sub_l, 50.0)]
            med_skin = np.median(hi_l if len(hi_l) >= 4 else sub, axis=0).astype(np.float32)
            # Ensure character skin spool is a clean bright peach/tan (never dark muddy orange)
            if float(med_skin @ luma_weights) < 158.0:
                boost = min(1.32, 165.0 / max(60.0, float(med_skin @ luma_weights)))
                med_skin = np.clip(med_skin * boost + np.array([10.0, 12.0, 14.0], dtype=np.float32), 0.0, 252.0)
            return med_skin

    max_c = np.maximum(1.0, np.max(fp, axis=1))
    min_c = np.min(fp, axis=1)
    sat = (max_c - min_c) / max_c
    thresh = np.percentile(sat, 55.0)
    vivid_sub = fp[sat >= thresh]
    if len(vivid_sub) >= 4:
        return np.median(vivid_sub, axis=0)
    return np.median(fp, axis=0)


def analyze_image_and_propose_palettes(
    img_rgb: np.ndarray,
    base_thickness_mm: float = 0.88,
    relief_height_mm: float = 1.60,
    first_layer_mm: float = 0.16,
    layer_height_mm: float = 0.08,
    vivid_boost: bool = True,
) -> Tuple[int, Dict[int, List[Dict[str, Any]]], Dict[int, List[Dict[str, Any]]]]:
    """
    Contiguous 5-Family HSV HueForge Palette Extractor for K in [2..8]:
    Separates image midtones into 5 true chromatic families + neutral silver:
      - `warm`   (Hue 330°..360° & 0°..43°: Crimson, Red, Terracotta, Coral-Orange, Warm Peach Skin)
      - `gold`   (Hue 43°..70°: Bright Yellow, Gold horns/emblems, Warm Cream)
      - `green`  (Hue 70°..168°: Forest Green, Emerald, Lime)
      - `cool`   (Hue 168°..252°: Teal-Cyan, Ice Blue, Royal Blue, Deep Navy)
      - `purple` (Hue 252°..330°: Violet, Mauve, Purple, Magenta aura)
      - `silver` (Low saturation S < 0.20: Metallic Silver / Grey hair & steel)
    Automatically recommends 7 or 8 colors (Double CFS) when 3+ families or a strong Purple/Mauve
    aura is present alongside Blue and Warm tones!
    """
    h, w, _ = img_rgb.shape
    scale = min(1.0, 220.0 / max(h, w))
    small_w = max(24, int(round(w * scale)))
    small_h = max(24, int(round(h * scale)))
    small_img = Image.fromarray(img_rgb).resize((small_w, small_h), Image.Resampling.BILINEAR)
    arr_2d = np.asarray(small_img, dtype=np.float32)

    # Weight the central 66% subject region 2x higher than outer borders
    y0, y1 = int(small_h * 0.17), int(small_h * 0.83)
    x0, x1 = int(small_w * 0.17), int(small_w * 0.83)
    center_patch = arr_2d[y0:y1, x0:x1].reshape(-1, 3)
    all_patch = arr_2d.reshape(-1, 3)
    pixels = np.vstack([all_patch, center_patch, center_patch])

    luma_weights = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    pixel_lumas = pixels @ luma_weights

    dark_anchor = np.array([10.0, 12.0, 18.0], dtype=np.float32)
    bright_anchor = np.array([252.0, 253.0, 255.0], dtype=np.float32)

    all_span = np.max(pixels, axis=1) - np.min(pixels, axis=1)
    mid_mask = ((pixel_lumas > 24.0) | ((pixel_lumas > 11.0) & (all_span >= 8.0))) & (pixel_lumas < 236.0)
    mid_pixels = pixels[mid_mask] if np.sum(mid_mask) >= 30 else pixels
    mid_lumas = mid_pixels @ luma_weights

    hue_deg, sat_hsv, _ = _rgb_array_to_hsv_deg(mid_pixels)
    chroma_span = np.max(mid_pixels, axis=1) - np.min(mid_pixels, axis=1)
    is_chromatic = ((sat_hsv >= 0.20) & (chroma_span > 14.0)) | ((sat_hsv >= 0.26) & (chroma_span >= 8.0))
    is_warm_chromatic = (sat_hsv >= 0.13) & (chroma_span >= 14.0)
    # For the Cool family (168°..252°), require dark pixels (mid_lumas < 75) to have true navy/cyan chroma (sat>=0.40, span>=16)
    # so cool-tinted charcoal black hair ([34, 41, 49], sat=0.28, span=15) is never mistaken for Blue, and route low-sat overcast sky (luma>=120, sat<0.26) to Silver!
    is_cool_chromatic = is_chromatic & (
        ((mid_lumas >= 75.0) & ((mid_lumas < 120.0) | (sat_hsv >= 0.26)))
        | ((mid_lumas < 75.0) & (sat_hsv >= 0.40) & (chroma_span >= 16.0))
    )

    # Neutral Silver / Mid-Grey family: includes neutral mid-grey (65..185) and desaturated overcast sky/cloud tones (110..215, sat<0.26)
    fam_silver = (
        ((~is_chromatic) & (~is_warm_chromatic) & (mid_lumas >= 65.0) & (mid_lumas <= 185.0))
        | ((hue_deg >= 168.0) & (hue_deg < 252.0) & (mid_lumas >= 110.0) & (mid_lumas <= 215.0) & (sat_hsv < 0.26))
    )
    fam_gold = is_chromatic & (
        ((hue_deg >= 40.0) & (hue_deg < 65.0) & (mid_lumas >= 90.0))
        | ((hue_deg >= 33.0) & (hue_deg < 40.0) & (sat_hsv >= 0.46) & (mid_lumas >= 110.0))
    )
    fam_warm = is_warm_chromatic & ((hue_deg < 40.0) | (hue_deg >= 332.0)) & (~fam_gold)
    fam_green = is_chromatic & (hue_deg >= 65.0) & (hue_deg < 168.0)
    fam_cool = is_cool_chromatic & (hue_deg >= 168.0) & (hue_deg < 252.0)
    fam_purple = is_chromatic & (hue_deg >= 252.0) & (hue_deg < 332.0)

    total_mid = max(1, len(mid_pixels))
    total_chroma_mid = max(1, int(np.sum(is_chromatic | is_warm_chromatic)))
    # Measure chromatic families against effective chromatic midtones so a large grey/white background never dilutes accent colors (like Goku's blue belt!)
    eff_mid = min(total_mid, max(1, int(total_chroma_mid * 1.65)))

    # Chromatic Adaptation for Cyan/Blue-Cast Illustrations (e.g. Goku standing inside a strong Cyan/Blue aura):
    # When >65% of midtones are Cool/Cyan and <2% are unshifted Warm, check for warm-balanced subject pixels
    # (skin, chest, abs, warm-shaded gi where R >= G - 2.5 and B - R <= 55.0) illuminated by the blue cast!
    if np.sum(fam_cool) >= 0.65 * total_mid and np.sum(fam_warm) < 0.02 * total_mid:
        r_m, g_m, b_m = mid_pixels[:, 0], mid_pixels[:, 1], mid_pixels[:, 2]
        blue_cast_warm = (
            (r_m >= g_m - 2.5)
            & ((b_m - r_m) <= 55.0)
            & (mid_lumas >= 35.0)
            & (mid_lumas <= 215.0)
            & (sat_hsv >= 0.08)
        )
        if np.sum(blue_cast_warm) >= 0.022 * total_mid:
            fam_cool = fam_cool & (~blue_cast_warm)
            fam_purple = fam_purple & (~blue_cast_warm)
            recovered_warm = np.stack([
                np.clip(r_m[blue_cast_warm] * 1.28 + 18.0, 0.0, 255.0),
                np.clip(g_m[blue_cast_warm] * 1.08 + 6.0, 0.0, 255.0),
                np.clip(b_m[blue_cast_warm] * 0.68 - 12.0, 0.0, 255.0),
            ], axis=-1).astype(np.float32)
        else:
            recovered_warm = None
    else:
        recovered_warm = None

    raw_families = {
        "cool": mid_pixels[fam_cool],
        "warm": recovered_warm if recovered_warm is not None else mid_pixels[fam_warm],
        "purple": mid_pixels[fam_purple],
        "gold": mid_pixels[fam_gold],
        "green": mid_pixels[fam_green],
    }

    # Self-Adapting Bidirectional Green / Cool Continuum Merge across the 168° boundary:
    # When both `green` and `cool` are present, check if they are two distinct visual objects
    # (e.g. Green Rocks + Royal Blue Aura with RGB distance ~76 and ΔHue ~70°) or a single continuous
    # Emerald-Teal / Foliage gradient straddling 168° (RGB distance < 52 and ΔHue < 38°).
    # Merge the smaller side into the dominant side so neither creates a spurious split!
    if len(raw_families["green"]) > 0 and len(raw_families["cool"]) > 0:
        grn_med_rgb = np.median(raw_families["green"], axis=0)
        cool_med_rgb = np.median(raw_families["cool"], axis=0)
        dist_gc_rgb = float(np.linalg.norm(grn_med_rgb - cool_med_rgb))
        grn_h_arr, _, _ = _rgb_array_to_hsv_deg(raw_families["green"])
        cool_h_arr, _, _ = _rgb_array_to_hsv_deg(raw_families["cool"])
        delta_h_gc = float(np.median(cool_h_arr)) - float(np.median(grn_h_arr))
        if dist_gc_rgb < 52.0 and delta_h_gc < 38.0:
            if len(raw_families["cool"]) >= len(raw_families["green"]):
                raw_families["cool"] = np.vstack([raw_families["cool"], raw_families["green"]])
                raw_families["green"] = np.empty((0, 3), dtype=np.float32)
            else:
                raw_families["green"] = np.vstack([raw_families["green"], raw_families["cool"]])
                raw_families["cool"] = np.empty((0, 3), dtype=np.float32)

    # Overcast Slate-Grey vs Vivid Blue Separation:
    # When `raw_families["cool"]` consists exclusively of muted overcast sky/foliage shadows (75th pct saturation < 0.36
    # and 75th pct chroma span < 36.0, as in Naito Mudano's overcast clouds), merge it into `silver` rather than creating a fake Blue spool!
    silver_pixels = mid_pixels[fam_silver]
    if len(raw_families["cool"]) > 0:
        _, c_sat_arr, _ = _rgb_array_to_hsv_deg(raw_families["cool"])
        c_span_arr = np.max(raw_families["cool"], axis=1) - np.min(raw_families["cool"], axis=1)
        if float(np.percentile(c_sat_arr, 75.0)) < 0.36 and float(np.percentile(c_span_arr, 75.0)) < 36.0:
            silver_pixels = np.vstack([silver_pixels, raw_families["cool"]]) if len(silver_pixels) > 0 else raw_families["cool"]
            raw_families["cool"] = np.empty((0, 3), dtype=np.float32)

    # Filter out spurious minor Green/Purple halo noise (e.g. <3.5% yellow-green aura around a Golden Dragon or dark space shadow noise):
    gold_ratio = len(raw_families["gold"]) / float(total_mid)
    warm_ratio = len(raw_families["warm"]) / float(total_mid)

    def _is_valid_family(name: str, fp: np.ndarray, is_extended: bool) -> bool:
        if len(fp) == 0:
            return False
        if name == "purple":
            if not is_extended:
                return len(fp) >= 0.085 * total_mid
            return len(fp) >= 0.042 * total_mid or (
                len(fp) >= 0.024 * total_mid and float(np.median(fp @ luma_weights)) >= 95.0
            )
        if name == "green":
            min_grn = 0.018 * total_mid if is_extended else 0.025 * total_mid
            if len(fp) < min_grn:
                return False
            # When Gold is strongly present (>=10%), reject yellow-green aura glow (median Hue < 88°)
            if gold_ratio >= 0.10 and len(fp) < 0.045 * total_mid:
                gh, _, _ = _rgb_array_to_hsv_deg(fp)
                if float(np.median(gh)) < 88.0:
                    return False
            return True
        if name == "cool":
            # Allow down to 1.8% for a blue belt/wristband accent (like Goku Red Sun or Goku SSJ3 Shenron)
            return len(fp) >= min(0.032 * total_mid, 0.028 * eff_mid) or len(fp) >= 0.018 * total_mid
        if name == "warm":
            return len(fp) >= min(0.032 * total_mid, 0.028 * eff_mid) or len(fp) >= 0.018 * total_mid
        # gold
        return len(fp) >= (0.025 * total_mid if is_extended else 0.032 * total_mid)

    primary_active = [
        (name, raw_families[name])
        for name in ("cool", "warm", "purple", "gold", "green")
        if _is_valid_family(name, raw_families[name], is_extended=False)
    ]
    primary_active.sort(key=lambda item: len(item[1]), reverse=True)

    extended_active = [
        (name, raw_families[name])
        for name in ("cool", "warm", "purple", "gold", "green")
        if _is_valid_family(name, raw_families[name], is_extended=True)
    ]
    extended_active.sort(key=lambda item: len(item[1]), reverse=True)

    has_silver = len(silver_pixels) >= 0.08 * total_mid
    warm_fp_all = raw_families["warm"]
    warm_has_skin = False
    warm_has_vivid_orange = False
    warm_has_dark_brown = False
    if len(warm_fp_all) > 0:
        wp_l = warm_fp_all @ luma_weights
        w_max = np.maximum(1.0, np.max(warm_fp_all, axis=1))
        w_min = np.min(warm_fp_all, axis=1)
        w_sat = (w_max - w_min) / w_max
        w_hue, _, _ = _rgb_array_to_hsv_deg(warm_fp_all)
        w_skin_mask = (
            ((w_hue < 33.5) | (w_hue >= 332.0))
            & (warm_fp_all[:, 1] >= 0.52 * warm_fp_all[:, 0])
            & (warm_fp_all[:, 2] >= 0.32 * warm_fp_all[:, 0])
            & (w_sat < 0.62)
            & (wp_l >= 95.0)
        )
        warm_has_skin = (
            float(np.mean(w_skin_mask)) >= 0.06
            or int(np.sum(w_skin_mask)) >= max(10, int(0.010 * total_mid))
        )
        warm_has_vivid_orange = float(np.mean((~w_skin_mask) & (w_sat >= 0.52) & (wp_l >= 70.0))) >= 0.12
        warm_has_dark_brown = float(np.mean((~w_skin_mask) & (wp_l < 92.0))) >= 0.16
    warm_is_bimodal = (
        warm_has_skin
        and (warm_has_vivid_orange or warm_has_dark_brown)
        and (recovered_warm is None)
    )
    warm_is_trimodal = (
        warm_has_skin
        and warm_has_vivid_orange
        and warm_has_dark_brown
        and (warm_ratio >= 0.35)
        and (recovered_warm is None)
    )

    palettes_by_k: Dict[int, List[Dict[str, Any]]] = {}
    stock_palettes_by_k: Dict[int, List[Dict[str, Any]]] = {}

    for k in range(2, 9):
        if k == 2:
            sorted_centroids = np.vstack([dark_anchor, bright_anchor])
        else:
            m_slots = k - 2
            active_for_k = list(extended_active if k >= 7 else primary_active)
            use_families = list(active_for_k)
            if has_silver and (
                len(use_families) <= 1
                or k >= 8
                or (len(use_families) == 2 and (not warm_has_skin or len(silver_pixels) >= 0.10 * total_mid) and k >= 5)
            ):
                use_families.append(("silver", silver_pixels))

            if use_families:
                alloc = {name: 0 for name, _ in use_families}
                for idx_f in range(min(m_slots, len(use_families))):
                    alloc[use_families[idx_f][0]] += 1
                rem = m_slots - sum(alloc.values())

                # Allocate remaining slots:
                # 1) If `warm` is bimodal (contains BOTH Vibrant Orange/Red/Brown AND Peach Skin, like Goku's Orange pants + Peach face),
                #    give `warm` its 2nd slot FIRST before `cool` gets a 2nd slot (since Peach Skin cannot optically produce Orange-Red!).
                # 2) If `warm` is trimodal (contains Dark Brown Shenron scales + Vibrant Orange Gi + Peach Skin fist/face and >35% of image),
                #    allow `warm` to receive a 3rd slot when slots remain!
                while rem > 0:
                    if alloc.get("warm", 0) == 1 and warm_is_bimodal and len(warm_fp_all) >= (0.014 if k >= 7 else 0.042) * total_mid:
                        best_f = "warm"
                    elif alloc.get("warm", 0) == 2 and warm_is_trimodal and k >= 7:
                        best_f = "warm"
                    else:
                        under_two_cw = [
                            (n, fp) for (n, fp) in use_families
                            if n in ("cool", "warm")
                            and alloc[n] == 1
                            and len(fp) >= 0.045 * total_mid
                            and (n != "warm" or warm_has_skin or len(use_families) == 1)
                        ]
                        under_two_any = [
                            (n, fp) for (n, fp) in use_families
                            if n != "silver"
                            and alloc[n] == 1
                            and len(fp) >= 0.055 * total_mid
                            and (n != "warm" or warm_has_skin or len(use_families) == 1)
                        ]
                        if under_two_cw:
                            best_f = under_two_cw[0][0]
                        elif under_two_any:
                            best_f = under_two_any[0][0]
                        else:
                            eligible_f = [
                                (n, fp) for (n, fp) in use_families
                                if not (n == "warm" and not warm_is_trimodal and alloc[n] >= (2 if warm_has_skin or len(use_families) == 1 else 1))
                                and not (n == "silver" and alloc[n] >= 1 and len(use_families) > 1)
                            ]
                            if not eligible_f:
                                eligible_f = use_families
                            best_f = max(eligible_f, key=lambda x: len(x[1]) / (alloc[x[0]] + 0.85))[0]
                    alloc[best_f] += 1
                    rem -= 1

                # Physical HueForge Family Ordering:
                fam_dict = dict(use_families)
                cool_total = len(fam_dict.get("cool", [])) + len(fam_dict.get("purple", []))
                warm_total = len(fam_dict.get("warm", [])) + len(fam_dict.get("gold", []))
                has_warm_highlight = (alloc.get("gold", 0) > 0) or (alloc.get("warm", 0) >= 2 and warm_has_skin)
                if warm_total >= 1.05 * cool_total and has_warm_highlight:
                    family_order = ["cool", "purple", "green", "warm", "gold", "silver"]
                else:
                    family_order = ["warm", "gold", "green", "purple", "cool", "silver"]

                ordered_seeds: List[np.ndarray] = []

                for f_name in family_order:
                    if f_name not in alloc or alloc[f_name] <= 0:
                        continue
                    fp = fam_dict[f_name]
                    count_s = alloc[f_name]
                    fp_lumas = fp @ luma_weights

                    if f_name == "silver":
                        # Neutral Silver / Slate Grey spool: keep saturation < 0.12 so `_boost_spool_vividness` never turns it Blue!
                        med_silv = np.median(fp, axis=0).astype(np.float32)
                        mean_c = float(np.mean(med_silv))
                        med_silv = 0.70 * np.array([mean_c, mean_c, mean_c], dtype=np.float32) + 0.30 * med_silv
                        ordered_seeds.append(med_silv)
                    elif count_s == 1:
                        # If Warm has only 1 slot (e.g. Shiryu face/skin or Goku Blue Aura skin), check if most Warm pixels
                        # are bright peach skin rather than dark red/orange, or if Warm is a character face (<14% of midtones) with skin
                        is_wb = False
                        if f_name == "warm" and len(fp) > 0:
                            f_hue, _, _ = _rgb_array_to_hsv_deg(fp)
                            f_max = np.maximum(1.0, np.max(fp, axis=1))
                            f_min = np.min(fp, axis=1)
                            f_sat = (f_max - f_min) / f_max
                            skin_ratio = float(np.mean(
                                ((f_hue < 33.5) | (f_hue >= 332.0))
                                & (fp[:, 1] >= 0.52 * fp[:, 0])
                                & (fp[:, 2] >= 0.32 * fp[:, 0])
                                & (f_sat < 0.62)
                                & (fp_lumas >= 95.0)
                            ))
                            is_wb = (
                                (skin_ratio >= 0.25)
                                or (warm_has_skin and len(fp) < 0.14 * total_mid)
                                or (recovered_warm is not None)
                            )
                        c_seed = _vivid_family_representative(fp, luma_weights, is_warm_bright=is_wb)
                        ordered_seeds.append(c_seed)
                    elif f_name == "warm" and warm_has_skin and count_s in (2, 3):
                        # Dedicated physical separation of Warm sub-types:
                        # - count_s == 2: [Vivid Orange/Red/Brown non-skin, Warm Peach Skin]
                        # - count_s == 3: [Dark Brown/Terracotta, Vibrant Orange/Red, Warm Peach Skin]
                        f_max = np.maximum(1.0, np.max(fp, axis=1))
                        f_min = np.min(fp, axis=1)
                        f_sat = (f_max - f_min) / f_max
                        f_skin = (
                            (fp[:, 1] >= 0.52 * fp[:, 0])
                            & (fp[:, 2] >= 0.36 * fp[:, 0])
                            & (f_sat < 0.54)
                            & (fp_lumas >= 100.0)
                        )
                        non_skin = fp[~f_skin] if np.sum(~f_skin) >= 8 else fp
                        skin_sub = fp[f_skin] if np.sum(f_skin) >= 6 else fp
                        if count_s == 2:
                            seed_lo = _vivid_family_representative(non_skin, luma_weights, is_warm_bright=False)
                            seed_hi = _vivid_family_representative(skin_sub, luma_weights, is_warm_bright=True)
                            fam_arr = np.vstack([seed_lo, seed_hi])
                        else:
                            ns_l = non_skin @ luma_weights
                            ns_sat = (np.max(non_skin, axis=1) - np.min(non_skin, axis=1)) / np.maximum(1.0, np.max(non_skin, axis=1))
                            dark_mask = ns_l < np.percentile(ns_l, 52.0)
                            vivid_orange_mask = (ns_l >= np.percentile(ns_l, 48.0)) & (ns_sat >= 0.50)
                            dark_sub = non_skin[dark_mask] if np.any(dark_mask) else non_skin
                            orange_sub = non_skin[vivid_orange_mask] if np.any(vivid_orange_mask) else non_skin
                            seed_dark = np.median(dark_sub, axis=0)
                            seed_orange = _vivid_family_representative(orange_sub, luma_weights, is_warm_bright=False)
                            seed_skin = _vivid_family_representative(skin_sub, luma_weights, is_warm_bright=True)
                            fam_arr = np.vstack([seed_dark, seed_orange, seed_skin])
                        fam_l = fam_arr @ luma_weights
                        fam_arr = fam_arr[np.argsort(fam_l)]
                        for row_s in fam_arr:
                            ordered_seeds.append(row_s)
                    else:
                        l_min = float(np.percentile(fp_lumas, 5.0))
                        l_max = float(np.percentile(fp_lumas, 95.0))
                        edges = np.linspace(l_min, l_max, count_s + 1)
                        fam_seeds = []
                        for b_idx in range(count_s):
                            lo, hi = edges[b_idx], edges[b_idx + 1]
                            band = (fp_lumas >= lo - 2.0) & (fp_lumas <= hi + 2.0)
                            is_wb = (f_name == "warm") and (b_idx == count_s - 1) and warm_has_skin
                            if np.any(band):
                                sub_b = fp[band]
                                if f_name == "cool" and b_idx == count_s - 1 and hi >= 165.0:
                                    # For the brightest Cool band (e.g. Ice-Cyan aura), sample the upper half of luminance
                                    sub_bl = sub_b @ luma_weights
                                    hi_sub = sub_b[sub_bl >= np.percentile(sub_bl, 55.0)]
                                    fam_seeds.append(np.median(hi_sub if len(hi_sub) >= 4 else sub_b, axis=0))
                                elif f_name == "gold" and count_s >= 2:
                                    if b_idx == 0:
                                        # Lower Gold band: Rich Amber-Gold / Metallic Gold bevels (Hue ~41.0°, Sat ~0.88, Val ~0.62 -> boosts to #D68E12)
                                        r_lo, g_lo, b_lo = colorsys.hsv_to_rgb(41.0 / 360.0, 0.88, 0.62)
                                        fam_seeds.append(np.array([r_lo * 255.0, g_lo * 255.0, b_lo * 255.0], dtype=np.float32))
                                    elif b_idx == count_s - 1:
                                        # Upper Gold band: Pale Champagne-Gold / Ivory-Yellow armor plates (Hue ~51°, Sat ~0.46, Val ~0.98 -> #FCE685)
                                        r_hi, g_hi, b_hi = colorsys.hsv_to_rgb(51.0 / 360.0, 0.46, 0.98)
                                        fam_seeds.append(np.array([r_hi * 255.0, g_hi * 255.0, b_hi * 255.0], dtype=np.float32))
                                    else:
                                        # Middle Gold band (when count_s == 3): Vivid Solar Gold (Hue ~46°, Sat ~0.82, Val ~0.94 -> #F0BA2B)
                                        r_mid, g_mid, b_mid = colorsys.hsv_to_rgb(46.0 / 360.0, 0.82, 0.94)
                                        fam_seeds.append(np.array([r_mid * 255.0, g_mid * 255.0, b_mid * 255.0], dtype=np.float32))
                                else:
                                    fam_seeds.append(_vivid_family_representative(sub_b, luma_weights, is_warm_bright=is_wb))
                            else:
                                target_l = 0.5 * (lo + hi)
                                closest_idx = int(np.argmin(np.abs(fp_lumas - target_l)))
                                fam_seeds.append(fp[closest_idx])
                        fam_arr = np.vstack(fam_seeds)
                        fam_l = fam_arr @ luma_weights
                        fam_arr = fam_arr[np.argsort(fam_l)]
                        if len(fam_arr) >= 2 and float((fam_arr[-1] - fam_arr[0]) @ luma_weights) < 34.0:
                            fam_arr[0] = np.clip(fam_arr[0] * 0.72, 12.0, 255.0)
                            fam_arr[-1] = np.clip(fam_arr[-1] * 1.32 + 16.0, 0.0, 245.0)
                        for row_s in fam_arr:
                            ordered_seeds.append(row_s)

                sorted_centroids = np.vstack([dark_anchor] + ordered_seeds + [bright_anchor]).astype(np.float32)
            else:
                edges = np.percentile(mid_lumas, np.linspace(0, 100, m_slots + 1))
                seeds = []
                for b_idx in range(m_slots):
                    lo, hi = edges[b_idx], edges[b_idx + 1]
                    band = (mid_lumas >= lo) & (mid_lumas <= hi)
                    sub = mid_pixels[band] if np.any(band) else mid_pixels
                    seeds.append(np.median(sub, axis=0))
                centroids = np.vstack([dark_anchor] + seeds + [bright_anchor]).astype(np.float32)
                c_lumas = centroids @ luma_weights
                sorted_centroids = centroids[np.argsort(c_lumas)]

        if vivid_boost:
            boosted = []
            for idx_c, c_rgb in enumerate(sorted_centroids):
                raw_tuple = (int(c_rgb[0]), int(c_rgb[1]), int(c_rgb[2]))
                boosted.append(_boost_spool_vividness(raw_tuple, idx_c, k))
            sorted_centroids = np.array(boosted, dtype=np.float32)
            # Universal Anti-Duplicate Spool Separator:
            # Guarantee that no two interior spools (adjacent or non-adjacent) in the palette are visually almost identical (RGB distance < 48)
            for i_c in range(1, k - 2):
                for j_c in range(i_c + 1, k - 1):
                    dist_pair = float(np.linalg.norm(sorted_centroids[j_c] - sorted_centroids[i_c]))
                    if dist_pair < 48.0:
                        c_lo = sorted_centroids[i_c] / 255.0
                        c_hi = sorted_centroids[j_c] / 255.0
                        h0, s0, v0 = colorsys.rgb_to_hsv(float(c_lo[0]), float(c_lo[1]), float(c_lo[2]))
                        h1, s1, v1 = colorsys.rgb_to_hsv(float(c_hi[0]), float(c_hi[1]), float(c_hi[2]))
                        v0_new = float(np.clip(min(v0, v1) * 0.76, 0.34, 0.80))
                        s0_new = float(np.clip(max(s0, s1) * 1.12, 0.64, 0.92))
                        v1_new = float(np.clip(max(v0, v1) * 1.12 + 0.06, 0.74, 0.98))
                        s1_new = float(np.clip(min(s0, s1) * 0.62, 0.38, 0.62))
                        if 35.0 <= h0 * 360.0 < 65.0:
                            h0 = 41.0 / 360.0
                            h1 = 51.0 / 360.0
                        r0, g0, b0 = colorsys.hsv_to_rgb(h0, s0_new, v0_new)
                        r1, g1, b1 = colorsys.hsv_to_rgb(h1, s1_new, v1_new)
                        sorted_centroids[i_c] = np.round(np.array([r0, g0, b0], dtype=np.float32) * 255.0)
                        sorted_centroids[j_c] = np.round(np.array([r1, g1, b1], dtype=np.float32) * 255.0)

        sorted_lumas = sorted_centroids @ luma_weights

        layers = _build_layer_schedule(
            sorted_centroids=sorted_centroids,
            sorted_lumas=sorted_lumas,
            base_thickness_mm=base_thickness_mm,
            relief_height_mm=relief_height_mm,
            first_layer_mm=first_layer_mm,
            layer_height_mm=layer_height_mm,
            custom_end_layer_nums=None,
        )
        palettes_by_k[k] = [layer.to_dict() for layer in layers]

        # Build the corresponding In-Stock Spool Matched Palette for K
        target_hexes = [layer.hex_color for layer in layers]
        matched_spools = match_palette_to_in_stock_spools(target_hexes)
        stock_layers = []
        for idx_l, base_dict in enumerate(palettes_by_k[k]):
            sp = matched_spools[idx_l] if idx_l < len(matched_spools) else None
            d_copy = dict(base_dict)
            if sp:
                sp_rgb = _hex_to_rgb(sp["hex_color"])
                d_copy["hex_color"] = sp["hex_color"]
                d_copy["rgb"] = sp_rgb
                d_copy["luminance"] = round(
                    (0.2126 * sp_rgb[0] + 0.7152 * sp_rgb[1] + 0.0722 * sp_rgb[2]) / 255.0, 3
                )
                d_copy["td_mm"] = float(sp.get("td_mm", 2.0))
                d_copy["spool_id"] = sp["id"]
                d_copy["spool_label"] = f"{sp['brand']} {sp['material']} — {sp['color_name']}"
            stock_layers.append(d_copy)
        stock_palettes_by_k[k] = stock_layers

    # Recommend K (up to 7-8 colors for Double CFS when 3+ chromatic families exist and need multi-tone ramps)
    if len(extended_active) >= 3:
        strong_fams = [n for (n, fp) in extended_active if len(fp) >= 0.06 * total_mid]
        recommended_k = 7 if (len(strong_fams) >= 2 or warm_is_bimodal) else 6
    elif len(primary_active) == 2:
        # Graphic / sumi-e poster with 1 main color + 1 accent color and no peach skin ramp (e.g. Goku Red Sun: Black, Red, Blue, White)
        if not warm_has_skin and len(primary_active[1][1]) < 0.08 * total_mid:
            recommended_k = 4
        else:
            recommended_k = 6
    else:
        recommended_k = 4

    return recommended_k, palettes_by_k, stock_palettes_by_k


def _build_layer_schedule(
    sorted_centroids: np.ndarray,
    sorted_lumas: np.ndarray,
    base_thickness_mm: float = 0.88,
    relief_height_mm: float = 1.60,
    first_layer_mm: float = 0.16,
    layer_height_mm: float = 0.08,
    custom_end_layer_nums: Optional[List[int]] = None,
    td_mm: float = 2.0,
) -> List[ColorLayerSpec]:
    """
    Maps K colors onto vertical Z heights and exact slicer layer numbers.
    Supports user-customized `custom_end_layer_nums` (interactive per-color layer sliders!).
    Uses non-uniform natural HueForge distribution by default (fewer layers for top white highlight,
    more layers for mid-tone color transitions).
    """
    k = len(sorted_centroids)
    total_relief_layers = max(k - 1, int(round(relief_height_mm / layer_height_mm)))
    base_layers_count = max(2, int(round((base_thickness_mm - first_layer_mm) / layer_height_mm)) + 1)
    total_layers = base_layers_count + total_relief_layers

    # Validate or compute end_layer_num for each of the K colors
    if custom_end_layer_nums and len(custom_end_layer_nums) == k:
        end_layers = list(custom_end_layer_nums)
        # Enforce strictly increasing layer numbers within [2 .. total_layers]
        end_layers[0] = max(2, min(end_layers[0], total_layers - (k - 1)))
        for i in range(1, k - 1):
            end_layers[i] = max(end_layers[i - 1] + 1, min(end_layers[i], total_layers - (k - 1 - i)))
        end_layers[k - 1] = max(end_layers[-2] + 1, total_layers)
    else:
        # Natural HueForge weighting: midtones get 1.3x layers, top highlight gets 0.65x layers (2-3 layers)
        end_layers = [base_layers_count]
        if k > 1:
            weights = []
            for idx in range(1, k):
                if idx == k - 1 and k >= 4:
                    weights.append(0.65)  # Crisp top white/highlight
                elif idx == 1:
                    weights.append(1.15)  # Deep shadow transition
                else:
                    weights.append(1.20)  # Rich midtone ramp
            w_sum = sum(weights)
            alloc = [max(1, int(round(total_relief_layers * (w / w_sum)))) for w in weights]
            # Adjust sum to match total_relief_layers
            diff = total_relief_layers - sum(alloc)
            alloc[0] = max(1, alloc[0] + diff)
            curr = base_layers_count
            for a in alloc:
                curr += a
                end_layers.append(curr)

    specs: List[ColorLayerSpec] = []
    prev_end_layer = 0
    prev_end_mm = 0.0

    for idx in range(k):
        start_l = prev_end_layer + 1
        end_l = end_layers[idx]
        end_z = round(first_layer_mm + (end_l - 1) * layer_height_mm, 2)
        start_z = 0.0 if idx == 0 else round(prev_end_mm + layer_height_mm, 2)

        rgb_i = (
            int(np.clip(sorted_centroids[idx][0], 0, 255)),
            int(np.clip(sorted_centroids[idx][1], 0, 255)),
            int(np.clip(sorted_centroids[idx][2], 0, 255)),
        )
        specs.append(
            ColorLayerSpec(
                layer_index=idx + 1,
                cfs_slot=CFS_SLOTS[idx % len(CFS_SLOTS)],
                hex_color=_rgb_to_hex(rgb_i),
                rgb=rgb_i,
                luminance=round(float(sorted_lumas[idx]) / 255.0, 3),
                start_mm=start_z,
                end_mm=end_z,
                start_layer_num=start_l,
                end_layer_num=end_l,
                td_mm=td_mm,
            )
        )
        prev_end_layer = end_l
        prev_end_mm = end_z

    return specs


def _get_reference_relief_specs(
    specs: List[ColorLayerSpec],
    first_layer_mm: float = 0.16,
    layer_height_mm: float = 0.08,
) -> List[ColorLayerSpec]:
    """
    Computes the default reference layer schedule (`custom_end_layer_nums=None`) for the same
    colors and total layer count as `specs`.
    Used by `compute_chroma_aware_pixel_z` so that when the user drags a layer swap slider
    (`Fin C.x` / `-1` / `+1`), the 3D relief heights `pixel_z` remain anchored to the reference
    topography while the filament swap heights (`specs[i].end_mm`) move across the relief,
    making every single layer change immediately visible on the 2D preview and 3D slice!
    """
    k = len(specs)
    if k <= 1:
        return specs
    total_layers = max(k + 1, int(specs[-1].end_layer_num))
    # Default base_layers_count is 10 (for standard 30-layer 2.48mm stack) or proportional when total_layers changes
    base_layers_count = 10 if total_layers == 30 else max(2, int(round(total_layers * (10.0 / 30.0))))
    total_relief_layers = max(k - 1, total_layers - base_layers_count)
    base_layers_count = max(2, total_layers - total_relief_layers)

    weights = []
    for idx in range(1, k):
        if idx == k - 1 and k >= 4:
            weights.append(0.65)
        elif idx == 1:
            weights.append(1.15)
        else:
            weights.append(1.20)
    w_sum = sum(weights)
    alloc = [max(1, int(round(total_relief_layers * (w / w_sum)))) for w in weights]
    diff = total_relief_layers - sum(alloc)
    alloc[0] = max(1, alloc[0] + diff)

    end_layers = [base_layers_count]
    curr = base_layers_count
    for a in alloc:
        curr += a
        end_layers.append(curr)

    ref_specs: List[ColorLayerSpec] = []
    prev_end_layer = 0
    prev_end_mm = 0.0
    for idx, sp in enumerate(specs):
        start_l = prev_end_layer + 1
        end_l = end_layers[idx]
        end_z = round(first_layer_mm + (end_l - 1) * layer_height_mm, 2)
        start_z = 0.0 if idx == 0 else round(prev_end_mm + layer_height_mm, 2)
        ref_specs.append(
            ColorLayerSpec(
                layer_index=sp.layer_index,
                cfs_slot=sp.cfs_slot,
                hex_color=sp.hex_color,
                rgb=sp.rgb,
                luminance=sp.luminance,
                start_mm=start_z,
                end_mm=end_z,
                start_layer_num=start_l,
                end_layer_num=end_l,
                td_mm=sp.td_mm,
                spool_id=sp.spool_id,
                spool_label=sp.spool_label,
            )
        )
        prev_end_layer = end_l
        prev_end_mm = end_z
    return ref_specs


# ---------------------------------------------------------------------------
# 2. Image Framing (Zoom / Pan) & Detail-Enhanced Luminance Map
# ---------------------------------------------------------------------------

def _strip_source_border_lines(img_rgb: np.ndarray) -> np.ndarray:
    """
    Removes thin 1px–8px white, grey, or black screenshot/frame borders along the 4 outer edges
    of `img_rgb` by replacing the outer margin with clean interior pixels.
    """
    h, w, _ = img_rgb.shape
    if h < 32 or w < 32:
        return img_rgb
    cleaned = img_rgb.copy()
    # Shave up to 1.8% (typically 4 to 10 pixels) on each side where screenshot/web borders sit
    mx = max(4, min(14, int(round(w * 0.018))))
    my = max(4, min(14, int(round(h * 0.015))))

    # Replace left & right outer margins with mirrored interior strip [mx : 2*mx]
    cleaned[:, :mx, :] = cleaned[:, 2 * mx - 1 : mx - 1 : -1, :]
    cleaned[:, w - mx :, :] = cleaned[:, w - mx - 1 : w - 2 * mx - 1 : -1, :]
    # Replace top & bottom outer margins with mirrored interior strip [my : 2*my]
    cleaned[:my, :, :] = cleaned[2 * my - 1 : my - 1 : -1, :, :]
    cleaned[h - my :, :, :] = cleaned[h - my - 1 : h - 2 * my - 1 : -1, :, :]
    return cleaned


def _filter_border_profile_intrusions(
    profile_rgb: np.ndarray,
    corner_bg_pixels: np.ndarray,
) -> np.ndarray:
    """
    Given a 1D border profile `profile_rgb` of shape `(N, 3)` along an image edge and
    `corner_bg_pixels` `(M, 3)` sampled from the image's corner background/aura,
    detects where a foreground subject limb (e.g., Goku's orange/brown knee or black ink outline)
    touches the edge and replaces that segment by smoothly interpolating the surrounding
    background & aura colors (e.g., blue space + purple/grey aura).
    """
    n = profile_rgb.shape[0]
    if n < 16 or corner_bg_pixels.shape[0] < 8:
        return profile_rgb

    # Characterize background chromaticity (R-B, R-G, G-B) from corners
    bg_rb = corner_bg_pixels[:, 0] - corner_bg_pixels[:, 2]
    bg_rg = corner_bg_pixels[:, 0] - corner_bg_pixels[:, 1]
    bg_gb = corner_bg_pixels[:, 1] - corner_bg_pixels[:, 2]
    med_rb = float(np.median(bg_rb))
    med_rg = float(np.median(bg_rg))
    med_gb = float(np.median(bg_gb))
    std_rb = max(14.0, float(np.percentile(np.abs(bg_rb - med_rb), 85)) * 1.4)
    std_rg = max(12.0, float(np.percentile(np.abs(bg_rg - med_rg), 85)) * 1.4)

    prof_rb = profile_rgb[:, 0] - profile_rgb[:, 2]
    prof_rg = profile_rgb[:, 0] - profile_rgb[:, 1]
    prof_gb = profile_rgb[:, 1] - profile_rgb[:, 2]

    # Detect foreground hue or bright-halo intrusion (e.g. warm orange/brown/skin or bright light burst on a dark cosmic background)
    bg_luma = corner_bg_pixels @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    med_luma = float(np.median(bg_luma))
    std_luma = max(18.0, float(np.percentile(np.abs(bg_luma - med_luma), 85)) * 1.4)
    prof_luma = profile_rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)

    is_intrusion = (np.abs(prof_rb - med_rb) > std_rb + 16.0) | (np.abs(prof_rg - med_rg) > std_rg + 14.0)
    if med_luma < 115.0:
        is_intrusion = is_intrusion | (prof_luma > med_luma + std_luma + 28.0)

    # If background is cool (B > R), any warm pixel (R > B + 10) is definitely foreground character
    if med_rb < -8.0:
        is_intrusion = is_intrusion | (prof_rb > 6.0)
    # If background is bright golden-yellow (G - B > 55), peach skin limbs or brown rocks (G - B < med_gb - 30) are intrusions
    elif med_gb > 55.0:
        is_intrusion = is_intrusion | (prof_gb < med_gb - 30.0)

    if not np.any(is_intrusion) or np.all(is_intrusion):
        return profile_rgb

    # Dilate intrusion mask along the profile by ~7% of length to also remove the black ink outline around the limb
    dilate_r = max(4, int(round(n * 0.065)))
    intrusion_f = gaussian_filter(is_intrusion.astype(np.float32), sigma=float(dilate_r) * 0.55) > 0.12
    if np.all(intrusion_f):
        return profile_rgb

    valid_idx = np.where(~intrusion_f)[0]
    all_idx = np.arange(n, dtype=np.float32)
    cleaned = profile_rgb.copy()
    for c in range(3):
        cleaned[:, c] = np.interp(all_idx, valid_idx.astype(np.float32), profile_rgb[valid_idx, c])

    return cleaned


def _crop_and_resample_image(
    img_rgb: np.ndarray,
    target_w: int,
    target_h: int,
    zoom: float = 1.0,
    offset_x_pct: float = 0.0,
    offset_y_pct: float = 0.0,
    fill_mode: FillMode = "smart_aura",
    return_void_mask: bool = False,
) -> Any:
    """
    Crops `img_rgb` according to the target aspect ratio (`target_w / target_h`),
    `zoom` (0.30 to 4.0), and pan offsets (`offset_x_pct`, `offset_y_pct` in [-100..+100]),
    then resamples cleanly to `(target_h, target_w, 3)`.
    Automatically strips 1-8px white/grey/black frame borders from the source image and
    fills out-of-bounds void areas according to `fill_mode`:
      - `"smart_aura"`  : Contextual background/aura extension (filters out character limbs on edges,
                          extends space + purple/blue aura, and synthesizes stars if cosmic).
      - `"edge_stretch"`: Smooth lateral extension of the cleaned border strip without mirroring.
      - `"mirror_blend"`: Seamless reflected mirror extension with border-frame removal & soft seam.
      - `"solid_edge"`  : Auto-detected dominant border background color.
      - `"none_preview"`: Renders void areas as a visual cyber checkerboard/hatched pattern.
    """
    clean_rgb = _strip_source_border_lines(img_rgb)
    src_h, src_w, _ = clean_rgb.shape
    target_aspect = float(target_w) / max(1.0, float(target_h))
    src_aspect = float(src_w) / max(1.0, float(src_h))

    if src_aspect > target_aspect:
        crop_h = float(src_h)
        crop_w = crop_h * target_aspect
    else:
        crop_w = float(src_w)
        crop_h = crop_w / target_aspect

    z = max(0.30, min(4.0, float(zoom)))
    crop_w /= z
    crop_h /= z

    pan_span_x = max(src_w * 0.65, abs(src_w - crop_w) * 0.55)
    pan_span_y = max(src_h * 0.65, abs(src_h - crop_h) * 0.55)

    cx = (src_w / 2.0) - (float(offset_x_pct) / 100.0) * pan_span_x
    cy = (src_h / 2.0) + (float(offset_y_pct) / 100.0) * pan_span_y

    left = cx - crop_w / 2.0
    top = cy - crop_h / 2.0
    right = cx + crop_w / 2.0
    bottom = cy + crop_h / 2.0

    xs_f = np.linspace(left + 0.5 * (crop_w / target_w), right - 0.5 * (crop_w / target_w), target_w, dtype=np.float32)
    ys_f = np.linspace(top + 0.5 * (crop_h / target_h), bottom - 0.5 * (crop_h / target_h), target_h, dtype=np.float32)

    # Inset valid bounds slightly (1.5%) so any residual edge artifact on the source file is treated as void & smoothly replaced
    inset_x = max(3.0, src_w * 0.015) if (left < 0 or right > src_w) else 0.0
    inset_y = max(3.0, src_h * 0.012) if (top < 0 or bottom > src_h) else 0.0

    valid_x = (xs_f >= inset_x) & (xs_f <= (src_w - 1.0 - inset_x))
    valid_y = (ys_f >= inset_y) & (ys_f <= (src_h - 1.0 - inset_y))
    valid_mask = valid_y[:, None] & valid_x[None, :]
    void_mask = ~valid_mask

    if not np.any(void_mask):
        pil_src = Image.fromarray(clean_rgb)
        cropped = pil_src.crop((int(round(left)), int(round(top)), int(round(right)), int(round(bottom)))).resize(
            (target_w, target_h), Image.Resampling.LANCZOS
        )
        res_arr = np.asarray(cropped, dtype=np.float32)
        return (res_arr, void_mask) if return_void_mask else res_arr

    # Sample valid interior with bilinear interpolation, clamped inside [inset_x .. src_w - 1 - inset_x]
    min_sx = float(inset_x)
    max_sx = float(max(min_sx + 1.0, src_w - 1.0 - inset_x))
    min_sy = float(inset_y)
    max_sy = float(max(min_sy + 1.0, src_h - 1.0 - inset_y))

    xs_clamped = np.clip(xs_f, min_sx, max_sx)
    ys_clamped = np.clip(ys_f, min_sy, max_sy)

    x0 = np.clip(np.floor(xs_clamped).astype(np.int32), 0, src_w - 1)
    x1 = np.clip(x0 + 1, 0, src_w - 1)
    y0 = np.clip(np.floor(ys_clamped).astype(np.int32), 0, src_h - 1)
    y1 = np.clip(y0 + 1, 0, src_h - 1)
    wx = np.clip(xs_clamped - x0, 0.0, 1.0)[None, :, None]
    wy = np.clip(ys_clamped - y0, 0.0, 1.0)[:, None, None]

    src_f = clean_rgb.astype(np.float32)
    c00 = src_f[y0[:, None], x0[None, :]]
    c10 = src_f[y0[:, None], x1[None, :]]
    c01 = src_f[y1[:, None], x0[None, :]]
    c11 = src_f[y1[:, None], x1[None, :]]
    clamped_canvas = (1.0 - wy) * ((1.0 - wx) * c00 + wx * c10) + wy * ((1.0 - wx) * c01 + wx * c11)

    if fill_mode == "none_preview":
        yy, xx = np.indices((target_h, target_w))
        checker = ((xx // 14) + (yy // 14)) % 2 == 0
        diag = ((xx + yy) % 16) < 2
        void_vis = np.zeros((target_h, target_w, 3), dtype=np.float32)
        void_vis[:, :] = np.where(checker[:, :, None], np.array([14.0, 22.0, 36.0]), np.array([22.0, 34.0, 54.0]))
        void_vis[diag] = np.array([0.0, 145.0, 195.0])
        out = np.where(valid_mask[:, :, None], clamped_canvas, void_vis)
        return (out, void_mask) if return_void_mask else out

    # Smooth feather weight inside valid_mask so there is NEVER a hard line at the image boundary
    dist_in = distance_transform_edt(valid_mask).astype(np.float32)
    dist_out = distance_transform_edt(void_mask).astype(np.float32)
    seam_feather = np.clip(dist_in / 9.0, 0.0, 1.0)
    seam_feather = (0.5 - 0.5 * np.cos(np.pi * seam_feather))[:, :, None]

    # Sample corner background pixels from clean interior corners to identify true background/aura vs character limbs
    cw = max(8, int(src_w * 0.16))
    ch = max(8, int(src_h * 0.16))
    ix = int(round(min_sx))
    iy = int(round(min_sy))
    top_corners = np.vstack([
        src_f[iy : iy + ch, ix : ix + cw].reshape(-1, 3),
        src_f[iy : iy + ch, src_w - ix - cw : src_w - ix].reshape(-1, 3),
    ])
    bot_corners = np.vstack([
        src_f[src_h - iy - ch : src_h - iy, ix : ix + cw].reshape(-1, 3),
        src_f[src_h - iy - ch : src_h - iy, src_w - ix - cw : src_w - ix].reshape(-1, 3),
    ])
    top_luma_med = float(np.median(top_corners @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)))
    # In portrait illustrations with a bright sky/aura background (like Gohan SSJ2's golden-yellow background),
    # the bottom corners touch the character's arms/clothing while the top corners are pure background!
    if top_luma_med >= 125.0:
        corner_bg = top_corners
    else:
        corner_bg = np.vstack([top_corners, top_corners, bot_corners])

    if fill_mode == "solid_edge":
        bg_color = np.median(corner_bg, axis=0)
        out = clamped_canvas * seam_feather + bg_color[None, None, :] * (1.0 - seam_feather)
        return (np.clip(out, 0.0, 255.0), void_mask) if return_void_mask else np.clip(out, 0.0, 255.0)

    if fill_mode == "mirror_blend":
        # Reflected coordinates strictly inside [min_sx .. max_sx] so border artifacts are never reflected
        eff_w = max(1.0, max_sx - min_sx)
        eff_h = max(1.0, max_sy - min_sy)
        rx_f = min_sx + (eff_w - np.abs(np.mod(xs_f - min_sx, 2.0 * eff_w) - eff_w))
        ry_f = min_sy + (eff_h - np.abs(np.mod(ys_f - min_sy, 2.0 * eff_h) - eff_h))
        rx = np.clip(np.round(rx_f).astype(np.int32), int(min_sx), int(max_sx))
        ry = np.clip(np.round(ry_f).astype(np.int32), int(min_sy), int(max_sy))
        mirror_canvas = src_f[ry[:, None], rx[None, :]]
        soft_m = gaussian_filter(mirror_canvas, sigma=(1.4, 1.4, 0.0))
        out = clamped_canvas * seam_feather + soft_m * (1.0 - seam_feather)
        return (np.clip(out, 0.0, 255.0), void_mask) if return_void_mask else np.clip(out, 0.0, 255.0)

    # Build Foreground-Filtered Border Extension Canvas for `"edge_stretch"` and `"smart_aura"`
    # Find valid column/row indices in target canvas
    valid_cols = np.where(valid_x)[0]
    valid_rows = np.where(valid_y)[0]
    if len(valid_cols) >= 4 and len(valid_rows) >= 4:
        c_left = valid_cols[0]
        c_right = valid_cols[-1]
        r_top = valid_rows[0]
        r_bot = valid_rows[-1]
        strip_k = max(3, min(14, (c_right - c_left) // 10))

        # Extract left and right vertical border profiles (averaged over strip_k interior columns) and filter out character limbs!
        left_prof_raw = np.mean(clamped_canvas[:, c_left : c_left + strip_k, :], axis=1)
        right_prof_raw = np.mean(clamped_canvas[:, c_right - strip_k + 1 : c_right + 1, :], axis=1)
        left_prof = _filter_border_profile_intrusions(left_prof_raw, corner_bg)
        right_prof = _filter_border_profile_intrusions(right_prof_raw, corner_bg)

        stretched = clamped_canvas.copy()
        if c_left > 0:
            stretched[:, : c_left + strip_k, :] = left_prof[:, None, :]
        if c_right < target_w - 1:
            stretched[:, c_right - strip_k + 1 :, :] = right_prof[:, None, :]

        # Similarly filter top & bottom horizontal profiles if vertical void exists
        if r_top > 0 or r_bot < target_h - 1:
            strip_ky = max(3, min(14, (r_bot - r_top) // 10))
            top_prof_raw = np.mean(stretched[r_top : r_top + strip_ky, :, :], axis=0)
            bot_prof_raw = np.mean(stretched[r_bot - strip_ky + 1 : r_bot + 1, :, :], axis=0)
            top_prof = _filter_border_profile_intrusions(top_prof_raw, corner_bg)
            bot_prof = _filter_border_profile_intrusions(bot_prof_raw, corner_bg)
            if r_top > 0:
                stretched[: r_top + strip_ky, :, :] = top_prof[None, :, :]
            if r_bot < target_h - 1:
                stretched[r_bot - strip_ky + 1 :, :, :] = bot_prof[None, :, :]
    else:
        stretched = clamped_canvas.copy()

    # Smooth organic diffusion of the stretched border
    blur_near = gaussian_filter(stretched, sigma=(6.0, 6.0, 0.0))
    blur_far = gaussian_filter(stretched, sigma=(22.0, 22.0, 0.0))
    w_far = np.clip(dist_out / 34.0, 0.0, 1.0)[:, :, None]
    edge_extended = blur_near * (1.0 - 0.65 * w_far) + blur_far * (0.65 * w_far)

    if fill_mode == "edge_stretch":
        out = clamped_canvas * seam_feather + edge_extended * (1.0 - seam_feather)
        return (np.clip(out, 0.0, 255.0), void_mask) if return_void_mask else np.clip(out, 0.0, 255.0)

    # Default `"smart_aura"`:
    # 1. Near the border: gently billowing aura (blue/purple/silver) from `edge_extended` (with character limbs already removed!)
    # 2. Further into the void: transitions into deep cosmic/ambient background + organic nebula clouds
    # 3. Starfield & energy sparkles synthesis when dark/cosmic background is detected!
    yy, xx = np.indices((target_h, target_w), dtype=np.float32)

    # Organic billowing wave displacement on `edge_extended` so aura is cloudy rather than rigid horizontal lines
    wave_dy = 9.0 * np.sin(xx / 13.0 + yy / 23.0) + 5.0 * np.cos(xx / 7.5 - yy / 17.0)
    wave_dx = 6.0 * np.cos(yy / 14.0 + xx / 19.0)
    wy_idx = np.clip(np.round(yy + wave_dy).astype(np.int32), 0, target_h - 1)
    wx_idx = np.clip(np.round(xx + wave_dx).astype(np.int32), 0, target_w - 1)
    wavy_aura = gaussian_filter(edge_extended[wy_idx, wx_idx], sigma=(3.5, 3.5, 0.0))

    # Extract background & aura colors from `corner_bg`:
    # For dark/cosmic backgrounds (`median_bg_luma < 135`), blend deep space (25th pct) with nebula aura (75th pct).
    # For bright backgrounds (e.g. Gohan SSJ2's Golden-Yellow background, `median_bg_luma >= 135`),
    # use the clean bright background percentiles (45th..90th) so dark hair/rock intrusions in the corners never muddy the yellow void!
    corner_luma = corner_bg @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    median_bg_luma = float(np.median(corner_luma))
    if median_bg_luma >= 135.0:
        low_mask = (corner_luma >= np.percentile(corner_luma, 40)) & (corner_luma <= np.percentile(corner_luma, 75))
        high_mask = (corner_luma >= np.percentile(corner_luma, 65)) & (corner_luma <= np.percentile(corner_luma, 94))
    else:
        low_mask = corner_luma <= np.percentile(corner_luma, 45)
        high_mask = (corner_luma >= np.percentile(corner_luma, 60)) & (corner_luma <= np.percentile(corner_luma, 92))
    deep_space_rgb = np.median(corner_bg[low_mask], axis=0) if np.any(low_mask) else np.median(corner_bg, axis=0)
    aura_nebula_rgb = np.median(corner_bg[high_mask], axis=0) if np.any(high_mask) else deep_space_rgb

    # Multi-scale organic nebula clouds in the void
    rng = np.random.default_rng(seed=42)
    cloud_n1 = gaussian_filter(rng.standard_normal((target_h, target_w)).astype(np.float32), sigma=18.0)
    cloud_n2 = gaussian_filter(rng.standard_normal((target_h, target_w)).astype(np.float32), sigma=7.5)
    cloud_field = 0.65 * (cloud_n1 / max(1e-5, float(np.std(cloud_n1)))) + 0.35 * (cloud_n2 / max(1e-5, float(np.std(cloud_n2))))
    cloud_alpha = np.clip(0.38 + 0.28 * cloud_field, 0.0, 0.85)[:, :, None]

    cosmic_bg = deep_space_rgb[None, None, :] * (1.0 - cloud_alpha) + aura_nebula_rgb[None, None, :] * cloud_alpha

    # As distance `dist_out` grows, transition smoothly from the local wavy border aura into the cosmic nebula background
    aura_fade = np.exp(-dist_out / max(18.0, float(min(target_w, target_h)) * 0.11))[:, :, None]
    synthesized = wavy_aura * (0.45 + 0.55 * aura_fade) + cosmic_bg * (0.55 * (1.0 - aura_fade))

    # Synthesize crisp Stars & Energy Sparkles if the background is dark/cosmic (like Goku Ultra Instinct or Saint Seiya)
    if median_bg_luma < 135.0:
        # Generate deterministic multi-size starfield in the void
        star_rng = np.random.default_rng(seed=1337)
        star_prob = star_rng.random((target_h, target_w), dtype=np.float32)

        # 1) Fine pinpoint stars (density ~0.35%)
        fine_stars = (star_prob > 0.9962).astype(np.float32)
        fine_glow = gaussian_filter(fine_stars, sigma=0.65)
        fine_glow = np.clip(fine_glow / max(1e-4, float(np.max(fine_glow))) * 1.15, 0.0, 1.0)

        # 2) Brighter 2-3px cosmic stars with soft aura halo (density ~0.08%)
        bright_stars = (star_prob < 0.00085).astype(np.float32)
        bright_core = gaussian_filter(bright_stars, sigma=1.05)
        bright_core = np.clip(bright_core / max(1e-4, float(np.max(bright_core))) * 1.35, 0.0, 1.0)
        bright_halo = gaussian_filter(bright_stars, sigma=2.8)
        bright_halo = np.clip(bright_halo / max(1e-4, float(np.max(bright_halo))) * 0.65, 0.0, 1.0)

        star_intensity = np.clip(fine_glow * 0.88 + bright_core, 0.0, 1.0)[:, :, None]
        halo_intensity = bright_halo[:, :, None]

        star_white = np.array([246.0, 249.0, 255.0], dtype=np.float32)[None, None, :]
        halo_tint = np.clip(aura_nebula_rgb * 1.45 + 40.0, 140.0, 245.0)[None, None, :]

        synthesized = synthesized * (1.0 - 0.55 * halo_intensity) + halo_tint * (0.55 * halo_intensity)
        synthesized = synthesized * (1.0 - star_intensity) + star_white * star_intensity

    out = clamped_canvas * seam_feather + synthesized * (1.0 - seam_feather)
    out = np.clip(out, 0.0, 255.0)
    return (out, void_mask) if return_void_mask else out


def compute_enhanced_luminance(
    arr_rgb: np.ndarray,
    detail_boost: float = 1.2,
    contrast_gamma: float = 1.0,
    smoothing_sigma: float = 0.35,
) -> np.ndarray:
    """
    Computes the normalized `[0.0 .. 1.0]` heightmap luminance from an `(H, W, 3)` float32 RGB array,
    applying:
    1. Perceptual luminance + dark line-art preservation (minimum channel weighting for crisp black ink outlines).
    2. Percentile auto-levels (1% to 99%) + Gamma curve (`contrast_gamma`).
    3. Unsharp Mask (`detail_boost`) so manga hair, eyes, and armor details stand out sharply in 3D.
    """
    # Combine standard luma (75%) with darkest-channel (25%) so black manga outlines & colored details stay deep
    std_luma = (0.2126 * arr_rgb[:, :, 0] + 0.7152 * arr_rgb[:, :, 1] + 0.0722 * arr_rgb[:, :, 2]) / 255.0
    min_chan = np.min(arr_rgb, axis=2) / 255.0
    luma = 0.78 * std_luma + 0.22 * min_chan

    # Auto-contrast stretch (1st to 99th percentile)
    p1, p99 = float(np.percentile(luma, 1.0)), float(np.percentile(luma, 99.0))
    if p99 - p1 > 1e-3:
        luma = np.clip((luma - p1) / (p99 - p1), 0.0, 1.0)

    # Unsharp Mask (High-Frequency Detail Enhancer for eyes, hair, aura)
    if detail_boost > 0.05:
        blurred = gaussian_filter(luma, sigma=1.8)
        high_freq = luma - blurred
        luma = np.clip(luma + float(detail_boost) * 0.65 * high_freq, 0.0, 1.0)

    # Gamma adjustment
    if abs(contrast_gamma - 1.0) > 0.02:
        luma = np.power(np.clip(luma, 0.0, 1.0), 1.0 / max(0.25, float(contrast_gamma)))

    # Micro-smoothing to prevent single-pixel needle artifacts while keeping sharp edges
    if smoothing_sigma > 0.05:
        luma = gaussian_filter(luma, sigma=float(smoothing_sigma))

    return np.clip(luma, 0.0, 1.0)


def _classify_layer_family(rgb: Tuple[int, int, int], s_idx: int, total_k: int) -> str:
    if s_idx == 0:
        return "dark"
    if s_idx == total_k - 1:
        r, g, b = rgb
        if max(r, g, b) > 215 and (max(r, g, b) - min(r, g, b)) < 45:
            return "white"
    arr = np.array([rgb], dtype=np.float32)
    hue_deg, sat, val = _rgb_array_to_hsv_deg(arr)
    h_val = float(hue_deg[0])
    s_val = float(sat[0])
    v_val = float(val[0])
    if s_val < 0.14:
        return "silver"
    if (40.0 <= h_val < 65.0) or (33.0 <= h_val < 40.0 and s_val >= 0.46 and v_val >= 0.62):
        return "gold"
    if h_val < 40.0 or h_val >= 332.0:
        return "warm"
    if 65.0 <= h_val < 168.0:
        return "green"
    if 168.0 <= h_val < 252.0:
        return "cool"
    return "purple"


def compute_chroma_aware_pixel_z(
    arr_rgb: np.ndarray,
    luma: np.ndarray,
    specs: List[ColorLayerSpec],
) -> np.ndarray:
    """
    Universal 5-Family Chromatic Spool-Affinity & Continuous Ramp Height Mapper (`compute_chroma_aware_pixel_z`):
    Works for ANY combination of 1 to 5 chromatic families (`warm`, `gold`, `green`, `cool`, `purple`) + `silver`:
    - Groups the palette into contiguous Chromatic Family Ramps and uses Spool-Color Affinity + `luma`
      to map each pixel cleanly into its matching spool sub-band (e.g. Brown vs Peach Skin vs Golden Yellow).
    - Never spills chromatic layers into Top White (`target_top_z = z_end`); only true white / low-saturation
      specular highlights (`luma >= 0.91` and `sat < 0.22`) enter Top White.
    - Protects minority/accent Cyan & Cool layers (e.g. Gohan's belt & lightning) from being hijacked by silver-hair rules.
    """
    base_z = float(specs[0].end_mm)
    max_z = max(float(specs[-1].end_mm), base_z + 0.1)
    z_luma = base_z + luma * (max_z - base_z)

    k = len(specs)
    if k <= 2:
        return z_luma

    ref_specs = _get_reference_relief_specs(specs)
    is_custom_layers = any(s.end_layer_num != r.end_layer_num for s, r in zip(specs, ref_specs))
    layer_ratios: List[float] = []
    for s_sp, r_sp in zip(specs, ref_specs):
        u_cnt = max(1, s_sp.end_layer_num - s_sp.start_layer_num + 1)
        r_cnt = max(1, r_sp.end_layer_num - r_sp.start_layer_num + 1)
        layer_ratios.append(float(u_cnt) / float(r_cnt) if is_custom_layers else 1.0)

    blk_scale = float(np.clip(layer_ratios[0] ** 0.85, 0.22, 2.20)) if is_custom_layers else 1.0

    pix_rgb = arr_rgb.astype(np.float32)
    hue_p, sat_p, val_p = _rgb_array_to_hsv_deg(pix_rgb)
    chroma_span_p = np.max(pix_rgb, axis=-1) - np.min(pix_rgb, axis=-1)
    # Dark chromatic pixels:
    # Rescue dark navy/cyan belts & wristbands (Hue 165°..255°, sat >= 0.42, span >= 16) or vivid mid-dark chromatic accents
    # (luma > 0.15, val >= 0.28, sat >= 0.52, span >= 28), while keeping dark cosmos backgrounds & charcoal-black anime hair
    # (e.g. [34, 36, 46] with sat=0.28, span=14) in Base Black!
    is_dark_cool_accent = (luma > 0.045 * blk_scale) & (hue_p >= 165.0) & (hue_p < 255.0) & (sat_p >= 0.42) & (chroma_span_p >= 16.0)
    is_dark_vivid_chroma = (luma > 0.15 * blk_scale) & (val_p >= 0.28) & (sat_p >= 0.52) & (chroma_span_p >= 28.0)
    is_dark_chromatic = is_dark_cool_accent | is_dark_vivid_chroma
    is_black_ink = (
        (luma <= 0.045 * blk_scale)
        | ((luma <= 0.15 * blk_scale) & (~is_dark_chromatic))
        | ((luma <= 0.24 * blk_scale) & ((val_p < 0.29 * blk_scale) | ((sat_p < 0.38) & (chroma_span_p < 18.0))) & (~is_dark_cool_accent))
        | ((luma < 0.28 * blk_scale) & ((sat_p < 0.22) | (chroma_span_p < 18.0)) & (~is_dark_cool_accent))
    )

    band_starts = np.zeros(k, dtype=np.float32)
    band_ends = np.zeros(k, dtype=np.float32)
    layer_fams: List[str] = []
    for s_idx, sp in enumerate(specs):
        band_starts[s_idx] = base_z if s_idx == 0 else float(specs[s_idx - 1].end_mm)
        band_ends[s_idx] = float(sp.end_mm)
        layer_fams.append(_classify_layer_family(sp.rgb, s_idx, k))

    has_top_white = layer_fams[-1] == "white"
    white_start_z = float(band_starts[-1]) if has_top_white else max_z

    def _dist_to_family_ramp(fam_idxs: List[int]) -> np.ndarray:
        """
        Computes the exact Euclidean RGB distance from each pixel to the continuous piecewise-linear
        color ramp achievable by `fam_idxs` (from dark shadow node through all spools in the family).
        """
        if not fam_idxs:
            return np.full(luma.shape, 1e6, dtype=np.float32)
        first_rgb = np.array(specs[fam_idxs[0]].rgb, dtype=np.float32)
        shadow_node = 0.22 * np.array(specs[0].rgb, dtype=np.float32) + 0.78 * first_rgb
        nodes = [shadow_node] + [np.array(specs[i].rgb, dtype=np.float32) for i in fam_idxs]
        if has_top_white and fam_idxs[-1] == k - 2:
            last_rgb = np.array(specs[fam_idxs[-1]].rgb, dtype=np.float32)
            nodes.append(0.68 * last_rgb + 0.32 * np.array([255.0, 255.0, 255.0], dtype=np.float32))
        best_d2 = np.sum((pix_rgb - nodes[0]) ** 2, axis=-1)
        for n_i in range(len(nodes) - 1):
            a_pt = nodes[n_i]
            b_pt = nodes[n_i + 1]
            ab = b_pt - a_pt
            ab_len2 = max(1e-4, float(np.dot(ab, ab)))
            t_proj = np.clip(np.sum((pix_rgb - a_pt) * ab, axis=-1) / ab_len2, 0.0, 1.0)
            proj = a_pt + t_proj[:, :, None] * ab
            d2 = np.sum((pix_rgb - proj) ** 2, axis=-1)
            best_d2 = np.minimum(best_d2, d2)
        return np.sqrt(best_d2)

    def _family_ramp_z(fam_name: str) -> Optional[np.ndarray]:
        idxs = [i for i, f in enumerate(layer_fams) if f == fam_name]
        if not idxs:
            return None
        first_i, last_i = idxs[0], idxs[-1]
        z_start = float(band_starts[first_i])
        z_end = float(band_ends[last_i])
        first_span = float(band_ends[first_i] - band_starts[first_i])

        # Multi-spool family (e.g. `warm` with Brown + Orange + Peach Skin, or `cool` with Navy + Sky Blue):
        if len(idxs) == 2:
            rgb_lo = np.array(specs[first_i].rgb, dtype=np.float32)
            rgb_hi = np.array(specs[last_i].rgb, dtype=np.float32)
            d_lo = np.sqrt(np.sum((pix_rgb - rgb_lo) ** 2, axis=-1)) / (layer_ratios[first_i] ** 0.55)
            d_hi = np.sqrt(np.sum((pix_rgb - rgb_hi) ** 2, axis=-1)) / (layer_ratios[last_i] ** 0.55)
            affinity_hi = np.clip((d_lo - d_hi) / np.maximum(18.0, d_lo + d_hi) + 0.5, 0.0, 1.0)
            luma_norm = np.clip((luma - 0.08) / 0.80, 0.0, 1.0)
            entry_z = z_start + (0.24 if first_i == 1 else 0.42) * first_span
            luma_shift_2 = 0.08 * (layer_ratios[first_i] - layer_ratios[last_i]) if is_custom_layers else 0.0
            if fam_name == "warm" and rgb_hi[1] >= 0.52 * rgb_hi[0] and rgb_hi[2] >= 0.36 * rgb_hi[0]:
                # Upper spool is Peach Skin, lower spool is Vibrant Orange/Red or Brown:
                # Ensure high-saturation Orange-Red pants/gi (`sat_p >= 0.54` and low Blue channel) stay squarely
                # in the lower Orange/Red spool (`<= band_ends[first_i]`), while Peach Skin sits in the upper spool!
                mid_z = float(band_ends[first_i])
                is_peach_pix = (
                    ((hue_p < 34.5) | (hue_p >= 332.0))
                    & (pix_rgb[:, :, 0] >= 150.0)
                    & (pix_rgb[:, :, 1] >= 0.52 * pix_rgb[:, :, 0])
                    & (pix_rgb[:, :, 2] >= 0.36 * pix_rgb[:, :, 0])
                    & (sat_p < 0.54)
                    & (luma >= np.clip(0.42 + luma_shift_2, 0.18, 0.78))
                ) | ((d_hi < d_lo * 0.90) & ((hue_p < 35.0) | (hue_p >= 332.0)))
                z_lo_sub = entry_z + np.clip((luma - 0.10) / 0.58, 0.0, 1.0) * (mid_z - entry_z)
                hi_entry = mid_z + 0.32 * (z_end - mid_z)
                z_hi_sub = hi_entry + np.clip((luma - 0.38) / 0.52, 0.0, 1.0) * (z_end - hi_entry)
                z_r = np.where(is_black_ink, base_z, np.where(is_peach_pix, z_hi_sub, z_lo_sub))
            elif fam_name == "gold":
                # 2-Spool Gold Ramp (Lower = Rich Amber-Gold bevels/wings, Upper = Champagne-Gold / Ivory-Yellow armor plates):
                mid_z = float(band_ends[first_i])
                is_champagne_plate = ((luma >= np.clip(0.62 + luma_shift_2, 0.25, 0.88)) & (~((hue_p < 44.0) & (sat_p >= 0.56) & (luma < 0.74)))) | (d_hi < d_lo * 0.94)
                z_lo_sub = entry_z + np.clip((luma - 0.16) / 0.52, 0.0, 1.0) * (mid_z - entry_z)
                hi_entry = mid_z + 0.36 * (z_end - mid_z)
                z_hi_sub = hi_entry + np.clip((luma - 0.56) / 0.38, 0.0, 1.0) * (z_end - hi_entry)
                z_r = np.where(is_black_ink, base_z, np.where(is_champagne_plate, z_hi_sub, z_lo_sub))
            else:
                if fam_name == "cool":
                    u_mix = np.clip(0.45 * affinity_hi + 0.55 * luma_norm, 0.0, 1.0)
                    # Ensure bright Ice-Cyan aura pixels (`luma >= 0.68` and `hue < 210°`) reach the top of the upper Cyan spool!
                    is_bright_cyan = (hue_p < 210.0) & (luma >= 0.65)
                    cyan_boost = np.clip(0.76 + 0.24 * np.clip((luma - 0.65) / 0.25, 0.0, 1.0), 0.0, 1.0)
                    u_mix = np.where(is_bright_cyan, np.maximum(u_mix, cyan_boost), u_mix)
                else:
                    u_mix = np.clip(0.65 * affinity_hi + 0.35 * luma_norm, 0.0, 1.0)
                z_r = np.where(is_black_ink, base_z, entry_z + u_mix * (z_end - entry_z))
        elif len(idxs) >= 3:
            # 3+ spools in the same family (e.g. Dark Brown + Vibrant Orange + Peach Skin on Goku SSJ3 Shenron,
            # or Deep Navy + Royal Blue + Ice Cyan on multi-blue aura):
            # Map each pixel into the sub-band `[sub_lo .. sub_hi]` of its closest spool in RGB+saturation!
            dists = []
            sub_zs = []
            for sub_pos, sp_i in enumerate(idxs):
                sp_rgb = np.array(specs[sp_i].rgb, dtype=np.float32)
                d_sp = np.sqrt(np.sum((pix_rgb - sp_rgb) ** 2, axis=-1)) / (layer_ratios[sp_i] ** 0.55)
                # For Warm 3-spool ramp (0=Dark Brown, 1=Vibrant Orange, 2=Peach Skin), reinforce physical separation
                if fam_name == "warm" and len(idxs) == 3:
                    if sub_pos == 1:
                        # Vibrant Orange Gi bonus for high-saturation mid/bright orange pixels
                        is_vivid_org = (sat_p >= 0.54) & (luma >= 0.28) & (pix_rgb[:, :, 2] < 0.38 * pix_rgb[:, :, 0])
                        d_sp = np.where(is_vivid_org, d_sp * 0.55, d_sp)
                    elif sub_pos == 2:
                        # Peach Skin bonus for pastel flesh pixels (significant B/R and moderate saturation)
                        is_flesh = (
                            (pix_rgb[:, :, 1] >= 0.52 * pix_rgb[:, :, 0])
                            & (pix_rgb[:, :, 2] >= 0.36 * pix_rgb[:, :, 0])
                            & (sat_p < 0.52)
                            & (luma >= 0.40)
                        )
                        d_sp = np.where(is_flesh, d_sp * 0.50, np.where(sat_p >= 0.58, d_sp * 1.45, d_sp))
                dists.append(d_sp)
                s_lo = float(band_starts[sp_i])
                s_hi = float(band_ends[sp_i])
                s_span = s_hi - s_lo
                if sub_pos == 0:
                    e_lo = s_lo + (0.24 if sp_i == 1 else 0.42) * s_span
                    u_local = np.power(np.clip((luma - 0.15) / 0.38, 0.0, 1.0), 1.35)
                    sub_zs.append(e_lo + u_local * (s_hi - e_lo))
                else:
                    e_lo = s_lo + 0.34 * s_span
                    u_local = np.clip((luma - 0.08) / 0.80, 0.0, 1.0)
                    sub_zs.append(e_lo + (0.25 + 0.75 * u_local) * (s_hi - e_lo))
            d_stack = np.stack(dists, axis=0)
            z_stack = np.stack(sub_zs, axis=0)
            best_sub = np.argmin(d_stack, axis=0)
            z_picked = np.take_along_axis(z_stack, best_sub[None, :, :], axis=0)[0]
            z_r = np.where(is_black_ink, base_z, z_picked)
        elif first_i == 1:
            # Single-spool family sitting directly on Base Black (e.g. Cyan belt/lightning or Red Sun/Gi):
            # Start at 38% thickness so dark/midtone accents aren't swallowed by Black
            u_single = 0.38 + 0.62 * np.clip((luma - 0.06) / 0.74, 0.0, 1.0)
            z_r = np.where(is_black_ink, base_z, z_start + u_single * (z_end - z_start))
        else:
            # Single-spool family sitting above another chromatic family (e.g. Cool Blue belt, Gold, Purple, Green):
            # Never spill into Top White (`z_end`, NOT `max_z`!)
            opaque_entry_z = z_start + 0.44 * first_span
            if fam_name == "gold":
                # Keep golden-yellow hair & background high in the Gold spool so they render vivid yellow
                u_val = np.clip(0.36 + 0.64 * np.clip((luma - 0.18) / 0.64, 0.0, 1.0), 0.0, 1.0)
            elif fam_name == "cool":
                # Ensure dark navy/blue belts & wristbands (luma 0.06..0.28) sit high enough in the Blue spool to be clearly visible
                u_val = np.clip(0.42 + 0.58 * np.clip((luma - 0.05) / 0.50, 0.0, 1.0), 0.0, 1.0)
            elif fam_name == "purple" and specs[first_i].rgb[0] >= 160 and specs[first_i].rgb[2] >= 130:
                # Pastel Rose-Pink cloth spool (e.g. Shiryu V1 #CE4EAC): keep high in the spool so it renders bright pink
                u_val = np.clip(0.58 + 0.42 * np.clip((luma - 0.20) / 0.60, 0.0, 1.0), 0.0, 1.0)
            else:
                u_val = np.clip(0.22 + 0.78 * np.clip((luma - 0.07) / 0.72, 0.0, 1.0), 0.0, 1.0)
            z_r = np.where(
                is_black_ink,
                base_z,
                opaque_entry_z + u_val * (z_end - opaque_entry_z),
            )

        if has_top_white:
            # Only allow truly white / low-saturation specular highlights to cross into Top White
            z_r = np.where(
                (luma > 0.94) & (sat_p < 0.22),
                white_start_z + 0.55 * (max_z - white_start_z) + np.clip((luma - 0.94) / 0.06, 0.0, 1.0) * 0.45 * (max_z - white_start_z),
                z_r,
            )
        return z_r

    ramps: Dict[str, Optional[np.ndarray]] = {
        fam: _family_ramp_z(fam)
        for fam in ("warm", "gold", "green", "cool", "purple", "silver")
    }

    active_chroma_ramps = [r for f, r in ramps.items() if f != "silver" and r is not None]
    if not active_chroma_ramps:
        return np.clip(z_luma, base_z, max_z)

    # Default ramp is the family of the highest chromatic layer in `specs` (right below silver/white)
    top_chroma_fam = next(
        (f for f in reversed(layer_fams) if f not in ("dark", "white", "silver") and ramps.get(f) is not None),
        None,
    )
    default_ramp = ramps[top_chroma_fam] if top_chroma_fam is not None else active_chroma_ramps[-1]

    # Resolve fallback ramp for each of the 5 chromatic families when K is small
    z_warm = ramps["warm"] if ramps["warm"] is not None else (ramps["gold"] if ramps["gold"] is not None else default_ramp)
    z_gold = ramps["gold"] if ramps["gold"] is not None else z_warm
    cool_idxs = [i for i, f in enumerate(layer_fams) if f == "cool"]
    warm_idxs = [i for i, f in enumerate(layer_fams) if f == "warm"]
    gold_idxs = [i for i, f in enumerate(layer_fams) if f == "gold"]
    green_idxs = [i for i, f in enumerate(layer_fams) if f == "green"]
    purple_idxs = [i for i, f in enumerate(layer_fams) if f == "purple"]
    cool_is_bottom_accent = bool(cool_idxs and len(cool_idxs) == 1 and cool_idxs[0] == 1 and (warm_idxs or gold_idxs))

    # Silver / White target for neutral grey hair, steel armor & pure white backgrounds
    if ramps["silver"] is not None:
        z_silver_target = ramps["silver"]
    elif has_top_white:
        z_silver_target = (
            white_start_z
            + 0.08 * (max_z - white_start_z)
            + np.power(np.clip((luma - 0.14) / 0.80, 0.0, 1.0), 1.18) * 0.92 * (max_z - white_start_z)
        )
    else:
        z_silver_target = default_ramp

    if ramps["cool"] is not None:
        z_cool = ramps["cool"]
    elif ramps["purple"] is not None:
        z_cool = ramps["purple"]
    elif ramps["green"] is not None:
        # When no Cool/Purple spool exists, teal-green foliage straddling 168°..205° maps to Green, and cool slate sky maps to Silver/Black
        z_cool = np.where(
            (hue_p < 205.0) & (pix_rgb[:, :, 1] >= pix_rgb[:, :, 2] * 0.88),
            ramps["green"],
            np.where(luma < 0.35, base_z, z_silver_target),
        )
    else:
        z_cool = np.where(luma < 0.35, base_z, z_silver_target)

    if ramps["green"] is not None:
        z_green = ramps["green"]
    elif cool_is_bottom_accent:
        sp_c_rgb = specs[cool_idxs[0]].rgb
        # Only route teal-green (122°..168°) to a bottom-accent Cool spool when Purple is present or the Cool spool is Teal/Cyan (e.g. Gohan SSJ2);
        # when Cool is a pure Royal Blue wristband on a Warm/Gold dragon image (e.g. Goku SSJ3), keep green flares in Gold!
        if purple_idxs or (sp_c_rgb[1] >= sp_c_rgb[2] * 0.78):
            is_teal_green = (hue_p >= 82.0) & ((pix_rgb[:, :, 1] - pix_rgb[:, :, 0]) >= 10.0) & (sat_p >= 0.14)
            is_pale_highlight = (hue_p >= 82.0) & (sat_p < 0.16) & (luma >= 0.55)
            z_green = np.where(is_teal_green, z_cool, np.where(is_pale_highlight, z_silver_target, z_gold))
        else:
            z_green = z_gold
    else:
        # Yellow-green glow (Hue < 112°) falls back to Gold (only if a Gold spool exists!), whereas teal-green falls back to Cool
        z_green = np.where(hue_p < 112.0, z_gold if gold_idxs else z_cool, z_cool)

    if ramps["purple"] is not None:
        z_purple = ramps["purple"]
    elif cool_is_bottom_accent:
        # On Warm/Gold-dominant images where Cool is just a single-spool Blue wristband/belt accent (e.g. Goku SSJ3 Shenron),
        # dark purple-brown cosmic background shadows must fall back to Warm (Brown) rather than turning bright Blue!
        z_purple = z_warm
    else:
        z_purple = ramps["cool"] if ramps["cool"] is not None else z_warm

    # Unified Perceptual Spool-Ramp Distance Matcher:
    # Measure each pixel's exact RGB distance to the continuous achievable ramp of each active family
    # instead of relying on rigid HSV degree cutoffs!
    if gold_idxs and warm_idxs:
        d_to_gold = _dist_to_family_ramp(gold_idxs)
        d_to_warm = _dist_to_family_ramp(warm_idxs)
        # When both Gold and Warm spools exist:
        # 1) Pure yellow / champagne-gold (`42.5° <= hue_p < 65.0°`, where G >= 0.86*R, NEVER human peach skin!)
        #    with `luma >= 0.45` and `sat >= 0.14` (captures both vivid yellow and pale champagne-gold armor plates!),
        # 2) Warm golden-amber zone `34.5° <= hue_p < 42.5°` with `sat >= 0.34`, `luma >= 0.54`, `R >= 188`, `B < 0.68*G`,
        # 3) When the palette has 2+ Gold spools (e.g. Golden Armor Saint Seiya with Rich Amber-Gold + Champagne-Gold),
        #    also route mid-tone golden armor bevels & golden-olive cosmos (`hue >= 38.0°`, `luma >= 0.28`, `sat >= 0.14`,
        #    or `hue >= 34.0°`, `sat >= 0.50`, `luma >= 0.34`) to the 2-spool Gold ramp!
        is_gold_pix = (
            (
                (hue_p >= 42.5)
                & (hue_p < 65.0)
                & (luma >= 0.55)
                & (sat_p >= 0.14)
                & (pix_rgb[:, :, 0] >= 188.0)
            )
            | (
                (hue_p >= 38.5)
                & (hue_p < 42.5)
                & (luma >= 0.48)
                & (sat_p >= 0.22)
                & (pix_rgb[:, :, 0] >= 190.0)
                & (pix_rgb[:, :, 2] < 0.72 * pix_rgb[:, :, 1])
            )
            | (
                (hue_p >= 34.5)
                & (hue_p < 38.5)
                & (sat_p >= 0.34)
                & (luma >= 0.54)
                & (pix_rgb[:, :, 0] >= 192.0)
                & (pix_rgb[:, :, 2] < 0.66 * pix_rgb[:, :, 1])
                & (d_to_gold <= d_to_warm * 1.04)
            )
        )
        if len(gold_idxs) >= 2:
            is_multi_gold_armor = (
                ((hue_p >= 38.0) & (hue_p < 65.0) & (luma >= 0.54) & (pix_rgb[:, :, 0] >= 186.0) & (sat_p >= 0.14))
                | ((hue_p >= 34.0) & (hue_p < 65.0) & (sat_p >= 0.68) & (luma >= 0.34) & (pix_rgb[:, :, 0] >= 152.0) & (pix_rgb[:, :, 2] < 46.0))
            )
            is_gold_pix = is_gold_pix | is_multi_gold_armor
    else:
        is_gold_pix = ((hue_p >= 41.0) & (hue_p < 65.0) & (sat_p >= 0.16)) | (
            (hue_p >= 36.5) & (hue_p < 41.0) & (sat_p >= 0.48) & (val_p >= 0.58)
        )

    # Rose-Pink vs Warm Crimson separation in [312°..354°]:
    # If the palette has a Rose-Pink / Purple spool (`purple_idxs`), route Rose-Pink cloth pixels (where B > G + 8)
    # to `is_purple_pix` when the purple spool is Rose-Pink (`R >= 0.78 * B`, e.g. Shiryu V1 #CE4EAC) or closer to the purple ramp!
    is_rose_pink_cloth = np.zeros(luma.shape, dtype=bool)
    if purple_idxs:
        sp_p_rgb = specs[purple_idxs[-1]].rgb
        if sp_p_rgb[0] >= 0.78 * sp_p_rgb[2]:
            is_rose_pink_cloth = (
                (hue_p >= 295.0)
                & (hue_p < 355.0)
                & ((pix_rgb[:, :, 2] - pix_rgb[:, :, 1]) >= 5.0)
                & ((pix_rgb[:, :, 0] - pix_rgb[:, :, 1]) >= 12.0)
                & (sat_p >= 0.06)
                & (luma < 0.90)
            )
    # Warm crimson-magenta shading on orange-red gi/pants (Hue 316°..332° where R > 1.12 * B and not Rose-Pink cloth) belongs to `warm`
    is_warm_magenta = (hue_p >= 316.0) & (pix_rgb[:, :, 0] > 1.12 * pix_rgb[:, :, 2]) & (~is_rose_pink_cloth)
    # Any pixel in [0°..65°) or [332°..360°) (or warm crimson-magenta) that is not `is_gold_pix` or `is_rose_pink_cloth` is `is_warm_pix`
    is_warm_pix = (((hue_p < 65.0) | (hue_p >= 332.0)) | is_warm_magenta) & (~is_gold_pix) & (~is_rose_pink_cloth)

    # Continuous Ramp Affinity across the 168° Green / Cool boundary (prevents green blotches in emerald-teal backgrounds):
    if green_idxs and cool_idxs:
        d_to_green = _dist_to_family_ramp(green_idxs)
        d_to_cool = _dist_to_family_ramp(cool_idxs)
        in_gc_zone = (hue_p >= 65.0) & (hue_p < 252.0)
        prefers_cool = (hue_p >= 168.0) | ((hue_p >= 122.0) & (d_to_cool < d_to_green * 0.96))
        is_cool_pix = in_gc_zone & prefers_cool
        is_green_pix = in_gc_zone & (~prefers_cool)
    else:
        is_green_pix = (hue_p >= 65.0) & (hue_p < 168.0)
        is_cool_pix = (hue_p >= 168.0) & (hue_p < 252.0)

    rejected_cool_pix = np.zeros(luma.shape, dtype=bool)
    if cool_is_bottom_accent:
        raw_cool_mask = is_cool_pix.copy()
        sp_c_rgb = specs[cool_idxs[0]].rgb
        # Distinguish a Deep Royal/Navy Blue accent on a pure Warm/Gold image (e.g. Goku SSJ3 wristbands)
        # from a Teal-Cyan belt/lightning accent or Purple+Warm+Gold character (e.g. Gohan SSJ2):
        if (not purple_idxs) and (sp_c_rgb[2] > sp_c_rgb[1] * 1.15):
            is_cool_pix = (
                is_cool_pix
                & (sat_p >= 0.30)
                & ((pix_rgb[:, :, 2] - pix_rgb[:, :, 0]) >= 16.0)
                & ((pix_rgb[:, :, 1] - pix_rgb[:, :, 0]) >= 6.0)
                & (hue_p < 232.0)
                & (pix_rgb[:, :, 0] < 82.0)
            )
        else:
            is_cool_pix = (
                is_cool_pix
                & (sat_p >= 0.16)
                & ((np.maximum(pix_rgb[:, :, 1], pix_rgb[:, :, 2]) - pix_rgb[:, :, 0]) >= 10.0)
                & (hue_p < 245.0)
            )
        # Any cool pixel that failed the strict bottom-accent filter must NEVER fall through to `default_ramp = Gold`!
        # Unless it is a warm rainbow sky flare in a golden aura (`R >= 82` and `G >= 82` on a non-purple image),
        # route rejected cool shadows to Black and rejected cool highlights to Silver/White.
        is_rainbow_flare = (not purple_idxs) & (pix_rgb[:, :, 0] >= 82.0) & (pix_rgb[:, :, 1] >= 82.0)
        rejected_cool_pix = raw_cool_mask & (~is_cool_pix) & (~is_rainbow_flare)

    is_purple_pix = (
        ((hue_p >= 252.0) & (hue_p < 332.0) & (~is_warm_magenta) & (sat_p >= (0.14 if purple_idxs else 0.22)))
        | is_rose_pink_cloth
    )
    rejected_purple_pix = (hue_p >= 252.0) & (hue_p < 332.0) & (~is_warm_magenta) & (~is_purple_pix)

    # Blue-Cast / Cyan-Illuminated Character Subject routing (e.g. Goku standing inside a strong Cyan/Blue aura):
    # When unshifted `is_warm_pix` is <0.8% of the image while `cool` is >55%, a `warm` spool is present, and no `purple` spool exists,
    # route warm-balanced character pixels inside the dark-ink-outlined character silhouette (`near_char_ink`) to `is_warm_pix`!
    if (not purple_idxs) and warm_idxs and float(np.mean(is_warm_pix & (~is_black_ink))) < 0.008 and float(np.mean(is_cool_pix)) >= 0.55:
        r_p, g_p, b_p = pix_rgb[:, :, 0], pix_rgb[:, :, 1], pix_rgb[:, :, 2]
        near_char_ink = gaussian_filter((luma < 0.38).astype(np.float32), sigma=6.5) >= 0.08
        is_blue_cast_warm = (
            near_char_ink
            & (
                ((r_p >= g_p - 2.5) & ((b_p - r_p) <= 55.0))
                | ((hue_p >= 228.0) & (r_p >= g_p - 11.5) & ((b_p - r_p) <= 76.0) & (luma >= 0.32))
            )
            & (luma >= 0.14)
            & (luma <= 0.68)
            & (sat_p >= 0.08)
        )
        is_warm_pix = is_warm_pix | is_blue_cast_warm
        is_cool_pix = is_cool_pix & (~is_blue_cast_warm)
        is_purple_pix = is_purple_pix & (~is_blue_cast_warm)

    # Neutral silver/grey detection:
    # Only treat cool-tinted pixels with low-moderate saturation (<0.23 and Hue >= 212°) as Silver (e.g. Goku UI hair)
    # when `cool` is the top dominant multi-spool family right below White (`cool_is_top_multi`),
    # so Cyan auras (`Hue < 212°`) and minority Cyan accents (like Gohan's belt & lightning) stay 100% Cyan!
    cool_is_top_multi = bool(cool_idxs and cool_idxs[-1] == k - 2 and len(cool_idxs) >= 2)
    sil_idxs = [i for i, f in enumerate(layer_fams) if f == "silver"]
    if is_custom_layers:
        sil_ratio = layer_ratios[sil_idxs[-1]] if sil_idxs else 1.0
        chroma_ratios = [layer_ratios[i] for i, f in enumerate(layer_fams) if f not in ("dark", "white", "silver")]
        max_chr_r = max(chroma_ratios) if chroma_ratios else 1.0
        sil_rel_scale = float(np.clip((sil_ratio / max(0.25, max_chr_r)) ** 0.65, 0.35, 2.20))
    else:
        sil_rel_scale = 1.0

    white_luma_cut = (
        float(np.clip(0.91 - 0.055 * (layer_ratios[-1] - 1.0), 0.58, 0.97))
        if (is_custom_layers and has_top_white)
        else 0.91
    )
    is_pure_white_pix = ((luma >= white_luma_cut) & (sat_p < 0.18)) | ((luma >= min(0.98, white_luma_cut + 0.04)) & (sat_p < 0.28))
    is_silver_pix = (
        is_pure_white_pix
        | ((~is_rose_pink_cloth) & (luma >= 0.25) & (sat_p < 0.08 * sil_rel_scale))
        | ((~(is_warm_pix | is_gold_pix | is_rose_pink_cloth)) & (luma >= 0.28) & (sat_p < (0.25 if ramps["silver"] is not None else 0.16) * sil_rel_scale))
        | ((~(is_warm_pix | is_gold_pix | is_rose_pink_cloth)) & (~cool_is_top_multi) & (luma >= 0.52) & (sat_p < 0.24 * sil_rel_scale))
        | (cool_is_top_multi & is_cool_pix & (hue_p >= 212.0) & (luma >= 0.30) & (sat_p < 0.23 * sil_rel_scale))
    )

    pixel_z = default_ramp
    pixel_z = np.where(rejected_cool_pix | rejected_purple_pix, np.where(luma < 0.45, base_z, z_silver_target), pixel_z)
    pixel_z = np.where(is_cool_pix, z_cool, pixel_z)
    pixel_z = np.where(is_purple_pix, z_purple, pixel_z)
    pixel_z = np.where(is_green_pix, z_green, pixel_z)
    pixel_z = np.where(is_gold_pix, z_gold, pixel_z)
    pixel_z = np.where(is_warm_pix, z_warm, pixel_z)

    # Apply Silver/White and Deep Black overrides
    pixel_z = np.where(is_silver_pix, z_silver_target, pixel_z)
    pixel_z = np.where(is_pure_white_pix, max_z, pixel_z)
    pixel_z = np.where(is_black_ink, base_z, pixel_z)

    return np.clip(pixel_z, base_z, max_z)


def _rgb_to_cielab_array(rgb_arr: np.ndarray) -> np.ndarray:
    """
    Vectorized sRGB [0..255] -> CIE L*a*b* (D65 illuminant).
    Works on any shape (..., 3) float32 array.
    Returns (..., 3) float32 with L* in [0..100], a* and b* in [-128..127].
    """
    rgb = np.clip(rgb_arr.astype(np.float32) / 255.0, 0.0, 1.0)
    lin = np.where(rgb > 0.04045, np.power((rgb + 0.055) / 1.055, 2.4), rgb / 12.92)
    r, g, b = lin[..., 0], lin[..., 1], lin[..., 2]

    # Normalized D65 XYZ
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = (0.2126729 * r + 0.7151522 * g + 0.0721750 * b) / 1.00000
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883

    eps = 0.008856451679  # (6/29)^3
    kappa = 7.787037037   # 1 / (3 * (6/29)^2)
    c_off = 16.0 / 116.0

    fx = np.where(x > eps, np.cbrt(np.maximum(x, 1e-9)), kappa * x + c_off)
    fy = np.where(y > eps, np.cbrt(np.maximum(y, 1e-9)), kappa * y + c_off)
    fz = np.where(z > eps, np.cbrt(np.maximum(z, 1e-9)), kappa * z + c_off)

    L = 116.0 * fy - 16.0
    a = 500.0 * (fx - fy)
    b_lab = 200.0 * (fy - fz)
    return np.stack([L, a, b_lab], axis=-1).astype(np.float32)


def _build_valid_optical_z_lut(
    specs: List[ColorLayerSpec],
    td_mm: float = 2.0,
    steps_per_layer: int = 14,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Builds a 1D Look-Up Table of physically valid printable Z heights `z_lut` (M,),
    their forward-simulated RGB colors `rgb_lut` (M, 3), and their CIELAB colors `lab_lut` (M, 3).
    Automatically excludes the [0..42%) inter-family color-blocking transition zone when a new
    chromatic family starts over an unrelated family so the inverse solver never exploits muddy
    cross-family bleed to approximate unrelated colors!
    """
    k = len(specs)
    base_z = float(specs[0].end_mm)
    rgbs = np.array([s.rgb for s in specs], dtype=np.float32)
    layer_fams = [_classify_layer_family(s.rgb, i, k) for i, s in enumerate(specs)]
    fam_counts = {f: layer_fams.count(f) for f in set(layer_fams)}

    z_list = [base_z]
    prev_z = base_z
    for idx in range(1, k):
        top_z = float(specs[idx].end_mm)
        prev_f = layer_fams[idx - 1]
        curr_f = layer_fams[idx]
        if prev_f not in ("dark", "white") and curr_f not in ("dark", "white") and curr_f != prev_f:
            # Start candidate heights at 43% into the layer (where opaque color-blocking is complete)
            entry_z = prev_z + 0.43 * (top_z - prev_z)
            z_seg = np.linspace(entry_z, top_z, steps_per_layer, dtype=np.float32)
        else:
            z_seg = np.linspace(prev_z, top_z, steps_per_layer, dtype=np.float32)[1:]
        z_list.extend(z_seg.tolist())
        prev_z = top_z

    z_lut = np.array(sorted(set(round(float(z), 4) for z in z_list)), dtype=np.float32)
    m_len = len(z_lut)
    out_rgb = np.zeros((m_len, 3), dtype=np.float32)
    out_rgb[:, :] = rgbs[0]

    prev_z = base_z
    for idx in range(1, k):
        top_z = float(specs[idx].end_mm)
        span = max(0.08, top_z - prev_z)
        thick = np.clip(z_lut - prev_z, 0.0, span)
        layer_td = max(0.2, float(specs[idx].td_mm or td_mm))
        norm_t = thick / span

        prev_f = layer_fams[idx - 1]
        curr_f = layer_fams[idx]
        if prev_f not in ("dark", "white") and curr_f not in ("dark", "white") and curr_f != prev_f:
            blend_factor = np.clip(norm_t / 0.42, 0.0, 1.0)[:, None]
            shade_t = np.clip((norm_t - 0.42) / 0.58, 0.0, 1.0)[:, None]
            if curr_f == "gold":
                warm_base = np.array([185.0, 105.0, 20.0], dtype=np.float32)
                shadow_rgb = 0.32 * warm_base + 0.68 * rgbs[idx]
            elif curr_f == "warm" and fam_counts.get("warm", 1) >= 3:
                shadow_rgb = 0.76 * rgbs[0] + 0.24 * rgbs[idx]
            else:
                shadow_rgb = 0.38 * rgbs[0] + 0.62 * rgbs[idx]
            layer_rgb = shadow_rgb[None, :] * (1.0 - shade_t) + rgbs[idx][None, :] * shade_t
            out_rgb = out_rgb * (1.0 - blend_factor) + layer_rgb * blend_factor
        else:
            exponent = max(0.35, min(1.5, 1.0 / (layer_td * 0.58)))
            blend_factor = np.power(norm_t, exponent)[:, None]
            out_rgb = out_rgb * (1.0 - blend_factor) + rgbs[idx][None, :] * blend_factor

        prev_z = top_z

    rgb_lut = np.clip(out_rgb, 0.0, 255.0)
    lab_lut = _rgb_to_cielab_array(rgb_lut)
    return z_lut, rgb_lut, lab_lut


def compute_cielab_optical_pixel_z(
    arr_rgb: np.ndarray,
    luma: np.ndarray,
    specs: List[ColorLayerSpec],
    td_mm: float = 2.0,
) -> np.ndarray:
    """
    Inverse Optical Solver in Perceptual CIELAB Space (`color_engine = "cie_delta_e"`):
    For every pixel (y, x), evaluates all valid printable heights `z_m` in the 1D Beer-Lambert LUT
    and selects the height `z^*(y,x)` that minimizes the perceptual CIELAB color error ΔE*ab
    combined with continuous 3D luminance regularization:
      Cost(z_m) = 1.0 * ΔL*^2 + 1.55 * (Δa*^2 + Δb*^2) + 0.06 * ΔZ_reg^2
    Applies soft-argmin local refinement + edge-aware micro-smoothing so the 3D mesh slices cleanly.
    """
    base_z = float(specs[0].end_mm)
    max_z = max(float(specs[-1].end_mm), base_z + 0.1)
    z_luma = base_z + luma * (max_z - base_z)

    k = len(specs)
    if k <= 2:
        return z_luma

    z_lut, _, lab_lut = _build_valid_optical_z_lut(specs, td_mm=td_mm, steps_per_layer=14)
    img_lab = _rgb_to_cielab_array(arr_rgb)

    # Blend true CIELAB L* (55%) with detail-enhanced luma (45%) so manga line-art & unsharp mask sculpt the 3D surface
    target_L = 0.55 * img_lab[:, :, 0] + 0.45 * (luma * 100.0)
    target_a = img_lab[:, :, 1]
    target_b = img_lab[:, :, 2]

    # Vectorized evaluation over M LUT heights: shape (M, H, W)
    dL = lab_lut[:, 0][:, None, None] - target_L[None, :, :]
    da = lab_lut[:, 1][:, None, None] - target_a[None, :, :]
    db = lab_lut[:, 2][:, None, None] - target_b[None, :, :]
    dZ = ((z_lut[:, None, None] - z_luma[None, :, :]) / max(0.1, max_z - base_z)) * 100.0

    cost_vol = (dL * dL) + 2.25 * (da * da + db * db) + 0.025 * (dZ * dZ)

    # Soft-min weighted average around the top-3 lowest-cost Z candidates for smooth sub-step interpolation
    best_idx = np.argmin(cost_vol, axis=0)
    m_len = len(z_lut)
    idx_lo = np.maximum(0, best_idx - 1)
    idx_hi = np.minimum(m_len - 1, best_idx + 1)

    rows, cols = np.indices(best_idx.shape)
    c_mid = cost_vol[best_idx, rows, cols]
    c_lo = cost_vol[idx_lo, rows, cols]
    c_hi = cost_vol[idx_hi, rows, cols]

    w_mid = 1.0 / np.maximum(1.0, c_mid)
    w_lo = np.exp(-np.clip((c_lo - c_mid) / 18.0, 0.0, 20.0)) / np.maximum(1.0, c_lo)
    w_hi = np.exp(-np.clip((c_hi - c_mid) / 18.0, 0.0, 20.0)) / np.maximum(1.0, c_hi)
    w_sum = w_mid + w_lo + w_hi

    pixel_z = (w_mid * z_lut[best_idx] + w_lo * z_lut[idx_lo] + w_hi * z_lut[idx_hi]) / w_sum

    # Anchor deep ink shadows and pure white highlights cleanly
    _, sat_p, _ = _rgb_array_to_hsv_deg(arr_rgb.astype(np.float32))
    pixel_z = np.where((luma >= 0.94) & (sat_p < 0.16), max_z, pixel_z)
    pixel_z = np.where(luma <= 0.11, base_z, pixel_z)

    # Light smoothing to eliminate isolated 1-pixel staircase jumps while keeping crisp edges
    pixel_z = gaussian_filter(pixel_z, sigma=0.30)
    return np.clip(pixel_z, base_z, max_z)


def compute_mean_cielab_delta_e(img_rgb: np.ndarray, rendered_rgb: np.ndarray) -> float:
    """
    Computes the mean perceptual CIE76 ΔE*ab between the cropped target image and the simulated HueForge print.
    """
    lab1 = _rgb_to_cielab_array(img_rgb)
    lab2 = _rgb_to_cielab_array(rendered_rgb)
    de = np.sqrt(np.sum((lab1 - lab2) ** 2, axis=-1))
    return round(float(np.mean(de)), 2)


def optimize_layer_order_cielab(
    img_rgb: np.ndarray,
    specs: List[ColorLayerSpec],
    aspect_ratio: float = 1.0,
    zoom: float = 1.0,
    offset_x_pct: float = 0.0,
    offset_y_pct: float = 0.0,
    detail_boost: float = 1.2,
    contrast_gamma: float = 1.0,
    td_mm: float = 2.0,
) -> Tuple[List[ColorLayerSpec], float, float]:
    """
    Searches for the vertical ordering of the intermediate filament spools (keeping Base Layer 0
    and Top Highlight Layer K-1 anchored) that minimizes the perceptual CIELAB ΔE error on the image.
    Groups spools of the same chromatic family contiguously (sorted dark-to-light within each family)
    so physical printing stays optically clean.
    Returns `(optimized_specs, delta_e_before, delta_e_after)`.
    """
    import itertools

    k = len(specs)
    if k <= 3:
        return specs, 0.0, 0.0

    # Downsample cropped image to 72x72 for ultra-fast (<25ms) permutation evaluation
    tw = 72
    th = max(36, int(round(tw / max(0.25, aspect_ratio))))
    if th > 72:
        th = 72
        tw = max(36, int(round(th * aspect_ratio)))

    thumb = _crop_and_resample_image(img_rgb, tw, th, zoom=zoom, offset_x_pct=offset_x_pct, offset_y_pct=offset_y_pct)
    thumb_luma = compute_enhanced_luminance(thumb, detail_boost=detail_boost, contrast_gamma=contrast_gamma, smoothing_sigma=0.20)
    thumb_lab = _rgb_to_cielab_array(thumb)
    target_L = 0.55 * thumb_lab[:, :, 0] + 0.45 * (thumb_luma * 100.0)
    target_a = thumb_lab[:, :, 1]
    target_b = thumb_lab[:, :, 2]

    def _eval_specs_de(cand_specs: List[ColorLayerSpec]) -> float:
        _, _, lab_lut = _build_valid_optical_z_lut(cand_specs, td_mm=td_mm, steps_per_layer=8)
        dL = lab_lut[:, 0][:, None, None] - target_L[None, :, :]
        da = lab_lut[:, 1][:, None, None] - target_a[None, :, :]
        db = lab_lut[:, 2][:, None, None] - target_b[None, :, :]
        de_sq = (dL * dL) + 1.45 * (da * da + db * db)
        min_de = np.sqrt(np.min(de_sq, axis=0))
        return float(np.mean(min_de))

    de_before = round(_eval_specs_de(specs), 2)

    # Group intermediate layers (1 .. k-2) by their HSV family (sorted by luminance inside each family)
    mid_specs = list(specs[1 : k - 1])
    fam_groups: Dict[str, List[ColorLayerSpec]] = {}
    for sp in mid_specs:
        fam = _classify_layer_family(sp.rgb, 1, k)
        fam_groups.setdefault(fam, []).append(sp)
    for fam in fam_groups:
        fam_groups[fam].sort(key=lambda s: s.luminance)

    group_keys = list(fam_groups.keys())
    best_order_mid = mid_specs
    best_de = de_before

    # Test all permutations of family groups (and if <= 4 intermediate layers total, also test all individual permutations)
    tested_hex_tuples = set()
    candidate_mid_lists: List[List[ColorLayerSpec]] = []

    for perm_fams in itertools.permutations(group_keys):
        flat = [sp for f in perm_fams for sp in fam_groups[f]]
        ht = tuple(s.hex_color for s in flat)
        if ht not in tested_hex_tuples:
            tested_hex_tuples.add(ht)
            candidate_mid_lists.append(flat)

    if len(mid_specs) <= 4:
        for perm_sp in itertools.permutations(mid_specs):
            ht = tuple(s.hex_color for s in perm_sp)
            if ht not in tested_hex_tuples:
                tested_hex_tuples.add(ht)
                candidate_mid_lists.append(list(perm_sp))

    for cand_mid in candidate_mid_lists:
        full_seq = [specs[0]] + cand_mid + [specs[-1]]
        # Rebuild specs keeping the original layer height boundaries (`end_layer_num`, `start_mm`, `end_mm`)
        rebuilt: List[ColorLayerSpec] = []
        for idx_s, orig_slot in enumerate(specs):
            chosen_color_sp = full_seq[idx_s]
            rebuilt.append(
                ColorLayerSpec(
                    layer_index=idx_s + 1,
                    cfs_slot=orig_slot.cfs_slot,
                    hex_color=chosen_color_sp.hex_color,
                    rgb=chosen_color_sp.rgb,
                    luminance=chosen_color_sp.luminance,
                    start_mm=orig_slot.start_mm,
                    end_mm=orig_slot.end_mm,
                    start_layer_num=orig_slot.start_layer_num,
                    end_layer_num=orig_slot.end_layer_num,
                    td_mm=chosen_color_sp.td_mm,
                    spool_id=chosen_color_sp.spool_id,
                    spool_label=chosen_color_sp.spool_label,
                )
            )
        score = _eval_specs_de(rebuilt)
        if score < best_de - 0.05:
            best_de = score
            best_order_mid = cand_mid

    final_seq = [specs[0]] + best_order_mid + [specs[-1]]
    final_specs: List[ColorLayerSpec] = []
    for idx_s, orig_slot in enumerate(specs):
        chosen_color_sp = final_seq[idx_s]
        final_specs.append(
            ColorLayerSpec(
                layer_index=idx_s + 1,
                cfs_slot=orig_slot.cfs_slot,
                hex_color=chosen_color_sp.hex_color,
                rgb=chosen_color_sp.rgb,
                luminance=chosen_color_sp.luminance,
                start_mm=orig_slot.start_mm,
                end_mm=orig_slot.end_mm,
                start_layer_num=orig_slot.start_layer_num,
                end_layer_num=orig_slot.end_layer_num,
                td_mm=chosen_color_sp.td_mm,
                spool_id=chosen_color_sp.spool_id,
                spool_label=chosen_color_sp.spool_label,
            )
        )
    return final_specs, de_before, round(best_de, 2)


def _rasterize_layout_masks(
    tiles: List[Tuple[str, sg.Polygon]],
    border_style: BorderStyle,
    border_width_mm: float,
    pw: int,
    ph: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Rasterizes the exact geometric layout `tiles` onto a `(ph, pw)` boolean mask pair:
      - `inside_mask`: True inside the tile polygons (with a crisp 1.5px visual gap between multi-frame tiles).
      - `rim_mask`: True inside the raised/recessed border rim around each tile.
    """
    union_poly = sg.MultiPolygon([t[1] for t in tiles])
    minx, miny, maxx, maxy = union_poly.bounds
    span_x = max(1e-3, maxx - minx)
    span_y = max(1e-3, maxy - miny)

    # Slight padding (2.5%) so the outer border rim and drop shadow fit cleanly inside the studio frame
    pad_x = span_x * 0.025
    pad_y = span_y * 0.025
    vx0, vx1 = minx - pad_x, maxx + pad_x
    vy0, vy1 = miny - pad_y, maxy + pad_y
    v_span_x = vx1 - vx0
    v_span_y = vy1 - vy0

    def _to_px(coords_seq) -> List[Tuple[float, float]]:
        pts = []
        for x, y in coords_seq:
            px = ((x - vx0) / v_span_x) * (pw - 1)
            py = (1.0 - (y - vy0) / v_span_y) * (ph - 1)
            pts.append((float(px), float(py)))
        return pts

    img_inside = Image.new("L", (pw, ph), 0)
    draw_inside = ImageDraw.Draw(img_inside)

    img_rim = Image.new("L", (pw, ph), 0)
    draw_rim = ImageDraw.Draw(img_rim)

    is_multi = len(tiles) > 1
    gap_mm = min(1.2, span_x * 0.004) if is_multi else 0.0

    for _, poly in tiles:
        vis_poly = poly.buffer(-gap_mm, join_style=2) if gap_mm > 0.05 else poly
        if vis_poly.is_empty or not isinstance(vis_poly, sg.Polygon):
            vis_poly = poly
        ext_pts = _to_px(vis_poly.exterior.coords[:-1])
        if len(ext_pts) >= 3:
            draw_inside.polygon(ext_pts, fill=255)

        if border_style in ("raised_top", "recessed_base") and border_width_mm > 0.2:
            inner_p = vis_poly.buffer(-float(border_width_mm), join_style=2)
            if len(ext_pts) >= 3:
                draw_rim.polygon(ext_pts, fill=255)
            if not inner_p.is_empty and isinstance(inner_p, sg.Polygon):
                in_pts = _to_px(inner_p.exterior.coords[:-1])
                if len(in_pts) >= 3:
                    draw_rim.polygon(in_pts, fill=0)

    inside_mask = np.asarray(img_inside, dtype=np.uint8) > 127
    rim_mask = (np.asarray(img_rim, dtype=np.uint8) > 127) & inside_mask
    return inside_mask, rim_mask


def prepare_specs_for_art_style(
    specs: List[ColorLayerSpec],
    art_style: ArtStyle = "standard",
) -> List[ColorLayerSpec]:
    """
    Adapts the filament layer stack to the selected `art_style`:
      - `stained_glass_ink`: Reorders layers so Brightest/White is at `Layer 1` (bottom),
        vivid chromatic spools in the middle, and Darkest/Black at `Layer K` (top raised outlines).
      - `intaglio_splash`: Ensures `Layer 1` is Pure Black (`#0C0D12`), `Layer K` is Pure White (`#FFFFFF`),
        and if the intermediate layers contain cold sky/space blue spools from the removed background,
        replaces them with a vibrant Warm Paint-Splatter & Stencil ramp (Orange ➔ Golden Yellow ➔ Warm Cream).
      - Other styles: If switching back from `stained_glass_ink`, restores Dark-to-Light bottom-to-top order.
    """
    if len(specs) < 3:
        return specs

    sorted_by_luma = sorted(specs, key=lambda s: s.luminance)
    darkest_sp = sorted_by_luma[0]
    brightest_sp = sorted_by_luma[-1]
    middle_sps = [s for s in specs if s is not darkest_sp and s is not brightest_sp]

    if art_style == "stained_glass_ink":
        middle_sps.sort(key=lambda s: -s.luminance)
        new_color_order = [brightest_sp] + middle_sps + [darkest_sp]
    elif art_style == "intaglio_splash":
        # Check if middle spools contain cold blue/purple background colors (b > r + 15) from a space/sky backdrop
        has_cold_sky_spools = any((sp.rgb[2] > sp.rgb[0] + 15) for sp in middle_sps)
        middle_sps.sort(key=lambda s: s.luminance)
        if has_cold_sky_spools:
            warm_ramp_Pool = [
                ("#D94A18", (217, 74, 24), 0.38),
                ("#E86F1C", (232, 111, 28), 0.51),
                ("#F5A623", (245, 166, 35), 0.67),
                ("#FAD275", (250, 210, 117), 0.82),
                ("#FCE6A6", (252, 230, 166), 0.90),
                ("#FFF2CC", (255, 242, 204), 0.94),
            ]
            n_mid = len(middle_sps)
            idxs = np.linspace(0, min(len(warm_ramp_Pool) - 1, max(1, n_mid)), n_mid, dtype=int)
            rebuilt_mid: List[ColorLayerSpec] = []
            for m_i, orig_m in enumerate(middle_sps):
                hx, rgb_t, lum_t = warm_ramp_Pool[idxs[m_i]]
                rebuilt_mid.append(
                    ColorLayerSpec(
                        layer_index=orig_m.layer_index,
                        cfs_slot=orig_m.cfs_slot,
                        hex_color=hx,
                        rgb=rgb_t,
                        luminance=lum_t,
                        start_mm=orig_m.start_mm,
                        end_mm=orig_m.end_mm,
                        start_layer_num=orig_m.start_layer_num,
                        end_layer_num=orig_m.end_layer_num,
                        td_mm=orig_m.td_mm,
                        spool_id=None,
                        spool_label=None,
                    )
                )
            middle_sps = rebuilt_mid

        black_base = ColorLayerSpec(
            layer_index=1,
            cfs_slot=specs[0].cfs_slot,
            hex_color="#0C0D12" if darkest_sp.luminance > 0.15 else darkest_sp.hex_color,
            rgb=(12, 13, 18) if darkest_sp.luminance > 0.15 else darkest_sp.rgb,
            luminance=0.05,
            start_mm=specs[0].start_mm,
            end_mm=specs[0].end_mm,
            start_layer_num=specs[0].start_layer_num,
            end_layer_num=specs[0].end_layer_num,
            td_mm=darkest_sp.td_mm,
            spool_id=darkest_sp.spool_id,
            spool_label=darkest_sp.spool_label,
        )
        white_top = ColorLayerSpec(
            layer_index=len(specs),
            cfs_slot=specs[-1].cfs_slot,
            hex_color="#FFFFFF",
            rgb=(250, 250, 252),
            luminance=0.99,
            start_mm=specs[-1].start_mm,
            end_mm=specs[-1].end_mm,
            start_layer_num=specs[-1].start_layer_num,
            end_layer_num=specs[-1].end_layer_num,
            td_mm=brightest_sp.td_mm,
            spool_id=brightest_sp.spool_id,
            spool_label=brightest_sp.spool_label,
        )
        new_color_order = [black_base] + middle_sps + [white_top]
    else:
        if specs[0].luminance > specs[-1].luminance + 0.10:
            middle_sps.sort(key=lambda s: s.luminance)
            new_color_order = [darkest_sp] + middle_sps + [brightest_sp]
        else:
            return specs

    rebuilt: List[ColorLayerSpec] = []
    for idx_s, orig_slot in enumerate(specs):
        c_sp = new_color_order[idx_s]
        rebuilt.append(
            ColorLayerSpec(
                layer_index=idx_s + 1,
                cfs_slot=orig_slot.cfs_slot,
                hex_color=c_sp.hex_color,
                rgb=c_sp.rgb,
                luminance=c_sp.luminance,
                start_mm=orig_slot.start_mm,
                end_mm=orig_slot.end_mm,
                start_layer_num=orig_slot.start_layer_num,
                end_layer_num=orig_slot.end_layer_num,
                td_mm=c_sp.td_mm,
                spool_id=c_sp.spool_id,
                spool_label=c_sp.spool_label,
            )
        )
    return rebuilt


def _snap_z_to_terraces(
    pixel_z: np.ndarray,
    specs: List[ColorLayerSpec],
    sub_steps_per_layer: int = 1,
    blend_ratio: float = 0.85,
) -> np.ndarray:
    """
    Quantizes continuous `pixel_z` heights onto discrete flat horizontal terraces (`specs[i].end_mm`)
    for Stepped / Paper-Cut / Intaglio relief modes.
    """
    base_z = float(specs[0].end_mm)
    levels = [base_z]
    prev_z = base_z
    for sp in specs[1:]:
        top_z = float(sp.end_mm)
        for s_idx in range(1, sub_steps_per_layer + 1):
            levels.append(prev_z + (s_idx / float(sub_steps_per_layer)) * (top_z - prev_z))
        prev_z = top_z
    lvl_arr = np.array(sorted(set(round(z, 4) for z in levels)), dtype=np.float32)
    diffs = np.abs(pixel_z[:, :, None] - lvl_arr[None, None, :])
    nearest_idx = np.argmin(diffs, axis=-1)
    snapped = lvl_arr[nearest_idx]
    return (blend_ratio * snapped + (1.0 - blend_ratio) * pixel_z).astype(np.float32)


def apply_art_style_topography(
    arr_rgb: np.ndarray,
    luma: np.ndarray,
    pixel_z: np.ndarray,
    specs: List[ColorLayerSpec],
    art_style: ArtStyle = "standard",
    art_intensity: float = 1.0,
    void_mask: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Transforms the 3D physical heightfield `pixel_z` according to the selected Artistic Style:
      1. `intaglio_splash`: Lifts outer background to Pure White plateau (`max_z`), generates a
         multi-scale dynamic Ink Splatter & Paint Droplets halo (`specs[1..k-2]`) around the subject,
         and carves the character's dark hair/outlines deep into `base_z` with stepped relief.
      2. `stained_glass_ink`: Works with `prepare_specs_for_art_style` (White at base, Vivid colors in middle,
         Black at top `max_z`). Maps comic/manga ink outlines & deep shadows to the raised top Black layer
         and maps bright colors over the White base.
      3. `papercut_terraced`: Smooths color regions into clean graphic shapes and snaps heights onto flat
         horizontal laser-cut paper terraces (`specs[i].end_mm`).
      4. `halftone_manga`: Modulates midtone layer transitions with a 45°-rotated comic Halftone Dot screen
         so gradients print as tactile 3D micro-pillars.
      5. `cyber_neon`: Plunges background & dark interiors to flat `base_z` and raises glowing edges & high-chroma
         auras to the upper filament layers.
    """
    if art_style == "standard" or len(specs) < 2:
        return pixel_z

    h, w = luma.shape
    k = len(specs)
    base_z = float(specs[0].end_mm)
    max_z = float(specs[-1].end_mm)
    intensity = float(np.clip(art_intensity, 0.25, 2.0))

    # ------------------------------------------------------------------
    # MODE 1 : GRAVURE SPLASH & POCHOIR (Intaglio sur Fond Blanc Haut)
    # ------------------------------------------------------------------
    if art_style == "intaglio_splash":
        from scipy.ndimage import (
            binary_closing,
            binary_dilation,
            binary_fill_holes,
            binary_opening,
            binary_propagation,
            label as nd_label,
            maximum_filter,
            minimum_filter,
        )

        arr_f = arr_rgb.astype(np.float32)
        arr_s = gaussian_filter(arr_f, sigma=(1.6, 1.6, 0.0))
        rs, gs, bs = arr_s[:, :, 0], arr_s[:, :, 1], arr_s[:, :, 2]
        luma_s = (0.2126 * rs + 0.7152 * gs + 0.0722 * bs) / 255.0

        # 1. Extract Character Foreground Silhouette (`subj_mask`) cleanly from dark/blue space or uniform backdrop
        warm_mask = ((rs > bs + 4.0) & (luma_s > 0.08)) | ((rs > gs + 12.0) & (luma_s > 0.09))
        warm_mask = binary_closing(warm_mask, structure=np.ones((5, 5)))

        blue_exc = bs - rs
        has_ink_within = minimum_filter(luma, size=11) < 0.42
        not_soft_white_aura = ~((luma_s > 0.76) & (minimum_filter(luma, size=9) > 0.48) & (blue_exc > 16.0))
        hair_and_ink_domain = (blue_exc < 44.0) & (luma_s > 0.06) & has_ink_within & not_soft_white_aura

        if np.mean(warm_mask) >= 0.02:
            seed = binary_dilation(warm_mask, iterations=4)
            char_connected = binary_propagation(seed, mask=(warm_mask | hair_and_ink_domain))
            char_closed = binary_closing(char_connected | warm_mask, structure=np.ones((5, 5)))
        else:
            # Fallback for non-warm subjects: segment against outer border color
            bw = max(4, int(round(min(h, w) * 0.06)))
            border_samples = np.vstack([
                arr_s[:bw, :, :].reshape(-1, 3),
                arr_s[:, :bw, :].reshape(-1, 3),
                arr_s[:, -bw:, :].reshape(-1, 3),
            ])
            bg_med = np.median(border_samples, axis=0)
            c_dist = np.sqrt(np.sum((arr_s - bg_med[None, None, :]) ** 2, axis=-1)) / 255.0
            local_c = maximum_filter(luma, size=9) - minimum_filter(luma, size=9)
            fg_raw = (c_dist > 0.18) | (local_c > 0.24)
            char_closed = binary_closing(binary_opening(fg_raw, structure=np.ones((3, 3))), structure=np.ones((7, 7)))

        char_filled = binary_fill_holes(char_closed)
        if void_mask is not None and void_mask.shape == char_filled.shape:
            char_filled = char_filled & (~void_mask)

        lbl, num_comp = nd_label(char_filled)
        subj_mask = np.zeros_like(char_filled, dtype=bool)
        for c_i in range(1, num_comp + 1):
            comp = lbl == c_i
            if np.sum(comp) > 0.008 * h * w:
                subj_mask |= comp

        near_void_edge = (
            binary_dilation(void_mask, iterations=5)
            if (void_mask is not None and void_mask.shape == subj_mask.shape and np.any(void_mask))
            else np.zeros_like(subj_mask, dtype=bool)
        )

        dist_out_px = distance_transform_edt(~subj_mask).astype(np.float32)
        dist_in_px = distance_transform_edt(subj_mask).astype(np.float32)
        min_dim = float(max(64, min(h, w)))
        dist_norm = dist_out_px / min_dim
        dist_in_norm = dist_in_px / min_dim

        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        if np.any(warm_mask):
            cy_char = float(np.mean(yy[warm_mask]))
            cx_char = float(np.mean(xx[warm_mask]))
        elif np.any(subj_mask):
            cy_char = float(np.mean(yy[subj_mask]))
            cx_char = float(np.mean(xx[subj_mask]))
        else:
            cy_char, cx_char = 0.52 * h, 0.50 * w

        # 2. Generate Realistic Paint Splatter Halo, Radial Bursts, Diagonal Slashes & Round Droplets
        ang = np.arctan2(yy - cy_char, xx - cx_char)
        rng = np.random.RandomState(42)
        # Resolution-independent noise field interpolated to (h, w)
        base_noise_pil = Image.fromarray((rng.rand(240, 240) * 255.0).astype(np.uint8))
        noise_grid = np.asarray(base_noise_pil.resize((w, h), resample=Image.Resampling.BILINEAR), dtype=np.float32) / 255.0

        def _norm01(a: np.ndarray) -> np.ndarray:
            mn, mx = float(np.min(a)), float(np.max(a))
            return (a - mn) / max(1e-5, mx - mn)

        b_micro = _norm01(gaussian_filter(noise_grid, sigma=max(0.8, min_dim * 0.003)))
        b_fine = _norm01(gaussian_filter(noise_grid, sigma=max(1.7, min_dim * 0.006)))
        b_med = _norm01(gaussian_filter(noise_grid, sigma=max(3.6, min_dim * 0.013)))
        b_large = _norm01(gaussian_filter(noise_grid, sigma=max(7.5, min_dim * 0.028)))

        spikes = (
            0.45
            + 0.24 * np.sin(ang * 11.0 + 0.5)
            + 0.18 * np.cos(ang * 19.0 - 1.2)
            + 0.14 * np.sin(ang * 31.0 + 2.3)
            + 0.10 * np.cos(ang * 53.0 + 0.8)
        )
        torso_weight = np.exp(-((yy - cy_char) / (0.31 * h)) ** 2) * np.exp(-((xx - cx_char) / (0.35 * w)) ** 2)
        splash_reach = (0.145 * torso_weight + 0.022) * intensity * (0.35 + 0.65 * spikes) * (0.45 + 0.55 * b_large)

        radial_frac = dist_norm / np.maximum(0.012, splash_reach)
        in_splash_halo = (~subj_mask) & (dist_norm < splash_reach) & (
            (radial_frac < 0.42)
            | ((0.55 * b_med + 0.30 * b_fine + 0.15 * spikes) > radial_frac * 0.62)
        )

        # Round Paint Droplets & Diagonal Paint Slashes scattered outside the halo
        droplet_mask = np.zeros((h, w), dtype=bool)
        for _ in range(int(95 * intensity)):
            ry = int(np.clip(cy_char + rng.uniform(-0.38, 0.38) * h, 2, h - 3))
            rx = int(np.clip(cx_char + rng.uniform(-0.38, 0.38) * w, 2, w - 3))
            d_val = dist_norm[ry, rx]
            if 0.008 < d_val < 0.18 * intensity:
                rad_px = rng.uniform(1.6, 5.4) * (min_dim / 310.0)
                drop_c = ((yy - ry) ** 2 + (xx - rx) ** 2) <= (rad_px ** 2)
                droplet_mask |= drop_c & (~subj_mask)

        for _ in range(int(16 * intensity)):
            theta = rng.uniform(-math.pi, math.pi)
            cy_s = cy_char + rng.uniform(-0.14, 0.14) * h
            cx_s = cx_char + rng.uniform(-0.12, 0.12) * w
            dx_s = xx - cx_s
            dy_s = yy - cy_s
            along = dx_s * math.cos(theta) + dy_s * math.sin(theta)
            perp = np.abs(-dx_s * math.sin(theta) + dy_s * math.cos(theta))
            slash_line = (
                (along > 0.06 * min_dim)
                & (along < 0.35 * min_dim)
                & (perp < max(1.1, min_dim * 0.0038))
                & (dist_norm < 0.17 * intensity)
                & (~subj_mask)
            )
            droplet_mask |= slash_line

        splash_mask = in_splash_halo | droplet_mask

        # White counter-splatter foam on the boundary between character and splash (and breaking up crop edges)
        subj_y_rows = np.where(np.any(subj_mask, axis=1))[0]
        max_subj_y = float(subj_y_rows[-1]) if len(subj_y_rows) > 0 else float(h - 1)
        min_subj_y = float(subj_y_rows[0]) if len(subj_y_rows) > 0 else 0.0
        near_crop_cut = (
            (yy > max_subj_y - 0.045 * h)
            | (yy < min_subj_y + 0.035 * h)
            | near_void_edge
        )

        white_foam = (
            (
                (dist_norm < 0.048 * intensity)
                | ((dist_in_norm < 0.048 * intensity) & (yy > cy_char - 0.10 * h))
                | (near_crop_cut & (b_med > 0.40))
            )
            & ((0.60 * b_fine + 0.40 * b_micro) > 0.64)
            & (b_med > 0.46)
        )

        # 3. Graphic 4-Level Comic Stencil Intaglio inside `subj_mask`
        is_hair_region = subj_mask & (~warm_mask)
        local_mean_fine = gaussian_filter(luma, sigma=max(1.5, min_dim * 0.006))
        local_mean_broad = gaussian_filter(luma, sigma=max(4.5, min_dim * 0.018))
        dog_fine = luma - local_mean_fine
        dog_broad = luma - local_mean_broad

        char_black = subj_mask & (
            (luma < 0.17)
            | (dog_fine < -0.028)
            | (dog_broad < -0.052)
            | (is_hair_region & (((dist_in_norm < 0.013) & (~near_crop_cut)) | (luma < 0.52) | (dog_broad < -0.006)))
            | ((dist_in_norm < 0.009) & (luma < 0.70) & (~near_crop_cut))
        )

        char_white = subj_mask & (~char_black) & (
            ((~is_hair_region) & (luma >= 0.65))
            | (is_hair_region & (luma >= 0.68) & (dog_broad > 0.015))
        )

        char_gold = subj_mask & (~char_black) & (~char_white) & (
            ((~is_hair_region) & (luma >= 0.38))
            | (is_hair_region & (luma >= 0.48))
        )
        char_orange = subj_mask & (~char_black) & (~char_white) & (~char_gold)

        # Map the 4 stencil levels onto the filament stack heights:
        # - z_black = specs[0].end_mm (Base Black)
        # - z_orange = specs[1].end_mm (Deep Splash Orange)
        # - z_gold = specs[min(k-2, max(2, k//2))].end_mm (Bright Gold / Mid Splash)
        # - z_white = specs[-1].end_mm (Top Pure White Plateau)
        z_black = base_z
        z_orange = float(specs[min(1, k - 1)].end_mm)
        gold_idx = min(k - 2, max(2, (k - 1) // 2 + 1)) if k >= 4 else min(1, k - 1)
        z_gold = float(specs[gold_idx].end_mm)
        z_white = max_z

        out_z = np.full_like(pixel_z, z_white)
        splash_is_gold = splash_mask & (((radial_frac < 0.58) & (b_fine > 0.38)) | (b_med > 0.62))
        out_z = np.where(splash_mask, np.where(splash_is_gold, z_gold, z_orange), out_z)

        out_z = np.where(char_orange, z_orange, out_z)
        out_z = np.where(char_gold, z_gold, out_z)
        out_z = np.where(char_white, z_white, out_z)
        out_z = np.where(char_black, z_black, out_z)

        face_core = (np.abs(yy - (cy_char - 0.12 * h)) < 0.12 * h) & (np.abs(xx - cx_char) < 0.12 * w)
        out_z = np.where(white_foam & (~face_core) & (~(char_black & (dist_in_norm > 0.022))), z_white, out_z)
        return np.clip(out_z, base_z, max_z)

    # ------------------------------------------------------------------
    # MODE 2 : VITRAIL / COMIC ENCRÉ (Traits Noirs en Relief Haut Z_max)
    # ------------------------------------------------------------------
    if art_style == "stained_glass_ink":
        # Note: `specs` has already been reordered by `prepare_specs_for_art_style` so:
        #   specs[0] = White (bottom base)
        #   specs[1 .. k-2] = Vivid Colors
        #   specs[k-1] = Black (top raised ink & frame)
        gy, gx = np.gradient(luma)
        edge_mag = np.hypot(gx, gy)
        dog = gaussian_filter(luma, sigma=0.65) - gaussian_filter(luma, sigma=2.1)

        ink_thresh = 0.23 * intensity
        is_black_ink = (
            (luma <= min(0.32, ink_thresh))
            | ((luma <= 0.48) & (dog < -0.042 / max(0.5, intensity)))
            | ((luma <= 0.55) & (edge_mag > 0.16 / max(0.5, intensity)))
        )

        _, sat_p, _ = _rgb_array_to_hsv_deg(arr_rgb.astype(np.float32))
        is_white_bg = (luma >= 0.86) & (sat_p < 0.20) & (~is_black_ink)

        # Match every non-ink, non-white pixel to its closest chromatic layer in specs[1 .. k-2]
        if k >= 3:
            mid_specs = specs[1 : k - 1]
            mid_rgbs = np.array([s.rgb for s in mid_specs], dtype=np.float32)
            mid_lab = _rgb_to_cielab_array(mid_rgbs)
            img_lab = _rgb_to_cielab_array(arr_rgb)
            d_ab = (
                0.35 * (mid_lab[:, 0][:, None, None] - img_lab[:, :, 0][None, :, :]) ** 2
                + 1.65 * (
                    (mid_lab[:, 1][:, None, None] - img_lab[:, :, 1][None, :, :]) ** 2
                    + (mid_lab[:, 2][:, None, None] - img_lab[:, :, 2][None, :, :]) ** 2
                )
            )
            best_mid_idx = np.argmin(d_ab, axis=0)
            mid_top_zs = np.array([float(s.end_mm) for s in mid_specs], dtype=np.float32)
            mid_bot_zs = np.array([float(specs[i].end_mm) for i in range(0, k - 2)], dtype=np.float32)
            z_top_sel = mid_top_zs[best_mid_idx]
            z_bot_sel = mid_bot_zs[best_mid_idx]
            # Deeper/more saturated color fills up to 100% of its chromatic layer; lighter tint uses 55..95% so White base shines through!
            color_weight = np.clip(0.55 + 0.45 * (1.0 - luma) + 0.25 * sat_p, 0.52, 1.0)
            color_z = z_bot_sel + color_weight * (z_top_sel - z_bot_sel)
        else:
            color_z = np.full_like(pixel_z, base_z)

        out_z = color_z
        out_z = np.where(is_white_bg, base_z, out_z)
        out_z = np.where(is_black_ink, max_z, out_z)
        return np.clip(out_z, base_z, max_z)

    # ------------------------------------------------------------------
    # MODE 3 : PAPIER DÉCOUPÉ 3D / SHADOWBOX (Paliers Plats & Lisses)
    # ------------------------------------------------------------------
    if art_style == "papercut_terraced":
        # Smooth out micro-texture noise while keeping main contours, then snap to flat horizontal layer terraces
        smooth_sigma = max(0.8, 1.35 * intensity)
        z_smooth = gaussian_filter(pixel_z, sigma=smooth_sigma)
        terraced_z = _snap_z_to_terraces(z_smooth, specs, sub_steps_per_layer=1, blend_ratio=0.95)
        # Preserve crisp dark outlines at base_z
        terraced_z = np.where(luma <= 0.14, base_z, terraced_z)
        return np.clip(terraced_z, base_z, max_z)

    # ------------------------------------------------------------------
    # MODE 4 : POP-ART TRAME MANGA / SPIDER-VERSE (Halftone Dots 3D)
    # ------------------------------------------------------------------
    if art_style == "halftone_manga":
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        # Calibrate dot pitch so roughly ~65..95 halftone dots span the width
        pitch_px = max(4.2, (min(h, w) / (78.0 / max(0.5, intensity))))
        omega = (2.0 * math.pi) / pitch_px
        rot_u = 0.70710678 * (xx - yy)
        rot_v = 0.70710678 * (xx + yy)
        # Cosine halftone screen in [0.12 .. 0.88]
        screen = 0.50 + 0.38 * np.cos(omega * rot_u) * np.cos(omega * rot_v)

        layer_tops = np.array([float(s.end_mm) for s in specs], dtype=np.float32)
        out_z = pixel_z.copy()
        for idx in range(1, k):
            z_lo = layer_tops[idx - 1]
            z_hi = layer_tops[idx]
            in_band = (pixel_z > z_lo) & (pixel_z <= z_hi)
            frac = np.clip((pixel_z - z_lo) / max(0.04, z_hi - z_lo), 0.0, 1.0)
            # Dither fractional thickness against the 2D halftone dot screen
            dot_on = frac >= screen
            z_dithered = np.where(dot_on, z_hi, z_lo + 0.15 * (z_hi - z_lo))
            out_z = np.where(in_band, z_dithered, out_z)

        # Keep deep manga ink lines and pure white highlights un-dithered and razor-sharp
        out_z = np.where(luma <= 0.16, base_z, out_z)
        out_z = np.where(luma >= 0.93, max_z, out_z)
        return np.clip(out_z, base_z, max_z)

    # ------------------------------------------------------------------
    # MODE 5 : NÉON CYBERPUNK / AURA ÉLECTRIQUE (Fond Noir Bas + Contours Hauts)
    # ------------------------------------------------------------------
    if art_style == "cyber_neon":
        gy, gx = np.gradient(luma)
        edge_glow = np.hypot(gx, gy)
        edge_glow = np.clip(edge_glow * 3.2 * intensity, 0.0, 1.0)
        edge_halo = gaussian_filter(edge_glow, sigma=1.6)

        _, sat_p, val_p = _rgb_array_to_hsv_deg(arr_rgb.astype(np.float32))
        neon_energy = np.clip(
            0.65 * edge_glow + 0.45 * edge_halo + 0.75 * (sat_p * val_p) + np.clip((luma - 0.65) * 2.2, 0.0, 1.0),
            0.0,
            1.0,
        )
        # Suppress dull dark/mid backgrounds down to base_z (Black), while boosting neon contours & vivid aura
        neon_z = base_z + (pixel_z - base_z) * np.power(neon_energy, 1.15)
        neon_z = np.where(edge_glow > 0.58, np.maximum(neon_z, base_z + 0.82 * (max_z - base_z)), neon_z)
        neon_z = np.where(luma >= 0.90, max_z, neon_z)
        return np.clip(neon_z, base_z, max_z)

    return pixel_z


def apply_3d_relief_shading_preview(
    out_rgb: np.ndarray,
    pixel_z: np.ndarray,
    base_z: float,
    max_z: float,
    art_style: ArtStyle = "standard",
) -> np.ndarray:
    """
    Adds a subtle directional 3D hillshade & step-wall shadow cue on the 2D Studio Preview
    so that carved intaglio trenches, raised black outlines, paper-cut terraces, and 3D halftone dots
    are immediately visible at a glance just like in a raking-light photograph!
    """
    span_z = max(0.2, float(max_z - base_z))
    norm_z = (pixel_z - base_z) / span_z
    dz_dy, dz_dx = np.gradient(norm_z)
    # Directional light from top-left (-1, -1)
    slope_light = (-dz_dx - dz_dy) * (2.6 if art_style != "standard" else 0.85)
    shade_mult = np.clip(1.0 + slope_light, 0.68, 1.16)[:, :, None]
    return np.clip(out_rgb * shade_mult, 0.0, 255.0)


def render_quantized_preview_base64(
    img_rgb: np.ndarray,
    specs: List[ColorLayerSpec],
    aspect_ratio: float = 1.0,
    zoom: float = 1.0,
    offset_x_pct: float = 0.0,
    offset_y_pct: float = 0.0,
    detail_boost: float = 1.2,
    contrast_gamma: float = 1.0,
    td_mm: float = 2.0,
    color_engine: Literal["hsv_ramp", "cie_delta_e"] = "hsv_ramp",
    fill_mode: FillMode = "smart_aura",
    art_style: ArtStyle = "standard",
    art_intensity: float = 1.0,
    tiles: Optional[List[Tuple[str, sg.Polygon]]] = None,
    border_style: BorderStyle = "raised_top",
    border_width_mm: float = 2.5,
    return_dual_studio: bool = False,
    highlight_layer_idx: Optional[int] = None,
) -> Any:
    """
    Simulates the HueForge 1D Z-stack filament blending directly from `pixel_z`,
    returning a sharp base64 PNG data URL cut out to the exact geometric shape (`tiles`)
    with its raised/recessed border rim!
    When `return_dual_studio=True`, returns `(hueforge_b64, source_framing_b64, void_pct)`.
    """
    pw = 500
    ph = max(160, int(round(pw / max(0.25, aspect_ratio))))
    if ph > 500:
        ph = 500
        pw = max(160, int(round(ph * aspect_ratio)))

    effective_fill: FillMode = "smart_aura" if fill_mode == "none_preview" else fill_mode
    small, void_mask = _crop_and_resample_image(
        img_rgb,
        pw,
        ph,
        zoom=zoom,
        offset_x_pct=offset_x_pct,
        offset_y_pct=offset_y_pct,
        fill_mode=effective_fill,
        return_void_mask=True,
    )
    luma = compute_enhanced_luminance(small, detail_boost=detail_boost, contrast_gamma=contrast_gamma, smoothing_sigma=0.25)

    base_z = specs[0].end_mm
    max_z = specs[-1].end_mm
    if art_style == "stained_glass_ink":
        pixel_z = apply_art_style_topography(
            small, luma, np.full_like(luma, base_z), specs, art_style=art_style, art_intensity=art_intensity, void_mask=void_mask
        )
    else:
        if color_engine == "cie_delta_e":
            pixel_z = compute_cielab_optical_pixel_z(small, luma, specs, td_mm=td_mm)
        else:
            pixel_z = compute_chroma_aware_pixel_z(small, luma, specs)
        if art_style != "standard":
            pixel_z = apply_art_style_topography(
                small, luma, pixel_z, specs, art_style=art_style, art_intensity=art_intensity, void_mask=void_mask
            )

    k = len(specs)
    rgbs = np.array([s.rgb for s in specs], dtype=np.float32)
    layer_fams = [_classify_layer_family(s.rgb, i, k) for i, s in enumerate(specs)]
    fam_counts = {f: layer_fams.count(f) for f in set(layer_fams)}

    ref_specs_prev = _get_reference_relief_specs(specs)
    is_custom_layers_prev = any(s.end_layer_num != r.end_layer_num for s, r in zip(specs, ref_specs_prev))
    layer_ratios_prev: List[float] = []
    for s_sp, r_sp in zip(specs, ref_specs_prev):
        u_cnt = max(1, s_sp.end_layer_num - s_sp.start_layer_num + 1)
        r_cnt = max(1, r_sp.end_layer_num - r_sp.start_layer_num + 1)
        layer_ratios_prev.append(float(u_cnt) / float(r_cnt) if is_custom_layers_prev else 1.0)

    out_rgb = np.zeros_like(small)
    out_rgb[:, :] = rgbs[0]

    prev_z = base_z
    for idx in range(1, k):
        top_z = specs[idx].end_mm
        span = max(0.08, top_z - prev_z)
        thick = np.clip(pixel_z - prev_z, 0.0, span)
        layer_td = max(0.2, float(specs[idx].td_mm or td_mm))
        norm_t = thick / span
        if is_custom_layers_prev and abs(layer_ratios_prev[idx] - 1.0) > 0.02:
            # Physical Beer-Lambert thickness modulation:
            # For pixels whose top surface stops inside layer `idx` (`pixel_z <= top_z + 0.005`),
            # a thinner layer (e.g. 1 layer = 0.08mm) has reduced optical opacity and lets the underlying layer shine through,
            # while a thicker layer (e.g. 15 layers) saturates its color opacity!
            in_this_layer = (pixel_z > prev_z) & (pixel_z <= top_z + 0.005)
            op_scale = float(np.clip(layer_ratios_prev[idx] ** 0.72, 0.24, 2.20))
            norm_t = np.where(in_this_layer, np.clip(norm_t * op_scale, 0.0, min(1.0, op_scale)), norm_t)

        prev_f = layer_fams[idx - 1]
        curr_f = layer_fams[idx]
        if art_style in ("intaglio_splash", "papercut_terraced"):
            # Flat terraced stencil modes: each discrete Z step displays its full opaque terrace color
            blend_factor = (norm_t >= 0.92).astype(np.float32)[:, :, None]
            if art_style == "papercut_terraced":
                blend_factor = np.clip(norm_t * 1.35, 0.0, 1.0)[:, :, None]
            out_rgb = out_rgb * (1.0 - blend_factor) + rgbs[idx] * blend_factor
        elif art_style in ("stained_glass_ink", "halftone_manga"):
            # Crisp step color transitions for vitrail & halftone modes
            exponent = max(0.28, min(1.1, 1.0 / (layer_td * 0.85)))
            blend_factor = np.power(norm_t, exponent)[:, :, None]
            out_rgb = out_rgb * (1.0 - blend_factor) + rgbs[idx] * blend_factor
        elif prev_f not in ("dark", "white") and curr_f not in ("dark", "white") and curr_f != prev_f:
            blend_factor = np.clip(norm_t / 0.42, 0.0, 1.0)[:, :, None]
            shade_t = np.clip((norm_t - 0.42) / 0.58, 0.0, 1.0)[:, :, None]
            if curr_f == "gold":
                warm_base = np.array([185.0, 105.0, 20.0], dtype=np.float32)
                shadow_rgb = 0.32 * warm_base + 0.68 * rgbs[idx]
            elif curr_f == "warm" and fam_counts.get("warm", 1) >= 3:
                shadow_rgb = 0.76 * rgbs[0] + 0.24 * rgbs[idx]
            else:
                shadow_rgb = 0.38 * rgbs[0] + 0.62 * rgbs[idx]
            layer_rgb = shadow_rgb * (1.0 - shade_t) + rgbs[idx] * shade_t
            out_rgb = out_rgb * (1.0 - blend_factor) + layer_rgb * blend_factor
        else:
            exponent = max(0.35, min(1.5, 1.0 / (layer_td * 0.58)))
            blend_factor = np.power(norm_t, exponent)[:, :, None]
            if curr_f == "white" and prev_f != "silver":
                # When translucent White is printed over a dark chromatic stack on neutral grey/silver pixels,
                # the sub-surface under the White layer transmits a cool dark charcoal-slate tone (`0.52 * Black + 0.48 * sub`)
                _, sat_sm, _ = _rgb_array_to_hsv_deg(small.astype(np.float32))
                is_neutral_sub = (sat_sm < 0.18) & (norm_t > 0.01) & (norm_t < 0.96)
                charcoal_sub = 0.52 * rgbs[0] + 0.48 * out_rgb
                base_under = np.where(is_neutral_sub[:, :, None], charcoal_sub, out_rgb)
                out_rgb = base_under * (1.0 - blend_factor) + rgbs[idx] * blend_factor
            else:
                out_rgb = out_rgb * (1.0 - blend_factor) + rgbs[idx] * blend_factor

        prev_z = top_z

    if art_style != "standard":
        out_rgb = apply_3d_relief_shading_preview(out_rgb, pixel_z, base_z, max_z, art_style=art_style)

    # Optional Interactive Layer Loupe ("👁️ Voir Zone de cette Couche"):
    # Highlights the exact pixels whose 3D height `pixel_z` falls inside `specs[highlight_layer_idx]`
    if highlight_layer_idx is not None and 0 <= int(highlight_layer_idx) < k:
        hl_i = int(highlight_layer_idx)
        if hl_i == 0:
            active_zone = pixel_z <= (specs[0].end_mm + 0.02)
        else:
            z_lo = specs[hl_i - 1].end_mm + 0.005
            z_hi = specs[hl_i].end_mm + 0.015
            active_zone = (pixel_z >= z_lo) & (pixel_z <= z_hi)

        gray_val = (0.2126 * out_rgb[:, :, 0] + 0.7152 * out_rgb[:, :, 1] + 0.0722 * out_rgb[:, :, 2])[:, :, None]
        dimmed_rgb = 0.20 * gray_val + 0.08 * out_rgb + np.array([6.0, 10.0, 18.0], dtype=np.float32) * 0.72
        # For dark base layer (hl_i == 0), boost active zone visibility with a subtle cyan tint so black ink stands out
        active_rgb = out_rgb.copy()
        if specs[hl_i].luminance < 0.12:
            active_rgb = active_rgb * 0.75 + np.array([0.0, 210.0, 255.0], dtype=np.float32) * 0.25
        out_rgb = np.where(active_zone[:, :, None], active_rgb, dimmed_rgb)
        zone_edge = np.abs(gaussian_filter(active_zone.astype(np.float32), sigma=0.75) - 0.5) < 0.22
        out_rgb[zone_edge] = np.array([0.0, 240.0, 255.0], dtype=np.float32)

    inside_mask: Optional[np.ndarray] = None
    rim_mask: Optional[np.ndarray] = None
    if tiles:
        inside_mask, rim_mask = _rasterize_layout_masks(tiles, border_style, border_width_mm, pw, ph)
        if rim_mask is not None and np.any(rim_mask):
            rim_rgb = rgbs[-1] if border_style == "raised_top" else rgbs[0]
            out_rgb[rim_mask] = rim_rgb

        # Studio background outside the cut shape with subtle ambient glow
        bg_studio = np.array([8.0, 12.0, 20.0], dtype=np.float32)
        glow = gaussian_filter(inside_mask.astype(np.float32), sigma=4.5)[:, :, None]
        bg_with_shadow = bg_studio * (1.0 - 0.35 * glow) + np.array([0.0, 180.0, 215.0], dtype=np.float32) * (0.14 * glow)
        out_rgb = np.where(inside_mask[:, :, None], out_rgb, bg_with_shadow)

    out_uint8 = np.clip(out_rgb, 0, 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(out_uint8).save(buf, format="PNG")
    hf_b64 = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"

    if not return_dual_studio:
        return hf_b64

    # Build Left Panel Source / Outpaint Framing Preview (`source_b64`) + compute `void_pct` inside the shape
    if fill_mode == "none_preview":
        src_vis = _crop_and_resample_image(
            img_rgb, pw, ph, zoom=zoom, offset_x_pct=offset_x_pct, offset_y_pct=offset_y_pct, fill_mode="none_preview"
        )
    else:
        src_vis = small.copy()

    if inside_mask is not None:
        void_in_shape = void_mask & inside_mask
        void_pct = round(100.0 * float(np.sum(void_in_shape)) / max(1, int(np.sum(inside_mask))), 1)
    else:
        void_pct = round(100.0 * float(np.mean(void_mask)), 1)

    src_uint8 = np.clip(src_vis, 0, 255).astype(np.uint8)
    buf_src = io.BytesIO()
    Image.fromarray(src_uint8).save(buf_src, format="PNG")
    src_b64 = f"data:image/png;base64,{base64.b64encode(buf_src.getvalue()).decode('ascii')}"

    return hf_b64, src_b64, void_pct


def render_shape_overlay_base64(
    tiles: Optional[List[Tuple[str, sg.Polygon]]],
    border_style: BorderStyle = "raised_top",
    border_width_mm: float = 2.5,
    aspect_ratio: float = 1.0,
    preview_max_dim: int = 460,
) -> Optional[str]:
    """
    Renders a stationary transparent RGBA PNG overlay (`shape_overlay_data_url`) for Étape A
    so the geometric shape outline (#00f0ff) and dimmed exterior stay 100% fixed while the user
    pans or zooms the image underneath at 60 FPS.
    """
    if not tiles:
        return None
    if aspect_ratio >= 1.0:
        pw = preview_max_dim
        ph = max(80, int(round(preview_max_dim / aspect_ratio)))
    else:
        ph = preview_max_dim
        pw = max(80, int(round(preview_max_dim * aspect_ratio)))

    inside_mask, _ = _rasterize_layout_masks(tiles, border_style, border_width_mm, pw, ph)
    rgba = np.zeros((ph, pw, 4), dtype=np.uint8)
    outside = ~inside_mask
    rgba[outside, 0] = 6
    rgba[outside, 1] = 10
    rgba[outside, 2] = 18
    rgba[outside, 3] = 158

    shape_border = np.abs(gaussian_filter(inside_mask.astype(np.float32), sigma=0.85) - 0.5) < 0.23
    rgba[shape_border, 0] = 0
    rgba[shape_border, 1] = 240
    rgba[shape_border, 2] = 255
    rgba[shape_border, 3] = 255

    buf_ov = io.BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(buf_ov, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buf_ov.getvalue()).decode('ascii')}"


# ---------------------------------------------------------------------------
# 3. Geometric Shapes & Multi-Frame Tile Polygons (Shapely 2D)
# ---------------------------------------------------------------------------

def _regular_polygon(center: Tuple[float, float], radius: float, num_sides: int, angle_deg: float = 0.0) -> sg.Polygon:
    cx, cy = center
    pts = []
    for i in range(num_sides):
        ang = math.radians(angle_deg + i * (360.0 / num_sides))
        pts.append((cx + radius * math.cos(ang), cy + radius * math.sin(ang)))
    return sg.Polygon(pts)


def _equilateral_triangle(center: Tuple[float, float], side: float, pointing_up: bool = True) -> sg.Polygon:
    R = side / math.sqrt(3.0)
    ang = 90.0 if pointing_up else -90.0
    return _regular_polygon(center, R, 3, angle_deg=ang)


def _heart_polygon(width_mm: float) -> sg.Polygon:
    ts = np.linspace(0.0, 2.0 * math.pi, 160, endpoint=False)
    xs = 16.0 * (np.sin(ts) ** 3)
    ys = 13.0 * np.cos(ts) - 5.0 * np.cos(2.0 * ts) - 2.0 * np.cos(3.0 * ts) - np.cos(4.0 * ts)
    cx = 0.5 * (float(np.min(xs)) + float(np.max(xs)))
    cy = 0.5 * (float(np.min(ys)) + float(np.max(ys)))
    xs = xs - cx
    ys = ys - cy
    scale = float(width_mm) / max(1e-5, float(np.max(xs) - np.min(xs)))
    pts = list(zip((xs * scale).tolist(), (ys * scale).tolist()))
    return sg.Polygon(pts).buffer(0.0)


def _star5_polygon(diameter_mm: float) -> sg.Polygon:
    R = float(diameter_mm) / 2.0
    r = R * 0.42
    pts = []
    for i in range(10):
        ang = math.radians(90.0 + i * 36.0)
        rad = R if (i % 2 == 0) else r
        pts.append((rad * math.cos(ang), rad * math.sin(ang)))
    poly = sg.Polygon(pts).buffer(0.0)
    fillet = min(1.8, R * 0.025)
    if fillet > 0.2:
        smoothed = poly.buffer(-fillet, join_style=1).buffer(fillet, join_style=1)
        if not smoothed.is_empty and isinstance(smoothed, sg.Polygon):
            return smoothed
    return poly


def _shield_polygon(height_mm: float) -> sg.Polygon:
    H = float(height_mm)
    W = H * 0.84
    pts = []
    # Top edge (left to right with subtle heraldic dip/crest)
    for t in np.linspace(-1.0, 1.0, 25):
        x = t * (W / 2.0)
        y = (H / 2.0) - 0.035 * H * (1.0 - t * t)
        pts.append((float(x), float(y)))
    # Right side curving down to bottom tip (0, -H/2)
    for t in np.linspace(0.0, 1.0, 50)[1:]:
        # Smooth cubic curve from (W/2, 0.465*H) to (0, -0.5*H)
        x = (W / 2.0) * ((1.0 - t) ** 0.72)
        y = (H / 2.0) - t * H
        pts.append((float(x), float(y)))
    # Left side curving back up from bottom tip to (-W/2, H/2)
    for t in np.linspace(1.0, 0.0, 50)[1:-1]:
        x = -(W / 2.0) * ((1.0 - t) ** 0.72)
        y = (H / 2.0) - t * H
        pts.append((float(x), float(y)))
    return sg.Polygon(pts).buffer(0.0)


def _arch_polygon(height_mm: float) -> sg.Polygon:
    H = float(height_mm)
    W = H * 0.72
    r = W / 2.0
    cy_arch = (H / 2.0) - r
    pts = [(-r, -H / 2.0), (r, -H / 2.0)]
    for ang in np.linspace(0.0, math.pi, 64):
        pts.append((float(r * math.cos(ang)), float(cy_arch + r * math.sin(ang))))
    return sg.Polygon(pts).buffer(0.0)


def _diamond_polygon(height_mm: float) -> sg.Polygon:
    H = float(height_mm)
    W = H * 0.78
    return sg.Polygon([(0.0, H / 2.0), (-W / 2.0, 0.0), (0.0, -H / 2.0), (W / 2.0, 0.0)])


def _octagon_polygon(width_mm: float) -> sg.Polygon:
    R = (float(width_mm) / 2.0) / math.cos(math.radians(22.5))
    return _regular_polygon((0.0, 0.0), radius=R, num_sides=8, angle_deg=22.5)


def compute_optimal_zoom_for_layout(img_aspect: float, layout_aspect: float) -> float:
    """
    Computes the optimal initial zoom factor so that an image with `img_aspect = W / H`
    fits harmoniously inside a layout or N×M grid of aspect ratio `layout_aspect = W_grid / H_grid`
    without decapitating the subject.
    Because `_crop_and_resample_image` uses a 'cover' base window at zoom=1.0,
    the full-image 'contain' zoom is `min(layout_aspect / img_aspect, img_aspect / layout_aspect)`.
    We blend slightly (×1.08) so the subject fills the shape comfortably with minimal void.
    """
    ia = max(0.15, float(img_aspect))
    la = max(0.15, float(layout_aspect))
    contain_z = min(la / ia, ia / la)
    if contain_z >= 0.92:
        return 1.0
    opt_z = max(0.38, min(1.0, round(contain_z * 1.06, 2)))
    return opt_z


def compute_max_tile_extents_mm(tiles: List[Tuple[str, sg.Polygon]]) -> Tuple[float, float]:
    max_w = 0.0
    max_h = 0.0
    for _, poly in tiles:
        minx, miny, maxx, maxy = poly.bounds
        max_w = max(max_w, float(maxx - minx))
        max_h = max(max_h, float(maxy - miny))
    return (round(max_w, 1), round(max_h, 1))


def build_layout_polygons(
    layout_mode: LayoutMode,
    size_mm: float,
    aspect_ratio: float = 1.0,
    grid_cols: int = 3,
    grid_rows: int = 2,
) -> List[Tuple[str, sg.Polygon]]:
    s = float(size_mm)

    if layout_mode == "single_original":
        w = s
        h = round(s / max(0.1, aspect_ratio), 2)
        poly = sg.box(-w / 2.0, -h / 2.0, w / 2.0, h / 2.0)
        return [("HueForge_Original_01.stl", poly)]

    if layout_mode == "single_circle":
        radius = s / 2.0
        poly = sg.Point(0.0, 0.0).buffer(radius, resolution=64)
        return [("HueForge_Circle_01.stl", poly)]

    if layout_mode == "single_square":
        poly = sg.box(-s / 2.0, -s / 2.0, s / 2.0, s / 2.0)
        return [("HueForge_Square_01.stl", poly)]

    if layout_mode == "single_hexagon":
        poly = _regular_polygon((0.0, 0.0), radius=s, num_sides=6, angle_deg=0.0)
        return [("HueForge_Hexagon_01.stl", poly)]

    if layout_mode == "single_octagon":
        poly = _octagon_polygon(width_mm=s)
        return [("HueForge_Octagon_01.stl", poly)]

    if layout_mode == "single_triangle":
        poly = _equilateral_triangle((0.0, 0.0), side=s, pointing_up=True)
        return [("HueForge_Triangle_01.stl", poly)]

    if layout_mode == "single_diamond":
        poly = _diamond_polygon(height_mm=s)
        return [("HueForge_Diamond_01.stl", poly)]

    if layout_mode == "single_heart":
        poly = _heart_polygon(width_mm=s)
        return [("HueForge_Heart_01.stl", poly)]

    if layout_mode == "single_star5":
        poly = _star5_polygon(diameter_mm=s)
        return [("HueForge_Star5_01.stl", poly)]

    if layout_mode == "single_shield":
        poly = _shield_polygon(height_mm=s)
        return [("HueForge_Shield_01.stl", poly)]

    if layout_mode == "single_arch":
        poly = _arch_polygon(height_mm=s)
        return [("HueForge_Arch_01.stl", poly)]

    if layout_mode == "multi_4_squares":
        tiles = []
        idx = 1
        for row, y_sign in enumerate([0.5, -0.5]):
            for col, x_sign in enumerate([-0.5, 0.5]):
                cx, cy = x_sign * s, y_sign * s
                p = sg.box(cx - s / 2.0, cy - s / 2.0, cx + s / 2.0, cy + s / 2.0)
                tiles.append((f"Tile_{idx:02d}_R{row+1}C{col+1}.stl", p))
                idx += 1
        return tiles

    if layout_mode in ("multi_grid_squares", "multi_15_squares"):
        cols = 5 if layout_mode == "multi_15_squares" else max(1, min(10, int(grid_cols)))
        rows = 3 if layout_mode == "multi_15_squares" else max(1, min(10, int(grid_rows)))
        tiles = []
        idx = 1
        for r_idx in range(rows):
            cy = ((rows - 1) / 2.0 - r_idx) * s
            for c_idx in range(cols):
                cx = (c_idx - (cols - 1) / 2.0) * s
                p = sg.box(cx - s / 2.0, cy - s / 2.0, cx + s / 2.0, cy + s / 2.0)
                tiles.append((f"Tile_{idx:02d}_R{r_idx+1}C{c_idx+1}.stl", p))
                idx += 1
        return tiles

    if layout_mode == "multi_7_hexagons":
        tiles = [("Hex_01_Center.stl", _regular_polygon((0.0, 0.0), radius=s, num_sides=6, angle_deg=0.0))]
        dist = math.sqrt(3.0) * s
        for i in range(6):
            ang = math.radians(30.0 + i * 60.0)
            cx, cy = dist * math.cos(ang), dist * math.sin(ang)
            tiles.append((f"Hex_{i+2:02d}_Ring.stl", _regular_polygon((cx, cy), radius=s, num_sides=6, angle_deg=0.0)))
        return tiles

    if layout_mode == "multi_6_triangles":
        tiles = []
        for i in range(6):
            a0 = math.radians(i * 60.0)
            a1 = math.radians((i + 1) * 60.0)
            p0 = (0.0, 0.0)
            p1 = (s * math.cos(a0), s * math.sin(a0))
            p2 = (s * math.cos(a1), s * math.sin(a1))
            poly = sg.Polygon([p0, p1, p2])
            tiles.append((f"Tri_Rosette_{i+1:02d}.stl", poly))
        return tiles

    if layout_mode == "multi_4_triangles":
        h = s * math.sqrt(3.0) / 2.0
        t1 = sg.Polygon([(0.0, h), (-s / 2.0, 0.0), (s / 2.0, 0.0)])
        t2 = sg.Polygon([(-s / 2.0, 0.0), (-s, -h), (0.0, -h)])
        t3 = sg.Polygon([(s / 2.0, 0.0), (0.0, -h), (s, -h)])
        t4 = sg.Polygon([(-s / 2.0, 0.0), (s / 2.0, 0.0), (0.0, -h)])
        return [
            ("Tri_Pyramid_01_Top.stl", t1),
            ("Tri_Pyramid_02_Left.stl", t2),
            ("Tri_Pyramid_03_Right.stl", t3),
            ("Tri_Pyramid_04_Center.stl", t4),
        ]

    raise ValueError(f"Mode de découpe inconnu: {layout_mode}")


def find_shared_edges_midpoints(tiles: List[Tuple[str, sg.Polygon]]) -> List[Tuple[float, float, float]]:
    midpoints: List[Tuple[float, float, float]] = []
    n = len(tiles)
    if n <= 1:
        return midpoints

    for i in range(n):
        poly_i = tiles[i][1].buffer(0.01)
        for j in range(i + 1, n):
            poly_j = tiles[j][1].buffer(0.01)
            inter = poly_i.intersection(poly_j)
            if not inter.is_empty and inter.area > 0.1:
                minx, miny, maxx, maxy = inter.bounds
                dx, dy = maxx - minx, maxy - miny
                length = math.hypot(dx, dy)
                if length >= 25.0:
                    c = inter.centroid
                    angle_deg = math.degrees(math.atan2(dy, dx))
                    midpoints.append((float(c.x), float(c.y), angle_deg))
    return midpoints


# ---------------------------------------------------------------------------
# 4. High-Definition Heightfield + Integrated Border Rim + Manifold3D Clipping
# ---------------------------------------------------------------------------

def build_hueforge_heightfield_manifold(
    img_rgb: np.ndarray,
    bbox_2d: Tuple[float, float, float, float],
    base_thickness_mm: float = 0.88,
    max_total_height_mm: float = 2.48,
    grid_resolution: int = 380,
    zoom: float = 1.0,
    offset_x_pct: float = 0.0,
    offset_y_pct: float = 0.0,
    detail_boost: float = 1.2,
    contrast_gamma: float = 1.0,
    specs: Optional[List[ColorLayerSpec]] = None,
    color_engine: Literal["hsv_ramp", "cie_delta_e"] = "hsv_ramp",
    td_mm: float = 2.0,
    fill_mode: FillMode = "smart_aura",
    art_style: ArtStyle = "standard",
    art_intensity: float = 1.0,
) -> m3d.Manifold:
    """
    Generates a high-resolution watertight 3D heightfield Manifold over `bbox_2d = (minx, miny, maxx, maxy)`
    with Chroma-Aware Height Remapping (either 5-Family HSV Ramp or CIELAB ΔE Optical Inverse Solver),
    Artistic Style 3D Topography (`art_style`), Unsharp Mask detail enhancement, and framing (zoom / pan).
    """
    minx, miny, maxx, maxy = bbox_2d
    pad = 1.5
    minx -= pad
    miny -= pad
    maxx += pad
    maxy += pad

    span_x = maxx - minx
    span_y = maxy - miny

    if span_x >= span_y:
        nx = grid_resolution
        ny = max(32, int(round(grid_resolution * (span_y / span_x))))
    else:
        ny = grid_resolution
        nx = max(32, int(round(grid_resolution * (span_x / span_y))))

    arr, void_mask = _crop_and_resample_image(
        img_rgb,
        target_w=nx,
        target_h=ny,
        zoom=zoom,
        offset_x_pct=offset_x_pct,
        offset_y_pct=offset_y_pct,
        fill_mode="smart_aura" if fill_mode == "none_preview" else fill_mode,
        return_void_mask=True,
    )
    arr = np.flipud(arr)
    void_mask = np.flipud(void_mask)

    luma = compute_enhanced_luminance(
        arr,
        detail_boost=detail_boost,
        contrast_gamma=contrast_gamma,
        smoothing_sigma=0.32,
    )

    if specs and len(specs) >= 3:
        if color_engine == "cie_delta_e":
            z_top = compute_cielab_optical_pixel_z(arr, luma, specs, td_mm=td_mm)
        else:
            z_top = compute_chroma_aware_pixel_z(arr, luma, specs)
    else:
        relief_span = max(0.2, max_total_height_mm - base_thickness_mm)
        z_top = base_thickness_mm + luma * relief_span

    if specs and art_style != "standard":
        z_top = apply_art_style_topography(
            arr_rgb=arr,
            luma=luma,
            pixel_z=z_top,
            specs=specs,
            art_style=art_style,
            art_intensity=art_intensity,
            void_mask=void_mask,
        )

    xs = np.linspace(minx, maxx, nx, dtype=np.float32)
    ys = np.linspace(miny, maxy, ny, dtype=np.float32)
    xv, yv = np.meshgrid(xs, ys)

    n_pts = nx * ny
    top_verts = np.column_stack([xv.ravel(), yv.ravel(), z_top.ravel().astype(np.float32)])
    bot_verts = np.column_stack([xv.ravel(), yv.ravel(), np.zeros(n_pts, dtype=np.float32)])
    all_verts = np.ascontiguousarray(np.vstack([top_verts, bot_verts]), dtype=np.float32)

    r = np.arange(ny - 1, dtype=np.uint32)[:, None]
    c = np.arange(nx - 1, dtype=np.uint32)[None, :]
    v00 = (r * nx + c).ravel()
    v10 = v00 + 1
    v01 = v00 + nx
    v11 = v01 + 1

    top_t1 = np.column_stack([v00, v10, v11])
    top_t2 = np.column_stack([v00, v11, v01])

    b00 = v00 + n_pts
    b10 = v10 + n_pts
    b01 = v01 + n_pts
    b11 = v11 + n_pts
    bot_t1 = np.column_stack([b00, b11, b10])
    bot_t2 = np.column_stack([b00, b01, b11])

    c_idx = np.arange(nx - 1, dtype=np.uint32)
    t_bot = c_idx
    b_bot = c_idx + n_pts
    w_south1 = np.column_stack([b_bot, b_bot + 1, t_bot + 1])
    w_south2 = np.column_stack([b_bot, t_bot + 1, t_bot])

    t_top = (ny - 1) * nx + c_idx
    b_top = t_top + n_pts
    w_north1 = np.column_stack([b_top + 1, b_top, t_top])
    w_north2 = np.column_stack([b_top + 1, t_top, t_top + 1])

    r_idx = np.arange(ny - 1, dtype=np.uint32)
    t_left = r_idx * nx
    b_left = t_left + n_pts
    w_west1 = np.column_stack([b_left + nx, b_left, t_left])
    w_west2 = np.column_stack([b_left + nx, t_left, t_left + nx])

    t_right = r_idx * nx + (nx - 1)
    b_right = t_right + n_pts
    w_east1 = np.column_stack([b_right, b_right + nx, t_right + nx])
    w_east2 = np.column_stack([b_right, t_right + nx, t_right])

    all_faces = np.ascontiguousarray(
        np.vstack([
            top_t1, top_t2,
            bot_t1, bot_t2,
            w_south1, w_south2,
            w_north1, w_north2,
            w_west1, w_west2,
            w_east1, w_east2,
        ]),
        dtype=np.uint32,
    )

    return m3d.Manifold(m3d.Mesh(vert_properties=all_verts, tri_verts=all_faces))


def _polygon_to_prism_manifold(poly: sg.Polygon, height: float = 10.0, z_offset: float = -1.0) -> m3d.Manifold:
    coords = np.array(poly.exterior.coords[:-1], dtype=np.float64)
    if not sg.LinearRing(coords).is_ccw:
        coords = coords[::-1]
    polygons_list = [coords.tolist()]
    for interior in poly.interiors:
        h_coords = np.array(interior.coords[:-1], dtype=np.float64)
        if sg.LinearRing(h_coords).is_ccw:
            h_coords = h_coords[::-1]
        polygons_list.append(h_coords.tolist())
    cs = m3d.CrossSection(polygons_list)
    return m3d.Manifold.extrude(cs, height=height).translate([0.0, 0.0, z_offset])


def _apply_tile_border_rim(
    tile_mani: m3d.Manifold,
    poly: sg.Polygon,
    border_style: BorderStyle,
    border_width_mm: float,
    base_thickness_mm: float,
    total_height_mm: float,
) -> m3d.Manifold:
    """
    Applies a clean geometric frame/rim around the outer perimeter of `poly`:
    - `raised_top`: Adds a crisp raised frame at `total_height_mm` (printed in the top filament color).
    - `recessed_base`: Flattens the outer rim down to `base_thickness_mm` (printed in the dark base color).
    """
    if border_style == "none" or border_width_mm <= 0.2:
        return tile_mani

    inner_poly = poly.buffer(-float(border_width_mm), join_style=2)
    if inner_poly.is_empty or not isinstance(inner_poly, sg.Polygon) or inner_poly.area < 10.0:
        return tile_mani

    rim_poly = sg.Polygon(poly.exterior.coords, [inner_poly.exterior.coords])

    if border_style == "raised_top":
        rim_mani = _polygon_to_prism_manifold(rim_poly, height=total_height_mm, z_offset=0.0)
        return tile_mani + rim_mani

    if border_style == "recessed_base":
        cut_ring = _polygon_to_prism_manifold(
            rim_poly,
            height=total_height_mm + 2.0,
            z_offset=base_thickness_mm,
        )
        return tile_mani - cut_ring

    return tile_mani


def _create_back_bowtie_socket_and_clip(
    clearance_mm: float = 0.15,
    socket_depth_mm: float = 0.56,
) -> Tuple[m3d.Manifold, trimesh.Trimesh]:
    pts_male = [
        (-13.0, -4.5), (-5.0, -6.5), (0.0, -4.2), (5.0, -6.5), (13.0, -4.5),
        (13.0, 4.5), (5.0, 6.5), (0.0, 4.2), (-5.0, 6.5), (-13.0, 4.5),
    ]
    poly_male = sg.Polygon(pts_male)
    poly_female = poly_male.buffer(clearance_mm, join_style=2)

    coords_f = np.array(poly_female.exterior.coords[:-1], dtype=np.float64)
    if not sg.LinearRing(coords_f).is_ccw:
        coords_f = coords_f[::-1]
    cs_f = m3d.CrossSection([coords_f.tolist()])
    female_mani = m3d.Manifold.extrude(cs_f, height=socket_depth_mm + 0.2).translate([0.0, 0.0, -0.2])

    coords_m = np.array(poly_male.exterior.coords[:-1], dtype=np.float64)
    if not sg.LinearRing(coords_m).is_ccw:
        coords_m = coords_m[::-1]
    cs_m = m3d.CrossSection([coords_m.tolist()])
    male_mani = m3d.Manifold.extrude(cs_m, height=max(0.45, socket_depth_mm - 0.06))
    male_mesh = manifold_to_trimesh(male_mani)

    return female_mani, male_mesh


def export_hueforge_3mf_bytes(
    output_files: List[Tuple[str, trimesh.Trimesh]],
    specs: List[ColorLayerSpec],
    first_layer_mm: float = 0.16,
    layer_height_mm: float = 0.08,
    bed_x_mm: float = 260.0,
    bed_y_mm: float = 260.0,
    bed_z_mm: float = 300.0,
    printer_name: str = "Creality Hi (Combo 2× CFS)",
) -> bytes:
    """
    Exports a complete, pre-configured Multi-Plate & Multi-Color `.3mf` project archive
    compatible with Creality Print 5/6, OrcaSlicer, Bambu Studio, and PrusaSlicer:
      - Places each tile (and the male clips plate) on its own dedicated build plate (`Plate 1..N`),
        centered at `(bed_x/2, bed_y/2, 0)` with automatic multi-plate grid spacing.
      - Injects the 2..8 CFS filament hex colors (`filament_colour`) and HueForge slicer settings
        (`100%` rectilinear infill, `0.16mm` first layer, `0.08mm` layer height, `1` wall loop).
      - Encodes automatic height-based filament changes (`Metadata/custom_gcode_per_layer.xml`)
        at the exact millimeter heights (`specs[i].start_mm + layer_height_mm`) for every tile plate.
    """
    import json as _json

    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
        '  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
        '  <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
        '  <Default Extension="config" ContentType="text/xml"/>\n'
        '  <Default Extension="xml" ContentType="text/xml"/>\n'
        '</Types>\n'
    )

    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        '  <Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
        '</Relationships>\n'
    )

    model_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<model unit="millimeter" xml:lang="fr-FR" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" xmlns:BambuStudio="http://schemas.bambulab.com/package/2021">',
        '  <metadata name="Application">MakerStudio 3D - HueForge Pro Auto-Studio</metadata>',
        f'  <metadata name="Printer">{printer_name}</metadata>',
        '  <resources>',
    ]

    build_lines = ['  <build>']
    model_settings_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<config>',
    ]
    custom_gcode_lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<custom_gcodes_per_layer>',
    ]

    stride_x = float(bed_x_mm) + 30.0
    stride_y = float(bed_y_mm) + 30.0
    plates_per_row = 4

    for idx, (fname, mesh_part) in enumerate(output_files, start=1):
        clean_name = fname.replace(".stl", "")
        verts = np.round(mesh_part.vertices, 3)
        faces = mesh_part.faces

        model_lines.append(f'    <object id="{idx}" name="{clean_name}" type="model">')
        model_lines.append('      <mesh>')
        model_lines.append('        <vertices>')
        v_strs = [f'          <vertex x="{v[0]}" y="{v[1]}" z="{v[2]}"/>' for v in verts]
        model_lines.extend(v_strs)
        model_lines.append('        </vertices>')
        model_lines.append('        <triangles>')
        f_strs = [f'          <triangle v1="{f[0]}" v2="{f[1]}" v3="{f[2]}"/>' for f in faces]
        model_lines.extend(f_strs)
        model_lines.append('        </triangles>')
        model_lines.append('      </mesh>')
        model_lines.append('    </object>')

        p_col = (idx - 1) % plates_per_row
        p_row = (idx - 1) // plates_per_row
        tx = round(p_col * stride_x + float(bed_x_mm) / 2.0, 2)
        ty = round(p_row * stride_y + float(bed_y_mm) / 2.0, 2)

        build_lines.append(
            f'    <item objectid="{idx}" transform="1 0 0 0 1 0 0 0 1 {tx} {ty} 0" printable="1"/>'
        )

        ext = mesh_part.extents
        model_settings_lines.extend([
            f'  <object id="{idx}">',
            f'    <metadata key="name" value="{fname}"/>',
            '    <metadata key="extruder" value="1"/>',
            f'    <metadata face_count="{len(faces)}"/>',
            '  </object>',
            '  <plate>',
            f'    <metadata key="plater_id" value="{idx}"/>',
            f'    <metadata key="plater_name" value="Plateau {idx} - {clean_name} ({ext[0]:.0f}x{ext[1]:.0f}mm)"/>',
            '    <metadata key="locked" value="false"/>',
            '    <model_instance>',
            f'      <metadata key="object_id" value="{idx}"/>',
            '      <metadata key="instance_id" value="0"/>',
            '      <metadata key="identify_id" value="1"/>',
            '    </model_instance>',
            '  </plate>',
        ])

        # Add automatic layer color changes for all HueForge tile plates (skip for clips plate)
        is_clips_plate = "Clips_Assemblage" in fname
        custom_gcode_lines.append('  <plate>')
        custom_gcode_lines.append(f'    <plate_info id="{idx}"/>')
        if not is_clips_plate and len(specs) >= 2:
            for s_idx in range(1, len(specs)):
                sp = specs[s_idx]
                change_z = round(float(sp.start_mm) + float(layer_height_mm), 2)
                extruder_num = s_idx + 1
                custom_gcode_lines.append(
                    f'    <layer top_z="{change_z:.2f}" type="2" extruder="{extruder_num}" color="{sp.hex_color.upper()}" extra="" gcode="tool_change"/>'
                )
        custom_gcode_lines.append('  </plate>')

    model_lines.append('  </resources>')
    build_lines.append('  </build>')
    model_lines.extend(build_lines)
    model_lines.append('</model>\n')

    model_settings_lines.append('</config>\n')
    custom_gcode_lines.append('  <mode value="MultiAsSingle"/>')
    custom_gcode_lines.append('</custom_gcodes_per_layer>\n')

    bx_i = int(round(bed_x_mm))
    by_i = int(round(bed_y_mm))
    bz_i = int(round(bed_z_mm))
    project_settings = {
        "printer_model": printer_name,
        "printable_area": [f"0x0", f"{bx_i}x0", f"{bx_i}x{by_i}", f"0x{by_i}"],
        "printable_height": str(bz_i),
        "layer_height": f"{layer_height_mm:.2f}",
        "initial_layer_print_height": f"{first_layer_mm:.2f}",
        "wall_loops": "1",
        "sparse_infill_density": "100%",
        "sparse_infill_pattern": "rectilinear",
        "top_shell_layers": "999",
        "bottom_shell_layers": "999",
        "filament_colour": [s.hex_color.upper() for s in specs],
        "filament_type": ["PLA"] * len(specs),
        "filament_settings_id": [f"{s.cfs_slot} ({s.hex_color.upper()})" for s in specs],
    }

    buf_3mf = io.BytesIO()
    with zipfile.ZipFile(buf_3mf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml.encode("utf-8"))
        zf.writestr("_rels/.rels", rels_xml.encode("utf-8"))
        zf.writestr("3D/3dmodel.model", "\n".join(model_lines).encode("utf-8"))
        zf.writestr("Metadata/model_settings.config", "\n".join(model_settings_lines).encode("utf-8"))
        zf.writestr("Metadata/custom_gcode_per_layer.xml", "\n".join(custom_gcode_lines).encode("utf-8"))
        zf.writestr("Metadata/project_settings.config", _json.dumps(project_settings, indent=2, ensure_ascii=False).encode("utf-8"))

    return buf_3mf.getvalue()


# ---------------------------------------------------------------------------
# 5. API Schemas & Endpoints
# ---------------------------------------------------------------------------

class HueForgeGenerateRequest(BaseModel):
    layout_mode: LayoutMode = "single_hexagon"
    size_mm: float = Field(default=110.0, gt=15.0, le=600.0)
    grid_cols: int = Field(default=3, ge=1, le=10)
    grid_rows: int = Field(default=2, ge=1, le=10)
    printer_bed_x_mm: float = Field(default=260.0, ge=50.0, le=1200.0)
    printer_bed_y_mm: float = Field(default=260.0, ge=50.0, le=1200.0)
    printer_bed_z_mm: float = Field(default=300.0, ge=50.0, le=1500.0)
    printer_name: str = Field(default="Creality Hi (Combo 2× CFS)")
    base_thickness_mm: float = Field(default=0.88, ge=0.48, le=2.40)
    relief_height_mm: float = Field(default=1.60, ge=0.40, le=3.20)
    first_layer_mm: float = Field(default=0.16, ge=0.12, le=0.28)
    layer_height_mm: float = Field(default=0.08, ge=0.04, le=0.20)
    num_colors: int = Field(default=5, ge=2, le=8)
    palette_mode: Literal["ai_recommended", "in_stock_spools"] = "ai_recommended"
    color_engine: Literal["hsv_ramp", "cie_delta_e"] = "hsv_ramp"
    custom_hex_colors: Optional[List[str]] = None
    custom_end_layer_nums: Optional[List[int]] = None

    # Pro Optical & Detail Controls
    td_mm: float = Field(default=2.0, ge=0.3, le=6.0, description="Filament Transmission Distance (mm)")
    detail_boost: float = Field(default=1.3, ge=0.0, le=3.0, description="Manga/Line-Art Unsharp Mask strength")
    contrast_gamma: float = Field(default=1.0, ge=0.5, le=2.0)
    zoom: float = Field(default=1.0, ge=0.30, le=3.5)
    offset_x_pct: float = Field(default=0.0, ge=-100.0, le=100.0)
    offset_y_pct: float = Field(default=0.0, ge=-100.0, le=100.0)
    fill_mode: FillMode = "smart_aura"

    # Artistic Style & 3D Topography Controls
    art_style: ArtStyle = "standard"
    art_intensity: float = Field(default=1.0, ge=0.25, le=2.0)

    # Frame / Border Rim Controls
    border_style: BorderStyle = "raised_top"
    border_width_mm: float = Field(default=2.5, ge=0.0, le=12.0)

    add_back_connectors: bool = True
    grid_resolution: int = Field(default=380, ge=120, le=540)
    highlight_layer_idx: Optional[int] = Field(
        default=None,
        description="Optional layer index (0..K-1) to isolate/highlight on the 2D HueForge preview",
    )


@router.get("/status")
async def hueforge_status():
    return {
        "module": "Module 2A - HueForge Pro Auto-Studio & Multi-Frame Tiler",
        "status": "active",
        "standard_spools": STANDARD_FILAMENT_SPOOLS,
    }


@router.post("/upload-image")
async def upload_hueforge_image(file: UploadFile = File(...)):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Le fichier image est vide.")

    try:
        pil_img = Image.open(io.BytesIO(raw)).convert("RGB")
        img_rgb = np.asarray(pil_img, dtype=np.uint8)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Impossible de lire l'image : {exc}") from exc

    h, w, _ = img_rgb.shape
    aspect_ratio = round(float(w) / max(1.0, float(h)), 4)

    rec_k, palettes, stock_palettes = analyze_image_and_propose_palettes(img_rgb, vivid_boost=True)
    session_id = str(uuid.uuid4())
    HUEFORGE_SESSIONS[session_id] = HueForgeSession(
        session_id=session_id,
        filename=file.filename or "image.png",
        image_rgb=img_rgb,
        original_image_rgb=img_rgb.copy(),
        aspect_ratio=aspect_ratio,
        recommended_colors=rec_k,
        palettes_by_k=palettes,
        stock_palettes_by_k=stock_palettes,
        has_validated_outpaint=False,
    )

    active_dicts = palettes[rec_k]
    specs = [ColorLayerSpec(**d) for d in active_dicts]
    tiles = build_layout_polygons("single_hexagon", 115.0, aspect_ratio)
    union_poly = sg.MultiPolygon([t[1] for t in tiles])
    minx, miny, maxx, maxy = union_poly.bounds
    layout_aspect = (maxx - minx) / max(1.0, (maxy - miny))
    opt_zoom = compute_optimal_zoom_for_layout(aspect_ratio, layout_aspect)
    tile_w, tile_h = compute_max_tile_extents_mm(tiles)

    preview_b64, src_preview_b64, void_pct = render_quantized_preview_base64(
        img_rgb,
        specs=specs,
        aspect_ratio=layout_aspect,
        zoom=opt_zoom,
        tiles=tiles,
        border_style="raised_top",
        border_width_mm=2.5,
        fill_mode="smart_aura",
        return_dual_studio=True,
    )
    shape_overlay_b64 = render_shape_overlay_base64(
        tiles=tiles,
        border_style="raised_top",
        border_width_mm=2.5,
        aspect_ratio=layout_aspect,
    )

    return {
        "session_id": session_id,
        "filename": file.filename,
        "image_dimensions": [w, h],
        "image_size_px": [w, h],
        "aspect_ratio": aspect_ratio,
        "recommended_colors": rec_k,
        "palettes_by_k": palettes,
        "stock_palettes_by_k": stock_palettes,
        "active_palette": active_dicts,
        "standard_spools": STANDARD_FILAMENT_SPOOLS,
        "preview_data_url": preview_b64,
        "source_preview_data_url": src_preview_b64,
        "shape_overlay_data_url": shape_overlay_b64,
        "void_pct": void_pct,
        "optimal_zoom": opt_zoom,
        "max_tile_dims_mm": [tile_w, tile_h],
        "has_validated_outpaint": False,
    }


@router.post("/{session_id}/reanalyze-palette")
async def reanalyze_hueforge_palette_on_crop(session_id: str, req: HueForgeGenerateRequest):
    """
    Re-analyzes the image specifically inside the user's current Zoom / Pan framing (`zoom`, `offset_x_pct`, `offset_y_pct`)
    and refreshes both the AI Recommended Palettes (`palettes_by_k`) and the In-Stock Spool Matched Palettes (`stock_palettes_by_k`).
    """
    sess = _get_hf_session(session_id)
    tiles = build_layout_polygons(req.layout_mode, req.size_mm, sess.aspect_ratio, req.grid_cols, req.grid_rows)
    union_poly = sg.MultiPolygon([t[1] for t in tiles])
    minx, miny, maxx, maxy = union_poly.bounds
    layout_aspect = (maxx - minx) / max(1.0, (maxy - miny))

    cropped_f32 = _crop_and_resample_image(
        sess.image_rgb,
        target_w=320,
        target_h=max(120, int(round(320 / max(0.2, layout_aspect)))),
        zoom=req.zoom,
        offset_x_pct=req.offset_x_pct,
        offset_y_pct=req.offset_y_pct,
        fill_mode="smart_aura" if req.fill_mode == "none_preview" else req.fill_mode,
    )
    cropped_u8 = np.clip(cropped_f32, 0, 255).astype(np.uint8)

    rec_k, palettes, stock_palettes = analyze_image_and_propose_palettes(
        cropped_u8,
        base_thickness_mm=req.base_thickness_mm,
        relief_height_mm=req.relief_height_mm,
        first_layer_mm=req.first_layer_mm,
        layer_height_mm=req.layer_height_mm,
        vivid_boost=True,
    )
    sess.recommended_colors = rec_k
    sess.palettes_by_k = palettes
    sess.stock_palettes_by_k = stock_palettes

    k = max(2, min(8, req.num_colors))
    chosen_dict_list = (
        stock_palettes.get(k, palettes[k])
        if req.palette_mode == "in_stock_spools"
        else palettes[k]
    )
    specs = [ColorLayerSpec(**d) for d in chosen_dict_list]
    specs = prepare_specs_for_art_style(specs, req.art_style)
    chosen_dict_list = [s.to_dict() for s in specs]

    preview_b64, src_preview_b64, void_pct = render_quantized_preview_base64(
        sess.image_rgb,
        specs=specs,
        aspect_ratio=layout_aspect,
        zoom=req.zoom,
        offset_x_pct=req.offset_x_pct,
        offset_y_pct=req.offset_y_pct,
        detail_boost=req.detail_boost,
        contrast_gamma=req.contrast_gamma,
        td_mm=req.td_mm,
        color_engine=req.color_engine,
        fill_mode=req.fill_mode,
        tiles=tiles,
        border_style=req.border_style,
        border_width_mm=req.border_width_mm,
        return_dual_studio=True,
        art_style=req.art_style,
        art_intensity=req.art_intensity,
        highlight_layer_idx=req.highlight_layer_idx,
    )

    shape_overlay_b64 = render_shape_overlay_base64(
        tiles=tiles,
        border_style=req.border_style,
        border_width_mm=req.border_width_mm,
        aspect_ratio=layout_aspect,
    )

    return {
        "session_id": session_id,
        "recommended_colors": rec_k,
        "palettes_by_k": palettes,
        "stock_palettes_by_k": stock_palettes,
        "active_palette": chosen_dict_list,
        "preview_data_url": preview_b64,
        "source_preview_data_url": src_preview_b64,
        "shape_overlay_data_url": shape_overlay_b64,
        "void_pct": void_pct,
        "has_validated_outpaint": sess.has_validated_outpaint,
    }


@router.post("/{session_id}/optimize-order")
async def optimize_hueforge_spool_order_endpoint(session_id: str, req: HueForgeGenerateRequest):
    """
    Finds the optimal vertical layer ordering of the user's current spools that minimizes
    perceptual CIELAB ΔE error on the cropped image, keeping Layer 1 (base) and Layer K (top highlight) anchored.
    """
    sess = _get_hf_session(session_id)
    k = max(2, min(8, req.num_colors))
    source_palettes = (
        sess.stock_palettes_by_k
        if req.palette_mode == "in_stock_spools"
        else sess.palettes_by_k
    )
    base_palette = source_palettes.get(k, sess.palettes_by_k[sess.recommended_colors])
    hex_list = (
        req.custom_hex_colors
        if (req.custom_hex_colors and len(req.custom_hex_colors) == k)
        else [c["hex_color"] for c in base_palette]
    )
    centroids = np.array([_hex_to_rgb(hx) for hx in hex_list], dtype=np.float32)
    lumas = centroids @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)

    specs = _build_layer_schedule(
        sorted_centroids=centroids,
        sorted_lumas=lumas,
        base_thickness_mm=req.base_thickness_mm,
        relief_height_mm=req.relief_height_mm,
        first_layer_mm=req.first_layer_mm,
        layer_height_mm=req.layer_height_mm,
        custom_end_layer_nums=req.custom_end_layer_nums,
        td_mm=req.td_mm,
    )

    tiles = build_layout_polygons(req.layout_mode, req.size_mm, sess.aspect_ratio, req.grid_cols, req.grid_rows)
    union_poly = sg.MultiPolygon([t[1] for t in tiles])
    minx, miny, maxx, maxy = union_poly.bounds
    layout_aspect = (maxx - minx) / max(1.0, (maxy - miny))

    opt_specs, de_before, de_after = optimize_layer_order_cielab(
        sess.image_rgb,
        specs=specs,
        aspect_ratio=layout_aspect,
        zoom=req.zoom,
        offset_x_pct=req.offset_x_pct,
        offset_y_pct=req.offset_y_pct,
        detail_boost=req.detail_boost,
        contrast_gamma=req.contrast_gamma,
        td_mm=req.td_mm,
    )
    opt_specs = prepare_specs_for_art_style(opt_specs, req.art_style)
    palette_dicts = [s.to_dict() for s in opt_specs]

    preview_b64, src_preview_b64, void_pct = render_quantized_preview_base64(
        sess.image_rgb,
        specs=opt_specs,
        aspect_ratio=layout_aspect,
        zoom=req.zoom,
        offset_x_pct=req.offset_x_pct,
        offset_y_pct=req.offset_y_pct,
        detail_boost=req.detail_boost,
        contrast_gamma=req.contrast_gamma,
        td_mm=req.td_mm,
        color_engine=req.color_engine,
        fill_mode=req.fill_mode,
        tiles=tiles,
        border_style=req.border_style,
        border_width_mm=req.border_width_mm,
        return_dual_studio=True,
        art_style=req.art_style,
        art_intensity=req.art_intensity,
        highlight_layer_idx=req.highlight_layer_idx,
    )

    shape_overlay_b64 = render_shape_overlay_base64(
        tiles=tiles,
        border_style=req.border_style,
        border_width_mm=req.border_width_mm,
        aspect_ratio=layout_aspect,
    )

    return {
        "session_id": session_id,
        "active_palette": palette_dicts,
        "preview_data_url": preview_b64,
        "source_preview_data_url": src_preview_b64,
        "shape_overlay_data_url": shape_overlay_b64,
        "void_pct": void_pct,
        "has_validated_outpaint": sess.has_validated_outpaint,
        "delta_e_before": de_before,
        "delta_e_after": de_after,
    }


@router.post("/{session_id}/preview-palette")
async def update_hueforge_palette_preview(session_id: str, req: HueForgeGenerateRequest):
    sess = _get_hf_session(session_id)
    k = max(2, min(8, req.num_colors))
    source_palettes = (
        sess.stock_palettes_by_k
        if req.palette_mode == "in_stock_spools"
        else sess.palettes_by_k
    )
    base_palette = source_palettes.get(k, sess.palettes_by_k[sess.recommended_colors])

    hex_list = (
        req.custom_hex_colors
        if (req.custom_hex_colors and len(req.custom_hex_colors) == k)
        else [c["hex_color"] for c in base_palette]
    )
    centroids = np.array([_hex_to_rgb(hx) for hx in hex_list], dtype=np.float32)
    lumas = centroids @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)

    specs = _build_layer_schedule(
        sorted_centroids=centroids,
        sorted_lumas=lumas,
        base_thickness_mm=req.base_thickness_mm,
        relief_height_mm=req.relief_height_mm,
        first_layer_mm=req.first_layer_mm,
        layer_height_mm=req.layer_height_mm,
        custom_end_layer_nums=req.custom_end_layer_nums,
        td_mm=req.td_mm,
    )
    specs = prepare_specs_for_art_style(specs, req.art_style)
    palette_dicts = [s.to_dict() for s in specs]

    tiles = build_layout_polygons(req.layout_mode, req.size_mm, sess.aspect_ratio, req.grid_cols, req.grid_rows)
    union_poly = sg.MultiPolygon([t[1] for t in tiles])
    minx, miny, maxx, maxy = union_poly.bounds
    layout_aspect = (maxx - minx) / max(1.0, (maxy - miny))
    opt_zoom = compute_optimal_zoom_for_layout(sess.aspect_ratio, layout_aspect)
    tile_w, tile_h = compute_max_tile_extents_mm(tiles)

    preview_b64, src_preview_b64, void_pct = render_quantized_preview_base64(
        sess.image_rgb,
        specs=specs,
        aspect_ratio=layout_aspect,
        zoom=req.zoom,
        offset_x_pct=req.offset_x_pct,
        offset_y_pct=req.offset_y_pct,
        detail_boost=req.detail_boost,
        contrast_gamma=req.contrast_gamma,
        td_mm=req.td_mm,
        color_engine=req.color_engine,
        fill_mode=req.fill_mode,
        tiles=tiles,
        border_style=req.border_style,
        border_width_mm=req.border_width_mm,
        return_dual_studio=True,
        art_style=req.art_style,
        art_intensity=req.art_intensity,
        highlight_layer_idx=req.highlight_layer_idx,
    )

    shape_overlay_b64 = render_shape_overlay_base64(
        tiles=tiles,
        border_style=req.border_style,
        border_width_mm=req.border_width_mm,
        aspect_ratio=layout_aspect,
    )
    seams = find_shared_edges_midpoints(tiles)

    return {
        "session_id": session_id,
        "active_palette": palette_dicts,
        "preview_data_url": preview_b64,
        "source_preview_data_url": src_preview_b64,
        "shape_overlay_data_url": shape_overlay_b64,
        "void_pct": void_pct,
        "optimal_zoom": opt_zoom,
        "has_validated_outpaint": sess.has_validated_outpaint,
        "layout_summary": {
            "tiles_count": len(tiles),
            "overall_dimensions_mm": [round(maxx - minx, 1), round(maxy - miny, 1)],
            "max_tile_dims_mm": [tile_w, tile_h],
            "connectors_clips_count": len(seams) if req.add_back_connectors else 0,
        },
    }


@router.post("/{session_id}/apply-outpaint")
async def apply_and_bake_outpaint_endpoint(session_id: str, req: HueForgeGenerateRequest):
    """
    Validates & bakes the current zoom/pan framing and void-filling outpaint into `sess.image_rgb`
    at high resolution (760px), resets framing to zoom=1.0 / offset=(0, 0), and re-analyzes palettes.
    """
    sess = _get_hf_session(session_id)
    tiles = build_layout_polygons(req.layout_mode, req.size_mm, sess.aspect_ratio, req.grid_cols, req.grid_rows)
    union_poly = sg.MultiPolygon([t[1] for t in tiles])
    minx, miny, maxx, maxy = union_poly.bounds
    layout_aspect = (maxx - minx) / max(1.0, (maxy - miny))

    max_dim = 760
    if layout_aspect >= 1.0:
        tw = max_dim
        th = max(240, int(round(max_dim / layout_aspect)))
    else:
        th = max_dim
        tw = max(240, int(round(max_dim * layout_aspect)))

    baked_mode: FillMode = "smart_aura" if req.fill_mode == "none_preview" else req.fill_mode
    baked_f32 = _crop_and_resample_image(
        sess.image_rgb,
        target_w=tw,
        target_h=th,
        zoom=req.zoom,
        offset_x_pct=req.offset_x_pct,
        offset_y_pct=req.offset_y_pct,
        fill_mode=baked_mode,
    )
    baked_u8 = np.clip(baked_f32, 0, 255).astype(np.uint8)

    sess.image_rgb = baked_u8
    sess.aspect_ratio = round(float(tw) / max(1.0, float(th)), 4)
    sess.has_validated_outpaint = True

    rec_k, palettes, stock_palettes = analyze_image_and_propose_palettes(
        sess.image_rgb,
        base_thickness_mm=req.base_thickness_mm,
        relief_height_mm=req.relief_height_mm,
        first_layer_mm=req.first_layer_mm,
        layer_height_mm=req.layer_height_mm,
        vivid_boost=True,
    )
    sess.recommended_colors = rec_k
    sess.palettes_by_k = palettes
    sess.stock_palettes_by_k = stock_palettes

    k = max(2, min(8, req.num_colors))
    source_palettes = stock_palettes if req.palette_mode == "in_stock_spools" else palettes
    base_palette = source_palettes.get(k, palettes[rec_k])
    hex_list = (
        req.custom_hex_colors
        if (req.custom_hex_colors and len(req.custom_hex_colors) == k)
        else [c["hex_color"] for c in base_palette]
    )
    centroids = np.array([_hex_to_rgb(hx) for hx in hex_list], dtype=np.float32)
    lumas = centroids @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    specs = _build_layer_schedule(
        sorted_centroids=centroids,
        sorted_lumas=lumas,
        base_thickness_mm=req.base_thickness_mm,
        relief_height_mm=req.relief_height_mm,
        first_layer_mm=req.first_layer_mm,
        layer_height_mm=req.layer_height_mm,
        custom_end_layer_nums=req.custom_end_layer_nums,
        td_mm=req.td_mm,
    )
    specs = prepare_specs_for_art_style(specs, req.art_style)
    palette_dicts = [s.to_dict() for s in specs]

    tiles_new = build_layout_polygons(req.layout_mode, req.size_mm, sess.aspect_ratio, req.grid_cols, req.grid_rows)
    preview_b64, src_preview_b64, void_pct = render_quantized_preview_base64(
        sess.image_rgb,
        specs=specs,
        aspect_ratio=layout_aspect,
        zoom=1.0,
        offset_x_pct=0.0,
        offset_y_pct=0.0,
        detail_boost=req.detail_boost,
        contrast_gamma=req.contrast_gamma,
        td_mm=req.td_mm,
        color_engine=req.color_engine,
        fill_mode=baked_mode,
        tiles=tiles_new,
        border_style=req.border_style,
        border_width_mm=req.border_width_mm,
        return_dual_studio=True,
        art_style=req.art_style,
        art_intensity=req.art_intensity,
        highlight_layer_idx=req.highlight_layer_idx,
    )

    shape_overlay_b64 = render_shape_overlay_base64(
        tiles=tiles_new,
        border_style=req.border_style,
        border_width_mm=req.border_width_mm,
        aspect_ratio=layout_aspect,
    )

    return {
        "session_id": session_id,
        "image_size_px": [tw, th],
        "aspect_ratio": sess.aspect_ratio,
        "recommended_colors": rec_k,
        "palettes_by_k": palettes,
        "stock_palettes_by_k": stock_palettes,
        "active_palette": palette_dicts,
        "preview_data_url": preview_b64,
        "source_preview_data_url": src_preview_b64,
        "shape_overlay_data_url": shape_overlay_b64,
        "void_pct": void_pct,
        "has_validated_outpaint": True,
    }


@router.post("/{session_id}/reset-outpaint")
async def reset_outpaint_to_original_endpoint(session_id: str, req: HueForgeGenerateRequest):
    """
    Restores the raw uncropped/unextended original image uploaded by the user.
    """
    sess = _get_hf_session(session_id)
    if sess.original_image_rgb is not None:
        sess.image_rgb = sess.original_image_rgb.copy()
        oh, ow, _ = sess.image_rgb.shape
        sess.aspect_ratio = round(float(ow) / max(1.0, float(oh)), 4)
    sess.has_validated_outpaint = False

    rec_k, palettes, stock_palettes = analyze_image_and_propose_palettes(
        sess.image_rgb,
        base_thickness_mm=req.base_thickness_mm,
        relief_height_mm=req.relief_height_mm,
        first_layer_mm=req.first_layer_mm,
        layer_height_mm=req.layer_height_mm,
        vivid_boost=True,
    )
    sess.recommended_colors = rec_k
    sess.palettes_by_k = palettes
    sess.stock_palettes_by_k = stock_palettes

    k = max(2, min(8, req.num_colors))
    source_palettes = stock_palettes if req.palette_mode == "in_stock_spools" else palettes
    chosen_dict_list = source_palettes.get(k, palettes[rec_k])
    specs = [ColorLayerSpec(**d) for d in chosen_dict_list]
    specs = prepare_specs_for_art_style(specs, req.art_style)
    chosen_dict_list = [s.to_dict() for s in specs]

    tiles = build_layout_polygons(req.layout_mode, req.size_mm, sess.aspect_ratio, req.grid_cols, req.grid_rows)
    union_poly = sg.MultiPolygon([t[1] for t in tiles])
    minx, miny, maxx, maxy = union_poly.bounds
    layout_aspect = (maxx - minx) / max(1.0, (maxy - miny))
    opt_zoom = compute_optimal_zoom_for_layout(sess.aspect_ratio, layout_aspect)

    preview_b64, src_preview_b64, void_pct = render_quantized_preview_base64(
        sess.image_rgb,
        specs=specs,
        aspect_ratio=layout_aspect,
        zoom=opt_zoom,
        offset_x_pct=0.0,
        offset_y_pct=0.0,
        detail_boost=req.detail_boost,
        contrast_gamma=req.contrast_gamma,
        td_mm=req.td_mm,
        color_engine=req.color_engine,
        fill_mode=req.fill_mode,
        tiles=tiles,
        border_style=req.border_style,
        border_width_mm=req.border_width_mm,
        return_dual_studio=True,
        art_style=req.art_style,
        art_intensity=req.art_intensity,
        highlight_layer_idx=req.highlight_layer_idx,
    )

    shape_overlay_b64 = render_shape_overlay_base64(
        tiles=tiles,
        border_style=req.border_style,
        border_width_mm=req.border_width_mm,
        aspect_ratio=layout_aspect,
    )
    oh_curr, ow_curr, _ = sess.image_rgb.shape

    return {
        "session_id": session_id,
        "image_size_px": [ow_curr, oh_curr],
        "aspect_ratio": sess.aspect_ratio,
        "recommended_colors": rec_k,
        "palettes_by_k": palettes,
        "stock_palettes_by_k": stock_palettes,
        "active_palette": chosen_dict_list,
        "preview_data_url": preview_b64,
        "source_preview_data_url": src_preview_b64,
        "shape_overlay_data_url": shape_overlay_b64,
        "void_pct": void_pct,
        "optimal_zoom": opt_zoom,
        "has_validated_outpaint": False,
    }


@router.post("/{session_id}/generate-stl")
async def generate_hueforge_stl_and_zip(session_id: str, req: HueForgeGenerateRequest):
    sess = _get_hf_session(session_id)
    k = max(2, min(8, req.num_colors))
    source_palettes = (
        sess.stock_palettes_by_k
        if req.palette_mode == "in_stock_spools"
        else sess.palettes_by_k
    )
    base_palette = source_palettes.get(k, sess.palettes_by_k[sess.recommended_colors])
    hex_list = (
        req.custom_hex_colors
        if (req.custom_hex_colors and len(req.custom_hex_colors) == k)
        else [c["hex_color"] for c in base_palette]
    )

    centroids = np.array([_hex_to_rgb(hx) for hx in hex_list], dtype=np.float32)
    lumas = centroids @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    specs = _build_layer_schedule(
        sorted_centroids=centroids,
        sorted_lumas=lumas,
        base_thickness_mm=req.base_thickness_mm,
        relief_height_mm=req.relief_height_mm,
        first_layer_mm=req.first_layer_mm,
        layer_height_mm=req.layer_height_mm,
        custom_end_layer_nums=req.custom_end_layer_nums,
        td_mm=req.td_mm,
    )
    specs = prepare_specs_for_art_style(specs, req.art_style)

    tiles = build_layout_polygons(req.layout_mode, req.size_mm, sess.aspect_ratio, req.grid_cols, req.grid_rows)
    union_poly = sg.MultiPolygon([t[1] for t in tiles])
    bbox_2d = union_poly.bounds

    total_height_mm = specs[-1].end_mm
    hf_mani = build_hueforge_heightfield_manifold(
        img_rgb=sess.image_rgb,
        bbox_2d=bbox_2d,
        base_thickness_mm=req.base_thickness_mm,
        max_total_height_mm=total_height_mm,
        grid_resolution=req.grid_resolution,
        zoom=req.zoom,
        offset_x_pct=req.offset_x_pct,
        offset_y_pct=req.offset_y_pct,
        detail_boost=req.detail_boost,
        contrast_gamma=req.contrast_gamma,
        specs=specs,
        color_engine=req.color_engine,
        td_mm=req.td_mm,
        fill_mode=req.fill_mode,
        art_style=req.art_style,
        art_intensity=req.art_intensity,
    )

    seams = find_shared_edges_midpoints(tiles) if (len(tiles) > 1 and req.add_back_connectors) else []
    socket_depth = min(0.56, req.base_thickness_mm * 0.65)
    female_socket_local, male_clip_mesh = _create_back_bowtie_socket_and_clip(
        clearance_mm=0.15,
        socket_depth_mm=socket_depth,
    )

    seam_manifolds: List[m3d.Manifold] = []
    for (mx, my, ang_deg) in seams:
        s_mani = female_socket_local.rotate([0.0, 0.0, ang_deg]).translate([mx, my, 0.0])
        seam_manifolds.append(s_mani)

    output_files: List[Tuple[str, trimesh.Trimesh]] = []
    preview_meshes: List[trimesh.Trimesh] = []
    parts_meta: List[Dict[str, Any]] = []

    for idx, (t_name, poly) in enumerate(tiles, start=1):
        prism = _polygon_to_prism_manifold(poly, height=total_height_mm + 4.0)
        tile_mani = hf_mani ^ prism

        # Apply Optional Integrated Frame / Border Rim around each tile
        tile_mani = _apply_tile_border_rim(
            tile_mani=tile_mani,
            poly=poly,
            border_style=req.border_style,
            border_width_mm=req.border_width_mm,
            base_thickness_mm=specs[0].end_mm,
            total_height_mm=total_height_mm,
        )

        # Subtract shared back-side female sockets touching this tile
        for s_mani in seam_manifolds:
            tile_mani = tile_mani - s_mani

        # Engrave tile number on the flat back (Z=0, depth=0.45mm) for multi-frame sets
        if len(tiles) > 1:
            c_pt = poly.centroid
            try:
                num_stamp = create_3d_number_stamp_manifold(
                    str(idx),
                    char_height_mm=min(10.0, req.size_mm * 0.18),
                    depth_mm=0.45,
                    mirror_x=True,
                )
                num_stamp = num_stamp.translate([float(c_pt.x), float(c_pt.y), 0.0])
                tile_mani = tile_mani - num_stamp
            except Exception:
                pass

        t_mesh = manifold_to_trimesh(tile_mani)
        preview_copy = t_mesh.copy()
        if len(tiles) > 1:
            c_pt = poly.centroid
            dist_from_origin = math.hypot(c_pt.x, c_pt.y)
            if dist_from_origin > 1e-2:
                ux, uy = (c_pt.x / dist_from_origin) * 4.5, (c_pt.y / dist_from_origin) * 4.5
                preview_copy.apply_translation([ux, uy, 0.0])
        preview_meshes.append(preview_copy)

        centered_tile = t_mesh.copy()
        b = centered_tile.bounds
        centered_tile.apply_translation([-(b[0][0] + b[1][0]) / 2.0, -(b[0][1] + b[1][1]) / 2.0, -b[0][2]])
        output_files.append((t_name, centered_tile))

        ext = centered_tile.extents
        parts_meta.append({
            "part_index": idx,
            "filename": t_name,
            "extents_mm": [round(float(ext[0]), 1), round(float(ext[1]), 1), round(float(ext[2]), 2)],
            "faces_count": int(len(centered_tile.faces)),
        })

    if seams:
        clips_list = []
        cols = max(1, int(math.ceil(math.sqrt(len(seams)))))
        for c_idx in range(len(seams)):
            clip_copy = male_clip_mesh.copy()
            r, c = c_idx // cols, c_idx % cols
            clip_copy.apply_translation([c * 32.0, r * 18.0, 0.0])
            clips_list.append(clip_copy)
        clips_plate = trimesh.util.concatenate(clips_list)
        b_c = clips_plate.bounds
        clips_plate.apply_translation([-(b_c[0][0] + b_c[1][0]) / 2.0, -(b_c[0][1] + b_c[1][1]) / 2.0, -b_c[0][2]])
        clip_fname = f"Clips_Assemblage_Males_x{len(seams)}.stl"
        output_files.append((clip_fname, clips_plate))
        ext_c = clips_plate.extents
        parts_meta.append({
            "part_index": len(output_files),
            "filename": clip_fname,
            "extents_mm": [round(float(ext_c[0]), 1), round(float(ext_c[1]), 1), round(float(ext_c[2]), 2)],
            "faces_count": int(len(clips_plate.faces)),
        })

    sess.last_preview_mesh = trimesh.util.concatenate(preview_meshes)

    # Generate complete pre-configured Multi-Plate & Multi-Color .3MF Project
    base_name = sess.filename.rsplit(".", 1)[0]
    project_3mf_bytes = export_hueforge_3mf_bytes(
        output_files=output_files,
        specs=specs,
        first_layer_mm=req.first_layer_mm,
        layer_height_mm=req.layer_height_mm,
        bed_x_mm=req.printer_bed_x_mm,
        bed_y_mm=req.printer_bed_y_mm,
        bed_z_mm=req.printer_bed_z_mm,
        printer_name=req.printer_name,
    )
    sess.last_3mf_bytes = project_3mf_bytes

    recipe_lines = [
        "======================================================================",
        f"  MAKERSTUDIO 3D - FICHE RECETTE HUEFORGE PRO ({req.printer_name.upper()})  ",
        "======================================================================",
        f"Image source : {sess.filename}",
        f"Imprimante cible : {req.printer_name} (Plateau {int(req.printer_bed_x_mm)}x{int(req.printer_bed_y_mm)}x{int(req.printer_bed_z_mm)} mm)",
        f"Style Artistique 3D : {req.art_style} (Intensité x{req.art_intensity:.2f}) | Moteur : {req.color_engine}",
        f"Disposition : {req.layout_mode} ({len(tiles)} tuile(s)) | Résolution : {req.grid_resolution}px",
        f"Cadre / Bordure : {req.border_style} ({req.border_width_mm} mm)",
        f"Projet Complet Multi-Plateaux inclus : {base_name}_Projet_HueForge_CFS.3mf",
        f"Paramètres Slicer obligatoires : Remplissage 100% Rectiligne | 1ère couche = {req.first_layer_mm} mm | Hauteur de couche = {req.layer_height_mm} mm",
        "",
        "--- ORDRE DES BOBINES & CHANGEMENTS DE COUCHES (CFS 1 & CFS 2) ---",
    ]
    for s in specs:
        recipe_lines.append(
            f"  [{s.cfs_slot}] Couleur #{s.layer_index} ({s.hex_color.upper()}) : "
            f"Couches {s.start_layer_num} à {s.end_layer_num}  ({s.start_mm:.2f} mm -> {s.end_mm:.2f} mm)"
        )
    if seams:
        recipe_lines.extend([
            "",
            "--- ASSEMBLAGE MULTI-FRAME (CLIPS MÂLES + ENCOCHES FEMELLES AU DOS) ---",
            f"  - Nombre de jonctions inter-tuiles : {len(seams)}",
            f"  - Fichier des clips mâles inclus : Clips_Assemblage_Males_x{len(seams)}.stl",
            "  - Chaque tuile est numérotée au dos (1, 2, 3...) et possède les demi-encoches femelles.",
        ])

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{base_name}_Projet_HueForge_CFS.3mf", project_3mf_bytes)
        for fname, mesh_part in output_files:
            zf.writestr(fname, export_mesh_stl_bytes(mesh_part))
        zf.writestr("RECETTE_COUCHES_CFS_CREALITY_PRINT.txt", "\n".join(recipe_lines).encode("utf-8"))

    sess.last_zip_bytes = zip_buf.getvalue()

    layout_aspect = (bbox_2d[2] - bbox_2d[0]) / max(1.0, (bbox_2d[3] - bbox_2d[1]))
    preview_b64, src_preview_b64, void_pct = render_quantized_preview_base64(
        sess.image_rgb,
        specs=specs,
        aspect_ratio=layout_aspect,
        zoom=req.zoom,
        offset_x_pct=req.offset_x_pct,
        offset_y_pct=req.offset_y_pct,
        detail_boost=req.detail_boost,
        contrast_gamma=req.contrast_gamma,
        td_mm=req.td_mm,
        color_engine=req.color_engine,
        fill_mode=req.fill_mode,
        tiles=tiles,
        border_style=req.border_style,
        border_width_mm=req.border_width_mm,
        return_dual_studio=True,
        art_style=req.art_style,
        art_intensity=req.art_intensity,
    )
    shape_overlay_b64 = render_shape_overlay_base64(
        tiles=tiles,
        border_style=req.border_style,
        border_width_mm=req.border_width_mm,
        aspect_ratio=layout_aspect,
    )

    return {
        "session_id": session_id,
        "layout_mode": req.layout_mode,
        "tiles_count": len(tiles),
        "plates_count": len(output_files),
        "clips_count": len(seams),
        "parts": parts_meta,
        "active_palette": [s.to_dict() for s in specs],
        "preview_data_url": preview_b64,
        "source_preview_data_url": src_preview_b64,
        "shape_overlay_data_url": shape_overlay_b64,
        "void_pct": void_pct,
        "has_validated_outpaint": sess.has_validated_outpaint,
        "recipe_text": "\n".join(recipe_lines),
        "preview_stl_url": f"/api/hueforge/{session_id}/preview-stl",
        "download_zip_url": f"/api/hueforge/{session_id}/download-zip",
        "download_3mf_url": f"/api/hueforge/{session_id}/download-3mf",
    }


@router.get("/{session_id}/preview-stl")
async def get_hueforge_preview_stl(session_id: str):
    sess = _get_hf_session(session_id)
    if sess.last_preview_mesh is None:
        raise HTTPException(status_code=404, detail="Aucun aperçu 3D généré.")
    return Response(
        content=export_mesh_stl_bytes(sess.last_preview_mesh),
        media_type="application/sla",
    )


@router.get("/{session_id}/download-3mf")
async def download_hueforge_3mf(session_id: str):
    sess = _get_hf_session(session_id)
    if not sess.last_3mf_bytes:
        raise HTTPException(status_code=404, detail="Aucun projet .3MF HueForge généré.")
    base = sess.filename.rsplit(".", 1)[0]
    return Response(
        content=sess.last_3mf_bytes,
        media_type="model/3mf",
        headers={"Content-Disposition": f'attachment; filename="{base}_Projet_HueForge_CFS.3mf"'},
    )


@router.get("/{session_id}/download-zip")
async def download_hueforge_zip(session_id: str):
    sess = _get_hf_session(session_id)
    if not sess.last_zip_bytes:
        raise HTTPException(status_code=404, detail="Aucune archive HueForge générée.")
    base = sess.filename.rsplit(".", 1)[0]
    return Response(
        content=sess.last_zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{base}_HueForge_Pro_CFS_Pack.zip"'},
    )


def _get_hf_session(session_id: str) -> HueForgeSession:
    if session_id not in HUEFORGE_SESSIONS:
        raise HTTPException(status_code=404, detail="Session HueForge introuvable ou expirée.")
    return HUEFORGE_SESSIONS[session_id]
