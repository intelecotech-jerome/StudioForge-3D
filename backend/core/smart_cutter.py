"""
Smart Cutter Engine (core/smart_cutter.py)
- Mode A (Auto-Grid Cosplay): Automatically slices models exceeding build volume (e.g. max_build_size = 285 mm
  for Creality K1 Max 300x300x300 mm or Creality Hi) into printable segments along Z (or full 3D grid),
  adding conical geometric connectors and 3D recessed part numbers (`1`, `2`, `3`...).
- Mode B (Bounded Cut Figurine): Performs a localized planar cut restricted to a 3D Bounding Box or Cylinder
  (e.g., to detach an arm, wing, or head on a figurine without slicing through the rest of the body).
- Packages all resulting watertight STL parts + connector pegs into a ready-to-slice `.ZIP` archive.
"""
from __future__ import annotations

import io
import math
import zipfile
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Tuple, Optional, Literal

import numpy as np
import trimesh
import manifold3d as m3d

from core.mesh_repair import trimesh_to_manifold, manifold_to_trimesh, export_mesh_stl_bytes
from core.connectors import (
    ConnectorConfig,
    apply_cut_connectors_and_numbers,
    transform_manifold,
)


# Printer Presets
PRINTER_PRESETS: Dict[str, Dict[str, Any]] = {
    "k1_max": {
        "name": "Creality K1 Max",
        "bed_size_mm": (300.0, 300.0, 300.0),
        "recommended_max_cut_mm": 285.0,
    },
    "creality_hi": {
        "name": "Creality Hi",
        "bed_size_mm": (260.0, 260.0, 300.0),
        "recommended_max_cut_mm": 245.0,
    },
}


@dataclass
class PartMetadata:
    part_index: int
    filename: str
    extents_mm: Tuple[float, float, float]
    bbox_min: Tuple[float, float, float]
    bbox_max: Tuple[float, float, float]
    volume_mm3: float
    faces_count: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BoundedCutParams:
    plane_origin: Tuple[float, float, float] = (0.0, 0.0, 100.0)
    plane_normal: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    bound_type: Literal["box", "cylinder"] = "cylinder"
    bound_size: Tuple[float, float, float] = (80.0, 80.0, 80.0)  # (X, Y, Z) for box or (Diameter, Diameter, Height) for cylinder


def compute_auto_cut_planes_z(
    mesh: trimesh.Trimesh,
    max_build_size: float = 285.0,
) -> List[float]:
    """
    Computes evenly distributed Z cut heights so every resulting segment has height <= `max_build_size`.
    """
    bounds = mesh.bounds
    z_min, z_max = float(bounds[0][2]), float(bounds[1][2])
    total_z = z_max - z_min

    if total_z <= max_build_size:
        return []

    num_segments = math.ceil(total_z / max_build_size)
    step = total_z / num_segments
    return [round(z_min + i * step, 3) for i in range(1, num_segments)]


def _create_halfspace_boxes_z(
    bbox_min: np.ndarray,
    bbox_max: np.ndarray,
    z_cut: float,
    padding: float = 50.0,
) -> Tuple[m3d.Manifold, m3d.Manifold]:
    """
    Creates two large `manifold3d` boxes representing `{Z <= z_cut}` (lower) and `{Z >= z_cut}` (upper).
    """
    span_x = (bbox_max[0] - bbox_min[0]) + 2.0 * padding
    span_y = (bbox_max[1] - bbox_min[1]) + 2.0 * padding
    cx = (bbox_min[0] + bbox_max[0]) / 2.0
    cy = (bbox_min[1] + bbox_max[1]) / 2.0

    lower_h = (z_cut - bbox_min[2]) + padding
    upper_h = (bbox_max[2] - z_cut) + padding

    lower_box = m3d.Manifold.cube([span_x, span_y, lower_h], center=True)
    lower_box = lower_box.translate([cx, cy, z_cut - lower_h / 2.0])

    upper_box = m3d.Manifold.cube([span_x, span_y, upper_h], center=True)
    upper_box = upper_box.translate([cx, cy, z_cut + upper_h / 2.0])

    return lower_box, upper_box


def slice_auto_grid_cosplay(
    mesh: trimesh.Trimesh,
    max_build_size: float = 285.0,
    custom_z_planes: Optional[List[float]] = None,
    connector_config: Optional[ConnectorConfig] = None,
    has_cosplay_rod: bool = False,
    base_mani: Optional[m3d.Manifold] = None,
) -> Tuple[List[Tuple[str, trimesh.Trimesh]], List[PartMetadata], List[float]]:
    """
    Mode A (Auto-Grid Cosplay):
    Slices `mesh` along horizontal Z planes (either auto-computed for `max_build_size = 285 mm`
    or user-specified `custom_z_planes`).
    On every cut plane, generates conical tenons/pegs and 3D recessed part numbers (`1`, `2`, `3`...).
    """
    if connector_config is None:
        connector_config = ConnectorConfig()

    z_planes = sorted(custom_z_planes) if custom_z_planes is not None else compute_auto_cut_planes_z(mesh, max_build_size)
    bbox_min, bbox_max = mesh.bounds[0].copy(), mesh.bounds[1].copy()

    if not z_planes:
        meta = _build_part_metadata(1, "part_01.stl", mesh)
        return [("part_01.stl", mesh)], [meta], []

    current_mani = base_mani if base_mani is not None else trimesh_to_manifold(mesh)
    parts_manifolds: List[m3d.Manifold] = []
    all_pegs: List[trimesh.Trimesh] = []

    for idx, z_cut in enumerate(z_planes):
        part_num_lower = idx + 1
        part_num_upper = idx + 2

        lower_box, upper_box = _create_halfspace_boxes_z(bbox_min, bbox_max, z_cut)
        lower_mani = current_mani ^ lower_box  # Intersection
        upper_mani = current_mani ^ upper_box  # Intersection

        plane_origin = np.array([0.0, 0.0, float(z_cut)], dtype=np.float64)
        plane_normal = np.array([0.0, 0.0, 1.0], dtype=np.float64)

        lower_mani, upper_mani, pegs = apply_cut_connectors_and_numbers(
            lower_mani=lower_mani,
            upper_mani=upper_mani,
            reference_mesh=mesh,
            plane_origin=plane_origin,
            plane_normal=plane_normal,
            lower_part_number=part_num_lower,
            upper_part_number=part_num_upper,
            config=connector_config,
            has_cosplay_rod=has_cosplay_rod,
        )

        parts_manifolds.append(lower_mani)
        all_pegs.extend(pegs)
        current_mani = upper_mani

    parts_manifolds.append(current_mani)

    output_files: List[Tuple[str, trimesh.Trimesh]] = []
    metadata_list: List[PartMetadata] = []

    for i, p_mani in enumerate(parts_manifolds, start=1):
        p_mesh = manifold_to_trimesh(p_mani)
        fname = f"part_{i:02d}.stl"
        output_files.append((fname, p_mesh))
        metadata_list.append(_build_part_metadata(i, fname, p_mesh))

    # Add connector pegs if any were generated
    if all_pegs:
        combined_pegs = _arrange_pegs_on_grid(all_pegs)
        peg_fname = f"connectors_pegs_x{len(all_pegs)}.stl"
        output_files.append((peg_fname, combined_pegs))
        metadata_list.append(_build_part_metadata(len(output_files), peg_fname, combined_pegs))

    return output_files, metadata_list, z_planes


def slice_bounded_figurine(
    mesh: trimesh.Trimesh,
    bounded_params: BoundedCutParams,
    connector_config: Optional[ConnectorConfig] = None,
) -> Tuple[List[Tuple[str, trimesh.Trimesh]], List[PartMetadata]]:
    """
    Mode B (Bounded Cut Figurine):
    Performs a localized cut inside a 3D Bounding Box or Cylinder centered at `plane_origin`
    oriented along `plane_normal`. Only geometry inside the bounding volume is split by the plane,
    allowing clean detachment of an arm, head, or weapon without slicing adjacent parts of the figurine.
    """
    if connector_config is None:
        connector_config = ConnectorConfig()

    origin = np.array(bounded_params.plane_origin, dtype=np.float64)
    normal = np.array(bounded_params.plane_normal, dtype=np.float64)
    norm_len = np.linalg.norm(normal)
    if norm_len < 1e-6:
        normal = np.array([0.0, 0.0, 1.0], dtype=np.float64)
    else:
        normal = normal / norm_len

    bx, by, bz = [float(v) for v in bounded_params.bound_size]
    half_h = bz / 2.0

    # Build local bounding volume split into lower [-half_h, 0] and upper [0, +half_h]
    if bounded_params.bound_type == "cylinder":
        radius = bx / 2.0
        upper_local = m3d.Manifold.cylinder(height=half_h, radius_low=radius, radius_high=radius, circular_segments=48, center=False)
        lower_local = upper_local.mirror([0.0, 0.0, 1.0])
    else:
        upper_local = m3d.Manifold.cube([bx, by, half_h], center=True).translate([0.0, 0.0, half_h / 2.0])
        lower_local = m3d.Manifold.cube([bx, by, half_h], center=True).translate([0.0, 0.0, -half_h / 2.0])

    # Transform local bounding volume to `(origin, normal)`
    T_plane = trimesh.geometry.align_vectors([0.0, 0.0, 1.0], normal)
    T_plane[:3, 3] = origin

    upper_bound_mani = transform_manifold(upper_local, T_plane)
    lower_bound_mani = transform_manifold(lower_local, T_plane)

    base_mani = trimesh_to_manifold(mesh)

    # Detach the upper bounded region from the main body
    detached_mani = base_mani ^ upper_bound_mani
    main_body_mani = base_mani - upper_bound_mani

    # Reference mesh inside the full local bounding box so connector only considers the local limb cross-section
    local_region_mani = base_mani ^ (upper_bound_mani + lower_bound_mani)
    local_ref_mesh = manifold_to_trimesh(local_region_mani)

    main_body_mani, detached_mani, pegs = apply_cut_connectors_and_numbers(
        lower_mani=main_body_mani,
        upper_mani=detached_mani,
        reference_mesh=local_ref_mesh,
        plane_origin=origin,
        plane_normal=normal,
        lower_part_number=1,
        upper_part_number=2,
        config=connector_config,
        has_cosplay_rod=False,
    )

    body_mesh = manifold_to_trimesh(main_body_mani)
    detached_mesh = manifold_to_trimesh(detached_mani)

    output_files: List[Tuple[str, trimesh.Trimesh]] = [
        ("figurine_body_01.stl", body_mesh),
        ("figurine_detached_part_02.stl", detached_mesh),
    ]
    metadata_list: List[PartMetadata] = [
        _build_part_metadata(1, "figurine_body_01.stl", body_mesh),
        _build_part_metadata(2, "figurine_detached_part_02.stl", detached_mesh),
    ]

    if pegs:
        combined_pegs = _arrange_pegs_on_grid(pegs)
        peg_fname = f"connectors_pegs_x{len(pegs)}.stl"
        output_files.append((peg_fname, combined_pegs))
        metadata_list.append(_build_part_metadata(3, peg_fname, combined_pegs))

    return output_files, metadata_list


def package_parts_to_zip_bytes(
    parts: List[Tuple[str, trimesh.Trimesh]],
    extra_report_txt: Optional[str] = None,
) -> bytes:
    """Packages all generated STL meshes and an optional assembly instructions text file into a ZIP archive."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for filename, part_mesh in parts:
            stl_bytes = export_mesh_stl_bytes(part_mesh)
            zf.writestr(filename, stl_bytes)
        if extra_report_txt:
            zf.writestr("READ_ME_ASSEMBLY_GUIDE.txt", extra_report_txt.encode("utf-8"))
    return zip_buffer.getvalue()


def _arrange_pegs_on_grid(pegs: List[trimesh.Trimesh], spacing: float = 25.0) -> trimesh.Trimesh:
    """Arranges multiple connector pegs on a neat X/Y grid so they can be printed in one go."""
    arranged = []
    cols = max(1, int(math.ceil(math.sqrt(len(pegs)))))
    for idx, peg in enumerate(pegs):
        p_copy = peg.copy()
        r = idx // cols
        c = idx % cols
        p_copy.apply_translation([c * spacing, r * spacing, 0.0])
        arranged.append(p_copy)
    return trimesh.util.concatenate(arranged)


def _build_part_metadata(index: int, filename: str, mesh: trimesh.Trimesh) -> PartMetadata:
    bounds = mesh.bounds if mesh.bounds is not None and len(mesh.vertices) > 0 else np.zeros((2, 3))
    extents = mesh.extents if mesh.extents is not None and len(mesh.vertices) > 0 else np.zeros(3)
    if len(mesh.faces) <= 250000 and len(mesh.vertices) > 0:
        vol = float(mesh.volume) if mesh.is_watertight else float(np.prod(extents) * 0.35)
    else:
        vol = float(np.prod(extents) * 0.35)
    return PartMetadata(
        part_index=index,
        filename=filename,
        extents_mm=(round(float(extents[0]), 2), round(float(extents[1]), 2), round(float(extents[2]), 2)),
        bbox_min=(round(float(bounds[0][0]), 2), round(float(bounds[0][1]), 2), round(float(bounds[0][2]), 2)),
        bbox_max=(round(float(bounds[1][0]), 2), round(float(bounds[1][1]), 2), round(float(bounds[1][2]), 2)),
        volume_mm3=round(vol, 1),
        faces_count=int(len(mesh.faces)),
    )

