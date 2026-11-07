"""
StudioForge 3D — Module HueForge 3D Pop-Out & Diorama Hybride
Permet de faire jaillir un véritable objet 3D (.STL ou Sujet 2D gonflé en volume 3D)
hors d'un tableau HueForge (Style 'Faucon Millenium Hyperspace' et 'Carte Pokémon Jolteon VMAX'),
avec génération automatique du Socle Présentoir Triangulaire Incliné (30° à 65°).
"""
from __future__ import annotations

import math
from typing import List, Literal, Optional, Tuple

import manifold3d as m3d
import numpy as np
import trimesh
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

PopoutMode = Literal["none", "stl_popout", "image_puff_3d"]
PopoutAssembly = Literal["monobloc_fusion", "snap_fit_socket"]
PopoutPresetStl = Literal["starship_falcon", "dragon_head", "pokeball_emblem", "custom_stl"]


def _trimesh_to_manifold_safe(mesh: trimesh.Trimesh) -> m3d.Manifold:
    v = np.ascontiguousarray(mesh.vertices, dtype=np.float32)
    f = np.ascontiguousarray(mesh.faces, dtype=np.uint32)
    return m3d.Manifold(m3d.Mesh(vert_properties=v, tri_verts=f))


def _manifold_to_trimesh_safe(man: m3d.Manifold) -> trimesh.Trimesh:
    m_mesh = man.to_mesh()
    verts = np.array(m_mesh.vert_properties[:, :3], dtype=np.float32)
    faces = np.array(m_mesh.tri_verts, dtype=np.int32)
    if len(verts) == 0 or len(faces) == 0:
        return trimesh.creation.box(extents=[2.0, 2.0, 1.0])
    return trimesh.Trimesh(vertices=verts, faces=faces, process=True)


def build_procedural_popout_stl(preset_id: str) -> trimesh.Trimesh:
    """
    Generates high-detail, watertight procedural 3D meshes for immediate 1-click testing:
    - `starship_falcon`: Sci-Fi Millennium Falcon style starship with saucer hull, forward mandibles,
      side cockpit tube, sensor dish, and dorsal quad-turret.
    - `dragon_head`: Stylized low-poly/sculpted Dragon bust with horns, snout, and neck crest.
    - `pokeball_emblem`: 3D Trophy Sphere / TCG Emblem with equatorial band and center button.
    - `rubber_duck`: Smooth 3D Duck mesh (for Bas-Relief & Pop-Out testing).
    """
    parts: List[trimesh.Trimesh] = []

    if preset_id == "starship_falcon":
        # 1. Main Saucer Hull (flattened cylinder + beveled upper/lower domes)
        saucer_mid = trimesh.creation.cylinder(radius=36.0, height=5.5, sections=48)
        saucer_top = trimesh.creation.cone(radius=35.5, height=6.5, sections=48)
        saucer_top.apply_translation([0.0, 0.0, 2.75])
        saucer_bot = trimesh.creation.cone(radius=35.5, height=5.0, sections=48)
        saucer_bot.apply_transform(trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0]))
        saucer_bot.apply_translation([0.0, 0.0, -2.75])
        parts.extend([saucer_mid, saucer_top, saucer_bot])

        # 2. Forward Mandibles (Left & Right tapered prongs extending toward +Y)
        for sign_x in (-1.0, 1.0):
            mandible = trimesh.creation.box(extents=[13.5, 42.0, 6.2])
            # Taper slightly inward
            mandible.apply_transform(
                trimesh.transformations.rotation_matrix(math.radians(-sign_x * 6.0), [0, 0, 1])
            )
            mandible.apply_translation([sign_x * 11.5, 36.0, 0.0])
            parts.append(mandible)

            # Mechanical greeble armor plates on each mandible
            plate = trimesh.creation.box(extents=[8.5, 28.0, 8.0])
            plate.apply_transform(
                trimesh.transformations.rotation_matrix(math.radians(-sign_x * 6.0), [0, 0, 1])
            )
            plate.apply_translation([sign_x * 11.5, 33.0, 0.8])
            parts.append(plate)

        # 3. Starboard Cockpit Tube & Outrigger Corridor (iconic side cockpit on +X side)
        corridor = trimesh.creation.cylinder(radius=4.8, height=24.0, sections=24)
        corridor.apply_transform(trimesh.transformations.rotation_matrix(math.radians(90.0), [0, 1, 0]))
        corridor.apply_translation([28.0, 12.0, 0.5])
        cockpit = trimesh.creation.cylinder(radius=5.4, height=22.0, sections=24)
        cockpit.apply_transform(trimesh.transformations.rotation_matrix(math.radians(-90.0), [1, 0, 0]))
        cockpit.apply_translation([38.5, 20.0, 0.8])
        cockpit_nose = trimesh.creation.cone(radius=5.4, height=8.0, sections=24)
        cockpit_nose.apply_transform(trimesh.transformations.rotation_matrix(math.radians(-90.0), [1, 0, 0]))
        cockpit_nose.apply_translation([38.5, 31.0, 0.8])
        parts.extend([corridor, cockpit, cockpit_nose])

        # 4. Dorsal Quad-Laser Turret & 6 Rear Engine Exhaust Vents
        turret_base = trimesh.creation.cylinder(radius=7.5, height=4.5, sections=24)
        turret_base.apply_translation([0.0, 0.0, 6.5])
        parts.append(turret_base)
        for ang_deg in range(-50, 60, 20):
            ang = math.radians(ang_deg)
            vent = trimesh.creation.box(extents=[5.2, 6.0, 3.2])
            vent.apply_translation([22.0 * math.sin(ang), -18.0 * math.cos(ang), 5.2])
            parts.append(vent)

        # 5. Radar Dish on Port Side (-X)
        dish_stalk = trimesh.creation.cylinder(radius=1.8, height=6.5, sections=16)
        dish_stalk.apply_translation([-18.0, 14.0, 6.5])
        dish_cone = trimesh.creation.cone(radius=6.2, height=3.5, sections=24)
        dish_cone.apply_transform(trimesh.transformations.rotation_matrix(math.radians(145.0), [1, 0, 0]))
        dish_cone.apply_translation([-18.0, 15.0, 10.2])
        parts.extend([dish_stalk, dish_cone])

    elif preset_id == "dragon_head":
        # Stylized Dragon Head & Neck emerging forward
        neck = trimesh.creation.cylinder(radius=16.0, height=36.0, sections=24)
        neck.apply_transform(trimesh.transformations.rotation_matrix(math.radians(-25.0), [1, 0, 0]))
        neck.apply_translation([0.0, -6.0, 12.0])
        skull = trimesh.creation.icosphere(subdivisions=2, radius=18.5)
        skull.apply_scale([0.85, 1.15, 0.82])
        skull.apply_translation([0.0, 6.0, 26.0])
        snout = trimesh.creation.cone(radius=13.5, height=28.0, sections=16)
        snout.apply_transform(trimesh.transformations.rotation_matrix(math.radians(-78.0), [1, 0, 0]))
        snout.apply_translation([0.0, 14.0, 24.0])
        jaw = trimesh.creation.cone(radius=10.5, height=24.0, sections=16)
        jaw.apply_transform(trimesh.transformations.rotation_matrix(math.radians(-62.0), [1, 0, 0]))
        jaw.apply_translation([0.0, 12.0, 18.0])
        parts.extend([neck, skull, snout, jaw])
        # Two swept-back horns
        for sx in (-1.0, 1.0):
            horn = trimesh.creation.cone(radius=4.8, height=28.0, sections=16)
            horn.apply_transform(trimesh.transformations.rotation_matrix(math.radians(42.0), [1, 0, 0]))
            horn.apply_transform(trimesh.transformations.rotation_matrix(math.radians(sx * 18.0), [0, 1, 0]))
            horn.apply_translation([sx * 9.5, -2.0, 34.0])
            parts.append(horn)

    elif preset_id == "rubber_duck":
        # Classic 3D Rubber Duck (like Photo 1 'Relief')
        body = trimesh.creation.icosphere(subdivisions=3, radius=24.0)
        body.apply_scale([1.35, 0.95, 0.85])
        body.apply_translation([0.0, -10.0, 0.0])
        head = trimesh.creation.icosphere(subdivisions=3, radius=16.5)
        head.apply_translation([-12.0, 14.0, 2.0])
        beak = trimesh.creation.cone(radius=7.5, height=16.0, sections=24)
        beak.apply_transform(trimesh.transformations.rotation_matrix(math.radians(-90.0), [0, 1, 0]))
        beak.apply_scale([1.0, 0.55, 1.0])
        beak.apply_translation([-24.0, 12.0, 2.0])
        tail = trimesh.creation.cone(radius=9.0, height=18.0, sections=20)
        tail.apply_transform(trimesh.transformations.rotation_matrix(math.radians(55.0), [0, 1, 0]))
        tail.apply_translation([26.0, -4.0, 0.0])
        wing = trimesh.creation.icosphere(subdivisions=2, radius=14.0)
        wing.apply_scale([1.25, 0.65, 0.45])
        wing.apply_translation([2.0, -10.0, 15.0])
        parts.extend([body, head, beak, tail, wing])

    else:
        # `pokeball_emblem`: 3D Sphere / TCG Power Emblem
        sphere = trimesh.creation.icosphere(subdivisions=3, radius=26.0)
        band = trimesh.creation.cylinder(radius=26.8, height=4.2, sections=48)
        band.apply_transform(trimesh.transformations.rotation_matrix(math.radians(90.0), [1, 0, 0]))
        btn_outer = trimesh.creation.cylinder(radius=8.5, height=28.5, sections=32)
        btn_inner = trimesh.creation.cylinder(radius=5.2, height=30.0, sections=32)
        parts.extend([sphere, band, btn_outer, btn_inner])

    combined = trimesh.util.concatenate(parts)
    try:
        # Union via Manifold3D if all parts are clean volumes
        man_total = _trimesh_to_manifold_safe(parts[0])
        for p in parts[1:]:
            man_total = man_total + _trimesh_to_manifold_safe(p)
        return _manifold_to_trimesh_safe(man_total)
    except Exception:
        return combined


def build_inclined_display_stand(
    plaque_width_mm: float,
    plaque_height_mm: float,
    plaque_thickness_mm: float,
    angle_deg: float = 45.0,
) -> trimesh.Trimesh:
    """
    Builds the sleek Triangular Wedge Display Stand shown in Photo 2 (under the Millennium Falcon HueForge):
    - Supports the HueForge painting at `angle_deg` (e.g. 45°) from horizontal.
    - Includes a front retaining lip + channeled slot (`plaque_thickness_mm + 0.6 mm` wide)
      so the HueForge plaque slides in and is held firmly even with a heavy 3D Pop-Out model on the front!
    """
    ang_rad = math.radians(max(25.0, min(70.0, float(angle_deg))))
    stand_w = max(60.0, min(250.0, float(plaque_width_mm) * 0.92))
    slant_len = max(55.0, min(160.0, float(plaque_height_mm) * 0.62))

    # Right-triangle profile in (Y, Z):
    # Front bottom lip at (y=0, z=0), rising along slant to back top at (y = slant_len * cos(a), z = slant_len * sin(a))
    back_y = slant_len * math.cos(ang_rad)
    top_z = slant_len * math.sin(ang_rad)

    slot_w = max(2.8, float(plaque_thickness_mm) + 0.65)
    lip_h = 9.5
    lip_thick = 4.2

    # Normal to the inclined plane pointing forward-up: (-sin(a), cos(a))
    nx, ny = -math.sin(ang_rad), math.cos(ang_rad)

    # Outer 2D polygon of the wedge side profile in (Y, Z):
    p_front_bot = (0.0, 0.0)
    p_back_bot = (back_y, 0.0)
    p_back_top = (back_y, top_z)
    # Front retaining hook / cradle at the bottom of the ramp:
    lip_base_y = - (slot_w + lip_thick) * math.sin(ang_rad)
    lip_base_z = 0.0
    lip_tip_y = lip_base_y + lip_h * math.cos(ang_rad)
    lip_tip_z = lip_h * math.sin(ang_rad) + 4.5
    slot_bot_y = -slot_w * math.sin(ang_rad)
    slot_bot_z = 3.2

    poly_2d = [
        (lip_base_y, lip_base_z),
        p_back_bot,
        p_back_top,
        (0.0, 3.2),
        (slot_bot_y, slot_bot_z),
        (lip_tip_y, lip_tip_z),
    ]

    try:
        import shapely.geometry as sg

        ring = sg.Polygon(poly_2d)
        if not ring.is_valid:
            ring = ring.buffer(0)
        # Carve a weight-saving triangular cutout inside the wedge if large enough
        inner_hole = ring.buffer(-6.5)
        cs_polys = [list(ring.exterior.coords)[:-1]]
        if not inner_hole.is_empty and inner_hole.geom_type == "Polygon" and inner_hole.area > 180.0:
            cs_polys.append(list(inner_hole.exterior.coords)[::-1][:-1])

        cs = m3d.CrossSection(cs_polys)
        man_extruded = m3d.Manifold.extrude(cs, height=stand_w)
        mesh = _manifold_to_trimesh_safe(man_extruded)
        # Rotate so extrusion is along X (-stand_w/2 .. +stand_w/2) and profile (Y, Z) sits on Z>=0
        # Currently (X_prof -> Y, Y_prof -> Z, Z_ext -> X)
        verts = mesh.vertices.copy()
        new_verts = np.column_stack([
            verts[:, 2] - stand_w / 2.0,
            verts[:, 0] - back_y / 2.0,
            verts[:, 1],
        ])
        mesh.vertices = new_verts
        b = mesh.bounds
        mesh.apply_translation([0.0, 0.0, -b[0][2]])
        return mesh
    except Exception:
        box = trimesh.creation.box(extents=[stand_w, back_y, top_z])
        return box


def compute_subject_puff_dome(
    arr_rgb: np.ndarray,
    puff_height_mm: float = 8.5,
    scale_pct: float = 65.0,
    offset_x_pct: float = 0.0,
    offset_y_pct: float = 0.0,
    inside_mask: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Segments the main character/subject directly on the cropped/framed `(H, W, 3)` image `arr_rgb`
    and computes a smooth 3D anatomical puff offset `puff_offset_mm` (`(H, W)` in mm),
    the binary subject mask `fg_mask` (`(H, W)` bool), and normalized dome `dome_norm` (`[0..1]`).
    """
    grid_h, grid_w, _ = arr_rgb.shape
    rgb_f = arr_rgb.astype(np.float32)
    luma = (0.2126 * rgb_f[:, :, 0] + 0.7152 * rgb_f[:, :, 1] + 0.0722 * rgb_f[:, :, 2]) / 255.0

    # Sample background color from outer border (or near the boundary of `inside_mask` if shaped tile)
    if inside_mask is not None and np.any(inside_mask):
        eroded = binary_erosion(inside_mask, iterations=max(2, min(grid_h, grid_w) // 35))
        rim_sample_mask = inside_mask & (~eroded)
        if np.sum(rim_sample_mask) >= 20:
            border_pixels = rgb_f[rim_sample_mask]
        else:
            border_pixels = rgb_f[inside_mask]
    else:
        bw = max(4, grid_w // 18)
        bh = max(4, grid_h // 18)
        border_pixels = np.concatenate(
            [
                rgb_f[:bh, :, :].reshape(-1, 3),
                rgb_f[-bh:, :, :].reshape(-1, 3),
                rgb_f[:, :bw, :].reshape(-1, 3),
                rgb_f[:, -bw:, :].reshape(-1, 3),
            ],
            axis=0,
        )
    bg_med = np.median(border_pixels, axis=0)
    dist_color = np.sqrt(np.sum((rgb_f - bg_med[None, None, :]) ** 2, axis=-1))

    # Central subject spotlight ellipse controlled by `scale_pct` ("Zone du Sujet") and `offset_x/y_pct`
    yy, xx = np.mgrid[0:grid_h, 0:grid_w]
    cx = (grid_w / 2.0) + (float(offset_x_pct) / 100.0) * (grid_w * 0.35)
    cy = (grid_h / 2.0) - (float(offset_y_pct) / 100.0) * (grid_h * 0.35)
    scale_clamped = max(20.0, min(100.0, float(scale_pct)))
    rx = max(10.0, grid_w * 0.48 * (scale_clamped / 100.0))
    ry = max(10.0, grid_h * 0.48 * (scale_clamped / 100.0))
    norm_rad_sq = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2
    in_ellipse = norm_rad_sq <= 1.0
    if inside_mask is not None:
        in_ellipse = in_ellipse & inside_mask

    sat = (np.max(rgb_f, axis=-1) - np.min(rgb_f, axis=-1)) / 255.0
    gx = sobel(luma, axis=1)
    gy = sobel(luma, axis=0)
    edges = np.hypot(gx, gy)
    edge_energy = gaussian_filter(edges, sigma=max(2.0, min(grid_h, grid_w) * 0.012))

    # Salience combines color contrast against background, saturation, and character line-art energy
    radial_bonus = np.clip(1.0 - 0.35 * norm_rad_sq, 0.2, 1.0)
    salience = ((dist_color / 95.0) + sat * 0.85 + edge_energy * 1.45) * radial_bonus

    if np.any(in_ellipse):
        # Adaptive threshold: lower `scale_pct` focuses tightly on the core subject; higher `scale_pct` captures wider aura/body
        pct_cut = float(np.clip(62.0 - 0.32 * scale_clamped, 24.0, 55.0))
        thresh = max(0.18, float(np.percentile(salience[in_ellipse], pct_cut)))
        fg_raw = in_ellipse & ((salience >= thresh) | (dist_color >= 42.0))
    else:
        fg_raw = in_ellipse

    close_iters = max(2, min(5, min(grid_h, grid_w) // 75))
    fg_mask = binary_fill_holes(binary_closing(fg_raw, iterations=close_iters))
    if inside_mask is not None:
        fg_mask = fg_mask & inside_mask

    lbl, n_c = nd_label(fg_mask)
    if n_c > 1:
        counts = np.bincount(lbl.ravel())
        counts[0] = 0
        main_id = int(np.argmax(counts))
        # Keep main component and any substantial secondary component (>12% of main, e.g. raised fist/weapon)
        main_cnt = counts[main_id]
        keep_ids = np.where(counts >= max(12, int(main_cnt * 0.12)))[0]
        fg_mask = np.isin(lbl, keep_ids)

    if np.mean(fg_mask) < 0.015:
        fg_mask = in_ellipse

    # Smooth organic 3D inflation dome + anatomical relief details
    dist_in = distance_transform_edt(fg_mask).astype(np.float32)
    max_d = max(2.0, float(np.max(dist_in)))
    dome = np.power(np.clip(dist_in / (max_d * 0.68), 0.0, 1.0), 0.54)
    sigma_dome = max(1.4, min(grid_h, grid_w) * 0.012)
    dome_smooth = gaussian_filter(dome, sigma=sigma_dome) * fg_mask.astype(np.float32)

    # Local sculptural detail (bright muscles/armor bulge out, dark manga ink lines carve crisp 3D grooves)
    local_luma_diff = luma - gaussian_filter(luma, sigma=max(2.5, min(grid_h, grid_w) * 0.018))
    ink_groove = np.clip((0.22 - luma) / 0.22, 0.0, 1.0) * 0.14
    sculpt_factor = np.clip(
        dome_smooth * 0.82 + (luma * 0.14 + local_luma_diff * 0.24 - ink_groove) * (dome_smooth > 0.05),
        0.0,
        1.0,
    )
    # Feather the outer 2 pixels of `fg_mask` for a clean transition wall
    edge_ramp = np.clip(dist_in / max(1.5, min(4.0, max_d * 0.12)), 0.0, 1.0)
    dome_norm = sculpt_factor * edge_ramp * fg_mask.astype(np.float32)
    puff_offset_mm = dome_norm * float(puff_height_mm)
    return puff_offset_mm, fg_mask, dome_norm


def build_image_puff_3d_manifold(
    img_rgb: np.ndarray,
    bbox_2d: Tuple[float, float, float, float],
    base_z_mm: float,
    puff_height_mm: float = 8.5,
    offset_x_pct: float = 0.0,
    offset_y_pct: float = 0.0,
    scale_pct: float = 75.0,
) -> Tuple[m3d.Manifold, trimesh.Trimesh]:
    """
    Standalone fallback 3D Puff manifold builder.
    """
    from modules_futurs.makerlab_gen import _heightmap_to_watertight_trimesh
    from PIL import Image

    minx, miny, maxx, maxy = bbox_2d
    w_mm = maxx - minx
    h_mm = maxy - miny

    res = 200
    aspect = w_mm / max(1.0, h_mm)
    grid_w = res if aspect >= 1.0 else max(64, int(round(res * aspect)))
    grid_h = max(64, int(round(res / aspect))) if aspect >= 1.0 else res

    pil_img = Image.fromarray(img_rgb).resize((grid_w, grid_h), Image.Resampling.LANCZOS)
    rgb_f = np.asarray(pil_img, dtype=np.float32)
    puff_offset, fg_mask, _ = compute_subject_puff_dome(
        rgb_f,
        puff_height_mm=puff_height_mm,
        scale_pct=scale_pct,
        offset_x_pct=offset_x_pct,
        offset_y_pct=offset_y_pct,
    )
    puff_z = base_z_mm + puff_offset
    px_mm = w_mm / float(grid_w)
    puff_mesh = _heightmap_to_watertight_trimesh(puff_z, fg_mask, px_mm, z_bottom=max(0.4, base_z_mm - 0.6))
    return _trimesh_to_manifold_safe(puff_mesh), puff_mesh


def render_popout_2d_preview_overlay(
    out_rgb: np.ndarray,
    small_rgb: np.ndarray,
    bbox_2d: Tuple[float, float, float, float],
    plaque_top_z_mm: float,
    popout_mode: str = "none",
    popout_preset_stl: str = "starship_falcon",
    custom_popout_mesh: Optional[trimesh.Trimesh] = None,
    popout_scale_pct: float = 60.0,
    popout_pitch_deg: float = 32.0,
    popout_yaw_deg: float = 0.0,
    popout_roll_deg: float = -12.0,
    popout_offset_x_pct: float = 0.0,
    popout_offset_y_pct: float = 0.0,
    popout_sink_pct: float = 28.0,
    popout_puff_height_mm: float = 8.5,
    popout_hex_color: str = "#94a3b8",
    inside_mask: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Renders a live, interactive 3D Pop-Out preview directly onto the 2D Studio Preview image (`out_rgb`):
    - In `image_puff_3d` mode: computes the subject 3D puff dome, casts a directional 3D drop shadow
      onto the flat HueForge background, applies 3D normal-mapped studio lighting & specular rim highlights
      onto the puffed character, and draws a subtle cyan/gold 3D relief contour ring.
    - In `stl_popout` mode: projects the positioned 3D `.STL` model (Millennium Falcon, Dragon, Pokéball,
      or Custom STL) onto the 2D HueForge canvas with real-time 3D Lambertian + Specular shading in
      `popout_hex_color` and a realistic 3D cast drop shadow!
    """
    if popout_mode == "none" or not popout_mode:
        return out_rgb

    ph, pw, _ = out_rgb.shape
    res_rgb = out_rgb.copy().astype(np.float32)

    if popout_mode == "image_puff_3d":
        puff_offset, fg_mask, dome_norm = compute_subject_puff_dome(
            small_rgb,
            puff_height_mm=popout_puff_height_mm,
            scale_pct=popout_scale_pct,
            offset_x_pct=popout_offset_x_pct,
            offset_y_pct=popout_offset_y_pct,
            inside_mask=inside_mask,
        )
        if not np.any(fg_mask):
            return out_rgb

        # 1. Cast a 3D drop shadow from the puffed subject onto the surrounding flat HueForge plate
        h_ratio = np.clip(float(popout_puff_height_mm) / 10.0, 0.25, 2.2)
        shift_x = max(2, int(round(7.0 * h_ratio)))
        shift_y = max(2, int(round(9.0 * h_ratio)))
        fg_f = fg_mask.astype(np.float32)
        shifted_mask = np.zeros_like(fg_f)
        if shift_y < ph and shift_x < pw:
            shifted_mask[shift_y:, shift_x:] = fg_f[:-shift_y, :-shift_x]
        shadow_field = gaussian_filter(shifted_mask, sigma=max(3.5, 6.0 * h_ratio))
        bg_zone = ~fg_mask
        # Slightly dim background plate & apply deep 3D drop shadow so the puffed subject pops out dramatically
        shadow_mult = np.clip(0.84 - 0.52 * shadow_field, 0.22, 0.88)
        res_rgb[bg_zone] = res_rgb[bg_zone] * shadow_mult[bg_zone, None]

        # 2. 3D Normal-Map Studio Lighting & Specular Rim on the Puffed Subject
        dz_dy, dz_dx = np.gradient(puff_offset * 0.85)
        nx = -dz_dx
        ny = -dz_dy
        nz = np.ones_like(puff_offset)
        norm_len = np.maximum(1e-5, np.sqrt(nx * nx + ny * ny + nz * nz))
        nx /= norm_len
        ny /= norm_len
        nz /= norm_len

        # Key light from top-left-front (-0.48, -0.52, 0.71)
        ndotl = np.clip(nx * (-0.48) + ny * (-0.52) + nz * 0.71, 0.0, 1.0)
        # Half-vector specular highlight for 3D sculpted sheen
        spec = np.power(np.clip(nx * (-0.28) + ny * (-0.32) + nz * 0.90, 0.0, 1.0), 16.0)
        bevel_light = (0.72 + 0.48 * ndotl) * (0.92 + 0.18 * dome_norm)
        lit_subj = res_rgb * bevel_light[:, :, None] + (spec * 52.0 * h_ratio)[:, :, None]
        res_rgb[fg_mask] = np.clip(lit_subj[fg_mask], 0.0, 255.0)

        # 3. Crisp 3D Pop-Out perimeter indicator contour (cyan-amber glow on the raised cliff wall)
        edge_band = binary_dilation(fg_mask, iterations=2) & (~binary_erosion(fg_mask, iterations=1))
        if inside_mask is not None:
            edge_band = edge_band & inside_mask
        res_rgb[edge_band] = 0.35 * res_rgb[edge_band] + 0.65 * np.array([0.0, 240.0, 255.0], dtype=np.float32)
        return np.clip(res_rgb, 0.0, 255.0)

    if popout_mode == "stl_popout":
        if popout_preset_stl == "custom_stl" and custom_popout_mesh is not None:
            raw_mesh = custom_popout_mesh
        else:
            raw_mesh = build_procedural_popout_stl(popout_preset_stl)

        _, _, part_mesh = position_and_clip_popout_stl(
            raw_mesh=raw_mesh,
            bbox_2d=bbox_2d,
            plaque_top_z_mm=plaque_top_z_mm,
            scale_pct=popout_scale_pct,
            pitch_deg=popout_pitch_deg,
            yaw_deg=popout_yaw_deg,
            roll_deg=popout_roll_deg,
            offset_x_pct=popout_offset_x_pct,
            offset_y_pct=popout_offset_y_pct,
            sink_pct=popout_sink_pct,
            assembly_mode="monobloc_fusion",
        )
        if part_mesh is None or len(part_mesh.faces) == 0:
            return out_rgb

        minx, miny, maxx, maxy = bbox_2d
        span_x = max(1.0, maxx - minx)
        span_y = max(1.0, maxy - miny)

        # Sample dense surface points + normals on triangles above the HueForge plaque
        faces = part_mesh.faces
        verts = part_mesh.vertices
        f_norms = part_mesh.face_normals
        v0 = verts[faces[:, 0]]
        v1 = verts[faces[:, 1]]
        v2 = verts[faces[:, 2]]

        # Keep faces that emerge above the plaque
        f_max_z = np.maximum(np.maximum(v0[:, 2], v1[:, 2]), v2[:, 2])
        vis_mask = f_max_z >= (plaque_top_z_mm - 0.2)
        if not np.any(vis_mask):
            return out_rgb

        v0 = v0[vis_mask]
        v1 = v1[vis_mask]
        v2 = v2[vis_mask]
        fn = f_norms[vis_mask]

        # Generate barycentric grid samples per triangle so every visible triangle is solidly rasterized
        steps = 7
        bary_uv = []
        for iu in range(steps + 1):
            for iv in range(steps + 1 - iu):
                u = iu / float(steps)
                v = iv / float(steps)
                bary_uv.append((u, v, 1.0 - u - v))
        bary = np.array(bary_uv, dtype=np.float32)  # (K, 3)

        pts = (
            bary[:, 0][:, None, None] * v0[None, :, :]
            + bary[:, 1][:, None, None] * v1[None, :, :]
            + bary[:, 2][:, None, None] * v2[None, :, :]
        ).reshape(-1, 3)
        norms = np.repeat(fn[None, :, :], len(bary), axis=0).reshape(-1, 3)

        # Map (X, Y) in bbox_2d to pixel coordinates (px, py)
        px = np.round(((pts[:, 0] - minx) / span_x) * (pw - 1)).astype(np.int32)
        py = np.round(((maxy - pts[:, 1]) / span_y) * (ph - 1)).astype(np.int32)
        valid = (px >= 0) & (px < pw) & (py >= 0) & (py < ph) & (pts[:, 2] >= plaque_top_z_mm - 0.1)
        if not np.any(valid):
            return out_rgb

        px = px[valid]
        py = py[valid]
        pz = pts[valid, 2]
        norms = norms[valid]

        # Sort ascending by Z so painter's algorithm writes front-most 3D surface last
        order = np.argsort(pz)
        px = px[order]
        py = py[order]
        pz = pz[order]
        norms = norms[order]

        # Parse hex color
        hx = (popout_hex_color or "#94a3b8").lstrip("#")
        if len(hx) == 6:
            base_c = np.array([int(hx[0:2], 16), int(hx[2:4], 16), int(hx[4:6], 16)], dtype=np.float32)
        else:
            base_c = np.array([148.0, 163.0, 184.0], dtype=np.float32)

        # 3D Lambertian + Specular lighting
        ndotl = np.clip(norms[:, 0] * (-0.42) + norms[:, 1] * 0.48 + norms[:, 2] * 0.77, 0.0, 1.0)
        spec = np.power(np.clip(norms[:, 0] * (-0.22) + norms[:, 1] * 0.28 + norms[:, 2] * 0.93, 0.0, 1.0), 18.0)
        z_rel = np.clip((pz - plaque_top_z_mm) / max(8.0, float(np.max(pz) - plaque_top_z_mm)), 0.0, 1.0)
        lit_c = base_c[None, :] * (0.32 + 0.68 * ndotl[:, None]) * (0.85 + 0.20 * z_rel[:, None]) + (spec * 95.0)[:, None]
        lit_c = np.clip(lit_c, 0.0, 255.0)

        obj_mask = np.zeros((ph, pw), dtype=bool)
        color_buf = np.zeros((ph, pw, 3), dtype=np.float32)
        obj_mask[py, px] = True
        color_buf[py, px] = lit_c

        # Fill tiny 1px pinhole gaps between triangle samples
        closed_mask = binary_closing(obj_mask, iterations=2)
        if inside_mask is not None:
            closed_mask = closed_mask & inside_mask
            obj_mask = obj_mask & inside_mask

        for ch in range(3):
            blurred_ch = gaussian_filter(color_buf[:, :, ch], sigma=1.1)
            weight_ch = gaussian_filter(obj_mask.astype(np.float32), sigma=1.1)
            filled_ch = blurred_ch / np.maximum(1e-4, weight_ch)
            color_buf[:, :, ch] = np.where(obj_mask, color_buf[:, :, ch], filled_ch)

        # Cast 3D drop shadow onto the HueForge plate toward bottom-right
        sh_mask = np.zeros((ph, pw), dtype=np.float32)
        sh_mask[8:, 7:] = closed_mask[:-8, :-7].astype(np.float32)
        sh_blur = gaussian_filter(sh_mask, sigma=6.5)
        bg_zone = ~closed_mask
        res_rgb[bg_zone] = res_rgb[bg_zone] * np.clip(1.0 - 0.62 * sh_blur[bg_zone, None], 0.25, 1.0)

        # Composite 3D shaded STL object + subtle cyan rim highlight
        res_rgb[closed_mask] = color_buf[closed_mask]
        rim = binary_dilation(closed_mask, iterations=1) & (~closed_mask)
        if inside_mask is not None:
            rim = rim & inside_mask
        res_rgb[rim] = 0.45 * res_rgb[rim] + 0.55 * np.array([0.0, 240.0, 255.0], dtype=np.float32)
        return np.clip(res_rgb, 0.0, 255.0)

    return out_rgb



def position_and_clip_popout_stl(
    raw_mesh: trimesh.Trimesh,
    bbox_2d: Tuple[float, float, float, float],
    plaque_top_z_mm: float,
    scale_pct: float = 60.0,
    pitch_deg: float = 32.0,
    yaw_deg: float = 0.0,
    roll_deg: float = -12.0,
    offset_x_pct: float = 0.0,
    offset_y_pct: float = 0.0,
    sink_pct: float = 28.0,
    assembly_mode: PopoutAssembly = "monobloc_fusion",
) -> Tuple[Optional[m3d.Manifold], Optional[m3d.Manifold], trimesh.Trimesh]:
    """
    Positions, scales, and tilts a 3D `.STL` mesh so it bursts out of the HueForge plaque (`Z >= plaque_top_z_mm`),
    slices off any rear geometry protruding below `Z = 0.4 mm` so the back of the HueForge stays flat on the print bed,
    and returns:
      - `union_mani`: Manifold to union with the HueForge tile (if `monobloc_fusion`)
      - `socket_mani`: Manifold to subtract from the HueForge tile (if `snap_fit_socket`)
      - `popout_part_mesh`: The standalone/assembled 3D Pop-Out mesh
    """
    mesh = raw_mesh.copy()
    # 1. Center mesh at origin
    b = mesh.bounds
    center = (b[0] + b[1]) / 2.0
    mesh.apply_translation(-center)

    # 2. Apply rotations (Pitch = nose tilting out of the frame, Roll = banking, Yaw = turning)
    if abs(pitch_deg) > 0.1:
        mesh.apply_transform(trimesh.transformations.rotation_matrix(math.radians(pitch_deg), [1, 0, 0]))
    if abs(roll_deg) > 0.1:
        mesh.apply_transform(trimesh.transformations.rotation_matrix(math.radians(roll_deg), [0, 1, 0]))
    if abs(yaw_deg) > 0.1:
        mesh.apply_transform(trimesh.transformations.rotation_matrix(math.radians(yaw_deg), [0, 0, 1]))

    # 3. Scale to `scale_pct` % of the HueForge plaque span
    minx, miny, maxx, maxy = bbox_2d
    plaque_w = maxx - minx
    plaque_h = maxy - miny
    target_span = min(plaque_w, plaque_h) * (max(15.0, min(130.0, float(scale_pct))) / 100.0)
    ext = mesh.extents
    max_xy = max(1e-3, float(max(ext[0], ext[1])))
    scale_factor = target_span / max_xy
    mesh.apply_scale(scale_factor)

    # 4. Translate to X, Y target position and sink into Z = plaque_top_z_mm
    b2 = mesh.bounds
    z_span = max(1.0, float(b2[1][2] - b2[0][2]))
    # Place bottom of mesh at `plaque_top_z_mm - (sink_pct/100) * z_span`
    sink_mm = (max(0.0, min(75.0, float(sink_pct))) / 100.0) * z_span
    z_shift = (plaque_top_z_mm - sink_mm) - float(b2[0][2])

    tx = ((minx + maxx) / 2.0) + (offset_x_pct / 100.0) * (plaque_w * 0.38)
    ty = ((miny + maxy) / 2.0) + (offset_y_pct / 100.0) * (plaque_h * 0.38)
    mesh.apply_translation([tx, ty, z_shift])

    # 5. Clip everything below `z_cut` so the back of the HueForge (`Z = 0`) is 100% flat!
    z_cut = 0.48 if assembly_mode == "monobloc_fusion" else max(0.6, plaque_top_z_mm - 0.8)
    try:
        man_mesh = _trimesh_to_manifold_safe(mesh)
        clip_box = m3d.Manifold.cube([plaque_w * 2.5, plaque_h * 2.5, 400.0], center=True).translate(
            [(minx + maxx) / 2.0, (miny + maxy) / 2.0, z_cut + 200.0]
        )
        man_clipped = man_mesh ^ clip_box

        if assembly_mode == "snap_fit_socket":
            # Add a hexagonal snap-fit alignment peg under the clipped 3D object
            peg_r = min(12.0, target_span * 0.16)
            peg_h = max(1.1, plaque_top_z_mm * 0.65)
            peg_male = m3d.Manifold.cylinder(height=peg_h, radius_low=peg_r, radius_high=peg_r, circular_segments=6)
            peg_male = peg_male.translate([tx, ty, z_cut - peg_h + 0.2])
            man_part = man_clipped + peg_male

            # Female socket to subtract from the HueForge plaque (with 0.20mm clearance)
            peg_female = m3d.Manifold.cylinder(
                height=plaque_top_z_mm + 2.0,
                radius_low=peg_r + 0.22,
                radius_high=peg_r + 0.22,
                circular_segments=6,
            ).translate([tx, ty, z_cut - peg_h])
            part_mesh = _manifold_to_trimesh_safe(man_part)
            return None, peg_female, part_mesh
        else:
            part_mesh = _manifold_to_trimesh_safe(man_clipped)
            return man_clipped, None, part_mesh
    except Exception:
        return None, None, mesh

