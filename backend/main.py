"""
MakerStudio 3D - Local Computational Geometry API Server (FastAPI)
Calibrated for Creality K1 Max (300x300x300 mm) & Creality Hi.
Module 1: Cosplay & Figurine Smart Slicer (trimesh + manifold3d + pymeshfix + scipy + shapely).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, Literal

import trimesh
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.mesh_repair import (
    load_and_repair_stl,
    align_mesh_pca_vertical,
    compute_mesh_stats,
    export_mesh_stl_bytes,
)
from core.cosplay_rod import (
    STANDARD_PROFILES,
    RodParameters,
    RodReport,
    compute_default_rod_endpoints,
    subtract_cosplay_rod,
)
from core.connectors import ConnectorConfig, ConnectorType
from core.smart_cutter import (
    PRINTER_PRESETS,
    BoundedCutParams,
    compute_auto_cut_planes_z,
    slice_auto_grid_cosplay,
    slice_bounded_figurine,
    package_parts_to_zip_bytes,
)
from modules_futurs import hueforge_tiler, lithophane_gen, puzzles_hash
from core import spool_library, license_manager


app = FastAPI(
    title="StudioForge 3D - Geometric Engine API",
    description="Moteur géométrique 3D local (trimesh + manifold3d + pymeshfix) pour HueForge Studio, Lumina 3D & SmartCut 3D.",
    version="1.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register future modular routers, Spool Library, Printer Fleet & License Manager
app.include_router(license_manager.router)
app.include_router(spool_library.router)
app.include_router(spool_library.printers_router)
app.include_router(hueforge_tiler.router)
app.include_router(lithophane_gen.router)
app.include_router(puzzles_hash.router)


@dataclass
class SessionModelState:
    session_id: str
    filename: str
    original_mesh: trimesh.Trimesh
    current_mesh: trimesh.Trimesh
    current_manifold: Optional[ Any ] = None
    has_rod_tunnel: bool = False
    last_rod_report: Optional[RodReport] = None
    last_zip_bytes: Optional[bytes] = None
    last_parts_metadata: List[Dict[str, Any]] = field(default_factory=list)


# In-memory store for active local studio sessions
SESSIONS: Dict[str, SessionModelState] = {}


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class RodRequest(BaseModel):
    profile_preset: Optional[str] = Field(
        default=None,
        description="Optional preset key from STANDARD_PROFILES (e.g. 'round_8', 'square_8x8', 'flat_10x2')",
    )
    profile_type: Literal["round", "square", "flat"] = "round"
    width: float = Field(default=8.0, gt=0.5, description="Diameter or width in mm")
    thickness: float = Field(default=8.0, gt=0.5, description="Thickness in mm (for flat profiles)")
    clearance: float = Field(default=0.30, ge=0.0, le=2.0, description="Print clearance in mm (+0.30 mm default)")
    margin_ends: float = Field(default=15.0, ge=0.0, description="Safety margin at both ends in mm")
    point_a: Optional[Tuple[float, float, float]] = None
    point_b: Optional[Tuple[float, float, float]] = None
    twist_angle_deg: float = 0.0


class SmartCutRequest(BaseModel):
    mode: Literal["auto_grid", "bounded_figurine"] = "auto_grid"
    printer_preset: Literal["k1_max", "creality_hi", "custom"] = "k1_max"
    max_build_size: float = Field(default=285.0, gt=20.0, description="Max segment height in mm (285 mm for K1 Max)")
    custom_z_planes: Optional[List[float]] = None

    # Optional on-the-fly rod subtraction before cutting if not already applied
    apply_rod_before_cut: bool = False
    rod_config: Optional[RodRequest] = None

    # Bounded cut parameters (Mode B - Figurine)
    plane_origin: Tuple[float, float, float] = (0.0, 0.0, 100.0)
    plane_normal: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    bound_type: Literal["box", "cylinder"] = "cylinder"
    bound_size: Tuple[float, float, float] = (80.0, 80.0, 80.0)

    # Geometric Connectors & 3D Numbering
    connector_type: ConnectorType = "hexagon_peg"
    female_clearance: float = Field(default=0.18, ge=0.0, le=1.0)
    draft_angle_deg: float = Field(default=2.0, ge=0.0, le=10.0)
    pin_height_half: float = Field(default=10.0, gt=2.0, le=40.0)
    base_size_mm: float = Field(default=10.0, gt=3.0, le=40.0)
    engrave_numbers: bool = True
    engrave_depth_mm: float = Field(default=0.8, gt=0.1, le=3.0)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/presets")
async def get_studio_presets():
    """Returns printer presets (Creality K1 Max / Creality Hi) and standard Brico rod profiles."""
    return {
        "printers": PRINTER_PRESETS,
        "rod_profiles": STANDARD_PROFILES,
    }


@app.post("/api/model/upload")
async def upload_and_repair_stl(file: UploadFile = File(...)):
    """
    1. Loads an uploaded `.STL` file.
    2. Detects if it is watertight/manifold and automatically repairs it (`pymeshfix` / `manifold3d`).
    3. Centers the mesh on the build plate (Z >= 0) and returns exact Bounding Box (X, Y, Z),
       default reinforcement rod endpoints (A -> B), and auto-cut preview planes for K1 Max (285 mm).
    """
    if not file.filename or not file.filename.lower().endswith(".stl"):
        raise HTTPException(status_code=400, detail="Veuillez fournir un fichier .STL valide.")

    raw_bytes = await file.read()
    if len(raw_bytes) == 0:
        raise HTTPException(status_code=400, detail="Le fichier STL est vide.")

    try:
        mesh, stats = load_and_repair_stl(raw_bytes, auto_center=True)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Erreur lors de la lecture/réparation du STL: {exc}") from exc

    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = SessionModelState(
        session_id=session_id,
        filename=file.filename,
        original_mesh=mesh.copy(),
        current_mesh=mesh,
    )

    pt_a, pt_b = compute_default_rod_endpoints(mesh, margin_ends=15.0)
    auto_planes_k1 = compute_auto_cut_planes_z(mesh, max_build_size=285.0)

    return {
        "session_id": session_id,
        "filename": file.filename,
        "stats": stats.to_dict(),
        "default_rod": {
            "point_a": [round(float(x), 2) for x in pt_a],
            "point_b": [round(float(x), 2) for x in pt_b],
            "rod_length_mm": round(float((pt_b[2] - pt_a[2])), 1),
        },
        "suggested_cut_planes_z": auto_planes_k1,
    }


@app.post("/api/model/load-local-path")
async def load_local_stl_path(payload: Dict[str, str]):
    """Loads an STL directly from a local path on disk for testing."""
    import pathlib
    raw_bytes = pathlib.Path(payload["path"]).read_bytes()
    mesh, stats = load_and_repair_stl(raw_bytes, auto_center=True)
    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = SessionModelState(
        session_id=session_id,
        filename=pathlib.Path(payload["path"]).name,
        original_mesh=mesh.copy(),
        current_mesh=mesh,
    )
    pt_a, pt_b = compute_default_rod_endpoints(mesh, margin_ends=15.0)
    return {
        "session_id": session_id,
        "filename": pathlib.Path(payload["path"]).name,
        "stats": stats.to_dict(),
        "default_rod": {
            "point_a": [round(float(x), 2) for x in pt_a],
            "point_b": [round(float(x), 2) for x in pt_b],
            "rod_length_mm": round(float(pt_b[2] - pt_a[2]), 1),
        },
        "suggested_cut_planes_z": compute_auto_cut_planes_z(mesh, max_build_size=285.0),
    }


@app.post("/api/model/demo/generate-demo-sword")
async def generate_demo_cosplay_sword():
    """
    Helper endpoint to generate a procedural 850 mm Cosplay Sword STL directly in memory
    so the user can test PCA alignment, 1m Rod Tunneling, and K1 Max Smart Slicing immediately.
    """
    import manifold3d as m3d
    from core.mesh_repair import manifold_to_trimesh, center_on_build_plate

    # Pommel + Grip + Crossguard + Blade (total height = 820 mm > 300 mm K1 Max)
    pommel = m3d.Manifold.sphere(radius=22.0, circular_segments=32).translate([0.0, 0.0, 22.0])
    grip = m3d.Manifold.cylinder(height=140.0, radius_low=14.0, radius_high=16.0, circular_segments=32).translate([0.0, 0.0, 35.0])
    guard = m3d.Manifold.cube([160.0, 28.0, 24.0], center=True).translate([0.0, 0.0, 182.0])
    blade_lower = m3d.Manifold.cylinder(height=500.0, radius_low=28.0, radius_high=20.0, circular_segments=4). scale([1.0, 0.32, 1.0]).translate([0.0, 0.0, 190.0])
    blade_tip = m3d.Manifold.cylinder(height=130.0, radius_low=20.0, radius_high=1.5, circular_segments=4).scale([1.0, 0.32, 1.0]).translate([0.0, 0.0, 690.0])

    sword_mani = pommel + grip + guard + blade_lower + blade_tip
    # Intentionally tilt the sword by 35 degrees to showcase the "Auto-Align PCA" button!
    sword_mani = sword_mani.rotate([25.0, 30.0, 10.0])
    mesh = center_on_build_plate(manifold_to_trimesh(sword_mani))

    session_id = str(uuid.uuid4())
    stats = compute_mesh_stats(mesh, repaired=False, repair_method="procedural_manifold")
    SESSIONS[session_id] = SessionModelState(
        session_id=session_id,
        filename="Epée_Cosplay_Demo_820mm.stl",
        original_mesh=mesh.copy(),
        current_mesh=mesh,
    )
    pt_a, pt_b = compute_default_rod_endpoints(mesh, margin_ends=15.0)
    auto_planes = compute_auto_cut_planes_z(mesh, max_build_size=285.0)

    return {
        "session_id": session_id,
        "filename": "Epée_Cosplay_Demo_820mm.stl",
        "stats": stats.to_dict(),
        "default_rod": {
            "point_a": [round(float(x), 2) for x in pt_a],
            "point_b": [round(float(x), 2) for x in pt_b],
            "rod_length_mm": round(float(pt_b[2] - pt_a[2]), 1),
        },
        "suggested_cut_planes_z": auto_planes,
    }


@app.get("/api/model/{session_id}/stl")
async def get_current_model_stl(session_id: str):
    """Returns the current binary `.STL` of the session for Three.js visualization."""
    state = _get_session(session_id)
    stl_bytes = export_mesh_stl_bytes(state.current_mesh)
    return Response(
        content=stl_bytes,
        media_type="application/sla",
        headers={"Content-Disposition": f'inline; filename="{state.filename}"'},
    )


@app.post("/api/model/{session_id}/align-pca")
async def align_model_pca(session_id: str):
    """
    Auto-Align PCA: Aligns the longest principal inertia axis of the 3D object vertically along Z
    and re-centers it on the build plate.
    """
    state = _get_session(session_id)
    aligned_mesh, pca_info = align_mesh_pca_vertical(state.current_mesh)
    state.current_mesh = aligned_mesh
    state.current_manifold = None
    state.has_rod_tunnel = False

    pt_a, pt_b = compute_default_rod_endpoints(aligned_mesh, margin_ends=15.0)
    auto_planes_k1 = compute_auto_cut_planes_z(aligned_mesh, max_build_size=285.0)

    return {
        "session_id": session_id,
        "pca": pca_info,
        "stats": pca_info["stats"],
        "default_rod": {
            "point_a": [round(float(x), 2) for x in pt_a],
            "point_b": [round(float(x), 2) for x in pt_b],
            "rod_length_mm": round(float(pt_b[2] - pt_a[2]), 1),
        },
        "suggested_cut_planes_z": auto_planes_k1,
    }


@app.post("/api/model/{session_id}/reset")
async def reset_model_to_original(session_id: str):
    """Resets the mesh to its freshly repaired import state."""
    state = _get_session(session_id)
    state.current_mesh = state.original_mesh.copy()
    state.current_manifold = None
    state.has_rod_tunnel = False
    state.last_rod_report = None
    stats = compute_mesh_stats(state.current_mesh)
    pt_a, pt_b = compute_default_rod_endpoints(state.current_mesh, margin_ends=15.0)
    return {
        "session_id": session_id,
        "stats": stats.to_dict(),
        "default_rod": {
            "point_a": [round(float(x), 2) for x in pt_a],
            "point_b": [round(float(x), 2) for x in pt_b],
            "rod_length_mm": round(float(pt_b[2] - pt_a[2]), 1),
        },
        "suggested_cut_planes_z": compute_auto_cut_planes_z(state.current_mesh, max_build_size=285.0),
    }


@app.post("/api/model/{session_id}/rod-tunnel")
async def apply_cosplay_rod_tunnel(session_id: str, req: RodRequest):
    """
    Subtracts a cosplay reinforcement rod tunnel (`round`, `square`, or `flat`) along `Point A -> Point B`
    with customizable print clearance (`+0.30 mm` default) using `manifold3d`.
    Returns the exact length in mm to cut on a 1-meter hardware store bar.
    """
    state = _get_session(session_id)
    params = _resolve_rod_parameters(req)

    try:
        hollowed_mesh, _, report, result_mani = subtract_cosplay_rod(
            state.current_mesh, params, base_mani=state.current_manifold
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Erreur lors du perçage de la tige: {exc}") from exc

    state.current_mesh = hollowed_mesh
    state.current_manifold = result_mani
    state.has_rod_tunnel = True
    state.last_rod_report = report
    stats = compute_mesh_stats(hollowed_mesh, is_manifold_override=True)

    return {
        "session_id": session_id,
        "rod_report": report.to_dict(),
        "stats": stats.to_dict(),
    }


@app.post("/api/model/{session_id}/smart-cut")
async def execute_smart_cut(session_id: str, req: SmartCutRequest):
    """
    Executes either:
    - Mode A (`auto_grid`): Auto-Grid Cosplay Slicer (`max_build_size = 285 mm` for K1 Max)
    - Mode B (`bounded_figurine`): Localized Bounded Cut (Box or Cylinder) for figurine limbs/heads
    Adds conical Hexagonal/Square tenons (2° draft angle, +0.18 mm female clearance) and
    engraves 3D part numbers (`1`, `2`, `3`...) recessed by `0.8 mm` on each cut face.
    Stores the ready-to-print `.ZIP` archive for immediate download.
    """
    state = _get_session(session_id)
    work_mesh = state.current_mesh.copy()
    rod_report = state.last_rod_report

    # Optional on-the-fly rod subtraction if requested in a single step
    if req.apply_rod_before_cut and req.rod_config is not None and not state.has_rod_tunnel:
        rod_params = _resolve_rod_parameters(req.rod_config)
        work_mesh, _, rod_report, result_mani = subtract_cosplay_rod(
            work_mesh, rod_params, base_mani=state.current_manifold
        )
        state.current_mesh = work_mesh
        state.current_manifold = result_mani
        state.has_rod_tunnel = True
        state.last_rod_report = rod_report

    conn_cfg = ConnectorConfig(
        connector_type=req.connector_type,
        female_clearance=req.female_clearance,
        draft_angle_deg=req.draft_angle_deg,
        pin_height_half=req.pin_height_half,
        base_size_mm=req.base_size_mm,
        engrave_numbers=req.engrave_numbers,
        engrave_depth_mm=req.engrave_depth_mm,
    )

    try:
        if req.mode == "auto_grid":
            parts, metadata, used_planes = slice_auto_grid_cosplay(
                mesh=work_mesh,
                max_build_size=req.max_build_size,
                custom_z_planes=req.custom_z_planes,
                connector_config=conn_cfg,
                has_cosplay_rod=state.has_rod_tunnel,
                base_mani=state.current_manifold,
            )
        else:
            b_params = BoundedCutParams(
                plane_origin=req.plane_origin,
                plane_normal=req.plane_normal,
                bound_type=req.bound_type,
                bound_size=req.bound_size,
            )
            parts, metadata = slice_bounded_figurine(
                mesh=work_mesh,
                bounded_params=b_params,
                connector_config=conn_cfg,
            )
            used_planes = [req.plane_origin[2]]
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Erreur lors de la découpe booléenne: {exc}") from exc

    # Build assembly summary report inside the ZIP
    lines = [
        "==========================================================",
        "  MAKERSTUDIO 3D - FICHE D'ASSEMBLAGE & DECOUPE (K1 MAX)  ",
        "==========================================================",
        f"Fichier source : {state.filename}",
        f"Mode de découpe : {req.mode}",
        f"Nombre de fichiers STL générés : {len(parts)}",
        f"Connecteurs géométriques : {req.connector_type} (Tolérance femelle: +{req.female_clearance} mm, Dépouille: {req.draft_angle_deg}°)",
        f"Numérotation 3D gravée : {'Oui (-' + str(req.engrave_depth_mm) + ' mm)' if req.engrave_numbers else 'Non'}",
        "",
    ]
    if rod_report is not None:
        lines.extend([
            "--- TIGE DE RENFORT COSPLAY (BRICO) ---",
            f"Profilé : {rod_report.profile_type.upper()} {rod_report.nominal_dimensions_mm[0]}x{rod_report.nominal_dimensions_mm[1]} mm",
            f"Dimensions du canal imprimé (avec jeu +{rod_report.clearance_mm} mm) : {rod_report.cutout_dimensions_mm[0]}x{rod_report.cutout_dimensions_mm[1]} mm",
            f"Longueur totale du canal interne : {rod_report.rod_length_mm} mm",
            f">>> LONGUEUR EXACTE À COUPER SUR VOTRE BARRE DE 1M : {rod_report.recommended_cut_length_mm} mm <<<",
            f"Barres de 1 mètre nécessaires : {rod_report.bars_1m_needed} (Chute restante : {rod_report.remaining_on_1m_bar_mm} mm)",
            "",
        ])
    lines.append("--- LISTE DES PIÈCES STL ---")
    for m in metadata:
        lines.append(
            f"  [{m.part_index}] {m.filename} | Dimensions: {m.extents_mm[0]} x {m.extents_mm[1]} x {m.extents_mm[2]} mm | Faces: {m.faces_count}"
        )

    zip_bytes = package_parts_to_zip_bytes(parts, extra_report_txt="\n".join(lines))
    state.last_zip_bytes = zip_bytes
    state.last_parts_metadata = [m.to_dict() for m in metadata]

    return {
        "session_id": session_id,
        "mode": req.mode,
        "parts_count": len(parts),
        "cut_planes_z": used_planes,
        "parts": state.last_parts_metadata,
        "rod_report": rod_report.to_dict() if rod_report else None,
        "download_zip_url": f"/api/model/{session_id}/download-zip",
    }


@app.get("/api/model/{session_id}/download-zip")
async def download_sliced_zip(session_id: str):
    """Downloads the `.ZIP` archive containing all numbered `.STL` segments, pegs, and the assembly guide."""
    state = _get_session(session_id)
    if not state.last_zip_bytes:
        raise HTTPException(status_code=404, detail="Aucune découpe n'a encore été générée pour cette session.")

    base_name = state.filename.rsplit(".", 1)[0]
    zip_filename = f"{base_name}_MakerStudio3D_ReadyToSlice.zip"
    return Response(
        content=state.last_zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_session(session_id: str) -> SessionModelState:
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' introuvable ou expirée.")
    return SESSIONS[session_id]


def _resolve_rod_parameters(req: RodRequest) -> RodParameters:
    profile_type = req.profile_type
    width = req.width
    thickness = req.thickness

    if req.profile_preset and req.profile_preset in STANDARD_PROFILES:
        preset = STANDARD_PROFILES[req.profile_preset]
        profile_type = preset["type"]
        width = preset["width"]
        thickness = preset["thickness"]

    return RodParameters(
        profile_type=profile_type,
        width=width,
        thickness=thickness,
        clearance=req.clearance,
        margin_ends=req.margin_ends,
        point_a=req.point_a,
        point_b=req.point_b,
        twist_angle_deg=req.twist_angle_deg,
    )


# ---------------------------------------------------------------------------
# Standalone .EXE Static Frontend Hosting (Serves `frontend/dist` on Port 8000)
# ---------------------------------------------------------------------------
import pathlib as _pathlib
import sys as _sys
from fastapi.staticfiles import StaticFiles

_FRONTEND_DIST_CANDIDATES = [
    _pathlib.Path(getattr(_sys, "_MEIPASS", "")) / "frontend_dist" if getattr(_sys, "frozen", False) else None,
    _pathlib.Path(_sys.executable).resolve().parent / "frontend_dist" if getattr(_sys, "frozen", False) else None,
    _pathlib.Path(__file__).resolve().parent.parent / "frontend" / "dist",
]
for _cand in _FRONTEND_DIST_CANDIDATES:
    if _cand is not None and (_cand / "index.html").exists():
        app.mount("/", StaticFiles(directory=str(_cand), html=True), name="frontend_static")
        break


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
