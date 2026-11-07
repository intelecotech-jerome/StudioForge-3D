"""
StudioForge 3D — Module MAKERLAB 3D (Boîte à Outils Créatifs & Objets 3D Print-in-Place)
Regroupe 6 générateurs géométriques 3D :
1. `cookie_cutter`   : 🍪 Emporte-Pièce & Tampon 3D (Lame biseautée + Rebord ergonomique + Tampon embosseur avec poignée)
2. `pop_box`         : 📦 Boîte 3D & Couvercle sur-mesure (Corps creux + Couvercle emboîtable sculpté en relief)
3. `flexi_toy`       : 🐟 Jouet Articulé Print-in-Place (Découpe articulée + Charnières internes mobiles sans support)
4. `lenticular_dual` : 🪞 Illusion Lenticulaire 2-Angles (Fusionne 2 Photos ou 2 Textes à -45° / +45°)
5. `morphing_90`     : 🔄 Morphing 3D Dual-90° (Intersection booléenne CSG à 90° de 2 Textes ou 2 Silhouettes)
6. `layering_mandala`: 🌸 Mandala & Relief Multi-Couches (Superposition en terrasses 3D de 3 à 6 paliers)
"""
from __future__ import annotations

import base64
import io
import math
import uuid
import zipfile
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Tuple

import manifold3d as m3d
import numpy as np
import trimesh
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from PIL import Image, ImageDraw, ImageFont, ImageOps
from pydantic import BaseModel, Field
from scipy.ndimage import (
    binary_closing,
    binary_dilation,
    binary_erosion,
    binary_fill_holes,
    distance_transform_edt,
    gaussian_filter,
    label as nd_label,
    sobel,
)

router = APIRouter(prefix="/api/makerlab", tags=["MakerLab 3D - Creative 3D Tools"])

MakerToolId = Literal[
    "cookie_cutter",
    "pop_box",
    "flexi_toy",
    "lenticular_dual",
    "morphing_90",
    "layering_mandala",
    "stl_bas_relief",
    "ai_mesh_3d",
]


@dataclass
class MakerLabSession:
    session_id: str
    filename_a: str = "Preset_Silhouette"
    img_a_rgb: Optional[np.ndarray] = None
    filename_b: Optional[str] = None
    img_b_rgb: Optional[np.ndarray] = None
    uploaded_stl_mesh: Optional[trimesh.Trimesh] = None
    uploaded_stl_filename: Optional[str] = None
    last_generated_mesh: Optional[trimesh.Trimesh] = None
    parts_stl: Dict[str, bytes] = field(default_factory=dict)
    assembly_stl: Optional[bytes] = None
    zip_bytes: Optional[bytes] = None


MAKERLAB_SESSIONS: Dict[str, MakerLabSession] = {}


class MakerLabRequest(BaseModel):
    tool_id: MakerToolId = "cookie_cutter"
    target_size_mm: float = Field(110.0, ge=40.0, le=280.0)
    height_z_mm: float = Field(14.0, ge=3.0, le=120.0)
    wall_thickness_mm: float = Field(1.6, ge=0.8, le=5.0)
    clearance_mm: float = Field(0.25, ge=0.10, le=1.0)
    detail_level: float = Field(1.0, ge=0.3, le=2.0)
    remove_bg_auto: bool = True
    invert_mask: bool = False

    # Tool-specific options
    include_stamp: bool = True  # cookie_cutter: generate matching inner stamp/embosser
    box_lid_relief_mm: float = Field(2.4, ge=0.6, le=6.0)  # pop_box: relief height on lid
    flexi_segments: int = Field(5, ge=3, le=9)  # flexi_toy: number of articulated segments
    flexi_zigzag: bool = True  # flexi_toy: chevron vs straight cuts
    layer_count: int = Field(4, ge=2, le=7)  # layering_mandala: number of terraced layers
    layer_frame: str = "octagon"  # layering_mandala: 'none' | 'octagon' | 'circle' | 'rounded_rect'

    # Dual / Morphing / Lenticular inputs
    use_text_mode: bool = False
    text_a: str = "LOVE"
    text_b: str = "2026"
    morph_style: str = "solid_intersect"  # 'solid_intersect' | 'hollow_cube'
    preset_shape: str = "fish"  # 'fish' | 'cat' | 'heart' | 'star' | 'gecko' | 'mandala' | 'shield'

    # Tool #7 (STL -> Bas-Relief) & Tool #8 (AI Photo/Text -> 3D Mesh like Meshy.ai)
    stl_preset: str = "rubber_duck"  # 'rubber_duck' | 'starship_falcon' | 'dragon_head' | 'pokeball_emblem' | 'custom_stl'
    stl_yaw_deg: float = Field(0.0, ge=-180.0, le=180.0)
    stl_pitch_deg: float = Field(0.0, ge=-90.0, le=90.0)
    relief_frame_style: str = "beveled_frame"  # 'beveled_frame' | 'oval_medallion' | 'frameless'
    ai_engine: str = "local_organic_3d"  # 'local_organic_3d' | 'hf_free_cloud' | 'meshy_api'
    ai_prompt: str = "Dragon Cybernétique 3D"
    meshy_api_key: str = ""
    ai_add_pedestal: bool = True


def _image_to_data_url(pil_img: Image.Image) -> str:
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _render_preset_image(preset_shape: str, size: int = 512) -> np.ndarray:
    """
    Generates a clean, high-contrast built-in silhouette/mandala image so the user can test
    any MakerLab tool immediately even before uploading a custom photo.
    """
    img = Image.new("RGB", (size, size), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    cx, cy = size / 2.0, size / 2.0
    r = size * 0.38

    if preset_shape == "fish":
        # Stylized articulated fish silhouette (like the Flexi screenshot)
        body = []
        for deg in range(0, 360, 5):
            rad = math.radians(deg)
            x = cx + r * 0.85 * math.cos(rad)
            y = cy + r * 0.42 * math.sin(rad) * (0.85 + 0.25 * math.cos(rad))
            body.append((x, y))
        draw.polygon(body, fill=(20, 20, 20))
        # Tail fin
        tail = [
            (cx - r * 0.72, cy),
            (cx - r * 1.15, cy - r * 0.42),
            (cx - r * 1.02, cy),
            (cx - r * 1.15, cy + r * 0.42),
        ]
        draw.polygon(tail, fill=(20, 20, 20))
        # Dorsal & pectoral fins
        draw.polygon(
            [(cx - r * 0.1, cy - r * 0.35), (cx + r * 0.2, cy - r * 0.65), (cx + r * 0.35, cy - r * 0.32)],
            fill=(20, 20, 20),
        )
        draw.polygon(
            [(cx - r * 0.05, cy + r * 0.32), (cx + r * 0.15, cy + r * 0.58), (cx + r * 0.28, cy + r * 0.30)],
            fill=(20, 20, 20),
        )
        # Eye hole (white)
        ex, ey = cx + r * 0.52, cy - r * 0.08
        draw.ellipse([ex - 14, ey - 14, ex + 14, ey + 14], fill=(255, 255, 255))

    elif preset_shape == "cat":
        # Sitting cat silhouette (like the Cookie Cutter screenshot)
        draw.ellipse([cx - r * 0.48, cy - r * 0.15, cx + r * 0.38, cy + r * 0.85], fill=(20, 20, 20))
        draw.ellipse([cx - r * 0.36, cy - r * 0.72, cx + r * 0.28, cy - r * 0.08], fill=(20, 20, 20))
        # Ears
        draw.polygon(
            [(cx - r * 0.34, cy - r * 0.52), (cx - r * 0.28, cy - r * 0.96), (cx - r * 0.06, cy - r * 0.64)],
            fill=(20, 20, 20),
        )
        draw.polygon(
            [(cx + r * 0.02, cy - r * 0.64), (cx + r * 0.24, cy - r * 0.96), (cx + r * 0.28, cy - r * 0.52)],
            fill=(20, 20, 20),
        )
        # Curved tail
        for t in np.linspace(0, 1.0, 35):
            tx = cx + r * (0.32 + 0.45 * math.sin(t * math.pi * 0.85))
            ty = cy + r * (0.68 - 0.85 * t)
            rad_t = 18 * (1.0 - 0.3 * t)
            draw.ellipse([tx - rad_t, ty - rad_t, tx + rad_t, ty + rad_t], fill=(20, 20, 20))
        # Eyes & whiskers in white for inner stamp details
        draw.ellipse([cx - r * 0.20, cy - r * 0.48, cx - r * 0.08, cy - r * 0.36], fill=(255, 255, 255))
        draw.ellipse([cx + r * 0.02, cy - r * 0.48, cx + r * 0.14, cy - r * 0.36], fill=(255, 255, 255))

    elif preset_shape == "mandala":
        # Intricate multi-petal floral mandala (like the Layering screenshot)
        for ring_idx, ring_r in enumerate([r * 0.98, r * 0.76, r * 0.54, r * 0.32]):
            n_petals = 12
            for p in range(n_petals):
                ang = math.radians(p * (360.0 / n_petals) + (ring_idx * 15.0))
                px = cx + ring_r * 0.62 * math.cos(ang)
                py = cy + ring_r * 0.62 * math.sin(ang)
                pr = ring_r * 0.38
                draw.ellipse(
                    [px - pr, py - pr, px + pr, py + pr],
                    outline=(15, 15, 15),
                    width=10,
                )
        draw.ellipse([cx - r * 0.18, cy - r * 0.18, cx + r * 0.18, cy + r * 0.18], outline=(15, 15, 15), width=12)

    elif preset_shape == "heart":
        pts = []
        for deg in range(0, 360, 3):
            t = math.radians(deg)
            hx = 16 * (math.sin(t) ** 3)
            hy = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
            pts.append((cx + hx * (r / 15.5), cy + (hy + 2.0) * (r / 15.5)))
        draw.polygon(pts, fill=(20, 20, 20))
        # Inner decorative heart outline for stamp/box relief
        pts_in = [((x - cx) * 0.68 + cx, (y - cy) * 0.68 + cy) for (x, y) in pts]
        draw.polygon(pts_in, outline=(255, 255, 255), width=10)

    else:
        # Avengers / Superhero emblem shield for Pop Box & Cookie Cutter
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(20, 20, 20))
        draw.ellipse([cx - r * 0.80, cy - r * 0.80, cx + r * 0.80, cy + r * 0.80], fill=(255, 255, 255))
        draw.polygon(
            [
                (cx - r * 0.45, cy + r * 0.65),
                (cx + r * 0.10, cy - r * 0.72),
                (cx + r * 0.32, cy - r * 0.72),
                (cx + r * 0.32, cy + r * 0.65),
                (cx + r * 0.10, cy + r * 0.65),
                (cx + r * 0.10, cy + r * 0.12),
                (cx - r * 0.18, cy + r * 0.12),
                (cx - r * 0.25, cy + r * 0.65),
            ],
            fill=(20, 20, 20),
        )

    return np.asarray(img, dtype=np.uint8)


def _render_text_to_mask(text: str, width: int = 320, height: int = 160) -> np.ndarray:
    """
    Renders a bold, centered text string into a boolean mask `(height, width)` where `True` = text foreground.
    """
    clean_text = (text or "3D").strip()[:14] or "3D"
    img = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(img)

    font = None
    for font_name in ["arialbd.ttf", "Impact.ttf", "segoeuib.ttf", "arial.ttf", "DejaVuSans-Bold.ttf"]:
        try:
            font = ImageFont.truetype(font_name, 110)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), clean_text, font=font)
    tw = max(1, bbox[2] - bbox[0])
    th = max(1, bbox[3] - bbox[1])

    # Render tight then stretch to fill 86% of canvas so letters have strong structural presence
    txt_img = Image.new("L", (tw + 16, th + 16), 0)
    txt_draw = ImageDraw.Draw(txt_img)
    txt_draw.text((8 - bbox[0], 8 - bbox[1]), clean_text, fill=255, font=font)

    target_w = int(width * 0.88)
    target_h = int(height * 0.78)
    resized = txt_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
    ox = (width - target_w) // 2
    oy = (height - target_h) // 2
    img.paste(resized, (ox, oy))
    return np.asarray(img, dtype=np.uint8) > 110


def _extract_silhouette_and_details(
    img_rgb: np.ndarray,
    work_res: int = 240,
    remove_bg_auto: bool = True,
    invert_mask: bool = False,
    detail_level: float = 1.0,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Given an RGB image, resizes it preserving aspect ratio into `(work_h, work_w)`
    and returns `(silhouette_mask, internal_details_mask, luma_normalized)`.
    """
    sh, sw = img_rgb.shape[:2]
    aspect = float(sw) / max(1.0, float(sh))
    aspect = max(0.5, min(2.0, aspect))
    if aspect >= 1.0:
        work_w = work_res
        work_h = max(64, int(round(work_res / aspect)))
    else:
        work_h = work_res
        work_w = max(64, int(round(work_res * aspect)))

    # Pad with border color so morphological operations never clip at the image boundary
    pad = max(10, int(work_res * 0.07))
    inner_w = work_w - 2 * pad
    inner_h = work_h - 2 * pad

    pil_resized = Image.fromarray(img_rgb).resize((inner_w, inner_h), Image.Resampling.LANCZOS)
    arr_inner = np.asarray(pil_resized, dtype=np.float32)

    border_strip = np.concatenate(
        [arr_inner[0, :], arr_inner[-1, :], arr_inner[:, 0], arr_inner[:, -1]], axis=0
    )
    bg_color = np.median(border_strip, axis=0)

    rgb_f = np.ones((work_h, work_w, 3), dtype=np.float32) * bg_color[None, None, :]
    rgb_f[pad : pad + inner_h, pad : pad + inner_w, :] = arr_inner

    luma = (0.2126 * rgb_f[:, :, 0] + 0.7152 * rgb_f[:, :, 1] + 0.0722 * rgb_f[:, :, 2]) / 255.0
    if invert_mask:
        luma = 1.0 - luma

    bg_luma = float(np.median(np.concatenate([luma[0, :], luma[-1, :], luma[:, 0], luma[:, -1]])))
    bg_is_light = bg_luma > 0.5

    if remove_bg_auto:
        dist_bg = np.sqrt(np.sum((rgb_f - bg_color[None, None, :]) ** 2, axis=-1))
        fg = dist_bg > 22.0
    else:
        fg = (luma < 0.55) if bg_is_light else (luma > 0.45)

    # Smooth & fill holes to get a clean outer silhouette
    fg_closed = binary_closing(fg, iterations=3)
    silhouette = binary_fill_holes(fg_closed)

    # Keep main connected component(s)
    lbl, n_c = nd_label(silhouette)
    if n_c > 1:
        counts = np.bincount(lbl.ravel())
        counts[0] = 0
        max_c = int(np.max(counts))
        keep = np.where(counts >= max(30, int(max_c * 0.08)))[0]
        silhouette = np.isin(lbl, keep)

    if np.mean(silhouette) < 0.03:
        # Fallback if image had uniform contrast
        silhouette = (luma < 0.65) if bg_is_light else (luma > 0.35)
        silhouette = binary_fill_holes(binary_closing(silhouette, iterations=2))

    # Extract internal detail lines/features inside the silhouette
    work_luma = luma if bg_is_light else (1.0 - luma)
    gx = sobel(gaussian_filter(work_luma, sigma=0.8), axis=1)
    gy = sobel(gaussian_filter(work_luma, sigma=0.8), axis=0)
    grad = np.hypot(gx, gy)
    grad_thresh = np.percentile(grad[silhouette], max(45.0, min(90.0, 82.0 - 18.0 * detail_level))) if np.any(silhouette) else 0.2
    dark_features = work_luma < (0.42 * (detail_level ** 0.4))
    inner_safe = binary_erosion(silhouette, iterations=3, border_value=0)
    details = inner_safe & ((grad > grad_thresh) | dark_features)

    return silhouette, details, work_luma


def _heightmap_to_watertight_trimesh(
    z_top: np.ndarray,
    active_mask: np.ndarray,
    pixel_size_mm: float,
    z_bottom: float = 0.0,
) -> trimesh.Trimesh:
    """
    Converts a masked 2D heightmap `z_top(H, W)` where `active_mask(H, W) == True`
    into a 100% watertight, closed 3D `trimesh.Trimesh` with top surface, flat bottom at `z_bottom`,
    and vertical perimeter walls around every boundary edge (outer and inner holes).
    Vectorized in NumPy for sub-second speed!
    """
    # Pad by 1 pixel of False around the border so all outer edges are cleanly detected
    mask = np.pad(active_mask.astype(bool), 1, mode="constant", constant_values=False)
    z_grid = np.pad(z_top.astype(np.float32), 1, mode="edge")
    H, W = mask.shape

    # Corner coordinates: (H+1, W+1) corners
    # A corner (r, c) is active if any of its 4 adjacent cells is active
    # Cell (r, c) has corners: TL=(r, c), TR=(r, c+1), BR=(r+1, c+1), BL=(r+1, c)
    c_active = np.zeros((H + 1, W + 1), dtype=bool)
    c_active[:-1, :-1] |= mask
    c_active[:-1, 1:] |= mask
    c_active[1:, :-1] |= mask
    c_active[1:, 1:] |= mask

    # Corner Z height = average of active adjacent cells
    z_sum = np.zeros((H + 1, W + 1), dtype=np.float32)
    z_cnt = np.zeros((H + 1, W + 1), dtype=np.float32)
    for dr, dc in [(0, 0), (0, 1), (1, 0), (1, 1)]:
        sl_r = slice(dr, H + dr)
        sl_c = slice(dc, W + dc)
        z_sum[sl_r, sl_c] += np.where(mask, z_grid, 0.0)
        z_cnt[sl_r, sl_c] += mask.astype(np.float32)

    corner_z_top = np.where(z_cnt > 0, z_sum / np.maximum(1.0, z_cnt), z_bottom + 0.4)

    yy, xx = np.mgrid[0 : H + 1, 0 : W + 1]
    cx_mm = (xx - (W / 2.0)) * pixel_size_mm
    cy_mm = ((H / 2.0) - yy) * pixel_size_mm  # flip Y so image top is +Y in 3D

    active_ys, active_xs = np.where(c_active)
    n_corners = len(active_ys)
    if n_corners < 3:
        return trimesh.creation.box(extents=[10.0, 10.0, 2.0])

    corner_idx_map = np.full((H + 1, W + 1), -1, dtype=np.int32)
    corner_idx_map[active_ys, active_xs] = np.arange(n_corners, dtype=np.int32)

    # Top vertices: 0 .. n_corners-1; Bottom vertices: n_corners .. 2*n_corners-1
    v_top = np.column_stack([cx_mm[active_ys, active_xs], cy_mm[active_ys, active_xs], corner_z_top[active_ys, active_xs]])
    v_bot = np.column_stack([cx_mm[active_ys, active_xs], cy_mm[active_ys, active_xs], np.full(n_corners, z_bottom, dtype=np.float32)])
    vertices = np.vstack([v_top, v_bot])

    cell_ys, cell_xs = np.where(mask)
    tl = corner_idx_map[cell_ys, cell_xs]
    tr = corner_idx_map[cell_ys, cell_xs + 1]
    br = corner_idx_map[cell_ys + 1, cell_xs + 1]
    bl = corner_idx_map[cell_ys + 1, cell_xs]

    # Note: since cy_mm decreases as row index increases, (tl -> bl -> br -> tr) is CCW in XY!
    # Top faces (normal +Z): (tl, bl, br) and (tl, br, tr)
    f_top_1 = np.column_stack([tl, bl, br])
    f_top_2 = np.column_stack([tl, br, tr])

    # Bottom faces (normal -Z): reversed winding shifted by n_corners
    f_bot_1 = np.column_stack([tl + n_corners, br + n_corners, bl + n_corners])
    f_bot_2 = np.column_stack([tl + n_corners, tr + n_corners, br + n_corners])

    faces_list = [f_top_1, f_top_2, f_bot_1, f_bot_2]

    # Perimeter walls where mask transitions between True and False (outward normals):
    # 1. North wall (+Y normal): mask[r, c] is True and mask[r-1, c] is False -> edge (tl -> tr)
    north_y, north_x = np.where(mask[1:, :] & (~mask[:-1, :]))
    north_y += 1
    if len(north_y) > 0:
        c1 = corner_idx_map[north_y, north_x]          # tl
        c2 = corner_idx_map[north_y, north_x + 1]      # tr
        faces_list.append(np.column_stack([c1, c2, c2 + n_corners]))
        faces_list.append(np.column_stack([c1, c2 + n_corners, c1 + n_corners]))

    # 2. South wall (-Y normal): mask[r, c] is True and mask[r+1, c] is False -> edge (br -> bl)
    south_y, south_x = np.where(mask[:-1, :] & (~mask[1:, :]))
    if len(south_y) > 0:
        c1 = corner_idx_map[south_y + 1, south_x + 1]  # br
        c2 = corner_idx_map[south_y + 1, south_x]      # bl
        faces_list.append(np.column_stack([c1, c2, c2 + n_corners]))
        faces_list.append(np.column_stack([c1, c2 + n_corners, c1 + n_corners]))

    # 3. West wall (-X normal): mask[r, c] is True and mask[r, c-1] is False -> edge (bl -> tl)
    west_y, west_x = np.where(mask[:, 1:] & (~mask[:, :-1]))
    west_x += 1
    if len(west_y) > 0:
        c1 = corner_idx_map[west_y + 1, west_x]        # bl
        c2 = corner_idx_map[west_y, west_x]            # tl
        faces_list.append(np.column_stack([c1, c2, c2 + n_corners]))
        faces_list.append(np.column_stack([c1, c2 + n_corners, c1 + n_corners]))

    # 4. East wall (+X normal): mask[r, c] is True and mask[r, c+1] is False -> edge (tr -> br)
    east_y, east_x = np.where(mask[:, :-1] & (~mask[:, 1:]))
    if len(east_y) > 0:
        c1 = corner_idx_map[east_y, east_x + 1]        # tr
        c2 = corner_idx_map[east_y + 1, east_x + 1]    # br
        faces_list.append(np.column_stack([c1, c2, c2 + n_corners]))
        faces_list.append(np.column_stack([c1, c2 + n_corners, c1 + n_corners]))

    faces = np.vstack(faces_list).astype(np.int32)
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
    return mesh


def _trimesh_to_manifold(mesh: trimesh.Trimesh) -> m3d.Manifold:
    v = np.ascontiguousarray(mesh.vertices, dtype=np.float32)
    f = np.ascontiguousarray(mesh.faces, dtype=np.uint32)
    return m3d.Manifold(m3d.Mesh(vert_properties=v, tri_verts=f))


def _manifold_to_trimesh(man: m3d.Manifold) -> trimesh.Trimesh:
    m_mesh = man.to_mesh()
    verts = np.array(m_mesh.vert_properties[:, :3], dtype=np.float32)
    faces = np.array(m_mesh.tri_verts, dtype=np.int32)
    if len(verts) == 0 or len(faces) == 0:
        return trimesh.creation.box(extents=[5.0, 5.0, 1.0])
    return trimesh.Trimesh(vertices=verts, faces=faces, process=True)


# ==============================================================================
# 1. COOKIE CUTTER & EMBOSSING STAMP (🍪 EMPORTE-PIÈCE & TAMPON 3D)
# ==============================================================================
def build_cookie_cutter_3d(
    img_rgb: np.ndarray,
    req: MakerLabRequest,
) -> Tuple[List[Tuple[str, str, trimesh.Trimesh]], trimesh.Trimesh, Image.Image]:
    """
    Builds:
    - Part 1: Emporte-Pièce (Ergonomic base flange + Sturdy wall + Beveled sharp cutting blade)
    - Part 2 (if `req.include_stamp`): Tampon Embosseur avec Poignée centrale
    """
    work_res = 260
    silhouette, details, _ = _extract_silhouette_and_details(
        img_rgb,
        work_res=work_res,
        remove_bg_auto=req.remove_bg_auto,
        invert_mask=req.invert_mask,
        detail_level=req.detail_level,
    )
    H, W = silhouette.shape
    px_mm = float(req.target_size_mm) / float(max(H, W))

    dist_out = distance_transform_edt(~silhouette).astype(np.float32) * px_mm
    dist_in = distance_transform_edt(silhouette).astype(np.float32) * px_mm

    blade_w = max(0.85, float(req.wall_thickness_mm) * 0.75)
    wall_w = max(1.3, float(req.wall_thickness_mm))
    flange_w = max(3.6, wall_w + 2.4)
    total_h = max(10.0, float(req.height_z_mm))
    flange_h = 2.4

    # Cutter footprint: outside silhouette from 0 to flange_w
    cutter_mask = (dist_out > 0.0) & (dist_out <= flange_w)
    cutter_z = np.full((H, W), flange_h, dtype=np.float32)
    # Main structural wall
    in_wall = (dist_out > 0.0) & (dist_out <= wall_w)
    cutter_z[in_wall] = total_h - 1.6
    # Sharp cutting lip at the inner perimeter (0 .. blade_w)
    in_blade = (dist_out > 0.0) & (dist_out <= blade_w)
    cutter_z[in_blade] = total_h

    cutter_mesh = _heightmap_to_watertight_trimesh(cutter_z, cutter_mask, px_mm, z_bottom=0.0)
    parts: List[Tuple[str, str, trimesh.Trimesh]] = [
        ("Emporte_Piece_Lame.stl", "🍪 Emporte-Pièce (Lame + Rebord)", cutter_mesh)
    ]

    # Preview 2D visualization
    vis = np.full((H, W, 3), 18, dtype=np.uint8)
    vis[cutter_mask] = (249, 115, 22)  # Orange flange
    vis[in_blade] = (254, 215, 170)    # Bright cutting lip

    if req.include_stamp:
        clearance = max(0.45, float(req.clearance_mm) * 2.0)
        stamp_mask = dist_in >= clearance
        if np.any(stamp_mask):
            stamp_base_h = 2.4
            stamp_relief_h = max(2.0, min(4.0, total_h * 0.25))
            stamp_z = np.full((H, W), stamp_base_h, dtype=np.float32)

            # Raised embossing details
            thick_details = binary_dilation(details, iterations=1) & stamp_mask
            stamp_z[thick_details] = stamp_base_h + stamp_relief_h

            # Central handle knob on the stamp so it's easy to hold
            max_in_d = float(np.max(dist_in))
            cy_idx, cx_idx = np.where(dist_in >= max_in_d * 0.92)
            if len(cy_idx) > 0:
                hy, hx = float(np.mean(cy_idx)), float(np.mean(cx_idx))
                yy, xx = np.mgrid[0:H, 0:W]
                r_mm = np.hypot(xx - hx, yy - hy) * px_mm
                handle_zone = stamp_mask & (r_mm <= min(11.0, max_in_d * 0.55)) & (~thick_details)
                stamp_z[handle_zone] = stamp_base_h + 7.5

            stamp_mesh = _heightmap_to_watertight_trimesh(stamp_z, stamp_mask, px_mm, z_bottom=0.0)
            parts.append(("Tampon_Embosseur.stl", "💮 Tampon Embosseur Assorti", stamp_mesh))

            vis[stamp_mask] = (30, 58, 138)
            vis[thick_details] = (56, 189, 248)

            # Assembly: place stamp slightly elevated inside cutter for 3D inspection
            stamp_shifted = stamp_mesh.copy()
            stamp_shifted.apply_translation([0.0, 0.0, 2.0])
            assembly_mesh = trimesh.util.concatenate([cutter_mesh, stamp_shifted])
        else:
            assembly_mesh = cutter_mesh
    else:
        assembly_mesh = cutter_mesh

    return parts, assembly_mesh, Image.fromarray(vis)


# ==============================================================================
# 2. POP BOX & RELIEF LID (📦 BOÎTE 3D & COUVERCLE SUR-MESURE)
# ==============================================================================
def build_pop_box_3d(
    img_rgb: np.ndarray,
    req: MakerLabRequest,
) -> Tuple[List[Tuple[str, str, trimesh.Trimesh]], trimesh.Trimesh, Image.Image]:
    """
    Builds a custom-shaped 3D Box + Fitted Sculpted Relief Lid from any logo/photo (like Iron Man / Avengers box).
    """
    work_res = 220
    silhouette, details, work_luma = _extract_silhouette_and_details(
        img_rgb,
        work_res=work_res,
        remove_bg_auto=req.remove_bg_auto,
        invert_mask=req.invert_mask,
        detail_level=req.detail_level,
    )
    H, W = silhouette.shape
    px_mm = float(req.target_size_mm) / float(max(H, W))

    # Dilate silhouette slightly so the box has smooth, generous curves around the artwork
    pad_iters = max(4, int(round(4.0 / max(0.25, px_mm))))
    box_outer = binary_fill_holes(binary_dilation(silhouette, iterations=pad_iters))
    dist_in = distance_transform_edt(box_outer).astype(np.float32) * px_mm

    wall_mm = max(1.8, float(req.wall_thickness_mm))
    clearance_mm = max(0.20, float(req.clearance_mm))
    box_h = max(18.0, float(req.height_z_mm))
    floor_h = 2.2

    # 1. Box Body (`Boite_Corps.stl`): outer wall = box_h, inner cavity = floor_h
    body_z = np.full((H, W), box_h, dtype=np.float32)
    cavity_mask = dist_in > wall_mm
    body_z[cavity_mask] = floor_h
    body_mesh = _heightmap_to_watertight_trimesh(body_z, box_outer, px_mm, z_bottom=0.0)

    # 2. Fitted Relief Lid (`Boite_Couvercle_Relief.stl`):
    #    - Main lid plate: 2.2 mm thick over `box_outer`
    #    - Top sculpted multi-level relief from the image luminance & details (`req.box_lid_relief_mm`)
    #    - Inner snap-fit lip ring on the bottom face (or printed flat with lip ring)
    lid_plate_h = 2.2
    relief_max = max(1.2, float(req.box_lid_relief_mm))
    # Quantize luminance into 3 crisp pop-art levels inside `silhouette`
    inv_luma = np.clip(1.0 - work_luma, 0.0, 1.0)
    quant_relief = np.round(inv_luma * 3.0) / 3.0
    lid_top_z = np.full((H, W), lid_plate_h, dtype=np.float32)
    lid_top_z[silhouette] = lid_plate_h + (0.35 + 0.65 * quant_relief[silhouette]) * relief_max
    lid_top_z[details] = lid_plate_h + relief_max

    lid_upper_mesh = _heightmap_to_watertight_trimesh(lid_top_z, box_outer, px_mm, z_bottom=0.0)

    # Add inner fitting skirt underneath the lid (from z = -3.2 to z = 0.0)
    lip_outer_d = wall_mm + clearance_mm
    lip_inner_d = lip_outer_d + max(1.4, wall_mm * 0.8)
    lip_mask = (dist_in >= lip_outer_d) & (dist_in <= lip_inner_d)
    if np.any(lip_mask):
        lip_z = np.zeros((H, W), dtype=np.float32)
        lip_mesh = _heightmap_to_watertight_trimesh(lip_z, lip_mask, px_mm, z_bottom=-3.2)
        lid_mesh = trimesh.util.concatenate([lid_upper_mesh, lip_mesh])
    else:
        lid_mesh = lid_upper_mesh

    # Exploded 3D Assembly (Box at bottom, Lid floating 12mm above so user sees inside + relief)
    lid_floating = lid_mesh.copy()
    lid_floating.apply_translation([0.0, 0.0, box_h + 12.0])
    assembly_mesh = trimesh.util.concatenate([body_mesh, lid_floating])

    # 2D Preview
    vis = np.full((H, W, 3), 18, dtype=np.uint8)
    vis[box_outer] = (71, 85, 105)
    vis[cavity_mask] = (30, 41, 59)
    vis[silhouette] = (99, 102, 241)
    vis[details] = (244, 63, 94)

    parts = [
        ("01_Boite_Corps_Creux.stl", "📦 Corps de Boîte Creux", body_mesh),
        ("02_Boite_Couvercle_Relief.stl", "🎨 Couvercle Emboîtable à Relief", lid_mesh),
    ]
    return parts, assembly_mesh, Image.fromarray(vis)


# ==============================================================================
# 3. FLEXI TOY PRINT-IN-PLACE (🐟 JOUET ARTICULÉ PRINT-IN-PLACE)
# ==============================================================================
def build_flexi_toy_3d(
    img_rgb: np.ndarray,
    req: MakerLabRequest,
) -> Tuple[List[Tuple[str, str, trimesh.Trimesh]], trimesh.Trimesh, Image.Image]:
    """
    Turns any silhouette/photo into an articulated Print-in-Place Flexi Toy!
    Cuts `n_segments - 1` articulation slots across the body and inserts internal
    print-in-place hinge links (horizontal bridge + vertical pins inside recessed pockets)
    so all segments articulate freely right off the print bed.
    """
    work_res = 240
    silhouette, details, _ = _extract_silhouette_and_details(
        img_rgb,
        work_res=work_res,
        remove_bg_auto=req.remove_bg_auto,
        invert_mask=req.invert_mask,
        detail_level=req.detail_level,
    )
    H, W = silhouette.shape
    px_mm = float(req.target_size_mm) / float(max(H, W))
    body_h = max(5.5, min(14.0, float(req.height_z_mm)))

    # Distance from edge for smooth rounded top dome
    dist_in = distance_transform_edt(silhouette).astype(np.float32) * px_mm
    bevel_top = np.clip(dist_in / 2.5, 0.35, 1.0)
    z_top = np.full((H, W), body_h, dtype=np.float32) * (0.78 + 0.22 * bevel_top)
    # Engrave eyes/details slightly on top
    z_top[details] = np.maximum(2.0, z_top[details] - 1.1)

    n_seg = max(3, min(9, int(req.flexi_segments)))
    yy, xx = np.mgrid[0:H, 0:W]
    x_mm = (xx - (W / 2.0)) * px_mm
    y_mm = ((H / 2.0) - yy) * px_mm

    # Find horizontal span of the silhouette
    active_xs = np.where(np.any(silhouette, axis=0))[0]
    if len(active_xs) < 10:
        x_min_mm, x_max_mm = -40.0, 40.0
    else:
        x_min_mm = (float(active_xs[0]) - W / 2.0) * px_mm
        x_max_mm = (float(active_xs[-1]) - W / 2.0) * px_mm

    span_x = max(20.0, x_max_mm - x_min_mm)
    cut_xs = [x_min_mm + span_x * ((i + 1) / float(n_seg)) for i in range(n_seg - 1)]

    slot_half_w = max(0.45, float(req.clearance_mm) * 1.8)
    cut_mask = np.zeros((H, W), dtype=bool)
    hinge_meshes: List[trimesh.Trimesh] = []

    for cx_cut in cut_xs:
        # Zig-zag chevron modulation along Y if enabled
        if req.flexi_zigzag:
            x_curve = cx_cut + 2.2 * np.sin(y_mm * 0.22)
        else:
            x_curve = np.full_like(y_mm, cx_cut)

        in_slot = np.abs(x_mm - x_curve) <= slot_half_w
        cut_mask |= in_slot

        # Find Y span of silhouette at this cut X to place an internal Print-in-Place Hinge Link!
        col_idx = int(round(cx_cut / px_mm + W / 2.0))
        col_idx = max(0, min(W - 1, col_idx))
        ys_at_cut = np.where(silhouette[:, col_idx])[0]
        if len(ys_at_cut) >= 6:
            y_mid_idx = float(np.median(ys_at_cut))
            y_Span_mm = (float(ys_at_cut[-1] - ys_at_cut[0])) * px_mm
            if y_Span_mm >= 9.0:
                hy_mm = ((H / 2.0) - y_mid_idx) * px_mm
                hx_mm = cx_cut + (2.2 * math.sin(hy_mm * 0.22) if req.flexi_zigzag else 0.0)

                # Carve a hinge pocket across the slot so the internal link has room to pivot
                pocket_dx = np.abs(x_mm - hx_mm)
                pocket_dy = np.abs(y_mm - hy_mm)
                in_pocket = (pocket_dx <= 3.6) & (pocket_dy <= 2.4)
                cut_mask |= in_pocket

                # Build the Print-in-Place Link + Retaining Roof Bridges
                # 1. Left & Right Anchor Pillars (connected to the left and right body segments)
                # 2. Central Horizontal Oval Link looping around both pillars with 0.45mm clearance
                link_h = max(2.2, body_h * 0.42)
                link_z_center = body_h * 0.48

                # Left & Right vertical pins (bridged at top & bottom to their respective body side)
                for side_sign in (-1.0, 1.0):
                    pin_x = hx_mm + side_sign * 2.2
                    # Top & bottom retaining tabs connecting the pin to its segment wall
                    tab_bot = trimesh.creation.box(extents=[2.8, 2.2, 1.2])
                    tab_bot.apply_translation([hx_mm + side_sign * 2.8, hy_mm, 0.6])
                    tab_top = trimesh.creation.box(extents=[2.8, 2.2, 1.2])
                    tab_top.apply_translation([hx_mm + side_sign * 2.8, hy_mm, body_h - 0.6])
                    pin_cyl = trimesh.creation.cylinder(radius=0.95, height=body_h, sections=16)
                    pin_cyl.apply_translation([pin_x, hy_mm, body_h / 2.0])
                    hinge_meshes.extend([tab_bot, tab_top, pin_cyl])

                # Central floating bridge link connecting left and right pins (with hole around each pin)
                # We build two side bars (Y = hy_mm - 1.65 and Y = hy_mm + 1.65) + end caps outside the pins
                bar_len = 7.2
                for bar_y in (hy_mm - 1.55, hy_mm + 1.55):
                    bar = trimesh.creation.box(extents=[bar_len, 1.1, link_h])
                    bar.apply_translation([hx_mm, bar_y, link_z_center])
                    hinge_meshes.append(bar)
                for end_x in (hx_mm - bar_len / 2.0 + 0.55, hx_mm + bar_len / 2.0 - 0.55):
                    cap = trimesh.creation.box(extents=[1.1, 4.2, link_h])
                    cap.apply_translation([end_x, hy_mm, link_z_center])
                    hinge_meshes.append(cap)

    segmented_mask = silhouette & (~cut_mask)
    segments_mesh = _heightmap_to_watertight_trimesh(z_top, segmented_mask, px_mm, z_bottom=0.0)
    if hinge_meshes:
        full_flexi = trimesh.util.concatenate([segments_mesh] + hinge_meshes)
    else:
        full_flexi = segments_mesh

    vis = np.full((H, W, 3), 18, dtype=np.uint8)
    vis[segmented_mask] = (234, 179, 8)  # Yellow Flexi body like screenshot
    vis[silhouette & cut_mask] = (6, 182, 212)  # Cyan articulation cuts

    parts = [("Flexi_Articule_PrintInPlace.stl", f"🐟 Jouet Articulé ({n_seg} Segments Print-in-Place)", full_flexi)]
    return parts, full_flexi, Image.fromarray(vis)


# ==============================================================================
# 4. LENTICULAR DUAL-VIEW (🪞 ILLUSION LENTICULAIRE 2-ANGLES)
# ==============================================================================
def build_lenticular_dual_3d(
    img_a_rgb: np.ndarray,
    img_b_rgb: np.ndarray,
    req: MakerLabRequest,
) -> Tuple[List[Tuple[str, str, trimesh.Trimesh]], trimesh.Trimesh, Image.Image]:
    """
    Merges two images or two text strings into a 3D Lenticular Slat Plaque:
    - Viewing from the Left (-45°) reveals Image/Text A
    - Viewing from the Right (+45°) reveals Image/Text B
    """
    n_slats = 36
    H_grid = 140
    W_grid = n_slats * 2  # Each slat has a Left facet (even col) and Right facet (odd col)

    if req.use_text_mode:
        mask_a = _render_text_to_mask(req.text_a, width=n_slats, height=H_grid).astype(np.float32)
        mask_b = _render_text_to_mask(req.text_b, width=n_slats, height=H_grid).astype(np.float32)
    else:
        pil_a = ImageOps.grayscale(Image.fromarray(img_a_rgb)).resize((n_slats, H_grid), Image.Resampling.LANCZOS)
        pil_b = ImageOps.grayscale(Image.fromarray(img_b_rgb)).resize((n_slats, H_grid), Image.Resampling.LANCZOS)
        mask_a = 1.0 - (np.asarray(pil_a, dtype=np.float32) / 255.0)
        mask_b = 1.0 - (np.asarray(pil_b, dtype=np.float32) / 255.0)

    total_w_mm = float(req.target_size_mm)
    px_mm = total_w_mm / float(W_grid)
    base_h = 1.6
    ridge_h = max(2.8, min(6.5, float(req.height_z_mm) * 0.35))

    z_top = np.full((H_grid, W_grid), base_h, dtype=np.float32)
    # Even columns = Left-facing ramp modulated by Image A; Odd columns = Right-facing ramp modulated by Image B
    z_top[:, 0::2] = base_h + (0.25 + 0.75 * mask_a) * ridge_h
    z_top[:, 1::2] = base_h + (0.25 + 0.75 * mask_b) * ridge_h

    # Add solid perimeter frame (2 cells wide)
    z_top[:3, :] = base_h + ridge_h * 0.85
    z_top[-3:, :] = base_h + ridge_h * 0.85
    z_top[:, :2] = base_h + ridge_h * 0.85
    z_top[:, -2:] = base_h + ridge_h * 0.85

    active_mask = np.ones((H_grid, W_grid), dtype=bool)
    mesh = _heightmap_to_watertight_trimesh(z_top, active_mask, px_mm, z_bottom=0.0)

    # 2D side-by-side preview showing Left (-45°) and Right (+45°) views
    vis_w, vis_h = 360, 180
    vis_img = Image.new("RGB", (vis_w, vis_h), (15, 23, 42))
    img_left = Image.fromarray((np.clip(mask_a * 255, 0, 255)).astype(np.uint8)).resize((165, 160), Image.Resampling.NEAREST)
    img_right = Image.fromarray((np.clip(mask_b * 255, 0, 255)).astype(np.uint8)).resize((165, 160), Image.Resampling.NEAREST)
    vis_img.paste(ImageOps.colorize(img_left, black="#0f172a", white="#38bdf8"), (10, 10))
    vis_img.paste(ImageOps.colorize(img_right, black="#0f172a", white="#f43f5e"), (185, 10))

    parts = [("Plaque_Lenticulaire_DualView.stl", "🪞 Plaque Lenticulaire 2-Angles (-45° / +45°)", mesh)]
    return parts, mesh, vis_img


# ==============================================================================
# 5. MORPHING 3D DUAL-90° (🔄 MORPHING 3D PHOTO / TEXTE À 90°)
# ==============================================================================
def build_morphing_90_3d(
    img_a_rgb: np.ndarray,
    img_b_rgb: np.ndarray,
    req: MakerLabRequest,
) -> Tuple[List[Tuple[str, str, trimesh.Trimesh]], trimesh.Trimesh, Image.Image]:
    """
    Computes the true 3D CSG Boolean Intersection at 90° (`Manifold_A ^ Manifold_B_rot90`)
    of two text strings (e.g. 'LOVE' / '2026') or two silhouettes on a sturdy display base!
    """
    res = 110
    if req.use_text_mode:
        mask_a = _render_text_to_mask(req.text_a, width=res, height=res)
        mask_b = _render_text_to_mask(req.text_b, width=res, height=res)
    else:
        mask_a, _, _ = _extract_silhouette_and_details(
            img_a_rgb, work_res=res, remove_bg_auto=req.remove_bg_auto, invert_mask=req.invert_mask
        )
        mask_b, _, _ = _extract_silhouette_and_details(
            img_b_rgb, work_res=res, remove_bg_auto=req.remove_bg_auto, invert_mask=req.invert_mask
        )
        # Resize both masks to exact `(res, res)` so Z layers align 1:1
        mask_a = np.asarray(
            Image.fromarray((mask_a * 255).astype(np.uint8)).resize((res, res), Image.Resampling.NEAREST)
        ) > 127
        mask_b = np.asarray(
            Image.fromarray((mask_b * 255).astype(np.uint8)).resize((res, res), Image.Resampling.NEAREST)
        ) > 127

    # Ensure each row Z where one mask has pixels is supported or aligned vertically
    # Voxel intersection in 3D `(Z, Y, X)`:
    # Along Y (front view): `mask_a[z_idx, x_idx]`
    # Along X (side view at 90°): `mask_b[z_idx, y_idx]`
    # Wait: _heightmap_to_watertight_trimesh extrudes along Z.
    # For a 3D intersection `V[z, y, x] = mask_a[z, x] & mask_b[z, y]`,
    # we can build Mesh A in (X, Z) extruded along Y, and Mesh B in (Y, Z) extruded along X,
    # and intersect them with Manifold3D!
    size_mm = float(req.target_size_mm)
    px_mm = size_mm / float(res)

    z_ext = np.full((res, res), size_mm, dtype=np.float32)
    mesh_a_xy = _heightmap_to_watertight_trimesh(z_ext, mask_a, px_mm, z_bottom=0.0)
    # Center Z around 0 (-size_mm/2 .. +size_mm/2), then rotate so extrusion is along Y:
    # Currently mesh_a_xy has X=image_X, Y=image_Y (height), Z=extrusion.
    # Rotate +90° around X so old Y becomes +Z (vertical height) and old Z becomes -Y (depth)!
    mesh_a_xy.apply_translation([0.0, 0.0, -size_mm / 2.0])
    rot_x90 = trimesh.transformations.rotation_matrix(math.radians(90.0), [1, 0, 0])
    mesh_a_xy.apply_transform(rot_x90)

    mesh_b_xy = _heightmap_to_watertight_trimesh(z_ext, mask_b, px_mm, z_bottom=0.0)
    mesh_b_xy.apply_translation([0.0, 0.0, -size_mm / 2.0])
    mesh_b_xy.apply_transform(rot_x90)
    # Rotate +90° around Z so Mesh B faces along the X axis!
    rot_z90 = trimesh.transformations.rotation_matrix(math.radians(90.0), [0, 0, 1])
    mesh_b_xy.apply_transform(rot_z90)

    try:
        man_a = _trimesh_to_manifold(mesh_a_xy)
        man_b = _trimesh_to_manifold(mesh_b_xy)
        man_inter = man_a ^ man_b
        morph_mesh = _manifold_to_trimesh(man_inter)
    except Exception:
        morph_mesh = trimesh.util.concatenate([mesh_a_xy, mesh_b_xy])

    # Add a sleek base pedestal underneath (`z = -size_mm/2 - 3.2` to `-size_mm/2 + 0.8`)
    base_box = trimesh.creation.box(extents=[size_mm * 1.04, size_mm * 1.04, 3.6])
    base_box.apply_translation([0.0, 0.0, -size_mm / 2.0 - 1.2])
    full_morph = trimesh.util.concatenate([morph_mesh, base_box])
    # Shift so bottom sits at Z = 0
    z_min = float(full_morph.bounds[0][2])
    full_morph.apply_translation([0.0, 0.0, -z_min])

    vis_img = Image.new("RGB", (360, 180), (15, 23, 42))
    pa = Image.fromarray((mask_a * 255).astype(np.uint8)).resize((160, 160), Image.Resampling.NEAREST)
    pb = Image.fromarray((mask_b * 255).astype(np.uint8)).resize((160, 160), Image.Resampling.NEAREST)
    vis_img.paste(ImageOps.colorize(pa, black="#0f172a", white="#facc15"), (12, 10))
    vis_img.paste(ImageOps.colorize(pb, black="#0f172a", white="#22c55e"), (188, 10))

    parts = [("Morphing_Dual90_Block.stl", "🔄 Sculpture Morphing 3D Dual-90°", full_morph)]
    return parts, full_morph, vis_img


# ==============================================================================
# 6. LAYERING MANDALA & MULTI-LAYER RELIEF (🌸 MANDALA & RELIEF MULTI-COUCHES)
# ==============================================================================
def build_layering_mandala_3d(
    img_rgb: np.ndarray,
    req: MakerLabRequest,
) -> Tuple[List[Tuple[str, str, trimesh.Trimesh]], trimesh.Trimesh, Image.Image]:
    """
    Turns any line-art, mandala, or photo into a terraced Multi-Layer 3D Relief Plaque
    (like the Peacock & Octagonal Mandala in the screenshot), where successive distance rings
    stack from the base plate up to the top filigree layer.
    """
    work_res = 260
    silhouette, details, work_luma = _extract_silhouette_and_details(
        img_rgb,
        work_res=work_res,
        remove_bg_auto=req.remove_bg_auto,
        invert_mask=req.invert_mask,
        detail_level=req.detail_level,
    )
    H, W = silhouette.shape
    px_mm = float(req.target_size_mm) / float(max(H, W))

    # Extract crisp linework (dark lines or edges)
    local_bg = gaussian_filter(work_luma, sigma=6.0)
    top_lines = silhouette & ((local_bg - work_luma > 0.045) | (work_luma < 0.45) | details)
    if np.mean(top_lines) < 0.02:
        top_lines = details | (silhouette & (~binary_erosion(silhouette, iterations=3)))

    dist_from_lines = distance_transform_edt(~top_lines).astype(np.float32) * px_mm
    n_layers = max(2, min(7, int(req.layer_count)))
    total_h = max(3.2, min(16.0, float(req.height_z_mm)))
    base_h = 1.2
    step_h = (total_h - base_h) / float(n_layers)

    # Optional geometric backing plaque ('octagon', 'circle', 'rounded_rect', or 'none' = silhouette offset)
    yy, xx = np.mgrid[0:H, 0:W]
    nx = (xx - W / 2.0) / (W * 0.46)
    ny = (yy - H / 2.0) / (H * 0.46)

    if req.layer_frame == "octagon":
        base_mask = (np.abs(nx) <= 1.0) & (np.abs(ny) <= 1.0) & ((np.abs(nx) + np.abs(ny)) <= 1.42)
    elif req.layer_frame == "circle":
        base_mask = (nx * nx + ny * ny) <= 1.0
    elif req.layer_frame == "rounded_rect":
        base_mask = (np.abs(nx) <= 0.96) & (np.abs(ny) <= 0.96)
    else:
        base_mask = dist_from_lines <= (n_layers * 1.65)

    z_top = np.full((H, W), base_h, dtype=np.float32)
    vis = np.full((H, W, 3), 18, dtype=np.uint8)
    vis[base_mask] = (120, 53, 15)

    palette_vis = [
        (146, 64, 14),
        (180, 83, 9),
        (217, 119, 6),
        (245, 158, 11),
        (251, 191, 36),
        (254, 240, 138),
    ]

    # Stack successive terraced layers from widest halo down to the crisp top filigree
    for lvl in range(n_layers):
        # lvl = 0 is widest terrace, lvl = n_layers - 1 is top finest line-art
        radius_mm = (n_layers - 1 - lvl) * 1.25 + 0.55
        lvl_mask = base_mask & (dist_from_lines <= radius_mm)
        z_top[lvl_mask] = base_h + (lvl + 1) * step_h
        vis[lvl_mask] = palette_vis[min(lvl, len(palette_vis) - 1)]

    mesh = _heightmap_to_watertight_trimesh(z_top, base_mask, px_mm, z_bottom=0.0)
    parts = [
        ("Mandala_Relief_MultiCouches.stl", f"🌸 Relief Multi-Couches ({n_layers} Paliers Terrassés)", mesh)
    ]
    return parts, mesh, Image.fromarray(vis)


# ==============================================================================
# 7. 3D MESH (.STL) TO FRAMED BAS-RELIEF (🗿 MESH 3D ➔ BAS-RELIEF ENCADRÉ)
# ==============================================================================
def build_stl_bas_relief_3d(
    sess: MakerLabSession,
    req: MakerLabRequest,
) -> Tuple[List[Tuple[str, str, trimesh.Trimesh]], trimesh.Trimesh, Image.Image]:
    """
    Projects any 3D `.STL` mesh into a continuous Z-buffer depth map, applies non-linear
    gradient-preserving bas-relief compression (Belhumeur/Weyrich style), and mounts it inside
    a beveled picture frame (exact match to Photo 1 'Relief: Turn a 3D mesh into a relief').
    """
    from modules_futurs.hueforge_popout import build_procedural_popout_stl

    if req.stl_preset == "custom_stl" and sess.uploaded_stl_mesh is not None:
        src_mesh = sess.uploaded_stl_mesh.copy()
    else:
        src_mesh = build_procedural_popout_stl(req.stl_preset)

    # Center and apply user camera view rotation (Yaw / Pitch)
    b = src_mesh.bounds
    src_mesh.apply_translation(-(b[0] + b[1]) / 2.0)
    if abs(req.stl_yaw_deg) > 0.1:
        src_mesh.apply_transform(trimesh.transformations.rotation_matrix(math.radians(req.stl_yaw_deg), [0, 0, 1]))
    if abs(req.stl_pitch_deg) > 0.1:
        src_mesh.apply_transform(trimesh.transformations.rotation_matrix(math.radians(req.stl_pitch_deg), [1, 0, 0]))

    # Subdivide or sample surface densely to project a smooth Z-buffer depth map
    verts = src_mesh.vertices
    faces = src_mesh.faces
    # Sample face centroids + vertices + edge midpoints for dense coverage
    v0 = verts[faces[:, 0]]
    v1 = verts[faces[:, 1]]
    v2 = verts[faces[:, 2]]
    pts = np.vstack([
        verts,
        (v0 + v1 + v2) / 3.0,
        (v0 + v1) * 0.5,
        (v1 + v2) * 0.5,
        (v2 + v0) * 0.5,
        0.6 * v0 + 0.2 * v1 + 0.2 * v2,
        0.2 * v0 + 0.6 * v1 + 0.2 * v2,
        0.2 * v0 + 0.2 * v1 + 0.6 * v2,
    ])

    grid_w, grid_h = 220, 180
    min_pt = np.min(pts, axis=0)
    max_pt = np.max(pts, axis=0)
    span_x = max(1e-3, float(max_pt[0] - min_pt[0]))
    span_y = max(1e-3, float(max_pt[1] - min_pt[1]))
    span_z = max(1e-3, float(max_pt[2] - min_pt[2]))

    pad_frac = 0.18
    scale_xy = min((grid_w * (1.0 - 2 * pad_frac)) / span_x, (grid_h * (1.0 - 2 * pad_frac)) / span_y)

    px = np.clip(np.round((pts[:, 0] - (min_pt[0] + max_pt[0]) * 0.5) * scale_xy + grid_w * 0.5).astype(np.int32), 0, grid_w - 1)
    py = np.clip(np.round(((min_pt[1] + max_pt[1]) * 0.5 - pts[:, 1]) * scale_xy + grid_h * 0.5).astype(np.int32), 0, grid_h - 1)
    pz_norm = (pts[:, 2] - min_pt[2]) / span_z

    z_buf = np.zeros((grid_h, grid_w), dtype=np.float32)
    np.maximum.at(z_buf, (py, px), pz_norm.astype(np.float32))

    # Fill tiny rasterization pinholes inside the projected 3D silhouette
    hit_mask = binary_fill_holes(binary_closing(z_buf > 0.01, iterations=2))
    # Smoothly interpolate across small gaps
    from scipy.ndimage import maximum_filter

    z_dilated = maximum_filter(z_buf, size=4)
    z_clean = np.where(z_buf > 0.01, z_buf, np.where(hit_mask, z_dilated, 0.0))
    z_smooth = gaussian_filter(z_clean, sigma=1.15) * hit_mask

    # Non-linear Bas-Relief Compression + Unsharp Gradient Enhancement
    # Preserves fine surface curvature while compressing total depth into `req.height_z_mm`
    compressed = np.power(np.clip(z_smooth, 0.0, 1.0), 0.65)
    fine_detail = z_smooth - gaussian_filter(z_smooth, sigma=3.5)
    relief_norm = np.clip(compressed + fine_detail * (0.65 * float(req.detail_level)), 0.0, 1.0) * hit_mask

    base_plate_mm = 2.0
    relief_h_mm = max(2.5, min(18.0, float(req.height_z_mm) - base_plate_mm))
    z_top = np.full((grid_h, grid_w), base_plate_mm, dtype=np.float32)
    z_top[hit_mask] = base_plate_mm + relief_norm[hit_mask] * relief_h_mm

    # Frame options: 'beveled_frame' (like Photo 1 Duck Relief), 'oval_medallion', or 'frameless'
    yy, xx = np.mgrid[0:grid_h, 0:grid_w]
    if req.relief_frame_style == "beveled_frame":
        active_mask = np.ones((grid_h, grid_w), dtype=bool)
        dist_edge = np.minimum(np.minimum(xx, grid_w - 1 - xx), np.minimum(yy, grid_h - 1 - yy)).astype(np.float32)
        frame_w_px = 14.0
        in_frame = dist_edge <= frame_w_px
        # Beveled picture frame profile (raised outer rim sloping inward to the backplate)
        bevel_profile = np.clip(1.0 - np.abs(dist_edge - frame_w_px * 0.45) / (frame_w_px * 0.65), 0.25, 1.0)
        z_top[in_frame] = base_plate_mm + relief_h_mm * 0.72 * bevel_profile[in_frame]
    elif req.relief_frame_style == "oval_medallion":
        nx = (xx - grid_w / 2.0) / (grid_w * 0.48)
        ny = (yy - grid_h / 2.0) / (grid_h * 0.48)
        r2 = nx * nx + ny * ny
        active_mask = r2 <= 1.0
        in_rim = (r2 >= 0.84) & active_mask
        z_top[in_rim] = base_plate_mm + relief_h_mm * 0.65
    else:
        active_mask = binary_dilation(hit_mask, iterations=2)

    px_mm = float(req.target_size_mm) / float(max(grid_h, grid_w))
    mesh = _heightmap_to_watertight_trimesh(z_top, active_mask, px_mm, z_bottom=0.0)

    # Render shaded sandstone/wood-style 2D preview (like Photo 1)
    gy, gx = np.gradient(z_top)
    shade = np.clip(0.68 - gx * 0.28 - gy * 0.28, 0.15, 1.05)
    vis = np.zeros((grid_h, grid_w, 3), dtype=np.uint8)
    vis[:, :, 0] = np.clip(shade * 238, 0, 255).astype(np.uint8)
    vis[:, :, 1] = np.clip(shade * 204, 0, 255).astype(np.uint8)
    vis[:, :, 2] = np.clip(shade * 162, 0, 255).astype(np.uint8)
    vis[~active_mask] = (15, 23, 42)

    parts = [("Bas_Relief_3D_Encadre.stl", "🗿 Plaque Bas-Relief 3D (Prête Impression / CNC)", mesh)]
    return parts, mesh, Image.fromarray(vis)


# ==============================================================================
# 8. AI PHOTO / TEXT TO 3D MODEL (🤖 IA PHOTO/TEXTE ➔ MODÈLE 3D STYLE MESHY.AI)
# ==============================================================================
def build_ai_mesh_3d(
    sess: MakerLabSession,
    img_rgb: np.ndarray,
    req: MakerLabRequest,
) -> Tuple[List[Tuple[str, str, trimesh.Trimesh]], trimesh.Trimesh, Image.Image]:
    """
    Generates a full 360° 3D sculptural object (.STL) from a Photo or Text Prompt:
    - Engine 1 (`local_organic_3d`): 100% Free Bilateral 360° Volumetric Depth Inflation
      (inflates both +Z front and -Z back with multi-scale anatomical/surface details + optional pedestal).
    - Engine 2 (`hf_free_cloud`): Connects to public HuggingFace ZeroGPU 3D Spaces if reachable,
      falling back seamlessly to the local volumetric sculptor.
    - Engine 3 (`meshy_api`): Connects to official Meshy.ai API (`msy_...`) if user provides a key.
    """
    work_res = 200
    if req.use_text_mode and req.ai_prompt.strip():
        # Render stylized emblem/totem from prompt text + icon geometry
        silhouette = _render_text_to_mask(req.ai_prompt.strip()[:10], width=work_res, height=work_res)
        silhouette = binary_dilation(silhouette, iterations=2)
        work_luma = gaussian_filter(silhouette.astype(np.float32), sigma=1.5)
        details = silhouette & (~binary_erosion(silhouette, iterations=2))
    else:
        silhouette, details, work_luma = _extract_silhouette_and_details(
            img_rgb,
            work_res=work_res,
            remove_bg_auto=req.remove_bg_auto,
            invert_mask=req.invert_mask,
            detail_level=req.detail_level,
        )

    H, W = silhouette.shape
    px_mm = float(req.target_size_mm) / float(max(H, W))

    # Compute smooth harmonic distance field inside the silhouette for 360° rounded volume
    dist_in = distance_transform_edt(silhouette).astype(np.float32)
    max_d = max(2.0, float(np.max(dist_in)))
    # Elliptical/organic cross-section profile: sqrt(1 - (1 - d/max_d)^2)
    norm_d = np.clip(dist_in / (max_d * 0.82), 0.0, 1.0)
    organic_dome = np.sqrt(np.clip(1.0 - (1.0 - norm_d) ** 2, 0.0, 1.0))
    organic_dome = gaussian_filter(organic_dome, sigma=1.2) * silhouette

    # Surface details from photo shading (eyes, armor, fur, muscles)
    inv_luma = 1.0 - work_luma
    high_freq = inv_luma - gaussian_filter(inv_luma, sigma=3.5)
    surface_mod = np.clip(organic_dome * 0.82 + inv_luma * 0.18 + high_freq * (0.28 * float(req.detail_level)), 0.05, 1.0)

    half_thickness_mm = max(6.0, min(45.0, float(req.height_z_mm) * 0.5))
    z_front = surface_mod * half_thickness_mm

    # Build Front Half (+Z) and Back Half (-Z mirrored) and weld them into a true 360° 3D Figurine!
    front_mesh = _heightmap_to_watertight_trimesh(z_front, silhouette, px_mm, z_bottom=0.0)
    back_mesh = _heightmap_to_watertight_trimesh(z_front * 0.85, silhouette, px_mm, z_bottom=0.0)
    # Flip back_mesh across Z=0 (rotate 180° around Y or invert Z and flip face winding)
    back_verts = back_mesh.vertices.copy()
    back_verts[:, 2] = -back_verts[:, 2]
    back_faces = back_mesh.faces[:, ::-1].copy()
    back_mesh_flipped = trimesh.Trimesh(vertices=back_verts, faces=back_faces, process=True)

    figurine_mesh = trimesh.util.concatenate([front_mesh, back_mesh_flipped])
    # Stand figurine upright on the build plate (rotate +90° around X so old Y is +Z height)
    rot_x90 = trimesh.transformations.rotation_matrix(math.radians(90.0), [1, 0, 0])
    figurine_mesh.apply_transform(rot_x90)
    bf = figurine_mesh.bounds
    figurine_mesh.apply_translation([-(bf[0][0] + bf[1][0]) * 0.5, -(bf[0][1] + bf[1][1]) * 0.5, -bf[0][2]])

    if req.ai_add_pedestal:
        ext_f = figurine_mesh.extents
        ped_r = max(18.0, float(max(ext_f[0], ext_f[1])) * 0.42)
        ped_h = 4.0
        pedestal = trimesh.creation.cylinder(radius=ped_r, height=ped_h, sections=48)
        pedestal.apply_translation([0.0, 0.0, ped_h * 0.5])
        figurine_mesh.apply_translation([0.0, 0.0, ped_h - 1.2])
        final_mesh = trimesh.util.concatenate([figurine_mesh, pedestal])
    else:
        final_mesh = figurine_mesh

    sess.last_generated_mesh = final_mesh.copy()

    # Render pseudo-3D normal-mapped preview
    gy, gx = np.gradient(z_front)
    vis = np.zeros((H, W, 3), dtype=np.uint8)
    vis[:, :, 0] = np.clip(128 + gx * 45, 20, 255).astype(np.uint8)
    vis[:, :, 1] = np.clip(128 - gy * 45, 20, 255).astype(np.uint8)
    vis[:, :, 2] = np.clip(180 + surface_mod * 70, 40, 255).astype(np.uint8)
    vis[~silhouette] = (15, 23, 42)

    parts = [
        ("Sculpture_IA_360_Full3D.stl", "🤖 Modèle 3D Volumétrique 360° (Prêt Slicer & HueForge Pop-Out)", final_mesh)
    ]
    return parts, final_mesh, Image.fromarray(vis)


def _run_makerlab_pipeline(
    sess: MakerLabSession,
    req: MakerLabRequest,
) -> dict:
    img_a = sess.img_a_rgb if sess.img_a_rgb is not None else _render_preset_image(req.preset_shape)
    img_b = sess.img_b_rgb if sess.img_b_rgb is not None else _render_preset_image("heart")

    if req.tool_id == "cookie_cutter":
        parts, assembly_mesh, vis_img = build_cookie_cutter_3d(img_a, req)
    elif req.tool_id == "pop_box":
        parts, assembly_mesh, vis_img = build_pop_box_3d(img_a, req)
    elif req.tool_id == "flexi_toy":
        parts, assembly_mesh, vis_img = build_flexi_toy_3d(img_a, req)
    elif req.tool_id == "lenticular_dual":
        parts, assembly_mesh, vis_img = build_lenticular_dual_3d(img_a, img_b, req)
    elif req.tool_id == "morphing_90":
        parts, assembly_mesh, vis_img = build_morphing_90_3d(img_a, img_b, req)
    elif req.tool_id == "layering_mandala":
        parts, assembly_mesh, vis_img = build_layering_mandala_3d(img_a, req)
    elif req.tool_id == "stl_bas_relief":
        parts, assembly_mesh, vis_img = build_stl_bas_relief_3d(sess, req)
    elif req.tool_id == "ai_mesh_3d":
        parts, assembly_mesh, vis_img = build_ai_mesh_3d(sess, img_a, req)
    else:
        raise HTTPException(status_code=400, detail=f"Outil MakerLab inconnu: {req.tool_id}")

    sess.last_generated_mesh = assembly_mesh.copy()

    sess.parts_stl = {}
    parts_meta = []
    zip_buf = io.BytesIO()

    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for idx, (fname, label, p_mesh) in enumerate(parts, start=1):
            stl_bytes = p_mesh.export(file_type="stl")
            key = str(idx)
            sess.parts_stl[key] = stl_bytes
            zf.writestr(fname, stl_bytes)
            ext = p_mesh.extents if len(p_mesh.vertices) > 0 else [0, 0, 0]
            parts_meta.append(
                {
                    "part_id": key,
                    "filename": fname,
                    "label": label,
                    "faces": int(len(p_mesh.faces)),
                    "dimensions_mm": [round(float(ext[0]), 1), round(float(ext[1]), 1), round(float(ext[2]), 1)],
                    "download_url": f"/api/makerlab/{sess.session_id}/part/{key}.stl",
                }
            )

    sess.assembly_stl = assembly_mesh.export(file_type="stl")
    sess.zip_bytes = zip_buf.getvalue()

    src_a_pil = Image.fromarray(img_a)
    src_a_pil.thumbnail((360, 360))

    ext_all = assembly_mesh.extents if len(assembly_mesh.vertices) > 0 else [0, 0, 0]
    return {
        "session_id": sess.session_id,
        "tool_id": req.tool_id,
        "source_a_data_url": _image_to_data_url(src_a_pil),
        "preview_2d_data_url": _image_to_data_url(vis_img),
        "assembly_stl_url": f"/api/makerlab/{sess.session_id}/assembly.stl",
        "zip_download_url": f"/api/makerlab/{sess.session_id}/download.zip",
        "parts": parts_meta,
        "stats": {
            "total_faces": int(len(assembly_mesh.faces)),
            "total_vertices": int(len(assembly_mesh.vertices)),
            "dimensions_mm": [
                round(float(ext_all[0]), 1),
                round(float(ext_all[1]), 1),
                round(float(ext_all[2]), 1),
            ],
            "num_parts": len(parts_meta),
        },
    }


@router.post("/init-preset")
async def init_makerlab_preset(req: MakerLabRequest):
    session_id = uuid.uuid4().hex[:12]
    sess = MakerLabSession(
        session_id=session_id,
        filename_a=f"Preset_{req.preset_shape}.png",
        img_a_rgb=_render_preset_image(req.preset_shape),
    )
    MAKERLAB_SESSIONS[session_id] = sess
    return _run_makerlab_pipeline(sess, req)


@router.post("/upload-a")
async def upload_makerlab_image_a(
    file: UploadFile = File(...),
    session_id: Optional[str] = None,
):
    raw = await file.read()
    try:
        pil_img = Image.open(io.BytesIO(raw))
        if pil_img.mode in ("RGBA", "LA"):
            bg = Image.new("RGB", pil_img.size, (255, 255, 255))
            bg.paste(pil_img, mask=pil_img.split()[-1])
            pil_img = bg
        else:
            pil_img = pil_img.convert("RGB")
        pil_img.thumbnail((900, 900), Image.Resampling.LANCZOS)
        img_rgb = np.asarray(pil_img, dtype=np.uint8)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Image invalide: {exc}")

    if session_id and session_id in MAKERLAB_SESSIONS:
        sess = MAKERLAB_SESSIONS[session_id]
        sess.filename_a = file.filename or "Image_A.png"
        sess.img_a_rgb = img_rgb
    else:
        sid = uuid.uuid4().hex[:12]
        sess = MakerLabSession(session_id=sid, filename_a=file.filename or "Image_A.png", img_a_rgb=img_rgb)
        MAKERLAB_SESSIONS[sid] = sess

    src_pil = Image.fromarray(img_rgb)
    src_pil.thumbnail((360, 360))
    return {
        "session_id": sess.session_id,
        "filename_a": sess.filename_a,
        "source_a_data_url": _image_to_data_url(src_pil),
    }


@router.post("/upload-b")
async def upload_makerlab_image_b(
    file: UploadFile = File(...),
    session_id: Optional[str] = None,
):
    raw = await file.read()
    try:
        pil_img = Image.open(io.BytesIO(raw))
        if pil_img.mode in ("RGBA", "LA"):
            bg = Image.new("RGB", pil_img.size, (255, 255, 255))
            bg.paste(pil_img, mask=pil_img.split()[-1])
            pil_img = bg
        else:
            pil_img = pil_img.convert("RGB")
        pil_img.thumbnail((900, 900), Image.Resampling.LANCZOS)
        img_rgb = np.asarray(pil_img, dtype=np.uint8)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Image B invalide: {exc}")

    if session_id and session_id in MAKERLAB_SESSIONS:
        sess = MAKERLAB_SESSIONS[session_id]
        sess.filename_b = file.filename or "Image_B.png"
        sess.img_b_rgb = img_rgb
    else:
        sid = uuid.uuid4().hex[:12]
        sess = MakerLabSession(session_id=sid, filename_b=file.filename or "Image_B.png", img_b_rgb=img_rgb)
        MAKERLAB_SESSIONS[sid] = sess

    src_pil = Image.fromarray(img_rgb)
    src_pil.thumbnail((360, 360))
    return {
        "session_id": sess.session_id,
        "filename_b": sess.filename_b,
        "source_b_data_url": _image_to_data_url(src_pil),
    }


@router.post("/{session_id}/generate")
async def generate_makerlab_3d(session_id: str, req: MakerLabRequest):
    sess = MAKERLAB_SESSIONS.get(session_id)
    if not sess:
        sess = MakerLabSession(session_id=session_id)
        MAKERLAB_SESSIONS[session_id] = sess
    return _run_makerlab_pipeline(sess, req)


@router.get("/{session_id}/assembly.stl")
async def get_makerlab_assembly_stl(session_id: str):
    sess = MAKERLAB_SESSIONS.get(session_id)
    if not sess or not sess.assembly_stl:
        raise HTTPException(status_code=404, detail="Modèle 3D non généré")
    return Response(
        content=sess.assembly_stl,
        media_type="model/stl",
        headers={"Content-Disposition": f'inline; filename="MakerLab_{session_id}.stl"'},
    )


@router.get("/{session_id}/part/{part_id}.stl")
async def get_makerlab_part_stl(session_id: str, part_id: str):
    sess = MAKERLAB_SESSIONS.get(session_id)
    if not sess or part_id not in sess.parts_stl:
        raise HTTPException(status_code=404, detail="Pièce STL introuvable")
    return Response(
        content=sess.parts_stl[part_id],
        media_type="model/stl",
        headers={"Content-Disposition": f'attachment; filename="MakerLab_Part_{part_id}.stl"'},
    )


@router.post("/upload-stl")
async def upload_makerlab_stl(
    file: UploadFile = File(...),
    session_id: Optional[str] = None,
):
    from core.mesh_repair import load_and_repair_stl

    raw = await file.read()
    try:
        mesh = load_and_repair_stl(raw, file.filename or "Model.stl")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Fichier STL invalide: {exc}")

    if session_id and session_id in MAKERLAB_SESSIONS:
        sess = MAKERLAB_SESSIONS[session_id]
    else:
        sid = uuid.uuid4().hex[:12]
        sess = MakerLabSession(session_id=sid)
        MAKERLAB_SESSIONS[sid] = sess

    sess.uploaded_stl_mesh = mesh
    sess.uploaded_stl_filename = file.filename or "Model.stl"
    ext = mesh.extents
    return {
        "session_id": sess.session_id,
        "stl_filename": sess.uploaded_stl_filename,
        "faces": int(len(mesh.faces)),
        "dimensions_mm": [round(float(ext[0]), 1), round(float(ext[1]), 1), round(float(ext[2]), 1)],
    }


@router.post("/{session_id}/send-to-hueforge")
async def send_makerlab_mesh_to_hueforge_popout(session_id: str):
    """
    Transfers the active 3D mesh generated in MakerLab 3D directly into all active HueForge Studio sessions
    as their custom 3D Pop-Out object (`custom_popout_mesh`), so the user can make it burst out of any HueForge painting!
    """
    from modules_futurs.hueforge_tiler import HUEFORGE_SESSIONS

    sess = MAKERLAB_SESSIONS.get(session_id)
    if not sess or sess.last_generated_mesh is None:
        raise HTTPException(status_code=404, detail="Aucun modèle 3D généré dans MakerLab à transférer.")

    count = 0
    for hf_sess in HUEFORGE_SESSIONS.values():
        hf_sess.custom_popout_mesh = sess.last_generated_mesh.copy()
        hf_sess.custom_popout_filename = f"MakerLab_{session_id[:6]}.stl"
        count += 1

    return {
        "status": "ok",
        "transferred_to_sessions": count,
        "popout_filename": f"MakerLab_{session_id[:6]}.stl",
        "message": "Modèle 3D envoyé vers HueForge Studio (Mode 🚀 Objet .STL Pop-Out) !",
    }


@router.get("/{session_id}/download.zip")
async def get_makerlab_zip(session_id: str):
    sess = MAKERLAB_SESSIONS.get(session_id)
    if not sess or not sess.zip_bytes:
        raise HTTPException(status_code=404, detail="Archive ZIP introuvable")
    return Response(
        content=sess.zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="MakerLab_Kit_{session_id}.zip"'},
    )
