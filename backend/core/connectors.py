"""
Geometric Connectors & 3D Part Numbering (core/connectors.py)
- Computes 2D cross-section centroids and safe inscribed zones using `shapely`.
- Generates conical prismatic tenons (Hexagonal or Square with 2° draft angle, +0.18mm female clearance)
  and Separate Pegs / Dovetails using `manifold3d`.
- Generates 3D recessed part numbers (0.8 mm depth) engraved directly into the cut faces.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple, Optional, Literal

import numpy as np
import shapely.geometry as sg
import shapely.ops as sops
import trimesh
import manifold3d as m3d

from core.mesh_repair import trimesh_to_manifold, manifold_to_trimesh


ConnectorType = Literal["hexagon_peg", "square_peg", "direct_tenon_hex", "direct_tenon_square", "none"]


@dataclass
class ConnectorConfig:
    connector_type: ConnectorType = "hexagon_peg"
    female_clearance: float = 0.18     # Default +0.18 mm radial/per-side clearance for female sockets
    draft_angle_deg: float = 2.0       # Conical taper angle (2°) for easy insertion and self-centering
    pin_height_half: float = 10.0      # 10 mm into lower part + 10 mm into upper part = 20 mm total peg
    base_size_mm: float = 10.0         # Nominal outer diameter/width of the connector (auto-clamped to section)
    engrave_numbers: bool = True
    engrave_depth_mm: float = 0.8      # 0.8 mm recessed depth on the cut plane


# Vector stroke segments for 7-segment-style 3D printable digits (0-9) in normalized [-0.5, 0.5]x[-0.8, 0.8] space
DIGIT_STROKES = {
    "0": [((-0.4, -0.7), (0.4, -0.7)), ((0.4, -0.7), (0.4, 0.7)), ((0.4, 0.7), (-0.4, 0.7)), ((-0.4, 0.7), (-0.4, -0.7))],
    "1": [((0.0, -0.7), (0.0, 0.7)), ((-0.25, 0.45), (0.0, 0.7)), ((-0.3, -0.7), (0.3, -0.7))],
    "2": [((-0.4, 0.7), (0.4, 0.7)), ((0.4, 0.7), (0.4, 0.0)), ((0.4, 0.0), (-0.4, 0.0)), ((-0.4, 0.0), (-0.4, -0.7)), ((-0.4, -0.7), (0.4, -0.7))],
    "3": [((-0.4, 0.7), (0.4, 0.7)), ((0.4, 0.7), (0.4, -0.7)), ((-0.35, 0.0), (0.4, 0.0)), ((-0.4, -0.7), (0.4, -0.7))],
    "4": [((-0.4, 0.7), (-0.4, 0.0)), ((-0.4, 0.0), (0.4, 0.0)), ((0.25, 0.7), (0.25, -0.7))],
    "5": [((0.4, 0.7), (-0.4, 0.7)), ((-0.4, 0.7), (-0.4, 0.0)), ((-0.4, 0.0), (0.4, 0.0)), ((0.4, 0.0), (0.4, -0.7)), ((0.4, -0.7), (-0.4, -0.7))],
    "6": [((0.4, 0.7), (-0.4, 0.7)), ((-0.4, 0.7), (-0.4, -0.7)), ((-0.4, -0.7), (0.4, -0.7)), ((0.4, -0.7), (0.4, 0.0)), ((0.4, 0.0), (-0.4, 0.0))],
    "7": [((-0.4, 0.7), (0.4, 0.7)), ((0.4, 0.7), (-0.1, -0.7))],
    "8": [((-0.4, -0.7), (0.4, -0.7)), ((0.4, -0.7), (0.4, 0.7)), ((0.4, 0.7), (-0.4, 0.7)), ((-0.4, 0.7), (-0.4, -0.7)), ((-0.4, 0.0), (0.4, 0.0))],
    "9": [((-0.4, -0.7), (0.4, -0.7)), ((0.4, -0.7), (0.4, 0.7)), ((0.4, 0.7), (-0.4, 0.7)), ((-0.4, 0.7), (-0.4, 0.0)), ((-0.4, 0.0), (0.4, 0.0))],
}


def compute_section_polygons_2d(
    mesh: trimesh.Trimesh,
    plane_origin: np.ndarray,
    plane_normal: np.ndarray,
) -> Tuple[List[sg.Polygon], np.ndarray]:
    """
    Slices `mesh` with the plane `(plane_origin, plane_normal)` and returns a list of
    valid 2D `shapely.geometry.Polygon` objects along with the 4x4 `to_3D` transform matrix.
    Pre-filters triangles near the cut plane for instant execution on 2M+ triangle meshes.
    """
    if len(mesh.faces) > 100000:
        verts = mesh.vertices
        faces = mesh.faces
        n = plane_normal / np.linalg.norm(plane_normal)
        dists = (verts - plane_origin) @ n
        f_dists = dists[faces]
        # Keep only triangles that straddle or touch the plane within 1mm
        mask = (f_dists.min(axis=1) <= 1.0) & (f_dists.max(axis=1) >= -1.0)
        sub_faces = faces[mask]
        if len(sub_faces) == 0:
            return [], np.eye(4)
        sub_mesh = trimesh.Trimesh(vertices=verts, faces=sub_faces, process=True)
        section = sub_mesh.section(plane_origin=plane_origin, plane_normal=plane_normal)
    else:
        section = mesh.section(plane_origin=plane_origin, plane_normal=plane_normal)

    if section is None:
        return [], np.eye(4)

    path_2d, to_3d = section.to_2D()
    polys = []
    for poly in path_2d.polygons_full:
        if isinstance(poly, sg.Polygon) and poly.is_valid and poly.area > 4.0:
            polys.append(poly)
    # Sort largest area first
    polys.sort(key=lambda p: p.area, reverse=True)
    return polys, to_3d


def find_optimal_placement_in_polygon(
    poly: sg.Polygon,
    avoid_Center_radius: float = 0.0,
) -> Tuple[Optional[Tuple[float, float]], float]:
    """
    Finds the best 2D placement (x, y) and maximum safe radius inside a `shapely.Polygon`
    for placing a connector or number stamp.
    If `avoid_Center_radius > 0` (e.g. when a reinforcement rod already passes through the middle),
    subtracts an exclusion zone around the rod first.
    """
    work_poly = poly
    if avoid_Center_radius > 0.0:
        center_pt = poly.centroid
        exclusion = center_pt.buffer(avoid_Center_radius + 2.0)
        diff = poly.difference(exclusion)
        if not diff.is_empty:
            if isinstance(diff, sg.MultiPolygon):
                work_poly = max(diff.geoms, key=lambda g: g.area)
            elif isinstance(diff, sg.Polygon):
                work_poly = diff

    if work_poly.is_empty or work_poly.area < 6.0:
        return None, 0.0

    # Try centroid first; if centroid is outside (concave/annular shape), use representative_point
    candidate = work_poly.centroid
    if not work_poly.contains(candidate):
        candidate = work_poly.representative_point()

    clearance_radius = float(work_poly.boundary.distance(candidate))

    # Iterative pole-of-inaccessibility refinement on a small grid inside bounds
    minx, miny, maxx, maxy = work_poly.bounds
    xs = np.linspace(minx, maxx, 12)
    ys = np.linspace(miny, maxy, 12)
    for x in xs:
        for y in ys:
            pt = sg.Point(x, y)
            if work_poly.contains(pt):
                dist = float(work_poly.boundary.distance(pt))
                if dist > clearance_radius:
                    clearance_radius = dist
                    candidate = pt

    return (float(candidate.x), float(candidate.y)), clearance_radius


def create_tapered_prism_manifold(
    shape: Literal["hex", "square"],
    base_width: float,
    height: float,
    draft_angle_deg: float = 2.0,
    extra_clearance: float = 0.0,
    bidirectional: bool = False,
) -> m3d.Manifold:
    """
    Creates a conical/tapered Hexagonal or Square prism along +Z (or [-height, +height] if bidirectional)
    with a 2° draft angle for self-centering fit.
    """
    w_base = base_width + 2.0 * extra_clearance
    taper_delta = 2.0 * height * math.tan(math.radians(draft_angle_deg))
    w_top = max(2.0, w_base - taper_delta)

    r_base = w_base / 2.0
    r_top = w_top / 2.0
    segments = 6 if shape == "hex" else 4

    upper_cone = m3d.Manifold.cylinder(
        height=height,
        radius_low=r_base,
        radius_high=r_top,
        circular_segments=segments,
        center=False,
    )
    if shape == "square":
        # Rotate 45 deg so square faces align cleanly with X/Y axes
        upper_cone = upper_cone.rotate([0.0, 0.0, 45.0])

    if not bidirectional:
        return upper_cone

    # For a standalone double-conical peg (biconical tenon), mirror onto -Z as well
    lower_cone = upper_cone.mirror([0.0, 0.0, 1.0])
    return upper_cone + lower_cone


def create_3d_number_stamp_manifold(
    number_str: str,
    char_height_mm: float = 7.0,
    depth_mm: float = 0.8,
    mirror_x: bool = False,
) -> m3d.Manifold:
    """
    Builds a 3D manifold stamp of `number_str` ('1', '2', ...) centered at (0, 0) in XY,
    spanning `[-depth_mm, +depth_mm]` in Z to cleanly boolean-subtract a 0.8 mm recess on a cut face.
    """
    stroke_thick = max(0.9, char_height_mm * 0.16)
    char_width = char_height_mm * 0.65
    spacing = char_width * 1.35

    polys_2d = []
    total_w = (len(number_str) - 1) * spacing
    start_x = -total_w / 2.0

    for idx, ch in enumerate(number_str):
        strokes = DIGIT_STROKES.get(ch, DIGIT_STROKES["0"])
        cx = start_x + idx * spacing
        for (x0, y0), (x1, y1) in strokes:
            p0 = (cx + x0 * char_width, y0 * (char_height_mm / 2.0))
            p1 = (cx + x1 * char_width, y1 * (char_height_mm / 2.0))
            line = sg.LineString([p0, p1]).buffer(stroke_thick / 2.0, cap_style=1, join_style=1)
            polys_2d.append(line)

    merged = sops.unary_union(polys_2d)
    if isinstance(merged, sg.Polygon):
        geoms = [merged]
    elif isinstance(merged, sg.MultiPolygon):
        geoms = list(merged.geoms)
    else:
        geoms = []

    cross_polygons = []
    for g in geoms:
        ext_coords = np.array(g.exterior.coords[:-1], dtype=np.float64)
        if mirror_x:
            ext_coords[:, 0] = -ext_coords[:, 0]
            ext_coords = ext_coords[::-1]
        # Ensure counter-clockwise orientation for manifold3d CrossSection
        if not sg.LinearRing(ext_coords).is_ccw:
            ext_coords = ext_coords[::-1]
        cross_polygons.append(ext_coords.tolist())
        for interior in g.interiors:
            hole_coords = np.array(interior.coords[:-1], dtype=np.float64)
            if mirror_x:
                hole_coords[:, 0] = -hole_coords[:, 0]
                hole_coords = hole_coords[::-1]
            if sg.LinearRing(hole_coords).is_ccw:
                hole_coords = hole_coords[::-1]
            cross_polygons.append(hole_coords.tolist())

    cs = m3d.CrossSection(cross_polygons)
    stamp = m3d.Manifold.extrude(cs, height=depth_mm * 2.0)
    stamp = stamp.translate([0.0, 0.0, -depth_mm])
    return stamp


def transform_manifold(mani: m3d.Manifold, matrix_4x4: np.ndarray) -> m3d.Manifold:
    """Applies a 4x4 rigid transformation matrix to a `manifold3d.Manifold`."""
    mesh = manifold_to_trimesh(mani)
    mesh.apply_transform(matrix_4x4)
    return trimesh_to_manifold(mesh)


def apply_cut_connectors_and_numbers(
    lower_mani: m3d.Manifold,
    upper_mani: m3d.Manifold,
    reference_mesh: trimesh.Trimesh,
    plane_origin: np.ndarray,
    plane_normal: np.ndarray,
    lower_part_number: int,
    upper_part_number: int,
    config: ConnectorConfig,
    has_cosplay_rod: bool = False,
) -> Tuple[m3d.Manifold, m3d.Manifold, List[trimesh.Trimesh]]:
    """
    On a given cut plane between `lower_mani` and `upper_mani`:
    1. Computes the 2D cross-section polygons (`shapely`).
    2. Places conical geometric connectors (either separate biconical pegs + female sockets,
       or direct male tenon on lower + female socket on upper) if enabled.
    3. Engraves 3D recessed part numbers (`0.8 mm` depth) into both cut faces.
    Returns `(lower_mani_modified, upper_mani_modified, list_of_separate_peg_meshes)`.
    """
    polys_2d, to_3d = compute_section_polygons_2d(reference_mesh, plane_origin, plane_normal)
    separate_pegs: List[trimesh.Trimesh] = []

    if not polys_2d:
        return lower_mani, upper_mani, separate_pegs

    main_poly = polys_2d[0]
    avoid_r = 6.0 if has_cosplay_rod else 0.0
    placement_xy, safe_radius = find_optimal_placement_in_polygon(main_poly, avoid_Center_radius=avoid_r)

    # 1. Geometric Connector (Tenon / Peg)
    if config.connector_type != "none" and placement_xy is not None and safe_radius >= 4.0:
        cx, cy = placement_xy
        # Clamp connector diameter to fit safely inside the cross section with at least 2.2mm wall thickness
        effective_width = min(config.base_size_mm, (safe_radius - 1.8) * 2.0)
        effective_width = max(5.0, effective_width)
        effective_height = min(config.pin_height_half, effective_width * 1.1)

        shape_kind: Literal["hex", "square"] = (
            "hex" if "hex" in config.connector_type else "square"
        )

        # Build local placement matrix at (cx, cy, 0) in the section frame
        T_local = np.eye(4, dtype=np.float64)
        T_local[0, 3] = cx
        T_local[1, 3] = cy
        T_world = to_3d @ T_local

        if config.connector_type in ("hexagon_peg", "square_peg"):
            # Female sockets in both lower and upper halves (+0.18 mm clearance)
            socket_local = create_tapered_prism_manifold(
                shape=shape_kind,
                base_width=effective_width,
                height=effective_height + 0.4,  # +0.4mm bottom clearance
                draft_angle_deg=config.draft_angle_deg,
                extra_clearance=config.female_clearance,
                bidirectional=False,
            )
            socket_world = transform_manifold(socket_local, T_world)
            lower_mani = lower_mani - socket_world
            upper_mani = upper_mani - socket_world

            # Generate printable standalone biconical peg mesh
            peg_local = create_tapered_prism_manifold(
                shape=shape_kind,
                base_width=effective_width,
                height=effective_height,
                draft_angle_deg=config.draft_angle_deg,
                extra_clearance=0.0,
                bidirectional=True,
            )
            peg_mesh = manifold_to_trimesh(peg_local)
            # Lay flat or keep vertical with Z >= 0 for immediate printing
            peg_mesh.apply_translation([0.0, 0.0, effective_height])
            separate_pegs.append(peg_mesh)

        elif config.connector_type in ("direct_tenon_hex", "direct_tenon_square"):
            # Direct male conical tenon protruding from lower_mani into upper_mani's female socket
            male_local = create_tapered_prism_manifold(
                shape=shape_kind,
                base_width=effective_width,
                height=effective_height,
                draft_angle_deg=config.draft_angle_deg,
                extra_clearance=0.0,
                bidirectional=False,
            )
            female_local = create_tapered_prism_manifold(
                shape=shape_kind,
                base_width=effective_width,
                height=effective_height + 0.4,
                draft_angle_deg=config.draft_angle_deg,
                extra_clearance=config.female_clearance,
                bidirectional=False,
            )
            male_world = transform_manifold(male_local, T_world)
            female_world = transform_manifold(female_local, T_world)

            lower_mani = lower_mani + male_world
            upper_mani = upper_mani - female_world

    # 2. 3D Part Numbering (0.8 mm recessed engraving on the cut faces)
    if config.engrave_numbers:
        # Find a clean spot for the number (offset from connector if present)
        num_poly = main_poly
        if placement_xy is not None:
            conn_pt = sg.Point(placement_xy[0], placement_xy[1])
            diff = main_poly.difference(conn_pt.buffer(config.base_size_mm * 0.65))
            if not diff.is_empty:
                if isinstance(diff, sg.MultiPolygon):
                    num_poly = max(diff.geoms, key=lambda g: g.area)
                elif isinstance(diff, sg.Polygon):
                    num_poly = diff

        num_xy, num_radius = find_optimal_placement_in_polygon(num_poly, avoid_Center_radius=avoid_r)
        if num_xy is not None and num_radius >= 3.0:
            char_h = min(8.0, max(4.0, num_radius * 1.1))
            T_num = np.eye(4, dtype=np.float64)
            T_num[0, 3] = num_xy[0]
            T_num[1, 3] = num_xy[1]
            T_num_world = to_3d @ T_num

            try:
                stamp_lower = create_3d_number_stamp_manifold(
                    str(lower_part_number),
                    char_height_mm=char_h,
                    depth_mm=config.engrave_depth_mm,
                    mirror_x=False,
                )
                stamp_upper = create_3d_number_stamp_manifold(
                    str(upper_part_number),
                    char_height_mm=char_h,
                    depth_mm=config.engrave_depth_mm,
                    mirror_x=True,
                )
                lower_mani = lower_mani - transform_manifold(stamp_lower, T_num_world)
                upper_mani = upper_mani - transform_manifold(stamp_upper, T_num_world)
            except Exception:
                # Never fail a cut if a complex polygon prevents text engraving
                pass

    return lower_mani, upper_mani, separate_pegs

