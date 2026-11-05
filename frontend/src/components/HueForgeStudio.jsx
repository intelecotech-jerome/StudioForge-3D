import React, { useState, useRef, useEffect } from 'react';
import Viewer3D from './Viewer3D';

const API_BASE = 'http://127.0.0.1:8000';

const LAYOUT_OPTIONS = [
  {
    group: 'Forme Unique (Calibrée selon le Plateau de votre Imprimante)',
    items: [
      { value: 'single_original', label: '🖼️ Format Original (Proportions conservées)', unitLabel: 'Dimension Principale (mm)', defaultSize: 220 },
      { value: 'single_heart', label: '❤️ Cœur Unique', unitLabel: 'Largeur du Cœur (mm)', defaultSize: 200 },
      { value: 'single_star5', label: '⭐ Étoile à 5 Branches Unique', unitLabel: "Envergure de l'Étoile (mm)", defaultSize: 210 },
      { value: 'single_shield', label: '🛡️ Blason / Écusson Héraldique', unitLabel: 'Hauteur du Blason (mm)', defaultSize: 200 },
      { value: 'single_arch', label: '⛩️ Arche / Vitrail Gothique', unitLabel: "Hauteur de l'Arche (mm)", defaultSize: 220 },
      { value: 'single_diamond', label: '💎 Losange / Diamant Unique', unitLabel: 'Hauteur du Losange (mm)', defaultSize: 210 },
      { value: 'single_octagon', label: '🛑 Octogone Régulier Unique', unitLabel: "Largeur de l'Octogone (mm)", defaultSize: 200 },
      { value: 'single_circle', label: '⭕ Cercle Unique', unitLabel: 'Diamètre du Cercle (mm)', defaultSize: 220 },
      { value: 'single_hexagon', label: '⬡ Hexagone Unique', unitLabel: "Taille d'un Côté / Rayon (mm)", defaultSize: 115 },
      { value: 'single_square', label: '⬛ Carré Unique', unitLabel: "Taille d'un Côté (mm)", defaultSize: 200 },
      { value: 'single_triangle', label: '🔺 Triangle Équilatéral Unique', unitLabel: "Taille d'un Côté (mm)", defaultSize: 220 },
    ],
  },
  {
    group: 'Multi-Frames Muraux (Découpe Auto + Clips Mâles/Femelles)',
    items: [
      { value: 'multi_4_squares', label: '⊞ Grille 4 Carrés (2×2)', unitLabel: "Côté d'un Carré (mm) — ex: 200mm = 400×400", defaultSize: 200 },
      { value: 'multi_grid_squares', label: '🧩 Grille sur mesure N × M Carrés (Horizontal / Vertical)', unitLabel: "Côté d'un Carré (mm)", defaultSize: 200 },
      { value: 'multi_7_hexagons', label: '❖ Rosace 7 Hexagones (1 Central + 6 Autour)', unitLabel: "Taille d'un Côté d'Hexagone (mm)", defaultSize: 105 },
      { value: 'multi_6_triangles', label: '✡️ Rosace 6 Triangles (Formant un Grand Hexagone)', unitLabel: "Taille d'un Côté de Triangle (mm)", defaultSize: 180 },
      { value: 'multi_4_triangles', label: '▲ Pyramide 4 Triangles (Formant un Grand Triangle 2×)', unitLabel: "Taille d'un Côté de Triangle (mm)", defaultSize: 180 },
    ],
  },
];

const ART_STYLE_OPTIONS = [
  {
    value: 'standard',
    shortLabel: '🎨 Standard Fidèle',
    title: 'HueForge Standard Fidèle',
    desc: "Rendu optique continu fidèle à l'image originale (base sombre en bas, reflets clairs au sommet).",
  },
  {
    value: 'intaglio_splash',
    shortLabel: '💥 Gravure Splash',
    title: 'Gravure Splash & Pochoir (Intaglio sur Fond Blanc Haut)',
    desc: "Style gravé en creux sur fond blanc : hisse le fond au plateau Blanc supérieur, génère un halo d'éclaboussures & gouttelettes dans les couches intermédiaires, et creuse le personnage jusqu'au Noir profond.",
  },
  {
    value: 'stained_glass_ink',
    shortLabel: '✒️ Vitrail Encré',
    title: 'Vitrail / Comic Encré (Ordre Inversé : Blanc en Bas ➔ Noir au Sommet)',
    desc: "Inverse automatiquement l'ordre des bobines : base Blanche lumineuse en bas (CFS1-A), couleurs vives au milieu, et traits d'encre noirs + contours manga en relief tout au sommet !",
  },
  {
    value: 'papercut_terraced',
    shortLabel: '🗂️ Papier Découpé',
    title: 'Papier Découpé 3D / Shadowbox (Paliers Plats & Lisses)',
    desc: 'Lisse les micro-textures et quantifie le relief en paliers horizontaux francs comme des feuilles de papier découpées au laser.',
  },
  {
    value: 'halftone_manga',
    shortLabel: '📰 Pop-Art Trame',
    title: 'Pop-Art Trame Manga / Spider-Verse (Points Halftone 3D)',
    desc: 'Convertit les transitions de couleurs en trame géométrique de points inclinés à 45° imprimés en micro-relief 3D.',
  },
  {
    value: 'cyber_neon',
    shortLabel: '⚡ Néon Cyber',
    title: 'Néon Cyberpunk / Aura Électrique (Fond Noir Bas + Contours Lumineux)',
    desc: 'Plonge le fond dans le Noir mat profond (couche de base) et fait jaillir les contours lumineux et auras saturées au sommet.',
  },
];

function computeLayoutAspect(mode, cols, rows, imgAspect) {
  if (mode === 'single_original') return imgAspect || 1.0;
  if (mode === 'multi_grid_squares') {
    const c = Math.max(1, Number(cols) || 2);
    const r = Math.max(1, Number(rows) || 2);
    return c / r;
  }
  if (mode === 'single_hexagon') return 2.0 / Math.sqrt(3.0);
  if (mode === 'multi_7_hexagons') return 5.0 / (3.0 * Math.sqrt(3.0));
  if (mode === 'single_triangle' || mode === 'multi_4_triangles') return 2.0 / Math.sqrt(3.0);
  if (mode === 'multi_6_triangles') return 2.0 / Math.sqrt(3.0);
  if (mode === 'single_diamond') return 0.80;
  if (mode === 'single_shield') return 0.86;
  if (mode === 'single_arch') return 0.76;
  if (mode === 'single_heart') return 1.04;
  return 1.0;
}

function computeOptimalZoomClient(imgSizePx, mode, cols, rows) {
  const w = imgSizePx?.[0] || 1000;
  const h = imgSizePx?.[1] || 1000;
  const imgAspect = Math.max(0.15, Math.min(6.0, w / Math.max(1, h)));
  const layAspect = Math.max(0.15, Math.min(6.0, computeLayoutAspect(mode, cols, rows, imgAspect)));
  const containZ = Math.min(layAspect / imgAspect, imgAspect / layAspect);
  const opt = containZ < 0.96 ? Math.min(1.0, containZ * 1.05) : 1.0;
  return Number(Math.max(0.35, Math.min(1.0, opt)).toFixed(2));
}

function computeFramingMetrics(imgSizePx, mode, cols, rows, zoomVal) {
  const srcW = Math.max(1, Number(imgSizePx?.[0]) || 1000);
  const srcH = Math.max(1, Number(imgSizePx?.[1]) || 1000);
  const srcAspect = srcW / srcH;
  const targetAspect = Math.max(0.15, Math.min(6.0, computeLayoutAspect(mode, cols, rows, srcAspect)));
  const baseCropW = srcAspect > targetAspect ? srcH * targetAspect : srcW;
  const baseCropH = srcAspect > targetAspect ? srcH : srcW / targetAspect;
  const z = Math.max(0.30, Math.min(4.0, Number(zoomVal) || 1.0));
  const cropW = baseCropW / z;
  const cropH = baseCropH / z;
  const panSpanX = Math.max(srcW * 0.65, Math.abs(srcW - cropW) * 0.55);
  const panSpanY = Math.max(srcH * 0.65, Math.abs(srcH - cropH) * 0.55);
  return { srcW, srcH, targetAspect, baseCropW, baseCropH, z, cropW, cropH, panSpanX, panSpanY };
}

function computeSingleTileDimsClient(mode, sizeMm, imgSizePx) {
  const s = Number(sizeMm) || 100;
  if (mode === 'single_hexagon' || mode === 'multi_7_hexagons') {
    return [Number((2.0 * s).toFixed(1)), Number((Math.sqrt(3.0) * s).toFixed(1))];
  }
  if (mode === 'single_triangle' || mode === 'multi_6_triangles' || mode === 'multi_4_triangles') {
    return [Number(s.toFixed(1)), Number(((Math.sqrt(3.0) / 2.0) * s).toFixed(1))];
  }
  if (mode === 'single_diamond') {
    return [Number((0.80 * s).toFixed(1)), Number(s.toFixed(1))];
  }
  if (mode === 'single_shield') {
    return [Number((0.86 * s).toFixed(1)), Number(s.toFixed(1))];
  }
  if (mode === 'single_arch') {
    return [Number((0.76 * s).toFixed(1)), Number(s.toFixed(1))];
  }
  if (mode === 'single_heart') {
    return [Number(s.toFixed(1)), Number((0.95 * s).toFixed(1))];
  }
  if (mode === 'single_original') {
    const w = imgSizePx?.[0] || 1000;
    const h = imgSizePx?.[1] || 1000;
    const aspect = w / Math.max(1, h);
    if (aspect >= 1.0) {
      return [Number(s.toFixed(1)), Number((s / aspect).toFixed(1))];
    }
    return [Number((s * aspect).toFixed(1)), Number(s.toFixed(1))];
  }
  return [Number(s.toFixed(1)), Number(s.toFixed(1))];
}

function computeMaxSafeSizeForBed(mode, bedX, bedY, imgSizePx) {
  const safeX = Math.max(50, (Number(bedX) || 260) - 2);
  const safeY = Math.max(50, (Number(bedY) || 260) - 2);
  if (mode === 'single_hexagon' || mode === 'multi_7_hexagons') {
    return Math.floor(Math.min(safeX / 2.0, safeY / Math.sqrt(3.0)));
  }
  if (mode === 'single_triangle' || mode === 'multi_6_triangles' || mode === 'multi_4_triangles') {
    return Math.floor(Math.min(safeX, safeY / (Math.sqrt(3.0) / 2.0)));
  }
  if (mode === 'single_diamond') {
    return Math.floor(Math.min(safeX / 0.80, safeY));
  }
  if (mode === 'single_shield') {
    return Math.floor(Math.min(safeX / 0.86, safeY));
  }
  if (mode === 'single_arch') {
    return Math.floor(Math.min(safeX / 0.76, safeY));
  }
  if (mode === 'single_original') {
    const w = imgSizePx?.[0] || 1000;
    const h = imgSizePx?.[1] || 1000;
    const aspect = w / Math.max(1, h);
    if (aspect >= 1.0) return Math.floor(Math.min(safeX, safeY * aspect));
    return Math.floor(Math.min(safeY, safeX / aspect));
  }
  return Math.floor(Math.min(safeX, safeY));
}

export default function HueForgeStudio({
  printerPreset,
  onChangePrinterPreset,
  spoolsRefreshTick = 0,
  onOpenSpoolSetup,
  onOpenPrinterSetup,
}) {
  const fileInputRef = useRef(null);
  const [loading, setLoading] = useState(false);
  const [hfSessionId, setHfSessionId] = useState(null);
  const [filename, setFilename] = useState('');
  const [imageSizePx, setImageSizePx] = useState([1000, 1000]);
  const [recommendedColors, setRecommendedColors] = useState(5);
  const [numColors, setNumColors] = useState(5);
  const [paletteMode, setPaletteMode] = useState('ai_recommended'); // 'ai_recommended' | 'in_stock_spools'
  const [colorEngine, setColorEngine] = useState('hsv_ramp'); // 'hsv_ramp' | 'cie_delta_e'
  const [artStyle, setArtStyle] = useState('standard'); // 'standard' | 'intaglio_splash' | 'stained_glass_ink' | 'papercut_terraced' | 'halftone_manga' | 'cyber_neon'
  const [artIntensity, setArtIntensity] = useState(1.0);
  const [deltaEInfo, setDeltaEInfo] = useState(null);
  const [palettesByK, setPalettesByK] = useState({});
  const [stockPalettesByK, setStockPalettesByK] = useState({});
  const [activePalette, setActivePalette] = useState([]);
  const [previewDataUrl, setPreviewDataUrl] = useState(null);
  const [sourcePreviewDataUrl, setSourcePreviewDataUrl] = useState(null);
  const [shapeOverlayDataUrl, setShapeOverlayDataUrl] = useState(null);
  const [committedFrame, setCommittedFrame] = useState({ zoom: 1.0, offsetXPct: 0.0, offsetYPct: 0.0 });
  const [voidPct, setVoidPct] = useState(0.0);
  const [fillMode, setFillMode] = useState('smart_aura'); // 'smart_aura' | 'edge_stretch' | 'mirror_blend' | 'solid_edge' | 'none_preview'
  const [hasValidatedOutpaint, setHasValidatedOutpaint] = useState(false);
  const [viewMode, setViewMode] = useState('studio_2d'); // 'studio_2d' | 'mesh_3d'
  const [highlightLayerIdx, setHighlightLayerIdx] = useState(null); // null or 0..K-1 (Loupe de Couche)

  // User's Configured Spool Library & Printer Fleet
  const [userSpools, setUserSpools] = useState([]);
  const [printers, setPrinters] = useState([]);

  // HueForge Pro Optical & Image Enhancement Controls
  const [tdMm, setTdMm] = useState(2.0);
  const [detailBoost, setDetailBoost] = useState(1.35);
  const [contrastGamma, setContrastGamma] = useState(1.0);
  const [zoom, setZoom] = useState(1.0);
  const [autoOptimalZoom, setAutoOptimalZoom] = useState(true);
  const [offsetXPct, setOffsetXPct] = useState(0.0);
  const [offsetYPct, setOffsetYPct] = useState(0.0);

  // Interactive 2D Preview Drag & Zoom State
  const [largePreview, setLargePreview] = useState(false);
  const [dragDeltaPx, setDragDeltaPx] = useState([0, 0]);
  const dragStateRef = useRef({ active: false, startX: 0, startY: 0, baseOffX: 0, baseOffY: 0 });
  const leftImgRef = useRef(null);
  const previewDebounceRef = useRef(null);
  const previewAbortRef = useRef(null);

  // Geometry, Border Rim & Slicing Parameters
  const [layoutMode, setLayoutMode] = useState('single_hexagon');
  const [sizeMm, setSizeMm] = useState(115);
  const [gridCols, setGridCols] = useState(4);
  const [gridRows, setGridRows] = useState(2);
  const [baseThicknessMm, setBaseThicknessMm] = useState(0.88);
  const [reliefHeightMm, setReliefHeightMm] = useState(1.60);
  const [borderStyle, setBorderStyle] = useState('raised_top');
  const [borderWidthMm, setBorderWidthMm] = useState(2.5);
  const [gridResolution, setGridResolution] = useState(380);
  const [verticalExaggeration, setVerticalExaggeration] = useState(2.5);
  const [addBackConnectors, setAddBackConnectors] = useState(true);

  // Generated 3D Output
  const [genResult, setGenResult] = useState(null);
  const [stlVersion, setStlVersion] = useState(0);

  // Load configured spools and printers from backend
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
        if (d.printers && d.printers.length > 0) {
          setPrinters(d.printers);
          const hfList = d.printers.filter((p) => p.use_hueforge !== false);
          if (hfList.length > 0 && !hfList.some((p) => p.id === printerPreset)) {
            onChangePrinterPreset(hfList[0].id);
          }
        }
      })
      .catch((err) => console.error('Erreur chargement imprimantes:', err));
  }, [spoolsRefreshTick]);

  const favoriteSpools = userSpools.filter((s) => s.is_favorite !== false);
  const inStockSpools = userSpools.filter((s) => s.in_stock !== false);
  const outOfStockSpools = userSpools.filter((s) => s.in_stock === false);

  const hueforgePrinters =
    printers.filter((p) => p.use_hueforge !== false).length > 0
      ? printers.filter((p) => p.use_hueforge !== false)
      : [
          {
            id: 'creality_hi',
            name: 'Creality Hi (Combo 2× CFS)',
            bed_x_mm: 260,
            bed_y_mm: 260,
            bed_z_mm: 300,
            max_colors: 8,
            use_hueforge: true,
          },
        ];

  const activePrinter =
    hueforgePrinters.find((p) => p.id === printerPreset) ||
    printers.find((p) => p.id === printerPreset) ||
    hueforgePrinters[0];

  const bedSize = [
    activePrinter?.bed_x_mm || 260,
    activePrinter?.bed_y_mm || 260,
    activePrinter?.bed_z_mm || 300,
  ];

  // Real-time check: does each individual tile fit on the selected printer's bed?
  const singleTileDimsMm = computeSingleTileDimsClient(layoutMode, sizeMm, imageSizePx);
  const exceedsBedX = singleTileDimsMm[0] > bedSize[0] + 0.1;
  const exceedsBedY = singleTileDimsMm[1] > bedSize[1] + 0.1;
  const exceedsPrinterBed = exceedsBedX || exceedsBedY;
  const maxSafeSizeMm = computeMaxSafeSizeForBed(layoutMode, bedSize[0], bedSize[1], imageSizePx);
  const optimalZoomForCurrent = computeOptimalZoomClient(imageSizePx, layoutMode, gridCols, gridRows);

  const currentLayoutMeta =
    LAYOUT_OPTIONS.flatMap((g) => g.items).find((i) => i.value === layoutMode) ||
    LAYOUT_OPTIONS[0].items[0];

  const handleLayoutChange = (newMode) => {
    setLayoutMode(newMode);
    const meta = LAYOUT_OPTIONS.flatMap((g) => g.items).find((i) => i.value === newMode);
    const nextSize = meta ? meta.defaultSize : sizeMm;
    if (meta) setSizeMm(nextSize);
    const nextZoom = autoOptimalZoom
      ? computeOptimalZoomClient(imageSizePx, newMode, gridCols, gridRows)
      : zoom;
    if (autoOptimalZoom) {
      setZoom(nextZoom);
      setOffsetXPct(0.0);
      setOffsetYPct(0.0);
    }
    if (hfSessionId) {
      refreshPalettePreview({
        layoutMode: newMode,
        sizeMm: nextSize,
        zoom: nextZoom,
        offsetXPct: autoOptimalZoom ? 0.0 : offsetXPct,
        offsetYPct: autoOptimalZoom ? 0.0 : offsetYPct,
      });
    }
  };

  const handleGridDimsChange = (newCols, newRows) => {
    const c = Math.max(1, Math.min(10, parseInt(newCols, 10) || 1));
    const r = Math.max(1, Math.min(10, parseInt(newRows, 10) || 1));
    setGridCols(c);
    setGridRows(r);
    const nextZoom = autoOptimalZoom
      ? computeOptimalZoomClient(imageSizePx, 'multi_grid_squares', c, r)
      : zoom;
    if (autoOptimalZoom) {
      setZoom(nextZoom);
      setOffsetXPct(0.0);
      setOffsetYPct(0.0);
    }
    if (hfSessionId) {
      refreshPalettePreview({
        layoutMode: 'multi_grid_squares',
        gridCols: c,
        gridRows: r,
        zoom: nextZoom,
        offsetXPct: autoOptimalZoom ? 0.0 : offsetXPct,
        offsetYPct: autoOptimalZoom ? 0.0 : offsetYPct,
      });
    }
  };

  const handleUploadImage = async (file) => {
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch(`${API_BASE}/api/hueforge/upload-image`, {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Erreur lors de l'analyse de l'image");

      const uploadedSizePx = data.image_size_px || data.image_dimensions || [1000, 1000];
      setImageSizePx(uploadedSizePx);
      setHfSessionId(data.session_id);
      setFilename(data.filename);
      setRecommendedColors(data.recommended_colors);
      setNumColors(data.recommended_colors);
      setPalettesByK(data.palettes_by_k);
      setStockPalettesByK(data.stock_palettes_by_k || {});
      setPaletteMode('ai_recommended');
      setActivePalette(data.active_palette);
      setPreviewDataUrl(data.preview_data_url);
      setSourcePreviewDataUrl(data.source_preview_data_url || data.preview_data_url);
      setShapeOverlayDataUrl(data.shape_overlay_data_url || null);
      setVoidPct(data.void_pct ?? 0.0);
      setHasValidatedOutpaint(Boolean(data.has_validated_outpaint));
      setFillMode('smart_aura');
      const optZ = computeOptimalZoomClient(uploadedSizePx, layoutMode, gridCols, gridRows);
      setZoom(optZ);
      setOffsetXPct(0.0);
      setOffsetYPct(0.0);
      setDragDeltaPx([0, 0]);
      setCommittedFrame({ zoom: data.optimal_zoom ?? optZ, offsetXPct: 0.0, offsetYPct: 0.0 });
      setGenResult(null);
      setViewMode('studio_2d');

      // If current layout, artStyle or optimal zoom differs from default upload preview, sync immediately
      if (layoutMode !== 'single_hexagon' || Math.abs(optZ - 1.0) > 0.01 || artStyle !== 'standard') {
        const resSync = await fetch(`${API_BASE}/api/hueforge/${data.session_id}/preview-palette`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            layout_mode: layoutMode,
            size_mm: sizeMm,
            grid_cols: gridCols,
            grid_rows: gridRows,
            printer_id: activePrinter?.id || printerPreset,
            base_thickness_mm: baseThicknessMm,
            relief_height_mm: reliefHeightMm,
            num_colors: data.recommended_colors,
            palette_mode: 'ai_recommended',
            color_engine: colorEngine,
            art_style: artStyle,
            art_intensity: artIntensity,
            custom_hex_colors: data.active_palette.map((c) => c.hex_color),
            custom_end_layer_nums: data.active_palette.map((c) => c.end_layer_num),
            td_mm: tdMm,
            detail_boost: detailBoost,
            contrast_gamma: contrastGamma,
            zoom: optZ,
            offset_x_pct: 0.0,
            offset_y_pct: 0.0,
            fill_mode: 'smart_aura',
            border_style: borderStyle,
            border_width_mm: borderWidthMm,
            add_back_connectors: addBackConnectors,
          }),
        });
        const dataSync = await resSync.json();
        if (resSync.ok) {
          setActivePalette(dataSync.active_palette);
          setPreviewDataUrl(dataSync.preview_data_url);
          if (dataSync.source_preview_data_url) setSourcePreviewDataUrl(dataSync.source_preview_data_url);
          if (dataSync.shape_overlay_data_url !== undefined) setShapeOverlayDataUrl(dataSync.shape_overlay_data_url);
          if (dataSync.void_pct !== undefined) setVoidPct(dataSync.void_pct);
          setCommittedFrame({ zoom: optZ, offsetXPct: 0.0, offsetYPct: 0.0 });
        }
      }
    } catch (e) {
      alert(e.message);
    } finally {
      setLoading(false);
    }
  };

  const refreshPalettePreview = async (overrides = {}) => {
    if (!hfSessionId) return;
    if (previewAbortRef.current) {
      previewAbortRef.current.abort();
    }
    const controller = new AbortController();
    previewAbortRef.current = controller;

    const targetK = overrides.numColors ?? numColors;
    const targetMode = overrides.paletteMode ?? paletteMode;
    const targetEngine = overrides.colorEngine ?? colorEngine;
    const targetArtStyle = overrides.artStyle ?? artStyle;
    const targetArtIntensity = overrides.artIntensity ?? artIntensity;
    const targetFill = overrides.fillMode ?? fillMode;
    const targetPalette = overrides.palette ?? activePalette;
    const hexList = overrides.customHexColors !== undefined ? overrides.customHexColors : targetPalette.map((c) => c.hex_color);
    const endLayers = overrides.customEndLayers !== undefined ? overrides.customEndLayers : targetPalette.map((c) => c.end_layer_num);
    const reqZoom = overrides.zoom ?? zoom;
    const reqOffX = overrides.offsetXPct ?? offsetXPct;
    const reqOffY = overrides.offsetYPct ?? offsetYPct;
    const targetHighlight =
      overrides.highlightLayerIdx !== undefined ? overrides.highlightLayerIdx : highlightLayerIdx;

    try {
      const res = await fetch(`${API_BASE}/api/hueforge/${hfSessionId}/preview-palette`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          layout_mode: overrides.layoutMode ?? layoutMode,
          size_mm: overrides.sizeMm ?? sizeMm,
          grid_cols: overrides.gridCols ?? gridCols,
          grid_rows: overrides.gridRows ?? gridRows,
          printer_id: overrides.printerId ?? (activePrinter?.id || printerPreset),
          base_thickness_mm: overrides.baseThicknessMm ?? baseThicknessMm,
          relief_height_mm: overrides.reliefHeightMm ?? reliefHeightMm,
          num_colors: targetK,
          palette_mode: targetMode,
          color_engine: targetEngine,
          art_style: targetArtStyle,
          art_intensity: targetArtIntensity,
          custom_hex_colors: hexList,
          custom_end_layer_nums: endLayers,
          td_mm: overrides.tdMm ?? tdMm,
          detail_boost: overrides.detailBoost ?? detailBoost,
          contrast_gamma: overrides.contrastGamma ?? contrastGamma,
          zoom: reqZoom,
          offset_x_pct: reqOffX,
          offset_y_pct: reqOffY,
          fill_mode: targetFill,
          border_style: overrides.borderStyle ?? borderStyle,
          border_width_mm: overrides.borderWidthMm ?? borderWidthMm,
          add_back_connectors: addBackConnectors,
          highlight_layer_idx: targetHighlight,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        const merged = data.active_palette.map((layer, idx) => ({
          ...layer,
          spool_id: targetPalette[idx]?.spool_id || layer.spool_id || null,
        }));
        setActivePalette(merged);
        setPreviewDataUrl(data.preview_data_url);
        if (data.source_preview_data_url) {
          setSourcePreviewDataUrl(data.source_preview_data_url);
          setCommittedFrame({ zoom: reqZoom, offsetXPct: reqOffX, offsetYPct: reqOffY });
        }
        if (data.shape_overlay_data_url !== undefined) setShapeOverlayDataUrl(data.shape_overlay_data_url);
        if (data.void_pct !== undefined) setVoidPct(data.void_pct);
        if (data.has_validated_outpaint !== undefined) setHasValidatedOutpaint(Boolean(data.has_validated_outpaint));
      }
    } catch (e) {
      if (e.name !== 'AbortError') {
        console.error(e);
      }
    }
  };

  const schedulePalettePreview = (overrides = {}, delayMs = 85) => {
    if (previewDebounceRef.current) {
      clearTimeout(previewDebounceRef.current);
    }
    previewDebounceRef.current = setTimeout(() => {
      previewDebounceRef.current = null;
      refreshPalettePreview(overrides);
    }, delayMs);
  };

  const handlePaletteModeChange = (newMode) => {
    setPaletteMode(newMode);
    const sourceDict = newMode === 'in_stock_spools' ? stockPalettesByK : palettesByK;
    const presetPal = sourceDict[numColors] || palettesByK[numColors] || [];
    if (presetPal.length > 0) {
      setActivePalette(presetPal);
      refreshPalettePreview({
        paletteMode: newMode,
        palette: presetPal,
        customHexColors: presetPal.map((c) => c.hex_color),
        customEndLayers: presetPal.map((c) => c.end_layer_num),
      });
    }
  };

  const handleColorEngineChange = (newEngine) => {
    setColorEngine(newEngine);
    refreshPalettePreview({ colorEngine: newEngine });
  };

  const handleArtStyleChange = (newStyle) => {
    const prevStyle = artStyle;
    setArtStyle(newStyle);
    // When switching to Gravure Splash (like the Goku photo), recessed_base gives a black frame around the white plateau
    const nextBorder =
      newStyle === 'intaglio_splash' && borderStyle === 'raised_top'
        ? 'recessed_base'
        : newStyle !== 'intaglio_splash' && borderStyle === 'recessed_base' && prevStyle === 'intaglio_splash'
        ? 'raised_top'
        : borderStyle;
    if (nextBorder !== borderStyle) {
      setBorderStyle(nextBorder);
    }

    // If leaving intaglio_splash or stained_glass_ink, restore the original AI/Stock palette for numColors
    const sourceDict = paletteMode === 'in_stock_spools' ? stockPalettesByK : palettesByK;
    const basePal = sourceDict[numColors] || palettesByK[numColors] || activePalette;
    const shouldRestoreBasePalette =
      (prevStyle === 'intaglio_splash' || prevStyle === 'stained_glass_ink') &&
      newStyle !== prevStyle &&
      basePal.length > 0;

    refreshPalettePreview({
      artStyle: newStyle,
      borderStyle: nextBorder,
      ...(shouldRestoreBasePalette
        ? {
            palette: basePal,
            customHexColors: basePal.map((c) => c.hex_color),
          }
        : {}),
    });
  };

  const handleFillModeChange = (newFillMode) => {
    setFillMode(newFillMode);
    refreshPalettePreview({ fillMode: newFillMode });
  };

  const handleApplyOutpaint = async () => {
    if (!hfSessionId) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/hueforge/${hfSessionId}/apply-outpaint`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          layout_mode: layoutMode,
          size_mm: sizeMm,
          grid_cols: gridCols,
          grid_rows: gridRows,
          printer_id: activePrinter?.id || printerPreset,
          base_thickness_mm: baseThicknessMm,
          relief_height_mm: reliefHeightMm,
          num_colors: numColors,
          palette_mode: paletteMode,
          color_engine: colorEngine,
          art_style: artStyle,
          art_intensity: artIntensity,
          custom_hex_colors: activePalette.map((c) => c.hex_color),
          custom_end_layer_nums: activePalette.map((c) => c.end_layer_num),
          td_mm: tdMm,
          detail_boost: detailBoost,
          contrast_gamma: contrastGamma,
          zoom,
          offset_x_pct: offsetXPct,
          offset_y_pct: offsetYPct,
          fill_mode: fillMode,
          border_style: borderStyle,
          border_width_mm: borderWidthMm,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        if (data.image_size_px) setImageSizePx(data.image_size_px);
        setRecommendedColors(data.recommended_colors);
        setPalettesByK(data.palettes_by_k);
        setStockPalettesByK(data.stock_palettes_by_k || {});
        setActivePalette(data.active_palette);
        setPreviewDataUrl(data.preview_data_url);
        if (data.source_preview_data_url) setSourcePreviewDataUrl(data.source_preview_data_url);
        if (data.shape_overlay_data_url !== undefined) setShapeOverlayDataUrl(data.shape_overlay_data_url);
        setVoidPct(data.void_pct ?? 0.0);
        setHasValidatedOutpaint(true);
        if (fillMode === 'none_preview') setFillMode('smart_aura');
        setZoom(1.0);
        setOffsetXPct(0.0);
        setOffsetYPct(0.0);
        setDragDeltaPx([0, 0]);
        setCommittedFrame({ zoom: 1.0, offsetXPct: 0.0, offsetYPct: 0.0 });
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleResetOutpaint = async () => {
    if (!hfSessionId) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/hueforge/${hfSessionId}/reset-outpaint`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          layout_mode: layoutMode,
          size_mm: sizeMm,
          grid_cols: gridCols,
          grid_rows: gridRows,
          printer_id: activePrinter?.id || printerPreset,
          base_thickness_mm: baseThicknessMm,
          relief_height_mm: reliefHeightMm,
          num_colors: numColors,
          palette_mode: paletteMode,
          color_engine: colorEngine,
          art_style: artStyle,
          art_intensity: artIntensity,
          td_mm: tdMm,
          detail_boost: detailBoost,
          contrast_gamma: contrastGamma,
          zoom: 1.0,
          offset_x_pct: 0.0,
          offset_y_pct: 0.0,
          fill_mode: fillMode,
          border_style: borderStyle,
          border_width_mm: borderWidthMm,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        const nextZ = data.optimal_zoom ?? 1.0;
        if (data.image_size_px) setImageSizePx(data.image_size_px);
        setRecommendedColors(data.recommended_colors);
        setPalettesByK(data.palettes_by_k);
        setStockPalettesByK(data.stock_palettes_by_k || {});
        setActivePalette(data.active_palette);
        setPreviewDataUrl(data.preview_data_url);
        if (data.source_preview_data_url) setSourcePreviewDataUrl(data.source_preview_data_url);
        if (data.shape_overlay_data_url !== undefined) setShapeOverlayDataUrl(data.shape_overlay_data_url);
        setVoidPct(data.void_pct ?? 0.0);
        setHasValidatedOutpaint(false);
        setZoom(nextZ);
        setOffsetXPct(0.0);
        setOffsetYPct(0.0);
        setDragDeltaPx([0, 0]);
        setCommittedFrame({ zoom: nextZ, offsetXPct: 0.0, offsetYPct: 0.0 });
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleOptimizeSpoolOrder = async () => {
    if (!hfSessionId) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/hueforge/${hfSessionId}/optimize-order`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          layout_mode: layoutMode,
          size_mm: sizeMm,
          grid_cols: gridCols,
          grid_rows: gridRows,
          printer_id: activePrinter?.id || printerPreset,
          base_thickness_mm: baseThicknessMm,
          relief_height_mm: reliefHeightMm,
          num_colors: numColors,
          palette_mode: paletteMode,
          color_engine: colorEngine,
          art_style: artStyle,
          art_intensity: artIntensity,
          custom_hex_colors: activePalette.map((c) => c.hex_color),
          custom_end_layer_nums: activePalette.map((c) => c.end_layer_num),
          td_mm: tdMm,
          detail_boost: detailBoost,
          contrast_gamma: contrastGamma,
          zoom,
          offset_x_pct: offsetXPct,
          offset_y_pct: offsetYPct,
          fill_mode: fillMode,
          border_style: borderStyle,
          border_width_mm: borderWidthMm,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        setActivePalette(data.active_palette);
        setPreviewDataUrl(data.preview_data_url);
        if (data.source_preview_data_url) {
          setSourcePreviewDataUrl(data.source_preview_data_url);
          setCommittedFrame({ zoom, offsetXPct, offsetYPct });
        }
        if (data.shape_overlay_data_url !== undefined) setShapeOverlayDataUrl(data.shape_overlay_data_url);
        if (data.void_pct !== undefined) setVoidPct(data.void_pct);
        setDeltaEInfo({ before: data.delta_e_before, after: data.delta_e_after });
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleReanalyzeOnCrop = async () => {
    if (!hfSessionId) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/hueforge/${hfSessionId}/reanalyze-palette`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          layout_mode: layoutMode,
          size_mm: sizeMm,
          grid_cols: gridCols,
          grid_rows: gridRows,
          printer_id: activePrinter?.id || printerPreset,
          base_thickness_mm: baseThicknessMm,
          relief_height_mm: reliefHeightMm,
          num_colors: numColors,
          palette_mode: paletteMode,
          color_engine: colorEngine,
          art_style: artStyle,
          art_intensity: artIntensity,
          td_mm: tdMm,
          detail_boost: detailBoost,
          contrast_gamma: contrastGamma,
          zoom,
          offset_x_pct: offsetXPct,
          offset_y_pct: offsetYPct,
          fill_mode: fillMode,
          border_style: borderStyle,
          border_width_mm: borderWidthMm,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        setRecommendedColors(data.recommended_colors);
        setPalettesByK(data.palettes_by_k);
        setStockPalettesByK(data.stock_palettes_by_k || {});
        setActivePalette(data.active_palette);
        setPreviewDataUrl(data.preview_data_url);
        if (data.source_preview_data_url) {
          setSourcePreviewDataUrl(data.source_preview_data_url);
          setCommittedFrame({ zoom, offsetXPct, offsetYPct });
        }
        if (data.shape_overlay_data_url !== undefined) setShapeOverlayDataUrl(data.shape_overlay_data_url);
        if (data.void_pct !== undefined) setVoidPct(data.void_pct);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleNumColorsChange = (newK) => {
    setNumColors(newK);
    const sourceDict = paletteMode === 'in_stock_spools' ? stockPalettesByK : palettesByK;
    const presetPal = sourceDict[newK] || palettesByK[newK] || [];
    if (presetPal.length > 0) {
      setActivePalette(presetPal);
    }
    refreshPalettePreview({
      numColors: newK,
      palette: presetPal,
      customHexColors: presetPal.map((c) => c.hex_color),
      customEndLayers: null,
    });
  };

  // Change color via custom picker or quick swatch or spool dropdown
  const handleColorHexChange = (index, newHex, spoolObj = null) => {
    const updated = activePalette.map((layer, idx) =>
      idx === index
        ? {
            ...layer,
            hex_color: newHex,
            spool_id: spoolObj ? spoolObj.id : null,
            td_mm: spoolObj?.td_mm ? Number(spoolObj.td_mm) : layer.td_mm,
          }
        : layer
    );
    setActivePalette(updated);
    refreshPalettePreview({
      palette: updated,
      customHexColors: updated.map((u) => u.hex_color),
      customEndLayers: updated.map((u) => u.end_layer_num),
    });
  };

  // Revert a single layer back to its original AI-detected color & layer height
  const handleResetSingleLayerToAi = (index) => {
    const sourceDict = paletteMode === 'in_stock_spools' ? stockPalettesByK : palettesByK;
    const aiPal = sourceDict[numColors] || palettesByK[numColors];
    if (!aiPal || !aiPal[index]) return;
    const aiLayer = aiPal[index];
    const updated = activePalette.map((layer, idx) =>
      idx === index
        ? {
            ...layer,
            hex_color: aiLayer.hex_color,
            spool_id: aiLayer.spool_id || null,
            td_mm: aiLayer.td_mm || layer.td_mm,
          }
        : layer
    );
    setActivePalette(updated);
    refreshPalettePreview({
      palette: updated,
      customHexColors: updated.map((u) => u.hex_color),
      customEndLayers: updated.map((u) => u.end_layer_num),
    });
  };

  // Revert ALL layers back to the original AI-proposed palette
  const handleResetAllColorsToAi = () => {
    const sourceDict = paletteMode === 'in_stock_spools' ? stockPalettesByK : palettesByK;
    const aiPal = sourceDict[numColors] || palettesByK[numColors];
    if (!aiPal) return;
    const restored = aiPal.map((l) => ({ ...l }));
    setActivePalette(restored);
    refreshPalettePreview({
      palette: restored,
      customHexColors: restored.map((u) => u.hex_color),
      customEndLayers: restored.map((u) => u.end_layer_num),
    });
  };

  // Swap the color/spool of layer `index` with `index - 1` (up) or `index + 1` (down) while keeping layer heights monotonic
  const handleSwapLayerOrder = (index, direction) => {
    const targetIdx = direction === 'up' ? index - 1 : index + 1;
    if (targetIdx < 0 || targetIdx >= activePalette.length) return;
    const updated = activePalette.map((l) => ({ ...l }));
    const srcColor = {
      hex_color: updated[index].hex_color,
      rgb: updated[index].rgb,
      spool_id: updated[index].spool_id || null,
      td_mm: updated[index].td_mm,
    };
    const dstColor = {
      hex_color: updated[targetIdx].hex_color,
      rgb: updated[targetIdx].rgb,
      spool_id: updated[targetIdx].spool_id || null,
      td_mm: updated[targetIdx].td_mm,
    };
    updated[index] = { ...updated[index], ...dstColor };
    updated[targetIdx] = { ...updated[targetIdx], ...srcColor };
    setActivePalette(updated);
    refreshPalettePreview({
      palette: updated,
      customHexColors: updated.map((u) => u.hex_color),
      customEndLayers: updated.map((u) => u.end_layer_num),
    });
  };

  // Interactive per-layer end_layer_num slider (updates 3D Viewer3D instantly + 2D preview)
  const handleLayerEndChange = (index, newEndLayer) => {
    const firstLayerMm = 0.16;
    const layerHeightMm = 0.08;
    const layerToMm = (lNum) => Number((firstLayerMm + (lNum - 1) * layerHeightMm).toFixed(2));

    const updated = activePalette.map((l) => ({ ...l }));
    const totalLayers = updated[updated.length - 1]?.end_layer_num || 30;
    const minValid = index === 0 ? 2 : updated[index - 1].end_layer_num + 1;
    const maxValid =
      index >= updated.length - 1
        ? totalLayers
        : updated[index + 1].end_layer_num - 1;

    const clamped = Math.max(minValid, Math.min(maxValid, newEndLayer));
    updated[index].end_layer_num = clamped;
    updated[index].end_mm = layerToMm(clamped);

    if (index + 1 < updated.length) {
      updated[index + 1].start_layer_num = clamped + 1;
      updated[index + 1].start_mm = updated[index].end_mm;
    }

    setActivePalette(updated);
    refreshPalettePreview({
      palette: updated,
      customHexColors: updated.map((u) => u.hex_color),
      customEndLayers: updated.map((u) => u.end_layer_num),
    });
  };

  const handleTdChange = (newTd) => {
    setTdMm(newTd);
    const updated = activePalette.map((l) => ({ ...l, td_mm: newTd }));
    setActivePalette(updated);
    refreshPalettePreview({ tdMm: newTd, palette: updated });
  };

  const handleResetFraming = () => {
    setZoom(1.0);
    setOffsetXPct(0.0);
    setOffsetYPct(0.0);
    setDragDeltaPx([0, 0]);
    refreshPalettePreview({ zoom: 1.0, offsetXPct: 0.0, offsetYPct: 0.0 });
  };

  const getRenderedImageBox = () => {
    const imgEl = leftImgRef.current;
    const containerW = Math.max(100, imgEl?.clientWidth || 440);
    const containerH = Math.max(100, imgEl?.clientHeight || 380);
    const natW = Math.max(10, imgEl?.naturalWidth || 460);
    const natH = Math.max(10, imgEl?.naturalHeight || 400);
    const natAspect = natW / natH;
    const boxAspect = containerW / containerH;
    const renderedW = boxAspect > natAspect ? containerH * natAspect : containerW;
    const renderedH = boxAspect > natAspect ? containerH : containerW / natAspect;
    return { renderedW, renderedH };
  };

  // Interactive 60 FPS mouse drag directly on the 2D HueForge Preview Window (moves image inside fixed shape)
  const handlePreviewMouseDown = (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    dragStateRef.current = {
      active: true,
      startX: e.clientX,
      startY: e.clientY,
      baseOffX: offsetXPct,
      baseOffY: offsetYPct,
    };
  };

  const handlePreviewMouseMove = (e) => {
    if (!dragStateRef.current.active) return;
    const dx = e.clientX - dragStateRef.current.startX;
    const dy = e.clientY - dragStateRef.current.startY;
    const { renderedW, renderedH } = getRenderedImageBox();
    const m1 = computeFramingMetrics(imageSizePx, layoutMode, gridCols, gridRows, zoom);
    const dOffX = (dx / renderedW) * (m1.cropW / m1.panSpanX) * 100.0;
    const dOffY = -(dy / renderedH) * (m1.cropH / m1.panSpanY) * 100.0;
    const nextOffX = Number(Math.max(-100, Math.min(100, dragStateRef.current.baseOffX + dOffX)).toFixed(2));
    const nextOffY = Number(Math.max(-100, Math.min(100, dragStateRef.current.baseOffY + dOffY)).toFixed(2));
    setOffsetXPct(nextOffX);
    setOffsetYPct(nextOffY);
    schedulePalettePreview({ offsetXPct: nextOffX, offsetYPct: nextOffY }, 95);
  };

  const finishPreviewDrag = (e) => {
    if (!dragStateRef.current.active) return;
    dragStateRef.current.active = false;
    const dx = e.clientX - dragStateRef.current.startX;
    const dy = e.clientY - dragStateRef.current.startY;
    setDragDeltaPx([0, 0]);
    if (Math.abs(dx) < 1 && Math.abs(dy) < 1) return;

    const { renderedW, renderedH } = getRenderedImageBox();
    const m1 = computeFramingMetrics(imageSizePx, layoutMode, gridCols, gridRows, zoom);
    const dOffX = (dx / renderedW) * (m1.cropW / m1.panSpanX) * 100.0;
    const dOffY = -(dy / renderedH) * (m1.cropH / m1.panSpanY) * 100.0;
    const newOffX = Number(Math.max(-100, Math.min(100, dragStateRef.current.baseOffX + dOffX)).toFixed(2));
    const newOffY = Number(Math.max(-100, Math.min(100, dragStateRef.current.baseOffY + dOffY)).toFixed(2));

    setOffsetXPct(newOffX);
    setOffsetYPct(newOffY);
    if (previewDebounceRef.current) {
      clearTimeout(previewDebounceRef.current);
      previewDebounceRef.current = null;
    }
    refreshPalettePreview({ offsetXPct: newOffX, offsetYPct: newOffY });
  };

  const handlePreviewWheel = (e) => {
    e.preventDefault();
    const step = Math.abs(e.deltaY) < 40 ? 0.03 : 0.05;
    const delta = e.deltaY < 0 ? step : -step;
    const nextZoom = Number(Math.max(0.30, Math.min(3.0, zoom + delta)).toFixed(2));
    if (nextZoom !== zoom) {
      setZoom(nextZoom);
      schedulePalettePreview({ zoom: nextZoom }, 85);
    }
  };

  const handleGenerateHueForge3D = async () => {
    if (!hfSessionId) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/hueforge/${hfSessionId}/generate-stl`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          layout_mode: layoutMode,
          size_mm: sizeMm,
          grid_cols: gridCols,
          grid_rows: gridRows,
          printer_bed_x_mm: bedSize[0],
          printer_bed_y_mm: bedSize[1],
          printer_bed_z_mm: bedSize[2],
          printer_name: activePrinter?.name || 'Creality Hi (Combo 2× CFS)',
          base_thickness_mm: baseThicknessMm,
          relief_height_mm: reliefHeightMm,
          first_layer_mm: 0.16,
          layer_height_mm: 0.08,
          num_colors: numColors,
          palette_mode: paletteMode,
          color_engine: colorEngine,
          art_style: artStyle,
          art_intensity: artIntensity,
          custom_hex_colors: activePalette.map((c) => c.hex_color),
          custom_end_layer_nums: activePalette.map((c) => c.end_layer_num),
          td_mm: tdMm,
          detail_boost: detailBoost,
          contrast_gamma: contrastGamma,
          zoom,
          offset_x_pct: offsetXPct,
          offset_y_pct: offsetYPct,
          fill_mode: fillMode,
          border_style: borderStyle,
          border_width_mm: borderWidthMm,
          add_back_connectors: addBackConnectors,
          grid_resolution: gridResolution,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Erreur génération HueForge 3D');
      setGenResult(data);
      const merged = data.active_palette.map((layer, idx) => ({
        ...layer,
        spool_id: activePalette[idx]?.spool_id || null,
      }));
      setActivePalette(merged);
      if (data.preview_data_url) setPreviewDataUrl(data.preview_data_url);
      if (data.source_preview_data_url) {
        setSourcePreviewDataUrl(data.source_preview_data_url);
        setCommittedFrame({ zoom, offsetXPct, offsetYPct });
      }
      if (data.shape_overlay_data_url !== undefined) setShapeOverlayDataUrl(data.shape_overlay_data_url);
      if (data.void_pct !== undefined) setVoidPct(data.void_pct);
      setStlVersion((v) => v + 1);
    } catch (e) {
      alert(e.message);
    } finally {
      setLoading(false);
    }
  };

  // Overlay SVG preview of the geometric cut mask on top of the 2D HueForge image preview
  const renderSvgOverlay = () => {
    if (layoutMode === 'single_circle') {
      return (
        <svg viewBox="-100 -100 200 200" className="hf-svg-overlay">
          <circle cx="0" cy="0" r="92" fill="none" stroke="#00f0ff" strokeWidth="2.5" strokeDasharray="5,4" />
        </svg>
      );
    }
    if (layoutMode === 'single_hexagon') {
      return (
        <svg viewBox="-100 -100 200 200" className="hf-svg-overlay">
          <polygon
            points="92,0 46,79.6 -46,79.6 -92,0 -46,-79.6 46,-79.6"
            fill="none"
            stroke="#00f0ff"
            strokeWidth="2.5"
          />
        </svg>
      );
    }
    if (layoutMode === 'single_triangle') {
      return (
        <svg viewBox="-100 -100 200 200" className="hf-svg-overlay">
          <polygon points="0,-90 -85,70 85,70" fill="none" stroke="#00f0ff" strokeWidth="2.5" />
        </svg>
      );
    }
    if (layoutMode === 'multi_4_squares') {
      return (
        <svg viewBox="-100 -100 200 200" className="hf-svg-overlay">
          <rect x="-92" y="-92" width="184" height="184" fill="none" stroke="#00f0ff" strokeWidth="2.5" />
          <line x1="0" y1="-92" x2="0" y2="92" stroke="#ff2a6d" strokeWidth="2" />
          <line x1="-92" y1="0" x2="92" y2="0" stroke="#ff2a6d" strokeWidth="2" />
        </svg>
      );
    }
    if (layoutMode === 'multi_7_hexagons') {
      const r = 32;
      const d = Math.sqrt(3) * r;
      const centers = [[0, 0]];
      for (let i = 0; i < 6; i++) {
        const a = ((30 + i * 60) * Math.PI) / 180;
        centers.push([d * Math.cos(a), d * Math.sin(a)]);
      }
      const hexPts = (cx, cy) =>
        [0, 60, 120, 180, 240, 300]
          .map((deg) => {
            const rad = (deg * Math.PI) / 180;
            return `${(cx + r * Math.cos(rad)).toFixed(1)},${(cy + r * Math.sin(rad)).toFixed(1)}`;
          })
          .join(' ');
      return (
        <svg viewBox="-100 -100 200 200" className="hf-svg-overlay">
          {centers.map(([cx, cy], idx) => (
            <polygon
              key={idx}
              points={hexPts(cx, cy)}
              fill="none"
              stroke={idx === 0 ? '#ff2a6d' : '#00f0ff'}
              strokeWidth="2"
            />
          ))}
        </svg>
      );
    }
    if (layoutMode === 'multi_6_triangles') {
      const r = 90;
      const tris = [0, 1, 2, 3, 4, 5].map((i) => {
        const a0 = (i * 60 * Math.PI) / 180;
        const a1 = ((i + 1) * 60 * Math.PI) / 180;
        return `0,0 ${(r * Math.cos(a0)).toFixed(1)},${(r * Math.sin(a0)).toFixed(1)} ${(r * Math.cos(a1)).toFixed(1)},${(r * Math.sin(a1)).toFixed(1)}`;
      });
      return (
        <svg viewBox="-100 -100 200 200" className="hf-svg-overlay">
          {tris.map((pts, idx) => (
            <polygon key={idx} points={pts} fill="none" stroke="#00f0ff" strokeWidth="2" />
          ))}
        </svg>
      );
    }
    if (layoutMode === 'multi_4_triangles') {
      return (
        <svg viewBox="-100 -100 200 200" className="hf-svg-overlay">
          <polygon points="0,-88 -88,80 88,80" fill="none" stroke="#00f0ff" strokeWidth="2.5" />
          <polygon points="-44,-4 44,-4 0,80" fill="none" stroke="#ff2a6d" strokeWidth="2" />
        </svg>
      );
    }
    return null;
  };

  const previewStlUrl =
    genResult && hfSessionId
      ? `${API_BASE}${genResult.preview_stl_url}?v=${stlVersion}`
      : null;

  const downloadZipUrl =
    genResult && hfSessionId
      ? `${API_BASE}${genResult.download_zip_url}`
      : null;

  const download3mfUrl =
    genResult && hfSessionId
      ? `${API_BASE}${genResult.download_3mf_url || `/api/hueforge/${hfSessionId}/download-3mf`}`
      : null;

  const maxTotalLayerNum = activePalette[activePalette.length - 1]?.end_layer_num || 30;
  const currentReferencePalettes = paletteMode === 'in_stock_spools' ? stockPalettesByK : palettesByK;
  const aiPaletteForCurrentK = currentReferencePalettes[numColors] || palettesByK[numColors] || [];

  // 60 FPS Live Client-Side Framing Transform (moves/zooms ONLY the image while the shape overlay stays 100% fixed)
  const liveFramingTransform = (() => {
    const m0 = computeFramingMetrics(imageSizePx, layoutMode, gridCols, gridRows, committedFrame.zoom);
    const m1 = computeFramingMetrics(imageSizePx, layoutMode, gridCols, gridRows, zoom);
    const { renderedW, renderedH } = getRenderedImageBox();
    const cx0 = m0.srcW / 2.0 - (committedFrame.offsetXPct / 100.0) * m0.panSpanX;
    const cy0 = m0.srcH / 2.0 + (committedFrame.offsetYPct / 100.0) * m0.panSpanY;
    const cx1 = m1.srcW / 2.0 - (offsetXPct / 100.0) * m1.panSpanX;
    const cy1 = m1.srcH / 2.0 + (offsetYPct / 100.0) * m1.panSpanY;
    const txPx = ((cx0 - cx1) / m1.cropW) * renderedW + dragDeltaPx[0];
    const tyPx = ((cy0 - cy1) / m1.cropH) * renderedH + dragDeltaPx[1];
    const scaleRatio = m1.z / Math.max(0.15, m0.z);
    if (Math.abs(txPx) < 0.15 && Math.abs(tyPx) < 0.15 && Math.abs(scaleRatio - 1.0) < 0.002) {
      return 'none';
    }
    return `translate(${txPx.toFixed(2)}px, ${tyPx.toFixed(2)}px) scale(${scaleRatio.toFixed(4)})`;
  })();

  return (
    <div className="app-layout" style={{ height: 'calc(100vh - 48px)' }}>
      <aside className="sidebar" style={{ height: 'calc(100vh - 48px)', width: '445px', minWidth: '445px' }}>
        <div className="sidebar-scroll">
          {/* STEP 1 : IMAGE UPLOAD & CFS PALETTE + SPOOL LIBRARY */}
          <section className="panel-card">
            <div className="panel-header-flex">
              <div className="panel-title">1. PALETTE DOUBLE CFS &amp; BOBINES</div>
              <div style={{ display: 'flex', gap: '4px' }}>
                {onOpenPrinterSetup && (
                  <button
                    type="button"
                    className="btn-hud"
                    style={{ fontSize: '0.66rem', padding: '3px 7px' }}
                    onClick={onOpenPrinterSetup}
                    title="Gérer mes imprimantes 3D, tailles de plateaux X/Y/Z et modules autorisés"
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
                    title="Configurer vos bobines Deeplee, Creality, Sunlu... et les raccourcis couleurs"
                  >
                    🎨 Bobines / + IA
                  </button>
                )}
              </div>
            </div>

            <div className="panel-header-flex" style={{ marginBottom: '3px' }}>
              <label className="field-label" style={{ margin: 0 }}>
                Imprimante Cible (Filtrée Module HueForge)
              </label>
              <span className="dim-badge" style={{ fontSize: '0.67rem' }}>
                Plateau {bedSize[0]}×{bedSize[1]} mm
              </span>
            </div>
            <select
              className="cyber-input"
              value={activePrinter?.id || printerPreset}
              onChange={(e) => {
                if (e.target.value === '__manage_printers__') {
                  if (onOpenPrinterSetup) onOpenPrinterSetup();
                  else if (onOpenSpoolSetup) onOpenSpoolSetup();
                  return;
                }
                onChangePrinterPreset(e.target.value);
              }}
            >
              {hueforgePrinters.map((pr) => (
                <option key={pr.id} value={pr.id}>
                  🖨️ {pr.name} ({pr.bed_x_mm}×{pr.bed_y_mm} mm — Jusqu&apos;à {pr.max_colors || 8} Couleurs)
                </option>
              ))}
              <option value="__manage_printers__">
                ➕ Encoder une imprimante / Activer une imprimante pour HueForge...
              </option>
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
              className="btn-cyber primary-full"
              style={{ marginTop: '10px' }}
              disabled={loading}
              onClick={() => fileInputRef.current?.click()}
            >
              🖼️ Importer une Image (.PNG / .JPG / .WEBP)
            </button>

            {hfSessionId && (
              <>
                <div className="file-pill" style={{ marginTop: '8px' }}>
                  Image : <strong>{filename}</strong> | IA recommande :{' '}
                  <strong className="text-cyan">{recommendedColors} bobines CFS</strong>
                </div>

                {/* Mode Selection: AI Ideal Recommended vs In-Stock Spools Matcher */}
                <label className="field-label" style={{ marginTop: '8px' }}>
                  Mode de Proposition des Couleurs :
                </label>
                <div className="mode-tabs">
                  <button
                    type="button"
                    className={`tab-btn ${paletteMode === 'ai_recommended' ? 'active' : ''}`}
                    onClick={() => handlePaletteModeChange('ai_recommended')}
                    title="Palette chromatique optimale extraite de l'image"
                  >
                    ✨ Recommandé IA
                  </button>
                  <button
                    type="button"
                    className={`tab-btn ${paletteMode === 'in_stock_spools' ? 'active' : ''}`}
                    onClick={() => handlePaletteModeChange('in_stock_spools')}
                    title="Sélectionne automatiquement les bobines les plus proches parmi celles marquées EN STOCK dans Setup"
                  >
                    📦 Mon Stock ({inStockSpools.length} bobines)
                  </button>
                </div>

                {/* Color Engine Selector: HSV Contiguous Family Ramp vs CIELAB Delta-E Inverse Optical Solver */}
                <label className="field-label" style={{ marginTop: '8px' }}>
                  Moteur Colorimétrique &amp; Projection 3D :
                </label>
                <div className="mode-tabs">
                  <button
                    type="button"
                    className={`tab-btn ${colorEngine === 'hsv_ramp' ? 'active' : ''}`}
                    onClick={() => handleColorEngineChange('hsv_ramp')}
                    title="Mode par défaut : Rampes Continues par Famille HSV (Idéal Manga, Comics, Logos, Dragon Ball, Saint Seiya)"
                  >
                    🎨 Rampe Manga (HSV)
                  </button>
                  <button
                    type="button"
                    className={`tab-btn ${colorEngine === 'cie_delta_e' ? 'active' : ''}`}
                    onClick={() => handleColorEngineChange('cie_delta_e')}
                    title="Solveur Optique Inverse ΔE CIELAB : Minimise mathématiquement l'erreur perceptuelle ΔE*ab sur vos couches et bobines personnalisées"
                  >
                    🔬 Solveur Optique ΔE
                  </button>
                </div>

                {/* NEW: Artistic Style & 3D Topography Selector (6 Modes) */}
                <label className="field-label" style={{ marginTop: '9px' }}>
                  🎭 Style Artistique &amp; Topographie 3D :
                </label>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(3, 1fr)',
                    gap: '4px',
                    marginBottom: '6px',
                  }}
                >
                  {ART_STYLE_OPTIONS.map((opt) => {
                    const isSelected = artStyle === opt.value;
                    return (
                      <button
                        key={opt.value}
                        type="button"
                        className={`btn-hud ${isSelected ? 'active' : ''}`}
                        style={{
                          padding: '6px 5px',
                          fontSize: '0.67rem',
                          fontWeight: isSelected ? 700 : 500,
                          textAlign: 'center',
                          borderColor: isSelected ? '#ff2a6d' : undefined,
                          background: isSelected
                            ? 'linear-gradient(135deg, rgba(255, 42, 109, 0.24), rgba(0, 240, 255, 0.16))'
                            : undefined,
                        }}
                        onClick={() => handleArtStyleChange(opt.value)}
                        title={opt.desc}
                      >
                        {opt.shortLabel}
                      </button>
                    );
                  })}
                </div>

                {artStyle !== 'standard' && (
                  <div
                    style={{
                      marginBottom: '8px',
                      padding: '8px 10px',
                      borderRadius: '7px',
                      background: 'rgba(255, 42, 109, 0.08)',
                      border: '1px solid rgba(255, 42, 109, 0.35)',
                      fontSize: '0.7rem',
                    }}
                  >
                    <div style={{ fontWeight: 700, color: '#ff2a6d', marginBottom: '3px' }}>
                      {ART_STYLE_OPTIONS.find((o) => o.value === artStyle)?.title}
                    </div>
                    <div style={{ color: '#cbd5e1', lineHeight: 1.35, marginBottom: '6px' }}>
                      {ART_STYLE_OPTIONS.find((o) => o.value === artStyle)?.desc}
                    </div>
                    <label className="field-label" style={{ margin: '2px 0' }}>
                      Intensité de l&apos;Effet Artistique / Relief :{' '}
                      <strong className="text-cyan">×{artIntensity.toFixed(2)}</strong>
                    </label>
                    <input
                      type="range"
                      min="0.40"
                      max="1.80"
                      step="0.10"
                      value={artIntensity}
                      onChange={(e) => {
                        const val = parseFloat(e.target.value);
                        setArtIntensity(val);
                        refreshPalettePreview({ artIntensity: val });
                      }}
                      style={{ width: '100%', accentColor: '#ff2a6d' }}
                    />
                  </div>
                )}

                <div className="btn-row" style={{ marginTop: '6px', gap: '5px' }}>
                  <button
                    type="button"
                    className="btn-hud"
                    style={{ flex: 1, fontSize: '0.68rem', padding: '5px 6px' }}
                    disabled={loading}
                    onClick={handleReanalyzeOnCrop}
                    title="Relance l'analyse des couleurs uniquement sur la zone visible dans votre forme (après zoom/déplacement)"
                  >
                    🔄 Ré-analyser Cadrage
                  </button>
                  <button
                    type="button"
                    className="btn-hud active"
                    style={{ flex: 1, fontSize: '0.68rem', padding: '5px 6px' }}
                    disabled={loading}
                    onClick={handleOptimizeSpoolOrder}
                    title="Teste automatiquement les permutations de vos bobines intermédiaires pour trouver l'ordre vertical qui minimise l'erreur ΔE CIELAB"
                  >
                    🪄 Optimiser Ordre ΔE
                  </button>
                </div>
                {deltaEInfo && (
                  <div
                    className="file-pill"
                    style={{
                      marginTop: '5px',
                      fontSize: '0.68rem',
                      padding: '4px 8px',
                      borderColor: 'rgba(16, 185, 129, 0.45)',
                    }}
                  >
                    🔬 Optimisation Optique CIELAB : ΔE moyen{' '}
                    <strong>{deltaEInfo.before}</strong> ➔{' '}
                    <strong className="text-cyan">{deltaEInfo.after}</strong>
                  </div>
                )}

                <div className="panel-header-flex" style={{ marginTop: '8px', marginBottom: '2px' }}>
                  <label className="field-label" style={{ margin: 0 }}>
                    Nombre de Couleurs (2 à 8 :{' '}
                    <strong className="text-cyan">{numColors} couleurs</strong>)
                  </label>
                  <button
                    type="button"
                    className="btn-hud"
                    style={{ fontSize: '0.66rem', padding: '2px 7px' }}
                    onClick={handleResetAllColorsToAi}
                    title="Revenir à toutes les couleurs proposées initialement par l'IA"
                  >
                    ↺ Réinitialiser Couleurs IA
                  </button>
                </div>
                <input
                  type="range"
                  min="2"
                  max="8"
                  value={numColors}
                  onChange={(e) => handleNumColorsChange(parseInt(e.target.value, 10))}
                  style={{ width: '100%', accentColor: '#00f0ff' }}
                />

                {/* Transmission Distance (TD) Slider */}
                <label className="field-label">
                  Translucidité Optique Filament (TD) :{' '}
                  <strong className="text-cyan">{tdMm.toFixed(1)} mm</strong>{' '}
                  <span className="dim-badge">(0.8 = Opaque | 3.0 = Dégradé fondu)</span>
                </label>
                <input
                  type="range"
                  min="0.5"
                  max="5.0"
                  step="0.25"
                  value={tdMm}
                  onChange={(e) => handleTdChange(parseFloat(e.target.value))}
                  style={{ width: '100%', accentColor: '#00f0ff' }}
                />

                {/* Interactive Stratigraphic Layer Stack Bar & Loupe de Couche */}
                <div
                  style={{
                    marginTop: '10px',
                    marginBottom: '8px',
                    padding: '9px 10px',
                    borderRadius: '8px',
                    background: 'rgba(15, 23, 42, 0.85)',
                    border: '1px solid rgba(0, 240, 255, 0.28)',
                  }}
                >
                  <div className="panel-header-flex" style={{ marginBottom: '5px' }}>
                    <span
                      style={{
                        fontSize: '0.7rem',
                        fontWeight: 800,
                        color: '#00f0ff',
                        letterSpacing: '0.03em',
                      }}
                    >
                      🧱 TOUR DE COUCHES INTERACTIVE (C.1 ➔ C.{maxTotalLayerNum})
                    </span>
                    {highlightLayerIdx !== null ? (
                      <button
                        type="button"
                        className="btn-hud active"
                        style={{
                          fontSize: '0.64rem',
                          padding: '2px 7px',
                          borderColor: '#00f0ff',
                          color: '#00f0ff',
                        }}
                        onClick={() => {
                          setHighlightLayerIdx(null);
                          refreshPalettePreview({ highlightLayerIdx: null });
                        }}
                        title="Désactiver la Loupe de Couche et réafficher le rendu complet"
                      >
                        ✕ Quitter Loupe ({activePalette[highlightLayerIdx]?.cfs_slot})
                      </button>
                    ) : (
                      <span className="dim-badge" style={{ fontSize: '0.63rem' }}>
                        Cliquez 👁️ pour isoler une couche
                      </span>
                    )}
                  </div>

                  {/* Proportional visual stack bar */}
                  <div
                    style={{
                      display: 'flex',
                      height: '22px',
                      borderRadius: '6px',
                      overflow: 'hidden',
                      border: '1px solid rgba(255,255,255,0.22)',
                      marginBottom: '6px',
                      cursor: 'pointer',
                    }}
                    title="Répartition proportionnelle des couches (cliquez sur une tranche pour isoler sa zone sur l'aperçu)"
                  >
                    {activePalette.map((layer, idx) => {
                      const count = Math.max(1, layer.end_layer_num - layer.start_layer_num + 1);
                      const isHi = highlightLayerIdx === idx;
                      return (
                        <div
                          key={idx}
                          onClick={() => {
                            const nextIdx = highlightLayerIdx === idx ? null : idx;
                            setHighlightLayerIdx(nextIdx);
                            refreshPalettePreview({ highlightLayerIdx: nextIdx });
                          }}
                          style={{
                            flex: count,
                            backgroundColor: layer.hex_color,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontSize: '0.6rem',
                            fontWeight: 800,
                            color: idx === 0 ? '#ffffff' : '#0f172a',
                            textShadow:
                              idx === 0
                                ? '0 1px 2px rgba(0,0,0,0.9)'
                                : '0 0 3px rgba(255,255,255,0.85)',
                            borderRight:
                              idx < activePalette.length - 1
                                ? '1px solid rgba(15,23,42,0.65)'
                                : 'none',
                            outline: isHi ? '2px solid #00f0ff' : 'none',
                            outlineOffset: '-2px',
                            opacity: highlightLayerIdx !== null && !isHi ? 0.35 : 1.0,
                            transition: 'all 0.15s ease',
                          }}
                          title={`${layer.cfs_slot} : C.${layer.start_layer_num}–${layer.end_layer_num} (${count} couches) — Cliquez pour isoler cette zone sur Étape B`}
                        >
                          {count >= 2 ? `C.${layer.start_layer_num}-${layer.end_layer_num}` : ''}
                        </div>
                      );
                    })}
                  </div>

                  {/* Total layers / Relief height quick control */}
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: '8px',
                      fontSize: '0.67rem',
                      color: '#cbd5e1',
                    }}
                  >
                    <span>
                      Hauteur Totale :{' '}
                      <strong className="text-cyan">
                        {(baseThicknessMm + reliefHeightMm).toFixed(2)} mm
                      </strong>{' '}
                      ({maxTotalLayerNum} couches à 0.08mm)
                    </span>
                    <div style={{ display: 'flex', gap: '4px' }}>
                      {[
                        { label: '25 c. (2.0mm)', relief: 1.12 },
                        { label: '30 c. (2.48mm)', relief: 1.60 },
                        { label: '36 c. (2.96mm)', relief: 2.08 },
                      ].map((preset) => {
                        const isCurrent = Math.abs(reliefHeightMm - preset.relief) < 0.05;
                        return (
                          <button
                            key={preset.label}
                            type="button"
                            className={`btn-hud ${isCurrent ? 'active' : ''}`}
                            style={{ fontSize: '0.61rem', padding: '2px 5px' }}
                            onClick={() => {
                              setReliefHeightMm(preset.relief);
                              refreshPalettePreview({
                                reliefHeightMm: preset.relief,
                                customEndLayers: null,
                              });
                            }}
                            title="Ajuster le nombre total de couches du HueForge"
                          >
                            {preset.label}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>

                {/* Color Layers Stack with Undo-to-AI, Spool Dropdown, Layer Sliders & 18+ Quick Swatches */}
                <div className="cfs-layers-list">
                  {activePalette.map((layer, idx) => {
                    const isLast = idx === activePalette.length - 1;
                    const minLayer = idx === 0 ? 2 : activePalette[idx - 1].end_layer_num + 1;
                    const maxLayer = isLast
                      ? maxTotalLayerNum
                      : activePalette[idx + 1].end_layer_num - 1;

                    const layerCount = Math.max(1, layer.end_layer_num - layer.start_layer_num + 1);
                    const layerThicknessMm = Number((layerCount * 0.08).toFixed(2));
                    const isHighlighted = highlightLayerIdx === idx;

                    const aiDefaultHex = aiPaletteForCurrentK[idx]?.hex_color;
                    const isModifiedFromAi =
                      aiDefaultHex &&
                      aiDefaultHex.toLowerCase() !== (layer.hex_color || '').toLowerCase();

                    // Check if a configured spool matches either by spool_id or exact hex_color
                    const matchedSpool =
                      userSpools.find((s) => s.id === layer.spool_id) ||
                      userSpools.find(
                        (s) => s.hex_color.toLowerCase() === (layer.hex_color || '').toLowerCase()
                      );

                    // Compute optical opacity % from filament TD and layer thickness (Beer-Lambert law)
                    const effectiveTd = matchedSpool?.td_mm || tdMm || 2.0;
                    const opacityPct =
                      idx === 0
                        ? 100
                        : Math.min(
                            100,
                            Math.max(15, Math.round((1 - Math.exp((-2.8 * layerThicknessMm) / Math.max(0.4, effectiveTd))) * 100))
                          );

                    return (
                      <div
                        key={idx}
                        className="cfs-layer-card"
                        style={
                          isHighlighted
                            ? {
                                borderColor: '#00f0ff',
                                boxShadow: '0 0 12px rgba(0, 240, 255, 0.28)',
                                background: 'rgba(0, 240, 255, 0.07)',
                              }
                            : undefined
                        }
                      >
                        {/* Top row: Color Swatch + CFS Slot + Loupe Button + Back-to-AI Button + Layer Range */}
                        <div className="cfs-layer-row">
                          <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '1px' }}>
                              <button
                                type="button"
                                className="btn-hud"
                                style={{ padding: '0px 4px', fontSize: '0.56rem', lineHeight: 1.1 }}
                                disabled={idx === 0}
                                onClick={() => handleSwapLayerOrder(idx, 'up')}
                                title="Échanger cette couleur avec la couche précédente (plus basse)"
                              >
                                ▲
                              </button>
                              <button
                                type="button"
                                className="btn-hud"
                                style={{ padding: '0px 4px', fontSize: '0.56rem', lineHeight: 1.1 }}
                                disabled={idx === activePalette.length - 1}
                                onClick={() => handleSwapLayerOrder(idx, 'down')}
                                title="Échanger cette couleur avec la couche suivante (plus haute)"
                              >
                                ▼
                              </button>
                            </div>
                            <input
                              type="color"
                              value={layer.hex_color}
                              onChange={(e) => handleColorHexChange(idx, e.target.value, null)}
                              className="color-Swatch-input"
                              title="Cliquez pour choisir une couleur sur mesure"
                            />
                            <span className="cfs-badge">{layer.cfs_slot}</span>

                            {/* Loupe de Couche (Isolate Layer Pixels on Preview) */}
                            <button
                              type="button"
                              className={`btn-hud ${isHighlighted ? 'active' : ''}`}
                              style={{
                                padding: '2px 6px',
                                fontSize: '0.62rem',
                                borderColor: isHighlighted ? '#00f0ff' : undefined,
                                color: isHighlighted ? '#00f0ff' : undefined,
                              }}
                              onClick={() => {
                                const nextIdx = isHighlighted ? null : idx;
                                setHighlightLayerIdx(nextIdx);
                                refreshPalettePreview({ highlightLayerIdx: nextIdx });
                              }}
                              title="Loupe de Couche : met en évidence en direct sur l'aperçu Étape B tous les pixels imprimés par cette bobine"
                            >
                              {isHighlighted ? '👁️ Zone Active' : '👁️ Voir Zone'}
                            </button>

                            {/* Individual Undo / Back to AI Original Color Button */}
                            {isModifiedFromAi && (
                              <button
                                type="button"
                                className="btn-undo-ai"
                                onClick={() => handleResetSingleLayerToAi(idx)}
                                title={`Revenir à la couleur IA d'origine (${aiDefaultHex})`}
                              >
                                <span
                                  className="undo-ai-dot"
                                  style={{ backgroundColor: aiDefaultHex }}
                                />
                                ↺ IA
                              </button>
                            )}
                          </div>

                          <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                            <span
                              style={{
                                fontSize: '0.62rem',
                                padding: '1px 5px',
                                borderRadius: '4px',
                                background:
                                  opacityPct >= 88
                                    ? 'rgba(16, 185, 129, 0.16)'
                                    : 'rgba(245, 158, 11, 0.18)',
                                color: opacityPct >= 88 ? '#34d399' : '#fbbf24',
                                border: `1px solid ${
                                  opacityPct >= 88
                                    ? 'rgba(16, 185, 129, 0.35)'
                                    : 'rgba(245, 158, 11, 0.35)'
                                }`,
                              }}
                              title={`Épaisseur de cette tranche : ${layerCount} couche(s) (${layerThicknessMm} mm) • Opacité optique : ${opacityPct}% (TD ${effectiveTd}mm)`}
                            >
                              {layerCount} c. • {opacityPct}%
                            </span>
                            <span className="cfs-range">
                              C.<strong>{layer.start_layer_num}–{layer.end_layer_num}</strong>
                            </span>
                            <span className="cfs-mm">{layer.end_mm.toFixed(2)} mm</span>
                          </div>
                        </div>

                        {/* Second row: Pre-configured Spool Selector Dropdown (with Color Square + Brand/Name) */}
                        <div className="cfs-spool-select-row">
                          <span
                            className="spool-inline-square"
                            style={{ backgroundColor: layer.hex_color }}
                          />
                          <select
                            className="cyber-input spool-select-compact"
                            value={matchedSpool ? matchedSpool.id : '__custom__'}
                            onChange={(e) => {
                              const val = e.target.value;
                              if (val === '__setup__') {
                                if (onOpenSpoolSetup) onOpenSpoolSetup();
                                return;
                              }
                              if (val === '__ai_reset__') {
                                handleResetSingleLayerToAi(idx);
                                return;
                              }
                              const sp = userSpools.find((s) => s.id === val);
                              if (sp) {
                                handleColorHexChange(idx, sp.hex_color, sp);
                              }
                            }}
                          >
                            <option value="__custom__">
                              🎨 Sur mesure / IA ({layer.hex_color.toUpperCase()})
                            </option>
                            {aiDefaultHex && (
                              <option value="__ai_reset__">
                                ↺ Couleur IA d&apos;origine ({aiDefaultHex.toUpperCase()})
                              </option>
                            )}
                            <optgroup label={`📦 Mes Bobines EN STOCK (${inStockSpools.length})`}>
                              {inStockSpools.map((sp) => (
                                <option key={sp.id} value={sp.id}>
                                  ■ {sp.brand} {sp.material} — {sp.color_name} (TD {sp.td_mm}mm)
                                </option>
                              ))}
                            </optgroup>
                            {outOfStockSpools.length > 0 && (
                              <optgroup label={`⏳ Autres Bobines Hors Stock (${outOfStockSpools.length})`}>
                                {outOfStockSpools.map((sp) => (
                                  <option key={sp.id} value={sp.id}>
                                    □ {sp.brand} {sp.material} — {sp.color_name} (Hors stock)
                                  </option>
                                ))}
                              </optgroup>
                            )}
                            <option value="__setup__">➕ Configurer / Gérer mon stock de bobines...</option>
                          </select>
                        </div>

                        {/* Third row: Interactive Layer Height Slider + [-1] / [+1] Step Buttons */}
                        {!isLast && (
                          <div className="cfs-slider-row">
                            <span title="Ajustez la couche exacte où s'arrête cette bobine avant le changement de filament">
                              Fin C.{layer.end_layer_num} :
                            </span>
                            <button
                              type="button"
                              className="btn-hud"
                              style={{ padding: '1px 6px', fontSize: '0.64rem', fontWeight: 700 }}
                              disabled={layer.end_layer_num <= minLayer}
                              onClick={() =>
                                handleLayerEndChange(idx, Math.max(minLayer, layer.end_layer_num - 1))
                              }
                              title="Retirer 1 couche (-0.08 mm) à cette couleur"
                            >
                              -1
                            </button>
                            <input
                              type="range"
                              min={minLayer}
                              max={maxLayer}
                              value={layer.end_layer_num}
                              onChange={(e) =>
                                handleLayerEndChange(idx, parseInt(e.target.value, 10))
                              }
                              title="Glissez pour ajuster la hauteur de transition de cette couleur en direct"
                            />
                            <button
                              type="button"
                              className="btn-hud"
                              style={{ padding: '1px 6px', fontSize: '0.64rem', fontWeight: 700 }}
                              disabled={layer.end_layer_num >= maxLayer}
                              onClick={() =>
                                handleLayerEndChange(idx, Math.min(maxLayer, layer.end_layer_num + 1))
                              }
                              title="Ajouter 1 couche (+0.08 mm) à cette couleur"
                            >
                              +1
                            </button>
                            <span style={{ minWidth: '34px', textAlign: 'right' }}>
                              {layerThicknessMm.toFixed(2)}mm
                            </span>
                          </div>
                        )}

                        {/* Fourth row: 18+ Quick Spool Shortcuts Bar */}
                        <div className="spool-presets-bar">
                          {favoriteSpools.map((sp) => (
                            <button
                              key={sp.id}
                              type="button"
                              className={`spool-dot ${
                                (layer.hex_color || '').toLowerCase() === sp.hex_color.toLowerCase()
                                  ? 'selected'
                                  : ''
                              }`}
                              style={{ backgroundColor: sp.hex_color }}
                              title={`${sp.brand} ${sp.material} — ${sp.color_name} (${sp.hex_color}, TD ${sp.td_mm}mm)`}
                              onClick={() => handleColorHexChange(idx, sp.hex_color, sp)}
                            />
                          ))}
                          {onOpenSpoolSetup && (
                            <button
                              type="button"
                              className="spool-dot-add"
                              title="Ajouter ou configurer mes raccourcis bobines"
                              onClick={onOpenSpoolSetup}
                            >
                              +
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </section>

          {/* STEP 2 : NETTETÉ MANGA / DÉTAILS & CADRAGE DE L'IMAGE */}
          {hfSessionId && (
            <section className="panel-card">
              <div className="panel-header-flex">
                <div className="panel-title">2. NETTETÉ MANGA &amp; CADRAGE IMAGE</div>
                <div style={{ display: 'flex', gap: '4px' }}>
                  <button
                    type="button"
                    className="btn-hud active"
                    style={{ fontSize: '0.66rem', padding: '3px 7px' }}
                    onClick={() => {
                      const optZ = computeOptimalZoomClient(imageSizePx, layoutMode, gridCols, gridRows);
                      setZoom(optZ);
                      setOffsetXPct(0.0);
                      setOffsetYPct(0.0);
                      setDragDeltaPx([0, 0]);
                      refreshPalettePreview({ zoom: optZ, offsetXPct: 0.0, offsetYPct: 0.0 });
                    }}
                    title="Adapte automatiquement le zoom pour faire entrer tout le sujet dans la forme ou la grille N×M choisie"
                  >
                    🎯 Zoom Optimal (×{optimalZoomForCurrent.toFixed(2)})
                  </button>
                  <button
                    type="button"
                    className="btn-hud"
                    style={{ fontSize: '0.66rem', padding: '3px 7px' }}
                    onClick={handleResetFraming}
                    title="Remettre le zoom à ×1.00 et centrer"
                  >
                    ↺ ×1.00
                  </button>
                </div>
              </div>

              <div className="file-pill" style={{ marginBottom: '8px', fontSize: '0.73rem' }}>
                💡 <strong>Astuce :</strong> Glissez l&apos;image à la souris et{' '}
                <strong>zoomez/dézoomez à la molette</strong> (jusqu&apos;à ×0.30) directement dans le{' '}
                <strong>Studio Côte-à-Côte</strong> à droite !
              </div>

              <label className="field-label">
                Boost Contours &amp; Traits Noirs (Manga / Line-Art) :{' '}
                <strong className="text-cyan">×{detailBoost.toFixed(2)}</strong>
              </label>
              <input
                type="range"
                min="0.0"
                max="2.5"
                step="0.1"
                value={detailBoost}
                onChange={(e) => {
                  const val = parseFloat(e.target.value);
                  setDetailBoost(val);
                  refreshPalettePreview({ detailBoost: val });
                }}
                style={{ width: '100%', accentColor: '#ff2a6d' }}
              />

              <label className="field-label">
                Contraste Lumineux (Gamma) :{' '}
                <strong className="text-cyan">{contrastGamma.toFixed(2)}</strong>{' '}
                <span className="dim-badge">(&lt;1 = Plus clair | &gt;1 = Ombres denses)</span>
              </label>
              <input
                type="range"
                min="0.60"
                max="1.80"
                step="0.05"
                value={contrastGamma}
                onChange={(e) => {
                  const val = parseFloat(e.target.value);
                  setContrastGamma(val);
                  refreshPalettePreview({ contrastGamma: val });
                }}
                style={{ width: '100%', accentColor: '#00f0ff' }}
              />

              <label className="field-label">
                Zoom / Dézoom Image dans la Forme : <strong className="text-cyan">×{zoom.toFixed(2)}</strong>{' '}
                <span className="dim-badge">(Optimal: ×{optimalZoomForCurrent.toFixed(2)})</span>
              </label>
              <input
                type="range"
                min="0.30"
                max="2.80"
                step="0.02"
                value={zoom}
                onChange={(e) => {
                  const val = parseFloat(e.target.value);
                  setZoom(val);
                  schedulePalettePreview({ zoom: val }, 80);
                }}
                style={{ width: '100%', accentColor: '#00f0ff' }}
              />

              <label className="switch-label" style={{ marginTop: '4px', marginBottom: '4px', fontSize: '0.72rem' }}>
                <input
                  type="checkbox"
                  checked={autoOptimalZoom}
                  onChange={(e) => setAutoOptimalZoom(e.target.checked)}
                />
                <span>
                  🎯 Ajuster automatiquement le zoom optimal lors d&apos;un changement de forme ou de grille N×M
                </span>
              </label>

              <div className="grid-2col" style={{ marginTop: '4px' }}>
                <div>
                  <label className="field-label">
                    Gauche / Droite (X) : <strong className="text-cyan">{Math.round(offsetXPct)}%</strong>
                  </label>
                  <input
                    type="range"
                    min="-100"
                    max="100"
                    step="1"
                    value={offsetXPct}
                    onChange={(e) => {
                      const val = parseFloat(e.target.value);
                      setOffsetXPct(val);
                      schedulePalettePreview({ offsetXPct: val }, 80);
                    }}
                    style={{ width: '100%', accentColor: '#00f0ff' }}
                  />
                </div>
                <div>
                  <label className="field-label">
                    Bas / Haut (Y) : <strong className="text-cyan">{Math.round(offsetYPct)}%</strong>
                  </label>
                  <input
                    type="range"
                    min="-100"
                    max="100"
                    step="1"
                    value={offsetYPct}
                    onChange={(e) => {
                      const val = parseFloat(e.target.value);
                      setOffsetYPct(val);
                      schedulePalettePreview({ offsetYPct: val }, 80);
                    }}
                    style={{ width: '100%', accentColor: '#ff2a6d' }}
                  />
                </div>
              </div>
            </section>
          )}

          {/* STEP 3 : FORME GÉOMÉTRIQUE, BORDURE CADRE & MULTI-FRAME */}
          <section className="panel-card">
            <div className="panel-title">3. FORME GÉOMÉTRIQUE, CADRE &amp; MULTI-FRAME</div>

            <label className="field-label">Choix du Format / Découpe Mosaïque</label>
            <select
              className="cyber-input"
              value={layoutMode}
              onChange={(e) => handleLayoutChange(e.target.value)}
            >
              {LAYOUT_OPTIONS.map((grp) => (
                <optgroup key={grp.group} label={grp.group}>
                  {grp.items.map((it) => (
                    <option key={it.value} value={it.value}>
                      {it.label}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>

            {/* Custom N x M Grid Controls when multi_grid_squares is selected */}
            {layoutMode === 'multi_grid_squares' && (
              <div
                style={{
                  marginTop: '8px',
                  marginBottom: '8px',
                  padding: '9px 10px',
                  borderRadius: '7px',
                  background: 'rgba(0, 240, 255, 0.06)',
                  border: '1px solid rgba(0, 240, 255, 0.28)',
                }}
              >
                <div className="panel-header-flex" style={{ marginBottom: '6px' }}>
                  <span style={{ fontSize: '0.74rem', fontWeight: 700, color: '#00f0ff' }}>
                    🧩 GRILLE SUR MESURE : {gridCols} LARGE × {gridRows} HAUT ({gridCols * gridRows} FRAMES)
                  </span>
                  <span className="dim-badge" style={{ fontSize: '0.68rem' }}>
                    Total : {Math.round(gridCols * sizeMm)} × {Math.round(gridRows * sizeMm)} mm
                  </span>
                </div>

                <div className="btn-row" style={{ gap: '4px', marginBottom: '7px', flexWrap: 'wrap' }}>
                  {[
                    { c: 2, r: 4, label: '2×4 Vertical' },
                    { c: 4, r: 2, label: '4×2 Horizontal' },
                    { c: 3, r: 3, label: '3×3 (9)' },
                    { c: 4, r: 3, label: '4×3 (12)' },
                    { c: 5, r: 4, label: '5×4 Géant (20)' },
                  ].map((preset) => (
                    <button
                      key={`${preset.c}x${preset.r}`}
                      type="button"
                      className={`btn-hud ${gridCols === preset.c && gridRows === preset.r ? 'active' : ''}`}
                      style={{ flex: 1, fontSize: '0.65rem', padding: '3px 5px' }}
                      onClick={() => handleGridDimsChange(preset.c, preset.r)}
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>

                <div className="grid-2col">
                  <div>
                    <label className="field-label">Nb Carrés en Largeur (X)</label>
                    <input
                      type="number"
                      min="1"
                      max="10"
                      className="cyber-input"
                      value={gridCols}
                      onChange={(e) => handleGridDimsChange(e.target.value, gridRows)}
                    />
                  </div>
                  <div>
                    <label className="field-label">Nb Carrés en Hauteur (Y)</label>
                    <input
                      type="number"
                      min="1"
                      max="10"
                      className="cyber-input"
                      value={gridRows}
                      onChange={(e) => handleGridDimsChange(gridCols, e.target.value)}
                    />
                  </div>
                </div>
              </div>
            )}

            <div className="grid-2col">
              <div>
                <label className="field-label">{currentLayoutMeta.unitLabel}</label>
                <input
                  type="number"
                  step="5"
                  className="cyber-input"
                  style={
                    exceedsPrinterBed
                      ? { borderColor: '#f97316', boxShadow: '0 0 8px rgba(249, 115, 22, 0.35)' }
                      : undefined
                  }
                  value={sizeMm}
                  onChange={(e) => {
                    const val = parseFloat(e.target.value) || 100;
                    setSizeMm(val);
                    refreshPalettePreview({ sizeMm: val });
                  }}
                />
              </div>
              <div>
                <label className="field-label">Épaisseur Base / Relief (mm)</label>
                <div className="btn-row">
                  <input
                    type="number"
                    step="0.08"
                    className="cyber-input"
                    value={baseThicknessMm}
                    onChange={(e) => setBaseThicknessMm(parseFloat(e.target.value) || 0.88)}
                    title="Épaisseur de la base sombre (mm)"
                  />
                  <input
                    type="number"
                    step="0.08"
                    className="cyber-input"
                    value={reliefHeightMm}
                    onChange={(e) => setReliefHeightMm(parseFloat(e.target.value) || 1.60)}
                    title="Hauteur du relief sculpté (mm)"
                  />
                </div>
              </div>
            </div>

            {/* Real-time Bed Size Warning Banner */}
            {exceedsPrinterBed ? (
              <div
                style={{
                  marginTop: '8px',
                  padding: '9px 11px',
                  borderRadius: '7px',
                  background: 'rgba(249, 115, 22, 0.14)',
                  border: '1px solid #f97316',
                  color: '#fed7aa',
                  fontSize: '0.73rem',
                }}
              >
                <div style={{ fontWeight: 700, color: '#fb923c', marginBottom: '4px' }}>
                  ⚠️ DÉPASSEMENT DU PLATEAU {activePrinter?.name?.toUpperCase()} ({bedSize[0]}×{bedSize[1]} mm) !
                </div>
                <div style={{ marginBottom: '7px', lineHeight: 1.35 }}>
                  Chaque pièce mesure actuellement{' '}
                  <strong>
                    {singleTileDimsMm[0]} × {singleTileDimsMm[1]} mm
                  </strong>
                  , ce qui dépasse la surface imprimable ({bedSize[0]} × {bedSize[1]} mm).
                </div>
                <button
                  type="button"
                  className="btn-cyber primary-full"
                  style={{ padding: '5px 10px', fontSize: '0.72rem', margin: 0 }}
                  onClick={() => {
                    setSizeMm(maxSafeSizeMm);
                    refreshPalettePreview({ sizeMm: maxSafeSizeMm });
                  }}
                >
                  📏 Ajuster au maximum du plateau ({maxSafeSizeMm} mm)
                </button>
              </div>
            ) : (
              <div
                className="file-pill"
                style={{
                  marginTop: '6px',
                  fontSize: '0.7rem',
                  padding: '4px 8px',
                  display: 'flex',
                  justifyContent: 'space-between',
                }}
              >
                <span>
                  📏 Taille d&apos;une pièce :{' '}
                  <strong className="text-cyan">
                    {singleTileDimsMm[0]} × {singleTileDimsMm[1]} mm
                  </strong>
                </span>
                <span style={{ color: '#34d399' }}>
                  ✓ Compatible {activePrinter?.name?.split('(')[0]?.trim()} ({bedSize[0]}×{bedSize[1]} mm)
                </span>
              </div>
            )}

            {/* Integrated Tile Perimeter Frame / Border */}
            <div className="grid-2col" style={{ marginTop: '6px' }}>
              <div>
                <label className="field-label">Bordure / Cadre Intégré</label>
                <select
                  className="cyber-input"
                  value={borderStyle}
                  onChange={(e) => {
                    const val = e.target.value;
                    setBorderStyle(val);
                    refreshPalettePreview({ borderStyle: val });
                  }}
                >
                  <option value="raised_top">Cadre Haut (Couleur Finale)</option>
                  <option value="recessed_base">Cadre Bas (Couleur de Base)</option>
                  <option value="none">Sans Cadre (Bord franc)</option>
                </select>
              </div>
              <div>
                <label className="field-label">Largeur Cadre (mm) &amp; finesse 3D</label>
                <div className="btn-row">
                  <input
                    type="number"
                    step="0.5"
                    min="0"
                    max="12"
                    disabled={borderStyle === 'none'}
                    className="cyber-input"
                    value={borderWidthMm}
                    onChange={(e) => {
                      const val = parseFloat(e.target.value) || 2.5;
                      setBorderWidthMm(val);
                      refreshPalettePreview({ borderWidthMm: val });
                    }}
                    title="Largeur de la bordure en mm"
                  />
                  <select
                    className="cyber-input"
                    value={gridResolution}
                    onChange={(e) => setGridResolution(parseInt(e.target.value, 10))}
                    title="Finesse du maillage 3D HueForge"
                  >
                    <option value={260}>Std (260)</option>
                    <option value={380}>HD (380)</option>
                    <option value={500}>Ultra (500)</option>
                  </select>
                </div>
              </div>
            </div>

            {layoutMode.startsWith('multi_') && (
              <label className="switch-label" style={{ marginTop: '10px' }}>
                <input
                  type="checkbox"
                  checked={addBackConnectors}
                  onChange={(e) => setAddBackConnectors(e.target.checked)}
                />
                <span>
                  Creuser Encoches Femelles au dos + Générer STL des Clips Mâles
                </span>
              </label>
            )}

            <button
              className="btn-cyber pink-full"
              style={{ marginTop: '12px' }}
              disabled={!hfSessionId || loading}
              onClick={handleGenerateHueForge3D}
            >
              {loading
                ? 'Sculpture HD du Relief 3D, Découpe & Projet .3MF...'
                : '⚡ Générer les STL + Projet Complet .3MF (Multi-Plateaux CFS)'}
            </button>

            {genResult && (
              <div className="cut-summary-box">
                <div className="summary-header">
                  ✓ {genResult.tiles_count} Plateau(x) 3D + {genResult.clips_count} Clips Mâles générés
                </div>
                <ul className="parts-list">
                  {genResult.parts.map((p) => (
                    <li key={p.part_index}>
                      <span>{p.filename}</span>
                      <span className="dim-badge">
                        {p.extents_mm[0]}×{p.extents_mm[1]}×{p.extents_mm[2]} mm
                      </span>
                    </li>
                  ))}
                </ul>
                {download3mfUrl && (
                  <a
                    href={download3mfUrl}
                    download
                    className="btn-cyber primary-full"
                    style={{
                      display: 'block',
                      textAlign: 'center',
                      textDecoration: 'none',
                      marginBottom: '7px',
                      padding: '9px 10px',
                      fontWeight: 700,
                    }}
                    title="Projet .3MF pré-configuré pour Creality Print / OrcaSlicer : couches 0.08mm, 100% infill, couleurs CFS et changements de bobines aux bonnes hauteurs Z sur multi-plateaux !"
                  >
                    🎨 Télécharger le Projet Complet .3MF (Multi-Plateaux, Couleurs CFS &amp; Couches Z)
                  </a>
                )}
                {downloadZipUrl && (
                  <a href={downloadZipUrl} download className="btn-cyber download-zip-btn">
                    📦 Télécharger le Pack .ZIP (Projet .3MF + Tuiles STL + Clips + Recette TXT)
                  </a>
                )}
              </div>
            )}
          </section>
        </div>
      </aside>

      {/* RIGHT WORKSPACE: DOUBLE STUDIO COMPARATIF 2D CÔTE-À-CÔTE (DEFAULT) OR OPTIONAL 3D MESH VIEWER */}
      <div className="hf-studio-workspace">
        {/* Top Studio Toolbar */}
        <div className="hf-studio-topbar">
          <div className="hf-view-switcher">
            <button
              type="button"
              className={`hf-view-tab ${viewMode === 'studio_2d' ? 'active' : ''}`}
              onClick={() => setViewMode('studio_2d')}
            >
              🖼️ Studio Comparatif Côte-à-Côte (Vue à Plat)
            </button>
            <button
              type="button"
              className={`hf-view-tab ${viewMode === 'mesh_3d' ? 'active' : ''}`}
              onClick={() => setViewMode('mesh_3d')}
              title="Voir le maillage 3D topographique extrudé (optionnel)"
            >
              🧊 Vue Maillage Relief 3D {genResult ? `(${genResult.tiles_count} STL)` : '(Optionnel)'}
            </button>
          </div>

          <div className="hf-studio-topbar-right">
            {hfSessionId && (
              <>
                {exceedsPrinterBed && (
                  <span
                    className="hf-meta-pill"
                    style={{
                      borderColor: '#f97316',
                      color: '#fb923c',
                      background: 'rgba(249, 115, 22, 0.14)',
                    }}
                  >
                    ⚠️ Pièce {singleTileDimsMm[0]}×{singleTileDimsMm[1]}mm &gt; Plateau {bedSize[0]}×{bedSize[1]}mm
                  </span>
                )}
                <span className="hf-meta-pill">
                  Forme :{' '}
                  <strong>
                    {layoutMode === 'multi_grid_squares'
                      ? `Grille ${gridCols}×${gridRows} (${gridCols * gridRows} carrés)`
                      : currentLayoutMeta.label.split('(')[0].trim()}
                  </strong>
                </span>
                <span className="hf-meta-pill">
                  Style :{' '}
                  <strong style={{ color: artStyle !== 'standard' ? '#ff2a6d' : '#00f0ff' }}>
                    {ART_STYLE_OPTIONS.find((o) => o.value === artStyle)?.shortLabel || '🎨 Standard'}
                  </strong>
                </span>
                <span className="hf-meta-pill">
                  Moteur :{' '}
                  <strong className="text-cyan">
                    {colorEngine === 'cie_delta_e' ? '🔬 Solveur ΔE CIELAB' : '🎨 Rampe Manga HSV'}
                  </strong>
                </span>
                {download3mfUrl && (
                  <a
                    href={download3mfUrl}
                    download
                    className="btn-hud active"
                    style={{
                      textDecoration: 'none',
                      padding: '5px 12px',
                      fontSize: '0.73rem',
                      borderColor: '#00f0ff',
                    }}
                    title="Télécharger le fichier .3MF complet pré-configuré (Multi-plateaux + Couleurs CFS + Changements de couche Z)"
                  >
                    🎨 Projet .3MF ({genResult.tiles_count} Plateau{genResult.tiles_count > 1 ? 'x' : ''})
                  </a>
                )}
                {downloadZipUrl && (
                  <a
                    href={downloadZipUrl}
                    download
                    className="btn-hud active"
                    style={{ textDecoration: 'none', padding: '5px 12px', fontSize: '0.73rem' }}
                  >
                    📦 Pack .ZIP
                  </a>
                )}
              </>
            )}
          </div>
        </div>

        {/* MODE 1 (DEFAULT): DOUBLE STUDIO COMPARATIF 2D CÔTE-À-CÔTE */}
        {viewMode === 'studio_2d' ? (
          !hfSessionId ? (
            <div className="hf-empty-studio">
              <div className="hf-empty-card">
                <div className="hf-empty-icon">🎨</div>
                <h2>Studio HueForge &amp; Multi-Frame Côte-à-Côte</h2>
                <p>
                  Importez une illustration, un manga ou une photo pour comparer en temps réel votre{' '}
                  <strong>image d&apos;origine (avec cadrage &amp; comblement IA des vides)</strong> à gauche et le{' '}
                  <strong>rendu HueForge final découpé à la forme</strong> à droite.
                </p>
                <button
                  type="button"
                  className="btn-cyber primary-full"
                  style={{ maxWidth: '340px', margin: '16px auto 0' }}
                  onClick={() => fileInputRef.current?.click()}
                >
                  🖼️ Choisir une Image (.PNG / .JPG / .WEBP)
                </button>
              </div>
            </div>
          ) : (
            <div className="hf-dual-studio-container">
              <div className="hf-dual-studio-grid">
                {/* LEFT PANEL: ORIGINAL IMAGE + INTERACTIVE FRAMING + SMART VOID FILLING STUDIO */}
                <div className="hf-studio-card">
                  <div className="hf-studio-card-header">
                    <div>
                      <span className="hf-step-tag">ÉTAPE A</span>
                      <span className="hf-card-title">
                        IMAGE D&apos;ORIGINE, CADRAGE &amp; COMBLEMENT DES VIDES
                      </span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span className="dim-badge">
                        Zoom ×{zoom.toFixed(2)} • ({Math.round(offsetXPct)}%, {Math.round(offsetYPct)}%)
                      </span>
                      <button
                        type="button"
                        className="btn-hud"
                        style={{ padding: '3px 8px', fontSize: '0.68rem' }}
                        onClick={handleResetFraming}
                        title="Recentrer l'image et remettre le zoom à ×1.00"
                      >
                        🎯 Centrer
                      </button>
                    </div>
                  </div>

                  <div
                    className="hf-studio-viewport interactive-pan"
                    onMouseDown={handlePreviewMouseDown}
                    onMouseMove={handlePreviewMouseMove}
                    onMouseUp={finishPreviewDrag}
                    onMouseLeave={finishPreviewDrag}
                    onWheel={handlePreviewWheel}
                    title="Glissez avec la souris pour déplacer l'image à l'intérieur de la forme fixe • Molette pour zoomer ou dézoomer (×0.30 à ×3.00)"
                  >
                    <img
                      ref={leftImgRef}
                      src={sourcePreviewDataUrl || previewDataUrl}
                      alt="Image Originale Cadrée & Étendue"
                      draggable={false}
                      style={{
                        transform: liveFramingTransform,
                        transformOrigin: 'center center',
                        transition: 'none',
                      }}
                    />
                    {shapeOverlayDataUrl && (
                      <img
                        src={shapeOverlayDataUrl}
                        alt=""
                        draggable={false}
                        className="hf-shape-fixed-overlay"
                      />
                    )}
                    <div className="hf-viewport-overlay-hint">
                      🖱️ Glisser : Déplacer l&apos;image • Molette : Zoom / Dézoom (×{zoom.toFixed(2)})
                    </div>
                  </div>

                  {/* ATELIER DE COMBLEMENT INTELLIGENT DES VIDES (OUTPAINTING) & VALIDATION */}
                  <div className={`hf-outpaint-studio ${voidPct > 0.3 ? 'has-void' : ''}`}>
                    <div className="hf-outpaint-header">
                      <div className="hf-outpaint-status">
                        {voidPct > 0.3 ? (
                          <>
                            <span className="void-badge warning">
                              ⚠️ Vide détecté dans la forme : {voidPct.toFixed(1)}%
                            </span>
                            <span>
                              Choisissez le mode d&apos;interprétation pour combler les bords manquants :
                            </span>
                          </>
                        ) : hasValidatedOutpaint ? (
                          <>
                            <span className="void-badge success">✅ Image Étendue Validée</span>
                            <span>
                              Les zones vides ont été fusionnées dans l&apos;image et les couleurs ré-analysées.
                            </span>
                          </>
                        ) : (
                          <>
                            <span className="void-badge neutral">✨ 0% de vide</span>
                            <span>
                              Dézoomez (molette ou curseur &lt; ×1.00) ou déplacez l&apos;image si un bord touche la forme.
                            </span>
                          </>
                        )}
                      </div>
                    </div>

                    <div className="hf-fill-modes-row">
                      <button
                        type="button"
                        className={`hf-fill-btn ${fillMode === 'smart_aura' ? 'active' : ''}`}
                        onClick={() => handleFillModeChange('smart_aura')}
                        title="Ignore les membres du personnage touchant le bord, prolonge l'espace bleu + l'aura mauve/grise et génère des étoiles"
                      >
                        🌌 IA Espace, Aura &amp; Étoiles
                      </button>
                      <button
                        type="button"
                        className={`hf-fill-btn ${fillMode === 'edge_stretch' ? 'active' : ''}`}
                        onClick={() => handleFillModeChange('edge_stretch')}
                        title="Étend et fond latéralement la bande de décor du bord (sans effet miroir)"
                      >
                        ↔️ Étirer Bords
                      </button>
                      <button
                        type="button"
                        className={`hf-fill-btn ${fillMode === 'mirror_blend' ? 'active' : ''}`}
                        onClick={() => handleFillModeChange('mirror_blend')}
                        title="Prolonge l'image par symétrie miroir fondue (sans le filet blanc de bordure)"
                      >
                        🪞 Miroir Fondu
                      </button>
                      <button
                        type="button"
                        className={`hf-fill-btn ${fillMode === 'solid_edge' ? 'active' : ''}`}
                        onClick={() => handleFillModeChange('solid_edge')}
                        title="Détecte la couleur de fond dominante des coins (ex: Blanc pur ou Bleu nuit) et unifie le vide"
                      >
                        🎨 Fond Unifié
                      </button>
                      <button
                        type="button"
                        className={`hf-fill-btn ${fillMode === 'none_preview' ? 'active' : ''}`}
                        onClick={() => handleFillModeChange('none_preview')}
                        title="Affiche un damier hachuré cyan pour visualiser exactement où se trouve le vide brut"
                      >
                        👁️ Voir Vide
                      </button>
                    </div>

                    <div className="hf-outpaint-actions">
                      <button
                        type="button"
                        className={`btn-cyber ${
                          voidPct > 0.3 || zoom !== 1.0 || offsetXPct !== 0 || offsetYPct !== 0
                            ? 'primary-full'
                            : ''
                        }`}
                        style={{ flex: 1, padding: '7px 12px', fontSize: '0.76rem', margin: 0 }}
                        disabled={
                          loading ||
                          (Math.abs(zoom - 1.0) < 0.01 &&
                            Math.abs(offsetXPct) < 1 &&
                            Math.abs(offsetYPct) < 1 &&
                            voidPct < 0.2)
                        }
                        onClick={handleApplyOutpaint}
                        title="Fige ce cadrage et le comblement des vides comme nouvelle image de référence, puis recalcule la palette optimale"
                      >
                        ✅ Valider &amp; Figer l&apos;Image Complétée (Recalculer Palette)
                      </button>
                      {hasValidatedOutpaint && (
                        <button
                          type="button"
                          className="btn-hud"
                          style={{ padding: '7px 11px', fontSize: '0.73rem' }}
                          disabled={loading}
                          onClick={handleResetOutpaint}
                          title="Annuler le comblement figé et revenir à l'image brute d'origine"
                        >
                          ↺ Revenir à l&apos;Image Brute
                        </button>
                      )}
                    </div>
                  </div>
                </div>

                {/* RIGHT PANEL: FINAL SIMULATED HUEFORGE PROJECT CUT TO EXACT SHAPE */}
                <div className="hf-studio-card">
                  <div className="hf-studio-card-header">
                    <div>
                      <span className="hf-step-tag pink">ÉTAPE B</span>
                      <span className="hf-card-title">
                        RENDU HUEFORGE FINAL DÉCOUPÉ ({numColors} COULEURS CFS)
                      </span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span className="dim-badge">
                        Cadre :{' '}
                        {borderStyle === 'raised_top'
                          ? `Haut (${borderWidthMm}mm)`
                          : borderStyle === 'recessed_base'
                          ? `Bas (${borderWidthMm}mm)`
                          : 'Sans cadre'}
                      </span>
                    </div>
                  </div>

                  <div
                    className="hf-studio-viewport interactive-pan"
                    onMouseDown={handlePreviewMouseDown}
                    onMouseMove={handlePreviewMouseMove}
                    onMouseUp={finishPreviewDrag}
                    onMouseLeave={finishPreviewDrag}
                    onWheel={handlePreviewWheel}
                    title="Simulation optique fidèle du HueForge à plat découpé dans votre forme géométrique (Glisser / Molette actif aussi ici)"
                  >
                    <img
                      src={previewDataUrl}
                      alt="Rendu HueForge Découpé à la Forme"
                      draggable={false}
                    />
                    <div className="hf-viewport-overlay-hint">
                      🎨 Simulation Optique {colorEngine === 'cie_delta_e' ? 'ΔE CIELAB' : 'HSV'} • TD{' '}
                      {tdMm.toFixed(1)}mm
                    </div>
                  </div>

                  {/* Interactive Bottom Color Stack Legend */}
                  <div className="hf-studio-palette-footer">
                    <div className="hf-palette-footer-title">
                      ORDRE D&apos;EMPILAGE VERTICAL DES BOBINES (DU FOND C.1 AU SOMMET C.{maxTotalLayerNum}) :
                    </div>
                    <div className="hf-palette-strip">
                      {activePalette.map((layer, idx) => {
                        const isHi = highlightLayerIdx === idx;
                        return (
                          <div
                            key={idx}
                            className="hf-palette-chip"
                            onClick={() => {
                              const nextIdx = isHi ? null : idx;
                              setHighlightLayerIdx(nextIdx);
                              refreshPalettePreview({ highlightLayerIdx: nextIdx });
                            }}
                            style={{
                              cursor: 'pointer',
                              borderColor: isHi ? '#00f0ff' : undefined,
                              boxShadow: isHi ? '0 0 10px rgba(0, 240, 255, 0.35)' : undefined,
                            }}
                            title={`${layer.cfs_slot} : Couches ${layer.start_layer_num} à ${layer.end_layer_num} (${layer.start_mm.toFixed(2)} ➔ ${layer.end_mm.toFixed(2)} mm) — Cliquez pour isoler cette couche sur l'aperçu`}
                          >
                            <span
                              className="hf-chip-color"
                              style={{ backgroundColor: layer.hex_color }}
                            />
                            <div className="hf-chip-meta">
                              <strong>
                                {layer.cfs_slot} {isHi ? '👁️' : ''}
                              </strong>
                              <span>
                                C.{layer.start_layer_num}–{layer.end_layer_num} ({layer.end_mm.toFixed(2)}mm)
                              </span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )
        ) : (
          /* MODE 2 (OPTIONAL): 3D RELIEF MESH VIEWER */
          <div style={{ flex: 1, position: 'relative', display: 'flex', flexDirection: 'column' }}>
            <div className="hf-3d-subbar">
              <span>
                🧊 <strong>Inspection Topographique 3D :</strong> Cliquez sur{' '}
                <strong>« ⚡ Générer les Fichiers STL HueForge HD »</strong> en bas à gauche pour charger le
                maillage 3D réel découpé.
              </span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '0.73rem', color: '#94a3b8' }}>
                  Exagération Relief Z : <strong className="text-cyan">×{verticalExaggeration}</strong>
                </span>
                <input
                  type="range"
                  min="1"
                  max="6"
                  step="0.5"
                  value={verticalExaggeration}
                  onChange={(e) => setVerticalExaggeration(parseFloat(e.target.value))}
                  style={{ width: '110px', accentColor: '#ff2a6d' }}
                />
              </div>
            </div>
            <Viewer3D
              stlUrl={previewStlUrl}
              colorLayers={activePalette}
              scaleZ={verticalExaggeration}
              modelStats={
                genResult
                  ? {
                      extents: genResult.parts[0]?.extents_mm || [200, 200, 2.48],
                      is_watertight: true,
                      faces_count: genResult.parts.reduce((acc, p) => acc + p.faces_count, 0),
                    }
                  : null
              }
              bedSize={bedSize}
              showRod={false}
              pointA={null}
              pointB={null}
              onChangePointA={() => {}}
              onChangePointB={() => {}}
              rodConfig={{}}
              cutMode="auto_grid"
              cutPlanesZ={[]}
              boundedOrigin={[0, 0, 0]}
              boundedSize={[80, 80, 80]}
              boundedType="cylinder"
            />
          </div>
        )}
      </div>
    </div>
  );
}
