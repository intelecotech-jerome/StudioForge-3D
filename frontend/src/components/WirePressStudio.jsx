import React, { useState, useEffect, useRef } from 'react';
import Viewer3D from './Viewer3D';

const API_BASE = 'http://127.0.0.1:8000';

const GARMENT_TYPES = [
  { id: 'tshirt', label: '👕 T-Shirt', desc: 'Coupe classique coton' },
  { id: 'hoodie', label: '🧥 Pull / Hoodie', desc: 'Sweat à capuche & poche' },
  { id: 'crewneck', label: '🧶 Pull Col Rond', desc: 'Sweatshirt manches longues' },
  { id: 'totebag', label: '👜 Tote Bag', desc: 'Sac cabas textile' },
];

const GARMENT_COLORS = [
  { name: 'Noir Profond', hex: '#12151e' },
  { name: 'Blanc Coton', hex: '#f1f5f9' },
  { name: 'Bleu Marine', hex: '#172554' },
  { name: 'Bleu Roi', hex: '#1d4ed8' },
  { name: 'Gris Chiné', hex: '#475569' },
  { name: 'Rouge Bordeaux', hex: '#7f1d1d' },
  { name: 'Vert Forêt', hex: '#14532d' },
  { name: 'Jaune Moutarde', hex: '#ca8a04' },
  { name: 'Beige Sable', hex: '#d6c7b2' },
  { name: 'Rose Pastel', hex: '#f472b6' },
];

const WIRE_STYLES = [
  {
    id: 'organic_portrait',
    label: '✨ Auto / Portrait',
    desc: 'Détecte automatiquement Photo ou Dessin/Manga et extrait des fils nets sans bavure',
  },
  {
    id: 'manga_lineart',
    label: '✒️ Line-Art Fin',
    desc: 'Tracé haute précision spécial mangas, coloriages, logos, tatouages et symboles',
  },
  {
    id: 'streetwear_stencil',
    label: '🕸️ Streetwear Mesh',
    desc: 'Transforme les ombres profondes en maillage graphique croisé',
  },
  {
    id: 'cell_halftone',
    label: '🔲 Cell / Grille Tramée',
    desc: 'Transforme la photo en grille cellulaire tramée (ouvertures modulées par la lumière)',
  },
];

const FRAME_MODES = [
  { id: 'rounded_rect', label: '▭ Badge Arrondi (Style Photo)' },
  { id: 'frameless', label: '✂️ Sans Cadre (Fils Libres Reliés)' },
  { id: 'silhouette_offset', label: '✨ Contour Détouré Silhouette' },
  { id: 'hexagon', label: '⬡ Cadre Hexagone' },
  { id: 'circle', label: '◯ Écusson Rond' },
  { id: 'shield', label: '🛡️ Blason / Bouclier' },
  { id: 'heart', label: '❤️ Cadre Cœur' },
];

export default function WirePressStudio({
  printerPreset,
  onChangePrinterPreset,
  spoolsRefreshTick = 0,
  onOpenSpoolSetup,
  onOpenPrinterSetup,
}) {
  const fileInputRef = useRef(null);
  const debounceRef = useRef(null);
  const garmentStageRef = useRef(null);
  const dragStateRef = useRef(null);
  const sourceDragRef = useRef(null);
  const latestStateRef = useRef({});
  const reqSeqRef = useRef(0);

  const [loading, setLoading] = useState(false);
  const [wpSessionId, setWpSessionId] = useState(null);
  const [filename, setFilename] = useState('');
  const [sourcePreviewUrl, setSourcePreviewUrl] = useState(null);
  const [wireRgbaUrl, setWireRgbaUrl] = useState(null);
  const [stats, setStats] = useState(null);
  const [viewMode, setViewMode] = useState('studio_2d'); // 'studio_2d' | 'mesh_3d'

  // Spools & Printers
  const [userSpools, setUserSpools] = useState([]);
  const [printers, setPrinters] = useState([]);
  const [selectedSpoolId, setSelectedSpoolId] = useState('__custom__');
  const [wireHexColor, setWireHexColor] = useState('#22c55e');

  // Interactive Garment Mockup & Wire Placement State
  const [garmentType, setGarmentType] = useState('tshirt');
  const [garmentColor, setGarmentColor] = useState('#12151e');
  const [garmentZoom, setGarmentZoom] = useState(0.88); // Fits full T-shirt cleanly by default
  const [garmentPan, setGarmentPan] = useState({ x: 0, y: 0 });
  // Wire position in % of the garment SVG coordinate box (50% = dead center horizontally!)
  const [wirePos, setWirePos] = useState({ x: 50.0, y: 40.0 });
  const [isDraggingWire, setIsDraggingWire] = useState(false);
  const [isResizingWire, setIsResizingWire] = useState(false);

  // Wire Extraction & Textile Parameters
  const [wireStyle, setWireStyle] = useState('organic_portrait');
  const [frameMode, setFrameMode] = useState('rounded_rect');
  const [detailLevel, setDetailLevel] = useState(1.0);
  const [lineWidthMm, setLineWidthMm] = useState(1.6);
  const [thicknessZMm, setThicknessZMm] = useState(0.60);
  const [targetWidthMm, setTargetWidthMm] = useState(160.0);
  const [autoBridges, setAutoBridges] = useState(true);
  const [removeBgAuto, setRemoveBgAuto] = useState(true);
  const [mirrorHorizontal, setMirrorHorizontal] = useState(false);
  const [invertImage, setInvertImage] = useState(false);
  const [zoom, setZoom] = useState(1.0);
  const [offsetXPct, setOffsetXPct] = useState(0.0);
  const [offsetYPct, setOffsetYPct] = useState(0.0);

  // 3D Generation Result
  const [genResult, setGenResult] = useState(null);
  const [stlVersion, setStlVersion] = useState(0);

  useEffect(() => {
    fetch(`${API_BASE}/api/spools`)
      .then((r) => r.json())
      .then((d) => {
        if (d.spools) setUserSpools(d.spools);
      })
      .catch((err) => console.error('Erreur chargement bobines:', err));

    fetch(`${API_BASE}/api/printers`)
      .then((r) => r.json())
      .then((d) => {
        if (d.printers && d.printers.length > 0) setPrinters(d.printers);
      })
      .catch((err) => console.error('Erreur chargement imprimantes:', err));
  }, [spoolsRefreshTick]);

  const inStockSpools = userSpools.filter((s) => s.in_stock !== false);
  const outOfStockSpools = userSpools.filter((s) => s.in_stock === false);
  const favoriteSpools = userSpools.filter((s) => s.is_favorite !== false);

  const activePrinter =
    printers.find((p) => p.id === printerPreset) ||
    printers[0] || {
      id: 'creality_hi',
      name: 'Creality Hi',
      bed_x_mm: 260,
      bed_y_mm: 260,
      bed_z_mm: 300,
    };

  const bedSize = [
    activePrinter?.bed_x_mm || 260,
    activePrinter?.bed_y_mm || 260,
    activePrinter?.bed_z_mm || 300,
  ];
  const maxSafeWidthMm = Math.max(80, Math.min(bedSize[0], bedSize[1]) - 15);

  // Keep `latestStateRef` synchronized on every render so event listeners never use a stale `wpSessionId`
  latestStateRef.current = {
    wpSessionId,
    wireStyle,
    frameMode,
    detailLevel,
    lineWidthMm,
    thicknessZMm,
    targetWidthMm,
    autoBridges,
    removeBgAuto,
    mirrorHorizontal,
    invertImage,
    zoom,
    offsetXPct,
    offsetYPct,
    wireHexColor,
  };

  const buildPayload = (overrides = {}) => {
    const s = latestStateRef.current;
    return {
      wire_style: overrides.wireStyle ?? s.wireStyle,
      frame_mode: overrides.frameMode ?? s.frameMode,
      detail_level: overrides.detailLevel ?? s.detailLevel,
      line_width_mm: overrides.lineWidthMm ?? s.lineWidthMm,
      thickness_z_mm: overrides.thicknessZMm ?? s.thicknessZMm,
      target_width_mm: overrides.targetWidthMm ?? s.targetWidthMm,
      auto_bridges: overrides.autoBridges ?? s.autoBridges,
      remove_bg_auto: overrides.removeBgAuto ?? s.removeBgAuto,
      mirror_horizontal: overrides.mirrorHorizontal ?? s.mirrorHorizontal,
      invert_image: overrides.invertImage ?? s.invertImage,
      zoom: overrides.zoom ?? s.zoom,
      offset_x_pct: overrides.offsetXPct ?? s.offsetXPct,
      offset_y_pct: overrides.offsetYPct ?? s.offsetYPct,
      wire_hex_color: overrides.wireHexColor ?? s.wireHexColor,
    };
  };

  const refreshPreview = async (overrides = {}) => {
    const activeSid = overrides.wpSessionId ?? latestStateRef.current.wpSessionId;
    if (!activeSid) return;
    const seq = ++reqSeqRef.current;
    try {
      const res = await fetch(`${API_BASE}/api/wirepress/${activeSid}/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildPayload(overrides)),
      });
      const data = await res.json();
      // Ignore stale responses if a newer request or a new image upload happened in the meantime
      if (seq !== reqSeqRef.current || activeSid !== latestStateRef.current.wpSessionId) {
        return;
      }
      if (res.ok) {
        setSourcePreviewUrl(data.source_preview_data_url);
        setWireRgbaUrl(data.wire_rgba_data_url);
        setStats(data.stats);
      }
    } catch (e) {
      console.error('Erreur aperçu WirePress:', e);
    }
  };

  const schedulePreview = (overrides = {}, delayMs = 80) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      debounceRef.current = null;
      refreshPreview(overrides);
    }, delayMs);
  };

  const handleUploadImage = async (file) => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }
    ++reqSeqRef.current;
    setLoading(true);
    setGenResult(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await fetch(`${API_BASE}/api/wirepress/upload`, {
        method: 'POST',
        body: fd,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Erreur upload image');

      // Immediately update ref and state with the new session_id and reset framing
      latestStateRef.current.wpSessionId = data.session_id;
      latestStateRef.current.zoom = 1.0;
      latestStateRef.current.offsetXPct = 0.0;
      latestStateRef.current.offsetYPct = 0.0;

      setWpSessionId(data.session_id);
      setFilename(data.filename);
      setZoom(1.0);
      setOffsetXPct(0.0);
      setOffsetYPct(0.0);
      setSourcePreviewUrl(data.source_preview_data_url);
      setWireRgbaUrl(data.wire_rgba_data_url);
      setStats(data.stats);
      setWirePos({ x: 50.0, y: 40.0 });
      setViewMode('studio_2d');

      // Apply current user settings (e.g. chosen spool color, frame mode, line width) to the newly uploaded image
      await refreshPreview({
        wpSessionId: data.session_id,
        zoom: 1.0,
        offsetXPct: 0.0,
        offsetYPct: 0.0,
      });
    } catch (e) {
      alert(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectSpoolColor = (hex, spoolObj = null) => {
    setWireHexColor(hex);
    setSelectedSpoolId(spoolObj ? spoolObj.id : '__custom__');
    schedulePreview({ wireHexColor: hex }, 35);
  };

  const handleGenerate3D = async () => {
    if (!wpSessionId) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/wirepress/${wpSessionId}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildPayload()),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Erreur génération 3D WirePress');
      setGenResult(data);
      if (data.stats) setStats(data.stats);
      setStlVersion((v) => v + 1);
    } catch (e) {
      alert(e.message);
    } finally {
      setLoading(false);
    }
  };

  // --- INTERACTIVE DRAG & RESIZE OF WIRE ON GARMENT + GARMENT PAN/ZOOM ---
  useEffect(() => {
    const handleWindowMouseMove = (e) => {
      const st = dragStateRef.current;
      if (!st) return;

      if (st.mode === 'move_wire') {
        const rect = st.stageRect;
        if (!rect || rect.width <= 0 || rect.height <= 0) return;
        const dxPct = ((e.clientX - st.startX) / (rect.width * garmentZoom)) * 100.0;
        const dyPct = ((e.clientY - st.startY) / (rect.height * garmentZoom)) * 100.0;
        let nextX = Math.max(18, Math.min(82, st.initWireX + dxPct));
        let nextY = Math.max(15, Math.min(85, st.initWireY + dyPct));
        // Magnetic snap to center vertical axis of the T-shirt (50%)
        if (Math.abs(nextX - 50.0) < 1.8) {
          nextX = 50.0;
        }
        setWirePos({ x: Number(nextX.toFixed(1)), y: Number(nextY.toFixed(1)) });
      } else if (st.mode === 'resize_wire') {
        const deltaPx = (e.clientX - st.startX) * st.dirX + (e.clientY - st.startY) * st.dirY;
        const deltaMm = (deltaPx / Math.max(0.4, garmentZoom)) * 0.85;
        const nextWidth = Math.round(
          Math.max(50, Math.min(maxSafeWidthMm, st.initWidthMm + deltaMm))
        );
        setTargetWidthMm(nextWidth);
        schedulePreview({ targetWidthMm: nextWidth }, 110);
      } else if (st.mode === 'pan_garment') {
        const dx = e.clientX - st.startX;
        const dy = e.clientY - st.startY;
        setGarmentPan({ x: st.initPanX + dx, y: st.initPanY + dy });
      }
    };

    const handleWindowMouseUp = () => {
      if (dragStateRef.current) {
        dragStateRef.current = null;
        setIsDraggingWire(false);
        setIsResizingWire(false);
      }
    };

    window.addEventListener('mousemove', handleWindowMouseMove);
    window.addEventListener('mouseup', handleWindowMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleWindowMouseMove);
      window.removeEventListener('mouseup', handleWindowMouseUp);
    };
  }, [garmentZoom, maxSafeWidthMm]);

  const handleStartMoveWire = (e) => {
    e.stopPropagation();
    e.preventDefault();
    const stageEl = garmentStageRef.current;
    if (!stageEl) return;
    dragStateRef.current = {
      mode: 'move_wire',
      startX: e.clientX,
      startY: e.clientY,
      initWireX: wirePos.x,
      initWireY: wirePos.y,
      stageRect: stageEl.getBoundingClientRect(),
    };
    setIsDraggingWire(true);
  };

  const handleStartResizeWire = (e, dirX, dirY) => {
    e.stopPropagation();
    e.preventDefault();
    dragStateRef.current = {
      mode: 'resize_wire',
      startX: e.clientX,
      startY: e.clientY,
      dirX,
      dirY,
      initWidthMm: targetWidthMm,
    };
    setIsResizingWire(true);
  };

  const handleStartPanGarment = (e) => {
    if (e.button !== 0) return;
    dragStateRef.current = {
      mode: 'pan_garment',
      startX: e.clientX,
      startY: e.clientY,
      initPanX: garmentPan.x,
      initPanY: garmentPan.y,
    };
  };

  const handleGarmentWheel = (e) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 0.08 : -0.08;
    setGarmentZoom((z) => Number(Math.max(0.45, Math.min(2.5, z + factor)).toFixed(2)));
  };

  // --- INTERACTIVE DRAG & WHEEL ON SOURCE PHOTO (ÉTAPE A) ---
  const handleSourceMouseDown = (e) => {
    if (e.button !== 0) return;
    sourceDragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      initX: offsetXPct,
      initY: offsetYPct,
    };
    const onMove = (ev) => {
      if (!sourceDragRef.current) return;
      const dx = ((ev.clientX - sourceDragRef.current.startX) / 240.0) * 100.0;
      const dy = ((ev.clientY - sourceDragRef.current.startY) / 240.0) * 100.0;
      const nx = Math.round(Math.max(-80, Math.min(80, sourceDragRef.current.initX + dx)));
      const ny = Math.round(Math.max(-80, Math.min(80, sourceDragRef.current.initY + dy)));
      setOffsetXPct(nx);
      setOffsetYPct(ny);
      schedulePreview({ offsetXPct: nx, offsetYPct: ny }, 75);
    };
    const onUp = () => {
      sourceDragRef.current = null;
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  const handleSourceWheel = (e) => {
    e.preventDefault();
    const step = e.deltaY < 0 ? 0.08 : -0.08;
    const nz = Number(Math.max(0.4, Math.min(3.0, zoom + step)).toFixed(2));
    setZoom(nz);
    schedulePreview({ zoom: nz }, 75);
  };

  const previewStlUrl =
    genResult && wpSessionId ? `${API_BASE}${genResult.preview_stl_url}?v=${stlVersion}` : null;
  const downloadStlUrl =
    genResult && wpSessionId ? `${API_BASE}${genResult.download_stl_url}` : null;
  const downloadZipUrl =
    genResult && wpSessionId ? `${API_BASE}${genResult.download_zip_url}` : null;

  // Render realistic SVG Garment silhouette (T-shirt, Hoodie, Crewneck, or Tote Bag)
  const renderGarmentSvg = () => {
    const isLightFabric =
      garmentColor.toLowerCase() === '#f1f5f9' ||
      garmentColor.toLowerCase() === '#ffffff' ||
      garmentColor.toLowerCase() === '#d6c7b2';
    const strokeCol = isLightFabric ? 'rgba(15, 23, 42, 0.28)' : 'rgba(255, 255, 255, 0.20)';
    const seamCol = isLightFabric ? 'rgba(15, 23, 42, 0.14)' : 'rgba(255, 255, 255, 0.10)';

    if (garmentType === 'totebag') {
      return (
        <svg viewBox="0 0 560 580" style={{ width: '100%', height: '100%', display: 'block' }}>
          <path
            d="M 205 145 C 205 30, 355 30, 355 145"
            fill="none"
            stroke={garmentColor}
            strokeWidth="24"
            strokeLinecap="round"
          />
          <path
            d="M 205 145 C 205 30, 355 30, 355 145"
            fill="none"
            stroke={strokeCol}
            strokeWidth="2"
          />
          <rect
            x="115"
            y="135"
            width="330"
            height="400"
            rx="14"
            fill={garmentColor}
            stroke={strokeCol}
            strokeWidth="3"
          />
          <line x1="125" y1="158" x2="435" y2="158" stroke={seamCol} strokeWidth="2" strokeDasharray="6 4" />
        </svg>
      );
    }

    if (garmentType === 'hoodie') {
      return (
        <svg viewBox="0 0 560 580" style={{ width: '100%', height: '100%', display: 'block' }}>
          <path
            d="M 195 75 C 210 25, 350 25, 365 75 L 445 110 L 535 255 L 475 295 L 425 205 L 425 525 L 135 525 L 135 205 L 85 295 L 25 255 L 115 110 Z"
            fill={garmentColor}
            stroke={strokeCol}
            strokeWidth="3"
            strokeLinejoin="round"
          />
          <path
            d="M 215 75 C 235 120, 325 120, 345 75"
            fill="rgba(0,0,0,0.22)"
            stroke={strokeCol}
            strokeWidth="2.5"
          />
          <line x1="255" y1="108" x2="252" y2="205" stroke={strokeCol} strokeWidth="3.5" strokeLinecap="round" />
          <line x1="305" y1="108" x2="308" y2="205" stroke={strokeCol} strokeWidth="3.5" strokeLinecap="round" />
          <path
            d="M 175 395 L 385 395 L 405 495 L 155 495 Z"
            fill="none"
            stroke={seamCol}
            strokeWidth="2.5"
          />
          <line x1="135" y1="500" x2="425" y2="500" stroke={seamCol} strokeWidth="2.5" />
        </svg>
      );
    }

    if (garmentType === 'crewneck') {
      return (
        <svg viewBox="0 0 560 580" style={{ width: '100%', height: '100%', display: 'block' }}>
          <path
            d="M 205 70 C 240 95, 320 95, 355 70 L 450 110 L 535 290 L 470 320 L 425 200 L 425 525 L 135 525 L 135 200 L 90 320 L 25 290 L 110 110 Z"
            fill={garmentColor}
            stroke={strokeCol}
            strokeWidth="3"
            strokeLinejoin="round"
          />
          <path
            d="M 205 70 C 240 112, 320 112, 355 70"
            fill="none"
            stroke={seamCol}
            strokeWidth="8"
          />
          <line x1="135" y1="500" x2="425" y2="500" stroke={seamCol} strokeWidth="3" />
        </svg>
      );
    }

    // Default: Classic T-Shirt
    return (
      <svg viewBox="0 0 560 580" style={{ width: '100%', height: '100%', display: 'block' }}>
        <path
          d="M 205 68 C 242 98, 318 98, 355 68 L 455 108 L 525 215 L 448 258 L 418 195 L 418 530 L 142 530 L 142 195 L 112 258 L 35 215 L 105 108 Z"
          fill={garmentColor}
          stroke={strokeCol}
          strokeWidth="3"
          strokeLinejoin="round"
        />
        <path
          d="M 200 72 C 242 112, 318 112, 360 72"
          fill="none"
          stroke={seamCol}
          strokeWidth="5"
        />
        <line x1="190" y1="220" x2="182" y2="490" stroke={seamCol} strokeWidth="1.5" />
        <line x1="370" y1="220" x2="378" y2="490" stroke={seamCol} strokeWidth="1.5" />
      </svg>
    );
  };

  // Visual width of the Wire as % of the Garment stage (480mm = full shoulder-to-shoulder span)
  const wireWidthPct = Math.min(52, Math.max(12, (targetWidthMm / 460.0) * 100.0));
  const isCenteredX = Math.abs(wirePos.x - 50.0) < 0.6;
  const selectedSpoolObj = userSpools.find((s) => s.id === selectedSpoolId);

  return (
    <div className="app-layout" style={{ height: 'calc(100vh - 48px)' }}>
      {/* LEFT SIDEBAR: WIREPRESS CONTROLS */}
      <aside className="sidebar" style={{ height: 'calc(100vh - 48px)', width: '430px', minWidth: '430px' }}>
        <div className="sidebar-scroll">
          {/* SECTION 1: IMAGE & FILAMENT SPOOL COLOR */}
          <section className="panel-card">
            <div className="panel-header-flex">
              <div className="panel-title">1. PHOTO SOURCE &amp; COULEUR DU WIRE</div>
              <div style={{ display: 'flex', gap: '4px' }}>
                {onOpenPrinterSetup && (
                  <button
                    type="button"
                    className="btn-hud"
                    style={{ fontSize: '0.66rem', padding: '3px 7px' }}
                    onClick={onOpenPrinterSetup}
                  >
                    🖨️ Imprimantes
                  </button>
                )}
                {onOpenSpoolSetup && (
                  <button
                    type="button"
                    className="btn-hud active"
                    style={{ fontSize: '0.66rem', padding: '3px 7px' }}
                    onClick={onOpenSpoolSetup}
                  >
                    🎨 Bobines / + IA
                  </button>
                )}
              </div>
            </div>

            <div className="panel-header-flex" style={{ marginBottom: '3px' }}>
              <label className="field-label" style={{ margin: 0 }}>
                Imprimante Cible
              </label>
              <span className="dim-badge" style={{ fontSize: '0.67rem' }}>
                Plateau {bedSize[0]}×{bedSize[1]} mm
              </span>
            </div>
            <select
              className="cyber-input"
              value={activePrinter?.id || printerPreset}
              onChange={(e) => onChangePrinterPreset(e.target.value)}
            >
              {printers.map((pr) => (
                <option key={pr.id} value={pr.id}>
                  🖨️ {pr.name} ({pr.bed_x_mm}×{pr.bed_y_mm} mm)
                </option>
              ))}
            </select>

            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              style={{ display: 'none' }}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleUploadImage(f);
                e.target.value = '';
              }}
            />
            <button
              type="button"
              className="btn-cyber primary-full"
              style={{ marginTop: '10px' }}
              disabled={loading}
              onClick={() => fileInputRef.current?.click()}
            >
              🖼️ Importer une Photo / Manga / Logo (.PNG / .JPG / .WEBP)
            </button>

            {/* Wire Spool Color Selector from User's Encoded Spool Library */}
            <label className="field-label" style={{ marginTop: '10px' }}>
              Couleur de la Bobine pour le Wire (Mon Stock) :
            </label>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '6px' }}>
              <input
                type="color"
                value={wireHexColor}
                onChange={(e) => handleSelectSpoolColor(e.target.value, null)}
                className="color-Swatch-input"
                title="Choisir une couleur sur mesure pour le Wire"
              />
              <select
                className="cyber-input spool-select-compact"
                value={selectedSpoolId}
                onChange={(e) => {
                  const val = e.target.value;
                  if (val === '__setup__') {
                    if (onOpenSpoolSetup) onOpenSpoolSetup();
                    return;
                  }
                  const sp = userSpools.find((s) => s.id === val);
                  if (sp) handleSelectSpoolColor(sp.hex_color, sp);
                }}
              >
                <option value="__custom__">
                  🎨 Couleur libre ({wireHexColor.toUpperCase()})
                </option>
                <optgroup label={`📦 Mes Bobines EN STOCK (${inStockSpools.length})`}>
                  {inStockSpools.map((sp) => (
                    <option key={sp.id} value={sp.id}>
                      ■ {sp.brand} {sp.material} — {sp.color_name}
                    </option>
                  ))}
                </optgroup>
                {outOfStockSpools.length > 0 && (
                  <optgroup label={`⏳ Autres Bobines (${outOfStockSpools.length})`}>
                    {outOfStockSpools.map((sp) => (
                      <option key={sp.id} value={sp.id}>
                        □ {sp.brand} {sp.material} — {sp.color_name}
                      </option>
                    ))}
                  </optgroup>
                )}
                <option value="__setup__">➕ Encoder / Gérer mes bobines...</option>
              </select>
            </div>

            {/* Quick Spool Swatches Bar */}
            <div className="spool-presets-bar">
              {favoriteSpools.map((sp) => (
                <button
                  key={sp.id}
                  type="button"
                  className={`spool-dot ${
                    wireHexColor.toLowerCase() === sp.hex_color.toLowerCase() ? 'selected' : ''
                  }`}
                  style={{ backgroundColor: sp.hex_color }}
                  title={`${sp.brand} ${sp.material} — ${sp.color_name} (${sp.hex_color})`}
                  onClick={() => handleSelectSpoolColor(sp.hex_color, sp)}
                />
              ))}
            </div>
          </section>

          {/* SECTION 2: WIRE STRUCTURE EXTRACTION & FRAME */}
          {wpSessionId && (
            <section className="panel-card">
              <div className="panel-header-flex">
                <div className="panel-title">2. STYLE DU WIRE &amp; FINESSE</div>
                {stats?.detected_lineart && (
                  <span className="dim-badge" style={{ color: '#34d399', borderColor: '#10b981', fontSize: '0.65rem' }}>
                    ✨ Tracé Line-Art HD actif
                  </span>
                )}
              </div>

              <label className="field-label">Algorithme &quot;Photo / Dessin ➔ Wire Structure&quot; :</label>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '5px', marginBottom: '8px' }}>
                {WIRE_STYLES.map((st) => {
                  const active = wireStyle === st.id;
                  return (
                    <button
                      key={st.id}
                      type="button"
                      className={`btn-hud ${active ? 'active' : ''}`}
                      style={{ padding: '6px 5px', fontSize: '0.67rem', fontWeight: active ? 700 : 500 }}
                      onClick={() => {
                        setWireStyle(st.id);
                        refreshPreview({ wireStyle: st.id });
                      }}
                      title={st.desc}
                    >
                      {st.label}
                    </button>
                  );
                })}
              </div>

              <label className="field-label">Forme du Cadre Extérieur :</label>
              <select
                className="cyber-input"
                value={frameMode}
                onChange={(e) => {
                  const v = e.target.value;
                  setFrameMode(v);
                  refreshPreview({ frameMode: v });
                }}
              >
                {FRAME_MODES.map((fm) => (
                  <option key={fm.id} value={fm.id}>
                    {fm.label}
                  </option>
                ))}
              </select>

              <label className="field-label" style={{ marginTop: '8px' }}>
                Sensibilité / Détails Internes : <strong className="text-cyan">×{detailLevel.toFixed(2)}</strong>
              </label>
              <input
                type="range"
                min="0.40"
                max="1.80"
                step="0.05"
                value={detailLevel}
                onChange={(e) => {
                  const v = parseFloat(e.target.value);
                  setDetailLevel(v);
                  schedulePreview({ detailLevel: v });
                }}
                style={{ width: '100%', accentColor: '#00f0ff' }}
              />

              <label className="field-label">
                Finesse / Largeur du Fil (Wire) : <strong className="text-cyan">{lineWidthMm.toFixed(1)} mm</strong>
              </label>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '4px', marginBottom: '4px' }}>
                {[
                  { label: '✒️ Ultra-Fin (1.2mm)', w: 1.2 },
                  { label: '✨ Standard (1.6mm)', w: 1.6 },
                  { label: '💪 Épais (2.4mm)', w: 2.4 },
                ].map((lw) => (
                  <button
                    key={lw.label}
                    type="button"
                    className={`btn-hud ${Math.abs(lineWidthMm - lw.w) < 0.15 ? 'active' : ''}`}
                    style={{ fontSize: '0.63rem', padding: '3px 4px' }}
                    onClick={() => {
                      setLineWidthMm(lw.w);
                      refreshPreview({ lineWidthMm: lw.w });
                    }}
                  >
                    {lw.label}
                  </button>
                ))}
              </div>
              <input
                type="range"
                min="0.8"
                max="3.6"
                step="0.1"
                value={lineWidthMm}
                onChange={(e) => {
                  const v = parseFloat(e.target.value);
                  setLineWidthMm(v);
                  schedulePreview({ lineWidthMm: v });
                }}
                style={{ width: '100%', accentColor: '#00f0ff' }}
              />

              {/* Smart toggles: Auto-bridges, Bg Removal, Mirror, Invert */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '5px', marginTop: '8px' }}>
                <button
                  type="button"
                  className={`btn-hud ${autoBridges ? 'active' : ''}`}
                  onClick={() => {
                    const next = !autoBridges;
                    setAutoBridges(next);
                    refreshPreview({ autoBridges: next });
                  }}
                  title="Relie automatiquement les détails isolés au trait voisin par de fins micro-ponts"
                >
                  {autoBridges ? '🔗 Ponts Auto : OUI' : '🔗 Ponts Auto : NON'}
                </button>
                <button
                  type="button"
                  className={`btn-hud ${removeBgAuto ? 'active' : ''}`}
                  onClick={() => {
                    const next = !removeBgAuto;
                    setRemoveBgAuto(next);
                    refreshPreview({ removeBgAuto: next });
                  }}
                  title="Détoure le sujet et élimine les petits logos/filigranes isolés dans les coins"
                >
                  {removeBgAuto ? '✨ Détourage : OUI' : '✨ Détourage : NON'}
                </button>
                <button
                  type="button"
                  className={`btn-hud ${mirrorHorizontal ? 'active' : ''}`}
                  onClick={() => {
                    const next = !mirrorHorizontal;
                    setMirrorHorizontal(next);
                    refreshPreview({ mirrorHorizontal: next });
                  }}
                >
                  {mirrorHorizontal ? '🔄 Miroir : ACTIF' : '🔄 Miroir : Normal'}
                </button>
                <button
                  type="button"
                  className={`btn-hud ${invertImage ? 'active' : ''}`}
                  onClick={() => {
                    const next = !invertImage;
                    setInvertImage(next);
                    refreshPreview({ invertImage: next });
                  }}
                >
                  {invertImage ? '🌓 Négatif : OUI' : '🌓 Négatif : NON'}
                </button>
              </div>
            </section>
          )}

          {/* SECTION 3: TEXTILE HEAT-PRESS CALIBRATION & 3D EXPORT */}
          {wpSessionId && (
            <section className="panel-card">
              <div className="panel-title">3. TAILLE DU WIRE &amp; EXPORT 3D (.STL)</div>

              <label className="field-label">
                Dimensions Réelles du Wire :{' '}
                <strong className="text-cyan">
                  {stats ? `${stats.width_mm} × ${stats.height_mm} mm` : `${targetWidthMm} mm`}
                </strong>
              </label>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '4px', marginBottom: '6px' }}>
                {[
                  { label: '❤️ Cœur (90mm)', w: 90, pos: { x: 61.0, y: 31.0 } },
                  { label: '👕 Torse (160mm)', w: 160, pos: { x: 50.0, y: 40.0 } },
                  { label: `🔥 Max (${maxSafeWidthMm}mm)`, w: maxSafeWidthMm, pos: { x: 50.0, y: 43.0 } },
                ].map((p) => (
                  <button
                    key={p.label}
                    type="button"
                    className={`btn-hud ${Math.abs(targetWidthMm - p.w) < 6 ? 'active' : ''}`}
                    style={{ fontSize: '0.64rem', padding: '4px 5px' }}
                    onClick={() => {
                      setTargetWidthMm(p.w);
                      setWirePos(p.pos);
                      refreshPreview({ targetWidthMm: p.w });
                    }}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
              <input
                type="range"
                min="50"
                max={maxSafeWidthMm}
                step="5"
                value={targetWidthMm}
                onChange={(e) => {
                  const v = parseFloat(e.target.value);
                  setTargetWidthMm(v);
                  schedulePreview({ targetWidthMm: v });
                }}
                style={{ width: '100%', accentColor: '#00f0ff' }}
              />

              <label className="field-label" style={{ marginTop: '8px' }}>
                Épaisseur Z du Transfert :{' '}
                <strong className="text-cyan">
                  {thicknessZMm.toFixed(2)} mm ({Math.round(thicknessZMm / 0.2)} couches à 0.20mm)
                </strong>
              </label>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '4px', marginBottom: '8px' }}>
                {[
                  { label: '🪶 Fin (0.40mm)', z: 0.4 },
                  { label: '👕 T-Shirt (0.60mm)', z: 0.6 },
                  { label: '🧥 Pull 3D (1.00mm)', z: 1.0 },
                ].map((pz) => (
                  <button
                    key={pz.label}
                    type="button"
                    className={`btn-hud ${Math.abs(thicknessZMm - pz.z) < 0.05 ? 'active' : ''}`}
                    style={{ fontSize: '0.64rem', padding: '4px 5px' }}
                    onClick={() => {
                      setThicknessZMm(pz.z);
                      refreshPreview({ thicknessZMm: pz.z });
                    }}
                  >
                    {pz.label}
                  </button>
                ))}
              </div>

              <div
                className="file-pill"
                style={{
                  marginBottom: '10px',
                  fontSize: '0.69rem',
                  lineHeight: 1.4,
                  borderColor: 'rgba(245, 158, 11, 0.4)',
                }}
              >
                🔥 <strong>Mémo Pressage ({selectedSpoolObj?.material || 'PLA+ / TPU'}) :</strong>{' '}
                {selectedSpoolObj?.material?.toUpperCase().includes('TPU')
                  ? '160 °C pendant 20 sec avec papier cuisson (lavable à 40 °C).'
                  : '165 °C pendant 15 sec avec papier cuisson (fusionne dans la maille coton).'}
              </div>

              <button
                type="button"
                className="btn-cyber primary-full"
                disabled={loading}
                onClick={handleGenerate3D}
              >
                {loading ? '⏳ Génération du Maillage Wire 3D...' : '🚀 Générer le Wire 3D (.STL & Guide Pressage)'}
              </button>

              {genResult && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '10px' }}>
                  <a
                    href={downloadStlUrl}
                    download
                    className="btn-cyber primary-full"
                    style={{ textAlign: 'center', textDecoration: 'none' }}
                  >
                    📥 Télécharger le Fichier .STL Prêt à Imprimer
                  </a>
                  <a
                    href={downloadZipUrl}
                    download
                    className="btn-cyber secondary"
                    style={{ textAlign: 'center', textDecoration: 'none' }}
                  >
                    📦 Télécharger le Pack Complet (.STL + Fiche Pressage .TXT)
                  </a>
                </div>
              )}
            </section>
          )}
        </div>
      </aside>

      {/* MAIN STUDIO WORKSPACE */}
      <main className="hf-studio-workspace">
        {!wpSessionId ? (
          <div className="hf-empty-studio">
            <div className="hf-empty-card">
              <div className="hf-empty-icon">👕</div>
              <h2>WIREPRESS 3D — STRUCTURE FILAIRE &amp; TRANSFERT VÊTEMENT</h2>
              <p style={{ marginBottom: '18px' }}>
                Transformez n&apos;importe quelle photo, personnage manga, coloriage ou logo en une{' '}
                <strong>structure filaire 3D (&quot;Wire Structure&quot;)</strong> haute précision, 100 % solidaire,
                prête à être imprimée en 3D et pressée à chaud sur un T-shirt, un Pull ou un Tote Bag.
              </p>
              <button
                type="button"
                className="btn-cyber primary"
                style={{ padding: '12px 24px', fontSize: '0.9rem' }}
                onClick={() => fileInputRef.current?.click()}
              >
                🖼️ Importer une Photo ou un Dessin
              </button>
            </div>
          </div>
        ) : (
          <>
            {/* TOP BAR */}
            <div className="hf-studio-topbar">
              <div className="hf-view-switcher">
                <button
                  type="button"
                  className={`hf-view-tab ${viewMode === 'studio_2d' ? 'active' : ''}`}
                  onClick={() => setViewMode('studio_2d')}
                >
                  👕 Studio Essayage Vêtement &amp; Wire (Côte-à-Côte)
                </button>
                <button
                  type="button"
                  className={`hf-view-tab ${viewMode === 'mesh_3d' ? 'active' : ''}`}
                  onClick={() => {
                    if (!genResult) handleGenerate3D();
                    setViewMode('mesh_3d');
                  }}
                >
                  🧊 Vue Maillage 3D (.STL)
                </button>
              </div>

              {stats && (
                <div className="hf-studio-topbar-right">
                  <span className="hf-meta-pill">
                    📏 {stats.width_mm} × {stats.height_mm} × {stats.thickness_z_mm} mm
                  </span>
                  <span className="hf-meta-pill">⚖️ ~{stats.filament_grams} g</span>
                  <span className="hf-meta-pill">⏱️ ~{stats.estimated_print_min} min</span>
                  <span
                    className="hf-meta-pill"
                    style={{
                      borderColor: stats.islands_after <= 1 ? '#10b981' : '#f59e0b',
                      color: stats.islands_after <= 1 ? '#34d399' : '#fbbf24',
                    }}
                  >
                    {stats.islands_after <= 1
                      ? '✅ 1 Seul Bloc Solidaire'
                      : `⚠️ ${stats.islands_after} pièces séparées`}
                  </span>
                </div>
              )}
            </div>

            {viewMode === 'mesh_3d' && previewStlUrl ? (
              <div style={{ flex: 1, position: 'relative' }}>
                <Viewer3D stlUrl={previewStlUrl} modelStats={null} bedSize={bedSize} showRod={false} />
              </div>
            ) : (
              <div className="hf-dual-studio-container">
                <div className="hf-dual-studio-grid">
                  {/* LEFT CARD: SOURCE PHOTO & INTERACTIVE FRAMING */}
                  <div className="hf-studio-card">
                    <div className="hf-studio-card-header">
                      <div>
                        <span className="hf-step-tag">ÉTAPE A</span>
                        <span className="hf-card-title">IMAGE D&apos;ORIGINE &amp; CADRAGE DU SUJET</span>
                      </div>
                      <button
                        type="button"
                        className="btn-hud"
                        style={{ fontSize: '0.68rem', padding: '3px 8px' }}
                        onClick={() => {
                          setZoom(1.0);
                          setOffsetXPct(0.0);
                          setOffsetYPct(0.0);
                          refreshPreview({ zoom: 1.0, offsetXPct: 0.0, offsetYPct: 0.0 });
                        }}
                      >
                        🎯 Réinitialiser Cadrage
                      </button>
                    </div>

                    <div
                      className="hf-studio-viewport interactive-pan"
                      onMouseDown={handleSourceMouseDown}
                      onWheel={handleSourceWheel}
                      title="Glissez l'image à la souris ou utilisez la molette pour zoomer/recadrer"
                    >
                      {sourcePreviewUrl && (
                        <img src={sourcePreviewUrl} alt="Photo source" draggable={false} />
                      )}
                      <div className="hf-viewport-overlay-hint">
                        🖱️ Glisser : Recadrer • Molette : Zoom Sujet (×{zoom.toFixed(2)})
                      </div>
                    </div>

                    <div className="hf-studio-palette-footer">
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px' }}>
                        <div>
                          <label className="field-label" style={{ margin: 0 }}>
                            Zoom Image : <strong>×{zoom.toFixed(2)}</strong>
                          </label>
                          <input
                            type="range"
                            min="0.50"
                            max="2.50"
                            step="0.05"
                            value={zoom}
                            onChange={(e) => {
                              const v = parseFloat(e.target.value);
                              setZoom(v);
                              schedulePreview({ zoom: v });
                            }}
                            style={{ width: '100%' }}
                          />
                        </div>
                        <div>
                          <label className="field-label" style={{ margin: 0 }}>
                            Décalage X : <strong>{offsetXPct}%</strong>
                          </label>
                          <input
                            type="range"
                            min="-60"
                            max="60"
                            step="2"
                            value={offsetXPct}
                            onChange={(e) => {
                              const v = parseFloat(e.target.value);
                              setOffsetXPct(v);
                              schedulePreview({ offsetXPct: v });
                            }}
                            style={{ width: '100%' }}
                          />
                        </div>
                        <div>
                          <label className="field-label" style={{ margin: 0 }}>
                            Décalage Y : <strong>{offsetYPct}%</strong>
                          </label>
                          <input
                            type="range"
                            min="-60"
                            max="60"
                            step="2"
                            value={offsetYPct}
                            onChange={(e) => {
                              const v = parseFloat(e.target.value);
                              setOffsetYPct(v);
                              schedulePreview({ offsetYPct: v });
                            }}
                            style={{ width: '100%' }}
                          />
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* RIGHT CARD: INTERACTIVE GARMENT TRY-ON & DRAGGABLE/RESIZABLE WIRE */}
                  <div className="hf-studio-card">
                    <div className="hf-studio-card-header">
                      <div>
                        <span className="hf-step-tag pink">ÉTAPE B</span>
                        <span className="hf-card-title">
                          CABINE D&apos;ESSAYAGE ({GARMENT_TYPES.find((g) => g.id === garmentType)?.label})
                        </span>
                      </div>

                      {/* Quick placement & zoom buttons */}
                      <div style={{ display: 'flex', gap: '5px', alignItems: 'center', flexWrap: 'wrap' }}>
                        <button
                          type="button"
                          className="btn-hud"
                          style={{ fontSize: '0.66rem', padding: '3px 7px' }}
                          onClick={() => setWirePos({ x: 50.0, y: 40.0 })}
                          title="Aligner parfaitement le Wire au centre de la poitrine"
                        >
                          🎯 Centrer Wire
                        </button>
                        <button
                          type="button"
                          className="btn-hud"
                          style={{ fontSize: '0.66rem', padding: '3px 7px' }}
                          onClick={() => {
                            setWirePos({ x: 61.0, y: 31.0 });
                            setTargetWidthMm(90);
                            refreshPreview({ targetWidthMm: 90 });
                          }}
                          title="Placer le Wire en écusson sur le cœur (côté gauche du T-shirt)"
                        >
                          ❤️ Position Cœur
                        </button>
                        <button
                          type="button"
                          className="btn-hud"
                          style={{ fontSize: '0.66rem', padding: '3px 7px' }}
                          onClick={() => {
                            setGarmentZoom(0.88);
                            setGarmentPan({ x: 0, y: 0 });
                          }}
                          title="Réinitialiser le zoom du T-shirt"
                        >
                          👕 Vue 100%
                        </button>
                      </div>
                    </div>

                    {/* Interactive Garment Viewport */}
                    <div
                      className="hf-studio-viewport"
                      onMouseDown={handleStartPanGarment}
                      onWheel={handleGarmentWheel}
                      style={{
                        position: 'relative',
                        background: 'radial-gradient(circle at 50% 42%, #1e293b 0%, #070b14 100%)',
                        cursor: 'grab',
                      }}
                    >
                      {/* Scalable & Pannable Garment Stage (Fixed 560:580 aspect ratio so coordinates never distort) */}
                      <div
                        ref={garmentStageRef}
                        style={{
                          position: 'relative',
                          height: '92%',
                          aspectRatio: '560 / 580',
                          maxWidth: '94%',
                          transform: `translate(${garmentPan.x}px, ${garmentPan.y}px) scale(${garmentZoom})`,
                          transformOrigin: 'center center',
                          transition: dragStateRef.current ? 'none' : 'transform 0.1s ease-out',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                        }}
                      >
                        {renderGarmentSvg()}

                        {/* Center alignment vertical axis guide when centered */}
                        {(isDraggingWire || isResizingWire) && isCenteredX && (
                          <div
                            style={{
                              position: 'absolute',
                              top: '8%',
                              bottom: '8%',
                              left: '50%',
                              width: '1px',
                              borderLeft: '1.5px dashed #00f0ff',
                              pointerEvents: 'none',
                              zIndex: 4,
                            }}
                          />
                        )}

                        {/* DRAGGABLE & RESIZABLE WIRE OVERLAY ON THE GARMENT */}
                        {wireRgbaUrl && (
                          <div
                            onMouseDown={handleStartMoveWire}
                            title="Glissez pour déplacer le Wire sur le T-shirt • Tirez les coins pour agrandir/réduire"
                            style={{
                              position: 'absolute',
                              left: `${wirePos.x}%`,
                              top: `${wirePos.y}%`,
                              width: `${wireWidthPct}%`,
                              transform: 'translate(-50%, -50%)',
                              cursor: isDraggingWire ? 'grabbing' : 'move',
                              zIndex: 5,
                              padding: '3px',
                              borderRadius: '6px',
                              border:
                                isDraggingWire || isResizingWire
                                  ? '1.5px dashed #00f0ff'
                                  : '1px dashed rgba(0, 240, 255, 0.35)',
                              background:
                                isDraggingWire || isResizingWire ? 'rgba(0, 240, 255, 0.06)' : 'transparent',
                              userSelect: 'none',
                            }}
                          >
                            <img
                              src={wireRgbaUrl}
                              alt="Wire Structure 3D"
                              draggable={false}
                              style={{
                                width: '100%',
                                height: 'auto',
                                display: 'block',
                                objectFit: 'contain',
                                filter: 'drop-shadow(0px 3px 5px rgba(0, 0, 0, 0.55))',
                                pointerEvents: 'none',
                              }}
                            />

                            {/* Bottom-Right Interactive Resize Handle */}
                            <div
                              onMouseDown={(e) => handleStartResizeWire(e, 1, 1)}
                              title="Tirer pour agrandir ou réduire le Wire"
                              style={{
                                position: 'absolute',
                                right: '-6px',
                                bottom: '-6px',
                                width: '13px',
                                height: '13px',
                                borderRadius: '3px',
                                background: '#00f0ff',
                                border: '2px solid #090d16',
                                cursor: 'nwse-resize',
                                boxShadow: '0 0 6px rgba(0,240,255,0.8)',
                              }}
                            />
                            {/* Top-Left Interactive Resize Handle */}
                            <div
                              onMouseDown={(e) => handleStartResizeWire(e, -1, -1)}
                              title="Tirer pour agrandir ou réduire le Wire"
                              style={{
                                position: 'absolute',
                                left: '-6px',
                                top: '-6px',
                                width: '11px',
                                height: '11px',
                                borderRadius: '3px',
                                background: '#00f0ff',
                                border: '2px solid #090d16',
                                cursor: 'nwse-resize',
                              }}
                            />
                          </div>
                        )}
                      </div>

                      <div className="hf-viewport-overlay-hint">
                        🖐️ Glissez le Wire pour le placer • Coins bleus : Agrandir/Réduire ({targetWidthMm}mm) • Molette : Zoom T-Shirt (×{garmentZoom.toFixed(2)})
                      </div>
                    </div>

                    {/* Bottom Controls: Zoom T-Shirt + Taille Wire + Type & Couleur Vêtement */}
                    <div className="hf-studio-palette-footer">
                      {/* Row 1: Sliders for T-shirt Zoom & Wire Size */}
                      <div
                        style={{
                          display: 'grid',
                          gridTemplateColumns: '1fr 1fr',
                          gap: '12px',
                          paddingBottom: '6px',
                          borderBottom: '1px solid #1e293b',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span style={{ fontSize: '0.68rem', color: '#94a3b8', whiteSpace: 'nowrap' }}>
                            🔍 Zoom Vêtement : <strong className="text-cyan">{Math.round(garmentZoom * 100)}%</strong>
                          </span>
                          <input
                            type="range"
                            min="0.50"
                            max="2.20"
                            step="0.05"
                            value={garmentZoom}
                            onChange={(e) => setGarmentZoom(parseFloat(e.target.value))}
                            style={{ flex: 1, accentColor: '#00f0ff' }}
                          />
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span style={{ fontSize: '0.68rem', color: '#94a3b8', whiteSpace: 'nowrap' }}>
                            📐 Taille Wire : <strong className="text-cyan">{targetWidthMm} mm</strong>
                          </span>
                          <input
                            type="range"
                            min="50"
                            max={maxSafeWidthMm}
                            step="5"
                            value={targetWidthMm}
                            onChange={(e) => {
                              const v = parseFloat(e.target.value);
                              setTargetWidthMm(v);
                              schedulePreview({ targetWidthMm: v }, 90);
                            }}
                            style={{ flex: 1, accentColor: '#00f0ff' }}
                          />
                        </div>
                      </div>

                      {/* Row 2: Garment Type & Fabric Color Swatches */}
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          flexWrap: 'wrap',
                          gap: '8px',
                          paddingTop: '2px',
                        }}
                      >
                        <div style={{ display: 'flex', gap: '4px' }}>
                          {GARMENT_TYPES.map((gt) => (
                            <button
                              key={gt.id}
                              type="button"
                              className={`btn-hud ${garmentType === gt.id ? 'active' : ''}`}
                              style={{ fontSize: '0.66rem', padding: '3px 7px' }}
                              onClick={() => setGarmentType(gt.id)}
                            >
                              {gt.label}
                            </button>
                          ))}
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <span style={{ fontSize: '0.67rem', color: '#94a3b8', marginRight: '2px' }}>
                            Tissu :
                          </span>
                          {GARMENT_COLORS.map((gc) => (
                            <button
                              key={gc.hex}
                              type="button"
                              className={`spool-dot ${
                                garmentColor.toLowerCase() === gc.hex.toLowerCase() ? 'selected' : ''
                              }`}
                              style={{
                                backgroundColor: gc.hex,
                                width: '18px',
                                height: '18px',
                                border:
                                  garmentColor.toLowerCase() === gc.hex.toLowerCase()
                                    ? '2px solid #00f0ff'
                                    : '1px solid rgba(255,255,255,0.35)',
                              }}
                              title={`Vêtement : ${gc.name}`}
                              onClick={() => setGarmentColor(gc.hex)}
                            />
                          ))}
                          <input
                            type="color"
                            value={garmentColor}
                            onChange={(e) => setGarmentColor(e.target.value)}
                            className="color-Swatch-input"
                            style={{ width: '22px', height: '20px' }}
                            title="Choisir une autre couleur de vêtement"
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
