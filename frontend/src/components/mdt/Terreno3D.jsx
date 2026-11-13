import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

/**
 * Terreno 3D a partir da malha do MDT (alturas reais, metros PT-TM06) com a textura hipsométrica + sombreado.
 * Eixos: x = este, z = sul (linhas do MDT), y = cota × exagero. O limite do terreno é desenhado a vermelho, colado ao relevo.
 */
export default function Terreno3D({ malha, exagero = 1.5, altura = 460 }) {
  const el = useRef(null);
  const st = useRef({});

  useEffect(() => {
    if (!el.current || !malha) return undefined;
    const W = el.current.clientWidth || 800, H = altura;
    const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(W, H);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    el.current.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#eef3ee");
    const { nx, ny, dx, dy, z, z_min: zmin, z_max: zmax } = malha;
    const Lx = nx * dx, Ly = ny * dy, span = Math.max(Lx, Ly);
    const camera = new THREE.PerspectiveCamera(45, W / H, span / 500, span * 20);
    camera.position.set(Lx * 0.55, span * 0.75, Ly * 1.05);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.maxPolarAngle = Math.PI * 0.49;

    const geo = new THREE.PlaneGeometry(Lx, Ly, nx - 1, ny - 1);
    geo.rotateX(-Math.PI / 2);                  // plano XZ; linha 0 (norte) em z = -Ly/2
    const pos = geo.attributes.position;
    const base = (zmin + zmax) / 2;
    const setAlturas = (ex) => {
      for (let i = 0; i < ny; i++) for (let j = 0; j < nx; j++) pos.setY(i * nx + j, (z[i * nx + j] - base) * ex);
      pos.needsUpdate = true;
      geo.computeVertexNormals();
    };
    setAlturas(exagero);
    const tex = new THREE.TextureLoader().load(malha.textura);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = 8;
    const mesh = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ map: tex, roughness: 0.95, metalness: 0, side: THREE.DoubleSide }));
    scene.add(mesh);

    // limite do terreno, colado ao relevo
    let limite = null;
    const desenharLimite = (ex) => {
      if (limite) { scene.remove(limite); limite.geometry.dispose(); }
      if (!malha.terreno?.length) return;
      const amostra = (x, y) => {
        const j = Math.min(Math.max(Math.round(x / dx - 0.5), 0), nx - 1), i = Math.min(Math.max(Math.round(y / dy - 0.5), 0), ny - 1);
        return (z[i * nx + j] - base) * ex + span * 0.002;
      };
      const pts = [];
      const T = [...malha.terreno, malha.terreno[0]];
      for (let k = 0; k < T.length - 1; k++) {
        const [x0, y0] = T[k], [x1, y1] = T[k + 1];
        const n = Math.max(2, Math.ceil(Math.hypot(x1 - x0, y1 - y0) / dx));
        for (let s = 0; s <= n; s++) {
          const x = x0 + ((x1 - x0) * s) / n, y = y0 + ((y1 - y0) * s) / n;
          pts.push(new THREE.Vector3(x - Lx / 2, amostra(x, y), y - Ly / 2));
        }
      }
      limite = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: "#d32f2f" }));
      scene.add(limite);
    };
    desenharLimite(exagero);

    scene.add(new THREE.HemisphereLight("#ffffff", "#6b5a45", 0.9));
    const sol = new THREE.DirectionalLight("#fff6e5", 1.6);
    sol.position.set(-span, span * 1.2, -span * 0.6);
    scene.add(sol);

    let raf = 0;
    const loop = () => { controls.update(); renderer.render(scene, camera); raf = requestAnimationFrame(loop); };
    loop();
    const onResize = () => {
      const w = el.current?.clientWidth || W;
      renderer.setSize(w, H);
      camera.aspect = w / H;
      camera.updateProjectionMatrix();
    };
    window.addEventListener("resize", onResize);
    st.current = { setAlturas, desenharLimite };
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
      controls.dispose();
      geo.dispose();
      tex.dispose();
      renderer.dispose();
      renderer.domElement.remove();
      st.current = {};
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [malha, altura]);

  useEffect(() => {
    st.current.setAlturas?.(exagero);
    st.current.desenharLimite?.(exagero);
  }, [exagero]);

  return <div ref={el} className="w-full rounded-xl overflow-hidden border border-border" style={{ height: altura }} />;
}
