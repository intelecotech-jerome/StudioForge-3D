"""
Cosplay Reinforcement Rod Tunnel Generator (core/cosplay_rod.py)
Supports round, square, and flat hardware store profiles with customizable clearance
and arbitrary 3D start/end points (Point A -> Point B).
Performs ultra-fast boolean subtraction using manifold3d.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Dict, Any, Tuple, Optional, Literal

import numpy as np
import trimesh
import manifold3d as m3d

from core.mesh_repair import trimesh_to_manifold, manifold_to_trimesh


ProfileType = Literal["round", "square", "flat"]

# Standard Hardware Store (Brico) Profiles Catalog in mm
STANDARD_PROFILES: Dict[str, Dict[str, Any]] = {
    "round_4": {"type": "round", "label": "Tige Ronde Ø4 mm", "width": 4.0, "thickness": 4.0},
    "round_6": {"type": "round", "label": "Tige Ronde Ø6 mm", "width": 6.0, "thickness": 6.0},
    "round_8": {"type": "round", "label": "Tige Ronde Ø8 mm", "width": 8.0, "thickness": 8.0},
    "round_10": {"type": "round", "label": "Tige Ronde Ø10 mm", "width": 10.0, "thickness": 10.0},
    "round_12": {"type": "round", "label": "Tige Ronde Ø12 mm", "width": 12.0, "thickness": 12.0},
    "square_6x6": {"type": "square", "label": "Tube Carré 6x6 mm", "width": 6.0, "thickness": 6.0},
    "square_8x8": {"type": "square", "label": "Tube Carré 8x8 mm", "width": 8.0, "thickness": 8.0},
    "square_10x10": {"type": "square", "label": "Tube Carré 10x10 mm", "width": 10.0, "thickness": 10.0},
    "flat_10x2": {"type": "flat", "label": "Plat Aluminium 10x2 mm (Lame fine)", "width": 10.0, "thickness": 2.0},
    "flat_15x3": {"type": "flat", "label": "Plat Aluminium 15x3 mm (Épée large)", "width": 15.0, "thickness": 3.0},
}


@dataclass
class RodParameters:
    profile_type: ProfileType = "round"
    width: float = 8.0           # Diameter for round, side for square, width for flat (mm)
    thickness: float = 8.0       # Ignored for round/square, thickness for flat (mm)
    clearance: float = 0.30      # Radial/total clearance added to diameter/width (+0.30 mm default)
    margin_ends: float = 15.0    # Margin from object extremities if points A/B are auto-computed (mm)
    point_a: Optional[Tuple[float, float, float]] = None
    point_b: Optional[Tuple[float, float, float]] = None
    twist_angle_deg: float = 0.0  # Rotation around rod axis (useful for flat profiles in blades)


@dataclass
class RodReport:
    profile_type: str
    nominal_dimensions_mm: Tuple[float, float]
    cutout_dimensions_mm: Tuple[float, float]
    clearance_mm: float
    point_a: Tuple[float, float, float]
    point_b: Tuple[float, float, float]
    rod_length_mm: float
    recommended_cut_length_mm: float  # With -2 mm axial safety play so rod never blocks joints
    bars_1m_needed: int
    remaining_on_1m_bar_mm: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compute_default_rod_endpoints(
    mesh: trimesh.Trimesh,
    margin_ends: float = 15.0,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Computes default Point A and Point B centered along the vertical Z axis of the object,
    stopping at `margin_ends` (default 15.0 mm) from the bottom and top Z bounds.
    """
    bounds = mesh.bounds
    center_xy = (bounds[0][:2] + bounds[1][:2]) / 2.0
    z_min, z_max = float(bounds[0][2]), float(bounds[1][2])
    total_height = z_max - z_min

    # Ensure valid segment even on very small models
    effective_margin = min(margin_ends, total_height * 0.35)
    pt_a = np.array([center_xy[0], center_xy[1], z_min + effective_margin], dtype=np.float64)
    pt_b = np.array([center_xy[0], center_xy[1], z_max - effective_margin], dtype=np.float64)
    return pt_a, pt_b


def _rotation_matrix_from_z_to_vector(direction: np.ndarray, twist_deg: float = 0.0) -> np.ndarray:
    """
    Builds a 4x4 homogeneous rotation matrix that aligns the local +Z axis with `direction`,
    plus an optional twist angle (in degrees) around the local Z axis.
    """
    z_axis = direction / np.linalg.norm(direction)
    # Pick a reference vector not collinear with z_axis
    ref = np.array([0.0, 1.0, 0.0]) if abs(z_axis[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
    x_axis = np.cross(ref, z_axis)
    x_axis /= np.linalg.norm(x_axis)
    y_axis = np.cross(z_axis, x_axis)

    R_align = np.column_stack((x_axis, y_axis, z_axis))

    if abs(twist_deg) > 1e-5:
        rad = math.radians(twist_deg)
        c, s = math.cos(rad), math.sin(rad)
        R_twist = np.array([
            [c, -s, 0.0],
            [s,  c, 0.0],
            [0.0, 0.0, 1.0],
        ], dtype=np.float64)
        R_align = R_align @ R_twist

    T = np.eye(4, dtype=np.float64)
    T[:3, :3] = R_align
    return T


def build_rod_manifold(params: RodParameters, pt_a: np.ndarray, pt_b: np.ndarray) -> Tuple[m3d.Manifold, trimesh.Trimesh]:
    """
    Constructs the 3D rod tunnel volume (with clearance) between Point A and Point B
    as both a `manifold3d.Manifold` (for CSG subtraction) and a `trimesh.Trimesh` (for preview).
    """
    vec = pt_b - pt_a
    length = float(np.linalg.norm(vec))
    if length < 1e-3:
        raise ValueError("Points A and B for the reinforcement rod are identical or too close.")

    clearance = float(params.clearance)
    w_cut = float(params.width) + clearance
    t_cut = (float(params.width) if params.profile_type in ("round", "square") else float(params.thickness)) + clearance

    if params.profile_type == "round":
        radius = w_cut / 2.0
        rod_mani = m3d.Manifold.cylinder(
            height=length,
            radius_low=radius,
            radius_high=radius,
            circular_segments=48,
            center=False,
        )
    elif params.profile_type == "square":
        rod_mani = m3d.Manifold.cube([w_cut, w_cut, length], center=True)
        rod_mani = rod_mani.translate([0.0, 0.0, length / 2.0])
    elif params.profile_type == "flat":
        rod_mani = m3d.Manifold.cube([w_cut, t_cut, length], center=True)
        rod_mani = rod_mani.translate([0.0, 0.0, length / 2.0])
    else:
        raise ValueError(f"Unsupported rod profile_type: {params.profile_type}")

    # Convert to trimesh to apply exact 3D orientation & translation from Point A to Point B
    rod_mesh = manifold_to_trimesh(rod_mani)
    T = _rotation_matrix_from_z_to_vector(vec, twist_deg=params.twist_angle_deg)
    T[:3, 3] = pt_a
    rod_mesh.apply_transform(T)

    rod_mani_transformed = trimesh_to_manifold(rod_mesh)
    return rod_mani_transformed, rod_mesh


def subtract_cosplay_rod(
    mesh: trimesh.Trimesh,
    params: RodParameters,
    base_mani: Optional[m3d.Manifold] = None,
) -> Tuple[trimesh.Trimesh, trimesh.Trimesh, RodReport, m3d.Manifold]:
    """
    Subtracts the cosplay reinforcement rod tunnel from `mesh` using `manifold3d`.
    Returns:
      - hollowed_mesh: The mesh with the internal tunnel subtracted
      - rod_preview_mesh: The 3D mesh of the tunnel itself (for display/verification)
      - report: Exact hardware cut specifications (length to cut on a 1m bar, etc.)
      - result_mani: The manifold3d.Manifold object ready for instant slicing
    """
    if params.point_a is not None and params.point_b is not None:
        pt_a = np.array(params.point_a, dtype=np.float64)
        pt_b = np.array(params.point_b, dtype=np.float64)
    else:
        pt_a, pt_b = compute_default_rod_endpoints(mesh, margin_ends=params.margin_ends)

    rod_mani, rod_preview_mesh = build_rod_manifold(params, pt_a, pt_b)
    if base_mani is None:
        base_mani = trimesh_to_manifold(mesh)

    # Boolean CSG Difference via manifold3d
    result_mani = base_mani - rod_mani
    if result_mani.num_tri() == 0:
        raise ValueError("La soustraction booléenne a produit un maillage vide (vérifiez la topologie du modèle).")
    hollowed_mesh = manifold_to_trimesh(result_mani)

    rod_length = float(np.linalg.norm(pt_b - pt_a))
    # Recommend cutting 2mm shorter than the internal blind tunnel so glue/expansion never prevents closing the seam
    recommended_cut = max(1.0, round(rod_length - 2.0, 1))
    bars_1m = max(1, math.ceil(recommended_cut / 1000.0))
    remaining_1m = round(bars_1m * 1000.0 - recommended_cut, 1)

    nom_t = params.width if params.profile_type in ("round", "square") else params.thickness
    cut_w = round(params.width + params.clearance, 3)
    cut_t = round(nom_t + params.clearance, 3)

    report = RodReport(
        profile_type=params.profile_type,
        nominal_dimensions_mm=(round(params.width, 2), round(nom_t, 2)),
        cutout_dimensions_mm=(cut_w, cut_t),
        clearance_mm=round(params.clearance, 3),
        point_a=(round(float(pt_a[0]), 2), round(float(pt_a[1]), 2), round(float(pt_a[2]), 2)),
        point_b=(round(float(pt_b[0]), 2), round(float(pt_b[1]), 2), round(float(pt_b[2]), 2)),
        rod_length_mm=round(rod_length, 1),
        recommended_cut_length_mm=recommended_cut,
        bars_1m_needed=bars_1m,
        remaining_on_1m_bar_mm=remaining_1m,
    )

    return hollowed_mesh, rod_preview_mesh, report, result_mani

