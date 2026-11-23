import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

/**
 * 3D do Estúdio de Projeto — desenhado só a partir do resultado do servidor (`derivado`): as mesmas paredes, vãos,
 * lajes e águas que servem para os alçados, cortes e medições. Modelo: x, y em planta e z = cota → three: (x, z, −y).
 */

const FACHADA = { reboco_branco: 0xf1efe9, granito: 0xb0aca2, madeira: 0xba8c60, xisto: 0x68625c, tijolo: 0xbe6e54, betao: 0xb0b0ac,
  misto_granito_reboco: 0xf1efe9, misto_madeira_reboco: 0xf1efe9 };
const COBERTURA = { telha_ceramica: 0xba6042, telha_preta: 0x46484c, zinco: 0x8c969c, plana_seixo: 0xb6b0a4 };
const CAIXILHO = { aluminio_antracite: 0x2f3235, aluminio_branco: 0xf2f2f0, madeira: 0x7a4b28, pvc_branco: 0xf5f5f3 };

function leque(pts3) {
  // polígono convexo → triângulos em leque; pontos do modelo [x, y, z] → three (x, z, −y)
  const pos = [];
  for (let i = 1; i < pts3.length - 1; i += 1) {
    for (const p of [pts3[0], pts3[i], pts3[i + 1]]) pos.push(p[0], p[2], -p[1]);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.computeVertexNormals();
  return g;
}

function construir(derivado, materiais, pisoVisivel) {
  const grupo = new THREE.Group();
  const corF = FACHADA[materiais?.fachada] ?? FACHADA.reboco_branco;
  const mExt = new THREE.MeshStandardMaterial({ color: corF, roughness: 0.85 });
  const mInt = new THREE.MeshStandardMaterial({ color: 0xe9e7e1, roughness: 0.9 });
  const mLaje = new THREE.MeshStandardMaterial({ color: 0xc9c7c1, roughness: 0.9 });
  const mCob = new THREE.MeshStandardMaterial({ color: COBERTURA[materiais?.cobertura] ?? COBERTURA.telha_ceramica, roughness: 0.8, side: THREE.DoubleSide });
  const mEmp = new THREE.MeshStandardMaterial({ color: corF, roughness: 0.85, side: THREE.DoubleSide });
  const mVidro = new THREE.MeshPhysicalMaterial({ color: 0x8fb4cc, roughness: 0.05, metalness: 0.2, transparent: true, opacity: 0.55 });
  const mPorta = new THREE.MeshStandardMaterial({ color: 0x7a4b28, roughness: 0.6 });
  const mCaix = new THREE.MeshStandardMaterial({ color: CAIXILHO[materiais?.caixilharia] ?? CAIXILHO.aluminio_antracite, roughness: 0.4, metalness: 0.3 });
  const ate = pisoVisivel == null ? Infinity : pisoVisivel;      // corta a vista acima deste piso (ver o interior)
  const ordem = Object.fromEntries((derivado.pisos || []).map((p, i) => [p.id, i]));

  for (const w of derivado.paredes || []) {
    if (ordem[w.piso] > ate) continue;
    const L = w.comprimento_m, t = w.esp_m;
    const ux = (w.b[0] - w.a[0]) / L, uy = (w.b[1] - w.a[1]) / L;
    const sh = new THREE.Shape();
    sh.moveTo(-w.ext_a, 0); sh.lineTo(L + w.ext_b, 0); sh.lineTo(L + w.ext_b, w.altura_m); sh.lineTo(-w.ext_a, w.altura_m); sh.closePath();
    const validos = (w.vaos || []).filter((v) => v.valido);
    for (const v of validos) {
      const h = new THREE.Path();
      h.moveTo(v.u0, v.z0); h.lineTo(v.u1, v.z0); h.lineTo(v.u1, v.z1); h.lineTo(v.u0, v.z1); h.closePath();
      sh.holes.push(h);
    }
    const geo = new THREE.ExtrudeGeometry(sh, { depth: t, bevelEnabled: false });
    geo.translate(0, 0, -t / 2);
    const base = new THREE.Matrix4().makeBasis(new THREE.Vector3(ux, 0, -uy), new THREE.Vector3(0, 1, 0), new THREE.Vector3(uy, 0, ux));
    base.setPosition(w.a[0], w.z0, -w.a[1]);
    const mesh = new THREE.Mesh(geo, w.exterior ? mExt : mInt);
    mesh.applyMatrix4(base);
    mesh.castShadow = true; mesh.receiveShadow = true;
    grupo.add(mesh);
    for (const v of validos) {
      const larg = v.u1 - v.u0, alt = v.z1 - v.z0;
      const folha = new THREE.Mesh(new THREE.BoxGeometry(larg, alt, 0.04), v.tipo === "porta" ? mPorta : mVidro);
      folha.position.set((v.u0 + v.u1) / 2, (v.z0 + v.z1) / 2, 0);
      folha.applyMatrix4(base);
      grupo.add(folha);
      if (v.tipo !== "porta") {
        for (const [bw, bh, bx, by] of [[larg, 0.05, 0, alt / 2], [larg, 0.05, 0, -alt / 2], [0.05, alt, larg / 2, 0], [0.05, alt, -larg / 2, 0]]) {
          const aro = new THREE.Mesh(new THREE.BoxGeometry(bw, bh, 0.07), mCaix);
          aro.position.set((v.u0 + v.u1) / 2 + bx, (v.z0 + v.z1) / 2 + by, 0);
          aro.applyMatrix4(base);
          grupo.add(aro);
        }
      }
    }
  }
  const nPisos = (derivado.pisos || []).length;
  (derivado.lajes || []).forEach((lj, i) => {
    if (i > ate) return;   // lajes acima do piso visível ficam de fora (laje i = sob o piso i; a última é a de cobertura)
    for (const anel of lj.polys) {
      const sh = new THREE.Shape(anel.map((p) => new THREE.Vector2(p[0], p[1])));
      const geo = new THREE.ExtrudeGeometry(sh, { depth: lj.z1 - lj.z0, bevelEnabled: false });
      geo.rotateX(-Math.PI / 2);
      const mesh = new THREE.Mesh(geo, mLaje);
      mesh.position.y = lj.z0;
      mesh.receiveShadow = true; mesh.castShadow = true;
      grupo.add(mesh);
    }
  });
  if (ate >= nPisos - 1) {
    for (const f of derivado.cobertura?.faces || []) { const m = new THREE.Mesh(leque(f.pts), mCob); m.castShadow = true; grupo.add(m); }
    for (const e of derivado.cobertura?.empenas || []) grupo.add(new THREE.Mesh(leque(e.pts), mEmp));
  }
  return grupo;
}

function libertar(grupo) {
  const mats = new Set();
  grupo.traverse((o) => { if (o.geometry) o.geometry.dispose(); if (o.material) mats.add(o.material); });
  mats.forEach((m) => m.dispose());
}

export default function Estudio3D({ derivado, materiais, altura = 420, pisoVisivel = null }) {
  const mount = useRef(null);
  const st = useRef({});
  const [erro, setErro] = useState(false);

  useEffect(() => {
    const el = mount.current;
    if (!el) return undefined;
    let renderer;
    try { renderer = new THREE.WebGLRenderer({ antialias: true }); } catch { setErro(true); return undefined; }
    const w = el.clientWidth || 600;
    renderer.setSize(w, altura);
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    el.innerHTML = "";
    el.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xe6eef4);
    const camera = new THREE.PerspectiveCamera(40, w / altura, 0.1, 800);
    camera.position.set(18, 12, 18);
    const sol = new THREE.DirectionalLight(0xfff3df, 2.4);
    sol.position.set(25, 40, 20);
    sol.castShadow = true;
    sol.shadow.mapSize.set(2048, 2048);
    Object.assign(sol.shadow.camera, { left: -40, right: 40, top: 40, bottom: -40, near: 1, far: 160 });
    scene.add(sol, sol.target, new THREE.HemisphereLight(0xeaf3ff, 0x8a8a7a, 1.5));
    const chao = new THREE.Mesh(new THREE.CircleGeometry(120, 48), new THREE.MeshStandardMaterial({ color: 0xb9c7a4, roughness: 1 }));
    chao.rotation.x = -Math.PI / 2; chao.position.y = -0.22; chao.receiveShadow = true;
    scene.add(chao);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.maxPolarAngle = Math.PI / 2.02;
    let raf;
    const loop = () => { controls.update(); renderer.render(scene, camera); raf = requestAnimationFrame(loop); };
    loop();
    const onResize = () => { const ww = el.clientWidth || w; renderer.setSize(ww, altura); camera.aspect = ww / altura; camera.updateProjectionMatrix(); };
    window.addEventListener("resize", onResize);
    st.current = { renderer, scene, camera, controls, sol, enquadrado: false };
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
      controls.dispose();
      if (st.current.grupo) libertar(st.current.grupo);
      chao.geometry.dispose(); chao.material.dispose();
      renderer.dispose();
      el.innerHTML = "";
      st.current = {};
    };
  }, [altura]);

  useEffect(() => {
    const s = st.current;
    if (!s.scene || !derivado) return;
    if (s.grupo) { s.scene.remove(s.grupo); libertar(s.grupo); }
    s.grupo = construir(derivado, materiais, pisoVisivel);
    s.scene.add(s.grupo);
    const lim = derivado.limites;
    if (lim && !s.enquadrado) {       // enquadra uma vez; depois a câmara fica onde o utilizador a deixou
      const cx = (lim[0] + lim[2]) / 2, cy = (lim[1] + lim[3]) / 2;
      const raio = Math.max(12, Math.hypot(lim[2] - lim[0], lim[3] - lim[1]) * 1.1);
      s.controls.target.set(cx, 2.5, -cy);
      s.camera.position.set(cx + raio * 0.8, raio * 0.6, -cy + raio * 0.9);
      s.sol.target.position.set(cx, 0, -cy);
      s.sol.position.set(cx + 25, 40, -cy + 20);
      s.controls.update();
      s.enquadrado = true;
    }
  }, [derivado, materiais, pisoVisivel]);

  if (erro) return <div className="p-6 text-sm text-muted-foreground border rounded">O seu navegador não suporta 3D (WebGL).</div>;
  return <div ref={mount} style={{ width: "100%", height: altura }} className="rounded-lg overflow-hidden border" data-testid="estudio-3d" />;
}
