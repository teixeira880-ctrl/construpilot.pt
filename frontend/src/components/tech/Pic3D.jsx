import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { Box, Plane, Play, Pause, Tag } from "lucide-react";

/**
 * Vista 3D realista / vista aérea do plano de estaleiro.
 * Tudo à escala da planta (metros): implantações, edifício, lanças das gruas. As alturas das
 * instalações (contentores, vedação…) são indicativas.
 * Eixos: X = x da planta, Z = y da planta, Y = altura.
 */
const H_INDIC = { base_vie: 2.6, benne: 1.5, branchement: 1.7, silo: 7, cloture: 2, etage: 3 };

// ---------------------------------------------------------------------------
// Textures procédurales (aucun fichier externe)
// ---------------------------------------------------------------------------
function canvasTex(w, h, draw, { repeat, alpha = false } = {}) {
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  const ctx = c.getContext("2d");
  if (!alpha) { ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, w, h); }
  draw(ctx, w, h);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.wrapS = THREE.RepeatWrapping; t.wrapT = THREE.RepeatWrapping;
  t.anisotropy = 8;
  if (repeat) t.repeat.set(repeat[0], repeat[1]);
  return t;
}

// bruit déterministe (pas de Math.random : rendu identique d'une capture à l'autre)
function rng(seed) { let s = seed; return () => { s = (s * 16807) % 2147483647; return s / 2147483647; }; }

function speckle(ctx, w, h, base, tones, n, seed, size = 2) {
  ctx.fillStyle = base; ctx.fillRect(0, 0, w, h);
  const r = rng(seed);
  for (let i = 0; i < n; i += 1) {
    ctx.fillStyle = tones[Math.floor(r() * tones.length)];
    ctx.globalAlpha = 0.25 + r() * 0.5;
    ctx.fillRect(r() * w, r() * h, 1 + r() * size, 1 + r() * size);
  }
  ctx.globalAlpha = 1;
}

const TEX = {
  grass: () => canvasTex(256, 256, (c, w, h) => speckle(c, w, h, "#7d9a5e", ["#6b8a4e", "#93ab72", "#5f7c45", "#a3b784", "#8a9463"], 9000, 7, 5)),
  gravel: () => canvasTex(256, 256, (c, w, h) => speckle(c, w, h, "#b9ad97", ["#a39782", "#cfc4ae", "#8f8573", "#d9d0bd"], 6000, 11, 3)),
  asphalt: () => canvasTex(256, 256, (c, w, h) => speckle(c, w, h, "#55585c", ["#484b4f", "#63666a", "#3d4043"], 5000, 13, 2)),
  concrete: () => canvasTex(256, 256, (c, w, h) => speckle(c, w, h, "#c9c5bc", ["#bdb9b0", "#d6d2c9", "#b0aca3"], 3500, 17, 3)),
  wood: () => canvasTex(128, 128, (c, w, h) => {
    c.fillStyle = "#c69c6d"; c.fillRect(0, 0, w, h);
    c.strokeStyle = "#8d6e4a"; c.lineWidth = 3;
    for (let y = 0; y <= h; y += 16) { c.beginPath(); c.moveTo(0, y); c.lineTo(w, y); c.stroke(); }
    for (let x = 0; x <= w; x += 42) { c.beginPath(); c.moveTo(x, 0); c.lineTo(x, h); c.stroke(); }
  }),
  rubble: () => canvasTex(128, 128, (c, w, h) => speckle(c, w, h, "#7a6a58", ["#5e5145", "#9a8a76", "#b8b0a4", "#4a4038"], 1800, 19, 7)),
  // treillis de grue : membrures + diagonales, fond transparent
  lattice: () => canvasTex(128, 128, (c, w, h) => {
    c.strokeStyle = "#fff"; c.lineCap = "round";
    c.lineWidth = 16; c.strokeRect(0, 0, w, h);
    c.lineWidth = 9;
    c.beginPath(); c.moveTo(6, 6); c.lineTo(w - 6, h - 6); c.moveTo(w - 6, 6); c.lineTo(6, h - 6); c.stroke();
  }, { alpha: true }),
  // panneau de clôture mobile 3,50 × 2,00 m : cadre + grillage
  fence: () => canvasTex(350, 200, (c, w, h) => {
    c.strokeStyle = "rgba(205,210,214,0.95)"; c.lineWidth = 2;
    for (let x = 14; x < w; x += 14) { c.beginPath(); c.moveTo(x, 6); c.lineTo(x, h - 16); c.stroke(); }
    for (let y = 20; y < h - 16; y += 34) { c.beginPath(); c.moveTo(4, y); c.lineTo(w - 4, y); c.stroke(); }
    c.lineWidth = 8; c.strokeStyle = "#dfe3e6"; c.strokeRect(4, 6, w - 8, h - 22);
    c.fillStyle = "#9a9a96"; c.fillRect(0, h - 14, 46, 14); c.fillRect(w - 46, h - 14, 46, 14);
  }, { alpha: true }),
  // échafaudage : montants, lisses, planchers
  scaffold: () => canvasTex(250, 200, (c, w, h) => {
    c.strokeStyle = "rgba(190,196,200,0.95)"; c.lineWidth = 7;
    c.beginPath(); c.moveTo(4, 0); c.lineTo(4, h); c.moveTo(w - 4, 0); c.lineTo(w - 4, h); c.stroke();
    c.lineWidth = 4;
    [70, 120].forEach((y) => { c.beginPath(); c.moveTo(0, y); c.lineTo(w, y); c.stroke(); });
    c.beginPath(); c.moveTo(4, h - 6); c.lineTo(w - 4, 10); c.stroke();
    c.fillStyle = "rgba(196,160,110,0.95)"; c.fillRect(0, h - 14, w, 12);
  }, { alpha: true }),
  // façade béton avec baies : tuile de 4 m × 3 m (un étage)
  facade: () => canvasTex(256, 192, (c, w, h) => {
    speckle(c, w, h, "#cdc8be", ["#c1bcb2", "#d8d3c9", "#b6b1a7"], 2500, 23, 3);
    c.fillStyle = "#8f8a80"; c.fillRect(0, 0, w, 10);
    c.fillStyle = "#1f2a36"; c.fillRect(70, 52, 116, 96);
    c.fillStyle = "rgba(120,170,210,0.35)"; c.fillRect(70, 52, 116, 30);
    c.strokeStyle = "#5c6166"; c.lineWidth = 4; c.strokeRect(70, 52, 116, 96);
    c.beginPath(); c.moveTo(128, 52); c.lineTo(128, 148); c.stroke();
  }),
  // module de base vie : tôle nervurée, porte, fenêtre, bandeau de couleur
  cabin: (accent) => canvasTex(512, 220, (c, w, h) => {
    c.fillStyle = "#eef0ee"; c.fillRect(0, 0, w, h);
    c.strokeStyle = "rgba(0,0,0,0.10)"; c.lineWidth = 2;
    for (let x = 0; x < w; x += 12) { c.beginPath(); c.moveTo(x, 0); c.lineTo(x, h); c.stroke(); }
    c.fillStyle = accent; c.fillRect(0, 0, w, 26);
    c.fillStyle = "#d9dcda"; c.fillRect(60, 60, 76, 150); c.strokeStyle = "#7d8285"; c.lineWidth = 4; c.strokeRect(60, 60, 76, 150);
    c.fillStyle = "#26333f"; c.fillRect(230, 70, 120, 70); c.fillRect(390, 70, 80, 70);
    c.fillStyle = "rgba(150,200,235,0.4)"; c.fillRect(230, 70, 120, 24); c.fillRect(390, 70, 80, 24);
    c.strokeStyle = "#f7f7f7"; c.lineWidth = 5; c.strokeRect(230, 70, 120, 70); c.strokeRect(390, 70, 80, 70);
  }),
  parking: () => canvasTex(250, 500, (c, w, h) => {
    speckle(c, w, h, "#55585c", ["#484b4f", "#63666a"], 4000, 29, 2);
    c.strokeStyle = "#f5f5f5"; c.lineWidth = 8; c.strokeRect(0, 0, w, h);
  }),
};

function sky() {
  const t = canvasTex(8, 512, (c, w, h) => {
    const g = c.createLinearGradient(0, 0, 0, h);
    g.addColorStop(0, "#3f8fe8"); g.addColorStop(0.55, "#9fcdf7"); g.addColorStop(1, "#e9f5ff");
    c.fillStyle = g; c.fillRect(0, 0, w, h);
  });
  t.wrapS = THREE.ClampToEdgeWrapping; t.wrapT = THREE.ClampToEdgeWrapping;
  return t;
}

function label(text, color = "#0A0D14") {
  const c = document.createElement("canvas");
  const ctx = c.getContext("2d");
  const font = "600 44px Inter, Arial, sans-serif";
  ctx.font = font;
  const w = Math.ceil(ctx.measureText(text).width) + 36;
  c.width = w; c.height = 68;
  ctx.font = font;
  ctx.fillStyle = "rgba(255,255,255,0.92)";
  if (ctx.roundRect) { ctx.beginPath(); ctx.roundRect(0, 0, w, 68, 14); ctx.fill(); } else ctx.fillRect(0, 0, w, 68);
  ctx.fillStyle = color; ctx.textBaseline = "middle"; ctx.fillText(text, 18, 36);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false }));
  sp.userData.aspect = w / 68;
  sp.renderOrder = 10;
  return sp;
}

const std = (color, opts = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.75, ...opts });

function mesh(geo, mat, { cast = true, receive = true } = {}) {
  const m = new THREE.Mesh(geo, mat);
  m.castShadow = cast; m.receiveShadow = receive;
  return m;
}
const box = (w, h, d, mat, o) => mesh(new THREE.BoxGeometry(w, h, d), mat.isMaterial || Array.isArray(mat) ? mat : std(mat), o);

function wheel(r = 0.5, w = 0.35) {
  const m = mesh(new THREE.CylinderGeometry(r, r, w, 18), std(0x1c1c1c, { roughness: 0.9 }));
  m.rotation.x = Math.PI / 2;
  return m;
}

// ---------------------------------------------------------------------------
// Grue à tour en treillis
// ---------------------------------------------------------------------------
function buildCrane(el, mastH, liftR, tex, annots, zAt = null, base = 0) {
  const g = new THREE.Group();
  g.position.set(el.x, 0, el.y);
  const YELLOW = 0xffc400;
  const truss = (w, h, d, ru, rv) => {
    const map = tex.lattice.clone(); map.needsUpdate = true; map.repeat.set(ru, rv);
    return mesh(new THREE.BoxGeometry(w, h, d), new THREE.MeshStandardMaterial({
      color: YELLOW, map, alphaTest: 0.35, side: THREE.DoubleSide, roughness: 0.45, metalness: 0.35 }));
  };
  const concrete = std(0xbdb9b0, { map: tex.concrete });
  const bw = el.w || 4.5;
  // châssis en croix + lests
  [0, Math.PI / 2].forEach((a) => { const beam = box(bw * 1.3, 0.35, 0.5, std(YELLOW, { metalness: 0.3, roughness: 0.5 })); beam.rotation.y = a + Math.PI / 4; beam.position.y = 0.35; g.add(beam); });
  [[1, 1], [1, -1], [-1, 1], [-1, -1]].forEach(([sx, sz]) => { const b = box(1.3, 1.1, 1.3, concrete); b.position.set(sx * bw * 0.32, 1.05, sz * bw * 0.32); g.add(b); });
  const mast = truss(1.7, mastH, 1.7, 1, mastH / 1.7); mast.position.y = mastH / 2 + 0.5; g.add(mast);
  const top = new THREE.Group(); top.position.y = mastH + 0.5; g.add(top);
  const ring = mesh(new THREE.CylinderGeometry(1.25, 1.25, 0.6, 24), std(0x37474f, { metalness: 0.5 })); ring.position.y = 0.3; top.add(ring);
  const jib = el.jib_m || 30;
  const j = truss(jib, 1.3, 1.2, jib / 1.3, 1); j.position.set(jib / 2, 1.45, 0); top.add(j);
  const cj = Math.max(jib * 0.26, 8);
  const c = truss(cj, 1.1, 1.2, cj / 1.1, 1); c.position.set(-cj / 2, 1.35, 0); top.add(c);
  for (let i = 0; i < 3; i += 1) { const w = box(0.7, 2.4, 1.5, concrete); w.position.set(-cj + 0.6 + i * 0.85, 0.5, 0); top.add(w); }
  const winch = box(2.2, 1.1, 1.3, std(0x455a64, { metalness: 0.4 })); winch.position.set(-cj * 0.55, 2.4, 0); top.add(winch);
  // cabine vitrée
  const cab = box(1.9, 2.1, 1.7, std(0xf5f5f5, { roughness: 0.5 })); cab.position.set(1.7, -0.1, 1.55); top.add(cab);
  const glass = box(0.08, 1.2, 1.5, new THREE.MeshStandardMaterial({ color: 0x4f86b5, roughness: 0.1, metalness: 0.8 })); glass.position.set(2.68, 0.15, 1.55); top.add(glass);
  // porte-flèche et tirants
  const apexH = Math.max(jib * 0.11, 5);
  const apex = truss(0.9, apexH, 0.9, 1, apexH / 0.9); apex.position.y = 2 + apexH / 2; top.add(apex);
  const tie = (x) => {
    const len = Math.hypot(x, apexH);
    const t = mesh(new THREE.CylinderGeometry(0.06, 0.06, len, 6), std(0x263238, { metalness: 0.6 }), { cast: false });
    t.position.set(x / 2, 2 + apexH / 2, 0); t.rotation.z = Math.atan2(-apexH, x) - Math.PI / 2;
    top.add(t);
  };
  tie(jib * 0.72); tie(-cj * 0.92);
  // chariot, câbles, moufle, benne à béton
  const hookX = Math.min(jib * 0.62, Math.max(liftR || jib * 0.62, 6));
  const trolley = box(1.6, 0.4, 1.3, std(0x37474f, { metalness: 0.4 })); trolley.position.set(hookX, 0.6, 0); top.add(trolley);
  const cableLen = Math.max(mastH * 0.5, 3);
  [-0.25, 0.25].forEach((dz) => { const cb = mesh(new THREE.CylinderGeometry(0.035, 0.035, cableLen, 5), std(0x1b1b1b), { cast: false }); cb.position.set(hookX, 0.5 - cableLen / 2, dz); top.add(cb); });
  const block = box(0.6, 0.7, 0.5, std(YELLOW, { metalness: 0.3 })); block.position.set(hookX, 0.3 - cableLen, 0); top.add(block);
  const bucket = mesh(new THREE.CylinderGeometry(0.75, 0.45, 1.5, 18), std(0xe53935, { metalness: 0.3, roughness: 0.5 })); bucket.position.set(hookX, -cableLen - 0.95, 0); top.add(bucket);
  // annotations au sol : zone balayée et limite de levage
  // drapeadas sobre o terreno: o círculo segue o relevo
  const flat = (geo, color, opacity, y) => {
    geo.rotateX(-Math.PI / 2);
    const pa = geo.attributes.position;
    for (let i = 0; i < pa.count; i += 1) pa.setY(i, (zAt ? zAt(el.x + pa.getX(i), el.y + pa.getZ(i)) : base) + y);
    const m = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color, transparent: true, opacity, side: THREE.DoubleSide, depthWrite: false }));
    m.position.set(el.x, 0, el.y); annots.add(m);
  };
  flat(new THREE.RingGeometry(0.01, jib, 128, 24), 0xff1744, 0.06, 0.1);
  flat(new THREE.RingGeometry(Math.max(jib - 0.5, 0.1), jib, 160), 0xff1744, 0.95, 0.14);
  if (liftR > 0 && liftR < jib - 0.05) flat(new THREE.RingGeometry(Math.max(liftR - 0.5, 0.1), liftR, 160), 0x00c853, 0.95, 0.16);
  return { group: g, top };
}

export default function Pic3D({ image, site, result, height = 460, onReady }) {
  const mountRef = useRef(null);
  const apiRef = useRef(null);
  const spinRef = useRef(true);
  const [spin, setSpin] = useState(true);
  const [notes, setNotes] = useState(true);
  const [glError, setGlError] = useState(false);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount || !result?.site || !site?.m_per_px) return undefined;
    const Wm = result.site.width_m; const Hm = result.site.height_m;
    const S = Math.max(Wm, Hm);
    const toM = (p) => [p[0] * Wm, p[1] * Hm];
    // relevo: grelha de cotas relativas à soleira (result.terrain), interpolação bilinear
    const tg = result.terrain?.z?.length ? result.terrain : null;
    const zAt = (x, z) => {
      if (!tg) return 0;
      const n = tg.n;
      const fx = Math.min(Math.max(x / Wm, 0), 1) * (n - 1); const fz = Math.min(Math.max(z / Hm, 0), 1) * (n - 1);
      const i = Math.min(Math.floor(fx), n - 2); const j = Math.min(Math.floor(fz), n - 2);
      const u = fx - i; const v = fz - j; const g = (a, b) => tg.z[b * n + a];
      return (g(i, j) * (1 - u) + g(i + 1, j) * u) * (1 - v) + (g(i, j + 1) * (1 - u) + g(i + 1, j + 1) * u) * v;
    };
    const zMin = tg ? Math.min(...tg.z) : 0;
    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    } catch {
      setGlError(true);
      return undefined;
    }
    const width = mount.clientWidth || 800;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(width, height);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap;   // three ≥ 0.182: sombras suaves por omissão
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;
    mount.appendChild(renderer.domElement);

    const tex = Object.fromEntries(Object.entries(TEX).filter(([k]) => k !== "cabin").map(([k, f]) => [k, f()]));
    const scene = new THREE.Scene();
    scene.background = sky();
    scene.fog = new THREE.Fog(0xe3f1fc, S * 3.5, S * 14);
    scene.add(new THREE.HemisphereLight(0xd6ecff, 0x8f8068, 1.0));
    const sun = new THREE.DirectionalLight(0xfff0d2, 2.6);
    sun.position.set(Wm / 2 - S * 0.7, S * 1.1, Hm / 2 + S * 0.9);
    sun.castShadow = true;
    sun.shadow.mapSize.set(4096, 4096);
    sun.shadow.bias = -0.0004;
    sun.shadow.normalBias = 0.05;
    Object.assign(sun.shadow.camera, { left: -S * 0.85, right: S * 0.85, top: S * 0.85, bottom: -S * 0.85, near: 1, far: S * 5 });
    sun.target.position.set(Wm / 2, 0, Hm / 2);
    scene.add(sun, sun.target);

    const annots = new THREE.Group(); scene.add(annots);   // libellés, zones de grue, limite d'emprise
    const labels = [];
    const addLabel = (text, x, y, z, color) => { const sp = label(text, color); sp.position.set(x, y, z); annots.add(sp); labels.push(sp); };

    // sol : herbe aux abords + plan / photo aérienne à l'échelle
    tex.grass.repeat.set(S * 6 / 8, S * 6 / 8);
    const around = mesh(new THREE.PlaneGeometry(S * 6, S * 6), std(0xffffff, { map: tex.grass, roughness: 1 }), { cast: false });
    around.rotation.x = -Math.PI / 2; around.position.set(Wm / 2, zMin - 0.25, Hm / 2); scene.add(around);
    const aerial = site.base === "aerial";
    const groundMat = std(aerial ? 0xffffff : 0xe7dfcc, { roughness: 1 });
    if (image) {
      const t = new THREE.TextureLoader().load(`data:image/png;base64,${image}`);
      t.colorSpace = THREE.SRGBColorSpace;
      t.anisotropy = renderer.capabilities.getMaxAnisotropy();
      groundMat.map = t;
    } else { tex.gravel.repeat.set(Wm / 6, Hm / 6); groundMat.map = tex.gravel; }
    const gseg = tg ? 120 : 1;
    const groundGeo = new THREE.PlaneGeometry(Wm, Hm, gseg, gseg);
    groundGeo.rotateX(-Math.PI / 2); groundGeo.translate(Wm / 2, 0, Hm / 2);
    if (tg) {
      const pa = groundGeo.attributes.position;
      for (let i = 0; i < pa.count; i += 1) pa.setY(i, zAt(pa.getX(i), pa.getZ(i)));
      groundGeo.computeVertexNormals();
      // saia de terra nos bordos: o terreno não fica "a flutuar" sobre a relva
      const soil = std(0x8d6e4f, { roughness: 1 });
      [[[0, 0], [Wm, 0]], [[Wm, 0], [Wm, Hm]], [[Wm, Hm], [0, Hm]], [[0, Hm], [0, 0]]].forEach(([a, b]) => {
        const N = 60; const pos = [];
        for (let k = 0; k < N; k += 1) {
          const p0 = [a[0] + (b[0] - a[0]) * k / N, a[1] + (b[1] - a[1]) * k / N];
          const p1 = [a[0] + (b[0] - a[0]) * (k + 1) / N, a[1] + (b[1] - a[1]) * (k + 1) / N];
          const y0 = zAt(...p0); const y1 = zAt(...p1); const yb = zMin - 0.25;
          pos.push(p0[0], y0, p0[1], p1[0], y1, p1[1], p1[0], yb, p1[1], p0[0], y0, p0[1], p1[0], yb, p1[1], p0[0], yb, p0[1]);
        }
        const sg = new THREE.BufferGeometry(); sg.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3)); sg.computeVertexNormals();
        const sk = new THREE.Mesh(sg, soil.clone()); sk.material.side = THREE.DoubleSide; scene.add(sk);
      });
    }
    const ground = mesh(groundGeo, groundMat, { cast: false });
    scene.add(ground);

    // clôture de chantier en panneaux grillagés + trait rouge de limite d'emprise
    const parcel = (site.parcel || []).map(toM);
    parcel.forEach((a, i) => {
      const b = parcel[(i + 1) % parcel.length];
      const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
      if (len < 0.2) return;
      const map = tex.fence.clone(); map.needsUpdate = true; map.repeat.set(Math.max(1, Math.round(len / 3.5)), 1);
      const panel = mesh(new THREE.PlaneGeometry(len, H_INDIC.cloture), new THREE.MeshStandardMaterial({ map, alphaTest: 0.3, side: THREE.DoubleSide, roughness: 0.5, metalness: 0.5 }));
      const zf = zAt((a[0] + b[0]) / 2, (a[1] + b[1]) / 2);
      panel.position.set((a[0] + b[0]) / 2, zf + H_INDIC.cloture / 2, (a[1] + b[1]) / 2);
      panel.rotation.y = -Math.atan2(b[1] - a[1], b[0] - a[0]);
      scene.add(panel);
      const line = box(len, 0.06, 0.45, new THREE.MeshBasicMaterial({ color: 0xff1744 }), { cast: false, receive: false });
      line.position.set((a[0] + b[0]) / 2, zf + 0.05, (a[1] + b[1]) / 2); line.rotation.y = panel.rotation.y; annots.add(line);
    });

    // bâtiment(s) en construction : façade béton à baies, dalle haute, échafaudage
    // modelo do edifício (motor): soleira = cota 0 da cena, pisos acima, caves abaixo
    const bm = result.building_model || {};
    const hb = Number(bm.height) > 0 ? Number(bm.height)
      : Number(result.answers?.hauteur_batiment_m) > 0 ? Number(result.answers.hauteur_batiment_m) : 6;
    const fh = Number(bm.floor_h) > 0 ? Number(bm.floor_h) : H_INDIC.etage;
    const zBot = Number.isFinite(bm.z_bottom) && Number.isFinite(bm.z_soleira) ? bm.z_bottom - bm.z_soleira : 0;
    tex.facade.repeat.set(1 / 4, 1 / fh);
    tex.concrete.repeat.set(1 / 5, 1 / 5);
    (site.buildings || []).forEach((b, i) => {
      const pts = b.map(toM);
      if (pts.length < 3) return;
      const shape = new THREE.Shape(pts.map(([x, z]) => new THREE.Vector2(x, z)));
      const geo = new THREE.ExtrudeGeometry(shape, { depth: hb, bevelEnabled: false });
      geo.rotateX(Math.PI / 2);
      const body = mesh(geo, [std(0xc9c5bc, { map: tex.concrete }), std(0xffffff, { map: tex.facade })]);
      body.position.y = hb; scene.add(body);
      // acrotère / attentes en tête
      const rim = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 40), new THREE.LineBasicMaterial({ color: 0x5f5b54 }));
      rim.position.y = hb; scene.add(rim);
      // linhas de laje em cada piso
      const loop = (y, color) => {
        const lg = new THREE.BufferGeometry().setFromPoints([...pts, pts[0]].map(([x, z]) => new THREE.Vector3(x, y, z)));
        scene.add(new THREE.Line(lg, new THREE.LineBasicMaterial({ color })));
      };
      for (let y = fh; y < hb - 0.3; y += fh) loop(y, 0x6d6a63);
      // caves: volume enterrado (visível onde o terreno desce)
      if (zBot < -0.1) {
        const bg = new THREE.ExtrudeGeometry(shape, { depth: -zBot, bevelEnabled: false });
        bg.rotateX(Math.PI / 2);
        const base = mesh(bg, std(0xb0a79a, { map: tex.concrete, roughness: 1 }));
        base.position.y = 0; scene.add(base);
        loop(0, 0x3e3a33);
      }
      // échafaudage sur chaque façade (décalé de 0,9 m vers l'extérieur)
      const area = pts.reduce((s, p, k) => { const q = pts[(k + 1) % pts.length]; return s + p[0] * q[1] - q[0] * p[1]; }, 0);
      pts.forEach((p, k) => {
        const q = pts[(k + 1) % pts.length];
        const len = Math.hypot(q[0] - p[0], q[1] - p[1]);
        if (len < 2) return;
        const sgn = area > 0 ? 1 : -1;
        const nx = sgn * (q[1] - p[1]) / len; const nz = -sgn * (q[0] - p[0]) / len;
        const zs = Math.min(0, zAt((p[0] + q[0]) / 2 + nx * 0.9, (p[1] + q[1]) / 2 + nz * 0.9));   // andaime apoiado no terreno
        const sh = hb + 1 - zs;
        const map = tex.scaffold.clone(); map.needsUpdate = true; map.repeat.set(Math.max(1, Math.round(len / 2.5)), Math.max(1, Math.round(sh / 2)));
        const sc = mesh(new THREE.PlaneGeometry(len, sh), new THREE.MeshStandardMaterial({ map, alphaTest: 0.3, side: THREE.DoubleSide, roughness: 0.5, metalness: 0.4 }));
        sc.position.set((p[0] + q[0]) / 2 + nx * 0.9, zs + sh / 2, (p[1] + q[1]) / 2 + nz * 0.9);
        sc.rotation.y = -Math.atan2(q[1] - p[1], q[0] - p[0]);
        scene.add(sc);
      });
      const cx = pts.reduce((s, p) => s + p[0], 0) / pts.length; const cz = pts.reduce((s, p) => s + p[1], 0) / pts.length;
      addLabel(`Edifício${site.buildings.length > 1 ? ` ${i + 1}` : ""} — ${hb.toLocaleString("pt-PT")} m${bm.levels_below ? ` + ${bm.levels_below} cave${bm.levels_below > 1 ? "s" : ""}` : ""}`, cx, hb + S * 0.03, cz);
    });

    // obstacles lus sur le plan
    (result.obstacles || []).forEach((o) => {
      const og = new THREE.Group(); og.position.y = zAt(o.x, o.y); scene.add(og);
      const oh = Number(result.answers?.obstacle_h_m) > 0 ? Number(result.answers.obstacle_h_m) : 6;
      if (o.type === "arbre") {
        const r = Math.max(Math.min(o.w, o.h) / 2, 1.5);
        const trunk = mesh(new THREE.CylinderGeometry(0.3, 0.45, 4.5, 10), std(0x6d4c41, { roughness: 1 })); trunk.position.set(o.x, 2.25, o.y); og.add(trunk);
        [[0, 0, 0, 1], [0.5, 0.5, 0.3, 0.75], [-0.45, 0.35, -0.3, 0.7], [0.1, 0.9, -0.2, 0.6]].forEach(([dx, dy, dz, k], n) => {
          const blob = mesh(new THREE.IcosahedronGeometry(r * k, 2), std([0x3f7d2f, 0x4f9438, 0x366c28, 0x5aa341][n], { roughness: 1, flatShading: true }));
          blob.position.set(o.x + dx * r, 4.5 + r * 0.6 + dy * r, o.y + dz * r); og.add(blob);
        });
      } else if (o.type === "ligne_electrique") {
        const along = o.w >= o.h;
        const len = along ? o.w : o.h;
        [-0.9, 0, 0.9].forEach((off) => {
          const wire = mesh(new THREE.CylinderGeometry(0.04, 0.04, len, 5), std(0x2b2b2b, { metalness: 0.6 }), { cast: false });
          wire.rotation.z = Math.PI / 2; if (!along) wire.rotation.y = Math.PI / 2;
          wire.position.set(o.x + (along ? 0 : off), 9, o.y + (along ? off : 0)); og.add(wire);
        });
        [-1, 1].forEach((s) => {
          const px = o.x + (along ? s * len / 2 : 0); const pz = o.y + (along ? 0 : s * len / 2);
          const pole = mesh(new THREE.CylinderGeometry(0.16, 0.22, 9.4, 10), std(0x5d4037, { roughness: 1 })); pole.position.set(px, 4.7, pz); og.add(pole);
          const arm = box(along ? 0.18 : 2.4, 0.18, along ? 2.4 : 0.18, std(0x4e342e)); arm.position.set(px, 9, pz); og.add(arm);
        });
        addLabel(o.label, o.x, og.position.y + 11.2, o.y, "#B45309");
      } else {
        const m = box(o.w, oh, o.h, std(0xd8d2c6, { map: tex.concrete })); m.position.set(o.x, oh / 2, o.y); og.add(m);
        const roof = box(o.w + 0.4, 0.3, o.h + 0.4, std(0x8d6e63)); roof.position.set(o.x, oh + 0.15, o.y); og.add(roof);
      }
    });

    // installations
    const tops = [];
    const cranes = result.cranes || [];
    (result.elements || []).forEach((e) => {
      const color = new THREE.Color(e.color || "#334155");
      const rotY = -THREE.MathUtils.degToRad(e.rot || 0);
      if (e.type === "grue") {
        const cr = cranes.find((c) => c.id === e.id) || {};
        const zc = Number.isFinite(cr.z_base_rel) ? cr.z_base_rel : zAt(e.x, e.y);
        const mastH = Math.max(cr.hsc_required_m || hb + 8, hb - zc + 6) + 3;
        const { group, top } = buildCrane(e, mastH, e.lift_radius_m, tex, annots, tg ? zAt : null, zc);
        group.position.y = zc;
        scene.add(group); tops.push(top);
        top.rotation.y = tops.length * 1.9;
        addLabel(e.label, e.x, zc + mastH + S * 0.06, e.y, "#B00020");
        return;
      }
      const ze = zAt(e.x, e.y);
      if (e.type === "acces") {
        // portail : deux poteaux, repère vert
        [-2, 2].forEach((d) => { const post = box(0.2, 2.3, 0.2, std(0x455a64, { metalness: 0.5 })); post.position.set(e.x + d, zAt(e.x + d, e.y) + 1.15, e.y); scene.add(post); });
        const cone = mesh(new THREE.ConeGeometry(1.3, 3, 20), new THREE.MeshStandardMaterial({ color: 0x00c853, emissive: 0x00c853, emissiveIntensity: 0.4 }), { cast: false });
        cone.position.set(e.x, ze + 6, e.y); cone.rotation.x = Math.PI; annots.add(cone);
        addLabel("Acesso ao estaleiro", e.x, ze + 9, e.y, "#007E33");
        return;
      }
      const g = new THREE.Group(); g.position.set(e.x, ze, e.y); g.rotation.y = rotY; scene.add(g);
      // liseré de couleur au sol : l'élément reste identifiable comme sur le plan
      const outline = (y) => {
        const edge = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(e.w, 0.02, e.h)), new THREE.LineBasicMaterial({ color }));
        edge.position.set(e.x, ze + y, e.y); edge.rotation.y = rotY; annots.add(edge);
      };
      const slab = (map, tint = 0xffffff, h = 0.1) => {
        const m2 = map ? map.clone() : null;
        if (m2) { m2.needsUpdate = true; m2.repeat.set(e.w / 5, e.h / 5); }
        const s = box(e.w, h, e.h, std(tint, { map: m2, roughness: 1 }), { cast: false }); s.position.y = h / 2; g.add(s);
        outline(h + 0.03);
      };
      if (e.type === "base_vie") {
        const side = std(0xffffff, { map: TEX.cabin(`#${color.getHexString()}`), roughness: 0.6 });
        const plain = std(0xeceeed, { roughness: 0.6 });
        const b = box(e.w, H_INDIC.base_vie, e.h, [plain, plain, std(0xd5d8d6), plain, side, side]); b.position.y = H_INDIC.base_vie / 2 + 0.15; g.add(b);
        [[-1, -1], [-1, 1], [1, -1], [1, 1]].forEach(([sx, sz]) => { const foot = box(0.3, 0.15, 0.3, std(0x777777)); foot.position.set(sx * (e.w / 2 - 0.3), 0.075, sz * (e.h / 2 - 0.3)); g.add(foot); });
      } else if (e.type === "benne") {
        const steel = std(color, { roughness: 0.55, metalness: 0.35 });
        const b = box(e.w, H_INDIC.benne, e.h, [steel, steel, std(0xffffff, { map: tex.rubble, roughness: 1 }), steel, steel, steel]); b.position.y = H_INDIC.benne / 2; g.add(b);
        [-1, 1].forEach((s) => { const rib = box(0.12, H_INDIC.benne + 0.06, e.h + 0.1, std(color.clone().multiplyScalar(0.7))); rib.position.set(s * e.w * 0.3, H_INDIC.benne / 2, 0); g.add(rib); });
      } else if (e.type === "branchement") {
        const cab = box(0.9, H_INDIC.branchement, 0.45, std(0xd0d4d6, { metalness: 0.3 })); cab.position.y = H_INDIC.branchement / 2; g.add(cab);
        const band = box(0.92, 0.3, 0.47, std(color)); band.position.y = H_INDIC.branchement - 0.25; g.add(band);
      } else if (e.type === "silo") {
        const r = Math.min(e.w, e.h) / 2.3;
        const cyl = mesh(new THREE.CylinderGeometry(r, r, H_INDIC.silo - 2.5, 28), std(0xf2f2f2, { roughness: 0.4, metalness: 0.2 })); cyl.position.y = 2.5 + (H_INDIC.silo - 2.5) / 2; g.add(cyl);
        const cone = mesh(new THREE.CylinderGeometry(r, 0.3, 1.5, 28), std(0xe0e0e0, { metalness: 0.2 })); cone.position.y = 1.75; g.add(cone);
        const band = mesh(new THREE.CylinderGeometry(r + 0.02, r + 0.02, 0.8, 28), std(color)); band.position.y = H_INDIC.silo - 1.2; g.add(band);
        [[1, 1], [1, -1], [-1, 1], [-1, -1]].forEach(([sx, sz]) => { const leg = box(0.15, 2.6, 0.15, std(0x607d8b, { metalness: 0.5 })); leg.position.set(sx * r * 0.7, 1.3, sz * r * 0.7); g.add(leg); });
      } else if (e.type === "livraison") {
        slab(tex.asphalt);
        // camion stationné sur l'aire
        const L = Math.max(e.w - 2.5, 6);
        const trailer = box(L - 2.6, 2.7, 2.5, std(0xf4f4f4, { roughness: 0.5 })); trailer.position.set(-1.3, 2.65, 0); g.add(trailer);
        const chassis = box(L - 0.4, 0.35, 2.2, std(0x2f3437)); chassis.position.set(0, 1.1, 0); g.add(chassis);
        const cabin = box(2.3, 2.6, 2.45, std(0x1e88e5, { roughness: 0.35, metalness: 0.3 })); cabin.position.set(L / 2 - 1.15, 2.2, 0); g.add(cabin);
        const ws = box(0.06, 1.1, 2.1, new THREE.MeshStandardMaterial({ color: 0x1b2a38, roughness: 0.08, metalness: 0.9 })); ws.position.set(L / 2 + 0.02, 2.75, 0); g.add(ws);
        [L / 2 - 1.2, -L / 2 + 1.2, -L / 2 + 2.5, ...(L > 12 ? [-L / 2 + 3.8] : [])].forEach((x) => [-1.05, 1.05].forEach((z) => { const w = wheel(); w.position.set(x, 0.6, z); g.add(w); }));
      } else if (e.type === "stockage") {
        slab(tex.gravel);
        const woodMat = std(0xffffff, { map: tex.wood });
        const n = Math.max(1, Math.min(5, Math.floor(e.w / 1.8)));
        const rows = Math.max(1, Math.min(3, Math.floor(e.h / 1.6)));
        for (let i = 0; i < n; i += 1) {
          for (let r = 0; r < rows; r += 1) {
            const hgt = 0.9 + ((i * 3 + r * 2) % 3) * 0.45;
            const x = n > 1 ? -e.w / 2 + 0.9 + i * (e.w - 1.8) / (n - 1) : 0;
            const z = rows > 1 ? -e.h / 2 + 0.8 + r * (e.h - 1.6) / (rows - 1) : 0;
            const pal = box(1.2, 0.15, 1.0, woodMat); pal.position.set(x, 0.18, z); g.add(pal);
            const stack = box(1.1, hgt, 0.9, std([0xb0a79a, 0xc96f4a, 0x9e9e9e][(i + r) % 3], { map: tex.concrete })); stack.position.set(x, 0.25 + hgt / 2, z); g.add(stack);
          }
        }
      } else if (e.type === "parking") {
        const n = Math.max(1, Math.round(e.w / 2.5));
        const map = tex.parking.clone(); map.needsUpdate = true; map.repeat.set(n, 1);
        const s = box(e.w, 0.08, e.h, std(0xffffff, { map, roughness: 1 }), { cast: false }); s.position.y = 0.04; g.add(s);
        for (let i = 0; i < Math.min(n, 2); i += 1) {       // deux véhicules garés
          const x = -e.w / 2 + 1.25 + i * 2.5;
          const paint = std([0xffffff, 0x37474f][i], { roughness: 0.3, metalness: 0.5 });
          const body = box(1.8, 0.7, 4.2, paint); body.position.set(x, 0.75, 0); g.add(body);
          const roof = box(1.6, 0.6, 2.2, new THREE.MeshStandardMaterial({ color: 0x1b2a38, roughness: 0.1, metalness: 0.8 })); roof.position.set(x, 1.4, -0.2); g.add(roof);
          [[-0.9, 1.3], [0.9, 1.3], [-0.9, -1.3], [0.9, -1.3]].forEach(([dx, dz]) => { const w = wheel(0.33, 0.22); w.rotation.set(0, 0, Math.PI / 2); w.position.set(x + dx, 0.33, dz); g.add(w); });
        }
        outline(0.12);
      } else {
        slab(tex.concrete, e.type === "lavage" ? 0x9fd6e0 : 0xffffff);
      }
    });

    // traço do corte vertical A–A′ sobre o terreno
    const ax = result.section?.axis;
    if (ax?.length === 2) {
      const [[x0, z0], [x1, z1]] = ax;
      const pts = Array.from({ length: 81 }, (_, k) => {
        const x = x0 + (x1 - x0) * k / 80; const z = z0 + (z1 - z0) * k / 80;
        return new THREE.Vector3(x, zAt(x, z) + 0.25, z);
      });
      const ln = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),
        new THREE.LineDashedMaterial({ color: 0x0f5257, dashSize: 2.2, gapSize: 0.9 }));
      ln.computeLineDistances(); annots.add(ln);
      addLabel("A", x0, zAt(x0, z0) + 3, z0, "#0F5257");
      addLabel("A′", x1, zAt(x1, z1) + 3, z1, "#0F5257");
    }

    // caméra et contrôles
    const camera = new THREE.PerspectiveCamera(40, width / height, 0.5, S * 30);
    const controls = new OrbitControls(camera, renderer.domElement);
    const center = new THREE.Vector3(Wm / 2, 0, Hm / 2);
    controls.target.copy(center);
    controls.maxPolarAngle = Math.PI / 2 - 0.03;
    controls.enableDamping = true;
    const fit = () => {
      const d = renderer.getSize(new THREE.Vector2());
      const vfov = THREE.MathUtils.degToRad(camera.fov);
      return Math.max(Hm / (2 * Math.tan(vfov / 2)), Wm / (2 * Math.tan(vfov / 2) * (d.x / d.y))) * 1.08;
    };
    const setView = (mode) => {
      controls.target.copy(center);
      const D = fit();
      if (mode === "aerial") camera.position.set(center.x, D, center.z + D * 0.0015);
      else camera.position.set(center.x - D * 0.42, D * 0.6, center.z + D * 1.0);   // oblique, site plein cadre
      controls.update();
    };
    setView("3d");

    const sizeLabels = () => { const h = camera.position.distanceTo(controls.target) * 0.026; labels.forEach((sp) => sp.scale.set(h * sp.userData.aspect, h, 1)); };
    let raf = 0; let last = performance.now();
    const loop = (t) => {
      const dt = Math.min((t - last) / 1000, 0.1); last = t;
      if (spinRef.current) tops.forEach((top, i) => { top.rotation.y += dt * 0.16 * (i % 2 ? -1 : 1); });
      sizeLabels();
      controls.update();
      renderer.render(scene, camera);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);

    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(() => {
      const w = mount.clientWidth || width;
      renderer.setSize(w, height); camera.aspect = w / height; camera.updateProjectionMatrix();
    }) : null;
    ro?.observe(mount);

    const api = {
      setView,
      // vista aérea capturada sem alterar o ângulo escolhido pelo utilizador
      captureAerial: () => {
        const pos = camera.position.clone(); const tgt = controls.target.clone();
        setView("aerial");
        const url = api.capture();
        camera.position.copy(pos); controls.target.copy(tgt); controls.update();
        return url;
      },
      setAnnotations: (on) => { annots.visible = on; },
      // capture haute définition de la vue affichée ; clean = sans libellés ni zones (pour le rendu photo)
      capture: ({ clean = false } = {}) => {
        const ratio = renderer.getPixelRatio();
        const shown = annots.visible;
        if (clean) annots.visible = false;
        renderer.setPixelRatio(3);
        sizeLabels();
        renderer.render(scene, camera);
        const url = renderer.domElement.toDataURL("image/jpeg", 0.9);
        annots.visible = shown;
        renderer.setPixelRatio(ratio);
        renderer.render(scene, camera);
        return url;
      },
    };
    apiRef.current = api;
    onReady?.(api);

    return () => {
      cancelAnimationFrame(raf);
      ro?.disconnect();
      onReady?.(null);
      apiRef.current = null;
      controls.dispose();
      scene.traverse((o) => {
        o.geometry?.dispose?.();
        const mats = Array.isArray(o.material) ? o.material : o.material ? [o.material] : [];
        mats.forEach((m) => { m.map?.dispose?.(); m.dispose?.(); });
      });
      scene.background?.dispose?.();
      Object.values(tex).forEach((t) => t.dispose());
      renderer.dispose();
      if (renderer.domElement.parentNode === mount) mount.removeChild(renderer.domElement);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [image, site, result, height]);

  if (glError) return <p className="text-xs text-muted-foreground" data-testid="pic-3d-error">A vista 3D precisa de WebGL, indisponível neste navegador.</p>;

  const btn = "px-2.5 h-7 rounded-sm border border-border text-xs font-semibold flex items-center gap-1 bg-background";
  return (
    <div className="space-y-2" data-testid="pic-3d">
      <div className="flex flex-wrap items-center gap-1">
        <button type="button" className={btn} onClick={() => apiRef.current?.setView("aerial")} data-testid="pic-3d-aerial"><Plane className="h-3 w-3" />Vista aérea</button>
        <button type="button" className={btn} onClick={() => apiRef.current?.setView("3d")} data-testid="pic-3d-persp"><Box className="h-3 w-3" />Vista 3D</button>
        <button type="button" className={btn} onClick={() => { spinRef.current = !spin; setSpin(!spin); }} data-testid="pic-3d-spin">
          {spin ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}{spin ? "Parar as gruas" : "Rodar as gruas"}
        </button>
        <button type="button" className={btn} onClick={() => { apiRef.current?.setAnnotations(!notes); setNotes(!notes); }} data-testid="pic-3d-notes">
          <Tag className="h-3 w-3" />{notes ? "Ocultar as anotações" : "Mostrar as anotações"}
        </button>
        <span className="ml-auto text-[11px] text-muted-foreground">Arrastar = rodar · roda do rato = zoom · botão direito = deslocar</span>
      </div>
      <div ref={mountRef} className="w-full rounded-sm border border-border overflow-hidden" style={{ height }} />
      <p className="text-[11px] text-muted-foreground">Implantações, edifício e lanças à escala da planta; alturas das instalações indicativas. A vista apresentada é incluída no PDF.</p>
    </div>
  );
}
