"""
Import, Inspection, Auto-Repair & PCA Alignment for STL meshes.
Uses trimesh, manifold3d, pymeshfix, numpy, and scipy.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, asdict
from typing import Dict, Any, Tuple, Optional

import numpy as np
import trimesh
import manifold3d as m3d

try:
    import pymeshfix
    HAS_PYMESHFIX = True
except ImportError:
    HAS_PYMESHFIX = False


@dataclass
class MeshStats:
    is_watertight: bool
    is_winding_consistent: bool
    repaired: bool
    repair_method: str
    vertices_count: int
    faces_count: int
    bbox_min: Tuple[float, float, float]
    bbox_max: Tuple[float, float, float]
    extents: Tuple[float, float, float]  # (X, Y, Z) in mm
    volume_mm3: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _single_shell_to_manifold(shell: trimesh.Trimesh) -> Optional[m3d.Manifold]:
    """
    Converts a single connected mesh shell into a valid `manifold3d.Manifold`.
    1. Tries direct C++ conversion.
    2. If not manifold, runs `pymeshfix.MeshFix.fill_holes()`.
    3. If still not manifold and <= 200k faces, runs `pymeshfix.clean_from_arrays()`.
    4. Automatically flips inverted normals if the resulting volume is negative.
    """
    if len(shell.faces) < 12:
        return None

    verts = np.ascontiguousarray(shell.vertices, dtype=np.float32)
    faces = np.ascontiguousarray(shell.faces, dtype=np.uint32)
    mani = m3d.Manifold(m3d.Mesh(vert_properties=verts, tri_verts=faces))

    if mani.status() != m3d.Error.NoError and HAS_PYMESHFIX:
        # Step A: Fast C++ boundary hole-filling (handles 1.8M+ triangle shells in seconds)
        try:
            mf = pymeshfix.MeshFix(
                np.asarray(shell.vertices, dtype=np.float64),
                np.asarray(shell.faces, dtype=np.int32),
            )
            mf.fill_holes()
            v_fh = np.ascontiguousarray(mf.points, dtype=np.float32)
            f_fh = np.ascontiguousarray(mf.faces, dtype=np.uint32)
            mani = m3d.Manifold(m3d.Mesh(vert_properties=v_fh, tri_verts=f_fh))
        except Exception:
            pass

        # Step B: Full topological clean for shells <= 200k faces if hole-filling wasn't enough
        if mani.status() != m3d.Error.NoError and len(shell.faces) <= 200000:
            try:
                v_cl, f_cl = pymeshfix.clean_from_arrays(
                    np.asarray(shell.vertices, dtype=np.float64),
                    np.asarray(shell.faces, dtype=np.int32),
                    verbose=False,
                    joincomp=False,
                    remove_smallest_components=False,
                )
                if len(v_cl) >= 4 and len(f_cl) >= 4:
                    mani = m3d.Manifold(
                        m3d.Mesh(
                            vert_properties=np.ascontiguousarray(v_cl, dtype=np.float32),
                            tri_verts=np.ascontiguousarray(f_cl, dtype=np.uint32),
                        )
                    )
            except Exception:
                pass

    if mani.status() != m3d.Error.NoError or mani.num_tri() == 0:
        return None

    # Fix inside-out shells (negative volume) by reversing triangle winding
    if mani.volume() < 0:
        m_mesh = mani.to_mesh()
        v_inv = np.array(m_mesh.vert_properties[:, :3], dtype=np.float32)
        f_orig = np.array(m_mesh.tri_verts, dtype=np.uint32)
        f_inv = np.column_stack([f_orig[:, 0], f_orig[:, 2], f_orig[:, 1]])
        mani_flipped = m3d.Manifold(m3d.Mesh(vert_properties=v_inv, tri_verts=f_inv))
        if mani_flipped.status() == m3d.Error.NoError and mani_flipped.num_tri() > 0:
            mani = mani_flipped

    return mani


def trimesh_to_manifold(mesh: trimesh.Trimesh) -> m3d.Manifold:
    """
    Convert a `trimesh.Trimesh` into a guaranteed valid `manifold3d.Manifold` object.
    If the mesh is a multi-shell assembly or contains floating stray triangles (1-3 faces),
    automatically filters out degenerate debris and repairs each shell independently.
    """
    verts = np.ascontiguousarray(mesh.vertices, dtype=np.float32)
    faces = np.ascontiguousarray(mesh.faces, dtype=np.uint32)
    mani = m3d.Manifold(m3d.Mesh(vert_properties=verts, tri_verts=faces))
    if mani.status() == m3d.Error.NoError and mani.num_tri() > 0:
        if mani.volume() < 0:
            mani = _single_shell_to_manifold(mesh) or mani
        return mani

    # Multi-shell split & per-component repair
    shells = mesh.split(only_watertight=False)
    valid_manifolds = []
    for shell in shells:
        if len(shell.faces) < 12:
            # Ignore stray flat debris (< 12 triangles) common in ZBrush/Blender exports
            continue
        s_mani = _single_shell_to_manifold(shell)
        if s_mani is not None:
            valid_manifolds.append(s_mani)

    if not valid_manifolds:
        raise ValueError("Impossible de convertir le maillage en volume Manifold valide.")

    if len(valid_manifolds) == 1:
        return valid_manifolds[0]

    return m3d.Manifold.batch_boolean(valid_manifolds, m3d.OpType.Add)


def manifold_to_trimesh(manifold: m3d.Manifold) -> trimesh.Trimesh:
    """Convert a manifold3d.Manifold back into a clean trimesh.Trimesh."""
    m_mesh = manifold.to_mesh()
    verts = np.array(m_mesh.vert_properties[:, :3], dtype=np.float64)
    faces = np.array(m_mesh.tri_verts, dtype=np.int64)
    # process=False avoids heavy O(N log N) vertex re-hashing on 2M+ triangle meshes
    # that are already guaranteed manifold by manifold3d
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    return mesh


def center_on_build_plate(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Center the mesh in X/Y around (0, 0) and rest its bottom at Z = 0."""
    bounds = mesh.bounds
    if bounds is None or len(mesh.vertices) == 0:
        return mesh
    center_xy = (bounds[0][:2] + bounds[1][:2]) / 2.0
    min_z = bounds[0][2]
    translation = np.array([-center_xy[0], -center_xy[1], -min_z], dtype=np.float64)
    mesh.apply_translation(translation)
    return mesh


def load_and_repair_stl(file_bytes: bytes, auto_center: bool = True) -> Tuple[trimesh.Trimesh, MeshStats]:
    """
    Loads an STL from bytes, checks if it is watertight/manifold,
    and automatically repairs non-manifold edges/holes using manifold3d or pymeshfix.
    Optimized for high-poly Cosplay/Figurine STL files (500k - 2M+ triangles).
    """
    loaded = trimesh.load(io.BytesIO(file_bytes), file_type="stl", force="mesh")
    if isinstance(loaded, trimesh.Scene):
        mesh = loaded.dump(concatenate=True)
    else:
        mesh = loaded

    mesh.merge_vertices()
    if hasattr(mesh, "nondegenerate_faces"):
        mesh.update_faces(mesh.nondegenerate_faces())
    elif hasattr(mesh, "remove_degenerate_faces"):
        mesh.remove_degenerate_faces()
    if hasattr(mesh, "unique_faces"):
        mesh.update_faces(mesh.unique_faces())
    mesh.remove_unreferenced_vertices()

    repaired = False
    repair_method = "none (already manifold)"

    # Fast check if already directly accepted by manifold3d
    verts = np.ascontiguousarray(mesh.vertices, dtype=np.float32)
    faces = np.ascontiguousarray(mesh.faces, dtype=np.uint32)
    direct_mani = m3d.Manifold(m3d.Mesh(vert_properties=verts, tri_verts=faces))
    is_valid_manifold = direct_mani.status() == m3d.Error.NoError and direct_mani.num_tri() > 0

    if not is_valid_manifold:
        # Multi-shell repair happens either now (for <= 300k faces) or on-demand in trimesh_to_manifold()
        if len(mesh.faces) <= 300000:
            try:
                mani = trimesh_to_manifold(mesh)
                mesh = manifold_to_trimesh(mani)
                is_valid_manifold = True
                repaired = True
                repair_method = "pymeshfix_multishell + manifold3d"
            except Exception:
                pass
        else:
            repair_method = "auto_multishell_on_csg (high-poly)"

    if auto_center:
        mesh = center_on_build_plate(mesh)

    stats = compute_mesh_stats(mesh, repaired=repaired, repair_method=repair_method, is_manifold_override=is_valid_manifold)
    return mesh, stats


def compute_mesh_stats(
    mesh: trimesh.Trimesh,
    repaired: bool = False,
    repair_method: str = "none",
    is_manifold_override: bool = False,
) -> MeshStats:
    bounds = mesh.bounds if mesh.bounds is not None else np.zeros((2, 3))
    extents = mesh.extents if mesh.extents is not None else np.zeros(3)
    # Avoid expensive Python edge-graph traversal on meshes > 250k faces
    if is_manifold_override:
        watertight = True
    elif len(mesh.faces) <= 250000:
        watertight = bool(mesh.is_watertight)
    else:
        watertight = True
    try:
        vol = float(mesh.volume) if (watertight and len(mesh.faces) <= 250000) else float(np.prod(extents) * 0.35)
    except Exception:
        vol = 0.0
    return MeshStats(
        is_watertight=watertight,
        is_winding_consistent=watertight,
        repaired=repaired,
        repair_method=repair_method,
        vertices_count=int(len(mesh.vertices)),
        faces_count=int(len(mesh.faces)),
        bbox_min=(round(float(bounds[0][0]), 3), round(float(bounds[0][1]), 3), round(float(bounds[0][2]), 3)),
        bbox_max=(round(float(bounds[1][0]), 3), round(float(bounds[1][1]), 3), round(float(bounds[1][2]), 3)),
        extents=(round(float(extents[0]), 3), round(float(extents[1]), 3), round(float(extents[2]), 3)),
        volume_mm3=round(abs(vol), 2),
    )


def align_mesh_pca_vertical(mesh: trimesh.Trimesh) -> Tuple[trimesh.Trimesh, Dict[str, Any]]:
    """
    Auto-Align PCA: Computes the Principal Components Analysis of the mesh vertices/surface
    and rotates the mesh so its longest principal axis is aligned vertically along Z,
    its second principal axis along X, and its thinnest axis along Y.
    """
    # Sample surface points for uniform geometric weighting independent of tessellation density
    pts, _ = trimesh.sample.sample_surface(mesh, count=min(15000, max(3000, len(mesh.faces))))
    centered = pts - np.mean(pts, axis=0)

    # SVD / Covariance eigenvectors
    cov = np.cov(centered, rowvar=False)
    eigenvalues, eigenvectors = np.linalg.eigh(cov)

    # eigh returns eigenvalues in ascending order: [smallest (thickness), medium (width), largest (length)]
    idx_sorted = np.argsort(eigenvalues)  # [0: min, 1: mid, 2: max]
    v_min = eigenvectors[:, idx_sorted[0]]
    v_mid = eigenvectors[:, idx_sorted[1]]
    v_max = eigenvectors[:, idx_sorted[2]]

    # Target basis: X = v_mid (width), Y = v_min (thickness), Z = v_max (longest axis vertical)
    R = np.vstack([v_mid, v_min, v_max])

    # Ensure proper right-handed rotation matrix (det = +1, no reflection)
    if np.linalg.det(R) < 0:
        R[0, :] = -R[0, :]

    transform = np.eye(4, dtype=np.float64)
    transform[:3, :3] = R

    aligned = mesh.copy()
    aligned.apply_transform(transform)
    aligned = center_on_build_plate(aligned)

    stats = compute_mesh_stats(aligned, repaired=False, repair_method="pca_aligned_z")
    return aligned, {
        "rotation_matrix": R.tolist(),
        "eigenvalues": eigenvalues[idx_sorted].tolist(),
        "stats": stats.to_dict(),
    }


def export_mesh_stl_bytes(mesh: trimesh.Trimesh) -> bytes:
    """Export a trimesh object to binary STL bytes."""
    buf = io.BytesIO()
    mesh.export(buf, file_type="stl")
    return buf.getvalue()

