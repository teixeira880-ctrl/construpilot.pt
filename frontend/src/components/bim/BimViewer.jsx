// Visualizador 3D do BIM Studio (three.js, já usado na plataforma).
// A geometria é gerada no servidor pelo IfcOpenShell e servida em blocos privados (autenticados);
// o ficheiro IFC original nunca é exposto ao navegador. Carregamento progressivo bloco a bloco.
import { useEffect, useImperativeHandle, useRef, useState, forwardRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { api } from "@/lib/api";
import { CATEGORY_COLORS, boundsOf, distance, isValidMesh, isVisible } from "./bimGeometry";

const SELECT = new THREE.Color(0x2f7a55);
const HILITE = new THREE.Color(0xc4733f);

const BimViewer = forwardRef(function BimViewer(
  { modelId, version, chunks, meta, filters, selectedGid, highlighted, onSelect, measuring, onMeasure }, ref) {
  const mountRef = useRef(null);
  const st = useRef({ meshes: new Map(), positions: [] });
  const [progress, setProgress] = useState({ loaded: 0, total: chunks || 0 });
  const [glError, setGlError] = useState(false);
  const [loadError, setLoadError] = useState(null);
  const filtersRef = useRef(filters);
  const measureRef = useRef({ active: measuring, points: [] });
  const cbRef = useRef({ onSelect, onMeasure });
  cbRef.current = { onSelect, onMeasure };
  filtersRef.current = filters;
  measureRef.current.active = measuring;

  useImperativeHandle(ref, () => ({
    fit: () => fit(),
    focus: (gid) => {
      const m = st.current.meshes.get(gid);
      if (!m) return;
      const box = new THREE.Box3().setFromObject(m);
      frame(box);
    },
  }));

  const frame = (box) => {
    const s = st.current;
    if (!s.camera || box.isEmpty()) return;
    const c = box.getCenter(new THREE.Vector3());
    const size = Math.max(...box.getSize(new THREE.Vector3()).toArray(), 1);
    s.camera.position.copy(c.clone().add(new THREE.Vector3(size * 1.1, size * 0.9, size * 1.3)));
    s.camera.near = size / 500;
    s.camera.far = size * 50;
    s.camera.updateProjectionMatrix();
    s.controls.target.copy(c);
    s.controls.update();
  };

  const fit = () => {
    const s = st.current;
    if (!s.root) return;
    const box = new THREE.Box3();
    s.meshes.forEach((m) => { if (m.visible) box.expandByObject(m); });
    if (box.isEmpty()) box.setFromObject(s.root);
    frame(box);
  };

  // Cena + carregamento
  useEffect(() => {
    const mount = mountRef.current;
    if (!mount || !modelId) return undefined;
    let disposed = false;
    const s = st.current;
    s.meshes = new Map();
    s.positions = [];
    const W = mount.clientWidth || 800;
    const H = mount.clientHeight || 520;
    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, failIfMajorPerformanceCaveat: false });
      if (!renderer.getContext()) throw new Error("no WebGL");
    } catch {
      setGlError(true);
      return undefined;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(W, H);
    mount.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(document.documentElement.classList.contains("dark") ? 0x111827 : 0xf6f3ec);
    const camera = new THREE.PerspectiveCamera(45, W / H, 0.05, 5000);
    camera.position.set(20, 15, 20);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8577, 0.9));
    const sun = new THREE.DirectionalLight(0xffffff, 0.9);
    sun.position.set(30, 60, 40);
    scene.add(sun);
    const root = new THREE.Group();
    root.rotation.x = -Math.PI / 2; // IFC: Z para cima → three.js: Y para cima
    scene.add(root);
    Object.assign(s, { renderer, scene, camera, controls, root });

    let raf;
    const loop = () => { controls.update(); renderer.render(scene, camera); raf = requestAnimationFrame(loop); };
    loop();
    const onResize = () => {
      const w = mount.clientWidth; const h = mount.clientHeight;
      if (!w || !h) return;
      camera.aspect = w / h; camera.updateProjectionMatrix(); renderer.setSize(w, h);
    };
    window.addEventListener("resize", onResize);
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(onResize) : null;
    ro?.observe(mount);

    // Seleção / medição por clique (ignora arrastos)
    const ray = new THREE.Raycaster();
    let down = null;
    const onDown = (e) => { down = [e.clientX, e.clientY]; };
    const onUp = (e) => {
      if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) return;
      const r = renderer.domElement.getBoundingClientRect();
      const ndc = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(ndc, camera);
      const hits = ray.intersectObjects([...s.meshes.values()].filter((m) => m.visible), false);
      const hit = hits[0];
      if (measureRef.current.active) {
        if (!hit) return;
        const p = root.worldToLocal(hit.point.clone()).toArray(); // coordenadas IFC (m)
        const pts = [...measureRef.current.points, p].slice(-2);
        measureRef.current.points = pts;
        drawMeasure(pts);
        if (pts.length === 2) cbRef.current.onMeasure?.(distance(pts[0], pts[1]));
        return;
      }
      cbRef.current.onSelect?.(hit ? hit.object.userData.gid : null);
    };
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointerup", onUp);

    const drawMeasure = (pts) => {
      if (s.measure) { root.remove(s.measure); s.measure.geometry.dispose(); }
      if (pts.length < 2) return;
      const g = new THREE.BufferGeometry().setFromPoints(pts.map((p) => new THREE.Vector3(...p)));
      s.measure = new THREE.Line(g, new THREE.LineBasicMaterial({ color: 0xc4733f, depthTest: false }));
      s.measure.renderOrder = 999;
      root.add(s.measure);
    };
    s.drawMeasure = drawMeasure;

    (async () => {
      setProgress({ loaded: 0, total: chunks });
      setLoadError(null);
      for (let c = 0; c < chunks; c += 1) {
        if (disposed) return;
        try {
          const { data } = await api.get(`/bim/models/${modelId}/versions/${version}/geometry/${c}`);
          if (disposed) return;
          (data.elements || []).forEach((el) => {
            if (!isValidMesh(el)) return;
            const g = new THREE.BufferGeometry();
            g.setAttribute("position", new THREE.Float32BufferAttribute(el.p, 3));
            g.setIndex(el.i);
            g.computeVertexNormals();
            const m0 = meta?.[el.gid];
            const base = new THREE.Color(...(CATEGORY_COLORS[m0?.category] || el.c || [0.75, 0.73, 0.7]));
            const transparent = m0?.category === "espacos" || m0?.category === "janelas";
            const mat = new THREE.MeshLambertMaterial({ color: base, transparent, opacity: transparent ? 0.35 : 1, side: THREE.DoubleSide });
            const mesh = new THREE.Mesh(g, mat);
            mesh.userData = { gid: el.gid, base, cat: m0?.category };
            mesh.visible = isVisible(m0, filtersRef.current);
            root.add(mesh);
            s.meshes.set(el.gid, mesh);
            s.positions.push(el.p);
          });
          if (c === 0) {
            const b = boundsOf(s.positions);
            if (b) fit();
          }
          setProgress({ loaded: c + 1, total: chunks });
        } catch (err) {
          setLoadError(err?.response?.status === 404 ? "Geometria indisponível." : "Falha ao carregar a geometria — tente novamente.");
          return;
        }
      }
      fit();
    })();

    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
      ro?.disconnect();
      renderer.domElement.removeEventListener("pointerdown", onDown);
      renderer.domElement.removeEventListener("pointerup", onUp);
      s.meshes.forEach((m) => { m.geometry.dispose(); m.material.dispose(); });
      controls.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode === mount) mount.removeChild(renderer.domElement);
      s.meshes = new Map();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelId, version, chunks]);

  // Filtros / seleção / destaque
  useEffect(() => {
    st.current.meshes.forEach((m, gid) => {
      const cat = meta?.[gid]?.category;
      if (cat && m.userData.cat !== cat) { // metadados chegaram depois da geometria
        m.userData.cat = cat;
        m.userData.base = new THREE.Color(...(CATEGORY_COLORS[cat] || [0.75, 0.73, 0.7]));
        const transparent = cat === "espacos" || cat === "janelas";
        m.material.transparent = transparent;
        m.material.opacity = transparent ? 0.35 : 1;
        m.material.needsUpdate = true;
      }
      m.visible = isVisible(meta?.[gid], filters);
      const c = gid === selectedGid ? SELECT : highlighted?.has(gid) ? HILITE : m.userData.base;
      m.material.color.copy(c);
      m.material.emissive?.setHex(gid === selectedGid ? 0x0b3b25 : 0x000000);
    });
  }, [filters, selectedGid, highlighted, meta]);

  useEffect(() => {
    if (!measuring) { measureRef.current.points = []; st.current.drawMeasure?.([]); }
  }, [measuring]);

  if (glError) {
    return (
      <div className="rounded-xl border border-dashed p-8 text-sm text-center text-muted-foreground" data-testid="bim-viewer-nogl">
        O seu navegador não suporta WebGL. As medições e o orçamento continuam disponíveis nos separadores ao lado.
      </div>
    );
  }
  return (
    <div className="relative h-[60vh] min-h-[380px] w-full rounded-xl overflow-hidden border bg-[#f6f3ec] dark:bg-slate-900" data-testid="bim-viewer">
      <div ref={mountRef} className="absolute inset-0" />
      {progress.loaded < progress.total && !loadError && (
        <div className="absolute left-3 top-3 rounded-full bg-white/90 dark:bg-slate-800/90 px-3 py-1 text-xs shadow" data-testid="bim-viewer-progress">
          A carregar geometria… {progress.loaded}/{progress.total}
        </div>
      )}
      {loadError && <div className="absolute left-3 top-3 rounded-lg bg-red-50 text-red-700 px-3 py-1 text-xs shadow">{loadError}</div>}
      {measuring && (
        <div className="absolute right-3 top-3 rounded-full bg-[#c4733f] text-white px-3 py-1 text-xs shadow">
          Medição: clique em dois pontos do modelo
        </div>
      )}
    </div>
  );
});

export default BimViewer;
