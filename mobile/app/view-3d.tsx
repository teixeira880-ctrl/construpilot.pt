/**
 * Écran Vue 3D — rendu interactif d'un escalier calculé via @react-three/fiber.
 *
 * Compatibilité :
 *  - Web preview : import direct depuis '@react-three/fiber' (WebGL DOM canvas).
 *  - Native (Expo Go / build) : import depuis '@react-three/fiber/native' + expo-gl.
 *    Chargé dynamiquement pour éviter les erreurs de bundling web.
 */
/* eslint-disable react/no-unknown-property, @typescript-eslint/no-require-imports */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  View, Text, StyleSheet, ActivityIndicator, TouchableOpacity, Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, Stack } from 'expo-router';
import { colors, radius, spacing, typography } from '../src/theme';
import { getProject } from '../src/storage';
import type { StoredProject, StairResult, StairType } from '../src/types';

// Import "web" par défaut ; sur natif on utilise 'react-three/fiber/native' dynamiquement.
const R3F: any = Platform.OS === 'web'
  ? require('@react-three/fiber')
  : require('@react-three/fiber/native');
const Canvas = R3F.Canvas;
const useFrame = R3F.useFrame;

type MaterialKey = 'brut' | 'lisse' | 'peint';
const MATERIALS: Record<MaterialKey, { color: string; label: string }> = {
  brut:  { color: '#7A7A7A', label: 'Béton brut' },
  lisse: { color: '#A8A8A8', label: 'Béton lissé' },
  peint: { color: '#E8E4DC', label: 'Béton peint' },
};

export default function View3DScreen() {
  const params = useLocalSearchParams<{ projectId: string }>();
  const [project, setProject] = useState<StoredProject | null>(null);
  const [loading, setLoading] = useState(true);
  const [material, setMaterial] = useState<MaterialKey>('lisse');
  const [resetKey, setResetKey] = useState(0);

  useEffect(() => {
    (async () => {
      if (params.projectId) {
        const p = await getProject(params.projectId);
        setProject(p);
      }
      setLoading(false);
    })();
  }, [params.projectId]);

  if (loading) {
    return (
      <SafeAreaView style={styles.center}>
        <ActivityIndicator />
      </SafeAreaView>
    );
  }
  if (!project || !project.result) {
    return (
      <SafeAreaView style={styles.center}>
        <Text style={{ color: colors.text }}>Projet introuvable.</Text>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView edges={['bottom']} style={styles.container} testID="view-3d-screen">
      <Stack.Screen options={{
        title: 'Vue 3D',
        headerRight: () => (
          <TouchableOpacity onPress={() => setResetKey(k => k + 1)} testID="reset-camera-btn">
            <Text style={styles.headerAction}>Reset</Text>
          </TouchableOpacity>
        ),
      }} />

      <View style={styles.canvasWrap}>
        <Canvas
          key={resetKey}
          camera={{ position: [4, 3.5, 4], fov: 45 }}
          style={{ width: '100%', height: '100%' }}
        >
          <ambientLight intensity={0.6} />
          <directionalLight position={[5, 8, 3]} intensity={0.8} castShadow />
          <directionalLight position={[-5, 4, -3]} intensity={0.25} />
          <StairMesh
            type={project.type}
            result={project.result}
            input={project.input as any}
            color={MATERIALS[material].color}
          />
          <GroundPlane />
          <OrbitControlsFallback />
        </Canvas>
      </View>

      {/* Overlay contrôles */}
      <View style={styles.overlay} testID="view-3d-controls">
        <Text style={styles.overlayLabel}>Matériau</Text>
        <View style={styles.matRow}>
          {(Object.keys(MATERIALS) as MaterialKey[]).map((k) => (
            <TouchableOpacity
              key={k}
              onPress={() => setMaterial(k)}
              style={[styles.matChip, material === k && styles.matChipActive]}
              testID={`material-${k}`}
            >
              <View style={[styles.matSwatch, { backgroundColor: MATERIALS[k].color }]} />
              <Text style={[styles.matChipText, material === k && styles.matChipTextActive]}>
                {MATERIALS[k].label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      <View style={styles.legend}>
        <Text style={styles.legendText}>
          {Platform.OS === 'web'
            ? 'Glisser = rotation · molette = zoom'
            : 'Glisser = rotation · pincer = zoom'}
        </Text>
      </View>
    </SafeAreaView>
  );
}

// ---------------------------------------------------------------------------
// Contrôles orbite : version simple (rotation + zoom) qui marche sur web.
// Sur natif, three/examples/jsm/controls/OrbitControls impose du DOM ; on utilise
// à la place un tracking manuel via useFrame et une rotation lente auto.
// ---------------------------------------------------------------------------
function OrbitControlsFallback() {
  // Sur web on essaie de charger three/examples OrbitControls, sinon rotation auto.
  const [ready, setReady] = useState(false);
  const [OC, setOC] = useState<any>(null);

  useEffect(() => {
    if (Platform.OS !== 'web') return;
    (async () => {
      try {
        const mod = await import('three/examples/jsm/controls/OrbitControls.js');
        setOC(() => mod.OrbitControls);
      } catch {
        setOC(null);
      } finally {
        setReady(true);
      }
    })();
  }, []);

  if (Platform.OS !== 'web' || !ready || !OC) {
    return <AutoRotate />;
  }
  return <OrbitDom OC={OC} />;
}

function OrbitDom({ OC }: { OC: any }) {
  const { camera, gl } = R3F.useThree();
  const ref = useRef<any>(null);
  useEffect(() => {
    if (!camera || !gl || !gl.domElement) return;
    const c = new OC(camera, gl.domElement);
    c.enableDamping = true;
    c.dampingFactor = 0.08;
    c.minDistance = 2;
    c.maxDistance = 20;
    ref.current = c;
    return () => c.dispose();
  }, [camera, gl, OC]);
  useFrame(() => { ref.current?.update(); });
  return null;
}

function AutoRotate() {
  const { camera } = R3F.useThree();
  useFrame((_state: any, delta: number) => {
    if (!camera) return;
    const speed = 0.15;
    const r = Math.hypot(camera.position.x, camera.position.z);
    const a = Math.atan2(camera.position.z, camera.position.x) + speed * delta;
    camera.position.x = r * Math.cos(a);
    camera.position.z = r * Math.sin(a);
    camera.lookAt(0, 1, 0);
  });
  return null;
}

// ---------------------------------------------------------------------------
// Sol pour repère visuel
// ---------------------------------------------------------------------------
function GroundPlane() {
  return (
    <mesh position={[0, -0.01, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
      <planeGeometry args={[20, 20]} />
      <meshStandardMaterial color="#EDEEF1" />
    </mesh>
  );
}

// ---------------------------------------------------------------------------
// Génération du maillage escalier selon le type
// ---------------------------------------------------------------------------
function StairMesh({
  type, result, input, color,
}: { type: StairType; result: StairResult; input: any; color: string }) {
  const material = useMemo(() => (
    <meshStandardMaterial color={color} roughness={0.75} metalness={0.05} />
  ), [color]);

  if (type === 'straight') {
    return <StraightMesh result={result} input={input} material={material} />;
  }
  if (type === 'quarter-turn-bottom' || type === 'quarter-turn-top') {
    return (
      <QuarterTurnMesh
        result={result} input={input} material={material}
        variant={type === 'quarter-turn-bottom' ? 'bottom' : 'top'}
      />
    );
  }
  if (type === 'half-turn') {
    return <HalfTurnMesh result={result} input={input} material={material} />;
  }
  if (type === 'helicoidal') {
    return <HelicoidalMesh result={result} input={input} material={material} />;
  }
  return <StraightMesh result={result} input={input} material={material} />;
}

// mm → m (three.js unit)
const MM = (v: number) => v / 1000;

function StraightMesh({ result, input, material }: any) {
  const n = result.num_steps;
  const g = MM(result.tread_depth_mm);
  const h = MM(result.riser_height_mm);
  const w = MM(input.stair_width_mm || 900);
  const treadTh = MM(input.tread_thickness_mm || 30);
  const cubes: React.ReactNode[] = [];
  for (let i = 0; i < n; i++) {
    const y = i * h;
    // Marche = pavé (largeur, épaisseur, profondeur giron)
    const depth = i < n - 1 ? g : Math.max(g, 0.05);
    cubes.push(
      <mesh key={i} position={[i * g + depth / 2, y + h / 2, 0]} castShadow>
        <boxGeometry args={[depth, h, w]} />
        {material}
      </mesh>
    );
    // Nez de marche (surépaisseur horizontale) si has_risers
    if (i < n - 1) {
      cubes.push(
        <mesh key={`n${i}`} position={[i * g + depth + treadTh / 2, y + h - treadTh / 2, 0]} castShadow>
          <boxGeometry args={[treadTh * 3, treadTh, w]} />
          {material}
        </mesh>
      );
    }
  }
  return <group position={[-((n * g) / 2), 0, 0]}>{cubes}</group>;
}

function QuarterTurnMesh({ result, input, material, variant }: any) {
  const n = result.num_steps;
  const h = MM(result.riser_height_mm);
  const g = MM(result.tread_depth_mm);
  const w = MM(input.stair_width_mm || 900);
  const treads = (result.treads || []) as any[];
  const winders = treads.filter((t) => t.type === 'winder');
  const numWind = winders.length;
  const numStr = Math.max(0, n - numWind - (variant === 'top' ? 1 : 0));

  const cubes: React.ReactNode[] = [];
  let stepIdx = 0;
  const pivot = { x: 0, z: 0 };

  const straightsRun = numStr * g;

  if (variant === 'top') {
    // Volée droite en premier puis tournant
    for (let i = 0; i < numStr; i++) {
      const y = stepIdx * h;
      cubes.push(
        <mesh key={`s${i}`} position={[-straightsRun / 2 + i * g + g / 2, y + h / 2, 0]} castShadow>
          <boxGeometry args={[g, h, w]} />
          {material}
        </mesh>
      );
      stepIdx++;
    }
    // Tournant en haut : winders trapézoïdaux depuis pivot au coin haut-droit
    pivot.x = -straightsRun / 2 + numStr * g;
    for (let i = 0; i < numWind; i++) {
      const a1 = (i * (Math.PI / 2)) / numWind;
      const a2 = ((i + 1) * (Math.PI / 2)) / numWind;
      const midA = (a1 + a2) / 2;
      const y = stepIdx * h;
      // Approx wedge par petit box orienté
      const rMid = w * 0.55;
      cubes.push(
        <mesh
          key={`w${i}`}
          position={[pivot.x + rMid * Math.cos(midA), y + h / 2, pivot.z + rMid * Math.sin(midA)]}
          rotation={[0, -midA, 0]}
          castShadow
        >
          <boxGeometry args={[w * 0.9, h, w * 0.7]} />
          {material}
        </mesh>
      );
      stepIdx++;
    }
  } else {
    // Bottom : winders d'abord depuis pivot bas-gauche puis volée droite
    pivot.x = -straightsRun / 2;
    pivot.z = 0;
    for (let i = 0; i < numWind; i++) {
      const a1 = (i * (Math.PI / 2)) / numWind;
      const a2 = ((i + 1) * (Math.PI / 2)) / numWind;
      const midA = (a1 + a2) / 2 + Math.PI; // départ en bas-gauche
      const y = stepIdx * h;
      const rMid = w * 0.55;
      cubes.push(
        <mesh
          key={`w${i}`}
          position={[pivot.x + rMid * Math.cos(midA), y + h / 2, pivot.z + rMid * Math.sin(midA)]}
          rotation={[0, -midA, 0]}
          castShadow
        >
          <boxGeometry args={[w * 0.9, h, w * 0.7]} />
          {material}
        </mesh>
      );
      stepIdx++;
    }
    for (let i = 0; i < numStr; i++) {
      const y = stepIdx * h;
      cubes.push(
        <mesh key={`s${i}`} position={[-straightsRun / 2 + i * g + g / 2, y + h / 2, 0]} castShadow>
          <boxGeometry args={[g, h, w]} />
          {material}
        </mesh>
      );
      stepIdx++;
    }
  }

  return <group>{cubes}</group>;
}

function HalfTurnMesh({ result, input, material }: any) {
  const n = result.num_steps;
  const h = MM(result.riser_height_mm);
  const g = MM(result.tread_depth_mm);
  const w = MM(input.stair_width_mm || 900);
  const flights = result.steps_per_flight || [Math.floor(n / 2), 0, Math.ceil(n / 2)];
  const nLower = flights[0] || Math.floor(n / 2);
  const nUpper = flights[2] || n - nLower;
  const cubes: React.ReactNode[] = [];
  let stepIdx = 0;
  // Volée basse (bande basse, +x direction)
  for (let i = 0; i < nLower; i++) {
    const y = stepIdx * h;
    cubes.push(
      <mesh key={`l${i}`} position={[i * g + g / 2, y + h / 2, -w / 2]} castShadow>
        <boxGeometry args={[g, h, w]} />
        {material}
      </mesh>
    );
    stepIdx++;
  }
  // Palier 180° (approx : plateforme unique)
  const platformY = stepIdx * h;
  cubes.push(
    <mesh key="palier" position={[nLower * g + w / 2, platformY - h / 4, 0]} castShadow>
      <boxGeometry args={[w, h / 2, 2 * w]} />
      {material}
    </mesh>
  );
  // Volée haute (bande haute, sens inverse)
  for (let i = 0; i < nUpper; i++) {
    const y = (nLower + i + 1) * h;
    const x = nLower * g - i * g;
    cubes.push(
      <mesh key={`u${i}`} position={[x - g / 2, y + h / 2, w / 2]} castShadow>
        <boxGeometry args={[g, h, w]} />
        {material}
      </mesh>
    );
  }
  const cx = (nLower * g) / 2;
  return <group position={[-cx, 0, 0]}>{cubes}</group>;
}

function HelicoidalMesh({ result, input, material }: any) {
  const n = result.num_treads || result.num_steps;
  const h = MM(result.riser_height_mm);
  const inner = MM(input.inner_radius_mm ?? 150);
  const outer = MM(input.outer_radius_mm ?? 750);
  const sweep = ((input.sweep_angle_deg ?? 360) * Math.PI) / 180;
  const anglePer = sweep / n;
  const cubes: React.ReactNode[] = [];
  const dir = input.direction === 'ccw' ? 1 : -1;

  for (let i = 0; i < n; i++) {
    const a = dir * (i * anglePer + anglePer / 2);
    const y = i * h;
    const rMid = (inner + outer) / 2;
    const width = outer - inner;
    cubes.push(
      <mesh
        key={i}
        position={[rMid * Math.cos(a), y + h / 2, rMid * Math.sin(a)]}
        rotation={[0, -a - Math.PI / 2, 0]}
        castShadow
      >
        <boxGeometry args={[width, h, anglePer * rMid]} />
        {material}
      </mesh>
    );
  }
  // Fût central
  cubes.push(
    <mesh key="fut" position={[0, (n * h) / 2, 0]}>
      <cylinderGeometry args={[inner, inner, n * h + h, 24]} />
      {material}
    </mesh>
  );
  return <group>{cubes}</group>;
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  headerAction: { color: colors.primary, fontWeight: '600', paddingHorizontal: spacing.m },
  canvasWrap: { flex: 1, backgroundColor: '#EDEEF1' },
  overlay: {
    position: 'absolute', left: 0, right: 0, bottom: 40,
    padding: spacing.m,
    marginHorizontal: spacing.l,
    borderRadius: radius.m,
    backgroundColor: 'rgba(255,255,255,0.95)',
    borderWidth: 1, borderColor: colors.border,
  },
  overlayLabel: { ...typography.caption, color: colors.textMuted, marginBottom: spacing.xs, textTransform: 'uppercase' },
  matRow: { flexDirection: 'row', gap: spacing.s as any, flexWrap: 'wrap' },
  matChip: {
    flexDirection: 'row', alignItems: 'center',
    borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.s, paddingHorizontal: spacing.s, paddingVertical: spacing.xs,
  },
  matChipActive: { borderColor: colors.primary, backgroundColor: colors.primaryBg },
  matSwatch: { width: 16, height: 16, borderRadius: 4, marginRight: 6, borderWidth: 1, borderColor: '#00000010' },
  matChipText: { ...typography.small, color: colors.textMuted },
  matChipTextActive: { color: colors.primary, fontWeight: '700' },
  legend: {
    position: 'absolute', top: 8, alignSelf: 'center',
    backgroundColor: 'rgba(255,255,255,0.85)',
    paddingHorizontal: spacing.m, paddingVertical: 4, borderRadius: radius.m,
  },
  legendText: { ...typography.small, color: colors.textMuted },
});
