import React, { useRef } from 'react';

const ROD_PRESETS = [
  { key: 'round_4', label: 'Tige Ronde Ø4 mm', type: 'round', width: 4, thickness: 4 },
  { key: 'round_6', label: 'Tige Ronde Ø6 mm', type: 'round', width: 6, thickness: 6 },
  { key: 'round_8', label: 'Tige Ronde Ø8 mm (Standard Cosplay)', type: 'round', width: 8, thickness: 8 },
  { key: 'round_10', label: 'Tige Ronde Ø10 mm', type: 'round', width: 10, thickness: 10 },
  { key: 'round_12', label: 'Tige Ronde Ø12 mm (Lourd)', type: 'round', width: 12, thickness: 12 },
  { key: 'square_6x6', label: 'Tube Carré 6×6 mm (Anti-rotation)', type: 'square', width: 6, thickness: 6 },
  { key: 'square_8x8', label: 'Tube Carré 8×8 mm (Anti-rotation)', type: 'square', width: 8, thickness: 8 },
  { key: 'square_10x10', label: 'Tube Carré 10×10 mm', type: 'square', width: 10, thickness: 10 },
  { key: 'flat_10x2', label: 'Plat Alu 10×2 mm (Lame fine)', type: 'flat', width: 10, thickness: 2 },
  { key: 'flat_15x3', label: 'Plat Alu 15×3 mm (Épée large)', type: 'flat', width: 15, thickness: 3 },
];

export default function Sidebar({
  loading,
  onUploadStl,
  onGenerateDemoSword,
  sessionId,
  filename,
  printerPreset,
  onChangePrinterPreset,
  printers = [],
  onAlignPca,
  onResetModel,
  showRod,
  setShowRod,
  rodConfig,
  setRodConfig,
  pointA,
  pointB,
  onApplyRodTunnel,
  rodReport,
  cutMode,
  setCutMode,
  maxBuildSize,
  setMaxBuildSize,
  connectorType,
  setConnectorType,
  femaleClearance,
  setFemaleClearance,
  engraveNumbers,
  setEngraveNumbers,
  boundedOrigin,
  setBoundedOrigin,
  boundedSize,
  setBoundedSize,
  boundedType,
  setBoundedType,
  onExecuteSmartCut,
  cutResult,
  downloadZipUrl,
}) {
  const fileInputRef = useRef(null);

  const handlePresetSelect = (presetKey) => {
    const found = ROD_PRESETS.find((p) => p.key === presetKey);
    if (!found) return;
    setRodConfig({
      ...rodConfig,
      presetKey: found.key,
      profileType: found.type,
      width: found.width,
      thickness: found.thickness,
    });
  };

  const liveRodLength =
    pointA && pointB
      ? Math.hypot(
          pointB[0] - pointA[0],
          pointB[1] - pointA[1],
          pointB[2] - pointA[2]
        ).toFixed(1)
      : 0;

  return (
    <aside className="sidebar">
      {/* Header */}
      <div className="sidebar-header">
        <div className="brand-title">
          MAKER<span>STUDIO</span> 3D
        </div>
        <div className="brand-subtitle">
          MODULE 1 : COSPLAY &amp; FIGURINE SMART SLICER
        </div>
      </div>

      <div className="sidebar-scroll">
        {/* SECTION 1 : IMPRIMANTE & IMPORT STL */}
        <section className="panel-card">
          <div className="panel-title">1. IMPRIMANTE &amp; IMPORT STL</div>

          <label className="field-label">Profil Imprimante Calibré (Filtré Module Cosplay)</label>
          <select
            className="cyber-input"
            value={printerPreset}
            onChange={(e) => onChangePrinterPreset(e.target.value)}
          >
            {printers.filter((p) => p.use_cosplay !== false).length > 0 ? (
              printers
                .filter((p) => p.use_cosplay !== false)
                .map((pr) => (
                  <option key={pr.id} value={pr.id}>
                    🖨️ {pr.name} ({pr.bed_x_mm}×{pr.bed_y_mm}×{pr.bed_z_mm} mm — Coupe {Math.max(100, (pr.bed_z_mm || 300) - 15)} mm)
                  </option>
                ))
            ) : (
              <>
                <option value="k1_max">Creality K1 Max (300×300×300 mm — Coupe 285 mm)</option>
                <option value="creality_hi">Creality Hi (260×260×300 mm — Coupe 245 mm)</option>
              </>
            )}
          </select>

          <input
            ref={fileInputRef}
            type="file"
            accept=".stl"
            style={{ display: 'none' }}
            onChange={(e) => {
              const selected = e.target.files?.[0];
              if (selected) {
                onUploadStl(selected);
              }
              e.target.value = '';
            }}
          />

          <div className="btn-row" style={{ marginTop: '10px' }}>
            <button
              className="btn-cyber primary"
              disabled={loading}
              onClick={() => fileInputRef.current?.click()}
            >
              Importer un .STL
            </button>
            <button
              className="btn-cyber secondary"
              disabled={loading}
              onClick={onGenerateDemoSword}
              title="Génère une épée Cosplay de 820 mm inclinée pour tester immédiatement l'alignement PCA et la découpe K1 Max"
            >
              Épée Démo (820mm)
            </button>
          </div>

          {sessionId && (
            <div className="file-pill">
              <span>Fichier actif :</span> <strong>{filename}</strong>
            </div>
          )}

          {sessionId && (
            <div className="btn-row" style={{ marginTop: '8px' }}>
              <button
                className="btn-cyber accent"
                disabled={loading}
                onClick={onAlignPca}
              >
                ⚡ Auto-Align PCA (Vertical Z)
              </button>
              <button
                className="btn-cyber ghost"
                disabled={loading}
                onClick={onResetModel}
              >
                Réinitialiser
              </button>
            </div>
          )}
        </section>

        {/* SECTION 2 : TUNNEL POUR TIGE DE RENFORT COSPLAY */}
        <section className="panel-card">
          <div className="panel-header-flex">
            <div className="panel-title">2. TUNNEL TIGE COSPLAY (BRICO)</div>
            <label className="switch-label">
              <input
                type="checkbox"
                checked={showRod}
                onChange={(e) => setShowRod(e.target.checked)}
              />
              <span>Activer</span>
            </label>
          </div>

          <label className="field-label">Profilé Standard (Barre 1 mètre)</label>
          <select
            className="cyber-input"
            value={rodConfig.presetKey}
            onChange={(e) => handlePresetSelect(e.target.value)}
          >
            {ROD_PRESETS.map((p) => (
              <option key={p.key} value={p.key}>
                {p.label}
              </option>
            ))}
          </select>

          <div className="grid-2col">
            <div>
              <label className="field-label">Diamètre / Largeur (mm)</label>
              <input
                type="number"
                step="0.5"
                className="cyber-input"
                value={rodConfig.width}
                onChange={(e) =>
                  setRodConfig({ ...rodConfig, width: parseFloat(e.target.value) || 8 })
                }
              />
            </div>
            <div>
              <label className="field-label">Tolérance Jeu (+mm)</label>
              <input
                type="number"
                step="0.05"
                className="cyber-input"
                value={rodConfig.clearance}
                onChange={(e) =>
                  setRodConfig({ ...rodConfig, clearance: parseFloat(e.target.value) || 0.3 })
                }
              />
            </div>
          </div>

          {rodConfig.profileType === 'flat' && (
            <div className="grid-2col">
              <div>
                <label className="field-label">Épaisseur du Plat (mm)</label>
                <input
                  type="number"
                  step="0.5"
                  className="cyber-input"
                  value={rodConfig.thickness}
                  onChange={(e) =>
                    setRodConfig({ ...rodConfig, thickness: parseFloat(e.target.value) || 2 })
                  }
                />
              </div>
              <div>
                <label className="field-label">Rotation Lame (°)</label>
                <input
                  type="number"
                  step="5"
                  className="cyber-input"
                  value={rodConfig.twistAngleDeg}
                  onChange={(e) =>
                    setRodConfig({
                      ...rodConfig,
                      twistAngleDeg: parseFloat(e.target.value) || 0,
                    })
                  }
                />
              </div>
            </div>
          )}

          <div className="rod-callout">
            <div>
              Longueur du canal A→B : <strong>{liveRodLength} mm</strong>
            </div>
            <div className="cut-highlight">
              ✂️ Longueur à couper (barre 1m) :{' '}
              <strong>{Math.max(0, (liveRodLength - 2).toFixed(1))} mm</strong>
            </div>
          </div>

          <button
            className="btn-cyber pink-full"
            disabled={!sessionId || loading}
            onClick={onApplyRodTunnel}
          >
            Soustraire le Canal de Tige (Manifold3D)
          </button>

          {rodReport && (
            <div className="success-box">
              ✓ Canal percé ({rodReport.cutout_dimensions_mm[0]}×
              {rodReport.cutout_dimensions_mm[1]} mm). Coupez exactement{' '}
              <strong>{rodReport.recommended_cut_length_mm} mm</strong> sur votre barre de 1m (Chute :{' '}
              {rodReport.remaining_on_1m_bar_mm} mm).
            </div>
          )}
        </section>

        {/* SECTION 3 : DÉCOUPE INTELLIGENTE & CONNECTEURS */}
        <section className="panel-card">
          <div className="panel-title">3. DÉCOUPE &amp; TENONS GÉOMÉTRIQUES</div>

          <div className="mode-tabs">
            <button
              className={`tab-btn ${cutMode === 'auto_grid' ? 'active' : ''}`}
              onClick={() => setCutMode('auto_grid')}
            >
              Mode A : Grille Auto (K1 Max)
            </button>
            <button
              className={`tab-btn ${cutMode === 'bounded_figurine' ? 'active' : ''}`}
              onClick={() => setCutMode('bounded_figurine')}
            >
              Mode B : Coupe Locale Figurine
            </button>
          </div>

          {cutMode === 'auto_grid' ? (
            <div style={{ marginTop: '10px' }}>
              <label className="field-label">
                Hauteur Max des Tronçons (mm) — K1 Max = 285 mm
              </label>
              <input
                type="number"
                step="5"
                className="cyber-input"
                value={maxBuildSize}
                onChange={(e) => setMaxBuildSize(parseFloat(e.target.value) || 285)}
              />
            </div>
          ) : (
            <div style={{ marginTop: '10px' }}>
              <label className="field-label">Forme de la Zone Locale (Membre / Tête)</label>
              <select
                className="cyber-input"
                value={boundedType}
                onChange={(e) => setBoundedType(e.target.value)}
              >
                <option value="cylinder">Cylindre Englobant Local</option>
                <option value="box">Bounding Box Locale</option>
              </select>
              <div className="grid-2col">
                <div>
                  <label className="field-label">Hauteur Z de Coupe (mm)</label>
                  <input
                    type="number"
                    className="cyber-input"
                    value={boundedOrigin[2]}
                    onChange={(e) =>
                      setBoundedOrigin([
                        boundedOrigin[0],
                        boundedOrigin[1],
                        parseFloat(e.target.value) || 100,
                      ])
                    }
                  />
                </div>
                <div>
                  <label className="field-label">Rayon / Taille Zone (mm)</label>
                  <input
                    type="number"
                    className="cyber-input"
                    value={boundedSize[0]}
                    onChange={(e) => {
                      const v = parseFloat(e.target.value) || 80;
                      setBoundedSize([v, v, v]);
                    }}
                  />
                </div>
              </div>
            </div>
          )}

          <label className="field-label" style={{ marginTop: '10px' }}>
            Type de Connecteur (Dépouille Conique 2°)
          </label>
          <select
            className="cyber-input"
            value={connectorType}
            onChange={(e) => setConnectorType(e.target.value)}
          >
            <option value="hexagon_peg">
              Cheville Hexagonale Biconique Séparée + Mortaises
            </option>
            <option value="square_peg">
              Cheville Carrée Biconique Séparée + Mortaises
            </option>
            <option value="direct_tenon_hex">
              Tenon Mâle Hexagonal Direct + Mortaise Femelle
            </option>
            <option value="direct_tenon_square">
              Tenon Mâle Carré Direct + Mortaise Femelle
            </option>
            <option value="none">Aucun (Tige traversante seule)</option>
          </select>

          <div className="grid-2col">
            <div>
              <label className="field-label">Tolérance Femelle (+mm)</label>
              <input
                type="number"
                step="0.02"
                className="cyber-input"
                value={femaleClearance}
                onChange={(e) => setFemaleClearance(parseFloat(e.target.value) || 0.18)}
              />
            </div>
            <div style={{ display: 'flex', alignItems: 'flex-end', paddingBottom: '6px' }}>
              <label className="switch-label">
                <input
                  type="checkbox"
                  checked={engraveNumbers}
                  onChange={(e) => setEngraveNumbers(e.target.checked)}
                />
                <span>Graver N° 3D (-0.8mm)</span>
              </label>
            </div>
          </div>

          <button
            className="btn-cyber primary-full"
            disabled={!sessionId || loading}
            onClick={onExecuteSmartCut}
          >
            {loading
              ? 'Calcul CSG Manifold3D en cours...'
              : '⚡ Lancer la Découpe & Générer les Connecteurs'}
          </button>

          {cutResult && (
            <div className="cut-summary-box">
              <div className="summary-header">
                ✓ {cutResult.parts_count} fichiers STL générés avec succès
              </div>
              <ul className="parts-list">
                {cutResult.parts.map((p) => (
                  <li key={p.part_index}>
                    <span>{p.filename}</span>
                    <span className="dim-badge">
                      {p.extents_mm[0]}×{p.extents_mm[1]}×{p.extents_mm[2]} mm
                    </span>
                  </li>
                ))}
              </ul>
              {downloadZipUrl && (
                <a
                  href={downloadZipUrl}
                  download
                  className="btn-cyber download-zip-btn"
                >
                  📦 Télécharger l&apos;Archive .ZIP (Prêt à Trancher)
                </a>
              )}
            </div>
          )}
        </section>
      </div>
    </aside>
  );
}

