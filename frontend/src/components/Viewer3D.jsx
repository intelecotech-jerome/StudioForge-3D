import React, { useEffect, useState, useRef, useMemo } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, TransformControls, Grid, Html, Line } from '@react-three/drei';
import * as THREE from 'three';
import { STLLoader } from 'three-stdlib';

/**
 * Loads binary STL from the backend URL and renders it in Three.js
 * Note: Our backend uses Z-up (standard 3D printing coordinate system).
 * We configure the Three.js camera with `up={[0, 0, 1]}` so (X, Y, Z) match the slicer 1:1.
 */
function StlMeshObject({
  stlUrl,
  wireframe,
  opacity,
  colorLayers,
  popoutConfig = null,
  lithoBacklightConfig = null,
  scaleZ = 1.0,
  centerObjectAtOrigin = false,
  onBoundsComputed = null,
}) {
  const [rawGeometry, setRawGeometry] = useState(null);
  const [meshOffset, setMeshOffset] = useState([0, 0, 0]);

  useEffect(() => {
    if (!stlUrl) {
      setRawGeometry(null);
      return;
    }
    let active = true;
    const loader = new STLLoader();
    loader.load(
      stlUrl,
      (geom) => {
        if (!active) return;
        geom.computeVertexNormals();
        geom.computeBoundingBox();
        if (geom.boundingBox) {
          const b = geom.boundingBox;
          const cx = (b.min.x + b.max.x) * 0.5;
          const cy = (b.min.y + b.max.y) * 0.5;
          const cz = (b.min.z + b.max.z) * 0.5;
          const sx = b.max.x - b.min.x;
          const sy = b.max.y - b.min.y;
          const sz = b.max.z - b.min.z;
          setMeshOffset([-cx, -cy, -cz]);
          if (onBoundsComputed) {
            onBoundsComputed({ center: [cx, cy, cz], size: [sx, sy, sz], min: [b.min.x, b.min.y, b.min.z], max: [b.max.x, b.max.y, b.max.z] });
          }
        }
        setRawGeometry(geom);
      },
      undefined,
      (err) => console.error('Erreur chargement STL:', err)
    );
    return () => {
      active = false;
    };
  }, [stlUrl]);

  const geometry = useMemo(() => {
    if (!rawGeometry) return null;
    const geom = rawGeometry.clone();
    geom.computeBoundingBox();
    const bbox = geom.boundingBox;

    if (colorLayers && colorLayers.length > 0) {
      const pos = geom.attributes.position;
      const count = pos.count;
      const colors = new Float32Array(count * 3);

      const classifyFam = (c, idx, total) => {
        if (idx === 0) return 'dark';
        const r = c.r * 255;
        const g = c.g * 255;
        const b = c.b * 255;
        const mx = Math.max(1, r, g, b);
        const mn = Math.min(r, g, b);
        const span = mx - mn;
        const sat = span / mx;
        if (idx === total - 1 && mx > 215 && span < 45) return 'white';
        if (sat < 0.14) return 'silver';
        let hue = 0;
        if (span > 1e-3) {
          if (mx === r) hue = ((60 * ((g - b) / span)) + 360) % 360;
          else if (mx === g) hue = 60 * ((b - r) / span) + 120;
          else hue = 60 * ((r - g) / span) + 240;
        }
        if (hue < 42 || hue >= 332) return 'warm';
        if (hue >= 42 && hue < 65) return 'gold';
        if (hue >= 65 && hue < 168) return 'green';
        if (hue >= 168 && hue < 252) return 'cool';
        return 'purple';
      };

      // Parse RGB stops sorted by end_mm + optical Transmission Distance (TD)
      const stops = colorLayers.map((layer, idx) => {
        const c = new THREE.Color(layer.hex_color);
        return {
          startZ: Number(layer.start_mm),
          endZ: Number(layer.end_mm),
          tdMm: Number(layer.td_mm || 2.0),
          r: c.r,
          g: c.g,
          b: c.b,
          fam: classifyFam(c, idx, colorLayers.length),
        };
      });

      const famCounts = {};
      stops.forEach((st) => {
        famCounts[st.fam] = (famCounts[st.fam] || 0) + 1;
      });

      const baseStop = stops[0];
      const maxPlateZ = stops[stops.length - 1].endZ;
      const popMode = popoutConfig?.mode || 'none';
      const popColor = popoutConfig?.hexColor ? new THREE.Color(popoutConfig.hexColor) : new THREE.Color('#94a3b8');

      for (let i = 0; i < count; i++) {
        const rawZ = pos.getZ(i);
        if (popMode === 'stl_popout' && rawZ > maxPlateZ + 0.08) {
          colors[i * 3] = popColor.r;
          colors[i * 3 + 1] = popColor.g;
          colors[i * 3 + 2] = popColor.b;
          continue;
        }

        let z = rawZ;
        if (popMode === 'image_puff_3d' && rawZ > maxPlateZ + 0.04) {
          const scaled = rawZ * 20.0;
          const frac = scaled - Math.floor(scaled);
          const normHf = Math.min(1.0, Math.max(0.0, (frac - 0.05) / 0.90));
          z = baseStop.endZ + normHf * Math.max(0.08, maxPlateZ - baseStop.endZ);
        }

        let r = baseStop.r;
        let g = baseStop.g;
        let b = baseStop.b;

        for (let s = 1; s < stops.length; s++) {
          const prev = stops[s - 1];
          const curr = stops[s];
          if (z > prev.endZ) {
            const span = Math.max(0.04, curr.endZ - prev.endZ);
            const normT = Math.min(1.0, Math.max(0.0, (z - prev.endZ) / span));
            if (
              prev.fam !== 'dark' &&
              prev.fam !== 'white' &&
              curr.fam !== 'dark' &&
              curr.fam !== 'white' &&
              curr.fam !== prev.fam
            ) {
              const blend = Math.min(1.0, normT / 0.42);
              const shadeT = Math.min(1.0, Math.max(0.0, (normT - 0.42) / 0.58));
              const darkMix = (curr.fam === 'warm' && (famCounts.warm || 1) >= 3) ? 0.76 : 0.38;
              const sr = darkMix * baseStop.r + (1.0 - darkMix) * curr.r;
              const sg = darkMix * baseStop.g + (1.0 - darkMix) * curr.g;
              const sb = darkMix * baseStop.b + (1.0 - darkMix) * curr.b;
              const tr = sr * (1.0 - shadeT) + curr.r * shadeT;
              const tg = sg * (1.0 - shadeT) + curr.g * shadeT;
              const tb = sb * (1.0 - shadeT) + curr.b * shadeT;
              r = r * (1.0 - blend) + tr * blend;
              g = g * (1.0 - blend) + tg * blend;
              b = b * (1.0 - blend) + tb * blend;
            } else {
              const tdScale = Math.max(0.2, curr.tdMm);
              const exponent = Math.max(0.35, Math.min(1.5, 1.0 / (tdScale * 0.58)));
              const blend = Math.pow(normT, exponent);
              r = r * (1.0 - blend) + curr.r * blend;
              g = g * (1.0 - blend) + curr.g * blend;
              b = b * (1.0 - blend) + curr.b * blend;
            }
          }
        }

        colors[i * 3] = r;
        colors[i * 3 + 1] = g;
        colors[i * 3 + 2] = b;
      }

      geom.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    } else if (lithoBacklightConfig && lithoBacklightConfig.ledTint !== 'plastic_off') {
      const pos = geom.attributes.position;
      const count = pos.count;
      const colors = new Float32Array(count * 3);

      const tMin = Number(lithoBacklightConfig.minThicknessMm || 0.8);
      const tMax = Number(lithoBacklightConfig.maxThicknessMm || 3.2);
      const tdVal = Number(lithoBacklightConfig.tdMm || 2.8);
      const shapeMode = lithoBacklightConfig.shapeMode || 'flat_plate';
      const standVertical = Boolean(lithoBacklightConfig.standVertical);

      const tintMap = {
        warm_3000k: { bright: [1.0, 0.955, 0.835], dark: [0.09, 0.06, 0.04] },
        neutral_5500k: { bright: [0.99, 0.995, 1.0], dark: [0.07, 0.085, 0.11] },
        candle_2200k: { bright: [1.0, 0.775, 0.45], dark: [0.12, 0.045, 0.02] },
        cyan_cyber: { bright: [0.72, 0.98, 1.0], dark: [0.03, 0.08, 0.14] },
        red_crimson: { bright: [1.0, 0.28, 0.28], dark: [0.14, 0.02, 0.02] },
        orange_sunset: { bright: [1.0, 0.58, 0.20], dark: [0.14, 0.04, 0.01] },
        gold_amber: { bright: [1.0, 0.88, 0.28], dark: [0.12, 0.08, 0.02] },
        emerald_green: { bright: [0.35, 1.0, 0.55], dark: [0.02, 0.11, 0.04] },
        royal_blue: { bright: [0.38, 0.65, 1.0], dark: [0.02, 0.05, 0.15] },
        violet_purple: { bright: [0.78, 0.42, 1.0], dark: [0.08, 0.02, 0.14] },
        magenta_pink: { bright: [1.0, 0.42, 0.82], dark: [0.13, 0.02, 0.09] },
      };

      let tint = tintMap[lithoBacklightConfig.ledTint] || tintMap.warm_3000k;
      if (lithoBacklightConfig.customColorHex) {
        const c = new THREE.Color(lithoBacklightConfig.customColorHex);
        tint = {
          bright: [Math.min(1.0, c.r * 1.08 + 0.12), Math.min(1.0, c.g * 1.08 + 0.12), Math.min(1.0, c.b * 1.08 + 0.12)],
          dark: [c.r * 0.11, c.g * 0.11, c.b * 0.11],
        };
      }

      const atten = 2.6 / Math.max(0.8, (tMax - tMin) * (tdVal / 2.6));

      const zMin = bbox ? bbox.min.z : 0;
      const zMax = bbox ? bbox.max.z : 100;
      const yMin = bbox ? bbox.min.y : -50;
      const yMax = bbox ? bbox.max.y : 50;
      const xMax = bbox ? bbox.max.x : 50;

      // Pre-scan inner radius for cylinders, spheres, and cubes
      let rMinCyl = 25.0;
      let sphereCenterZ = (zMin + zMax) * 0.5;
      let sphereInnerR = 45.0;
      let sphereOuterMaxR = 70.0;
      let standCutoffZ = zMin + 12.0;

      if (['cylinder_lamp', 'polygon_lantern', 'cone_lampshade', 'vase_lumina'].includes(shapeMode)) {
        let minR = 1e9;
        const midZ = (zMin + zMax) * 0.55;
        for (let i = 0; i < count; i++) {
          const z = pos.getZ(i);
          if (z > midZ - 15 && z < midZ + 15) {
            const r = Math.hypot(pos.getX(i), pos.getY(i));
            if (r > 10.0 && r < minR) minR = r;
          }
        }
        if (minR < 1e8) rMinCyl = minR;
      } else if (shapeMode === 'sphere_globe') {
        const cfgDiameter = Number(lithoBacklightConfig.sphereDiameterMm || 140.0);
        const exactRIn = Math.max(20.0, cfgDiameter * 0.5 - tMax);

        // In build_sphere_globe_lithophane_mesh, the North Pole inner vertex is at (x=0, y=0, z = sphere_center_z + r_in)
        // and the North Pole outer vertex is at (x=0, y=0, z = sphere_center_z + r_in + t_pole).
        // Scanning vertices at (x=0, y=0) near zMax gives us z_north_in with 0.000mm error regardless of the stand!
        let zNorthIn = 1e9;
        let foundNorthPole = false;
        for (let i = 0; i < count; i++) {
          const z = pos.getZ(i);
          if (z > zMax - tMax - 4.0) {
            const rxy = Math.hypot(pos.getX(i), pos.getY(i));
            if (rxy < 0.08) {
              if (z < zNorthIn) zNorthIn = z;
              foundNorthPole = true;
            }
          }
        }

        if (foundNorthPole && zNorthIn < 1e8) {
          sphereInnerR = exactRIn;
          sphereCenterZ = zNorthIn - sphereInnerR;
          sphereOuterMaxR = sphereInnerR + tMax + 0.35;
        } else {
          // Fallback for imported external STL globes
          sphereInnerR = exactRIn;
          sphereCenterZ = zMax - cfgDiameter * 0.5;
          sphereOuterMaxR = sphereInnerR + tMax + 0.5;
        }
        standCutoffZ = Math.max(zMin + 8.0, sphereCenterZ - sphereInnerR * 0.82);
      }

      for (let i = 0; i < count; i++) {
        const x = pos.getX(i);
        const y = pos.getY(i);
        const z = pos.getZ(i);

        let localT = tMax;
        let isStructuralFrame = false;

        if (shapeMode === 'flat_plate' || shapeMode === 'stencil_cutout') {
          localT = standVertical ? Math.abs(y - yMin) : z - zMin;
          if (localT < 0.05) localT = tMax * 0.85;
          if (standVertical && z < zMin + 3.4 && Math.abs(y) > tMax * 1.3) {
            isStructuralFrame = true;
          }
        } else if (['cylinder_lamp', 'polygon_lantern', 'cone_lampshade', 'vase_lumina'].includes(shapeMode)) {
          if (z < zMin + 10.5 && Math.hypot(x, y) < rMinCyl - 1.5) {
            isStructuralFrame = true;
          } else {
            const r = Math.hypot(x, y);
            localT = Math.max(tMin, Math.min(tMax, r - rMinCyl));
          }
        } else if (shapeMode === 'sphere_globe') {
          const cfgDiameter = Number(lithoBacklightConfig.sphereDiameterMm || 140.0);
          const isStandOnly = (zMax - zMin) < cfgDiameter * 0.78;
          const r = Math.hypot(x, y, z - sphereCenterZ);
          // Any vertex below standCutoffZ OR in the lower half whose radius lies outside the sphere's shell
          // (such as the Rocky Lunar base or Wavy stand arms!) is shaded as structural stand.
          const isOutsideSphereShell =
            z < sphereCenterZ + 5.0 && (r < sphereInnerR - 0.35 || r > sphereOuterMaxR + 0.35);
          if (isStandOnly || z < standCutoffZ || isOutsideSphereShell) {
            isStructuralFrame = true;
          } else {
            localT = Math.max(tMin, r - sphereInnerR);
          }
        } else if (shapeMode === 'framed_lightbox') {
          // If standing assembly (zMax > 30), front face is near yMin
          if (zMax - zMin > 25.0) {
            if (y < yMin + tMax + 1.8) {
              localT = Math.max(tMin, (yMin + tMax) - y);
            } else {
              isStructuralFrame = true;
            }
          } else {
            localT = z - zMin;
          }
        } else if (shapeMode === 'cube_lightbox') {
          // If 3D assembled cube (zMax - zMin > 25), the 4 outer faces are near |x| ~ xMax or |y| ~ yMax
          if (zMax - zMin > 25.0) {
            const maxAbsXY = Math.max(Math.abs(x), Math.abs(y));
            const outerHalf = xMax;
            const innerHalf = outerHalf - tMax;
            const cornerSpan = Math.min(Math.abs(x), Math.abs(y));
            if (z < zMin + 6.0 || z > zMax - 5.0 || cornerSpan > outerHalf - 7.5 || maxAbsXY < innerHalf - 0.8) {
              isStructuralFrame = true;
            } else {
              localT = Math.max(tMin, maxAbsXY - innerHalf);
            }
          } else {
            localT = z - zMin;
          }
        } else {
          // Curved arc / half cylinder
          localT = tMin + (tMax - tMin) * 0.42;
        }

        if (isStructuralFrame) {
          // Dark structural base / frame with subtle LED reflection
          colors[i * 3] = 0.11 + tint.dark[0] * 0.35;
          colors[i * 3 + 1] = 0.13 + tint.dark[1] * 0.35;
          colors[i * 3 + 2] = 0.17 + tint.dark[2] * 0.35;
        } else {
          const trans = Math.min(1.0, Math.max(0.0, Math.exp(-atten * Math.max(0.0, localT - tMin))));
          colors[i * 3] = tint.dark[0] + trans * (tint.bright[0] - tint.dark[0]);
          colors[i * 3 + 1] = tint.dark[1] + trans * (tint.bright[1] - tint.dark[1]);
          colors[i * 3 + 2] = tint.dark[2] + trans * (tint.bright[2] - tint.dark[2]);
        }
      }

      geom.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    }

    return geom;
  }, [rawGeometry, colorLayers, popoutConfig, lithoBacklightConfig]);

  if (!geometry) return null;

  const hasLithoBacklight = Boolean(
    lithoBacklightConfig && lithoBacklightConfig.ledTint !== 'plastic_off'
  );
  const hasVertexColors = Boolean((colorLayers && colorLayers.length > 0) || hasLithoBacklight);
  const isLithoPlastic = Boolean(
    lithoBacklightConfig && lithoBacklightConfig.ledTint === 'plastic_off'
  );

  const posOffset = centerObjectAtOrigin
    ? [meshOffset[0], meshOffset[1], meshOffset[2] * scaleZ]
    : [0, 0, 0];

  return (
    <mesh
      geometry={geometry}
      position={posOffset}
      scale={[1, 1, scaleZ]}
      castShadow
      receiveShadow
    >
      <meshStandardMaterial
        key={hasVertexColors ? 'vc-on' : isLithoPlastic ? 'litho-white' : 'vc-off'}
        vertexColors={hasVertexColors}
        color={hasVertexColors ? '#ffffff' : isLithoPlastic ? '#f1f5f9' : '#64748b'}
        roughness={hasVertexColors ? 0.45 : isLithoPlastic ? 0.42 : 0.35}
        metalness={hasVertexColors ? 0.05 : isLithoPlastic ? 0.05 : 0.25}
        wireframe={wireframe}
        transparent={!hasVertexColors && opacity < 1.0}
        opacity={hasVertexColors ? 1.0 : opacity}
      />
    </mesh>
  );
}

/**
 * Visualizes the Printer Build Volume (e.g. Creality K1 Max 300x300x300 mm)
 */
function PrinterVolumeBox({ bedSize }) {
  const [bx, by, bz] = bedSize;
  return (
    <group position={[0, 0, bz / 2]}>
      <mesh>
        <boxGeometry args={[bx, by, bz]} />
        <meshBasicMaterial color="#00f0ff" wireframe transparent opacity={0.18} />
      </mesh>
      <Html position={[-bx / 2 + 10, -by / 2 + 10, -bz / 2 + 6]} center={false}>
        <div className="hud-tag cyan">
          Plateau {bx}×{by}×{bz} mm
        </div>
      </Html>
    </group>
  );
}

/**
 * Interactive 3D Cosplay Reinforcement Rod Preview (Point A -> Point B)
 * Manipulable via Two TransformControls handles (Handle A & Handle B) to adjust angle on curved blades.
 */
function CosplayRodPreview({
  pointA,
  pointB,
  onChangePointA,
  onChangePointB,
  profileType,
  width,
  thickness,
  clearance,
  twistAngleDeg,
  activeHandle,
  setActiveHandle,
  orbitRef,
}) {
  const handleARef = useRef();
  const handleBRef = useRef();

  const { position, quaternion, length, cutW, cutT } = useMemo(() => {
    const vA = new THREE.Vector3(...pointA);
    const vB = new THREE.Vector3(...pointB);
    const dir = new THREE.Vector3().subVectors(vB, vA);
    const len = Math.max(1.0, dir.length());
    const mid = new THREE.Vector3().addVectors(vA, vB).multiplyScalar(0.5);

    const q = new THREE.Quaternion();
    const up = new THREE.Vector3(0, 1, 0); // Three.js cylinder/box default height axis is Y
    if (len > 1e-4) {
      q.setFromUnitVectors(up, dir.clone().normalize());
    }
    if (Math.abs(twistAngleDeg) > 0.01) {
      const qTwist = new THREE.Quaternion().setFromAxisAngle(
        new THREE.Vector3(0, 1, 0),
        THREE.MathUtils.degToRad(twistAngleDeg)
      );
      q.multiply(qTwist);
    }

    const w = Number(width) + Number(clearance);
    const t = (profileType === 'flat' ? Number(thickness) : Number(width)) + Number(clearance);

    return { position: mid, quaternion: q, length: len, cutW: w, cutT: t };
  }, [pointA, pointB, profileType, width, thickness, clearance, twistAngleDeg]);

  return (
    <group>
      {/* Semi-transparent Red/Cyan Internal Reinforcement Tube */}
      <mesh position={position} quaternion={quaternion}>
        {profileType === 'round' ? (
          <cylinderGeometry args={[cutW / 2, cutW / 2, length, 32]} />
        ) : (
          <boxGeometry args={[cutW, length, cutT]} />
        )}
        <meshStandardMaterial
          color="#ff2a6d"
          emissive="#ff2a6d"
          emissiveIntensity={0.45}
          transparent
          opacity={0.62}
          depthTest={false}
        />
      </mesh>

      {/* Center axis line */}
      <Line points={[pointA, pointB]} color="#00f0ff" lineWidth={2} dashed={false} />

      {/* Endpoint Sphere A */}
      <mesh
        ref={handleARef}
        position={pointA}
        onClick={(e) => {
          e.stopPropagation();
          setActiveHandle(activeHandle === 'A' ? null : 'A');
        }}
      >
        <sphereGeometry args={[6, 20, 20]} />
        <meshBasicMaterial color={activeHandle === 'A' ? '#00f0ff' : '#ff2a6d'} depthTest={false} />
        <Html position={[10, 0, 0]}>
          <div className="hud-tag pink" onClick={() => setActiveHandle('A')}>
            A ({Math.round(pointA[2])}mm)
          </div>
        </Html>
      </mesh>

      {/* Endpoint Sphere B */}
      <mesh
        ref={handleBRef}
        position={pointB}
        onClick={(e) => {
          e.stopPropagation();
          setActiveHandle(activeHandle === 'B' ? null : 'B');
        }}
      >
        <sphereGeometry args={[6, 20, 20]} />
        <meshBasicMaterial color={activeHandle === 'B' ? '#00f0ff' : '#ff2a6d'} depthTest={false} />
        <Html position={[10, 0, 0]}>
          <div className="hud-tag pink" onClick={() => setActiveHandle('B')}>
            B ({Math.round(pointB[2])}mm)
          </div>
        </Html>
      </mesh>

      {/* TransformControls Gizmo for Point A */}
      {activeHandle === 'A' && handleARef.current && (
        <TransformControls
          object={handleARef.current}
          mode="translate"
          onMouseDown={() => {
            if (orbitRef.current) orbitRef.current.enabled = false;
          }}
          onMouseUp={() => {
            if (orbitRef.current) orbitRef.current.enabled = true;
            if (handleARef.current) {
              const p = handleARef.current.position;
              onChangePointA([
                Number(p.x.toFixed(1)),
                Number(p.y.toFixed(1)),
                Number(p.z.toFixed(1)),
              ]);
            }
          }}
        />
      )}

      {/* TransformControls Gizmo for Point B */}
      {activeHandle === 'B' && handleBRef.current && (
        <TransformControls
          object={handleBRef.current}
          mode="translate"
          onMouseDown={() => {
            if (orbitRef.current) orbitRef.current.enabled = false;
          }}
          onMouseUp={() => {
            if (orbitRef.current) orbitRef.current.enabled = true;
            if (handleBRef.current) {
              const p = handleBRef.current.position;
              onChangePointB([
                Number(p.x.toFixed(1)),
                Number(p.y.toFixed(1)),
                Number(p.z.toFixed(1)),
              ]);
            }
          }}
        />
      )}
    </group>
  );
}

/**
 * Visualizes Horizontal Auto-Grid Cut Planes (Mode A) or Localized Bounded Figurine Cut (Mode B)
 */
function CutPlanesPreview({
  cutMode = 'auto_grid',
  cutPlanesZ = [],
  bedSize = [300, 300, 300],
  boundedOrigin = [0, 0, 0],
  boundedSize = [80, 80, 80],
  boundedType = 'cylinder',
}) {
  const [bx, by] = bedSize || [300, 300, 300];
  const safePlanes = Array.isArray(cutPlanesZ) ? cutPlanesZ : [];

  if (cutMode === 'bounded_figurine') {
    const [ox, oy, oz] = boundedOrigin || [0, 0, 0];
    const [sx, sy, sz] = boundedSize || [80, 80, 80];
    return (
      <group position={[ox, oy, oz]}>
        {boundedType === 'cylinder' ? (
          <mesh rotation={[Math.PI / 2, 0, 0]}>
            <cylinderGeometry args={[sx / 2, sx / 2, sz, 32]} />
            <meshBasicMaterial color="#00f0ff" wireframe transparent opacity={0.45} />
          </mesh>
        ) : (
          <mesh>
            <boxGeometry args={[sx, sy, sz]} />
            <meshBasicMaterial color="#00f0ff" wireframe transparent opacity={0.45} />
          </mesh>
        )}
        <mesh>
          <planeGeometry args={[sx * 1.1, sy * 1.1]} />
          <meshBasicMaterial
            color="#ff2a6d"
            transparent
            opacity={0.35}
            side={THREE.DoubleSide}
          />
        </mesh>
      </group>
    );
  }

  return (
    <group>
      {safePlanes.map((zVal, idx) => (
        <group key={idx} position={[0, 0, zVal]}>
          <mesh>
            <planeGeometry args={[bx * 0.9, by * 0.9]} />
            <meshBasicMaterial
              color="#00f0ff"
              transparent
              opacity={0.22}
              side={THREE.DoubleSide}
            />
          </mesh>
          <Html position={[-bx * 0.45, 0, 0]}>
            <div className="hud-tag cyan">
              Coupe #{idx + 1} (Z = {zVal} mm)
            </div>
          </Html>
        </group>
      ))}
    </group>
  );
}

export default function Viewer3D({
  stlUrl,
  modelStats,
  bedSize = [300, 300, 300],
  showRod = false,
  pointA = null,
  pointB = null,
  onChangePointA = () => {},
  onChangePointB = () => {},
  rodConfig = {},
  cutMode = 'auto_grid',
  cutPlanesZ = [],
  boundedOrigin = [0, 0, 0],
  boundedSize = [80, 80, 80],
  boundedType = 'cylinder',
  colorLayers = null,
  popoutConfig = null,
  lithoBacklightConfig = null,
  scaleZ = 1.0,
}) {
  const orbitRef = useRef();
  const isObjectStudioMode = Boolean(lithoBacklightConfig || colorLayers);
  const [wireframe, setWireframe] = useState(false);
  const [xrayOpacity, setXrayOpacity] = useState(isObjectStudioMode ? 1.0 : 0.72);
  const [activeHandle, setActiveHandle] = useState(null);
  const [lockObjectCenter, setLockObjectCenter] = useState(true);
  const [showPrinterCage, setShowPrinterCage] = useState(!isObjectStudioMode);
  const [loadedBounds, setLoadedBounds] = useState(null);

  const handleRecenterCamera = (bounds = loadedBounds) => {
    if (!orbitRef.current) return;
    const ctrl = orbitRef.current;
    const cam = ctrl.object;
    const useOrigin = lockObjectCenter && !showRod;
    const targetVec = useOrigin
      ? new THREE.Vector3(0, 0, 0)
      : bounds
      ? new THREE.Vector3(bounds.center[0], bounds.center[1], bounds.center[2] * scaleZ)
      : new THREE.Vector3(0, 0, 120);

    ctrl.target.copy(targetVec);
    if (bounds && cam) {
      const maxDim = Math.max(40, bounds.size[0], bounds.size[1], bounds.size[2] * scaleZ);
      const dist = maxDim * 1.95;
      cam.position.set(
        targetVec.x + dist * 0.72,
        targetVec.y - dist * 0.88,
        targetVec.z + dist * 0.52
      );
      cam.updateProjectionMatrix();
    }
    ctrl.update();
  };

  const handleBoundsComputed = (b) => {
    setLoadedBounds(b);
    setTimeout(() => {
      handleRecenterCamera(b);
    }, 30);
  };

  return (
    <div className="viewer-container">
      {/* Top Floating Viewport Toolbar */}
      <div className="viewer-toolbar">
        <div className="viewer-badge">
          <span className="dot-live" /> MOTEUR CSG : MANIFOLD3D + TRIMESH
        </div>
        <div className="viewer-controls-row">
          <button
            className={`btn-hud ${lockObjectCenter ? 'active' : ''}`}
            onClick={() => {
              const next = !lockObjectCenter;
              setLockObjectCenter(next);
              setTimeout(() => handleRecenterCamera(loadedBounds), 20);
            }}
            title="Garde l'objet verrouillé au milieu de l'écran : rotation 360° dans tous les sens + zoom molette sans que la boîte ne se déplace"
          >
            🎯 Objet Fixe au Centre
          </button>
          <button
            className="btn-hud"
            onClick={() => handleRecenterCamera(loadedBounds)}
            title="Recentrer immédiatement la caméra sur l'objet"
          >
            🔄 Recentrer
          </button>
          <button
            className={`btn-hud ${showPrinterCage ? 'active' : ''}`}
            onClick={() => setShowPrinterCage(!showPrinterCage)}
            title="Afficher ou masquer la boîte et la grille du plateau d'imprimante"
          >
            📦 Plateau Imprimante
          </button>
          {!isObjectStudioMode && (
            <button
              className={`btn-hud ${xrayOpacity < 1 ? 'active' : ''}`}
              onClick={() => setXrayOpacity(xrayOpacity < 1 ? 1.0 : 0.68)}
            >
              Vue Rayons-X
            </button>
          )}
          <button
            className={`btn-hud ${wireframe ? 'active' : ''}`}
            onClick={() => setWireframe(!wireframe)}
          >
            Maillage Filaire
          </button>
          {showRod && (
            <>
              <button
                className={`btn-hud ${activeHandle === 'A' ? 'active-pink' : ''}`}
                onClick={() => setActiveHandle(activeHandle === 'A' ? null : 'A')}
              >
                Gizmo Point A
              </button>
              <button
                className={`btn-hud ${activeHandle === 'B' ? 'active-pink' : ''}`}
                onClick={() => setActiveHandle(activeHandle === 'B' ? null : 'B')}
              >
                Gizmo Point B
              </button>
            </>
          )}
        </div>
      </div>

      {/* Model Dimensions HUD Overlay */}
      {modelStats && modelStats.extents && (
        <div className="viewer-stats-overlay">
          <div>
            <strong>DIMENSIONS (X×Y×Z) :</strong> {modelStats.extents[0]} × {modelStats.extents[1]} ×{' '}
            <span className={modelStats.extents[2] > (bedSize?.[2] || 300) ? 'text-warn' : 'text-cyan'}>
              {modelStats.extents[2]} mm
            </span>
          </div>
          <div>
            <strong>TOPOLOGIE :</strong>{' '}
            {modelStats.is_watertight ? (
              <span className="text-cyan">Manifold Watertight ✓</span>
            ) : (
              <span className="text-warn">Non-Manifold (Réparé: {modelStats.repair_method})</span>
            )}{' '}
            | {(modelStats.faces_count ?? modelStats.faces ?? 0).toLocaleString()} triangles
          </div>
        </div>
      )}

      <Canvas
        shadows
        camera={{ position: [240, -280, 190], up: [0, 0, 1], fov: 40, near: 1, far: 5000 }}
        onPointerMissed={() => setActiveHandle(null)}
      >
        <color attach="background" args={['#07090e']} />
        <ambientLight intensity={0.72} />
        <directionalLight position={[300, -300, 500]} intensity={1.15} castShadow />
        <directionalLight position={[-300, 300, -200]} intensity={0.55} color="#e2e8f0" />
        <directionalLight position={[0, 300, 250]} intensity={0.45} color="#00f0ff" />

        <OrbitControls
          ref={orbitRef}
          makeDefault
          target={lockObjectCenter && !showRod ? [0, 0, 0] : [0, 0, 120]}
          enablePan={!lockObjectCenter}
          enableDamping={true}
          dampingFactor={0.08}
          minDistance={15}
          maxDistance={2200}
        />

        {/* Build plate floor grid & Printer Build Volume Box (only shown when showPrinterCage is true) */}
        {showPrinterCage && (
          <>
            <Grid
              rotation={[Math.PI / 2, 0, 0]}
              position={
                lockObjectCenter && !showRod && loadedBounds
                  ? [0, 0, -loadedBounds.size[2] * 0.5 * scaleZ]
                  : [0, 0, 0]
              }
              args={[600, 600]}
              cellSize={20}
              cellThickness={0.6}
              cellColor="#1e293b"
              sectionSize={100}
              sectionThickness={1.2}
              sectionColor="#00f0ff"
              fadeDistance={1500}
            />
            <group
              position={
                lockObjectCenter && !showRod && loadedBounds
                  ? [0, 0, -loadedBounds.size[2] * 0.5 * scaleZ]
                  : [0, 0, 0]
              }
            >
              <PrinterVolumeBox bedSize={bedSize} />
            </group>
          </>
        )}

        {/* 3D STL Mesh (centered at [0,0,0] when lockObjectCenter is active) */}
        <StlMeshObject
          stlUrl={stlUrl}
          wireframe={wireframe}
          opacity={xrayOpacity}
          colorLayers={colorLayers}
          popoutConfig={popoutConfig}
          lithoBacklightConfig={lithoBacklightConfig}
          scaleZ={scaleZ}
          centerObjectAtOrigin={lockObjectCenter && !showRod}
          onBoundsComputed={handleBoundsComputed}
        />

        {/* Semi-transparent Red/Cyan Cosplay Reinforcement Rod + TransformControls */}
        {showRod && pointA && pointB && (
          <CosplayRodPreview
            pointA={pointA}
            pointB={pointB}
            onChangePointA={onChangePointA}
            onChangePointB={onChangePointB}
            profileType={rodConfig.profileType}
            width={rodConfig.width}
            thickness={rodConfig.thickness}
            clearance={rodConfig.clearance}
            twistAngleDeg={rodConfig.twistAngleDeg}
            activeHandle={activeHandle}
            setActiveHandle={setActiveHandle}
            orbitRef={orbitRef}
          />
        )}

        {/* Cut Planes / Bounded Figurine Box Preview */}
        {!isObjectStudioMode && (
          <CutPlanesPreview
            cutMode={cutMode}
            cutPlanesZ={cutPlanesZ}
            bedSize={bedSize}
            boundedOrigin={boundedOrigin}
            boundedSize={boundedSize}
            boundedType={boundedType}
          />
        )}
      </Canvas>
    </div>
  );
}

