import React, { useState, useEffect } from 'react';

const API_BASE = 'http://127.0.0.1:8000';

function FieldInfo({ title, children }) {
  return (
    <span className="info-badge-wrap">
      <span className="info-badge-icon" tabIndex={0} aria-label={title}>
        i
      </span>
      <span className="info-tooltip-popup" role="tooltip">
        {title && <span className="info-tooltip-title">{title}</span>}
        {children}
      </span>
    </span>
  );
}

export default function SpoolManager({
  onSpoolsUpdated,
  onPrintersUpdated,
  initialTab = 'spools',
  onCloseModal = null,
  licenseStatus = null,
  onLicenseUpdated = null,
}) {
  const [setupTab, setSetupTab] = useState(initialTab); // 'spools' | 'printers' | 'license'
  const [spools, setSpools] = useState([]);
  const [printers, setPrinters] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [stockFilter, setStockFilter] = useState('all'); // 'all' | 'in_stock' | 'favorites'
  const [aiPrompt, setAiPrompt] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [editingId, setEditingId] = useState(null);

  // Licensing & Updates State
  const [localLicense, setLocalLicense] = useState(licenseStatus);
  const [licenseKeyInput, setLicenseKeyInput] = useState('');
  const [licenseMsg, setLicenseMsg] = useState(null);
  const [updateInfo, setUpdateInfo] = useState(null);
  const [checkingUpdate, setCheckingUpdate] = useState(false);

  // Admin Key Generator State (only active if localLicense?.is_admin_machine === true)
  const [adminCustomerName, setAdminCustomerName] = useState('Ma Fille - PC Maison');
  const [adminPresetPack, setAdminPresetPack] = useState('base_20');
  const [adminModules, setAdminModules] = useState(['hueforge', 'lithophane']);
  const [generatedKeyData, setGeneratedKeyData] = useState(null);
  const [copiedKey, setCopiedKey] = useState(false);

  // Printer Fleet Form State
  const [printerAiPrompt, setPrinterAiPrompt] = useState('');
  const [printerAiLoading, setPrinterAiLoading] = useState(false);
  const [editingPrinterId, setEditingPrinterId] = useState(null);
  const [printerName, setPrinterName] = useState('');
  const [printerBrand, setPrinterBrand] = useState('Creality');
  const [bedXMm, setBedXMm] = useState(260);
  const [bedYMm, setBedYMm] = useState(260);
  const [bedZMm, setBedZMm] = useState(300);
  const [maxColors, setMaxColors] = useState(8);
  const [useCosplay, setUseCosplay] = useState(true);
  const [useHueforge, setUseHueforge] = useState(true);
  const [useLithophane, setUseLithophane] = useState(true);
  const [printerNotes, setPrinterNotes] = useState('');

  useEffect(() => {
    if (initialTab) setSetupTab(initialTab);
  }, [initialTab]);

  useEffect(() => {
    if (licenseStatus) setLocalLicense(licenseStatus);
  }, [licenseStatus]);

  const fetchLicenseStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/license/status`);
      const data = await res.json();
      if (res.ok) {
        setLocalLicense(data);
        if (onLicenseUpdated) onLicenseUpdated(data);
      }
    } catch (e) {
      console.error('Erreur chargement licence:', e);
    }
  };

  const handleActivateLicenseKey = async (e) => {
    if (e) e.preventDefault();
    const k = licenseKeyInput.trim();
    if (!k) return;
    setLicenseMsg(null);
    try {
      const res = await fetch(`${API_BASE}/api/license/activate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ license_key: k }),
      });
      const data = await res.json();
      if (!res.ok) {
        setLicenseMsg({ type: 'error', text: data.detail || 'Clé invalide' });
      } else {
        setLicenseMsg({ type: 'success', text: data.message || 'Clé activée avec succès !' });
        setLicenseKeyInput('');
        setLocalLicense(data.status);
        if (onLicenseUpdated) onLicenseUpdated(data.status);
      }
    } catch (err) {
      setLicenseMsg({ type: 'error', text: err.message });
    }
  };

  const handleResetLicenses = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/license/deactivate-all`, { method: 'POST' });
      const data = await res.json();
      if (res.ok && data.status) {
        setLocalLicense(data.status);
        if (onLicenseUpdated) onLicenseUpdated(data.status);
        setLicenseMsg({ type: 'info', text: 'Licences réinitialisées sur ce poste.' });
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleCheckUpdates = async () => {
    setCheckingUpdate(true);
    try {
      const res = await fetch(`${API_BASE}/api/license/updates/check`);
      const data = await res.json();
      if (res.ok) setUpdateInfo(data);
    } catch (err) {
      console.error(err);
    } finally {
      setCheckingUpdate(false);
    }
  };

  const handleAdminGenerateKey = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/license/admin/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          customer_name: adminCustomerName.trim() || 'Client StudioForge 3D',
          preset_pack: adminPresetPack,
          modules: adminModules,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        setGeneratedKeyData(data);
        setCopiedKey(false);
      } else {
        alert(data.detail || 'Erreur génération clé');
      }
    } catch (err) {
      alert(err.message);
    }
  };

  const handleAdminSimulateView = async (presetName) => {
    const presets = {
      none: [],
      base_20: ['hueforge', 'lithophane'],
      base_plus_cut: ['hueforge', 'lithophane', 'smartcut'],
      full_creator: ['hueforge', 'lithophane', 'smartcut', 'puzzles', 'wirepress'],
    };
    const mods = presets[presetName] || [];
    try {
      const res = await fetch(`${API_BASE}/api/license/admin/simulate-view`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          modules: mods,
          customer_name:
            presetName === 'none'
              ? ''
              : presetName === 'base_20'
              ? 'Client Pack Base (20 €)'
              : presetName === 'base_plus_cut'
              ? 'Client Pack Base + SmartCut (25 €)'
              : 'Créateur StudioForge 3D (Intégral)',
        }),
      });
      const data = await res.json();
      if (res.ok && data.status) {
        setLocalLicense(data.status);
        if (onLicenseUpdated) onLicenseUpdated(data.status);
      }
    } catch (err) {
      console.error(err);
    }
  };

  // Spool Form State (Core + Optical + TDS Technical Parameters)
  const [brand, setBrand] = useState('Deeplee');
  const [material, setMaterial] = useState('PLA+');
  const [colorName, setColorName] = useState('Blanc Pur');
  const [hexColor, setHexColor] = useState('#ffffff');
  const [surfaceFinish, setSurfaceFinish] = useState('Standard');
  const [tdMm, setTdMm] = useState(2.8);
  const [nozzleTemp, setNozzleTemp] = useState(210);
  const [bedTemp, setBedTemp] = useState(60);
  const [flowRatio, setFlowRatio] = useState(0.96);
  const [maxVolumetricFlow, setMaxVolumetricFlow] = useState(12.0);
  const [dryingTempC, setDryingTempC] = useState(48);
  const [dryingHours, setDryingHours] = useState(6);
  const [hdtC, setHdtC] = useState(52);
  const [tensileZMpa, setTensileZMpa] = useState(23.8);
  const [referenceSku, setReferenceSku] = useState('DEEPLEE-PLAP-WHITE');
  const [notes, setNotes] = useState('');
  const [isFavorite, setIsFavorite] = useState(true);
  const [inStock, setInStock] = useState(true);

  const fetchSpools = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/spools`);
      const data = await res.json();
      if (res.ok && data.spools) {
        setSpools(data.spools);
        if (onSpoolsUpdated) onSpoolsUpdated(data.spools);
      }
    } catch (e) {
      console.error('Erreur chargement bobines:', e);
    }
  };

  const fetchPrinters = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/printers`);
      const data = await res.json();
      if (res.ok && data.printers) {
        setPrinters(data.printers);
        if (onPrintersUpdated) onPrintersUpdated(data.printers);
      }
    } catch (e) {
      console.error('Erreur chargement imprimantes:', e);
    }
  };

  useEffect(() => {
    fetchSpools();
    fetchPrinters();
    fetchLicenseStatus();
  }, []);

  const applyPrinterSuggestionToForm = (s) => {
    setPrinterName(s.name || 'Imprimante 3D');
    setPrinterBrand(s.brand || 'Creality');
    setBedXMm(Number(s.bed_x_mm ?? 250));
    setBedYMm(Number(s.bed_y_mm ?? 250));
    setBedZMm(Number(s.bed_z_mm ?? 250));
    setMaxColors(Number(s.max_colors ?? 1));
    setUseCosplay(s.use_cosplay !== false);
    setUseHueforge(Boolean(s.use_hueforge));
    setUseLithophane(s.use_lithophane !== false);
    setPrinterNotes(s.notes || '');
  };

  const handlePrinterAiSuggest = async (quickAdd = false) => {
    const q = printerAiPrompt.trim();
    if (!q) return;
    setPrinterAiLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/printers/ai-suggest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: q }),
      });
      const data = await res.json();
      if (res.ok && data.suggestion) {
        applyPrinterSuggestionToForm(data.suggestion);
        if (quickAdd && data.suggestion.recognized) {
          const resSave = await fetch(`${API_BASE}/api/printers`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data.suggestion),
          });
          const dataSave = await resSave.json();
          if (resSave.ok && dataSave.printers) {
            setPrinters(dataSave.printers);
            if (onPrintersUpdated) onPrintersUpdated(dataSave.printers);
            setPrinterAiPrompt('');
          }
        }
      }
    } catch (e) {
      alert('Erreur IA Imprimante : ' + e.message);
    } finally {
      setPrinterAiLoading(false);
    }
  };

  const handleSavePrinter = async (e) => {
    e.preventDefault();
    const payload = {
      name: printerName.trim() || 'Imprimante 3D',
      brand: printerBrand.trim() || 'Générique',
      bed_x_mm: Number(bedXMm) || 250,
      bed_y_mm: Number(bedYMm) || 250,
      bed_z_mm: Number(bedZMm) || 250,
      max_colors: Number(maxColors) || 1,
      use_cosplay: Boolean(useCosplay),
      use_hueforge: Boolean(useHueforge),
      use_lithophane: Boolean(useLithophane),
      notes: printerNotes,
    };
    try {
      const url = editingPrinterId
        ? `${API_BASE}/api/printers/${editingPrinterId}`
        : `${API_BASE}/api/printers`;
      const method = editingPrinterId ? 'PUT' : 'POST';
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (res.ok && data.printers) {
        setPrinters(data.printers);
        if (onPrintersUpdated) onPrintersUpdated(data.printers);
        setEditingPrinterId(null);
      }
    } catch (err) {
      alert('Erreur sauvegarde imprimante: ' + err.message);
    }
  };

  const handleEditPrinterClick = (pr) => {
    setEditingPrinterId(pr.id);
    setPrinterName(pr.name);
    setPrinterBrand(pr.brand || 'Creality');
    setBedXMm(pr.bed_x_mm);
    setBedYMm(pr.bed_y_mm);
    setBedZMm(pr.bed_z_mm);
    setMaxColors(pr.max_colors || 1);
    setUseCosplay(pr.use_cosplay !== false);
    setUseHueforge(pr.use_hueforge !== false);
    setUseLithophane(pr.use_lithophane !== false);
    setPrinterNotes(pr.notes || '');
  };

  const handleTogglePrinterModule = async (printerId, modKey) => {
    try {
      const res = await fetch(`${API_BASE}/api/printers/${printerId}/toggle-module/${modKey}`, {
        method: 'POST',
      });
      const data = await res.json();
      if (res.ok && data.printers) {
        setPrinters(data.printers);
        if (onPrintersUpdated) onPrintersUpdated(data.printers);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleDeletePrinter = async (printerId) => {
    try {
      const res = await fetch(`${API_BASE}/api/printers/${printerId}`, {
        method: 'DELETE',
      });
      const data = await res.json();
      if (res.ok && data.printers) {
        setPrinters(data.printers);
        if (onPrintersUpdated) onPrintersUpdated(data.printers);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const applySuggestionToForm = (s) => {
    setBrand(s.brand || 'Générique');
    setMaterial(s.material || 'PLA+');
    setColorName(s.color_name || 'Couleur');
    setHexColor(s.hex_color || '#3b82f6');
    setSurfaceFinish(s.surface_finish || 'Standard');
    setTdMm(Number(s.td_mm ?? 2.0));
    setNozzleTemp(Number(s.nozzle_temp_c ?? 210));
    setBedTemp(Number(s.bed_temp_c ?? 60));
    setFlowRatio(Number(s.flow_ratio ?? 0.96));
    setMaxVolumetricFlow(Number(s.max_volumetric_flow ?? 12.0));
    setDryingTempC(Number(s.drying_temp_c ?? 48));
    setDryingHours(Number(s.drying_hours ?? 6));
    setHdtC(Number(s.hdt_c ?? 52));
    setTensileZMpa(Number(s.tensile_z_mpa ?? 23.8));
    setReferenceSku(s.reference_sku || '');
    setNotes(s.notes || '');
    setIsFavorite(s.is_favorite ?? true);
    setInStock(s.in_stock ?? true);
  };

  const handleAiAssist = async (customText = null) => {
    const queryText = (customText ?? aiPrompt).trim();
    if (!queryText) return;
    setAiLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/spools/ai-assist`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: queryText }),
      });
      const data = await res.json();
      if (res.ok && data.suggestion) {
        applySuggestionToForm(data.suggestion);
      }
    } catch (e) {
      alert("Erreur de l'assistant IA : " + e.message);
    } finally {
      setAiLoading(false);
    }
  };

  const handleAiQuickAdd = async () => {
    const queryText = aiPrompt.trim();
    if (!queryText) return;
    setAiLoading(true);
    try {
      const resAi = await fetch(`${API_BASE}/api/spools/ai-assist`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: queryText }),
      });
      const dataAi = await resAi.json();
      if (!resAi.ok || !dataAi.suggestion) throw new Error('Suggestion IA invalide');

      applySuggestionToForm(dataAi.suggestion);

      const resSave = await fetch(`${API_BASE}/api/spools`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(dataAi.suggestion),
      });
      const dataSave = await resSave.json();
      if (resSave.ok && dataSave.spools) {
        setSpools(dataSave.spools);
        if (onSpoolsUpdated) onSpoolsUpdated(dataSave.spools);
        setAiPrompt('');
      }
    } catch (e) {
      alert(e.message);
    } finally {
      setAiLoading(false);
    }
  };

  const handleSaveSpool = async (e) => {
    e.preventDefault();
    const payload = {
      brand,
      material,
      color_name: colorName,
      hex_color: hexColor,
      surface_finish: surfaceFinish,
      td_mm: Number(tdMm),
      nozzle_temp_c: Number(nozzleTemp),
      bed_temp_c: Number(bedTemp),
      flow_ratio: Number(flowRatio),
      max_volumetric_flow: Number(maxVolumetricFlow),
      drying_temp_c: Number(dryingTempC),
      drying_hours: Number(dryingHours),
      hdt_c: Number(hdtC),
      tensile_z_mpa: Number(tensileZMpa),
      reference_sku: referenceSku,
      notes,
      is_favorite: isFavorite,
      in_stock: inStock,
    };

    try {
      const url = editingId ? `${API_BASE}/api/spools/${editingId}` : `${API_BASE}/api/spools`;
      const method = editingId ? 'PUT' : 'POST';
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (res.ok && data.spools) {
        setSpools(data.spools);
        if (onSpoolsUpdated) onSpoolsUpdated(data.spools);
        setEditingId(null);
      }
    } catch (err) {
      alert('Erreur sauvegarde bobine: ' + err.message);
    }
  };

  const handleEditClick = (sp) => {
    setEditingId(sp.id);
    setBrand(sp.brand);
    setMaterial(sp.material);
    setColorName(sp.color_name);
    setHexColor(sp.hex_color);
    setSurfaceFinish(sp.surface_finish || 'Standard');
    setTdMm(sp.td_mm);
    setNozzleTemp(sp.nozzle_temp_c || 210);
    setBedTemp(sp.bed_temp_c || 60);
    setFlowRatio(sp.flow_ratio ?? 0.96);
    setMaxVolumetricFlow(sp.max_volumetric_flow ?? 12.0);
    setDryingTempC(sp.drying_temp_c ?? 48);
    setDryingHours(sp.drying_hours ?? 6);
    setHdtC(sp.hdt_c ?? 52);
    setTensileZMpa(sp.tensile_z_mpa ?? 23.8);
    setReferenceSku(sp.reference_sku || '');
    setNotes(sp.notes || '');
    setIsFavorite(Boolean(sp.is_favorite));
    setInStock(sp.in_stock !== false);
  };

  const handleToggleFavorite = async (spoolId) => {
    try {
      const res = await fetch(`${API_BASE}/api/spools/${spoolId}/toggle-favorite`, {
        method: 'POST',
      });
      const data = await res.json();
      if (res.ok && data.spools) {
        setSpools(data.spools);
        if (onSpoolsUpdated) onSpoolsUpdated(data.spools);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleToggleStock = async (spoolId) => {
    try {
      const res = await fetch(`${API_BASE}/api/spools/${spoolId}/toggle-stock`, {
        method: 'POST',
      });
      const data = await res.json();
      if (res.ok && data.spools) {
        setSpools(data.spools);
        if (onSpoolsUpdated) onSpoolsUpdated(data.spools);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleDeleteSpool = async (spoolId) => {
    try {
      const res = await fetch(`${API_BASE}/api/spools/${spoolId}`, {
        method: 'DELETE',
      });
      const data = await res.json();
      if (res.ok && data.spools) {
        setSpools(data.spools);
        if (onSpoolsUpdated) onSpoolsUpdated(data.spools);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleMoveSpool = async (spoolId, direction) => {
    try {
      const res = await fetch(`${API_BASE}/api/spools/${spoolId}/move/${direction}`, {
        method: 'POST',
      });
      const data = await res.json();
      if (res.ok && data.spools) {
        setSpools(data.spools);
        if (onSpoolsUpdated) onSpoolsUpdated(data.spools);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleSortSpools = async (sortBy) => {
    try {
      const res = await fetch(`${API_BASE}/api/spools/sort/${sortBy}`, {
        method: 'POST',
      });
      const data = await res.json();
      if (res.ok && data.spools) {
        setSpools(data.spools);
        if (onSpoolsUpdated) onSpoolsUpdated(data.spools);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const filteredSpools = spools.filter((s) => {
    if (stockFilter === 'in_stock' && s.in_stock === false) return false;
    if (stockFilter === 'favorites' && !s.is_favorite) return false;
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      (s.brand || '').toLowerCase().includes(q) ||
      (s.material || '').toLowerCase().includes(q) ||
      (s.color_name || '').toLowerCase().includes(q) ||
      (s.reference_sku || '').toLowerCase().includes(q) ||
      (s.hex_color || '').toLowerCase().includes(q)
    );
  });

  const favoritesCount = spools.filter((s) => s.is_favorite).length;
  const inStockCount = spools.filter((s) => s.in_stock !== false).length;

  return (
    <div className="spool-manager-container">
      <div className="spool-manager-inner">
        {/* HEADER */}
        <div className="spool-header-bar">
          <div>
            <h2 className="spool-main-title">
              ⚙️ ATELIER &amp; LICENCES : BOBINES CFS, IMPRIMANTES 3D &amp; MODULES
            </h2>
            <p className="spool-subtitle">
              Gérez votre stock de bobines CFS, vos imprimantes 3D, vos clés de licence modulaires et les mises à jour StudioForge 3D.
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
            <div className="mode-tabs" style={{ minWidth: '580px' }}>
              <button
                type="button"
                className={`tab-btn ${setupTab === 'spools' ? 'active' : ''}`}
                onClick={() => setSetupTab('spools')}
              >
                🎨 Stock de Bobines ({spools.length})
              </button>
              <button
                type="button"
                className={`tab-btn ${setupTab === 'printers' ? 'active' : ''}`}
                onClick={() => setSetupTab('printers')}
              >
                🖨️ Imprimantes 3D ({printers.length})
              </button>
              <button
                type="button"
                className={`tab-btn ${setupTab === 'license' ? 'active' : ''}`}
                onClick={() => setSetupTab('license')}
              >
                🔑 Licence &amp; Mises à jour
              </button>
            </div>
            {onCloseModal && (
              <button type="button" className="btn-cyber secondary" style={{ flex: 'none' }} onClick={onCloseModal}>
                ✕ Retour au Studio
              </button>
            )}
          </div>
        </div>

        {setupTab === 'license' ? (
          <div className="spool-grid-layout">
            {/* LEFT COLUMN: CLIENT LICENSE ACTIVATION & UPDATES */}
            <div className="spool-left-col">
              <section className="panel-card" style={{ borderColor: '#00f0ff' }}>
                <div className="panel-header-flex">
                  <div className="panel-title">🔑 ACTIVATION DE LICENCE &amp; MODULES ADDITIFS</div>
                  <span className="dim-badge" style={{ color: '#00f0ff' }}>
                    {localLicense?.unlocked_modules?.length || 0} / 5 modules actifs
                  </span>
                </div>
                <p style={{ fontSize: '0.76rem', color: '#94a3b8', marginBottom: '10px' }}>
                  Entrez une clé de licence <strong>StudioForge 3D</strong> (<code>SF3D-...</code>) pour débloquer votre
                  pack de base ou ajouter un module supplémentaire (chaque nouvelle clé s&apos;additionne aux modules déjà
                  activés sur ce PC).
                </p>

                <form onSubmit={handleActivateLicenseKey}>
                  <input
                    type="text"
                    className="cyber-input"
                    placeholder="Collez votre clé ici : SF3D-BASE20-..."
                    value={licenseKeyInput}
                    onChange={(e) => setLicenseKeyInput(e.target.value)}
                    style={{ fontFamily: 'monospace', fontSize: '0.78rem', letterSpacing: '0.03em' }}
                  />
                  <div className="btn-row" style={{ marginTop: '8px' }}>
                    <button
                      type="submit"
                      className="btn-cyber primary-full"
                      disabled={!licenseKeyInput.trim()}
                    >
                      🔓 Activer la Clé &amp; Débloquer les Modules
                    </button>
                  </div>
                </form>

                {licenseMsg && (
                  <div
                    className="file-pill"
                    style={{
                      marginTop: '10px',
                      borderColor:
                        licenseMsg.type === 'error'
                          ? '#ef4444'
                          : licenseMsg.type === 'success'
                          ? '#10b981'
                          : '#00f0ff',
                      color:
                        licenseMsg.type === 'error'
                          ? '#fca5a5'
                          : licenseMsg.type === 'success'
                          ? '#6ee7b7'
                          : '#e2e8f0',
                    }}
                  >
                    {licenseMsg.text}
                  </div>
                )}

                <div style={{ marginTop: '14px' }}>
                  <div className="field-label" style={{ marginBottom: '6px' }}>
                    État des Modules sur cet ordinateur ({localLicense?.customer_name || 'Poste Local'}) :
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                    {(localLicense?.catalog || []).map((mod) => (
                      <div
                        key={mod.id}
                        style={{
                          padding: '9px 11px',
                          borderRadius: '8px',
                          background: mod.unlocked
                            ? 'rgba(16, 185, 129, 0.10)'
                            : 'rgba(15, 23, 42, 0.75)',
                          border: `1px solid ${
                            mod.unlocked ? 'rgba(16, 185, 129, 0.45)' : 'rgba(148, 163, 184, 0.22)'
                          }`,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: '8px',
                        }}
                      >
                        <div>
                          <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#f8fafc' }}>
                            {mod.icon} {mod.name}
                          </div>
                          <div style={{ fontSize: '0.67rem', color: '#94a3b8' }}>{mod.pack_label}</div>
                        </div>
                        <span
                          style={{
                            fontSize: '0.66rem',
                            fontWeight: 700,
                            padding: '2px 7px',
                            borderRadius: '999px',
                            background: mod.unlocked
                              ? 'rgba(16, 185, 129, 0.22)'
                              : 'rgba(239, 68, 68, 0.18)',
                            color: mod.unlocked ? '#34d399' : '#fca5a5',
                          }}
                        >
                          {mod.unlocked ? '✅ Actif' : `🔒 +${mod.price_eur} €`}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </section>

              {/* VERSION & GITHUB UPDATES CARD */}
              <section className="panel-card">
                <div className="panel-header-flex">
                  <div className="panel-title">🔄 VERSION &amp; MISES À JOUR (GITHUB RELEASE)</div>
                  <span className="dim-badge">v{localLicense?.app_version || '1.2.0'}</span>
                </div>
                <p style={{ fontSize: '0.75rem', color: '#94a3b8', marginBottom: '10px' }}>
                  Les mises à jour téléchargent les nouvelles bobines pré-calibrées, les optimisations de performance
                  et les nouveaux outils tout en conservant votre licence et votre stock de bobines personnel.
                </p>
                <button
                  type="button"
                  className="btn-cyber secondary"
                  style={{ width: '100%' }}
                  disabled={checkingUpdate}
                  onClick={handleCheckUpdates}
                >
                  {checkingUpdate
                    ? '⏳ Vérification auprès de GitHub...'
                    : '🔄 Vérifier les mises à jour disponibles'}
                </button>
                {updateInfo && (
                  <div
                    className="file-pill"
                    style={{ marginTop: '10px', borderColor: 'rgba(16, 185, 129, 0.45)' }}
                  >
                    <div style={{ fontWeight: 700, color: '#34d399', marginBottom: '4px' }}>
                      ✅ Version {updateInfo.current_version} ({updateInfo.release_channel}) — À jour
                    </div>
                    <ul style={{ margin: '4px 0 0 16px', padding: 0, fontSize: '0.71rem', color: '#cbd5e1' }}>
                      {(updateInfo.changelog || []).map((line, i) => (
                        <li key={i}>{line}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </section>
            </div>

            {/* RIGHT COLUMN: STRICTLY ADMIN-ONLY KEYGEN OR CLIENT SUMMARY */}
            <div className="spool-right-col">
              {localLicense?.is_admin_machine ? (
                <section
                  className="panel-card"
                  style={{
                    borderColor: '#f59e0b',
                    background: 'linear-gradient(180deg, rgba(245, 158, 11, 0.07), rgba(15, 23, 42, 0.92))',
                  }}
                >
                  <div className="panel-header-flex">
                    <div className="panel-title" style={{ color: '#fbbf24' }}>
                      🔐 CONSOLE CRÉATEUR : GÉNÉRATEUR DE CLÉS RSA (VISIBLE UNIQUEMENT SUR VOTRE PC)
                    </div>
                    <span
                      className="dim-badge"
                      style={{
                        borderColor: '#f59e0b',
                        color: '#fbbf24',
                        background: 'rgba(245, 158, 11, 0.15)',
                      }}
                    >
                      Clé Privée Locale Détectée
                    </span>
                  </div>

                  <div
                    style={{
                      padding: '8px 10px',
                      borderRadius: '7px',
                      background: 'rgba(245, 158, 11, 0.12)',
                      border: '1px solid rgba(245, 158, 11, 0.35)',
                      fontSize: '0.72rem',
                      color: '#fde68a',
                      marginBottom: '12px',
                    }}
                  >
                    🛡️ <strong>Sécurité GitHub garantie :</strong> Ce panneau n&apos;apparaît que parce que le fichier
                    secret <code>backend/data/.admin_private_key.json</code> est présent sur votre PC maître. Il est
                    exclu par <code>.gitignore</code> : vos clients et votre fille qui téléchargent l&apos;application
                    depuis GitHub ne verront <strong>jamais</strong> ce générateur et ne pourront pas créer de clés.
                  </div>

                  <label className="field-label">Nom du Client / Destinataire (ex: Ma Fille, Client #01) :</label>
                  <input
                    type="text"
                    className="cyber-input"
                    value={adminCustomerName}
                    onChange={(e) => setAdminCustomerName(e.target.value)}
                    placeholder="Ex: Ma Fille - PC Maison"
                  />

                  <label className="field-label" style={{ marginTop: '10px' }}>
                    Choisir le Pack ou l&apos;Extension à signer cryptographiquement :
                  </label>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px', marginBottom: '10px' }}>
                    {[
                      {
                        id: 'pack_fille_3',
                        label: '💝 Pack Fille / Créatif (3 Modules)',
                        sub: 'HueForge Studio + Lumina 3D + WirePress 3D',
                        mods: ['hueforge', 'lithophane', 'wirepress'],
                      },
                      {
                        id: 'base_20',
                        label: '📦 Pack Base (20 €)',
                        sub: 'HueForge Studio + Lumina 3D',
                        mods: ['hueforge', 'lithophane'],
                      },
                      {
                        id: 'addon_wirepress_5',
                        label: '👕 Extension WirePress (+5 €)',
                        sub: 'Ajoute WirePress 3D (Textile)',
                        mods: ['wirepress'],
                      },
                      {
                        id: 'addon_makerlab_5',
                        label: '🛠️ Extension MakerLab 3D (+5 €)',
                        sub: 'Ajoute les 8 Outils MakerLab 3D',
                        mods: ['makerlab'],
                      },
                      {
                        id: 'addon_smartcut_5',
                        label: '✂️ Extension SmartCut (+5 €)',
                        sub: 'Ajoute SmartCut 3D à une licence',
                        mods: ['smartcut'],
                      },
                      {
                        id: 'full_pack',
                        label: '👑 Pack Intégral (Tous Modules)',
                        sub: 'HueForge + Lumina + WirePress + MakerLab + SmartCut',
                        mods: ['hueforge', 'lithophane', 'wirepress', 'makerlab', 'smartcut', 'puzzles'],
                      },
                    ].map((pk) => {
                      const active = adminPresetPack === pk.id;
                      return (
                        <button
                          key={pk.id}
                          type="button"
                          className={`btn-hud ${active ? 'active' : ''}`}
                          style={{
                            textAlign: 'left',
                            padding: '8px 10px',
                            borderColor: active ? '#fbbf24' : undefined,
                          }}
                          onClick={() => {
                            setAdminPresetPack(pk.id);
                            setAdminModules(pk.mods);
                          }}
                        >
                          <div style={{ fontWeight: 700, fontSize: '0.74rem', color: '#f8fafc' }}>
                            {pk.label}
                          </div>
                          <div style={{ fontSize: '0.65rem', color: '#94a3b8', marginTop: '2px' }}>
                            {pk.sub}
                          </div>
                        </button>
                      );
                    })}
                  </div>

                  <button
                    type="button"
                    className="btn-cyber primary-full"
                    style={{
                      background: 'linear-gradient(135deg, #f59e0b, #d97706)',
                      color: '#0f172a',
                      fontWeight: 800,
                    }}
                    onClick={handleAdminGenerateKey}
                  >
                    🔑 Générer &amp; Signer la Clé de Licence RSA
                  </button>

                  {generatedKeyData && (
                    <div
                      style={{
                        marginTop: '12px',
                        padding: '10px 12px',
                        borderRadius: '8px',
                        background: 'rgba(15, 23, 42, 0.95)',
                        border: '1px solid #fbbf24',
                      }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          marginBottom: '6px',
                        }}
                      >
                        <span style={{ fontSize: '0.72rem', fontWeight: 700, color: '#fbbf24' }}>
                          Clé générée pour : {generatedKeyData.customer_name} (
                          {generatedKeyData.modules.join(' + ')})
                        </span>
                        <button
                          type="button"
                          className="btn-hud active"
                          style={{ fontSize: '0.66rem', padding: '3px 8px' }}
                          onClick={() => {
                            navigator.clipboard.writeText(generatedKeyData.license_key);
                            setCopiedKey(true);
                          }}
                        >
                          {copiedKey ? '✅ Copiée !' : '📋 Copier la Clé'}
                        </button>
                      </div>
                      <code
                        style={{
                          display: 'block',
                          wordBreak: 'break-all',
                          fontSize: '0.73rem',
                          color: '#34d399',
                          background: 'rgba(0,0,0,0.45)',
                          padding: '8px',
                          borderRadius: '6px',
                          userSelect: 'all',
                        }}
                      >
                        {generatedKeyData.license_key}
                      </code>
                    </div>
                  )}

                  {/* LIVE CLIENT SIMULATOR */}
                  <div
                    style={{
                      marginTop: '16px',
                      paddingTop: '12px',
                      borderTop: '1px solid rgba(245, 158, 11, 0.25)',
                    }}
                  >
                    <div className="field-label" style={{ color: '#fbbf24', marginBottom: '6px' }}>
                      👁️ Simulateur d&apos;Expérience Client (Tester le verrouillage en 1 clic sur votre écran) :
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '6px' }}>
                      <button
                        type="button"
                        className="btn-hud"
                        onClick={() => handleAdminSimulateView('none')}
                      >
                        🔒 Simuler : Aucun module (Poste vierge)
                      </button>
                      <button
                        type="button"
                        className="btn-hud"
                        onClick={() => handleAdminSimulateView('base_20')}
                      >
                        🎨 Simuler : Pack Base 20 € (HueForge + Lumina)
                      </button>
                      <button
                        type="button"
                        className="btn-hud"
                        onClick={() => handleAdminSimulateView('base_plus_cut')}
                      >
                        ✂️ Simuler : Pack 20 € + SmartCut (25 €)
                      </button>
                      <button
                        type="button"
                        className="btn-hud active"
                        onClick={() => handleAdminSimulateView('full_creator')}
                      >
                        👑 Restaurer : Mode Créateur Complet (Tout débloqué)
                      </button>
                    </div>
                  </div>
                </section>
              ) : (
                <section className="panel-card">
                  <div className="panel-title">📜 HISTORIQUE DES CLÉS ACTIVÉES SUR CE POSTE</div>
                  {(localLicense?.activated_keys || []).length === 0 ? (
                    <p style={{ fontSize: '0.76rem', color: '#94a3b8' }}>
                      Aucune clé commerciale enregistrée pour le moment. Entrez une clé <code>SF3D-...</code> à gauche
                      pour débloquer vos modules.
                    </p>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '8px' }}>
                      {localLicense.activated_keys.map((item, idx) => (
                        <div
                          key={idx}
                          style={{
                            padding: '8px 10px',
                            borderRadius: '7px',
                            background: 'rgba(15, 23, 42, 0.75)',
                            border: '1px solid rgba(0, 240, 255, 0.25)',
                            fontSize: '0.74rem',
                          }}
                        >
                          <div style={{ fontWeight: 700, color: '#00f0ff' }}>{item.key_preview}</div>
                          <div style={{ color: '#cbd5e1', fontSize: '0.68rem', marginTop: '2px' }}>
                            Titulaire : <strong>{item.customer_name}</strong> • Modules :{' '}
                            {(item.modules_granted || []).join(', ')}
                          </div>
                        </div>
                      ))}
                      <button
                        type="button"
                        className="btn-hud"
                        style={{ alignSelf: 'flex-start', marginTop: '6px', color: '#fca5a5' }}
                        onClick={handleResetLicenses}
                      >
                        🗑️ Réinitialiser les licences de ce poste
                      </button>
                    </div>
                  )}
                </section>
              )}
            </div>
          </div>
        ) : setupTab === 'printers' ? (
          <div className="spool-grid-layout">
            {/* LEFT COLUMN: PRINTER AI ASSISTANT + ADD/EDIT PRINTER FORM */}
            <div className="spool-left-col">
              <section className="panel-card" style={{ borderColor: '#00f0ff' }}>
                <div className="panel-title">🤖 RECHERCHE IA DE MODÈLE D&apos;IMPRIMANTE 3D</div>
                <p style={{ fontSize: '0.76rem', color: '#94a3b8', marginBottom: '8px' }}>
                  Tapez le nom d&apos;une imprimante (ex:{' '}
                  <strong className="text-cyan">&quot;Bambu Lab X1C&quot;</strong>,{' '}
                  <strong className="text-cyan">&quot;Creality K2 Plus&quot;</strong>,{' '}
                  <strong className="text-cyan">&quot;Anycubic Kobra 3 Combo&quot;</strong>,{' '}
                  <strong className="text-cyan">&quot;Prusa MK4&quot;</strong>) : l&apos;IA pré-remplit son volume X/Y/Z
                  et le nombre de couleurs. Si le modèle n&apos;est pas trouvé, encodez ses dimensions manuellement ci-dessous.
                </p>

                <div className="btn-row">
                  <input
                    type="text"
                    className="cyber-input"
                    placeholder="Ex: Creality K2 Plus, Bambu Lab P1S, Elegoo Neptune 4 Max..."
                    value={printerAiPrompt}
                    onChange={(e) => setPrinterAiPrompt(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        handlePrinterAiSuggest(false);
                      }
                    }}
                  />
                </div>

                <div className="btn-row" style={{ marginTop: '8px' }}>
                  <button
                    type="button"
                    className="btn-cyber primary"
                    disabled={printerAiLoading || !printerAiPrompt.trim()}
                    onClick={() => handlePrinterAiSuggest(false)}
                  >
                    ✨ Détecter Dimensions X/Y/Z par IA
                  </button>
                  <button
                    type="button"
                    className="btn-cyber secondary"
                    disabled={printerAiLoading || !printerAiPrompt.trim()}
                    onClick={() => handlePrinterAiSuggest(true)}
                  >
                    ⚡ Créer &amp; Ajouter Directement
                  </button>
                </div>
              </section>

              <form className="panel-card" onSubmit={handleSavePrinter}>
                <div className="panel-header-flex">
                  <div className="panel-title">
                    {editingPrinterId
                      ? '✏️ MODIFIER L’IMPRIMANTE SÉLECTIONNÉE'
                      : '➕ ENCODER UNE IMPRIMANTE 3D ( DIMENSIONS X / Y / Z & MODULES )'}
                  </div>
                  {editingPrinterId && (
                    <button
                      type="button"
                      className="btn-hud"
                      onClick={() => setEditingPrinterId(null)}
                    >
                      Annuler édition
                    </button>
                  )}
                </div>

                <div className="grid-2col" style={{ marginTop: '6px' }}>
                  <div>
                    <label className="field-label">Nom de l&apos;Imprimante</label>
                    <input
                      type="text"
                      className="cyber-input"
                      value={printerName}
                      onChange={(e) => setPrinterName(e.target.value)}
                      placeholder="Ex: Creality Hi (Combo 2× CFS)"
                      required
                    />
                  </div>
                  <div>
                    <label className="field-label">Marque (Fabricant)</label>
                    <input
                      type="text"
                      className="cyber-input"
                      value={printerBrand}
                      onChange={(e) => setPrinterBrand(e.target.value)}
                      placeholder="Creality, Bambu Lab, Anycubic, Prusa..."
                      required
                    />
                  </div>
                </div>

                <div className="tds-section-divider">
                  📏 1. DIMENSIONS UTILES DU PLATEAU (EN MILLIMÈTRES)
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '8px' }}>
                  <div>
                    <label className="field-label">Largeur X (mm)</label>
                    <input
                      type="number"
                      min="50"
                      max="1200"
                      className="cyber-input"
                      value={bedXMm}
                      onChange={(e) => setBedXMm(parseInt(e.target.value, 10) || 250)}
                      required
                    />
                  </div>
                  <div>
                    <label className="field-label">Profondeur Y (mm)</label>
                    <input
                      type="number"
                      min="50"
                      max="1200"
                      className="cyber-input"
                      value={bedYMm}
                      onChange={(e) => setBedYMm(parseInt(e.target.value, 10) || 250)}
                      required
                    />
                  </div>
                  <div>
                    <label className="field-label">Hauteur Z (mm)</label>
                    <input
                      type="number"
                      min="50"
                      max="1200"
                      className="cyber-input"
                      value={bedZMm}
                      onChange={(e) => setBedZMm(parseInt(e.target.value, 10) || 250)}
                      required
                    />
                  </div>
                  <div>
                    <label className="field-label">Max Couleurs CFS/AMS</label>
                    <input
                      type="number"
                      min="1"
                      max="16"
                      className="cyber-input"
                      value={maxColors}
                      onChange={(e) => {
                        const c = parseInt(e.target.value, 10) || 1;
                        setMaxColors(c);
                        if (c === 1) setUseHueforge(false);
                        if (c >= 4) setUseHueforge(true);
                      }}
                      title="1 = Mono-couleur, 4 = 1 CFS/AMS, 8 = 2 CFS/AMS"
                    />
                  </div>
                </div>

                <div className="tds-section-divider">
                  🎛️ 2. MODULES AUTORISÉS POUR CETTE IMPRIMANTE
                </div>
                <p style={{ fontSize: '0.73rem', color: '#94a3b8', marginBottom: '8px' }}>
                  Choisissez dans quels modules cette imprimante doit apparaître dans la liste déroulante (ex: décochez{' '}
                  <strong>HueForge</strong> pour une imprimante mono-couleur comme la K1 Max afin d&apos;alléger vos listes).
                </p>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '10px' }}>
                  <label className="switch-label">
                    <input
                      type="checkbox"
                      checked={useCosplay}
                      onChange={(e) => setUseCosplay(e.target.checked)}
                    />
                    <span>
                      ⚔️ <strong>Module 1 : Cosplay &amp; Figurine</strong> (Découpe grand format &amp; tige interne)
                    </span>
                  </label>

                  <label className="switch-label">
                    <input
                      type="checkbox"
                      checked={useHueforge}
                      onChange={(e) => setUseHueforge(e.target.checked)}
                    />
                    <span>
                      🎨 <strong>Module 2A : HueForge &amp; Multi-Frame</strong> (Peinture filament multi-couleurs CFS/AMS)
                    </span>
                  </label>

                  <label className="switch-label">
                    <input
                      type="checkbox"
                      checked={useLithophane}
                      onChange={(e) => setUseLithophane(e.target.checked)}
                    />
                    <span>
                      💡 <strong>Module 2B : Lithophanes &amp; Lightbox LED</strong> (Sculpture lumineuse Beer-Lambert)
                    </span>
                  </label>
                </div>

                <div>
                  <label className="field-label">Notes / Configuration (CFS, Buse, Profil...)</label>
                  <input
                    type="text"
                    className="cyber-input"
                    value={printerNotes}
                    onChange={(e) => setPrinterNotes(e.target.value)}
                    placeholder="Ex: 2 unités CFS connectées (8 couleurs auto), buse 0.4mm"
                  />
                </div>

                <button type="submit" className="btn-cyber primary-full" style={{ marginTop: '12px' }}>
                  {editingPrinterId
                    ? '💾 Enregistrer les Modifications de l’Imprimante'
                    : '➕ Ajouter cette Imprimante à mon Parc'}
                </button>
              </form>
            </div>

            {/* RIGHT COLUMN: CONFIGURED PRINTERS LIST WITH 1-CLICK MODULE TOGGLES */}
            <div className="spool-right-col">
              <section className="panel-card" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                <div className="panel-header-flex">
                  <div className="panel-title">
                    🖨️ PARC D&apos;IMPRIMANTES CONFIGURÉES ({printers.length})
                  </div>
                </div>
                <p style={{ fontSize: '0.75rem', color: '#94a3b8', marginBottom: '10px' }}>
                  Cliquez directement sur les badges <strong>⚔️ Cosplay</strong>, <strong>🎨 HueForge</strong> ou{' '}
                  <strong>💡 Lithophane</strong> d&apos;une imprimante pour l&apos;activer ou la masquer dans ce module.
                  La vérification de dépassement de plateau dans HueForge utilise automatiquement la taille{' '}
                  <strong>X × Y</strong> de l&apos;imprimante sélectionnée.
                </p>

                <div className="spool-cards-list">
                  {printers.map((pr) => (
                    <div key={pr.id} className="spool-item-card" style={{ alignItems: 'flex-start' }}>
                      <div
                        className="spool-color-big-swatch"
                        style={{
                          background:
                            pr.max_colors > 1
                              ? 'linear-gradient(135deg, #00f0ff 0%, #a855f7 50%, #ff2a6d 100%)'
                              : '#334155',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontSize: '0.72rem',
                          fontWeight: 800,
                          color: '#fff',
                        }}
                        title={`${pr.max_colors} couleur(s)`}
                      >
                        {pr.max_colors}C
                      </div>

                      <div className="spool-item-info">
                        <div className="spool-item-title-row">
                          <strong>{pr.name}</strong>
                          <span className="spool-color-badge">{pr.brand}</span>
                          <span
                            className="dim-badge"
                            style={{
                              fontSize: '0.72rem',
                              color: '#00f0ff',
                              border: '1px solid rgba(0, 240, 255, 0.35)',
                              padding: '1px 6px',
                              borderRadius: '4px',
                            }}
                          >
                            📏 Plateau {pr.bed_x_mm} × {pr.bed_y_mm} × {pr.bed_z_mm} mm
                          </span>
                          <span className="dim-badge" style={{ fontSize: '0.7rem' }}>
                            {pr.max_colors > 1 ? `🎨 Jusqu'à ${pr.max_colors} couleurs` : '⚪ Mono-couleur (1C)'}
                          </span>
                        </div>

                        {pr.notes && <div className="spool-item-notes" style={{ marginTop: '4px' }}>{pr.notes}</div>}

                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '6px',
                            marginTop: '8px',
                            flexWrap: 'wrap',
                          }}
                        >
                          <span style={{ fontSize: '0.7rem', color: '#94a3b8' }}>Afficher dans :</span>
                          <button
                            type="button"
                            className={`btn-hud ${pr.use_cosplay !== false ? 'active' : ''}`}
                            style={
                              pr.use_cosplay !== false
                                ? { borderColor: '#00f0ff', color: '#00f0ff', background: 'rgba(0,240,255,0.12)' }
                                : { opacity: 0.5 }
                            }
                            onClick={() => handleTogglePrinterModule(pr.id, 'cosplay')}
                            title="Activer/Masquer cette imprimante dans le Module 1 (Cosplay & Figurine)"
                          >
                            {pr.use_cosplay !== false ? '✓ ⚔️ Cosplay' : '✗ ⚔️ Cosplay'}
                          </button>

                          <button
                            type="button"
                            className={`btn-hud ${pr.use_hueforge !== false ? 'active' : ''}`}
                            style={
                              pr.use_hueforge !== false
                                ? { borderColor: '#ff2a6d', color: '#ff8da1', background: 'rgba(255,42,109,0.15)' }
                                : { opacity: 0.5 }
                            }
                            onClick={() => handleTogglePrinterModule(pr.id, 'hueforge')}
                            title="Activer/Masquer cette imprimante dans le Module 2A (HueForge & Multi-Frame)"
                          >
                            {pr.use_hueforge !== false ? '✓ 🎨 HueForge' : '✗ 🎨 HueForge'}
                          </button>

                          <button
                            type="button"
                            className={`btn-hud ${pr.use_lithophane !== false ? 'active' : ''}`}
                            style={
                              pr.use_lithophane !== false
                                ? { borderColor: '#facc15', color: '#fde047', background: 'rgba(250,204,21,0.12)' }
                                : { opacity: 0.5 }
                            }
                            onClick={() => handleTogglePrinterModule(pr.id, 'lithophane')}
                            title="Activer/Masquer cette imprimante dans le Module 2B (Lithophanes & Lightbox LED)"
                          >
                            {pr.use_lithophane !== false ? '✓ 💡 Lithophane' : '✗ 💡 Lithophane'}
                          </button>
                        </div>
                      </div>

                      <div className="spool-item-actions">
                        <button
                          type="button"
                          className="btn-hud"
                          onClick={() => handleEditPrinterClick(pr)}
                          title="Modifier les dimensions X/Y/Z ou les modules de cette imprimante"
                        >
                          ✏️
                        </button>
                        <button
                          type="button"
                          className="btn-hud"
                          style={{ borderColor: '#7f1d1d', color: '#fca5a5' }}
                          onClick={() => handleDeletePrinter(pr.id)}
                          title="Supprimer cette imprimante"
                        >
                          🗑️
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            </div>
          </div>
        ) : (
        <div className="spool-grid-layout">
          {/* LEFT COLUMN: AI ASSISTANT + SPOOL FORM */}
          <div className="spool-left-col">
            {/* AI ASSISTANT CARD */}
            <section className="panel-card" style={{ borderColor: '#00f0ff' }}>
              <div className="panel-title">🤖 ASSISTANT IA D&apos;ENCODAGE RAPIDE DE BOBINE</div>
              <p style={{ fontSize: '0.76rem', color: '#94a3b8', marginBottom: '8px' }}>
                Tapez simplement le nom de votre bobine ou d&apos;une nuance (ex:{' '}
                <strong className="text-cyan">&quot;Deeplee PLA+ Blanc&quot;</strong>,{' '}
                <strong className="text-cyan">&quot;Creality PLA Rouge&quot;</strong>,{' '}
                <strong className="text-cyan">&quot;Bleu glacier clair&quot;</strong>) : l&apos;IA génère le bon code
                couleur Hex, la translucidité TD et les températures.
              </p>

              <div className="btn-row">
                <input
                  type="text"
                  className="cyber-input"
                  placeholder="Ex: Deeplee PLA+ Blanc, Sunlu PLA Noir, Bleu nuit..."
                  value={aiPrompt}
                  onChange={(e) => setAiPrompt(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      handleAiAssist();
                    }
                  }}
                />
              </div>

              <div className="btn-row" style={{ marginTop: '8px' }}>
                <button
                  type="button"
                  className="btn-cyber primary"
                  disabled={aiLoading || !aiPrompt.trim()}
                  onClick={() => handleAiAssist()}
                >
                  ✨ Pré-remplir avec l&apos;IA
                </button>
                <button
                  type="button"
                  className="btn-cyber secondary"
                  disabled={aiLoading || !aiPrompt.trim()}
                  onClick={handleAiQuickAdd}
                >
                  ⚡ Créer &amp; Ajouter Directement
                </button>
              </div>
            </section>

            {/* ADD / EDIT SPOOL FORM */}
            <form className="panel-card" onSubmit={handleSaveSpool}>
              <div className="panel-header-flex">
                <div className="panel-title">
                  {editingId ? '✏️ MODIFIER LA BOBINE SÉLECTIONNÉE' : '➕ AJOUTER / PERSONNALISER UNE BOBINE'}
                </div>
                {editingId && (
                  <button
                    type="button"
                    className="btn-hud"
                    onClick={() => setEditingId(null)}
                  >
                    Annuler édition
                  </button>
                )}
              </div>

              <div className="tds-section-divider" style={{ marginTop: '4px', borderTop: 'none', paddingTop: 0 }}>
                🎨 1. IDENTITÉ &amp; PROPRIÉTÉS OPTIQUES (HUEFORGE)
              </div>

              <div className="grid-2col">
                <div>
                  <label className="field-label-with-info">
                    <span>Marque (Brand)</span>
                    <FieldInfo title="Marque du Fabricant">
                      Chaque fabricant utilise ses propres pigments et additifs. L&apos;IA pré-charge automatiquement les paramètres de fiche technique (TDS) pour Anycubic, Creality, Deeplee, Sunlu, eSUN, Bambu Lab, Polymaker, etc.
                    </FieldInfo>
                  </label>
                  <input
                    type="text"
                    className="cyber-input"
                    value={brand}
                    onChange={(e) => setBrand(e.target.value)}
                    placeholder="Anycubic, Deeplee, Creality, Sunlu..."
                    required
                  />
                </div>
                <div>
                  <label className="field-label-with-info">
                    <span>Type / Matériau</span>
                    <FieldInfo title="Famille de Polymère (PLA+, Hyper PLA, PETG...)">
                      Le <strong>PLA+</strong> (ex: Anycubic PLA+) offre une haute ténacité et une meilleure liaison inter-couches que le PLA classique (idéal pour les armes Cosplay du Module 1), tandis que le <strong>Hyper PLA</strong> est fluidifié pour les hautes vitesses Creality Hi / K1 Max.
                    </FieldInfo>
                  </label>
                  <input
                    type="text"
                    className="cyber-input"
                    value={material}
                    onChange={(e) => setMaterial(e.target.value)}
                    placeholder="PLA+, Hyper PLA, PLA Matte, PETG..."
                    required
                  />
                </div>
              </div>

              <div className="grid-2col">
                <div>
                  <label className="field-label-with-info">
                    <span>Nom de la Couleur</span>
                    <FieldInfo title="Désignation Commerciale de la Nuance">
                      Nom de la couleur sur la bobine (ex: <em>Blanc Pur, Bleu Nuit, Gris Argent</em>). Utilisé pour rechercher rapidement votre bobine dans la liste déroulante CFS.
                    </FieldInfo>
                  </label>
                  <input
                    type="text"
                    className="cyber-input"
                    value={colorName}
                    onChange={(e) => setColorName(e.target.value)}
                    placeholder="Blanc Pur, Rouge Sang..."
                    required
                  />
                </div>
                <div>
                  <label className="field-label-with-info">
                    <span>Carré Couleur &amp; Code Hex</span>
                    <FieldInfo title="Code Couleur Optique (#RRGGBB)">
                      Couleur réelle du filament extrudé à pleine opacité. Ce code est utilisé par le <strong>Matcher IA (&quot;Mon Stock&quot;)</strong> pour comparer vos bobines aux couleurs de l&apos;image et simuler le rendu 2D/3D HueForge.
                    </FieldInfo>
                  </label>
                  <div className="btn-row" style={{ alignItems: 'center' }}>
                    <input
                      type="color"
                      value={hexColor}
                      onChange={(e) => setHexColor(e.target.value)}
                      style={{
                        width: '44px',
                        height: '35px',
                        border: '1px solid #38bdf8',
                        borderRadius: '5px',
                        background: 'transparent',
                        cursor: 'pointer',
                      }}
                    />
                    <input
                      type="text"
                      className="cyber-input"
                      value={hexColor}
                      onChange={(e) => setHexColor(e.target.value)}
                    />
                  </div>
                </div>
              </div>

              <div className="grid-2col">
                <div>
                  <label className="field-label-with-info">
                    <span>
                      Translucidité TD : <strong className="text-cyan">{tdMm} mm</strong>
                    </span>
                    <FieldInfo title="Transmission Distance (TD en mm) — Paramètre Clé HueForge">
                      Épaisseur au-delà de laquelle le filament bloque 99% de la lumière (à 0.08 mm/couche) :<br />
                      • <strong>0.5 à 1.2 mm (Opaque)</strong> : couvre la couleur inférieure dès 2–3 couches (Noir, Gris foncé).<br />
                      • <strong>2.0 à 3.5 mm (Semi-translucide)</strong> : laisse transparaître la couleur du dessous sur 4–7 couches pour créer des dégradés fondus.<br />
                      • <strong>&gt; 4.0 mm (Glacis)</strong> : très translucide.
                    </FieldInfo>
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    min="0.3"
                    max="6.0"
                    className="cyber-input"
                    value={tdMm}
                    onChange={(e) => setTdMm(parseFloat(e.target.value) || 2.0)}
                  />
                </div>
                <div>
                  <label className="field-label-with-info">
                    <span>Finition / Rendu Optique</span>
                    <FieldInfo title="Réflexion & Diffusion de la Lumière en Surface">
                      • <strong>Standard (Satiné)</strong> : équilibre fidèle des couleurs.<br />
                      • <strong>Matte (Mat)</strong> : diffuse la lumière sans reflet parasite et paraît plus sombre et velouté.<br />
                      • <strong>Silk (Soie)</strong> : réfléchit la lumière de façon spéculaire (brillante/métallique) mais possède un TD plus opaque.<br />
                      • <strong>Translucide</strong> : laisse passer la lumière en profondeur.
                    </FieldInfo>
                  </label>
                  <select
                    className="cyber-input"
                    value={surfaceFinish}
                    onChange={(e) => setSurfaceFinish(e.target.value)}
                  >
                    <option value="Standard">Standard (Satiné)</option>
                    <option value="Matte">Matte (Mat anti-reflet)</option>
                    <option value="Silk">Silk (Soie brillante / Métallisé)</option>
                    <option value="Translucide">Translucide / Clear</option>
                    <option value="Pailleté / Effet">Pailleté / Galaxy / Marbre</option>
                  </select>
                </div>
              </div>

              <div className="tds-section-divider">
                🔥 2. EXTRUSION, DÉBIT &amp; SÉCHAGE (FICHE TECHNIQUE TDS)
              </div>

              <div className="grid-2col">
                <div>
                  <label className="field-label-with-info">
                    <span>Temp. Buse / Plateau (°C)</span>
                    <FieldInfo title="Températures d'Extrusion & Lit Chauffant (TDS)">
                      Sur la fiche Anycubic PLA+ : Buse <strong>190–230°C</strong> (idéal 210°C) et Plateau <strong>55–65°C</strong> (60°C). En HueForge (couches fines de 0.08 mm), imprimer vers 210–215°C rend le plastique plus limpide et améliore la fusion optique entre les couleurs.
                    </FieldInfo>
                  </label>
                  <div className="btn-row">
                    <input
                      type="number"
                      className="cyber-input"
                      value={nozzleTemp}
                      onChange={(e) => setNozzleTemp(parseInt(e.target.value, 10) || 210)}
                      title="Température Buse (°C)"
                    />
                    <input
                      type="number"
                      className="cyber-input"
                      value={bedTemp}
                      onChange={(e) => setBedTemp(parseInt(e.target.value, 10) || 60)}
                      title="Température Plateau (°C)"
                    />
                  </div>
                </div>
                <div>
                  <label className="field-label-with-info">
                    <span>Multiplicateur Flux &amp; Débit Max</span>
                    <FieldInfo title="Extrusion Multiplier (Flow) & Max Volumetric Flow (mm³/s)">
                      Valeurs clés de la fiche TDS (ex: Anycubic PLA+ : <strong>Flow = 0.96</strong>, <strong>Débit max = 12 mm³/s</strong>) :<br />
                      • <strong>Flow Ratio (0.96)</strong> : évite la sur-extrusion sur les couches 100% pleines à 0.08 mm (qui créerait des bourrelets raclés par la buse).<br />
                      • <strong>Débit Max (mm³/s)</strong> : limite la vitesse sur Creality Hi / K1 Max pour éviter la sous-extrusion (12 mm³/s en PLA+ standard vs 20+ mm³/s en Hyper PLA).
                    </FieldInfo>
                  </label>
                  <div className="btn-row">
                    <input
                      type="number"
                      step="0.01"
                      min="0.80"
                      max="1.15"
                      className="cyber-input"
                      value={flowRatio}
                      onChange={(e) => setFlowRatio(parseFloat(e.target.value) || 0.96)}
                      title="Extrusion Multiplier / Flow Ratio (ex: 0.96)"
                    />
                    <input
                      type="number"
                      step="0.5"
                      min="2"
                      max="40"
                      className="cyber-input"
                      value={maxVolumetricFlow}
                      onChange={(e) => setMaxVolumetricFlow(parseFloat(e.target.value) || 12.0)}
                      title="Max Volumetric Flow Rate en mm³/s (ex: 12 mm³/s)"
                    />
                  </div>
                </div>
              </div>

              <div className="grid-2col">
                <div>
                  <label className="field-label-with-info">
                    <span>Séchage TDS (°C / Heures)</span>
                    <FieldInfo title="Conditionnement & Séchage (Dry Environment)">
                      Fiche TDS Anycubic PLA+ : <strong>45–50°C pendant 6 à 8h</strong> (taux d&apos;humidité &lt; 0.23%). Un filament humide fait des bulles et crée des fils d&apos;ange (<em>stringing</em>) sur les micro-reliefs HueForge qui salissent les couleurs claires lors des changements CFS.
                    </FieldInfo>
                  </label>
                  <div className="btn-row">
                    <input
                      type="number"
                      className="cyber-input"
                      value={dryingTempC}
                      onChange={(e) => setDryingTempC(parseInt(e.target.value, 10) || 48)}
                      title="Température de séchage (°C) — ex: 48°C"
                    />
                    <input
                      type="number"
                      className="cyber-input"
                      value={dryingHours}
                      onChange={(e) => setDryingHours(parseInt(e.target.value, 10) || 6)}
                      title="Durée de séchage (heures) — ex: 6h"
                    />
                  </div>
                </div>
                <div>
                  <label className="field-label-with-info">
                    <span>Ramollissement HDT (°C) / Z (MPa)</span>
                    <FieldInfo title="Résistance Thermique (HDT/Vicat) & Adhérence Inter-Couches (Axe Z)">
                      Issu de la fiche mécanique &amp; thermique TDS (ex: Anycubic PLA+ : <strong>HDT/Vicat = 50–52°C</strong>, <strong>Traction Z = 23.8 MPa</strong>) :<br />
                      • <strong>HDT (°C)</strong> : température où la pièce se déforme (à 52°C, ne jamais laisser une arme Cosplay ou un cadre PLA+ dans une voiture au soleil !).<br />
                      • <strong>Traction Z (MPa)</strong> : solidité entre les couches pour les grandes pièces du Module 1.
                    </FieldInfo>
                  </label>
                  <div className="btn-row">
                    <input
                      type="number"
                      className="cyber-input"
                      value={hdtC}
                      onChange={(e) => setHdtC(parseInt(e.target.value, 10) || 52)}
                      title="Température de ramollissement HDT / Vicat (°C)"
                    />
                    <input
                      type="number"
                      step="0.5"
                      className="cyber-input"
                      value={tensileZMpa}
                      onChange={(e) => setTensileZMpa(parseFloat(e.target.value) || 23.8)}
                      title="Résistance à la traction inter-couches Axe Z (MPa)"
                    />
                  </div>
                </div>
              </div>

              <div className="tds-section-divider">
                🏷️ 3. RÉFÉRENCE, NOTES &amp; DISPONIBILITÉ STOCK
              </div>

              <div className="grid-2col">
                <div>
                  <label className="field-label-with-info">
                    <span>Référence / Code Recherche</span>
                    <FieldInfo title="Code SKU ou Référence Interne">
                      Identifiant court (généré automatiquement ou personnalisé) permettant de retrouver instantanément la bobine dans la barre de recherche.
                    </FieldInfo>
                  </label>
                  <input
                    type="text"
                    className="cyber-input"
                    value={referenceSku}
                    onChange={(e) => setReferenceSku(e.target.value)}
                    placeholder="Ex: ANY-PLA+-WHITE"
                  />
                </div>
                <div>
                  <label className="field-label-with-info">
                    <span>Note / Usage HueForge &amp; Cosplay</span>
                    <FieldInfo title="Notes Personnelles d'Impression">
                      Notez ici vos observations (ex: <em>&quot;Super blanc final très lumineux&quot;, &quot;Nécessite 0.96 de flow dans Creality Print&quot;</em>).
                    </FieldInfo>
                  </label>
                  <input
                    type="text"
                    className="cyber-input"
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="Ex: Très bon blanc final"
                  />
                </div>
              </div>

              <div className="grid-2col" style={{ marginTop: '10px' }}>
                <label className="switch-label">
                  <input
                    type="checkbox"
                    checked={inStock}
                    onChange={(e) => setInStock(e.target.checked)}
                  />
                  <span>
                    📦 <strong>En stock actuellement</strong> (Utilisable par le Matcher IA)
                  </span>
                </label>

                <label className="switch-label">
                  <input
                    type="checkbox"
                    checked={isFavorite}
                    onChange={(e) => setIsFavorite(e.target.checked)}
                  />
                  <span>
                    ⭐ <strong>Raccourci rapide</strong> dans HueForge Studio
                  </span>
                </label>
              </div>

              <button type="submit" className="btn-cyber primary-full" style={{ marginTop: '12px' }}>
                {editingId
                  ? '💾 Enregistrer les Modifications de la Bobine'
                  : '➕ Ajouter cette Bobine à ma Bibliothèque'}
              </button>
            </form>
          </div>

          {/* RIGHT COLUMN: SPOOL LIBRARY LIST & SHORTCUT MANAGER */}
          <div className="spool-right-col">
            <section className="panel-card" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
              <div className="panel-header-flex">
                <div className="panel-title">
                  📚 MES BOBINES ({spools.length}) —{' '}
                  <span style={{ color: '#10b981' }}>📦 {inStockCount} En Stock</span> •{' '}
                  <span style={{ color: '#facc15' }}>⭐ {favoritesCount} Raccourcis</span>
                </div>
                <div className="mode-tabs" style={{ width: '280px' }}>
                  <button
                    type="button"
                    className={`tab-btn ${stockFilter === 'all' ? 'active' : ''}`}
                    onClick={() => setStockFilter('all')}
                  >
                    Toutes ({spools.length})
                  </button>
                  <button
                    type="button"
                    className={`tab-btn ${stockFilter === 'in_stock' ? 'active' : ''}`}
                    onClick={() => setStockFilter('in_stock')}
                  >
                    📦 En Stock ({inStockCount})
                  </button>
                  <button
                    type="button"
                    className={`tab-btn ${stockFilter === 'favorites' ? 'active' : ''}`}
                    onClick={() => setStockFilter('favorites')}
                  >
                    ⭐ Raccourcis ({favoritesCount})
                  </button>
                </div>
              </div>

              <div className="btn-row" style={{ marginBottom: '10px', alignItems: 'center' }}>
                <input
                  type="text"
                  className="cyber-input"
                  placeholder="🔍 Rechercher par marque (Deeplee, Sunlu, Creality), couleur, référence..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  style={{ flex: 1 }}
                />
                <button
                  type="button"
                  className="btn-hud"
                  onClick={() => handleSortSpools('luminance')}
                  title="Trier automatiquement vos bobines de la plus sombre (Noir) à la plus claire (Blanc)"
                >
                  🎨 Sombre → Clair
                </button>
                <button
                  type="button"
                  className="btn-hud"
                  onClick={() => handleSortSpools('brand')}
                  title="Trier vos bobines par Marque puis par Couleur"
                >
                  🏷️ Par Marque
                </button>
              </div>

              <div className="spool-cards-list">
                {filteredSpools.map((sp) => {
                  const globalIdx = spools.findIndex((item) => item.id === sp.id);
                  return (
                  <div
                    key={sp.id}
                    className="spool-item-card"
                    style={{ opacity: sp.in_stock === false ? 0.58 : 1 }}
                  >
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                      <button
                        type="button"
                        className="btn-hud"
                        style={{ padding: '1px 5px', fontSize: '0.62rem', lineHeight: 1 }}
                        disabled={globalIdx <= 0}
                        onClick={() => handleMoveSpool(sp.id, 'up')}
                        title="Monter cette couleur dans la liste et les raccourcis"
                      >
                        ▲
                      </button>
                      <button
                        type="button"
                        className="btn-hud"
                        style={{ padding: '1px 5px', fontSize: '0.62rem', lineHeight: 1 }}
                        disabled={globalIdx < 0 || globalIdx >= spools.length - 1}
                        onClick={() => handleMoveSpool(sp.id, 'down')}
                        title="Descendre cette couleur dans la liste et les raccourcis"
                      >
                        ▼
                      </button>
                    </div>
                    <div
                      className="spool-color-big-swatch"
                      style={{ backgroundColor: sp.hex_color }}
                      title={sp.hex_color}
                    />
                    <div className="spool-item-info">
                      <div className="spool-item-title-row">
                        <strong>
                          {sp.brand} {sp.material}
                        </strong>
                        <span className="spool-color-badge">{sp.color_name}</span>
                        {sp.surface_finish && sp.surface_finish !== 'Standard' && (
                          <span
                            className="dim-badge"
                            style={{ fontSize: '0.68rem', color: '#38bdf8', border: '1px solid #1e3a5f', padding: '1px 5px', borderRadius: '4px' }}
                          >
                            ✨ {sp.surface_finish}
                          </span>
                        )}
                        <span className="dim-badge" style={{ fontSize: '0.7rem' }}>
                          {sp.hex_color}
                        </span>
                      </div>
                      <div className="spool-item-meta" style={{ flexWrap: 'wrap' }}>
                        <span>
                          TD: <strong className="text-cyan">{sp.td_mm} mm</strong>
                        </span>
                        <span>•</span>
                        <span>
                          Buse: <strong>{sp.nozzle_temp_c}°C</strong> / Lit: <strong>{sp.bed_temp_c}°C</strong>
                        </span>
                        <span>•</span>
                        <span>
                          Flow: <strong>{sp.flow_ratio ?? 0.96}</strong> ({sp.max_volumetric_flow ?? 12} mm³/s)
                        </span>
                        <span>•</span>
                        <span>
                          Séchage: <strong>{sp.drying_temp_c ?? 48}°C/{sp.drying_hours ?? 6}h</strong>
                        </span>
                        <span>•</span>
                        <span>
                          HDT: <strong>{sp.hdt_c ?? 52}°C</strong> | Z: <strong>{sp.tensile_z_mpa ?? 23.8} MPa</strong>
                        </span>
                        {sp.reference_sku && (
                          <>
                            <span>•</span>
                            <span>
                              Réf: <code>{sp.reference_sku}</code>
                            </span>
                          </>
                        )}
                      </div>
                      {sp.notes && <div className="spool-item-notes">{sp.notes}</div>}
                    </div>

                    <div className="spool-item-actions">
                      <button
                        type="button"
                        className={`btn-hud ${sp.in_stock !== false ? 'active' : ''}`}
                        style={
                          sp.in_stock !== false
                            ? { borderColor: '#10b981', color: '#34d399', background: 'rgba(16,185,129,0.12)' }
                            : { borderColor: '#475569', color: '#94a3b8' }
                        }
                        onClick={() => handleToggleStock(sp.id)}
                        title="Indiquer si vous avez actuellement cette bobine en stock pour le Matcher IA"
                      >
                        {sp.in_stock !== false ? '📦 En Stock' : '⏳ Rupture'}
                      </button>
                      <button
                        type="button"
                        className={`btn-hud ${sp.is_favorite ? 'active' : ''}`}
                        onClick={() => handleToggleFavorite(sp.id)}
                        title="Activer/Désactiver dans la barre de raccourcis rapides HueForge"
                      >
                        {sp.is_favorite ? '⭐ Raccourci' : '☆ Raccourci'}
                      </button>
                      <button
                        type="button"
                        className="btn-hud"
                        onClick={() => handleEditClick(sp)}
                      >
                        ✏️
                      </button>
                      <button
                        type="button"
                        className="btn-hud"
                        style={{ borderColor: '#7f1d1d', color: '#fca5a5' }}
                        onClick={() => handleDeleteSpool(sp.id)}
                        title="Supprimer cette bobine"
                      >
                        🗑️
                      </button>
                    </div>
                  </div>
                  );
                })}
              </div>
            </section>
          </div>
        </div>
        )}
      </div>
    </div>
  );
}

