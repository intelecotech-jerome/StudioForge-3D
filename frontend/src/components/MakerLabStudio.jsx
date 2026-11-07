import React, { useState, useEffect, useRef } from 'react';
import Viewer3D from './Viewer3D';

const API_BASE = 'http://127.0.0.1:8000';

const MAKER_TOOLS = [
  {
    id: 'cookie_cutter',
    icon: '🍪',
    title: 'Emporte-Pièce & Tampon',
    desc: 'Lame tranchante biseautée + Rebord ergonomique + Tampon embosseur à poignée',
    defaultPreset: 'cat',
    defaultSize: 95,
    defaultHeight: 14,
  },
  {
    id: 'pop_box',
    icon: '📦',
    title: 'Boîte 3D & Couvercle Relief',
    desc: 'Corps de boîte creux + Couvercle emboîtable sculpté en relief multi-niveaux',
    defaultPreset: 'shield',
    defaultSize: 120,
    defaultHeight: 34,
  },
  {
    id: 'flexi_toy',
    icon: '🐟',
    title: 'Flexi Articulé Print-in-Place',
    desc: 'Découpe articulée zig-zag + Charnières internes mobiles imprimées en 1 bloc',
    defaultPreset: 'fish',
    defaultSize: 135,
    defaultHeight: 7,
  },
  {
    id: 'layering_mandala',
    icon: '🌸',
    title: 'Mandala & Relief Multi-Couches',
    desc: 'Superpose une photo ou un dessin en 3 à 6 paliers 3D terrassés (Style Laser/Bois)',
    defaultPreset: 'mandala',
    defaultSize: 140,
    defaultHeight: 6,
  },
  {
    id: 'lenticular_dual',
    icon: '🪞',
    title: 'Illusion Lenticulaire 2-Angles',
    desc: 'Fusionne 2 Photos ou 2 Textes visibles à -45° (Gauche) et +45° (Droite)',
    defaultPreset: 'heart',
    defaultSize: 130,
    defaultHeight: 10,
  },
  {
    id: 'morphing_90',
    icon: '🔄',
    title: 'Morphing 3D Dual-90°',
    desc: 'Intersection 3D CSG à 90° de 2 Textes (ex: LOVE / 2026) ou 2 Silhouettes',
    defaultPreset: 'heart',
    defaultSize: 85,
    defaultHeight: 85,
  },
  {
    id: 'stl_bas_relief',
    icon: '🗿',
    title: 'Mesh .STL ➔ Bas-Relief',
    desc: 'Compresse un objet 3D (.STL) en tableau Bas-Relief encadré (Style Photo 1)',
    defaultPreset: 'cat',
    defaultSize: 135,
    defaultHeight: 9,
  },
  {
    id: 'ai_mesh_3d',
    icon: '🤖',
    title: 'IA Photo/Texte ➔ 3D (Meshy)',
    desc: 'Sculpte une Figurine 3D 360° depuis une Photo ou un Texte (+ envoi HueForge Pop-Out)',
    defaultPreset: 'cat',
    defaultSize: 110,
    defaultHeight: 38,
  },
];

const PRESET_SHAPES = [
  { id: 'cat', label: '🐱 Chat' },
  { id: 'fish', label: '🐟 Poisson' },
  { id: 'mandala', label: '🌸 Mandala' },
  { id: 'shield', label: '🛡️ Hero Logo' },
  { id: 'heart', label: '❤️ Cœur' },
];

export default function MakerLabStudio({ bedSize = [300, 300, 300], isVisible = true, onOpenHueForge }) {
  const fileARef = useRef(null);
  const fileBRef = useRef(null);
  const stlInputRef = useRef(null);

  const [sessionId, setSessionId] = useState(null);
  const [toolId, setToolId] = useState('cookie_cutter');
  const [presetShape, setPresetShape] = useState('cat');

  const [targetSizeMm, setTargetSizeMm] = useState(95);
  const [heightZMm, setHeightZMm] = useState(14);
  const [wallThicknessMm, setWallThicknessMm] = useState(1.6);
  const [clearanceMm, setClearanceMm] = useState(0.25);
  const [detailLevel, setDetailLevel] = useState(1.0);
  const [removeBgAuto, setRemoveBgAuto] = useState(true);
  const [invertMask, setInvertMask] = useState(false);

  // Tool-specific states
  const [includeStamp, setIncludeStamp] = useState(true);
  const [boxLidReliefMm, setBoxLidReliefMm] = useState(2.4);
  const [flexiSegments, setFlexiSegments] = useState(5);
  const [flexiZigzag, setFlexiZigzag] = useState(true);
  const [layerCount, setLayerCount] = useState(4);
  const [layerFrame, setLayerFrame] = useState('octagon');

  // Dual / Text inputs
  const [useTextMode, setUseTextMode] = useState(false);
  const [textA, setTextA] = useState('LOVE');
  const [textB, setTextB] = useState('2026');

  // Tool #7 (STL -> Bas-Relief) & Tool #8 (AI 3D Sculptor style Meshy.ai)
  const [stlPreset, setStlPreset] = useState('rubber_duck');
  const [uploadedStlName, setUploadedStlName] = useState(null);
  const [stlYawDeg, setStlYawDeg] = useState(0);
  const [stlPitchDeg, setStlPitchDeg] = useState(0);
  const [reliefFrameStyle, setReliefFrameStyle] = useState('beveled_frame');
  const [aiEngine, setAiEngine] = useState('local_organic_3d');
  const [aiPrompt, setAiPrompt] = useState('DRAGON 3D');
  const [meshyApiKey, setMeshyApiKey] = useState('');
  const [aiAddPedestal, setAiAddPedestal] = useState(true);
  const [transferMsg, setTransferMsg] = useState(null);

  // Previews & 3D outputs
  const [sourceAUrl, setSourceAUrl] = useState(null);
  const [sourceBUrl, setSourceBUrl] = useState(null);
  const [preview2dUrl, setPreview2dUrl] = useState(null);
  const [assemblyStlUrl, setAssemblyStlUrl] = useState(null);
  const [activeStlUrl, setActiveStlUrl] = useState(null);
  const [activePartIdx, setActivePartIdx] = useState(0);
  const [partsMeta, setPartsMeta] = useState([]);
  const [zipDownloadUrl, setZipDownloadUrl] = useState(null);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [stlTick, setStlTick] = useState(0);

  const buildPayload = (overrides = {}) => ({
    tool_id: overrides.toolId ?? toolId,
    target_size_mm: Number(overrides.targetSizeMm ?? targetSizeMm),
    height_z_mm: Number(overrides.heightZMm ?? heightZMm),
    wall_thickness_mm: Number(overrides.wallThicknessMm ?? wallThicknessMm),
    clearance_mm: Number(overrides.clearanceMm ?? clearanceMm),
    detail_level: Number(overrides.detailLevel ?? detailLevel),
    remove_bg_auto: overrides.removeBgAuto ?? removeBgAuto,
    invert_mask: overrides.invertMask ?? invertMask,
    include_stamp: overrides.includeStamp ?? includeStamp,
    box_lid_relief_mm: Number(overrides.boxLidReliefMm ?? boxLidReliefMm),
    flexi_segments: Number(overrides.flexiSegments ?? flexiSegments),
    flexi_zigzag: overrides.flexiZigzag ?? flexiZigzag,
    layer_count: Number(overrides.layerCount ?? layerCount),
    layer_frame: overrides.layerFrame ?? layerFrame,
    use_text_mode: overrides.useTextMode ?? useTextMode,
    text_a: overrides.textA ?? textA,
    text_b: overrides.textB ?? textB,
    preset_shape: overrides.presetShape ?? presetShape,
    stl_preset: overrides.stlPreset ?? stlPreset,
    stl_yaw_deg: Number(overrides.stlYawDeg ?? stlYawDeg),
    stl_pitch_deg: Number(overrides.stlPitchDeg ?? stlPitchDeg),
    relief_frame_style: overrides.reliefFrameStyle ?? reliefFrameStyle,
    ai_engine: overrides.aiEngine ?? aiEngine,
    ai_prompt: overrides.aiPrompt ?? aiPrompt,
    meshy_api_key: overrides.meshyApiKey ?? meshyApiKey,
    ai_add_pedestal: overrides.aiAddPedestal ?? aiAddPedestal,
  });

  const applyResult = (data) => {
    const tick = Date.now();
    setSessionId(data.session_id);
    if (data.source_a_data_url) setSourceAUrl(data.source_a_data_url);
    setPreview2dUrl(data.preview_2d_data_url);
    const fullUrl = `${API_BASE}${data.assembly_stl_url}?t=${tick}`;
    setAssemblyStlUrl(fullUrl);
    setActiveStlUrl(fullUrl);
    setActivePartIdx(0);
    setPartsMeta(data.parts || []);
    setZipDownloadUrl(`${API_BASE}${data.zip_download_url}`);
    setStats(data.stats);
    setStlTick(tick);
  };

  const handleInitPreset = async (overrides = {}) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/makerlab/init-preset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildPayload(overrides)),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Erreur initialisation MakerLab');
      applyResult(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isVisible && !sessionId && !loading) {
      handleInitPreset({ toolId: 'cookie_cutter', presetShape: 'cat' });
    }
  }, [isVisible]);

  const handleGenerate = async (overrides = {}) => {
    if (!sessionId) {
      return handleInitPreset(overrides);
    }
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/makerlab/${sessionId}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildPayload(overrides)),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Erreur génération MakerLab 3D');
      applyResult(data);
    } catch (e) {
      alert(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectTool = (tool) => {
    setToolId(tool.id);
    setTargetSizeMm(tool.defaultSize);
    setHeightZMm(tool.defaultHeight);
    const nextTextMode = tool.id === 'morphing_90';
    setUseTextMode(nextTextMode);
    handleGenerate({
      toolId: tool.id,
      targetSizeMm: tool.defaultSize,
      heightZMm: tool.defaultHeight,
      useTextMode: nextTextMode,
    });
  };

  const handleUploadImage = async (file, slot = 'a') => {
    setLoading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const url =
        slot === 'b'
          ? `${API_BASE}/api/makerlab/upload-b${sessionId ? `?session_id=${sessionId}` : ''}`
          : `${API_BASE}/api/makerlab/upload-a${sessionId ? `?session_id=${sessionId}` : ''}`;
      const res = await fetch(url, { method: 'POST', body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Erreur upload image');
      setSessionId(data.session_id);
      if (data.source_a_data_url) setSourceAUrl(data.source_a_data_url);
      if (data.source_b_data_url) setSourceBUrl(data.source_b_data_url);

      // Immediately generate the 3D object with the newly uploaded photo
      const resGen = await fetch(`${API_BASE}/api/makerlab/${data.session_id}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildPayload({ useTextMode: false })),
      });
      const genData = await resGen.json();
      if (resGen.ok) {
        setUseTextMode(false);
        applyResult(genData);
      }
    } catch (e) {
      alert(e.message);
    } finally {
      setLoading(false);
    }
  };

  const isDualTool = toolId === 'lenticular_dual' || toolId === 'morphing_90';

  return (
    <div className="app-layout" style={{ height: 'calc(100vh - 48px)' }}>
      {/* LEFT SIDEBAR: MAKERLAB 3D CONTROLS */}
      <aside className="sidebar" style={{ height: 'calc(100vh - 48px)', width: '440px', minWidth: '440px' }}>
        <div className="sidebar-scroll">
          {/* SECTION 1: CHOOSE MAKERLAB GENERATOR */}
          <section className="panel-card">
            <div className="panel-title">1. CHOIX DU GÉNÉRATEUR MAKERLAB 3D</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px' }}>
              {MAKER_TOOLS.map((t) => {
                const active = toolId === t.id;
                return (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => handleSelectTool(t)}
                    style={{
                      textAlign: 'left',
                      padding: '8px 9px',
                      borderRadius: '8px',
                      border: active ? '1px solid #00f0ff' : '1px solid #1e293b',
                      background: active ? 'rgba(0, 240, 255, 0.14)' : 'rgba(15, 23, 42, 0.72)',
                      color: '#f8fafc',
                      cursor: 'pointer',
                    }}
                  >
                    <div style={{ fontSize: '0.76rem', fontWeight: 800, color: active ? '#00f0ff' : '#f1f5f9' }}>
                      {t.icon} {t.title}
                    </div>
                    <div style={{ fontSize: '0.63rem', color: '#94a3b8', marginTop: '3px', lineHeight: 1.25 }}>
                      {t.desc}
                    </div>
                  </button>
                );
              })}
            </div>
          </section>

          {/* SECTION 2: SOURCE IMAGE(S), PRESETS OR DUAL TEXT */}
          <section className="panel-card">
            <div className="panel-title">2. IMAGE SOURCE, MODÈLE TEST OU TEXTE 3D</div>

            {/* Quick 1-Click Built-in Presets */}
            <label className="field-label">Modèles de Démonstration Instantanés (1-Clic) :</label>
            <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', marginBottom: '8px' }}>
              {PRESET_SHAPES.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  className={`btn-hud ${presetShape === p.id && !useTextMode ? 'active' : ''}`}
                  style={{ flex: 1, fontSize: '0.67rem', padding: '4px 6px' }}
                  onClick={() => {
                    setPresetShape(p.id);
                    setUseTextMode(false);
                    handleInitPreset({ presetShape: p.id, useTextMode: false });
                  }}
                >
                  {p.label}
                </button>
              ))}
            </div>

            {/* Upload Image A */}
            <input
              ref={fileARef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              style={{ display: 'none' }}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleUploadImage(f, 'a');
                e.target.value = '';
              }}
            />
            <button
              type="button"
              className="btn-cyber primary-full"
              disabled={loading}
              onClick={() => fileARef.current?.click()}
            >
              📷 Importer ma Photo / Silhouette / Logo (.PNG / .JPG)
            </button>

            {/* Dual Mode Controls (Lenticular & Morphing 90°) */}
            {isDualTool && (
              <div
                style={{
                  marginTop: '10px',
                  padding: '9px 10px',
                  borderRadius: '8px',
                  background: 'rgba(0, 240, 255, 0.06)',
                  border: '1px solid rgba(0, 240, 255, 0.28)',
                }}
              >
                <div className="btn-row" style={{ marginBottom: '8px' }}>
                  <button
                    type="button"
                    className={`btn-hud ${!useTextMode ? 'active' : ''}`}
                    style={{ flex: 1, fontSize: '0.7rem' }}
                    onClick={() => {
                      setUseTextMode(false);
                      handleGenerate({ useTextMode: false });
                    }}
                  >
                    🖼️ Mode 2 Photos / Silhouettes
                  </button>
                  <button
                    type="button"
                    className={`btn-hud ${useTextMode ? 'active' : ''}`}
                    style={{ flex: 1, fontSize: '0.7rem' }}
                    onClick={() => {
                      setUseTextMode(true);
                      handleGenerate({ useTextMode: true });
                    }}
                  >
                    🔤 Mode 2 Textes (A ↔ B)
                  </button>
                </div>

                {useTextMode ? (
                  <div className="grid-2col">
                    <div>
                      <label className="field-label">Texte Vue A (-45° / Face) :</label>
                      <input
                        type="text"
                        className="cyber-input"
                        value={textA}
                        onChange={(e) => setTextA(e.target.value.toUpperCase())}
                        placeholder="Ex: LOVE"
                      />
                    </div>
                    <div>
                      <label className="field-label">Texte Vue B (+45° / 90°) :</label>
                      <input
                        type="text"
                        className="cyber-input"
                        value={textB}
                        onChange={(e) => setTextB(e.target.value.toUpperCase())}
                        placeholder="Ex: 2026"
                      />
                    </div>
                  </div>
                ) : (
                  <div>
                    <input
                      ref={fileBRef}
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
                      style={{ display: 'none' }}
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) handleUploadImage(f, 'b');
                        e.target.value = '';
                      }}
                    />
                    <button
                      type="button"
                      className="btn-cyber secondary"
                      style={{ width: '100%' }}
                      onClick={() => fileBRef.current?.click()}
                    >
                      ➕ Importer la 2ème Photo / Silhouette (Angle B)
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* 2D Source & Structural Map Preview */}
            {(sourceAUrl || preview2dUrl) && (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginTop: '10px' }}>
                {sourceAUrl && (
                  <div
                    style={{
                      background: '#090d16',
                      border: '1px solid #1e293b',
                      borderRadius: '7px',
                      padding: '5px',
                      textAlign: 'center',
                    }}
                  >
                    <div style={{ fontSize: '0.64rem', color: '#94a3b8', marginBottom: '3px' }}>Image / Forme Source</div>
                    <img
                      src={sourceAUrl}
                      alt="Source"
                      style={{ maxHeight: '105px', maxWidth: '100%', objectFit: 'contain', borderRadius: '4px' }}
                    />
                  </div>
                )}
                {preview2dUrl && (
                  <div
                    style={{
                      background: '#090d16',
                      border: '1px solid rgba(0, 240, 255, 0.35)',
                      borderRadius: '7px',
                      padding: '5px',
                      textAlign: 'center',
                    }}
                  >
                    <div style={{ fontSize: '0.64rem', color: '#00f0ff', marginBottom: '3px' }}>
                      Topologie &amp; Découpe 2D
                    </div>
                    <img
                      src={preview2dUrl}
                      alt="Preview 2D"
                      style={{ maxHeight: '105px', maxWidth: '100%', objectFit: 'contain', borderRadius: '4px' }}
                    />
                  </div>
                )}
              </div>
            )}
          </section>

          {/* SECTION 3: GEOMETRIC & MECHANICAL PARAMETERS */}
          <section className="panel-card">
            <div className="panel-title">3. PARAMÈTRES GÉOMÉTRIQUES &amp; MÉCANIQUES</div>

            <div className="grid-2col">
              <div>
                <label className="field-label">
                  Envergure XY : <strong className="text-cyan">{targetSizeMm} mm</strong>
                </label>
                <input
                  type="range"
                  min="45"
                  max="250"
                  step="5"
                  value={targetSizeMm}
                  onChange={(e) => setTargetSizeMm(parseFloat(e.target.value))}
                  style={{ width: '100%', accentColor: '#00f0ff' }}
                />
              </div>
              <div>
                <label className="field-label">
                  Hauteur Z : <strong className="text-cyan">{heightZMm} mm</strong>
                </label>
                <input
                  type="range"
                  min="4"
                  max="80"
                  step="1"
                  value={heightZMm}
                  onChange={(e) => setHeightZMm(parseFloat(e.target.value))}
                  style={{ width: '100%', accentColor: '#00f0ff' }}
                />
              </div>
            </div>

            {toolId === 'cookie_cutter' && (
              <div style={{ marginTop: '6px' }}>
                <label className="switch-label">
                  <input
                    type="checkbox"
                    checked={includeStamp}
                    onChange={(e) => setIncludeStamp(e.target.checked)}
                  />
                  <span>💮 Générer aussi le Tampon Embosseur assorti avec poignée</span>
                </label>
                <label className="field-label" style={{ marginTop: '6px' }}>
                  Épaisseur Paroi / Lame : <strong className="text-cyan">{wallThicknessMm.toFixed(1)} mm</strong>
                </label>
                <input
                  type="range"
                  min="1.0"
                  max="3.0"
                  step="0.2"
                  value={wallThicknessMm}
                  onChange={(e) => setWallThicknessMm(parseFloat(e.target.value))}
                  style={{ width: '100%', accentColor: '#f97316' }}
                />
              </div>
            )}

            {toolId === 'pop_box' && (
              <div className="grid-2col" style={{ marginTop: '6px' }}>
                <div>
                  <label className="field-label">
                    Paroi Boîte : <strong className="text-cyan">{wallThicknessMm.toFixed(1)} mm</strong>
                  </label>
                  <input
                    type="range"
                    min="1.6"
                    max="4.0"
                    step="0.2"
                    value={wallThicknessMm}
                    onChange={(e) => setWallThicknessMm(parseFloat(e.target.value))}
                    style={{ width: '100%', accentColor: '#00f0ff' }}
                  />
                </div>
                <div>
                  <label className="field-label">
                    Relief Couvercle : <strong className="text-cyan">{boxLidReliefMm.toFixed(1)} mm</strong>
                  </label>
                  <input
                    type="range"
                    min="1.0"
                    max="5.0"
                    step="0.2"
                    value={boxLidReliefMm}
                    onChange={(e) => setBoxLidReliefMm(parseFloat(e.target.value))}
                    style={{ width: '100%', accentColor: '#f43f5e' }}
                  />
                </div>
              </div>
            )}

            {toolId === 'flexi_toy' && (
              <div style={{ marginTop: '6px' }}>
                <label className="field-label">
                  Nombre de Segments Articulés : <strong className="text-cyan">{flexiSegments} segments</strong>
                </label>
                <input
                  type="range"
                  min="3"
                  max="8"
                  step="1"
                  value={flexiSegments}
                  onChange={(e) => setFlexiSegments(parseInt(e.target.value, 10))}
                  style={{ width: '100%', accentColor: '#eab308' }}
                />
                <label className="switch-label" style={{ marginTop: '4px' }}>
                  <input
                    type="checkbox"
                    checked={flexiZigzag}
                    onChange={(e) => setFlexiZigzag(e.target.checked)}
                  />
                  <span>⚡ Découpes Articulées en Zig-Zag + Charnières Print-in-Place</span>
                </label>
              </div>
            )}

            {toolId === 'layering_mandala' && (
              <div className="grid-2col" style={{ marginTop: '6px' }}>
                <div>
                  <label className="field-label">
                    Nb Couches 3D : <strong className="text-cyan">{layerCount} paliers</strong>
                  </label>
                  <input
                    type="range"
                    min="2"
                    max="6"
                    step="1"
                    value={layerCount}
                    onChange={(e) => setLayerCount(parseInt(e.target.value, 10))}
                    style={{ width: '100%', accentColor: '#f59e0b' }}
                  />
                </div>
                <div>
                  <label className="field-label">Socle / Plaque de Fond :</label>
                  <select
                    className="cyber-input"
                    value={layerFrame}
                    onChange={(e) => setLayerFrame(e.target.value)}
                  >
                    <option value="octagon">🛑 Octogone (Style Photo)</option>
                    <option value="circle">⭕ Médaillon Rond</option>
                    <option value="rounded_rect">▭ Plaque Carrée</option>
                    <option value="none">✂️ Détouré Silhouette</option>
                  </select>
                </div>
              </div>
            )}

            {toolId === 'stl_bas_relief' && (
              <div style={{ marginTop: '8px' }}>
                <label className="field-label">Modèle 3D (.STL) à projeter en Bas-Relief :</label>
                <div className="btn-row" style={{ gap: '4px', marginBottom: '6px', flexWrap: 'wrap' }}>
                  {[
                    { id: 'rubber_duck', label: '🦆 Canard 3D (Photo 1)' },
                    { id: 'starship_falcon', label: '🚀 Vaisseau Falcon' },
                    { id: 'dragon_head', label: '🐉 Dragon 3D' },
                    { id: 'pokeball_emblem', label: '⚡ Sphère 3D' },
                  ].map((sp) => (
                    <button
                      key={sp.id}
                      type="button"
                      className={`btn-hud ${stlPreset === sp.id ? 'active' : ''}`}
                      style={{ flex: 1, fontSize: '0.65rem', padding: '4px 5px' }}
                      onClick={() => {
                        setStlPreset(sp.id);
                        handleGenerate({ stlPreset: sp.id });
                      }}
                    >
                      {sp.label}
                    </button>
                  ))}
                </div>

                <input
                  ref={stlInputRef}
                  type="file"
                  accept=".stl"
                  style={{ display: 'none' }}
                  onChange={async (e) => {
                    const f = e.target.files?.[0];
                    if (!f) return;
                    e.target.value = '';
                    setLoading(true);
                    try {
                      const fd = new FormData();
                      fd.append('file', f);
                      const url = `${API_BASE}/api/makerlab/upload-stl${sessionId ? `?session_id=${sessionId}` : ''}`;
                      const res = await fetch(url, { method: 'POST', body: fd });
                      const d = await res.json();
                      if (!res.ok) throw new Error(d.detail || 'Erreur import STL');
                      setSessionId(d.session_id);
                      setUploadedStlName(d.stl_filename);
                      setStlPreset('custom_stl');
                      const resGen = await fetch(`${API_BASE}/api/makerlab/${d.session_id}/generate`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(buildPayload({ stlPreset: 'custom_stl' })),
                      });
                      const genData = await resGen.json();
                      if (resGen.ok) applyResult(genData);
                    } catch (err) {
                      alert(err.message);
                    } finally {
                      setLoading(false);
                    }
                  }}
                />
                <button
                  type="button"
                  className={`btn-cyber ${stlPreset === 'custom_stl' ? 'primary-full' : 'secondary'}`}
                  style={{ width: '100%', marginBottom: '7px', fontSize: '0.72rem' }}
                  onClick={() => stlInputRef.current?.click()}
                >
                  📂 {uploadedStlName ? `STL Actif : ${uploadedStlName}` : 'Importer mon propre fichier .STL à convertir en Bas-Relief...'}
                </button>

                <div className="grid-2col">
                  <div>
                    <label className="field-label">
                      Angle Rotation (Yaw) : <strong className="text-cyan">{stlYawDeg}°</strong>
                    </label>
                    <input
                      type="range"
                      min="-180"
                      max="180"
                      step="5"
                      value={stlYawDeg}
                      onChange={(e) => setStlYawDeg(parseFloat(e.target.value))}
                      style={{ width: '100%', accentColor: '#00f0ff' }}
                    />
                  </div>
                  <div>
                    <label className="field-label">
                      Inclinaison (Pitch) : <strong className="text-cyan">{stlPitchDeg}°</strong>
                    </label>
                    <input
                      type="range"
                      min="-75"
                      max="75"
                      step="5"
                      value={stlPitchDeg}
                      onChange={(e) => setStlPitchDeg(parseFloat(e.target.value))}
                      style={{ width: '100%', accentColor: '#00f0ff' }}
                    />
                  </div>
                </div>

                <label className="field-label" style={{ marginTop: '4px' }}>Style de Cadre Bas-Relief :</label>
                <select
                  className="cyber-input"
                  value={reliefFrameStyle}
                  onChange={(e) => setReliefFrameStyle(e.target.value)}
                >
                  <option value="beveled_frame">🖼️ Cadre Biseauté Rectangulaire (Style Photo 1)</option>
                  <option value="oval_medallion">⭕ Médaillon Ovale</option>
                  <option value="frameless">✂️ Sans Cadre (Détouré Objet)</option>
                </select>
              </div>
            )}

            {toolId === 'ai_mesh_3d' && (
              <div
                style={{
                  marginTop: '8px',
                  padding: '9px 10px',
                  borderRadius: '8px',
                  background: 'rgba(168, 85, 247, 0.08)',
                  border: '1px solid rgba(168, 85, 247, 0.35)',
                }}
              >
                <label className="field-label" style={{ color: '#d8b4fe', fontWeight: 700 }}>
                  🤖 Moteur de Sculpture 3D (Style Meshy.ai) :
                </label>
                <select
                  className="cyber-input"
                  value={aiEngine}
                  onChange={(e) => setAiEngine(e.target.value)}
                  style={{ marginBottom: '6px' }}
                >
                  <option value="local_organic_3d">🟢 Moteur Local Gratuit (Inflation Volumétrique 360° Instantanée)</option>
                  <option value="hf_free_cloud">☁️ Cloud IA Gratuit sans clé (HuggingFace ZeroGPU + Repli Local)</option>
                  <option value="meshy_api">🔑 Connecteur Officiel Meshy.ai API (Clé msy_...)</option>
                </select>

                {aiEngine === 'meshy_api' && (
                  <div style={{ marginBottom: '6px' }}>
                    <label className="field-label">Clé API Meshy.ai (`msy_...`) :</label>
                    <input
                      type="password"
                      className="cyber-input"
                      placeholder="msy_..."
                      value={meshyApiKey}
                      onChange={(e) => setMeshyApiKey(e.target.value)}
                    />
                  </div>
                )}

                <label className="switch-label" style={{ marginTop: '4px' }}>
                  <input
                    type="checkbox"
                    checked={aiAddPedestal}
                    onChange={(e) => setAiAddPedestal(e.target.checked)}
                  />
                  <span>🏛️ Ajouter un socle figurine circulaire sous la sculpture 3D</span>
                </label>
              </div>
            )}

            <div className="btn-row" style={{ marginTop: '8px' }}>
              <label className="switch-label" style={{ flex: 1 }}>
                <input
                  type="checkbox"
                  checked={removeBgAuto}
                  onChange={(e) => setRemoveBgAuto(e.target.checked)}
                />
                <span>Détourage Auto</span>
              </label>
              <label className="switch-label" style={{ flex: 1 }}>
                <input
                  type="checkbox"
                  checked={invertMask}
                  onChange={(e) => setInvertMask(e.target.checked)}
                />
                <span>Inverser Négatif</span>
              </label>
            </div>

            <button
              type="button"
              className="btn-cyber primary-full"
              style={{ marginTop: '10px', fontWeight: 800 }}
              disabled={loading}
              onClick={() => handleGenerate()}
            >
              {loading ? '⏳ Calcul Géométrique 3D en cours...' : '⚡ Générer / Actualiser le Modèle 3D'}
            </button>
          </section>

          {/* SECTION 4: 3D PARTS INSPECTION & STL / ZIP EXPORT */}
          {partsMeta.length > 0 && (
            <section className="panel-card">
              <div className="panel-title">
                4. INSPECTION DES PIÈCES &amp; EXPORT .STL ({partsMeta.length} PIÈCE{partsMeta.length > 1 ? 'S' : ''})
              </div>

              {partsMeta.length > 1 && (
                <button
                  type="button"
                  className={`btn-hud ${activePartIdx === 0 ? 'active' : ''}`}
                  style={{ width: '100%', marginBottom: '6px', padding: '7px', fontWeight: 700 }}
                  onClick={() => {
                    setActivePartIdx(0);
                    setActiveStlUrl(assemblyStlUrl);
                  }}
                >
                  🌟 Vue 3D Assemblée Complète (Toutes les pièces)
                </button>
              )}

              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '10px' }}>
                {partsMeta.map((pt, idx) => {
                  const pIdx = idx + 1;
                  const isSel = activePartIdx === pIdx;
                  return (
                    <div
                      key={pt.part_id}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '6px 9px',
                        borderRadius: '7px',
                        background: isSel ? 'rgba(0, 240, 255, 0.14)' : 'rgba(15, 23, 42, 0.75)',
                        border: isSel ? '1px solid #00f0ff' : '1px solid #1e293b',
                      }}
                    >
                      <div
                        style={{ cursor: 'pointer', flex: 1 }}
                        onClick={() => {
                          setActivePartIdx(pIdx);
                          setActiveStlUrl(`${API_BASE}${pt.download_url}?t=${stlTick}`);
                        }}
                      >
                        <div style={{ fontSize: '0.73rem', fontWeight: 700, color: '#f8fafc' }}>{pt.label}</div>
                        <div style={{ fontSize: '0.64rem', color: '#94a3b8' }}>
                          {pt.dimensions_mm.join(' × ')} mm • {pt.faces.toLocaleString()} triangles
                        </div>
                      </div>
                      <a
                        href={`${API_BASE}${pt.download_url}`}
                        download={pt.filename}
                        className="btn-hud active"
                        style={{ textDecoration: 'none', padding: '4px 8px', fontSize: '0.68rem' }}
                      >
                        ⬇ STL
                      </a>
                    </div>
                  );
                })}
              </div>

              {zipDownloadUrl && (
                <a
                  href={zipDownloadUrl}
                  download
                  className="btn-cyber primary-full"
                  style={{
                    display: 'block',
                    textAlign: 'center',
                    textDecoration: 'none',
                    background: 'linear-gradient(90deg, #10b981, #059669)',
                  }}
                >
                  📦 Télécharger le Kit Complet (.ZIP)
                </a>
              )}

              {sessionId && (
                <div style={{ marginTop: '8px' }}>
                  <button
                    type="button"
                    className="btn-cyber secondary"
                    style={{
                      width: '100%',
                      borderColor: '#f59e0b',
                      color: '#fde68a',
                      fontSize: '0.72rem',
                    }}
                    onClick={async () => {
                      try {
                        const res = await fetch(`${API_BASE}/api/makerlab/${sessionId}/send-to-hueforge`, {
                          method: 'POST',
                        });
                        const d = await res.json();
                        if (res.ok) {
                          setTransferMsg(d.message);
                          if (onOpenHueForge) onOpenHueForge();
                        }
                      } catch (e) {
                        console.error(e);
                      }
                    }}
                  >
                    🚀 Envoyer ce Modèle 3D vers HueForge Studio (Mode Pop-Out)
                  </button>
                  {transferMsg && (
                    <div style={{ fontSize: '0.67rem', color: '#34d399', marginTop: '4px', textAlign: 'center' }}>
                      ✓ {transferMsg}
                    </div>
                  )}
                </div>
              )}
            </section>
          )}
        </div>
      </aside>

      {/* RIGHT 3D INTERACTIVE VIEWPORT */}
      <main style={{ flex: 1, height: 'calc(100vh - 48px)', position: 'relative' }}>
        {isVisible && (
          <Viewer3D
            stlUrl={activeStlUrl}
            modelStats={
              stats
                ? {
                    vertices_count: stats.total_vertices,
                    faces_count: stats.total_faces,
                    extents: stats.dimensions_mm,
                    is_watertight: true,
                  }
                : null
            }
            bedSize={bedSize}
            showRod={false}
            cutMode="auto_grid"
            cutPlanesZ={[]}
            boundedOrigin={[0, 0, 0]}
            boundedSize={[80, 80, 80]}
            boundedType="cylinder"
          />
        )}
      </main>
    </div>
  );
}

