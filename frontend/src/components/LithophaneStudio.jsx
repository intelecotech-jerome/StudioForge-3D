import React, { useState, useRef, useEffect } from 'react';
import Viewer3D from './Viewer3D';

const API_BASE = 'http://127.0.0.1:8000';

const SHAPE_OPTIONS = [
  {
    id: 'flat_plate',
    icon: '🖼️',
    title: 'Lithophanie Plate & Formes',
    desc: 'Classique, Cœur, Étoile, Nid d’abeille, Rond, Grille L×H...',
  },
  {
    id: 'sphere_globe',
    icon: '🌕',
    title: 'Boule / Planètes Officiel',
    desc: '19 Planètes & Lunes STL officielles ou Photo + 9 Socles LED',
  },
  {
    id: 'cylinder_lamp',
    icon: '🕯️',
    title: 'Abat-Jour Cylindre 360°',
    desc: 'Taille auto-adaptée à l’image + Support Lampe surélevé & fil',
  },
  {
    id: 'polygon_lantern',
    icon: '🏮',
    title: 'Polygon / Lanterne (5–8 Faces)',
    desc: 'Lanterne multi-facettes + anneaux suspension + support lampe',
  },
  {
    id: 'cone_lampshade',
    icon: '📐',
    title: 'Cone / Abat-Jour Conique',
    desc: 'Abat-jour conique évasé 360° + support lampe LED intégré',
  },
  {
    id: 'vase_lumina',
    icon: '🏺',
    title: 'Vase / Amphore Lumineuse',
    desc: 'Vase galbé 360° design porcelaine + support lampe LED',
  },
  {
    id: 'accordion_dual',
    icon: '🪗',
    title: 'Dual / Paravent Zig-Zag',
    desc: '2 à 4 volets pliés en accordéon (tient debout tout seul)',
  },
  {
    id: 'balloon_heart',
    icon: '🎈',
    title: 'Balloon / Cœur Bombé 3D',
    desc: 'Coussin Cœur gonflé en volume 3D + socle veilleuse intégré',
  },
  {
    id: 'stencil_cutout',
    icon: '🦒',
    title: 'Stencil / Silhouette Détourée',
    desc: 'Fond découpé autour du sujet + contour renforcé + socle',
  },
  {
    id: 'framed_lightbox',
    icon: '📦',
    title: 'Caisson Lightbox LED',
    desc: 'Façade + Boîtier avec support lampe sur barres (Vue 3D Assemblée)',
  },
  {
    id: 'cube_lightbox',
    icon: '🎲',
    title: 'Cube Lightbox 4-Faces',
    desc: '1 à 4 photos différentes + Support lampe sur barres (Vue 3D Cube)',
  },
  {
    id: 'curved_arc',
    icon: '🌙',
    title: 'Arc Courbé Autoportant',
    desc: 'Tient debout tout seul sans support (60° à 160°)',
  },
  {
    id: 'half_cylinder',
    icon: '🌓',
    title: 'Demi-Cylindre 180°',
    desc: 'Applique / Veilleuse dôme 180° haute stabilité',
  },
];

const FLAT_LAYOUT_OPTIONS = [
  { id: 'single_original', label: '▭ Rectangle / Format Photo', group: 'Forme Unique' },
  { id: 'single_hexagon', label: '⬡ Hexagone (Nid d’Abeille)', group: 'Forme Unique' },
  { id: 'single_circle', label: '◯ Rond / Médaillon', group: 'Forme Unique' },
  { id: 'single_square', label: '▢ Carré 1:1', group: 'Forme Unique' },
  { id: 'single_heart', label: '❤️ Cœur', group: 'Forme Unique' },
  { id: 'single_star5', label: '⭐ Étoile 5 Branches', group: 'Forme Unique' },
  { id: 'single_triangle', label: '△ Triangle Équilatéral', group: 'Forme Unique' },
  { id: 'single_diamond', label: '◇ Losange / Diamant', group: 'Forme Unique' },
  { id: 'single_shield', label: '🛡️ Blason / Écusson', group: 'Forme Unique' },
  { id: 'single_octagon', label: '⯃ Octogone', group: 'Forme Unique' },
  { id: 'single_arch', label: '🏛️ Arche / Vitrail', group: 'Forme Unique' },
  { id: 'multi_grid_squares', label: '⊞ Grille Sur-Mesure (L × H Carrés)', group: 'Multi-Tuiles' },
  { id: 'multi_puzzle', label: '🧩 Puzzle 3D Imbriqué (L × H Pièces Jigsaw)', group: 'Multi-Tuiles' },
  { id: 'multi_4_squares', label: '田 Quadriptyque (2×2 Carrés)', group: 'Multi-Tuiles' },
  { id: 'multi_7_hexagons', label: '❖ Ruche 7 Hexagones (Nid d’Abeille)', group: 'Multi-Tuiles' },
  { id: 'multi_4_triangles', label: '▲ Triforce 4 Triangles', group: 'Multi-Tuiles' },
  { id: 'multi_6_triangles', label: '✳️ Rosace 6 Triangles', group: 'Multi-Tuiles' },
];

const GLOBE_SOURCES = [
  { id: 'custom_photo', icon: '📷', label: 'Ma Photo (ou 1–4 Photos)', group: 'Photo & Import' },
  { id: 'external_stl', icon: '📂', label: 'Importer un .STL Externe', group: 'Photo & Import' },
  { id: 'planet_moon', icon: '🌕', label: 'La Lune (NASA Officiel HD)', group: 'Lunes & Sci-Fi' },
  { id: 'planet_death_star', icon: '🛸', label: 'Étoile de la Mort (Star Wars)', group: 'Lunes & Sci-Fi' },
  { id: 'planet_earth', icon: '🌍', label: 'La Terre — Frontières & Pays (comme votre photo)', group: 'La Terre (4 Versions)' },
  { id: 'planet_earth_topo', icon: '🏔️', label: 'La Terre — Topographie Pure', group: 'La Terre (4 Versions)' },
  { id: 'planet_earth_day', icon: '☀️', label: 'La Terre — Vue Jour & Nuages', group: 'La Terre (4 Versions)' },
  { id: 'planet_earth_bathy', icon: '🌊', label: 'La Terre — Bathymétrie Océans & Pays', group: 'La Terre (4 Versions)' },
  { id: 'planet_mars', icon: '🔴', label: 'Mars (Olympus Mons & Canyons)', group: 'Système Solaire' },
  { id: 'planet_jupiter', icon: '🟠', label: 'Jupiter (Bandes & Grande Tache)', group: 'Système Solaire' },
  { id: 'planet_saturn', icon: '🪐', label: 'Saturne (Atmosphère)', group: 'Système Solaire' },
  { id: 'planet_venus', icon: '🟡', label: 'Vénus — Surface Volcanique', group: 'Système Solaire' },
  { id: 'planet_venus_atmo', icon: '☁️', label: 'Vénus — Atmosphère', group: 'Système Solaire' },
  { id: 'planet_mercury', icon: '🪨', label: 'Mercure (Cratères)', group: 'Système Solaire' },
  { id: 'planet_uranus', icon: '🩵', label: 'Uranus', group: 'Système Solaire' },
  { id: 'planet_neptune', icon: '🔵', label: 'Neptune', group: 'Système Solaire' },
  { id: 'planet_pluto', icon: '❄️', label: 'Pluton (Cœur Tombaugh)', group: 'Système Solaire' },
  { id: 'planet_sun', icon: '☀️', label: 'Le Soleil (Éruptions)', group: 'Système Solaire' },
  { id: 'planet_europa', icon: '🧊', label: 'Europe (Lune Glacée de Jupiter)', group: 'Lunes & Sci-Fi' },
  { id: 'planet_callisto', icon: '🌑', label: 'Callisto (Lune Cratérisée)', group: 'Lunes & Sci-Fi' },
  { id: 'planet_universe', icon: '🌌', label: 'Expansion de l’Univers (Cosmologie)', group: 'Lunes & Sci-Fi' },
];

const GLOBE_STANDS = [
  { id: 'stand_bambu_official', icon: '⭐', title: 'Socle Officiel Bambu', desc: 'Votre STL officiel 04_bambu_base.stl' },
  { id: 'stand_rock_lunar', icon: '🪨', title: 'Socle Rocheux Lunaire', desc: 'Votre STL officiel 05_rock_base.stl' },
  { id: 'stand_wavy_moon', icon: '🌊', title: 'Socle Ondulé Wavy', desc: 'Votre STL Moon Lamp Wavy Stand' },
  { id: 'stand_legacy_smooth', icon: '💿', title: 'Socle Classique Lisse', desc: 'Votre STL 02_legacy_base_no_threads' },
  { id: 'stand_legacy_threaded', icon: '🔩', title: 'Socle Classique Fileté', desc: 'Votre STL 02_legacy_base_threaded' },
  { id: 'ring_bambu', icon: '⭕', title: 'Socle Anneau Paramétrique', desc: 'S’adapte à tout diamètre de lampe' },
  { id: 'tripod_modern', icon: '🛸', title: 'Socle Trépied 3 Pieds', desc: '3 bras design + berceau LED suspendu' },
  { id: 'pedestal_fluted', icon: '🏛️', title: 'Piédestal Cannelé', desc: 'Colonne striée architecturale' },
  { id: 'crown_gothic', icon: '👑', title: 'Couronne 4 Griffes', desc: '4 arches royales enlaçant la boule' },
];

const LED_TINTS = [
  { id: 'warm_3000k', label: '💡 Blanc Chaud 3000K', swatch: '#ffefc2' },
  { id: 'neutral_5500k', label: '☀️ Blanc Pur 5500K', swatch: '#f0f9ff' },
  { id: 'candle_2200k', label: '🕯️ Bougie 2200K', swatch: '#ffb74d' },
  { id: 'red_crimson', label: '🔴 LED Rouge', swatch: '#ff4747' },
  { id: 'orange_sunset', label: '🟠 LED Orange', swatch: '#ff9432' },
  { id: 'gold_amber', label: '🟡 LED Jaune Or', swatch: '#ffe047' },
  { id: 'emerald_green', label: '🟢 LED Vert', swatch: '#4ade80' },
  { id: 'cyan_cyber', label: '🩵 LED Cyan', swatch: '#67e8f9' },
  { id: 'royal_blue', label: '🔵 LED Bleu', swatch: '#60a5fa' },
  { id: 'violet_purple', label: '🟣 LED Violet', swatch: '#c084fc' },
  { id: 'magenta_pink', label: '🩷 LED Rose', swatch: '#f472b6' },
  { id: 'custom_rgb', label: '🎨 Sur-Mesure RGB', swatch: 'conic-gradient(red, yellow, lime, cyan, blue, magenta, red)' },
  { id: 'plastic_off', label: '🌑 Éteint (PLA Blanc)', swatch: '#cbd5e1' },
];

export default function LithophaneStudio({ bedSize = [300, 300, 300] }) {
  const fileInputRef = useRef(null);
  const extraFileRefs = { 1: useRef(null), 2: useRef(null), 3: useRef(null) };
  const externalStlRef = useRef(null);

  const [sessionId, setSessionId] = useState(null);
  const [filename, setFilename] = useState(null);
  const [imageSize, setImageSize] = useState(null);
  const [aspectRatio, setAspectRatio] = useState(1.0);
  const [sourcePreviewB64, setSourcePreviewB64] = useState(null);
  const [backlightPreviewB64, setBacklightPreviewB64] = useState(null);

  // Extra images for Cube 4-Faces / Cylinder / Globe (slots 1, 2, 3)
  const [extraImages, setExtraImages] = useState({});
  const [externalGlobeFilename, setExternalGlobeFilename] = useState(null);

  // Printers & Lamp Standards
  const [printers, setPrinters] = useState([]);
  const [selectedPrinterId, setSelectedPrinterId] = useState('');
  const [lampStandards, setLampStandards] = useState([]);
  const [lampStandardId, setLampStandardId] = useState('bambu_led_001');
  const [showNewLampModal, setShowNewLampModal] = useState(false);
  const [newLampName, setNewLampName] = useState('');

  // Architecture & Shape Parameters
  const [shapeMode, setShapeMode] = useState('flat_plate');
  const [flatLayoutMode, setFlatLayoutMode] = useState('single_original');
  const [gridCols, setGridCols] = useState(2);
  const [gridRows, setGridRows] = useState(2);

  const [globeSourceMode, setGlobeSourceMode] = useState('custom_photo');
  const [globeStandStyle, setGlobeStandStyle] = useState('stand_bambu_official');
  const [sphereDiameterMm, setSphereDiameterMm] = useState(140.0);

  // New Architecture Controls (Accordion Dual & Polygon Lantern)
  const [accordionPanels, setAccordionPanels] = useState(3);
  const [polygonSides, setPolygonSides] = useState(6);

  const [widthMm, setWidthMm] = useState(140.0);
  const [effectiveWidthMm, setEffectiveWidthMm] = useState(140.0);
  const [effectiveHeightMm, setEffectiveHeightMm] = useState(140.0);
  const [maxTileExtentsMm, setMaxTileExtentsMm] = useState([140.0, 140.0]);
  const [minThicknessMm, setMinThicknessMm] = useState(0.8);
  const [maxThicknessMm, setMaxThicknessMm] = useState(3.2);
  const [borderWidthMm, setBorderWidthMm] = useState(4.0);
  const [borderExtraMm, setBorderExtraMm] = useState(0.8);

  // Optical & Image Controls
  const [negativeInvert, setNegativeInvert] = useState(false);
  const [flipHorizontal, setFlipHorizontal] = useState(false);
  const [contrast, setContrast] = useState(1.15);
  const [gamma, setGamma] = useState(1.0);
  const [detailBoost, setDetailBoost] = useState(1.2);
  const [smoothingSigma, setSmoothingSigma] = useState(0.45);
  const [tdMm, setTdMm] = useState(2.8);
  const [ledTint, setLedTint] = useState('warm_3000k');
  const [customLedHex, setCustomLedHex] = useState('#ff9d00');

  // Shape-specific Controls
  const [curveAngleDeg, setCurveAngleDeg] = useState(90.0);
  const [cylinderDiameterMm, setCylinderDiameterMm] = useState(90.0);
  const [autoAdaptCylinder, setAutoAdaptCylinder] = useState(true);
  const [lightboxDepthMm, setLightboxDepthMm] = useState(42.0);

  // Lamp Mount Mechanical Parameters
  const [ledSocketDiameterMm, setLedSocketDiameterMm] = useState(60.0);
  const [lampElevationMm, setLampElevationMm] = useState(8.0);
  const [lampRecessDepthMm, setLampRecessDepthMm] = useState(9.0);
  const [cableNotchWidthMm, setCableNotchWidthMm] = useState(8.5);
  const [cableNotchHeightMm, setCableNotchHeightMm] = useState(6.5);

  const [addHangingRing, setAddHangingRing] = useState(false);
  const [addStandFeet, setAddStandFeet] = useState(false);
  const [standVerticalForPrint, setStandVerticalForPrint] = useState(true);
  const [gridResolution, setGridResolution] = useState(280);

  // 3D Output State
  const [viewTab, setViewTab] = useState('2d');
  const [stlPreviewUrl, setStlPreviewUrl] = useState(null);
  const [activePartPreviewIdx, setActivePartPreviewIdx] = useState(0); // 0 = Full Assembly, 1..N = Part #
  const [meshStats, setMeshStats] = useState(null);
  const [partsMeta, setPartsMeta] = useState([]);
  const [downloadStlUrl, setDownloadStlUrl] = useState(null);
  const [downloadZipUrl, setDownloadZipUrl] = useState(null);

  const [loading2D, setLoading2D] = useState(false);
  const [loading3D, setLoading3D] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);

  // Load Printers & Lamp Standards on mount
  useEffect(() => {
    fetch(`${API_BASE}/api/printers`)
      .then((r) => r.json())
      .then((d) => {
        if (d.printers && d.printers.length > 0) {
          setPrinters(d.printers);
          setSelectedPrinterId(d.printers[0].id);
        }
      })
      .catch(() => {});

    fetch(`${API_BASE}/api/lithophane/lamp-standards`)
      .then((r) => r.json())
      .then((d) => {
        if (d.lamp_standards) setLampStandards(d.lamp_standards);
      })
      .catch(() => {});
  }, []);

  const currentPrinter = printers.find((p) => p.id === selectedPrinterId) || {
    name: 'Creality K1 Max',
    bed_x_mm: bedSize[0] || 300,
    bed_y_mm: bedSize[1] || 300,
    bed_z_mm: bedSize[2] || 300,
  };
  const activeBedSize = [
    Number(currentPrinter.bed_x_mm || 300),
    Number(currentPrinter.bed_y_mm || 300),
    Number(currentPrinter.bed_z_mm || 300),
  ];

  // Check if current tile/object exceeds printer bed
  const checkBedOverflow = () => {
    const [bx, by, bz] = activeBedSize;
    if (shapeMode === 'flat_plate' && flatLayoutMode !== 'single_original') {
      const [tw, th] = maxTileExtentsMm;
      if (tw > bx || th > by) {
        return `⚠️ Attention : La taille d'une tuile (${tw} × ${th} mm) dépasse le plateau de ${currentPrinter.name} (${bx} × ${by} mm) ! Réduisez la taille unitaire.`;
      }
    } else if (shapeMode === 'sphere_globe') {
      if (sphereDiameterMm > Math.min(bx, by, bz)) {
        return `⚠️ Attention : La boule Ø${sphereDiameterMm} mm dépasse le volume de ${currentPrinter.name} (${bx}×${by}×${bz} mm) !`;
      }
    } else if (shapeMode === 'cylinder_lamp') {
      if (cylinderDiameterMm > Math.min(bx, by) || effectiveHeightMm > bz) {
        return `⚠️ Attention : Le cylindre (Ø${cylinderDiameterMm} × H${effectiveHeightMm} mm) dépasse le volume de ${currentPrinter.name} !`;
      }
    } else {
      const maxXY = Math.max(bx, by);
      if (effectiveWidthMm > maxXY || effectiveHeightMm > bz) {
        return `⚠️ Attention : Les dimensions (${effectiveWidthMm} × ${effectiveHeightMm} mm) dépassent le volume de ${currentPrinter.name} (${bx}×${by}×${bz} mm) !`;
      }
    }
    return null;
  };
  const bedWarning = checkBedOverflow();

  const applyLampStandard = (stdId) => {
    setLampStandardId(stdId);
    const found = lampStandards.find((s) => s.id === stdId);
    if (found) {
      setLedSocketDiameterMm(Number(found.puck_diameter_mm));
      setLampElevationMm(Number(found.elevation_mm));
      setLampRecessDepthMm(Number(found.recess_depth_mm));
      setCableNotchWidthMm(Number(found.cable_notch_width_mm));
      setCableNotchHeightMm(Number(found.cable_notch_height_mm));
    }
  };

  const handleSaveCustomLampStandard = async () => {
    if (!newLampName.trim()) return;
    try {
      const res = await fetch(`${API_BASE}/api/lithophane/lamp-standards`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newLampName.trim(),
          puck_diameter_mm: Number(ledSocketDiameterMm),
          inner_ledge_diameter_mm: Math.max(10, Number(ledSocketDiameterMm) - 5.5),
          recess_depth_mm: Number(lampRecessDepthMm),
          elevation_mm: Number(lampElevationMm),
          cable_notch_width_mm: Number(cableNotchWidthMm),
          cable_notch_height_mm: Number(cableNotchHeightMm),
        }),
      });
      const data = await res.json();
      if (data.lamp_standards) {
        setLampStandards(data.lamp_standards);
        const newest = data.lamp_standards[data.lamp_standards.length - 1];
        if (newest) setLampStandardId(newest.id);
      }
      setNewLampName('');
      setShowNewLampModal(false);
    } catch (e) {
      setErrorMsg(e.message);
    }
  };

  const buildRequestPayload = (overrides = {}) => ({
    shape_mode: shapeMode,
    width_mm: Number(widthMm),
    height_mm: 0.0,
    min_thickness_mm: Number(minThicknessMm),
    max_thickness_mm: Number(maxThicknessMm),
    border_width_mm: Number(borderWidthMm),
    border_extra_mm: Number(borderExtraMm),
    flat_layout_mode: flatLayoutMode,
    grid_cols: Number(gridCols),
    grid_rows: Number(gridRows),
    negative_invert: Boolean(negativeInvert),
    flip_horizontal: Boolean(flipHorizontal),
    contrast: Number(contrast),
    gamma: Number(gamma),
    detail_boost: Number(detailBoost),
    smoothing_sigma: Number(smoothingSigma),
    td_mm: Number(tdMm),
    led_tint: ledTint,
    custom_led_hex: customLedHex,
    curve_angle_deg: Number(curveAngleDeg),
    cylinder_diameter_mm: Number(cylinderDiameterMm),
    auto_adapt_cylinder: Boolean(autoAdaptCylinder),
    lightbox_depth_mm: Number(lightboxDepthMm),
    lamp_standard_id: lampStandardId,
    led_socket_diameter_mm: Number(ledSocketDiameterMm),
    lamp_elevation_mm: Number(lampElevationMm),
    lamp_recess_depth_mm: Number(lampRecessDepthMm),
    cable_notch_width_mm: Number(cableNotchWidthMm),
    cable_notch_height_mm: Number(cableNotchHeightMm),
    globe_source_mode: globeSourceMode,
    globe_stand_style: globeStandStyle,
    sphere_diameter_mm: Number(sphereDiameterMm),
    accordion_panels: Number(accordionPanels),
    polygon_sides: Number(polygonSides),
    add_hanging_ring: Boolean(addHangingRing),
    add_stand_feet: Boolean(addStandFeet),
    stand_vertical_for_print: Boolean(standVerticalForPrint),
    grid_resolution: Number(gridResolution),
    ...overrides,
  });

  const handleUploadImage = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setLoading2D(true);
    setErrorMsg(null);
    setStlPreviewUrl(null);
    setPartsMeta([]);
    setExtraImages({});

    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch(`${API_BASE}/api/lithophane/upload-image`, {
        method: 'POST',
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Erreur upload image');
      }
      const data = await res.json();
      setSessionId(data.session_id);
      setFilename(data.filename);
      setImageSize(data.image_size);
      setAspectRatio(data.aspect_ratio);
      setEffectiveWidthMm(data.effective_width_mm);
      setEffectiveHeightMm(data.effective_height_mm);
      setSourcePreviewB64(data.source_preview_b64);
      setBacklightPreviewB64(data.backlight_preview_b64);
      setViewTab('2d');
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setLoading2D(false);
    }
  };

  const handleInitPlanetSession = async (planetMode) => {
    setGlobeSourceMode(planetMode);
    setShapeMode('sphere_globe');
    if (sessionId) {
      // Session already exists, just refresh 2D preview with the new planet mode
      refresh2DPreview({ shape_mode: 'sphere_globe', globe_source_mode: planetMode });
      return;
    }
    setLoading2D(true);
    setErrorMsg(null);
    try {
      const res = await fetch(
        `${API_BASE}/api/lithophane/init-planet-session?planet_mode=${planetMode}`,
        { method: 'POST' }
      );
      const data = await res.json();
      setSessionId(data.session_id);
      setFilename(data.filename);
      setImageSize(data.image_size);
      setAspectRatio(data.aspect_ratio);
      setEffectiveWidthMm(data.effective_width_mm);
      setEffectiveHeightMm(data.effective_height_mm);
      setSourcePreviewB64(data.source_preview_b64);
      setBacklightPreviewB64(data.backlight_preview_b64);
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setLoading2D(false);
    }
  };

  const handleUploadExtraImage = async (slot, e) => {
    const file = e.target.files?.[0];
    if (!file || !sessionId) return;
    setLoading2D(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch(
        `${API_BASE}/api/lithophane/${sessionId}/upload-extra-image?slot=${slot}`,
        { method: 'POST', body: formData }
      );
      if (!res.ok) throw new Error('Erreur import photo supplémentaire');
      const data = await res.json();
      setExtraImages((prev) => ({
        ...prev,
        [slot]: { filename: data.filename, thumb_b64: data.thumb_b64 },
      }));
      await refresh2DPreview();
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setLoading2D(false);
    }
  };

  const handleRemoveExtraImage = async (slot) => {
    if (!sessionId) return;
    await fetch(`${API_BASE}/api/lithophane/${sessionId}/extra-image/${slot}`, {
      method: 'DELETE',
    });
    setExtraImages((prev) => {
      const copy = { ...prev };
      delete copy[slot];
      return copy;
    });
    refresh2DPreview();
  };

  const handleUploadExternalGlobeStl = async (e) => {
    const file = e.target.files?.[0];
    if (!file || !sessionId) return;
    setLoading2D(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch(`${API_BASE}/api/lithophane/${sessionId}/upload-globe-stl`, {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      setExternalGlobeFilename(data.external_globe_filename);
      setGlobeSourceMode('external_stl');
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setLoading2D(false);
    }
  };

  const refresh2DPreview = async (overrides = {}) => {
    if (!sessionId) return;
    setLoading2D(true);
    setErrorMsg(null);
    try {
      const payload = buildRequestPayload(overrides);
      const res = await fetch(`${API_BASE}/api/lithophane/${sessionId}/preview-2d`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Erreur simulation 2D');
      }
      const data = await res.json();
      setBacklightPreviewB64(data.backlight_preview_b64);
      if (data.source_preview_b64) setSourcePreviewB64(data.source_preview_b64);
      setEffectiveWidthMm(data.effective_width_mm);
      setEffectiveHeightMm(data.effective_height_mm);
      if (data.max_tile_extents_mm) setMaxTileExtentsMm(data.max_tile_extents_mm);
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setLoading2D(false);
    }
  };

  useEffect(() => {
    if (!sessionId) return;
    const timer = setTimeout(() => {
      refresh2DPreview();
    }, 180);
    return () => clearTimeout(timer);
  }, [
    shapeMode,
    flatLayoutMode,
    gridCols,
    gridRows,
    globeSourceMode,
    sphereDiameterMm,
    accordionPanels,
    polygonSides,
    widthMm,
    cylinderDiameterMm,
    autoAdaptCylinder,
    minThicknessMm,
    maxThicknessMm,
    borderWidthMm,
    borderExtraMm,
    negativeInvert,
    flipHorizontal,
    contrast,
    gamma,
    detailBoost,
    smoothingSigma,
    tdMm,
    ledTint,
    customLedHex,
  ]);

  const handleGenerate3D = async () => {
    if (!sessionId) return;
    setLoading3D(true);
    setErrorMsg(null);
    try {
      const payload = buildRequestPayload();
      const res = await fetch(`${API_BASE}/api/lithophane/${sessionId}/generate-stl`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Erreur génération 3D STL');
      }
      const data = await res.json();
      setActivePartPreviewIdx(0); // Default to full 3D assembly preview!
      setStlPreviewUrl(`${API_BASE}${data.preview_stl_url}?part_index=0&t=${Date.now()}`);
      setMeshStats(data.stats);
      setPartsMeta(data.parts || []);
      setDownloadStlUrl(`${API_BASE}${data.download_stl_url}`);
      setDownloadZipUrl(`${API_BASE}${data.download_zip_url}`);
      setViewTab('3d');
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setLoading3D(false);
    }
  };

  const handleSelectPartPreview = (partIndex) => {
    if (!sessionId) return;
    setActivePartPreviewIdx(partIndex);
    setStlPreviewUrl(`${API_BASE}/api/lithophane/${sessionId}/preview-stl?part_index=${partIndex}&t=${Date.now()}`);
  };

  const showLampMountControls = [
    'cylinder_lamp',
    'polygon_lantern',
    'cone_lampshade',
    'vase_lumina',
    'sphere_globe',
    'framed_lightbox',
    'cube_lightbox',
  ].includes(shapeMode);
  const showMultiImagePanel =
    shapeMode === 'cube_lightbox' ||
    shapeMode === 'cylinder_lamp' ||
    shapeMode === 'polygon_lantern' ||
    shapeMode === 'cone_lampshade' ||
    shapeMode === 'vase_lumina' ||
    shapeMode === 'accordion_dual' ||
    (shapeMode === 'sphere_globe' && globeSourceMode === 'custom_photo');

  return (
    <div className="app-layout" style={{ height: 'calc(100vh - 48px)' }}>
      {/* LEFT SIDEBAR : LITHOPHANE & LIGHTBOX CONTROLS */}
      <aside className="sidebar" style={{ height: 'calc(100vh - 48px)', width: '445px', minWidth: '445px' }}>
        <div className="sidebar-scroll">
          {/* SECTION 1 : PRINTER & IMAGE UPLOAD */}
        <section className="panel-card">
          <div className="panel-title">
            <span>1. IMPRIMANTE & PHOTO SOURCE</span>
            <span className="badge-step">M2B V2</span>
          </div>

          {/* Printer selector for bed check */}
          {printers.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.68rem', color: '#94a3b8', marginBottom: 3 }}>
                <span>Imprimante cible :</span>
                <span className="text-cyan">
                  Plateau {activeBedSize[0]}×{activeBedSize[1]}×{activeBedSize[2]} mm
                </span>
              </div>
              <select
                value={selectedPrinterId}
                onChange={(e) => setSelectedPrinterId(e.target.value)}
                style={{
                  width: '100%',
                  background: '#0f172a',
                  color: '#e2e8f0',
                  border: '1px solid #1e293b',
                  borderRadius: 6,
                  padding: '5px 8px',
                  fontSize: '0.74rem',
                }}
              >
                {printers.map((p) => (
                  <option key={p.id} value={p.id}>
                    🖨️ {p.name} ({p.bed_x_mm}×{p.bed_y_mm}×{p.bed_z_mm} mm)
                  </option>
                ))}
              </select>
            </div>
          )}

          <input
            type="file"
            accept=".png,.jpg,.jpeg,.webp"
            ref={fileInputRef}
            style={{ display: 'none' }}
            onChange={handleUploadImage}
          />
          <div style={{ display: 'flex', gap: 6 }}>
            <button
              className="btn-cyber primary"
              style={{ flex: 1 }}
              onClick={() => fileInputRef.current?.click()}
              disabled={loading2D}
            >
              {loading2D ? 'Traitement...' : '📷 Importer une Photo'}
            </button>
            <button
              className="btn-cyber secondary"
              style={{ padding: '7px 10px', fontSize: '0.74rem', flex: '0 0 auto' }}
              onClick={() => handleInitPlanetSession('planet_moon')}
              title="Lancer directement une Boule Lune 3D sans photo"
            >
              🌕 Lune 3D
            </button>
          </div>

          {filename && (
            <div className="file-pill">
              <div>
                <strong>Source :</strong> {filename} ({imageSize?.[0]}×{imageSize?.[1]} px)
              </div>
              <div>
                <strong>Dimensions 3D :</strong>{' '}
                <span className="text-cyan">
                  {effectiveWidthMm} × {effectiveHeightMm} mm
                </span>
              </div>
            </div>
          )}

          {bedWarning && (
            <div
              style={{
                marginTop: 8,
                padding: '7px 9px',
                borderRadius: 6,
                background: 'rgba(245, 158, 11, 0.14)',
                border: '1px solid #f59e0b',
                color: '#fcd34d',
                fontSize: '0.71rem',
                lineHeight: 1.35,
              }}
            >
              {bedWarning}
            </div>
          )}

          {/* MULTI-IMAGE LOADER (Cube 4 Faces / Cylinder / Photo Globe) */}
          {sessionId && showMultiImagePanel && (
            <div
              style={{
                marginTop: 10,
                padding: '8px',
                borderRadius: 7,
                background: 'rgba(15, 23, 42, 0.78)',
                border: '1px solid #1e293b',
              }}
            >
              <div style={{ fontSize: '0.72rem', fontWeight: 700, color: '#38bdf8', marginBottom: 4 }}>
                🖼️ Mode Multi-Images ({shapeMode === 'cube_lightbox' ? '1 Photo par Face du Cube' : 'Panoramique 360°'}) :
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 5 }}>
                {[1, 2, 3].map((slot) => {
                  const slotLabels =
                    shapeMode === 'cube_lightbox'
                      ? { 1: 'Face 2 (Droite)', 2: 'Face 3 (Arrière)', 3: 'Face 4 (Gauche)' }
                      : { 1: 'Photo #2', 2: 'Photo #3', 3: 'Photo #4' };
                  const item = extraImages[slot];
                  return (
                    <div
                      key={slot}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        background: '#090d16',
                        border: item ? '1px solid #00f0ff' : '1px dashed #334155',
                        borderRadius: 5,
                        padding: '4px 6px',
                        fontSize: '0.68rem',
                      }}
                    >
                      <input
                        type="file"
                        accept=".png,.jpg,.jpeg,.webp"
                        ref={extraFileRefs[slot]}
                        style={{ display: 'none' }}
                        onChange={(e) => handleUploadExtraImage(slot, e)}
                      />
                      {item ? (
                        <>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 5, overflow: 'hidden' }}>
                            <img
                              src={item.thumb_b64}
                              alt=""
                              style={{ width: 22, height: 22, objectFit: 'cover', borderRadius: 3 }}
                            />
                            <span style={{ color: '#e2e8f0', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                              {slotLabels[slot]}
                            </span>
                          </div>
                          <button
                            onClick={() => handleRemoveExtraImage(slot)}
                            style={{ background: 'transparent', border: 'none', color: '#f43f5e', cursor: 'pointer', fontWeight: 700 }}
                            title="Retirer cette photo"
                          >
                            ✕
                          </button>
                        </>
                      ) : (
                        <button
                          onClick={() => extraFileRefs[slot].current?.click()}
                          style={{
                            width: '100%',
                            background: 'transparent',
                            border: 'none',
                            color: '#94a3b8',
                            cursor: 'pointer',
                            textAlign: 'left',
                            fontSize: '0.67rem',
                          }}
                        >
                          + {slotLabels[slot]}
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </section>

        {/* SECTION 2 : 7 ARCHITECTURES 3D */}
        <section className={`panel-card ${!sessionId ? 'disabled-card' : ''}`}>
          <div className="panel-title">
            <span>2. ARCHITECTURE 3D & FORME</span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 10 }}>
            {SHAPE_OPTIONS.map((opt) => {
              const active = shapeMode === opt.id;
              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => setShapeMode(opt.id)}
                  style={{
                    textAlign: 'left',
                    padding: '7px 8px',
                    borderRadius: 7,
                    border: active ? '1px solid #00f0ff' : '1px solid #1e293b',
                    background: active ? 'rgba(0, 240, 255, 0.12)' : 'rgba(15, 23, 42, 0.65)',
                    color: '#f8fafc',
                    cursor: 'pointer',
                  }}
                >
                  <div style={{ fontSize: '0.75rem', fontWeight: 700, color: active ? '#00f0ff' : '#e2e8f0' }}>
                    {opt.icon} {opt.title}
                  </div>
                  <div style={{ fontSize: '0.63rem', color: '#94a3b8', marginTop: 2, lineHeight: 1.2 }}>
                    {opt.desc}
                  </div>
                </button>
              );
            })}
          </div>

          {/* SUB-PANEL A : FLAT PLATE SHAPES & MULTI-TILES (LIKE HUEFORGE) */}
          {shapeMode === 'flat_plate' && (
            <div
              style={{
                padding: '8px',
                borderRadius: 7,
                background: 'rgba(15, 23, 42, 0.78)',
                border: '1px solid #1e293b',
                marginBottom: 10,
              }}
            >
              <div style={{ fontSize: '0.72rem', fontWeight: 700, color: '#00f0ff', marginBottom: 5 }}>
                ✨ Forme Géométrique ou Multi-Tuiles (Style HueForge) :
              </div>
              <select
                value={flatLayoutMode}
                onChange={(e) => setFlatLayoutMode(e.target.value)}
                style={{
                  width: '100%',
                  background: '#090d16',
                  color: '#f8fafc',
                  border: '1px solid #334155',
                  borderRadius: 6,
                  padding: '6px 8px',
                  fontSize: '0.74rem',
                }}
              >
                {FLAT_LAYOUT_OPTIONS.map((lo) => (
                  <option key={lo.id} value={lo.id}>
                    [{lo.group}] {lo.label}
                  </option>
                ))}
              </select>

              {(flatLayoutMode === 'multi_grid_squares' || flatLayoutMode === 'multi_puzzle') && (
                <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                  <label className="field-label" style={{ flex: 1 }}>
                    <span>Largeur (Colonnes) : {gridCols}</span>
                    <input
                      type="range"
                      min="1"
                      max="6"
                      step="1"
                      value={gridCols}
                      onChange={(e) => setGridCols(parseInt(e.target.value, 10))}
                    />
                  </label>
                  <label className="field-label" style={{ flex: 1 }}>
                    <span>Hauteur (Lignes) : {gridRows}</span>
                    <input
                      type="range"
                      min="1"
                      max="6"
                      step="1"
                      value={gridRows}
                      onChange={(e) => setGridRows(parseInt(e.target.value, 10))}
                    />
                  </label>
                </div>
              )}
            </div>
          )}

          {/* SUB-PANEL B : SPHERE / GLOBE SOURCE (19 OFFICIAL PLANETS / PHOTO / STL) & 9 SOCLES */}
          {shapeMode === 'sphere_globe' && (
            <div
              style={{
                padding: '8px',
                borderRadius: 7,
                background: 'rgba(15, 23, 42, 0.82)',
                border: '1px solid #00f0ff44',
                marginBottom: 10,
              }}
            >
              <div style={{ fontSize: '0.72rem', fontWeight: 700, color: '#00f0ff', marginBottom: 5 }}>
                🌕 Source du Globe (Vos 19 Planètes & Lunes STL Officielles ou Photo) :
              </div>
              <select
                value={globeSourceMode}
                onChange={(e) => {
                  const val = e.target.value;
                  if (val.startsWith('planet_')) {
                    handleInitPlanetSession(val);
                  } else if (val === 'external_stl') {
                    externalStlRef.current?.click();
                  } else {
                    setGlobeSourceMode(val);
                  }
                }}
                style={{
                  width: '100%',
                  background: '#090d16',
                  color: '#f8fafc',
                  border: '1px solid #00f0ff',
                  borderRadius: 6,
                  padding: '6px 8px',
                  fontSize: '0.73rem',
                  fontWeight: 600,
                  marginBottom: 6,
                }}
              >
                {GLOBE_SOURCES.map((gs) => (
                  <option key={gs.id} value={gs.id}>
                    [{gs.group}] {gs.icon} {gs.label}
                  </option>
                ))}
              </select>

              {/* Quick Planet Shortcuts */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 4, marginBottom: 8 }}>
                {[
                  { id: 'planet_moon', label: '🌕 Lune' },
                  { id: 'planet_earth', label: '🌍 Terre Pays' },
                  { id: 'planet_mars', label: '🔴 Mars' },
                  { id: 'planet_death_star', label: '🛸 Death Star' },
                  { id: 'planet_jupiter', label: '🟠 Jupiter' },
                  { id: 'planet_saturn', label: '🪐 Saturne' },
                  { id: 'planet_earth_topo', label: '🏔️ Terre Topo' },
                  { id: 'custom_photo', label: '📷 Ma Photo' },
                ].map((q) => {
                  const act = globeSourceMode === q.id;
                  return (
                    <button
                      key={q.id}
                      type="button"
                      onClick={() => {
                        if (q.id.startsWith('planet_')) handleInitPlanetSession(q.id);
                        else setGlobeSourceMode(q.id);
                      }}
                      style={{
                        padding: '4px 5px',
                        borderRadius: 4,
                        border: act ? '1px solid #00f0ff' : '1px solid #1e293b',
                        background: act ? 'rgba(0, 240, 255, 0.16)' : '#090d16',
                        color: act ? '#00f0ff' : '#cbd5e1',
                        fontSize: '0.64rem',
                        fontWeight: act ? 700 : 500,
                        cursor: 'pointer',
                      }}
                    >
                      {q.label}
                    </button>
                  );
                })}
              </div>

              <input
                type="file"
                accept=".stl"
                ref={externalStlRef}
                style={{ display: 'none' }}
                onChange={handleUploadExternalGlobeStl}
              />
              {externalGlobeFilename && (
                <div style={{ fontSize: '0.68rem', color: '#4ade80', marginBottom: 6 }}>
                  ✓ STL Planète chargé : {externalGlobeFilename}
                </div>
              )}

              <label className="field-label">
                <span>Diamètre de la Boule : {sphereDiameterMm} mm</span>
                <input
                  type="range"
                  min="70"
                  max="240"
                  step="5"
                  value={sphereDiameterMm}
                  onChange={(e) => setSphereDiameterMm(parseFloat(e.target.value))}
                />
              </label>

              <div style={{ fontSize: '0.72rem', fontWeight: 700, color: '#38bdf8', margin: '6px 0 4px' }}>
                🏛️ Choix du Socle Porte-Lampe (5 Socles STL Officiels + 4 Paramétriques) :
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 5 }}>
                {GLOBE_STANDS.map((st) => {
                  const act = globeStandStyle === st.id;
                  return (
                    <button
                      key={st.id}
                      type="button"
                      onClick={() => setGlobeStandStyle(st.id)}
                      style={{
                        padding: '5px 7px',
                        borderRadius: 5,
                        border: act ? '1px solid #38bdf8' : '1px solid #1e293b',
                        background: act ? 'rgba(56, 189, 248, 0.15)' : '#090d16',
                        color: '#f8fafc',
                        cursor: 'pointer',
                        textAlign: 'left',
                      }}
                    >
                      <div style={{ fontSize: '0.68rem', fontWeight: 700, color: act ? '#38bdf8' : '#e2e8f0' }}>
                        {st.icon} {st.title}
                      </div>
                      <div style={{ fontSize: '0.59rem', color: '#94a3b8' }}>{st.desc}</div>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* SUB-PANEL C : ACCORDION DUAL (2 TO 4 PANELS) */}
          {shapeMode === 'accordion_dual' && (
            <div
              style={{
                padding: '8px',
                borderRadius: 7,
                background: 'rgba(15, 23, 42, 0.78)',
                border: '1px solid #1e293b',
                marginBottom: 10,
              }}
            >
              <div style={{ fontSize: '0.72rem', fontWeight: 700, color: '#00f0ff', marginBottom: 6 }}>
                🪗 Nombre de Volets Pliés en Accordéon (Autoportant) :
              </div>
              <div style={{ display: 'flex', gap: 6 }}>
                {[2, 3, 4].map((np) => (
                  <button
                    key={np}
                    type="button"
                    onClick={() => setAccordionPanels(np)}
                    style={{
                      flex: 1,
                      padding: '6px',
                      borderRadius: 6,
                      border: accordionPanels === np ? '1px solid #00f0ff' : '1px solid #334155',
                      background: accordionPanels === np ? 'rgba(0, 240, 255, 0.16)' : '#090d16',
                      color: accordionPanels === np ? '#00f0ff' : '#cbd5e1',
                      fontSize: '0.72rem',
                      fontWeight: 700,
                      cursor: 'pointer',
                    }}
                  >
                    {np} Volets ({np === 2 ? 'Dual V' : np === 3 ? 'Triptyque Z' : 'Paravent W'})
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* SUB-PANEL D : POLYGON LANTERN (5, 6, OR 8 FACES) */}
          {shapeMode === 'polygon_lantern' && (
            <div
              style={{
                padding: '8px',
                borderRadius: 7,
                background: 'rgba(15, 23, 42, 0.78)',
                border: '1px solid #1e293b',
                marginBottom: 10,
              }}
            >
              <div style={{ fontSize: '0.72rem', fontWeight: 700, color: '#00f0ff', marginBottom: 6 }}>
                🏮 Nombre de Faces de la Lanterne Polygone :
              </div>
              <div style={{ display: 'flex', gap: 6 }}>
                {[5, 6, 8].map((ns) => (
                  <button
                    key={ns}
                    type="button"
                    onClick={() => setPolygonSides(ns)}
                    style={{
                      flex: 1,
                      padding: '6px',
                      borderRadius: 6,
                      border: polygonSides === ns ? '1px solid #00f0ff' : '1px solid #334155',
                      background: polygonSides === ns ? 'rgba(0, 240, 255, 0.16)' : '#090d16',
                      color: polygonSides === ns ? '#00f0ff' : '#cbd5e1',
                      fontSize: '0.72rem',
                      fontWeight: 700,
                      cursor: 'pointer',
                    }}
                  >
                    {ns} Faces ({ns === 5 ? 'Pentagone' : ns === 6 ? 'Hexagone' : 'Octogone'})
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* DIMENSIONS SLIDERS */}
          {!['cylinder_lamp', 'polygon_lantern', 'cone_lampshade', 'vase_lumina', 'sphere_globe'].includes(shapeMode) && (
            <label className="field-label">
              <span>
                {shapeMode === 'cube_lightbox'
                  ? `Largeur Face Cube : ${widthMm} mm`
                  : shapeMode === 'balloon_heart'
                  ? `Largeur Cœur Bombé 3D : ${widthMm} mm`
                  : flatLayoutMode !== 'single_original'
                  ? `Taille Unitaire Forme / Tuile : ${widthMm} mm`
                  : `Largeur du Panneau : ${widthMm} mm (Hauteur auto: ${effectiveHeightMm} mm)`}
              </span>
              <input
                type="range"
                min="60"
                max="260"
                step="5"
                value={widthMm}
                onChange={(e) => setWidthMm(parseFloat(e.target.value))}
              />
            </label>
          )}

          {shapeMode === 'curved_arc' && (
            <label className="field-label">
              <span>Angle de Courbure Autoportant : {curveAngleDeg}°</span>
              <input
                type="range"
                min="45"
                max="160"
                step="5"
                value={curveAngleDeg}
                onChange={(e) => setCurveAngleDeg(parseFloat(e.target.value))}
              />
            </label>
          )}

          {['cylinder_lamp', 'polygon_lantern', 'cone_lampshade', 'vase_lumina'].includes(shapeMode) && (
            <>
              <label className="field-label">
                <span>
                  Diamètre Extérieur : Ø {cylinderDiameterMm} mm (Hauteur : {effectiveHeightMm} mm)
                </span>
                <input
                  type="range"
                  min="50"
                  max="200"
                  step="5"
                  value={cylinderDiameterMm}
                  onChange={(e) => setCylinderDiameterMm(parseFloat(e.target.value))}
                />
              </label>
              <label className="checkbox-row" style={{ marginBottom: 6 }}>
                <input
                  type="checkbox"
                  checked={autoAdaptCylinder}
                  onChange={(e) => setAutoAdaptCylinder(e.target.checked)}
                />
                <span>Adapter automatiquement la hauteur au ratio de l’image (360° complet)</span>
              </label>
            </>
          )}

          {shapeMode === 'framed_lightbox' && (
            <label className="field-label">
              <span>Profondeur du Caisson Lightbox : {lightboxDepthMm} mm</span>
              <input
                type="range"
                min="28"
                max="100"
                step="2"
                value={lightboxDepthMm}
                onChange={(e) => setLightboxDepthMm(parseFloat(e.target.value))}
              />
            </label>
          )}

          {/* STANDARD & CUSTOM LED LAMP MOUNT SYSTEM */}
          {showLampMountControls && (
            <div
              style={{
                marginTop: 8,
                padding: '8px',
                borderRadius: 7,
                background: 'rgba(15, 23, 42, 0.78)',
                border: '1px solid #1e293b',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5 }}>
                <span style={{ fontSize: '0.72rem', fontWeight: 700, color: '#fbbf24' }}>
                  💡 Support Lampe Surélevé & Encoche Fil :
                </span>
                <button
                  type="button"
                  onClick={() => setShowNewLampModal(!showNewLampModal)}
                  style={{
                    background: 'rgba(251, 191, 36, 0.15)',
                    border: '1px solid #fbbf24',
                    color: '#fde68a',
                    borderRadius: 4,
                    padding: '2px 6px',
                    fontSize: '0.65rem',
                    cursor: 'pointer',
                  }}
                >
                  + Nouveau Standard
                </button>
              </div>

              <select
                value={lampStandardId}
                onChange={(e) => applyLampStandard(e.target.value)}
                style={{
                  width: '100%',
                  background: '#090d16',
                  color: '#f8fafc',
                  border: '1px solid #334155',
                  borderRadius: 5,
                  padding: '5px 7px',
                  fontSize: '0.72rem',
                  marginBottom: 6,
                }}
              >
                {lampStandards.map((ls) => (
                  <option key={ls.id} value={ls.id}>
                    {ls.name}
                  </option>
                ))}
              </select>

              {showNewLampModal && (
                <div style={{ display: 'flex', gap: 5, marginBottom: 6 }}>
                  <input
                    type="text"
                    placeholder="Nom du standard (ex: Galet Amazon Ø65mm)"
                    value={newLampName}
                    onChange={(e) => setNewLampName(e.target.value)}
                    style={{
                      flex: 1,
                      background: '#090d16',
                      border: '1px solid #fbbf24',
                      color: '#fff',
                      borderRadius: 4,
                      padding: '4px 6px',
                      fontSize: '0.70rem',
                    }}
                  />
                  <button
                    type="button"
                    onClick={handleSaveCustomLampStandard}
                    style={{
                      background: '#fbbf24',
                      color: '#090d16',
                      border: 'none',
                      borderRadius: 4,
                      padding: '4px 8px',
                      fontSize: '0.70rem',
                      fontWeight: 700,
                      cursor: 'pointer',
                    }}
                  >
                    Sauver
                  </button>
                </div>
              )}

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                <label className="field-label" style={{ marginBottom: 0 }}>
                  <span style={{ fontSize: '0.66rem' }}>Ø Galet / Douille : {ledSocketDiameterMm} mm</span>
                  <input
                    type="range"
                    min="20"
                    max="100"
                    step="0.5"
                    value={ledSocketDiameterMm}
                    onChange={(e) => setLedSocketDiameterMm(parseFloat(e.target.value))}
                  />
                </label>
                <label className="field-label" style={{ marginBottom: 0 }}>
                  <span style={{ fontSize: '0.66rem' }}>Réhausse Socle : {lampElevationMm} mm</span>
                  <input
                    type="range"
                    min="4"
                    max="25"
                    step="0.5"
                    value={lampElevationMm}
                    onChange={(e) => setLampElevationMm(parseFloat(e.target.value))}
                  />
                </label>
                <label className="field-label" style={{ marginBottom: 0 }}>
                  <span style={{ fontSize: '0.66rem' }}>Encoche Fil (Larg.) : {cableNotchWidthMm} mm</span>
                  <input
                    type="range"
                    min="0"
                    max="18"
                    step="0.5"
                    value={cableNotchWidthMm}
                    onChange={(e) => setCableNotchWidthMm(parseFloat(e.target.value))}
                  />
                </label>
                <label className="field-label" style={{ marginBottom: 0 }}>
                  <span style={{ fontSize: '0.66rem' }}>Encoche Fil (Haut.) : {cableNotchHeightMm} mm</span>
                  <input
                    type="range"
                    min="0"
                    max="15"
                    step="0.5"
                    value={cableNotchHeightMm}
                    onChange={(e) => setCableNotchHeightMm(parseFloat(e.target.value))}
                  />
                </label>
              </div>
            </div>
          )}

          {shapeMode === 'flat_plate' && flatLayoutMode === 'single_original' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5, marginTop: 6 }}>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={addHangingRing}
                  onChange={(e) => setAddHangingRing(e.target.checked)}
                />
                <span>Ajouter un anneau de suspension en haut (Ø8 mm)</span>
              </label>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={addStandFeet}
                  onChange={(e) => setAddStandFeet(e.target.checked)}
                />
                <span>Ajouter 2 pieds de support intégrés à la base</span>
              </label>
            </div>
          )}
        </section>

        {/* SECTION 3 : CALIBRATION OPTIQUE & ÉPAISSEURS */}
        <section className={`panel-card ${!sessionId ? 'disabled-card' : ''}`}>
          <div className="panel-title">
            <span>3. CALIBRATION OPTIQUE & RELIEF</span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <label className="field-label">
              <span>Épaisseur Min (Clair) : {minThicknessMm.toFixed(1)} mm</span>
              <input
                type="range"
                min="0.4"
                max="1.6"
                step="0.1"
                value={minThicknessMm}
                onChange={(e) => setMinThicknessMm(parseFloat(e.target.value))}
              />
            </label>
            <label className="field-label">
              <span>Épaisseur Max (Noir) : {maxThicknessMm.toFixed(1)} mm</span>
              <input
                type="range"
                min="2.0"
                max="4.8"
                step="0.1"
                value={maxThicknessMm}
                onChange={(e) => setMaxThicknessMm(parseFloat(e.target.value))}
              />
            </label>
          </div>

          {shapeMode !== 'sphere_globe' && (
            <label className="field-label">
              <span>Largeur Bordure Opaque (Cadre) : {borderWidthMm.toFixed(1)} mm</span>
              <input
                type="range"
                min="0"
                max="10"
                step="0.5"
                value={borderWidthMm}
                onChange={(e) => setBorderWidthMm(parseFloat(e.target.value))}
              />
            </label>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <label className="field-label">
              <span>Contraste : ×{contrast.toFixed(2)}</span>
              <input
                type="range"
                min="0.6"
                max="2.0"
                step="0.05"
                value={contrast}
                onChange={(e) => setContrast(parseFloat(e.target.value))}
              />
            </label>
            <label className="field-label">
              <span>Netteté Micro-Détails : {detailBoost.toFixed(1)}</span>
              <input
                type="range"
                min="0.0"
                max="2.5"
                step="0.1"
                value={detailBoost}
                onChange={(e) => setDetailBoost(parseFloat(e.target.value))}
              />
            </label>
          </div>

          <div style={{ display: 'flex', gap: 12, marginTop: 4 }}>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={negativeInvert}
                onChange={(e) => setNegativeInvert(e.target.checked)}
              />
              <span>Inverser Négatif</span>
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={flipHorizontal}
                onChange={(e) => setFlipHorizontal(e.target.checked)}
              />
              <span>Miroir Horizontal</span>
            </label>
          </div>
        </section>

        {/* SECTION 4 : GÉNÉRATION 3D & EXPORT */}
        <section className={`panel-card ${!sessionId ? 'disabled-card' : ''}`}>
          <div className="panel-title">
            <span>4. GÉNÉRATION 3D & EXPORT SLICER</span>
          </div>

          <label className="field-label">
            <span>Finesse du Maillage 3D : {gridResolution} pts</span>
            <input
              type="range"
              min="160"
              max="440"
              step="20"
              value={gridResolution}
              onChange={(e) => setGridResolution(parseInt(e.target.value, 10))}
            />
          </label>

          <button
            className="btn-cyber pink-full"
            style={{ width: '100%', marginTop: 6 }}
            onClick={handleGenerate3D}
            disabled={!sessionId || loading3D}
          >
            {loading3D ? '⏳ Construction du Modèle 3D...' : '⚡ Générer le Modèle 3D & Vue Assemblée'}
          </button>

          {partsMeta.length > 0 && (
            <div style={{ marginTop: 10 }}>
              <div style={{ fontSize: '0.71rem', color: '#94a3b8', marginBottom: 5 }}>
                🔍 <strong>Inspecter dans la Vue 3D ({partsMeta.length} pièces) :</strong>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {partsMeta.length > 1 && (
                  <button
                    type="button"
                    onClick={() => handleSelectPartPreview(0)}
                    style={{
                      padding: '6px 8px',
                      borderRadius: 5,
                      border: activePartPreviewIdx === 0 ? '1px solid #00f0ff' : '1px solid #1e293b',
                      background: activePartPreviewIdx === 0 ? 'rgba(0, 240, 255, 0.16)' : '#090d16',
                      color: '#00f0ff',
                      fontSize: '0.72rem',
                      fontWeight: 700,
                      cursor: 'pointer',
                      textAlign: 'left',
                    }}
                  >
                    🌟 Vue 3D Assemblée Complète (Toutes les pièces montées)
                  </button>
                )}
                {partsMeta.map((p) => (
                  <div
                    key={p.part_index}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '4px 7px',
                      borderRadius: 5,
                      border: activePartPreviewIdx === p.part_index ? '1px solid #38bdf8' : '1px solid #1e293b',
                      background: activePartPreviewIdx === p.part_index ? 'rgba(56, 189, 248, 0.14)' : '#090d16',
                      fontSize: '0.69rem',
                    }}
                  >
                    <span
                      onClick={() => handleSelectPartPreview(p.part_index)}
                      style={{ cursor: 'pointer', color: '#e2e8f0', flex: 1 }}
                    >
                      <strong>#{p.part_index}</strong> {p.label} ({p.extents_mm[0]}×{p.extents_mm[1]}×{p.extents_mm[2]}mm)
                    </span>
                    <a
                      href={`${API_BASE}/api/lithophane/${sessionId}/download-stl?part_index=${p.part_index}`}
                      style={{ color: '#00f0ff', textDecoration: 'none', fontWeight: 700, marginLeft: 6 }}
                      title="Télécharger ce STL seul"
                    >
                      ⬇ STL
                    </a>
                  </div>
                ))}
              </div>

              <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                {downloadZipUrl && (
                  <a
                    href={downloadZipUrl}
                    className="btn-cyber download-zip-btn"
                    style={{ flex: 1, textAlign: 'center', textDecoration: 'none' }}
                  >
                    📦 Télécharger le Kit Complet (.ZIP : {partsMeta.length} STL + Guide)
                  </a>
                )}
              </div>
            </div>
          )}

          {errorMsg && <div className="error-banner">{errorMsg}</div>}
        </section>
        </div>
      </aside>

      {/* CENTER STUDIO : 2D & 3D VIEWPORT + FULL RGB LED COLOR SIMULATOR */}
      <div
        className="hf-studio-workspace"
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          height: 'calc(100vh - 48px)',
          overflow: 'hidden',
        }}
      >
        {/* Top Switch Bar + LED Color Simulator */}
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 8,
            padding: '8px 14px',
            background: '#0b0f17',
            borderBottom: '1px solid #1e293b',
          }}
        >
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              className={`btn-hud ${viewTab === '2d' ? 'active' : ''}`}
              onClick={() => setViewTab('2d')}
            >
              💡 Studio Rétro-Éclairage 2D
            </button>
            <button
              className={`btn-hud ${viewTab === '3d' ? 'active-pink' : ''}`}
              onClick={() => {
                if (stlPreviewUrl) setViewTab('3d');
                else if (sessionId) handleGenerate3D();
              }}
              disabled={!sessionId}
            >
              🧊 Vue 3D Interactive (Objet Fixe au Centre)
            </button>
          </div>

          {/* Full RGB LED Lamp Color Bar + Custom Color Picker */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, flexWrap: 'wrap' }}>
            <span style={{ fontSize: '0.70rem', color: '#94a3b8', marginRight: 2 }}>Couleur Lampe LED :</span>
            {LED_TINTS.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setLedTint(t.id)}
                title={t.label}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  padding: '3px 7px',
                  borderRadius: 5,
                  fontSize: '0.68rem',
                  cursor: 'pointer',
                  border: ledTint === t.id ? '1px solid #00f0ff' : '1px solid #1e293b',
                  background: ledTint === t.id ? 'rgba(0, 240, 255, 0.16)' : '#0f172a',
                  color: ledTint === t.id ? '#f8fafc' : '#94a3b8',
                }}
              >
                <span
                  style={{
                    width: 9,
                    height: 9,
                    borderRadius: '50%',
                    background: t.swatch,
                    display: 'inline-block',
                  }}
                />
                {t.label.replace(/^[^\s]+\s/, '')}
              </button>
            ))}

            {/* Native RGB Color Picker for Custom LED Lamp Color */}
            <label
              title="Choisir une couleur LED RGB sur mesure"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                padding: '2px 6px',
                borderRadius: 5,
                border: ledTint === 'custom_rgb' ? '1px solid #00f0ff' : '1px solid #334155',
                background: '#090d16',
                cursor: 'pointer',
                fontSize: '0.68rem',
                color: '#e2e8f0',
              }}
            >
              <input
                type="color"
                value={customLedHex}
                onChange={(e) => {
                  setCustomLedHex(e.target.value);
                  setLedTint('custom_rgb');
                }}
                style={{ width: 18, height: 18, border: 'none', background: 'transparent', cursor: 'pointer', padding: 0 }}
              />
              <span>{customLedHex.toUpperCase()}</span>
            </label>
          </div>
        </div>

        {/* Viewport Content */}
        <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
          {!sessionId ? (
            <div
              style={{
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#64748b',
                padding: 32,
                textAlign: 'center',
              }}
            >
              <div style={{ fontSize: '3.2rem', marginBottom: 12 }}>💡🌕🏮🎲</div>
              <h2 style={{ color: '#e2e8f0', fontSize: '1.15rem', marginBottom: 8 }}>
                Studio Lithophanies, Globes Planètes & Lightbox LED V2
              </h2>
              <p style={{ maxWidth: 580, fontSize: '0.84rem', lineHeight: 1.6 }}>
                Importez une photo (ou cliquez sur <strong>🌕 Lune 3D</strong>) pour créer des{' '}
                <strong>Lithophanies Plates découpées en Formes & Multi-Tuiles</strong> (Cœur, Nid d’abeille, Étoile, Grille L×H),
                des <strong>Cylindres 360° auto-adaptatifs</strong> avec support lampe Bambu Lab surélevé et passage de fil,
                des <strong>Caissons & Cubes 4-Faces Multi-Images</strong> assemblés en 3D, ou des{' '}
                <strong>Boules / Planètes Lithophanies avec 4 Socles au choix</strong>.
              </p>
              <div style={{ display: 'flex', gap: 10, marginTop: 18 }}>
                <button
                  className="btn-cyber primary"
                  style={{ padding: '10px 18px' }}
                  onClick={() => fileInputRef.current?.click()}
                >
                  📷 Choisir une Photo (.JPG / .PNG)
                </button>
                <button
                  className="btn-cyber secondary"
                  style={{ padding: '10px 18px' }}
                  onClick={() => handleInitPlanetSession('planet_moon')}
                >
                  🌕 Générer une Boule Lune Cratérisée 3D
                </button>
              </div>
            </div>
          ) : viewTab === '2d' ? (
            <div
              style={{
                height: '100%',
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: 18,
                padding: 20,
                background: '#07090e',
                overflowY: 'auto',
              }}
            >
              {/* Left Card: Original Photo / Planet Map */}
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  background: '#0f172a',
                  border: '1px solid #1e293b',
                  borderRadius: 10,
                  overflow: 'hidden',
                }}
              >
                <div
                  style={{
                    padding: '9px 14px',
                    background: '#1e293b',
                    fontSize: '0.76rem',
                    fontWeight: 700,
                    color: '#cbd5e1',
                    display: 'flex',
                    justifyContent: 'space-between',
                  }}
                >
                  <span>1. IMAGE / CARTE TOPOGRAPHIQUE SOURCE</span>
                  <span className="text-cyan">
                    {effectiveWidthMm} × {effectiveHeightMm} mm
                  </span>
                </div>
                <div
                  style={{
                    flex: 1,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    padding: 16,
                    background: '#090d16',
                  }}
                >
                  {sourcePreviewB64 && (
                    <img
                      src={sourcePreviewB64}
                      alt="Source"
                      style={{
                        maxWidth: '100%',
                        maxHeight: '62vh',
                        objectFit: 'contain',
                        borderRadius: 6,
                        transform: flipHorizontal ? 'scaleX(-1)' : 'none',
                      }}
                    />
                  )}
                </div>
              </div>

              {/* Right Card: Simulated Backlit Lithophane */}
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  background: '#0f172a',
                  border: '1px solid #00f0ff44',
                  borderRadius: 10,
                  overflow: 'hidden',
                }}
              >
                <div
                  style={{
                    padding: '9px 14px',
                    background: 'rgba(0, 240, 255, 0.1)',
                    fontSize: '0.76rem',
                    fontWeight: 700,
                    color: '#00f0ff',
                    display: 'flex',
                    justifyContent: 'space-between',
                  }}
                >
                  <span>
                    2. SIMULATION RÉTRO-ÉCLAIRAGE LED ({minThicknessMm}–{maxThicknessMm} mm)
                  </span>
                  <span>{ loading2D ? 'Calcul optique...' : 'Beer-Lambert RGB Actif' }</span>
                </div>
                <div
                  style={{
                    flex: 1,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    padding: 16,
                    background: ledTint === 'plastic_off' ? '#0f172a' : '#040609',
                  }}
                >
                  {backlightPreviewB64 && (
                    <img
                      src={backlightPreviewB64}
                      alt="Simulation Lithophanie"
                      style={{
                        maxWidth: '100%',
                        maxHeight: '62vh',
                        objectFit: 'contain',
                        borderRadius: 6,
                        boxShadow:
                          ledTint === 'plastic_off'
                            ? '0 10px 25px rgba(0,0,0,0.6)'
                            : `0 0 38px ${ledTint === 'custom_rgb' ? customLedHex + '55' : 'rgba(255, 220, 150, 0.25)'}`,
                      }}
                    />
                  )}
                </div>
              </div>
            </div>
          ) : (
            <Viewer3D
              stlUrl={stlPreviewUrl}
              modelStats={meshStats}
              bedSize={activeBedSize}
              showRod={false}
              lithoBacklightConfig={{
                ledTint,
                customColorHex: ledTint === 'custom_rgb' ? customLedHex : null,
                minThicknessMm,
                maxThicknessMm,
                tdMm,
                shapeMode,
                sphereDiameterMm,
                cylinderDiameterMm,
                standVertical: standVerticalForPrint && flatLayoutMode === 'single_original',
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}
