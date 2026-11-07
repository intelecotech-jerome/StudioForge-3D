"""
StudioForge 3D — Module WirePress 3D (Structures Filaires 3D & Transfert Textile à Chaud)
Transforms any photo, portrait, pet, manga, or logo into a 100% connected 3D wire structure
ready to be 3D-printed (in PLA, PLA+, PETG, or TPU) and heat-pressed onto a T-shirt, Hoodie, or Tote Bag.
"""
from __future__ import annotations

import base64
import io
import math
import uuid
import zipfile
from dataclasses import dataclass
from typing import Dict, List, Literal, Optional, Tuple

import numpy as np
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from PIL import Image, ImageDraw, ImageOps
from pydantic import BaseModel, Field
from scipy.ndimage import (
    binary_closing,
    binary_dilation,
    binary_erosion,
    binary_fill_holes,
    distance_transform_edt,
    gaussian_filter,
    label as nd_label,
    maximum_filter,
    sobel,
)

router = APIRouter(prefix="/api/wirepress", tags=["WirePress 3D - Textile Wire Structure"])

WireStyle = Literal["organic_portrait", "manga_lineart", "streetwear_stencil", "cell_halftone"]
FrameMode = Literal[
    "rounded_rect",
    "hexagon",
    "circle",
    "shield",
    "heart",
    "silhouette_offset",
    "frameless",
]


@dataclass
class WirePressSession:
    session_id: str
    filename: str
    img_rgb: np.ndarray  # (H, W, 3) uint8
    last_stl_bytes: Optional[bytes] = None
    last_3mf_bytes: Optional[bytes] = None
    last_zip_bytes: Optional[bytes] = None
    last_wire_rgba_b64: Optional[str] = None


WIREPRESS_SESSIONS: Dict[str, WirePressSession] = {}


class WirePressPreviewRequest(BaseModel):
    wire_style: WireStyle = "organic_portrait"
    frame_mode: FrameMode = "rounded_rect"
    detail_level: float = Field(1.0, ge=0.2, le=2.0)
    line_width_mm: float = Field(1.6, ge=0.8, le=5.0)
    thickness_z_mm: float = Field(0.60, ge=0.24, le=2.40)
    target_width_mm: float = Field(160.0, ge=40.0, le=300.0)
    auto_bridges: bool = True
    remove_bg_auto: bool = True
    mirror_horizontal: bool = False
    invert_image: bool = False
    zoom: float = Field(1.0, ge=0.35, le=3.5)
    offset_x_pct: float = Field(0.0, ge=-100.0, le=100.0)
    offset_y_pct: float = Field(0.0, ge=-100.0, le=100.0)
    wire_hex_color: str = "#22c55e"


def _hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
    h = (hex_str or "#22c55e").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return (34, 197, 94)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return (34, 197, 94)


def _crop_and_frame_image(
    img_rgb: np.ndarray,
    work_w: int,
    work_h: int,
    zoom: float = 1.0,
    offset_x_pct: float = 0.0,
    offset_y_pct: float = 0.0,
    mirror_horizontal: bool = False,
) -> np.ndarray:
    src_h, src_w = img_rgb.shape[:2]
    src_aspect = src_w / max(1.0, float(src_h))
    target_aspect = work_w / max(1.0, float(work_h))

    if src_aspect > target_aspect:
        base_w = src_h * target_aspect
        base_h = float(src_h)
    else:
        base_w = float(src_w)
        base_h = src_w / target_aspect

    z = max(0.35, min(3.5, float(zoom)))
    crop_w = base_w / z
    crop_h = base_h / z

    pan_span_x = max(src_w * 0.60, abs(src_w - crop_w) * 0.60)
    pan_span_y = max(src_h * 0.60, abs(src_h - crop_h) * 0.60)

    cx = src_w / 2.0 - (offset_x_pct / 100.0) * pan_span_x
    cy = src_h / 2.0 - (offset_y_pct / 100.0) * pan_span_y

    x0 = int(round(cx - crop_w / 2.0))
    y0 = int(round(cy - crop_h / 2.0))
    x1 = int(round(cx + crop_w / 2.0))
    y1 = int(round(cy + crop_h / 2.0))

    # Sample border color for out-of-bounds padding
    border_pixels = np.concatenate(
        [img_rgb[0, :], img_rgb[-1, :], img_rgb[:, 0], img_rgb[:, -1]], axis=0
    )
    bg_color = tuple(int(v) for v in np.median(border_pixels, axis=0))

    pil_src = Image.fromarray(img_rgb)
    canvas = Image.new("RGB", (max(1, x1 - x0), max(1, y1 - y0)), bg_color)
    paste_x = max(0, -x0)
    paste_y = max(0, -y0)
    sub_x0 = max(0, x0)
    sub_y0 = max(0, y0)
    sub_x1 = min(src_w, x1)
    sub_y1 = min(src_h, y1)
    if sub_x1 > sub_x0 and sub_y1 > sub_y0:
        cropped_part = pil_src.crop((sub_x0, sub_y0, sub_x1, sub_y1))
        canvas.paste(cropped_part, (paste_x, paste_y))

    resized = canvas.resize((work_w, work_h), Image.Resampling.LANCZOS)
    if mirror_horizontal:
        resized = ImageOps.mirror(resized)
    return np.asarray(resized, dtype=np.uint8)


def _build_frame_masks(
    work_w: int,
    work_h: int,
    frame_mode: FrameMode,
    line_width_px: int,
    subject_mask: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Returns `(inside_canvas_mask, frame_ring_mask)` as boolean arrays of shape `(work_h, work_w)`.
    """
    lw = max(4, int(round(line_width_px * 1.15)))
    margin = max(lw + 4, int(min(work_w, work_h) * 0.032))

    if frame_mode == "frameless":
        inside = np.ones((work_h, work_w), dtype=bool)
        ring = np.zeros((work_h, work_w), dtype=bool)
        return inside, ring

    if frame_mode == "silhouette_offset":
        dil_rad = max(lw * 2, int(min(work_w, work_h) * 0.03))
        outer = binary_dilation(subject_mask, iterations=dil_rad)
        outer = binary_fill_holes(outer)
        inner = binary_erosion(outer, iterations=lw, border_value=0)
        ring = outer & (~inner)
        return outer, ring

    img_outer = Image.new("L", (work_w, work_h), 0)
    draw_outer = ImageDraw.Draw(img_outer)
    x0, y0, x1, y1 = margin, margin, work_w - 1 - margin, work_h - 1 - margin

    if frame_mode == "rounded_rect":
        radius = int(min(work_w, work_h) * 0.13)
        draw_outer.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=255)
    elif frame_mode == "circle":
        draw_outer.ellipse([x0, y0, x1, y1], fill=255)
    elif frame_mode == "hexagon":
        cx, cy = work_w / 2.0, work_h / 2.0
        rx, ry = (x1 - x0) / 2.0, (y1 - y0) / 2.0
        pts = [
            (
                cx + rx * math.cos(math.radians(60 * i - 30)),
                cy + ry * math.sin(math.radians(60 * i - 30)),
            )
            for i in range(6)
        ]
        draw_outer.polygon(pts, fill=255)
    elif frame_mode == "shield":
        cx = work_w / 2.0
        pts = [
            (x0, y0 + (y1 - y0) * 0.06),
            (cx, y0),
            (x1, y0 + (y1 - y0) * 0.06),
            (x1, y0 + (y1 - y0) * 0.56),
            (cx, y1),
            (x0, y0 + (y1 - y0) * 0.56),
        ]
        draw_outer.polygon(pts, fill=255)
    elif frame_mode == "heart":
        cx = work_w / 2.0
        w_span = x1 - x0
        h_span = y1 - y0
        pts = []
        for t_deg in range(0, 360, 4):
            t = math.radians(t_deg)
            hx = 16 * (math.sin(t) ** 3)
            hy = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
            px = cx + (hx / 17.0) * (w_span / 2.0)
            py = y0 + ((hy + 12.5) / 30.0) * h_span
            pts.append((px, py))
        draw_outer.polygon(pts, fill=255)

    outer_arr = np.asarray(img_outer, dtype=np.uint8) > 127
    inner_arr = binary_erosion(outer_arr, iterations=lw, border_value=0)
    ring_arr = outer_arr & (~inner_arr)
    return outer_arr, ring_arr


def _connect_floating_islands(
    wire_mask: np.ndarray,
    line_width_px: int,
    min_island_area: int = 24,
) -> Tuple[np.ndarray, int, int]:
    """
    Guarantees that all significant wire segments form a single 100% connected structure
    so nothing falls apart when peeling off the bed or heat-pressing onto a garment.
    Uses sleek, discreet micro-bridges (`0.65 * line_width_px`) so visual details stay crisp!
    """
    labeled, num_features = nd_label(wire_mask)
    if num_features <= 1:
        return wire_mask, max(1, num_features), max(1, num_features)

    counts = np.bincount(labeled.ravel())
    counts[0] = 0
    keep_labels = np.where(counts >= min_island_area)[0]
    if len(keep_labels) == 0:
        return wire_mask, num_features, 1

    cleaned = np.isin(labeled, keep_labels)
    labeled, comp_before = nd_label(cleaned)
    if comp_before <= 1:
        return cleaned, comp_before, comp_before

    work = cleaned.copy()
    pil_bridge = Image.fromarray((work * 255).astype(np.uint8))
    draw = ImageDraw.Draw(pil_bridge)
    bridge_w = max(2, int(round(line_width_px * 0.62)))
    max_bridge_len = max(35.0, min(wire_mask.shape) * 0.16)

    for _ in range(min(55, comp_before - 1)):
        lbl, n_comp = nd_label(work)
        if n_comp <= 1:
            break
        c_sizes = np.bincount(lbl.ravel())
        c_sizes[0] = 0
        main_lbl = int(np.argmax(c_sizes))
        main_mask = lbl == main_lbl
        other_mask = (lbl > 0) & (~main_mask)
        if not np.any(other_mask):
            break

        dist_to_main, indices = distance_transform_edt(~main_mask, return_indices=True)
        other_ys, other_xs = np.where(other_mask)
        dists_other = dist_to_main[other_ys, other_xs]
        best_idx = int(np.argmin(dists_other))
        min_dist = float(dists_other[best_idx])

        y_from, x_from = int(other_ys[best_idx]), int(other_xs[best_idx])
        if min_dist > max_bridge_len:
            # Far-away stray speck (e.g. corner watermark): remove it instead of drawing a long ugly line
            bad_lbl = lbl[y_from, x_from]
            work[lbl == bad_lbl] = False
            pil_bridge = Image.fromarray((work * 255).astype(np.uint8))
            draw = ImageDraw.Draw(pil_bridge)
            continue

        y_to = int(indices[0, y_from, x_from])
        x_to = int(indices[1, y_from, x_from])

        draw.line([(x_from, y_from), (x_to, y_to)], fill=255, width=bridge_w)
        work = np.asarray(pil_bridge, dtype=np.uint8) > 127

    _, comp_after = nd_label(work)
    return work, int(comp_before), int(comp_after)


def _detect_is_lineart(luma: np.ndarray, rgb_f: np.ndarray) -> bool:
    """
    Automatically detects whether the input image is a line-art drawing / manga / logo / coloring page
    versus a continuous-tone photograph.
    """
    sat = (np.max(rgb_f, axis=-1) - np.min(rgb_f, axis=-1)) / 255.0
    extreme_lights = float(np.mean(luma > 0.80))
    extreme_darks = float(np.mean(luma < 0.22))
    midtones = float(np.mean((luma >= 0.25) & (luma <= 0.75)))
    mean_sat = float(np.mean(sat))

    # Typical manga/coloring/logo: mostly white/black background with crisp lines and few midtones
    if (extreme_lights + extreme_darks) > 0.68 and midtones < 0.28:
        return True
    if extreme_lights > 0.52 and mean_sat < 0.14:
        return True
    return False


def _extract_clean_subject_mask(
    rgb_f: np.ndarray,
    luma: np.ndarray,
    remove_bg_auto: bool,
    is_lineart: bool,
) -> Tuple[np.ndarray, bool]:
    """
    Extracts the foreground subject mask and automatically filters out small corner watermarks
    (like 'COURS DE MANGA' logos in corners) when `remove_bg_auto` is enabled.
    Returns `(subject_mask, bg_is_light)`.
    """
    work_h, work_w = luma.shape
    border_strip = np.concatenate(
        [
            rgb_f[:8, :, :].reshape(-1, 3),
            rgb_f[-8:, :, :].reshape(-1, 3),
            rgb_f[:, :8, :].reshape(-1, 3),
            rgb_f[:, -8:, :].reshape(-1, 3),
        ],
        axis=0,
    )
    bg_median = np.median(border_strip, axis=0)
    bg_luma = (0.2126 * bg_median[0] + 0.7152 * bg_median[1] + 0.0722 * bg_median[2]) / 255.0
    bg_is_light = bg_luma > 0.5
    bg_std = float(np.mean(np.std(border_strip, axis=0)))

    if not remove_bg_auto:
        return np.ones((work_h, work_w), dtype=bool), bg_is_light

    dist_from_bg = np.sqrt(np.sum((rgb_f - bg_median[None, None, :]) ** 2, axis=-1))
    fg_diff = dist_from_bg > max(20.0, bg_std * 1.4)

    # Close small gaps along the outer silhouette of the character so interior white regions are filled
    closed_fg = binary_closing(fg_diff, iterations=4 if is_lineart else 3)
    filled_fg = binary_fill_holes(closed_fg)

    # Filter out small disconnected corner watermarks/logos (e.g. top-left watermark on manga scans)
    lbl, n_comp = nd_label(filled_fg)
    if n_comp > 1:
        counts = np.bincount(lbl.ravel())
        counts[0] = 0
        max_area = int(np.max(counts))
        # Keep components that are at least 6% of the main subject's area
        keep_ids = np.where(counts >= max(120, int(max_area * 0.06)))[0]
        filled_fg = np.isin(lbl, keep_ids)

    fg_ratio = float(np.mean(filled_fg))
    if fg_ratio < 0.03 or fg_ratio > 0.97:
        return np.ones((work_h, work_w), dtype=bool), bg_is_light

    return filled_fg, bg_is_light


def _thicken_with_valley_protection(
    raw_lines: np.ndarray,
    target_half_width_px: float,
) -> np.ndarray:
    """
    Thickens `raw_lines` to the desired physical wire width while preserving the white gaps (valleys)
    between closely-spaced parallel lines (eyes, hair strands, kimono patterns, fingers)
    so adjacent lines NEVER fuse into a solid green blob!
    """
    if target_half_width_px <= 0.8:
        return raw_lines

    # 1. Compute distance transform inside the gaps (`~raw_lines`)
    gap_mask = ~raw_lines
    dist_in_gap = distance_transform_edt(gap_mask).astype(np.float32)

    # 2. Identify narrow valleys between nearby lines: local maxima of `dist_in_gap`
    # where two lines are close enough that dilation would otherwise merge them.
    local_max = maximum_filter(dist_in_gap, size=3)
    valley_ridge = (
        gap_mask
        & (dist_in_gap >= 1.0)
        & (dist_in_gap <= target_half_width_px * 2.1 + 1.5)
        & (dist_in_gap >= local_max - 0.25)
    )

    # 3. Distance from raw_lines
    dist_to_line = distance_transform_edt(~raw_lines).astype(np.float32)
    thickened = (dist_to_line <= target_half_width_px) & (~valley_ridge)

    # Light smoothing that respects the valley barrier
    smooth = gaussian_filter(thickened.astype(np.float32), sigma=0.75)
    result = (smooth >= 0.45) & (~valley_ridge)
    return result


def extract_wire_structure(
    img_rgb: np.ndarray,
    req: WirePressPreviewRequest,
) -> Tuple[np.ndarray, np.ndarray, Dict[str, float]]:
    """
    High-Precision Wire Structure Extractor (v2.0):
    - Works at HD resolution (680px) for crisp details.
    - Automatically distinguishes Line-Art/Manga/Logos from Continuous-Tone Photos.
    - Uses Valley-Protected Distance Transform so close lines (kimono patterns, eyes, hair)
      never melt into solid blobs.
    - Hollows out thick dark areas into structural wire loops.
    - Automatically ignores stray corner watermarks when `remove_bg_auto` is enabled.
    """
    src_h, src_w = img_rgb.shape[:2]
    aspect = float(src_w) / max(1.0, float(src_h))
    aspect = max(0.55, min(1.80, aspect))

    work_w = 680
    work_h = int(round(work_w / aspect))
    if work_h > 720:
        work_h = 720
        work_w = int(round(work_h * aspect))

    cropped_rgb = _crop_and_frame_image(
        img_rgb,
        work_w=work_w,
        work_h=work_h,
        zoom=req.zoom,
        offset_x_pct=req.offset_x_pct,
        offset_y_pct=req.offset_y_pct,
        mirror_horizontal=req.mirror_horizontal,
    )

    target_w_mm = float(req.target_width_mm)
    target_h_mm = round(target_w_mm / aspect, 1)
    px_per_mm = work_w / max(25.0, target_w_mm)
    line_width_px = max(3, int(round(req.line_width_mm * px_per_mm)))

    rgb_f = cropped_rgb.astype(np.float32)
    luma = (0.2126 * rgb_f[:, :, 0] + 0.7152 * rgb_f[:, :, 1] + 0.0722 * rgb_f[:, :, 2]) / 255.0
    if req.invert_image:
        luma = 1.0 - luma

    is_lineart_img = _detect_is_lineart(luma, rgb_f)
    subject_mask, bg_is_light = _extract_clean_subject_mask(
        rgb_f, luma, req.remove_bg_auto, is_lineart_img
    )

    detail = float(req.detail_level)

    # Effective style: if the user uploaded a pure line-art/coloring image (like Tanjiro or Goku)
    # and left the style on default `organic_portrait`, use the high-precision line-art ridge extractor
    # so we don't add double-outlines or photo-shadow blobs!
    effective_style = req.wire_style
    if is_lineart_img and req.wire_style == "organic_portrait":
        effective_style = "manga_lineart"

    if effective_style == "manga_lineart":
        # If background is dark and lines are bright (e.g. neon/white logo on black background), flip luma
        work_luma = luma if bg_is_light else (1.0 - luma)

        # Adaptive local ink extraction: captures both thin pen lines and crisp contours
        local_bg = gaussian_filter(work_luma, sigma=8.5)
        local_diff = local_bg - work_luma
        ink_thresh = max(0.035, 0.075 / max(0.35, detail))
        global_thresh = min(0.62, 0.36 * (detail ** 0.55))

        raw_ink = subject_mask & ((local_diff > ink_thresh) | (work_luma < global_thresh))

        # Hollow out any large solid black fills so they become crisp wire loops instead of big flat puddles
        dist_inside_ink = distance_transform_edt(raw_ink).astype(np.float32)
        max_solid_half = max(2.8, line_width_px * 0.65)
        # Keep the contour wall of thick black zones + centerline of normal strokes
        local_ink_max = maximum_filter(dist_inside_ink, size=3)
        stroke_skeleton = (
            raw_ink
            & (dist_inside_ink <= max_solid_half)
            & (dist_inside_ink >= local_ink_max - 0.35)
        )
        thick_region_walls = raw_ink & (dist_inside_ink > 0) & (dist_inside_ink <= max(2.2, line_width_px * 0.45))
        core_lines = stroke_skeleton | thick_region_walls

        target_half_w = max(1.1, (line_width_px * 0.36))
        organic_wire = _thicken_with_valley_protection(core_lines, target_half_w)

    elif effective_style == "organic_portrait":
        # Continuous-tone photo (like the Beagle puppy, cat, or human portrait)
        smooth_luma = gaussian_filter(luma, sigma=0.9)
        gx = sobel(smooth_luma, axis=1)
        gy = sobel(smooth_luma, axis=0)
        grad_mag = np.hypot(gx, gy)
        grad_norm = grad_mag / max(1e-4, float(np.percentile(grad_mag, 98.5)))

        # Ridge detection on gradient magnitude (thin edges before thickening)
        grad_max = maximum_filter(grad_norm, size=3)
        grad_ridges = (grad_norm > (0.28 / max(0.4, detail ** 0.75))) & (grad_norm >= grad_max - 0.04)

        # Multi-scale DoG for expressive facial features (eyes, nose, ear folds)
        dog_fine = gaussian_filter(luma, sigma=1.1) - gaussian_filter(luma, sigma=3.4)
        dog_med = gaussian_filter(luma, sigma=2.2) - gaussian_filter(luma, sigma=6.5)

        dark_ridges = (dog_fine < (-0.036 / max(0.35, detail))) | (
            dog_med < (-0.055 / max(0.35, detail))
        )

        # Hollow loops around deep dark features (pupils, nostrils, mouth)
        deep_dark = subject_mask & (luma < min(0.28, 0.16 * detail))
        dist_dark = distance_transform_edt(deep_dark).astype(np.float32)
        dark_loops = deep_dark & (dist_dark > 0) & (dist_dark <= max(2.2, line_width_px * 0.45))

        # Outer silhouette of the photo subject
        subj_eroded = binary_erosion(subject_mask, iterations=2, border_value=1)
        subject_outline = subject_mask & (~subj_eroded)

        core_lines = subject_mask & (subject_outline | grad_ridges | dark_ridges | dark_loops)
        target_half_w = max(1.3, line_width_px * 0.40)
        organic_wire = _thicken_with_valley_protection(core_lines, target_half_w)

    elif effective_style == "cell_halftone":
        # "cell_halftone": Cellular Grid / Halftone Mesh Structure (like 'Cell: Turn a photo into a cell structure')
        # Builds a connected orthogonal lattice where cell wall thickness / hole aperture is modulated by darkness
        work_luma = luma if bg_is_light else (1.0 - luma)
        smooth_l = gaussian_filter(work_luma, sigma=1.2)
        darkness = np.clip((1.0 - smooth_l) * (0.85 + 0.35 * detail), 0.0, 1.0)

        yy, xx = np.mgrid[0:work_h, 0:work_w]
        pitch = max(10, int(round(line_width_px * (3.2 / max(0.55, detail ** 0.45)))))
        half_p = pitch / 2.0

        # Distance from each pixel to the nearest cell center
        rx = np.abs(((xx % pitch) - half_p)) / half_p  # 0 at cell center, 1 at cell border
        ry = np.abs(((yy % pitch) - half_p)) / half_p
        cell_wall_metric = np.maximum(rx, ry)  # Chebyshev distance to cell center (square cells)

        # Base structural lattice wire (always present inside subject_mask so all cells are 100% linked)
        min_wall_frac = max(0.18, min(0.42, (line_width_px * 0.48) / max(4.0, half_p)))
        # Threshold for hole opening: darker pixels shrink the hole (more plastic), brighter pixels open the hole
        hole_radius_frac = np.clip((1.0 - darkness * 0.88) * (1.0 - min_wall_frac), 0.0, 1.0 - min_wall_frac)
        organic_wire = subject_mask & (cell_wall_metric >= hole_radius_frac)

    else:
        # "streetwear_stencil": graphic shadow contours + diagonal structural mesh inside dark zones
        work_luma = luma if bg_is_light else (1.0 - luma)
        yy, xx = np.mgrid[0:work_h, 0:work_w]
        pitch = max(14, int(round(line_width_px * 3.2)))
        grid_w = max(2, int(round(line_width_px * 0.35)))
        diag_grid = (((xx + yy) % pitch) < grid_w) | (((xx - yy) % pitch) < grid_w)

        shadow_zone = subject_mask & (work_luma < min(0.52, 0.32 * detail))
        dist_shadow = distance_transform_edt(shadow_zone).astype(np.float32)
        shadow_wall = shadow_zone & (dist_shadow <= max(2.2, line_width_px * 0.45))

        local_bg = gaussian_filter(work_luma, sigma=6.0)
        crisp_edges = subject_mask & ((local_bg - work_luma) > (0.055 / max(0.4, detail)))

        core_lines = shadow_wall | (shadow_zone & diag_grid) | crisp_edges
        target_half_w = max(1.1, line_width_px * 0.34)
        organic_wire = _thicken_with_valley_protection(core_lines, target_half_w)

    # 4. Apply Outer Frame (`rounded_rect`, `hexagon`, `circle`, `shield`, `heart`, `silhouette_offset`, `frameless`)
    inside_frame, frame_ring = _build_frame_masks(
        work_w=work_w,
        work_h=work_h,
        frame_mode=req.frame_mode,
        line_width_px=line_width_px,
        subject_mask=subject_mask,
    )
    combined_wire = (organic_wire & inside_frame) | frame_ring

    # 5. Connect Floating Islands (`auto_bridges`) so the print holds in 1 solid piece
    if req.auto_bridges:
        final_wire, comp_before, comp_after = _connect_floating_islands(
            combined_wire,
            line_width_px=line_width_px,
            min_island_area=max(16, int(line_width_px * line_width_px * 0.8)),
        )
    else:
        labeled_raw, comp_before = nd_label(combined_wire)
        counts = np.bincount(labeled_raw.ravel())
        counts[0] = 0
        keep = np.where(counts >= max(14, line_width_px * 2))[0]
        final_wire = np.isin(labeled_raw, keep)
        _, comp_after = nd_label(final_wire)

    coverage_ratio = float(np.mean(final_wire))
    area_mm2 = target_w_mm * target_h_mm * coverage_ratio
    volume_cm3 = (area_mm2 * float(req.thickness_z_mm)) / 1000.0
    filament_grams = round(max(0.5, volume_cm3 * 1.24), 1)
    est_minutes = max(3, int(round(filament_grams * 2.2 + 2.0)))

    stats = {
        "width_mm": round(target_w_mm, 1),
        "height_mm": round(target_h_mm, 1),
        "thickness_z_mm": round(float(req.thickness_z_mm), 2),
        "line_width_mm": round(float(req.line_width_mm), 2),
        "coverage_pct": round(coverage_ratio * 100.0, 1),
        "filament_grams": filament_grams,
        "estimated_print_min": est_minutes,
        "islands_before": int(comp_before),
        "islands_after": int(comp_after),
        "detected_lineart": bool(is_lineart_img),
    }
    return final_wire, cropped_rgb, stats


def render_wire_rgba_base64(wire_mask: np.ndarray, hex_color: str) -> str:
    """
    Renders the boolean `wire_mask` as a razor-sharp, high-definition transparent RGBA PNG
    with realistic 3D extruded filament shading and a clean offset drop shadow.
    """
    h, w = wire_mask.shape
    r, g, b = _hex_to_rgb(hex_color)

    dist_inside = distance_transform_edt(wire_mask).astype(np.float32)
    max_d = max(1.5, float(np.percentile(dist_inside[wire_mask], 90.0)) if np.any(wire_mask) else 2.0)
    ridge = np.clip(dist_inside / max_d, 0.0, 1.0)

    # Crisp 3D filament bevel lighting
    gy, gx = np.gradient(gaussian_filter(wire_mask.astype(np.float32), sigma=0.55))
    bevel = np.clip((-gx - gy) * 0.35, -0.20, 0.24)

    shade = np.clip(0.84 + 0.20 * ridge + bevel, 0.68, 1.18)
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[:, :, 0] = np.clip(r * shade, 0, 255).astype(np.uint8)
    rgba[:, :, 1] = np.clip(g * shade, 0, 255).astype(np.uint8)
    rgba[:, :, 2] = np.clip(b * shade, 0, 255).astype(np.uint8)

    # Razor-sharp anti-aliased edge
    smooth_alpha = gaussian_filter(wire_mask.astype(np.float32), sigma=0.42)
    alpha_wire = np.clip((smooth_alpha - 0.15) / 0.70, 0.0, 1.0)
    rgba[:, :, 3] = (alpha_wire * 255.0).astype(np.uint8)

    buf = io.BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(buf, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"


def render_source_preview_base64(cropped_rgb: np.ndarray) -> str:
    buf = io.BytesIO()
    Image.fromarray(cropped_rgb).save(buf, format="JPEG", quality=90)
    return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"


def build_wirepress_watertight_mesh(
    wire_mask: np.ndarray,
    width_mm: float,
    height_mm: float,
    thickness_z_mm: float,
) -> bytes:
    """
    Converts the 2D `wire_mask` into a clean, watertight 3D binary STL mesh.
    """
    mask_3d = np.flipud(wire_mask)
    padded = np.pad(mask_3d, pad_width=1, mode="constant", constant_values=False)
    py, px = padded.shape

    z_top_val = float(thickness_z_mm)
    active_r, active_c = np.where(padded)
    if len(active_r) == 0:
        raise ValueError("La structure filaire est vide. Augmentez le niveau de détails.")

    x_corners = np.linspace(-width_mm / 2.0, width_mm / 2.0, px + 1, dtype=np.float32)
    y_corners = np.linspace(-height_mm / 2.0, height_mm / 2.0, py + 1, dtype=np.float32)

    r0 = active_r
    c0 = active_c
    r1 = r0 + 1
    c1 = c0 + 1

    x00 = x_corners[c0]
    x10 = x_corners[c1]
    y00 = y_corners[r0]
    y01 = y_corners[r1]

    n_cells = len(r0)
    z0 = np.zeros(n_cells, dtype=np.float32)
    z1 = np.full(n_cells, z_top_val, dtype=np.float32)

    tris_list = []

    t_top1 = np.stack(
        [
            np.column_stack([x00, y00, z1]),
            np.column_stack([x10, y00, z1]),
            np.column_stack([x10, y01, z1]),
        ],
        axis=1,
    )
    t_top2 = np.stack(
        [
            np.column_stack([x00, y00, z1]),
            np.column_stack([x10, y01, z1]),
            np.column_stack([x00, y01, z1]),
        ],
        axis=1,
    )
    t_bot1 = np.stack(
        [
            np.column_stack([x00, y00, z0]),
            np.column_stack([x10, y01, z0]),
            np.column_stack([x10, y00, z0]),
        ],
        axis=1,
    )
    t_bot2 = np.stack(
        [
            np.column_stack([x00, y00, z0]),
            np.column_stack([x00, y01, z0]),
            np.column_stack([x10, y01, z0]),
        ],
        axis=1,
    )
    tris_list.extend([t_top1, t_top2, t_bot1, t_bot2])

    south_open = ~padded[r0 - 1, c0]
    if np.any(south_open):
        xs0, xs1, ys0 = x00[south_open], x10[south_open], y00[south_open]
        zs0, zs1 = z0[south_open], z1[south_open]
        tris_list.append(
            np.stack(
                [
                    np.column_stack([xs0, ys0, zs0]),
                    np.column_stack([xs1, ys0, zs0]),
                    np.column_stack([xs1, ys0, zs1]),
                ],
                axis=1,
            )
        )
        tris_list.append(
            np.stack(
                [
                    np.column_stack([xs0, ys0, zs0]),
                    np.column_stack([xs1, ys0, zs1]),
                    np.column_stack([xs0, ys0, zs1]),
                ],
                axis=1,
            )
        )

    north_open = ~padded[r0 + 1, c0]
    if np.any(north_open):
        xn0, xn1, yn1 = x00[north_open], x10[north_open], y01[north_open]
        zn0, zn1 = z0[north_open], z1[north_open]
        tris_list.append(
            np.stack(
                [
                    np.column_stack([xn1, yn1, zn0]),
                    np.column_stack([xn0, yn1, zn0]),
                    np.column_stack([xn0, yn1, zn1]),
                ],
                axis=1,
            )
        )
        tris_list.append(
            np.stack(
                [
                    np.column_stack([xn1, yn1, zn0]),
                    np.column_stack([xn0, yn1, zn1]),
                    np.column_stack([xn1, yn1, zn1]),
                ],
                axis=1,
            )
        )

    west_open = ~padded[r0, c0 - 1]
    if np.any(west_open):
        xw0, yw0, yw1 = x00[west_open], y00[west_open], y01[west_open]
        zw0, zw1 = z0[west_open], z1[west_open]
        tris_list.append(
            np.stack(
                [
                    np.column_stack([xw0, yw1, zw0]),
                    np.column_stack([xw0, yw0, zw0]),
                    np.column_stack([xw0, yw0, zw1]),
                ],
                axis=1,
            )
        )
        tris_list.append(
            np.stack(
                [
                    np.column_stack([xw0, yw1, zw0]),
                    np.column_stack([xw0, yw0, zw1]),
                    np.column_stack([xw0, yw1, zw1]),
                ],
                axis=1,
            )
        )

    east_open = ~padded[r0, c0 + 1]
    if np.any(east_open):
        xe1, ye0, ye1 = x10[east_open], y00[east_open], y01[east_open]
        ze0, ze1 = z0[east_open], z1[east_open]
        tris_list.append(
            np.stack(
                [
                    np.column_stack([xe1, ye0, ze0]),
                    np.column_stack([xe1, ye1, ze0]),
                    np.column_stack([xe1, ye1, ze1]),
                ],
                axis=1,
            )
        )
        tris_list.append(
            np.stack(
                [
                    np.column_stack([xe1, ye0, ze0]),
                    np.column_stack([xe1, ye1, ze1]),
                    np.column_stack([xe1, ye0, ze1]),
                ],
                axis=1,
            )
        )

    all_tris = np.concatenate(tris_list, axis=0).astype(np.float32)
    num_tris = len(all_tris)

    stl_dtype = np.dtype(
        [
            ("normal", "<f4", (3,)),
            ("v1", "<f4", (3,)),
            ("v2", "<f4", (3,)),
            ("v3", "<f4", (3,)),
            ("attr", "<u2"),
        ]
    )
    records = np.zeros(num_tris, dtype=stl_dtype)
    records["v1"] = all_tris[:, 0, :]
    records["v2"] = all_tris[:, 1, :]
    records["v3"] = all_tris[:, 2, :]

    buf = io.BytesIO()
    header = b"StudioForge 3D - WirePress 3D Textile Transfer Mesh".ljust(80, b"\x00")
    buf.write(header)
    buf.write(np.uint32(num_tris).tobytes())
    buf.write(records.tobytes())
    return buf.getvalue()


@router.post("/upload")
async def upload_wirepress_image(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        pil_img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Image invalide: {exc}") from exc

    max_dim = 1400
    if max(pil_img.size) > max_dim:
        pil_img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

    img_rgb = np.asarray(pil_img, dtype=np.uint8)
    session_id = str(uuid.uuid4())
    session = WirePressSession(
        session_id=session_id,
        filename=file.filename or "image_wire.png",
        img_rgb=img_rgb,
    )
    WIREPRESS_SESSIONS[session_id] = session

    default_req = WirePressPreviewRequest()
    wire_mask, cropped_rgb, stats = extract_wire_structure(img_rgb, default_req)
    wire_rgba_b64 = render_wire_rgba_base64(wire_mask, default_req.wire_hex_color)
    source_b64 = render_source_preview_base64(cropped_rgb)
    session.last_wire_rgba_b64 = wire_rgba_b64

    return {
        "session_id": session_id,
        "filename": session.filename,
        "image_size_px": [int(img_rgb.shape[1]), int(img_rgb.shape[0])],
        "source_preview_data_url": source_b64,
        "wire_rgba_data_url": wire_rgba_b64,
        "stats": stats,
    }


@router.post("/{session_id}/preview")
async def preview_wirepress(session_id: str, req: WirePressPreviewRequest):
    if session_id not in WIREPRESS_SESSIONS:
        raise HTTPException(status_code=404, detail="Session WirePress expirée ou introuvable.")
    session = WIREPRESS_SESSIONS[session_id]

    wire_mask, cropped_rgb, stats = extract_wire_structure(session.img_rgb, req)
    wire_rgba_b64 = render_wire_rgba_base64(wire_mask, req.wire_hex_color)
    source_b64 = render_source_preview_base64(cropped_rgb)
    session.last_wire_rgba_b64 = wire_rgba_b64

    return {
        "session_id": session_id,
        "source_preview_data_url": source_b64,
        "wire_rgba_data_url": wire_rgba_b64,
        "stats": stats,
    }


@router.post("/{session_id}/generate")
async def generate_wirepress_3d(session_id: str, req: WirePressPreviewRequest):
    if session_id not in WIREPRESS_SESSIONS:
        raise HTTPException(status_code=404, detail="Session WirePress expirée ou introuvable.")
    session = WIREPRESS_SESSIONS[session_id]

    wire_mask, _, stats = extract_wire_structure(session.img_rgb, req)
    stl_bytes = build_wirepress_watertight_mesh(
        wire_mask=wire_mask,
        width_mm=stats["width_mm"],
        height_mm=stats["height_mm"],
        thickness_z_mm=req.thickness_z_mm,
    )
    session.last_stl_bytes = stl_bytes

    guide_txt = "\n".join(
        [
            "====================================================================",
            "  STUDIOFORGE 3D — WIREPRESS 3D : FICHE DE PRESSAGE TEXTILE À CHAUD ",
            "====================================================================",
            f"Fichier source : {session.filename}",
            f"Dimensions du Wire : {stats['width_mm']} x {stats['height_mm']} mm",
            f"Épaisseur Z : {stats['thickness_z_mm']} mm ({int(round(stats['thickness_z_mm'] / 0.20))} couches à 0.20 mm)",
            f"Largeur de fil : {stats['line_width_mm']} mm",
            f"Poids estimé : ~{stats['filament_grams']} g",
            "",
            "--- PARAMÈTRES D'IMPRESSION 3D CONSEILLÉS ---",
            "• Hauteur de couche : 0.20 mm (1ère couche à 0.20 mm, vitesse 1ère couche réduite à 35 mm/s)",
            "• Parois (Walls) : 3 à 4 périmètres / Générateur de parois Arachne activé",
            "• Remplissage haut/bas : Motif Concentrique (Concentric) à 100%",
            "• Support / Bordure (Brim) : Aucun (Sans Brim pour garder les bords nets)",
            "",
            "--- GUIDE DE PRESSAGE À CHAUD SUR T-SHIRT / PULL ---",
            "1. Décollez délicatement la structure Wire du plateau une fois refroidi.",
            "2. Pré-chauffez le vêtement 5 secondes pour retirer l'humidité.",
            "3. Posez le Wire sur le T-shirt/Pull et couvrez d'une feuille de papier cuisson (ou Teflon).",
            "4. Température & Durée :",
            "   • Filament PLA / PLA+ : 165 °C pendant 15 à 18 secondes (pression moyenne)",
            "   • Filament TPU 95A (ultra-souple lavage 40°C) : 160 °C pendant 20 à 25 secondes",
            "5. Laissez refroidir 30 secondes à plat avant de retirer le papier cuisson.",
        ]
    )

    zip_buf = io.BytesIO()
    base_name = session.filename.rsplit(".", 1)[0]
    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{base_name}_WirePress3D.stl", stl_bytes)
        zf.writestr("GUIDE_PRESSAGE_TEXTILE_CHAUD.txt", guide_txt)
    session.last_zip_bytes = zip_buf.getvalue()

    return {
        "session_id": session_id,
        "stats": stats,
        "preview_stl_url": f"/api/wirepress/{session_id}/stl",
        "download_stl_url": f"/api/wirepress/{session_id}/download-stl",
        "download_zip_url": f"/api/wirepress/{session_id}/download-zip",
    }


@router.get("/{session_id}/stl")
async def get_wirepress_preview_stl(session_id: str):
    if session_id not in WIREPRESS_SESSIONS or not WIREPRESS_SESSIONS[session_id].last_stl_bytes:
        raise HTTPException(status_code=404, detail="Maillage STL non généré.")
    return Response(content=WIREPRESS_SESSIONS[session_id].last_stl_bytes, media_type="model/stl")


@router.get("/{session_id}/download-stl")
async def download_wirepress_stl(session_id: str):
    if session_id not in WIREPRESS_SESSIONS or not WIREPRESS_SESSIONS[session_id].last_stl_bytes:
        raise HTTPException(status_code=404, detail="Maillage STL non généré.")
    s = WIREPRESS_SESSIONS[session_id]
    base_name = s.filename.rsplit(".", 1)[0]
    return Response(
        content=s.last_stl_bytes,
        media_type="model/stl",
        headers={"Content-Disposition": f'attachment; filename="{base_name}_WirePress3D.stl"'},
    )


@router.get("/{session_id}/download-zip")
async def download_wirepress_zip(session_id: str):
    if session_id not in WIREPRESS_SESSIONS or not WIREPRESS_SESSIONS[session_id].last_zip_bytes:
        raise HTTPException(status_code=404, detail="Archive ZIP non générée.")
    s = WIREPRESS_SESSIONS[session_id]
    base_name = s.filename.rsplit(".", 1)[0]
    return Response(
        content=s.last_zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{base_name}_WirePress3D_Pack.zip"'},
    )
