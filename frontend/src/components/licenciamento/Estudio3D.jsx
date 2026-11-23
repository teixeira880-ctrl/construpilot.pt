import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

/**
 * 3D do Estúdio de Projeto — desenhado só a partir do resultado do servidor (`derivado`): as mesmas paredes, vãos,
 * lajes, divisões e águas que servem para os alçados, cortes e medições. Modelo: x, y em planta e z = cota →
 * three: (x, z, −y). Cada peça leva o seu acabamento: fachada por parede, caixilharia por vão, e pavimento, faces de
 * parede e teto por divisão. Um clique numa peça seleciona-a no editor (`onSelecionar`).
 */

const RESERVA = { fachada: "#f1efe9", cobertura: "#ba6042", caixilharia: "#2f3235", parede_interior: "#f6f5f0", pavimento: "#b9b7b1", teto: "#f6f5f0" };

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

// retângulo vertical (de u0 a L, altura h) com os vãos recortados
function painel(L, h, u0, vaos) {
  const sh = new THREE.Shape();
  sh.moveTo(u0, 0); sh.lineTo(L, 0); sh.lineTo(L, h); sh.lineTo(u0, h); sh.closePath();
  for (const v of vaos) {
    const z1 = Math.min(v.z1, h);
    const f = new THREE.Path();
    f.moveTo(v.u0, v.z0); f.lineTo(v.u1, v.z0); f.lineTo(v.u1, z1); f.lineTo(v.u0, z1); f.closePath();
    sh.holes.push(f);
  }
  return sh;
}

// referencial de um plano vertical que parte de `a` na direção (ux, uy), à cota z0
function base(a, ux, uy, z0) {
  const b = new THREE.Matrix4().makeBasis(new THREE.Vector3(ux, 0, -uy), new THREE.Vector3(0, 1, 0), new THREE.Vector3(uy, 0, ux));
  b.setPosition(a[0], z0, -a[1]);
  return b;
}

function construir(derivado, pisoVisivel) {
  const grupo = new THREE.Group();
  const cores = { ...RESERVA, ...(derivado.cores || {}) };
  const cache = {};
  const mat = (cor, extra = {}) => {       // um material por cor (e variante), partilhado entre peças
    const k = `${cor}|${JSON.stringify(extra)}`;
    if (!cache[k]) cache[k] = new THREE.MeshStandardMaterial({ color: cor, roughness: 0.85, ...extra });
    return cache[k];
  };
  const mVidro = new THREE.MeshPhysicalMaterial({ color: 0x8fb4cc, roughness: 0.05, metalness: 0.2, transparent: true, opacity: 0.55 });
  const mPorta = mat("#7a4b28", { roughness: 0.6 });
  const ate = pisoVisivel == null ? Infinity : pisoVisivel;      // corta a vista acima deste piso (ver o interior)
  const ordem = Object.fromEntries((derivado.pisos || []).map((p, i) => [p.id, i]));
  const nPisos = (derivado.pisos || []).length;
  const junta = (mesh, alvo) => { mesh.userData.alvo = alvo; grupo.add(mesh); return mesh; };

  for (const w of derivado.paredes || []) {
    if (ordem[w.piso] > ate) continue;
    const L = w.comprimento_m, t = w.esp_m;
    const ux = (w.b[0] - w.a[0]) / L, uy = (w.b[1] - w.a[1]) / L;
    const validos = (w.vaos || []).filter((v) => v.valido);
    // nos encontros só a parede dona avança; as outras param na face dela (sem volumes sobrepostos)
    const ea = w.ext3d_a ?? w.ext_a, eb = w.ext3d_b ?? w.ext_b;
    const geo = new THREE.ExtrudeGeometry(painel(L + eb, w.altura_m, -ea, validos), { depth: t, bevelEnabled: false });
    geo.translate(0, 0, -t / 2);
    const B = base(w.a, ux, uy, w.z0);
    const mesh = new THREE.Mesh(geo, mat(w.cor || (w.exterior ? cores.fachada : cores.parede_interior)));
    mesh.applyMatrix4(B);
    mesh.castShadow = true; mesh.receiveShadow = true;
    junta(mesh, { tipo: "parede", id: w.id, piso: w.piso });
    for (const v of validos) {
      const larg = v.u1 - v.u0, alt = v.z1 - v.z0;
      const alvo = { tipo: "vao", id: v.id, piso: w.piso };
      const folha = new THREE.Mesh(new THREE.BoxGeometry(larg, alt, 0.04), v.tipo === "porta" ? mPorta : mVidro);
      folha.position.set((v.u0 + v.u1) / 2, (v.z0 + v.z1) / 2, 0);
      folha.applyMatrix4(B);
      junta(folha, alvo);
      const mCaix = mat(v.cor || cores.caixilharia, { roughness: 0.4, metalness: 0.3 });
      const aros = [[larg, 0.05, 0, alt / 2], [0.05, alt, larg / 2, 0], [0.05, alt, -larg / 2, 0]];
      if (v.tipo !== "porta") aros.push([larg, 0.05, 0, -alt / 2]);
      for (const [bw, bh, bx, by] of aros) {
        const aro = new THREE.Mesh(new THREE.BoxGeometry(bw, bh, t + 0.02), mCaix);
        aro.position.set((v.u0 + v.u1) / 2 + bx, (v.z0 + v.z1) / 2 + by, 0);
        aro.applyMatrix4(B);
        junta(aro, alvo);
      }
    }
  }

  (derivado.lajes || []).forEach((lj, i) => {
    if (i > ate) return;   // lajes acima do piso visível ficam de fora (laje i = sob o piso i; a última é a de cobertura)
    for (const anel of lj.polys) {
      const sh = new THREE.Shape(anel.map((p) => new THREE.Vector2(p[0], p[1])));
      const geo = new THREE.ExtrudeGeometry(sh, { depth: lj.z1 - lj.z0, bevelEnabled: false });
      geo.rotateX(-Math.PI / 2);
      const mesh = new THREE.Mesh(geo, mat("#c9c7c1", { roughness: 0.9 }));
      mesh.position.y = lj.z0;
      mesh.receiveShadow = true; mesh.castShadow = true;
      grupo.add(mesh);
    }
  });

  // cada divisão vestida com os seus acabamentos: pavimento, faces de parede (com os vãos recortados) e teto
  for (const d of derivado.divisoes || []) {
    const k = ordem[d.piso];
    if (k > ate || !d.acabamentos) continue;
    const alvo = { tipo: "divisao", pt: d.centro, piso: d.piso };
    const z0 = d.z0 ?? 0, h = (d.z1 ?? z0 + 2.7) - z0;
    const forma = new THREE.Shape(d.pts.map((p) => new THREE.Vector2(p[0], p[1])));
    const chao = new THREE.ShapeGeometry(forma);
    chao.rotateX(-Math.PI / 2);
    const mChao = new THREE.Mesh(chao, mat(d.acabamentos.pavimento.cor, { roughness: 0.7, side: THREE.DoubleSide }));
    mChao.position.y = z0 + 0.012;
    mChao.receiveShadow = true;
    junta(mChao, alvo);
    for (const f of d.faces || []) {
      const L = Math.hypot(f.b[0] - f.a[0], f.b[1] - f.a[1]);
      const ux = (f.b[0] - f.a[0]) / L, uy = (f.b[1] - f.a[1]) / L;
      // 8 mm para dentro da divisão (o contorno roda no sentido anti-horário: o interior fica à esquerda)
      const a = [f.a[0] - uy * 0.008, f.a[1] + ux * 0.008];
      const pele = new THREE.Mesh(new THREE.ShapeGeometry(painel(L, h, 0, f.vaos || [])), mat(d.acabamentos.parede_interior.cor, { side: THREE.DoubleSide }));
      pele.applyMatrix4(base(a, ux, uy, z0));
      pele.receiveShadow = true;
      junta(pele, alvo);
    }
    if (ate === Infinity || k < ate) {      // o teto do piso que se está a ver por dentro fica de fora
      const teto = new THREE.ShapeGeometry(forma);
      teto.rotateX(-Math.PI / 2);
      const mTeto = new THREE.Mesh(teto, mat(d.acabamentos.teto.cor, { side: THREE.DoubleSide }));
      mTeto.position.y = z0 + h - 0.012;
      junta(mTeto, alvo);
    }
  }

  if (ate >= nPisos - 1) {
    const mCob = mat(cores.cobertura, { roughness: 0.8, side: THREE.DoubleSide });
    for (const f of derivado.cobertura?.faces || []) { const m = new THREE.Mesh(leque(f.pts), mCob); m.castShadow = true; grupo.add(m); }
    for (const e of derivado.cobertura?.empenas || []) grupo.add(new THREE.Mesh(leque(e.pts), mat(cores.fachada, { side: THREE.DoubleSide })));
  }
  return grupo;
}

function libertar(grupo) {
  const mats = new Set();
  grupo.traverse((o) => { if (o.geometry) o.geometry.dispose(); if (o.material) mats.add(o.material); });
  mats.forEach((m) => m.dispose());
}

export default function Estudio3D({ derivado, altura = 420, pisoVisivel = null, onSelecionar = null }) {
  const mount = useRef(null);
  const st = useRef({});
  const aoSelecionar = useRef(onSelecionar);
  aoSelecionar.current = onSelecionar;
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

    // clique (sem arrastar) numa peça → selecionar essa peça no editor
    const raio = new THREE.Raycaster();
    let baixo = null;
    const down = (ev) => { baixo = [ev.clientX, ev.clientY]; };
    const up = (ev) => {
      if (!baixo || Math.hypot(ev.clientX - baixo[0], ev.clientY - baixo[1]) > 5 || !st.current.grupo) return;
      const r = renderer.domElement.getBoundingClientRect();
      raio.setFromCamera(new THREE.Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1), camera);
      const hit = raio.intersectObjects(st.current.grupo.children, false).find((x) => x.object.userData.alvo);
      if (hit && aoSelecionar.current) aoSelecionar.current(hit.object.userData.alvo);
    };
    renderer.domElement.addEventListener("pointerdown", down);
    renderer.domElement.addEventListener("pointerup", up);

    st.current = { renderer, scene, camera, controls, sol, enquadrado: false };
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
      renderer.domElement.removeEventListener("pointerdown", down);
      renderer.domElement.removeEventListener("pointerup", up);
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
    s.grupo = construir(derivado, pisoVisivel);
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
  }, [derivado, pisoVisivel]);

  if (erro) return <div className="p-6 text-sm text-muted-foreground border rounded">O seu navegador não suporta 3D (WebGL).</div>;
  return <div ref={mount} style={{ width: "100%", height: altura }} className="rounded-lg overflow-hidden border" data-testid="estudio-3d" />;
}
