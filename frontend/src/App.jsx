import React, { useState, useMemo, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import Viewer3D from './components/Viewer3D';
import HueForgeStudio from './components/HueForgeStudio';
import LithophaneStudio from './components/LithophaneStudio';
import SpoolManager from './components/SpoolManager';

// Direct connection to local FastAPI engine (CORS enabled) to avoid Vite proxy timeouts on 2M+ triangle meshes
const API_BASE = 'http://127.0.0.1:8000';

const PRINTER_BEDS = {
  k1_max: [300, 300, 300],
  creality_hi: [260, 260, 300],
};

export default function App() {
  const [activeModule, setActiveModule] = useState('home');
  const [initialSetupTab, setInitialSetupTab] = useState('spools');
  const [spoolsRefreshTick, setSpoolsRefreshTick] = useState(0);
  const [printers, setPrinters] = useState([]);
  const [licenseStatus, setLicenseStatus] = useState({
    unlocked_modules: ['hueforge', 'lithophane', 'smartcut', 'puzzles'],
    is_admin_machine: false,
    customer_name: 'Chargement...',
    app_version: '1.2.0',
  });
  const [quickKeyInput, setQuickKeyInput] = useState('');
  const [quickKeyMsg, setQuickKeyMsg] = useState(null);
  const [lockedModalModule, setLockedModalModule] = useState(null);
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [filename, setFilename] = useState('');
  const [modelStats, setModelStats] = useState(null);
  const [stlVersion, setStlVersion] = useState(0);

  // Printer Preset
  const [printerPreset, setPrinterPreset] = useState('k1_max');
  const [maxBuildSize, setMaxBuildSize] = useState(285.0);

  useEffect(() => {
    fetch(`${API_BASE}/api/printers`)
      .then((r) => r.json())
      .then((d) => {
        if (d.printers) setPrinters(d.printers);
      })
      .catch((err) => console.error('Erreur chargement imprimantes:', err));

    fetch(`${API_BASE}/api/license/status`)
      .then((r) => r.json())
      .then((d) => {
        if (d && d.unlocked_modules) setLicenseStatus(d);
      })
      .catch((err) => console.error('Erreur chargement licence:', err));
  }, [spoolsRefreshTick]);

  const isModuleUnlocked = (modId) => {
    if (modId === 'home' || modId === 'setup_spools') return true;
    const unlocked = licenseStatus?.unlocked_modules || [];
    if (modId === 'module_2a_hueforge') return unlocked.includes('hueforge');
    if (modId === 'module_2b_lithophane') return unlocked.includes('lithophane');
    if (modId === 'module_1_cosplay') return unlocked.includes('smartcut');
    if (modId === 'module_puzzles') return unlocked.includes('puzzles');
    return true;
  };

  const handleOpenModule = (targetMod, fallbackMeta = null) => {
    if (!isModuleUnlocked(targetMod)) {
      setLockedModalModule(
        fallbackMeta || {
          id: targetMod,
          title:
            targetMod === 'module_1_cosplay'
              ? '✂️ SmartCut 3D'
              : targetMod === 'module_2a_hueforge'
              ? '🎨 HueForge Studio'
              : targetMod === 'module_2b_lithophane'
              ? '💡 Lumina 3D'
              : '🧩 Puzzle & Cryptex 3D',
          packLabel:
            targetMod === 'module_1_cosplay' || targetMod === 'module_puzzles'
              ? 'Extension +5 €'
              : 'Pack de Base 20 €',
        }
      );
      return;
    }
    setActiveModule(targetMod);
  };

  const handleQuickActivateKey = async (e) => {
    if (e) e.preventDefault();
    const k = quickKeyInput.trim();
    if (!k) return;
    setQuickKeyMsg(null);
    try {
      const res = await fetch(`${API_BASE}/api/license/activate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ license_key: k }),
      });
      const data = await res.json();
      if (!res.ok) {
        setQuickKeyMsg({ type: 'error', text: data.detail || 'Clé invalide' });
      } else {
        setQuickKeyMsg({ type: 'success', text: data.message || 'Clé activée !' });
        setQuickKeyInput('');
        if (data.status) setLicenseStatus(data.status);
        setLockedModalModule(null);
      }
    } catch (err) {
      setQuickKeyMsg({ type: 'error', text: err.message });
    }
  };

  // Cosplay Reinforcement Rod State
  const [showRod, setShowRod] = useState(true);
  const [pointA, setPointA] = useState([0, 0, 15]);
  const [pointB, setPointB] = useState([0, 0, 250]);
  const [rodConfig, setRodConfig] = useState({
    presetKey: 'round_8',
    profileType: 'round',
    width: 8.0,
    thickness: 8.0,
    clearance: 0.30,
    twistAngleDeg: 0.0,
  });
  const [rodReport, setRodReport] = useState(null);

  // Smart Cutter & Connectors State
  const [cutMode, setCutMode] = useState('auto_grid');
  const [connectorType, setConnectorType] = useState('hexagon_peg');
  const [femaleClearance, setFemaleClearance] = useState(0.18);
  const [engraveNumbers, setEngraveNumbers] = useState(true);

  // Mode B (Bounded Cut Figurine) State
  const [boundedOrigin, setBoundedOrigin] = useState([0, 0, 120]);
  const [boundedSize, setBoundedSize] = useState([80, 80, 80]);
  const [boundedType, setBoundedType] = useState('cylinder');

  // Output Cut Result
  const [cutResult, setCutResult] = useState(null);

  const selectedPrinterObj = printers.find((p) => p.id === printerPreset);
  const bedSize = selectedPrinterObj
    ? [selectedPrinterObj.bed_x_mm || 300, selectedPrinterObj.bed_y_mm || 300, selectedPrinterObj.bed_z_mm || 300]
    : PRINTER_BEDS[printerPreset] || [300, 300, 300];

  const handlePrinterChange = (preset) => {
    setPrinterPreset(preset);
    const pr = printers.find((p) => p.id === preset);
    if (pr && pr.bed_z_mm) {
      setMaxBuildSize(Math.max(100, pr.bed_z_mm - 15));
    } else if (preset === 'k1_max') {
      setMaxBuildSize(285.0);
    } else if (preset === 'creality_hi') {
      setMaxBuildSize(245.0);
    }
  };

  // Live preview of horizontal cut planes Z based on model height and maxBuildSize
  const cutPlanesZ = useMemo(() => {
    if (!modelStats) return [];
    const zMin = modelStats.bbox_min[2];
    const zMax = modelStats.bbox_max[2];
    const totalZ = zMax - zMin;
    if (totalZ <= maxBuildSize || maxBuildSize <= 10) return [];
    const numSegments = Math.ceil(totalZ / maxBuildSize);
    const step = totalZ / numSegments;
    const planes = [];
    for (let i = 1; i < numSegments; i++) {
      planes.push(Number((zMin + i * step).toFixed(1)));
    }
    return planes;
  }, [modelStats, maxBuildSize]);

  const applySessionPayload = (data) => {
    setSessionId(data.session_id);
    if (data.filename) setFilename(data.filename);
    setModelStats(data.stats);
    if (data.default_rod) {
      setPointA(data.default_rod.point_a);
      setPointB(data.default_rod.point_b);
    }
    setRodReport(null);
    setCutResult(null);
    setStlVersion((v) => v + 1);
  };

  const parseJsonResponse = async (res, fallbackMsg) => {
    const text = await res.text();
    if (!text) {
      throw new Error(`${fallbackMsg} (Réponse vide du serveur — vérifiez que le backend tourne).`);
    }
    let data;
    try {
      data = JSON.parse(text);
    } catch {
      throw new Error(`${fallbackMsg} : ${text.slice(0, 160)}`);
    }
    if (!res.ok) {
      throw new Error(data.detail || fallbackMsg);
    }
    return data;
  };

  const handleUploadStl = async (file) => {
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch(`${API_BASE}/api/model/upload`, {
        method: 'POST',
        body: formData,
      });
      const data = await parseJsonResponse(res, 'Erreur upload STL');
      applySessionPayload(data);
    } catch (e) {
      alert(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateDemoSword = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/model/demo/generate-demo-sword`, {
        method: 'POST',
      });
      if (!res.ok) throw new Error('Erreur génération épée démo');
      const data = await res.json();
      applySessionPayload(data);
    } catch (e) {
      alert(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleAlignPca = async () => {
    if (!sessionId) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/model/${sessionId}/align-pca`, {
        method: 'POST',
      });
      if (!res.ok) throw new Error('Erreur alignement PCA');
      const data = await res.json();
      applySessionPayload(data);
    } catch (e) {
      alert(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleResetModel = async () => {
    if (!sessionId) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/model/${sessionId}/reset`, {
        method: 'POST',
      });
      if (!res.ok) throw new Error('Erreur reset');
      const data = await res.json();
      applySessionPayload(data);
    } catch (e) {
      alert(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleApplyRodTunnel = async () => {
    if (!sessionId) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/model/${sessionId}/rod-tunnel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          profile_preset: rodConfig.presetKey,
          profile_type: rodConfig.profileType,
          width: rodConfig.width,
          thickness: rodConfig.thickness,
          clearance: rodConfig.clearance,
          point_a: pointA,
          point_b: pointB,
          twist_angle_deg: rodConfig.twistAngleDeg,
        }),
      });
      const data = await parseJsonResponse(res, 'Erreur perçage tige');
      setModelStats(data.stats);
      setRodReport(data.rod_report);
      setStlVersion((v) => v + 1);
    } catch (e) {
      alert(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleExecuteSmartCut = async () => {
    if (!sessionId) return;
    setLoading(true);
    try {
      const payload = {
        mode: cutMode,
        printer_preset: printerPreset,
        max_build_size: maxBuildSize,
        apply_rod_before_cut: showRod && !rodReport,
        rod_config: showRod
          ? {
              profile_preset: rodConfig.presetKey,
              profile_type: rodConfig.profileType,
              width: rodConfig.width,
              thickness: rodConfig.thickness,
              clearance: rodConfig.clearance,
              point_a: pointA,
              point_b: pointB,
              twist_angle_deg: rodConfig.twistAngleDeg,
            }
          : null,
        plane_origin: boundedOrigin,
        plane_normal: [0, 0, 1],
        bound_type: boundedType,
        bound_size: boundedSize,
        connector_type: connectorType,
        female_clearance: femaleClearance,
        draft_angle_deg: 2.0,
        pin_height_half: 10.0,
        base_size_mm: 10.0,
        engrave_numbers: engraveNumbers,
        engrave_depth_mm: 0.8,
      };

      const res = await fetch(`${API_BASE}/api/model/${sessionId}/smart-cut`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await parseJsonResponse(res, 'Erreur découpe');
      setCutResult(data);
      if (data.rod_report) setRodReport(data.rod_report);
      setStlVersion((v) => v + 1);
    } catch (e) {
      alert(e.message);
    } finally {
      setLoading(false);
    }
  };

  const stlUrl = sessionId
    ? `${API_BASE}/api/model/${sessionId}/stl?v=${stlVersion}`
    : null;

  const downloadZipUrl =
    cutResult && sessionId
      ? `${API_BASE}${cutResult.download_zip_url}`
      : null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', width: '100vw', height: '100vh' }}>
      {/* Top Module Navigation Bar */}
      <header className="top-module-bar">
        <div
          className="top-brand"
          style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer' }}
          onClick={() => setActiveModule('home')}
          title="Retourner à l'écran d'accueil StudioForge 3D"
        >
          <img
            src="/studioforge-icon.png"
            alt="StudioForge 3D"
            style={{
              width: '30px',
              height: '30px',
              borderRadius: '7px',
              boxShadow: '0 0 10px rgba(0, 240, 255, 0.35)',
            }}
          />
          <div>
            STUDIO<span>FORGE</span> 3D
          </div>
        </div>
        <div className="top-module-tabs">
          <button
            className={`top-tab-btn ${activeModule === 'home' ? 'active' : ''}`}
            onClick={() => setActiveModule('home')}
          >
            🏠 ACCUEIL
          </button>
          <button
            className={`top-tab-btn ${activeModule === 'module_2a_hueforge' ? 'active' : ''}`}
            onClick={() => handleOpenModule('module_2a_hueforge')}
          >
            🎨 HUEFORGE STUDIO {!isModuleUnlocked('module_2a_hueforge') && '🔒'}
          </button>
          <button
            className={`top-tab-btn ${activeModule === 'module_2b_lithophane' ? 'active' : ''}`}
            onClick={() => handleOpenModule('module_2b_lithophane')}
          >
            💡 LUMINA 3D {!isModuleUnlocked('module_2b_lithophane') && '🔒'}
          </button>
          <button
            className={`top-tab-btn ${activeModule === 'module_1_cosplay' ? 'active' : ''}`}
            onClick={() => handleOpenModule('module_1_cosplay')}
          >
            ✂️ SMARTCUT 3D {!isModuleUnlocked('module_1_cosplay') && '🔒'}
          </button>
          <button
            className={`top-tab-btn ${activeModule === 'setup_spools' ? 'active' : ''}`}
            onClick={() => {
              setInitialSetupTab('spools');
              setActiveModule('setup_spools');
            }}
          >
            ⚙️ ATELIER &amp; LICENCES
          </button>
        </div>
      </header>

      {/* HOME HUB SCREEN */}
      {activeModule === 'home' && (
        <div
          style={{
            height: 'calc(100vh - 48px)',
            overflowY: 'auto',
            padding: '28px 36px',
            background:
              'radial-gradient(circle at 20% 15%, rgba(0, 240, 255, 0.08), transparent 45%), radial-gradient(circle at 80% 80%, rgba(245, 158, 11, 0.08), transparent 45%), #070b14',
          }}
        >
          <div style={{ maxWidth: '1240px', margin: '0 auto' }}>
            {/* HERO BANNER */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: '20px',
                padding: '22px 26px',
                borderRadius: '16px',
                background: 'linear-gradient(135deg, rgba(15, 23, 42, 0.95), rgba(30, 41, 59, 0.88))',
                border: '1px solid rgba(0, 240, 255, 0.28)',
                boxShadow: '0 16px 40px rgba(0, 0, 0, 0.45)',
                marginBottom: '24px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '18px' }}>
                <img
                  src="/studioforge-icon.png"
                  alt="StudioForge 3D Icon"
                  style={{
                    width: '74px',
                    height: '74px',
                    borderRadius: '16px',
                    border: '2px solid rgba(0, 240, 255, 0.5)',
                    boxShadow: '0 0 24px rgba(0, 240, 255, 0.25)',
                  }}
                />
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <h1
                      style={{
                        margin: 0,
                        fontSize: '1.65rem',
                        fontWeight: 900,
                        letterSpacing: '0.04em',
                        color: '#f8fafc',
                      }}
                    >
                      STUDIO<span style={{ color: '#00f0ff' }}>FORGE</span> 3D
                    </h1>
                    <span className="dim-badge" style={{ fontSize: '0.72rem' }}>
                      v{licenseStatus?.app_version || '1.2.0'}
                    </span>
                    {licenseStatus?.is_admin_machine && (
                      <span
                        className="dim-badge"
                        style={{
                          borderColor: '#f59e0b',
                          color: '#fbbf24',
                          background: 'rgba(245, 158, 11, 0.15)',
                          fontSize: '0.7rem',
                        }}
                      >
                        👑 Poste Créateur Maître
                      </span>
                    )}
                  </div>
                  <p style={{ margin: '6px 0 0 0', fontSize: '0.86rem', color: '#94a3b8', maxWidth: '640px' }}>
                    Suite de géométrie computationnelle 3D &amp; optique multi-couleurs CFS. Choisissez un atelier
                    ci-dessous pour démarrer votre création ou gérer vos licences modulaires.
                  </p>
                </div>
              </div>

              {/* License Status & Quick Key Activation */}
              <div
                style={{
                  minWidth: '320px',
                  padding: '12px 14px',
                  borderRadius: '12px',
                  background: 'rgba(7, 11, 20, 0.75)',
                  border: '1px solid rgba(148, 163, 184, 0.22)',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: '6px',
                    fontSize: '0.74rem',
                  }}
                >
                  <span style={{ color: '#cbd5e1', fontWeight: 700 }}>
                    🔑 Licence : <strong className="text-cyan">{licenseStatus?.customer_name || 'Standard'}</strong>
                  </span>
                  <button
                    type="button"
                    className="btn-hud"
                    style={{ fontSize: '0.66rem', padding: '2px 8px' }}
                    onClick={() => {
                      setInitialSetupTab('license');
                      setActiveModule('setup_spools');
                    }}
                  >
                    Gérer / + Clé
                  </button>
                </div>
                <form onSubmit={handleQuickActivateKey} style={{ display: 'flex', gap: '6px' }}>
                  <input
                    type="text"
                    className="cyber-input"
                    placeholder="Activer une clé SF3D-..."
                    value={quickKeyInput}
                    onChange={(e) => setQuickKeyInput(e.target.value)}
                    style={{ fontSize: '0.73rem', padding: '6px 9px', fontFamily: 'monospace' }}
                  />
                  <button
                    type="submit"
                    className="btn-cyber primary"
                    style={{ padding: '6px 12px', fontSize: '0.73rem', flex: 'none' }}
                    disabled={!quickKeyInput.trim()}
                  >
                    Activer
                  </button>
                </form>
                {quickKeyMsg && (
                  <div
                    style={{
                      marginTop: '6px',
                      fontSize: '0.7rem',
                      color: quickKeyMsg.type === 'error' ? '#fca5a5' : '#34d399',
                    }}
                  >
                    {quickKeyMsg.text}
                  </div>
                )}
              </div>
            </div>

            {/* MODULE CARDS GRID */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(350px, 1fr))',
                gap: '18px',
              }}
            >
              {[
                {
                  target: 'module_2a_hueforge',
                  icon: '🎨',
                  name: 'HueForge Studio',
                  badge: 'Pack de Base (20 €)',
                  unlocked: isModuleUnlocked('module_2a_hueforge'),
                  accent: '#00f0ff',
                  desc: "Peinture par couches 3D & Multi-Frame (Hexagones, Cœurs, Boucliers, Triptyques). Moteur Manga HSV & Solveur Optique CIELAB ΔE jusqu'à 8 bobines CFS avec Tour de Couches Interactive et Loupe de Couche.",
                  features: ['Tour de Couches & Loupe 👁️', 'Jusqu’à 8 couleurs CFS (.3MF / .STL)', 'Outpainting IA des bords'],
                },
                {
                  target: 'module_2b_lithophane',
                  icon: '💡',
                  name: 'Lumina 3D',
                  badge: 'Pack de Base (20 €)',
                  unlocked: isModuleUnlocked('module_2b_lithophane'),
                  accent: '#38bdf8',
                  desc: 'Générateur de Lithophanes HD, Caissons Lightbox LED Multi-Couleurs, Lampes Lune / Planètes 360° et Abat-jours sur mesure avec aperçu du rétroéclairage LED en temps réel.',
                  features: ['Lithophanes Courbes, Cœur, Étoile', 'Caisson Lightbox LED & Couvercle', 'Sphères Lune & Planètes 360°'],
                },
                {
                  target: 'module_1_cosplay',
                  icon: '✂️',
                  name: 'SmartCut 3D',
                  badge: 'Extension (+5 €)',
                  unlocked: isModuleUnlocked('module_1_cosplay'),
                  accent: '#f59e0b',
                  desc: 'Découpe intelligente de grandes pièces 3D, armures Cosplay et figurines hors-gabarit. Tunnels de tiges de renfort, tenons hexagonaux anti-rotation et gravure automatique des numéros.',
                  features: ['Découpe Auto-Grille & Locale', 'Tunnels de renfort métalliques', 'Tenons & Mortaises paramétriques'],
                },
                {
                  target: 'module_puzzles',
                  icon: '🧩',
                  name: 'Puzzle & Cryptex 3D',
                  badge: 'Extension (+5 €) • Bientôt',
                  unlocked: isModuleUnlocked('module_puzzles'),
                  comingSoon: true,
                  accent: '#a855f7',
                  desc: 'Générateur de boîtes à secret mécaniques, Cryptex à code personnalisable, labyrinthes 3D et puzzles géométriques emboîtables prêts à imprimer sans support.',
                  features: ['Cryptex à anneaux codés', 'Puzzles 3D à partir de vos images', 'Mécanismes sans support'],
                },
                {
                  target: 'setup_spools',
                  icon: '⚙️',
                  name: 'Atelier & Licences',
                  badge: 'Inclus d’office',
                  unlocked: true,
                  accent: '#10b981',
                  desc: 'Gérez votre stock de bobines CFS (Deeplee, Creality, Sunlu, Bambu...) avec l’Assistant IA, configurez les plateaux X/Y/Z de vos imprimantes 3D et activez vos clés de licence.',
                  features: ['Bibliothèque Bobines & TD Optique', 'Flotte Imprimantes 3D X/Y/Z', 'Activation Clés & Mises à jour'],
                },
              ].map((card) => (
                <div
                  key={card.name}
                  onClick={() => {
                    if (card.comingSoon && card.unlocked) {
                      alert(
                        '🧩 Le module Puzzle & Cryptex 3D est déjà débloqué sur votre licence ! Ses générateurs mécaniques arriveront dans la prochaine mise à jour.'
                      );
                      return;
                    }
                    if (card.target === 'setup_spools') {
                      setInitialSetupTab('spools');
                      setActiveModule('setup_spools');
                    } else {
                      handleOpenModule(card.target, {
                        id: card.target,
                        title: `${card.icon} ${card.name}`,
                        packLabel: card.badge,
                      });
                    }
                  }}
                  style={{
                    padding: '20px 22px',
                    borderRadius: '14px',
                    background: 'linear-gradient(180deg, rgba(15, 23, 42, 0.92), rgba(15, 23, 42, 0.75))',
                    border: `1px solid ${card.unlocked ? 'rgba(0, 240, 255, 0.25)' : 'rgba(239, 68, 68, 0.35)'}`,
                    boxShadow: '0 10px 25px rgba(0, 0, 0, 0.35)',
                    cursor: 'pointer',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                    transition: 'transform 0.15s ease, border-color 0.15s ease',
                  }}
                >
                  <div>
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'flex-start',
                        gap: '10px',
                        marginBottom: '10px',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <span
                          style={{
                            fontSize: '1.65rem',
                            width: '44px',
                            height: '44px',
                            borderRadius: '11px',
                            background: 'rgba(255, 255, 255, 0.05)',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                          }}
                        >
                          {card.icon}
                        </span>
                        <div>
                          <h3 style={{ margin: 0, fontSize: '1.08rem', fontWeight: 800, color: '#f8fafc' }}>
                            {card.name}
                          </h3>
                          <span style={{ fontSize: '0.68rem', color: '#94a3b8' }}>{card.badge}</span>
                        </div>
                      </div>

                      <span
                        style={{
                          fontSize: '0.68rem',
                          fontWeight: 700,
                          padding: '3px 9px',
                          borderRadius: '999px',
                          background: card.unlocked
                            ? 'rgba(16, 185, 129, 0.18)'
                            : 'rgba(239, 68, 68, 0.18)',
                          color: card.unlocked ? '#34d399' : '#fca5a5',
                          border: `1px solid ${
                            card.unlocked ? 'rgba(16, 185, 129, 0.4)' : 'rgba(239, 68, 68, 0.4)'
                          }`,
                        }}
                      >
                        {card.unlocked ? '✅ Actif' : '🔒 Verrouillé'}
                      </span>
                    </div>

                    <p style={{ fontSize: '0.78rem', color: '#cbd5e1', lineHeight: 1.45, margin: '0 0 12px 0' }}>
                      {card.desc}
                    </p>

                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '16px' }}>
                      {card.features.map((f) => (
                        <span
                          key={f}
                          style={{
                            fontSize: '0.66rem',
                            padding: '3px 8px',
                            borderRadius: '6px',
                            background: 'rgba(30, 41, 59, 0.85)',
                            color: '#94a3b8',
                            border: '1px solid rgba(148, 163, 184, 0.18)',
                          }}
                        >
                          • {f}
                        </span>
                      ))}
                    </div>
                  </div>

                  <button
                    type="button"
                    className={`btn-cyber ${card.unlocked ? 'primary-full' : 'secondary'}`}
                    style={{ width: '100%', marginTop: 'auto' }}
                  >
                    {card.unlocked
                      ? card.comingSoon
                        ? '🧩 Pré-activé (Bientôt disponible)'
                        : `🚀 Ouvrir ${card.name}`
                      : `🔓 Débloquer ${card.name} (${card.badge})`}
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* LOCKED MODULE ACTIVATION MODAL */}
      {lockedModalModule && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(3, 7, 18, 0.82)',
            backdropFilter: 'blur(6px)',
            zIndex: 9999,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '20px',
          }}
          onClick={() => setLockedModalModule(null)}
        >
          <div
            style={{
              maxWidth: '480px',
              width: '100%',
              padding: '24px',
              borderRadius: '14px',
              background: '#0f172a',
              border: '1px solid #00f0ff',
              boxShadow: '0 20px 50px rgba(0, 0, 0, 0.7)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ margin: '0 0 8px 0', color: '#f8fafc', fontSize: '1.1rem' }}>
              🔒 Module Verrouillé : {lockedModalModule.title}
            </h3>
            <p style={{ fontSize: '0.8rem', color: '#cbd5e1', lineHeight: 1.45, marginBottom: '14px' }}>
              Ce module fait partie de l&apos;offre <strong>{lockedModalModule.packLabel}</strong>. Entrez votre clé
              d&apos;activation <code>SF3D-...</code> ci-dessous pour le débloquer instantanément sur cet ordinateur :
            </p>
            <form onSubmit={handleQuickActivateKey}>
              <input
                type="text"
                className="cyber-input"
                placeholder="Collez votre clé SF3D-..."
                value={quickKeyInput}
                onChange={(e) => setQuickKeyInput(e.target.value)}
                style={{ fontFamily: 'monospace', marginBottom: '10px' }}
              />
              <div className="btn-row">
                <button type="submit" className="btn-cyber primary" disabled={!quickKeyInput.trim()}>
                  🔓 Débloquer Maintenant
                </button>
                <button
                  type="button"
                  className="btn-cyber secondary"
                  onClick={() => {
                    setLockedModalModule(null);
                    setInitialSetupTab('license');
                    setActiveModule('setup_spools');
                  }}
                >
                  ⚙️ Aller aux Licences
                </button>
                <button
                  type="button"
                  className="btn-hud"
                  onClick={() => setLockedModalModule(null)}
                >
                  Fermer
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Keep HueForgeStudio and LithophaneStudio mounted so switching to Setup Spools or Home never loses active work */}
      <div style={{ display: activeModule === 'module_2a_hueforge' ? 'block' : 'none' }}>
        <HueForgeStudio
          printerPreset={printerPreset}
          onChangePrinterPreset={handlePrinterChange}
          spoolsRefreshTick={spoolsRefreshTick}
          onOpenSpoolSetup={() => {
            setInitialSetupTab('spools');
            setActiveModule('setup_spools');
          }}
          onOpenPrinterSetup={() => {
            setInitialSetupTab('printers');
            setActiveModule('setup_spools');
          }}
        />
      </div>

      <div style={{ display: activeModule === 'module_2b_lithophane' ? 'block' : 'none' }}>
        <LithophaneStudio
          printerPreset={printerPreset}
          onChangePrinterPreset={handlePrinterChange}
          printers={printers}
          spoolsRefreshTick={spoolsRefreshTick}
          onOpenSpoolSetup={() => {
            setInitialSetupTab('spools');
            setActiveModule('setup_spools');
          }}
        />
      </div>

      {activeModule === 'setup_spools' && (
        <SpoolManager
          initialTab={initialSetupTab}
          licenseStatus={licenseStatus}
          onLicenseUpdated={(newStatus) => setLicenseStatus(newStatus)}
          onSpoolsUpdated={() => setSpoolsRefreshTick((t) => t + 1)}
          onPrintersUpdated={() => setSpoolsRefreshTick((t) => t + 1)}
          onCloseModal={() => setActiveModule('home')}
        />
      )}

      {activeModule === 'module_1_cosplay' && (
        <div className="app-layout" style={{ height: 'calc(100vh - 48px)' }}>
          <Sidebar
            loading={loading}
            onUploadStl={handleUploadStl}
            onGenerateDemoSword={handleGenerateDemoSword}
            sessionId={sessionId}
            filename={filename}
            printerPreset={printerPreset}
            onChangePrinterPreset={handlePrinterChange}
            printers={printers}
            onAlignPca={handleAlignPca}
            onResetModel={handleResetModel}
            showRod={showRod}
            setShowRod={setShowRod}
            rodConfig={rodConfig}
            setRodConfig={setRodConfig}
            pointA={pointA}
            pointB={pointB}
            onApplyRodTunnel={handleApplyRodTunnel}
            rodReport={rodReport}
            cutMode={cutMode}
            setCutMode={setCutMode}
            maxBuildSize={maxBuildSize}
            setMaxBuildSize={setMaxBuildSize}
            connectorType={connectorType}
            setConnectorType={setConnectorType}
            femaleClearance={femaleClearance}
            setFemaleClearance={setFemaleClearance}
            engraveNumbers={engraveNumbers}
            setEngraveNumbers={setEngraveNumbers}
            boundedOrigin={boundedOrigin}
            setBoundedOrigin={setBoundedOrigin}
            boundedSize={boundedSize}
            setBoundedSize={setBoundedSize}
            boundedType={boundedType}
            setBoundedType={setBoundedType}
            onExecuteSmartCut={handleExecuteSmartCut}
            cutResult={cutResult}
            downloadZipUrl={downloadZipUrl}
          />

          <Viewer3D
            stlUrl={stlUrl}
            modelStats={modelStats}
            bedSize={bedSize}
            showRod={showRod && Boolean(sessionId)}
            pointA={pointA}
            pointB={pointB}
            onChangePointA={setPointA}
            onChangePointB={setPointB}
            rodConfig={rodConfig}
            cutMode={cutMode}
            cutPlanesZ={cutPlanesZ}
            boundedOrigin={boundedOrigin}
            boundedSize={boundedSize}
            boundedType={boundedType}
          />
        </div>
      )}
    </div>
  );
}

