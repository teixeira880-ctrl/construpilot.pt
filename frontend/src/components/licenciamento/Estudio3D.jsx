import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Camera, Download, Footprints, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { sol as posicaoSol, vetorSol, fmt } from "@/components/licenciamento/estudioGeo";
import { texturasReais, corComTextura } from "@/components/licenciamento/texturasReais";
import RenderFotorrealista from "@/components/licenciamento/RenderFotorrealista";

/**
 * 3D do Estúdio de Projeto — desenhado só a partir do resultado do servidor (`derivado`): as mesmas paredes, vãos,
 * lajes, divisões e águas que servem para os alçados, cortes e medições. Modelo: x, y em planta e z = cota →
 * three: (x, z, −y). Cada peça leva o seu acabamento: fachada por parede, caixilharia por vão, e pavimento, faces de
 * parede e teto por divisão. Um clique numa peça seleciona-a no editor (`onSelecionar`).
 */

const RESERVA = { fachada: "#f1efe9", cobertura: "#ba6042", caixilharia: "#2f3235", parede_interior: "#f6f5f0", pavimento: "#b9b7b1", teto: "#f6f5f0" };

// ---------------------------------------------------------------- texturas desenhadas (sem ficheiros de imagem)
// Cada padrão é desenhado num canvas em tons de cinza claro e multiplicado pela cor do acabamento; `m` = metros por repetição.
const PADROES = {
  tijolo: { m: 0.6, f: (c, n) => { c.fillStyle = "#d9d9d9"; c.fillRect(0, 0, n, n); c.fillStyle = "#fff"; const h = n / 8, w = n / 2;
    for (let j = 0; j < 8; j += 1) for (let i = -1; i < 2; i += 1) c.fillRect(i * w + (j % 2 ? w / 2 : 0) + 2, j * h + 2, w - 4, h - 4); } },
  pedra: { m: 1.6, f: (c, n, r) => { c.fillStyle = "#cfcfcf"; c.fillRect(0, 0, n, n); const h = n / 5; let y = 0;
    for (let j = 0; j < 5; j += 1) { let x = -r() * 40; while (x < n) { const w = 50 + r() * 70, v = 225 + Math.floor(r() * 30);
      c.fillStyle = `rgb(${v},${v},${v})`; c.fillRect(x + 2, y + 2, w - 4, h - 4); x += w; } y += h; } } },
  ladrilho: { m: 1.2, f: (c, n) => { c.fillStyle = "#c9c9c9"; c.fillRect(0, 0, n, n); c.fillStyle = "#fff"; const q = n / 2;
    for (let j = 0; j < 2; j += 1) for (let i = 0; i < 2; i += 1) c.fillRect(i * q + 1.5, j * q + 1.5, q - 3, q - 3); } },
  soalho: { m: 1.4, f: (c, n, r) => { const h = n / 8; for (let j = 0; j < 8; j += 1) { const v = 225 + Math.floor(r() * 30);
      c.fillStyle = `rgb(${v},${v},${v})`; c.fillRect(0, j * h, n, h); c.fillStyle = "#b9b9b9"; c.fillRect(0, j * h, n, 1.5); c.fillRect(Math.floor(r() * n), j * h, 1.5, h); } } },
  ripado: { m: 0.8, f: (c, n, r) => { const w = n / 8; for (let i = 0; i < 8; i += 1) { const v = 220 + Math.floor(r() * 35);
      c.fillStyle = `rgb(${v},${v},${v})`; c.fillRect(i * w, 0, w, n); c.fillStyle = "#a9a9a9"; c.fillRect(i * w, 0, 2, n); } } },
  chapa: { m: 1.0, f: (c, n) => { c.fillStyle = "#f4f4f4"; c.fillRect(0, 0, n, n); c.fillStyle = "#c4c4c4"; for (let i = 0; i < 2; i += 1) c.fillRect(i * (n / 2), 0, 5, n);
    c.fillStyle = "#fff"; for (let i = 0; i < 2; i += 1) c.fillRect(i * (n / 2) + 5, 0, 3, n); } },
  telha: { m: 0.9, f: (c, n) => { c.fillStyle = "#e9e9e9"; c.fillRect(0, 0, n, n); const w = n / 4, h = n / 3;
    for (let j = 0; j < 3; j += 1) { c.fillStyle = "#9f9f9f"; c.fillRect(0, j * h, n, 4);
      for (let i = 0; i < 4; i += 1) { const g = c.createLinearGradient(i * w, 0, (i + 1) * w, 0); g.addColorStop(0, "#bdbdbd"); g.addColorStop(0.5, "#ffffff"); g.addColorStop(1, "#bdbdbd");
        c.fillStyle = g; c.fillRect(i * w, j * h + 4, w, h - 4); } } } },
  ardosia: { m: 0.8, f: (c, n, r) => { c.fillStyle = "#bdbdbd"; c.fillRect(0, 0, n, n); const w = n / 4, h = n / 4;
    for (let j = 0; j < 4; j += 1) for (let i = -1; i < 4; i += 1) { const v = 215 + Math.floor(r() * 40); c.fillStyle = `rgb(${v},${v},${v})`;
      c.fillRect(i * w + (j % 2 ? w / 2 : 0) + 1.5, j * h + 1.5, w - 3, h - 3); } } },
  betao: { m: 2.4, f: (c, n, r) => { c.fillStyle = "#f2f2f2"; c.fillRect(0, 0, n, n); for (let k = 0; k < 500; k += 1) { const v = 205 + Math.floor(r() * 50);
      c.fillStyle = `rgb(${v},${v},${v})`; c.fillRect(r() * n, r() * n, 2 + r() * 3, 2 + r() * 3); } c.fillStyle = "#c9c9c9"; c.fillRect(0, 0, n, 2); c.fillRect(0, 0, 2, n); } },
  reboco: { m: 1.5, f: (c, n, r) => { c.fillStyle = "#f6f6f6"; c.fillRect(0, 0, n, n); for (let k = 0; k < 1400; k += 1) { const v = 228 + Math.floor(r() * 27);
      c.fillStyle = `rgb(${v},${v},${v})`; c.fillRect(r() * n, r() * n, 1.5, 1.5); } } },
  marmore: { m: 1.2, f: (c, n, r) => { c.fillStyle = "#f7f7f7"; c.fillRect(0, 0, n, n); c.strokeStyle = "rgba(150,150,150,0.45)";
    for (let k = 0; k < 7; k += 1) { c.lineWidth = 0.6 + r() * 1.6; c.beginPath(); let x = r() * n, y = 0; c.moveTo(x, y);
      while (y < n) { x += (r() - 0.5) * 40; y += 12 + r() * 20; c.lineTo(x, y); } c.stroke(); }
    c.fillStyle = "#dedede"; c.fillRect(0, 0, n, 1.5); c.fillRect(0, 0, 1.5, n); } },
  relva: { m: 1.0, f: (c, n, r) => { c.fillStyle = "#cfcfcf"; c.fillRect(0, 0, n, n); for (let k = 0; k < 2600; k += 1) { const v = 185 + Math.floor(r() * 70);
      c.fillStyle = `rgb(${v},${v},${v})`; c.fillRect(r() * n, r() * n, 1.2, 3 + r() * 4); } } },
  agua: { m: 3.0, f: (c, n, r) => { const g = c.createLinearGradient(0, 0, n, n); g.addColorStop(0, "#e9f4ff"); g.addColorStop(1, "#ffffff");
    c.fillStyle = g; c.fillRect(0, 0, n, n); c.strokeStyle = "rgba(255,255,255,0.9)";
    for (let k = 0; k < 40; k += 1) { c.lineWidth = 1 + r() * 2; c.beginPath(); const x = r() * n, y = r() * n; c.moveTo(x, y);
      c.bezierCurveTo(x + 15, y - 6, x + 30, y + 6, x + 45, y); c.stroke(); } } },
  seixo: { m: 1.0, f: (c, n, r) => { c.fillStyle = "#c4c4c4"; c.fillRect(0, 0, n, n); for (let k = 0; k < 420; k += 1) { const v = 200 + Math.floor(r() * 55);
      c.fillStyle = `rgb(${v},${v},${v})`; c.beginPath(); c.arc(r() * n, r() * n, 3 + r() * 4, 0, 6.3); c.fill(); } } },
};

function texturaDe(padrao, cacheTex) {
  const def = padrao ? PADROES[padrao] : null;
  if (!def || typeof document === "undefined") return null;
  if (!cacheTex[padrao]) {
    const n = 256, cv = document.createElement("canvas");
    cv.width = n; cv.height = n;
    let semente = 7 + padrao.length * 131;                  // sempre o mesmo desenho para o mesmo padrão
    const r = () => { semente = (semente * 16807) % 2147483647; return semente / 2147483647; };
    def.f(cv.getContext("2d"), n, r);
    const t = new THREE.CanvasTexture(cv);
    t.wrapS = THREE.RepeatWrapping; t.wrapT = THREE.RepeatWrapping;
    t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
    t.repeat.set(1 / def.m, 1 / def.m);                     // as geometrias têm UV em metros
    cacheTex[padrao] = t;
  }
  return cacheTex[padrao];
}

// UV em metros para faces inclinadas (águas): projeção na horizontal perpendicular à maior pendente e ao longo dela
function uvPlano(g) {
  const pos = g.getAttribute("position");
  if (!pos || pos.count < 3) return g;
  const a = new THREE.Vector3().fromBufferAttribute(pos, 0), b = new THREE.Vector3().fromBufferAttribute(pos, 1), c = new THREE.Vector3().fromBufferAttribute(pos, 2);
  const nrm = new THREE.Vector3().subVectors(b, a).cross(new THREE.Vector3().subVectors(c, a)).normalize();
  let u = new THREE.Vector3(0, 1, 0).cross(nrm);
  if (u.lengthSq() < 1e-8) u = new THREE.Vector3(1, 0, 0);
  u.normalize();
  const v = new THREE.Vector3().crossVectors(nrm, u).normalize();
  const uv = new Float32Array(pos.count * 2), q = new THREE.Vector3();
  for (let i = 0; i < pos.count; i += 1) { q.fromBufferAttribute(pos, i); uv[2 * i] = q.dot(u); uv[2 * i + 1] = q.dot(v); }
  g.setAttribute("uv", new THREE.BufferAttribute(uv, 2));
  return g;
}

function leque(pts3, tris = null) {
  // triângulos dados pelo servidor (faces com reentrâncias) ou, na falta, leque de um polígono convexo;
  // pontos do modelo [x, y, z] → three (x, z, −y)
  const pos = [];
  if (tris && tris.length) {
    for (const t of tris) for (const p of t) pos.push(p[0], p[2], -p[1]);
  } else {
    for (let i = 1; i < pts3.length - 1; i += 1) {
      for (const p of [pts3[0], pts3[i], pts3[i + 1]]) pos.push(p[0], p[2], -p[1]);
    }
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

// Peças de exterior: material e textura próprios (água da piscina, relva, pedra do terraço, madeira do deck…)
const EXTERIOR = {
  piscina: { cor: "#3fa4d8", padrao: "agua", extra: { roughness: 0.08, metalness: 0.1, transparent: true, opacity: 0.88 } },
  piscina_infinita: { cor: "#3fa4d8", padrao: "agua", extra: { roughness: 0.08, metalness: 0.1, transparent: true, opacity: 0.88 } },
  jacuzzi: { cor: "#4fb3e0", padrao: "agua", extra: { roughness: 0.1, transparent: true, opacity: 0.9 } },
  terraco_pedra: { cor: "#d8cfc0", padrao: "pedra_exterior" },
  deck_madeira: { cor: "#a47a52", padrao: "deck" },
  deck_piscina: { cor: "#a47a52", padrao: "deck" },
  caminho: { cor: "#c9c2b6", padrao: "pedra_exterior" },
  acesso_viaturas: { cor: "#9c9890", padrao: "seixo" },
  relvado: { cor: "#7fae5a", padrao: "relva", extra: { roughness: 1 } },
  canteiro: { cor: "#7b5a3c", padrao: "seixo" },
  muro_vedacao: { cor: "#e9e5dd", padrao: "reboco" },
  estrada: { cor: "#55585c", padrao: "seixo", extra: { roughness: 0.95 } },
  estacionamento: { cor: "#8d8f92", padrao: "seixo" },
  terraco_suspenso: { cor: "#d8cfc0", padrao: "pedra_exterior" },
  sebe: { cor: "#4f7f3a", padrao: "relva", extra: { roughness: 1 } },
  lago: { cor: "#4a9ccf", padrao: "agua", extra: { roughness: 0.08, transparent: true, opacity: 0.88 } },
  horta: { cor: "#6b4d32", padrao: "seixo" },
  parque_infantil: { cor: "#e0a23c", padrao: "seixo", extra: { roughness: 1 } },
  caixa_areia: { cor: "#e6d3a3", padrao: "seixo" },
  campo_jogos: { cor: "#3f8f5f", padrao: "relva" },
  campo_tenis: { cor: "#b5573a", padrao: "seixo" },
};
const ALIAS = { deck: "soalho", pedra_exterior: "pedra" };   // sem fotografia própria, usa o desenho mais próximo

function construir(derivado, pisoVisivel, comTexturas = true, reais = {}) {
  const grupo = new THREE.Group();
  const cores = { ...RESERVA, ...(derivado.cores || {}) };
  const padroes = derivado.padroes || {};
  const cache = {}, cacheTex = {};
  const mat = (cor, extra = {}, padrao = null) => {       // um material por cor, variante e textura, partilhado entre peças
    const k = `${cor}|${JSON.stringify(extra)}|${padrao || ""}`;
    if (!cache[k]) {
      const real = comTexturas && padrao ? (reais[padrao] || reais[ALIAS[padrao]]) : null;
      if (real) {                                         // fotografia CC0 com relevo (normal) e rugosidade reais
        cache[k] = new THREE.MeshStandardMaterial({ color: corComTextura(cor, real), roughness: 0.9, ...extra, map: real.map,
          ...(real.normalMap ? { normalMap: real.normalMap } : {}), ...(real.roughnessMap ? { roughnessMap: real.roughnessMap } : {}) });
      } else {
        const tex = comTexturas && padrao ? texturaDe(PADROES[padrao] ? padrao : ALIAS[padrao], cacheTex) : null;
        cache[k] = new THREE.MeshStandardMaterial({ color: cor, roughness: 0.85, ...extra, ...(tex ? { map: tex } : {}) });
      }
    }
    return cache[k];
  };
  grupo.userData.texturas = cacheTex;
  const mVidro = new THREE.MeshPhysicalMaterial({ color: 0x8fb4cc, roughness: 0.05, metalness: 0.2, transparent: true, opacity: 0.55 });
  const mPorta = mat("#7a4b28", { roughness: 0.6 });
  const mPortao = mat("#686e72", { roughness: 0.5, metalness: 0.3 });
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
    const mesh = new THREE.Mesh(geo, mat(w.cor || (w.exterior ? cores.fachada : cores.parede_interior), {}, w.exterior ? w.padrao : null));
    mesh.applyMatrix4(B);
    mesh.castShadow = true; mesh.receiveShadow = true;
    junta(mesh, { tipo: "parede", id: w.id, piso: w.piso });
    for (const v of validos) {
      const larg = v.u1 - v.u0, alt = v.z1 - v.z0;
      const alvo = { tipo: "vao", id: v.id, piso: w.piso };
      const folha = new THREE.Mesh(new THREE.BoxGeometry(larg, alt, 0.04), v.tipo === "porta" ? mPorta : v.tipo === "portao" ? mPortao : mVidro);
      folha.position.set((v.u0 + v.u1) / 2, (v.z0 + v.z1) / 2, 0);
      folha.applyMatrix4(B);
      junta(folha, alvo);
      const mCaix = mat(v.cor || cores.caixilharia, { roughness: 0.4, metalness: 0.3 });
      const aros = [[larg, 0.05, 0, alt / 2], [0.05, alt, larg / 2, 0], [0.05, alt, -larg / 2, 0]];
      if (v.tipo !== "porta" && v.tipo !== "portao") aros.push([larg, 0.05, 0, -alt / 2]);
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
    lj.polys.forEach((anel, n) => {
      const sh = new THREE.Shape(anel.map((p) => new THREE.Vector2(p[0], p[1])));
      for (const furo of lj.furos?.[n] || []) sh.holes.push(new THREE.Path(furo.map((p) => new THREE.Vector2(p[0], p[1]))));   // vazios das escadas
      const geo = new THREE.ExtrudeGeometry(sh, { depth: lj.z1 - lj.z0, bevelEnabled: false });
      geo.rotateX(-Math.PI / 2);
      const mesh = new THREE.Mesh(geo, mat("#c9c7c1", { roughness: 0.9 }));
      mesh.position.y = lj.z0;
      mesh.receiveShadow = true; mesh.castShadow = true;
      grupo.add(mesh);
    });
  });

  // escadas: um bloco por degrau e por patamar, com a espessura de um espelho
  for (const e of derivado.escadas || []) {
    if (ordem[e.piso] > ate) continue;
    const mEsc = mat("#d9d4c8", { roughness: 0.8 });
    for (const peca of [...e.degraus, ...e.patamares]) {
      const geo = new THREE.ExtrudeGeometry(new THREE.Shape(peca.pts.map((p) => new THREE.Vector2(p[0], p[1]))), { depth: e.espelho_m, bevelEnabled: false });
      geo.rotateX(-Math.PI / 2);
      const bloco = new THREE.Mesh(geo, mEsc);
      bloco.position.y = peca.z - e.espelho_m;
      bloco.castShadow = true; bloco.receiveShadow = true;
      junta(bloco, { tipo: "escada", id: e.id, piso: e.piso });
    }
  }

  // cada divisão vestida com os seus acabamentos: pavimento, faces de parede (com os vãos recortados) e teto
  for (const d of derivado.divisoes || []) {
    const k = ordem[d.piso];
    if (k > ate || !d.acabamentos) continue;
    const alvo = { tipo: "divisao", pt: d.centro, piso: d.piso };
    const z0 = d.z0 ?? 0, h = (d.z1 ?? z0 + 2.7) - z0;
    const forma = new THREE.Shape(d.pts.map((p) => new THREE.Vector2(p[0], p[1])));
    const chao = new THREE.ShapeGeometry(forma);
    chao.rotateX(-Math.PI / 2);
    const mChao = new THREE.Mesh(chao, mat(d.acabamentos.pavimento.cor, { roughness: 0.7, side: THREE.DoubleSide }, d.acabamentos.pavimento.padrao));
    mChao.position.y = z0 + 0.012;
    mChao.receiveShadow = true;
    junta(mChao, alvo);
    for (const f of d.faces || []) {
      const L = Math.hypot(f.b[0] - f.a[0], f.b[1] - f.a[1]);
      const ux = (f.b[0] - f.a[0]) / L, uy = (f.b[1] - f.a[1]) / L;
      // 8 mm para dentro da divisão (o contorno roda no sentido anti-horário: o interior fica à esquerda)
      const a = [f.a[0] - uy * 0.008, f.a[1] + ux * 0.008];
      const pele = new THREE.Mesh(new THREE.ShapeGeometry(painel(L, h, 0, f.vaos || [])), mat(d.acabamentos.parede_interior.cor, { side: THREE.DoubleSide }, d.acabamentos.parede_interior.padrao));
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
    const mCob = mat(cores.cobertura, { roughness: 0.8, side: THREE.DoubleSide }, padroes.cobertura);
    for (const f of derivado.cobertura?.faces || []) { const m = new THREE.Mesh(uvPlano(leque(f.pts, f.tris)), mCob); m.castShadow = true; m.receiveShadow = true; grupo.add(m); }
    for (const e of derivado.cobertura?.empenas || []) { const m = new THREE.Mesh(uvPlano(leque(e.pts)), mat(cores.fachada, { side: THREE.DoubleSide }, padroes.fachada)); m.castShadow = true; grupo.add(m); }
  }

  // mobiliário, sanitários e equipamentos: volume de ocupação de cada peça
  for (const o of derivado.objetos || []) {
    if (ordem[o.piso] > ate) continue;
    if (o.tipo === "arvore" || o.tipo === "arbusto") {      // árvore: tronco + copa ; arbusto: copa
      const r = Math.max(0.3, Math.min(o.largura_m, o.prof_m) / 2), h = Math.max(0.5, o.z1 - o.z0);
      const copa = new THREE.Mesh(new THREE.SphereGeometry(r, 18, 12), mat("#5f8f45", { roughness: 1 }, comTexturas ? "relva" : null));
      copa.position.set(o.x, o.z0 + (o.tipo === "arvore" ? h - r : r), -o.y);
      copa.castShadow = true; junta(copa, { tipo: "objeto", id: o.id, piso: o.piso });
      if (o.tipo === "arvore") {
        const tronco = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.18, h - r, 10), mat("#6b4a2f", { roughness: 1 }));
        tronco.position.set(o.x, o.z0 + (h - r) / 2, -o.y); tronco.castShadow = true;
        junta(tronco, { tipo: "objeto", id: o.id, piso: o.piso });
      }
      continue;
    }
    if (o.tipo === "pergola") {                               // pérgola: 4 pilares + ripas
      const h = Math.max(2.2, o.z1 - o.z0), mp = mat("#8a6a4a", { roughness: 0.8 }, comTexturas ? "ripado" : null);
      for (const [px, py] of o.pts) {
        const pil = new THREE.Mesh(new THREE.BoxGeometry(0.12, h, 0.12), mp);
        pil.position.set(px + (o.x - px) * 0.04, o.z0 + h / 2, -(py + (o.y - py) * 0.04)); pil.castShadow = true;
        junta(pil, { tipo: "objeto", id: o.id, piso: o.piso });
      }
      const n = Math.max(4, Math.round(o.largura_m / 0.4));
      const ang = (o.rot || 0) * Math.PI / 180;
      for (let i = 0; i < n; i += 1) {
        const u = -o.largura_m / 2 + (i + 0.5) * (o.largura_m / n);
        const rip = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.12, o.prof_m), mp);
        rip.position.set(o.x + u * Math.cos(ang), o.z0 + h, -(o.y + u * Math.sin(ang))); rip.rotation.y = ang;
        rip.castShadow = true; junta(rip, { tipo: "objeto", id: o.id, piso: o.piso });
      }
      continue;
    }
    const ext = EXTERIOR[o.tipo];
    const alt = ext ? Math.max(0.02, o.z1 - o.z0) : Math.max(0.02, o.z1 - o.z0);
    const geo = new THREE.ExtrudeGeometry(new THREE.Shape(o.pts.map((p) => new THREE.Vector2(p[0], p[1]))), { depth: alt, bevelEnabled: false });
    geo.rotateX(-Math.PI / 2);
    const m = new THREE.Mesh(geo, ext ? mat(ext.cor, { roughness: 0.85, ...(ext.extra || {}) }, comTexturas ? ext.padrao : null) : mat(o.cor, { roughness: 0.75 }));
    m.position.y = o.z0 + 0.014;
    m.castShadow = !ext; m.receiveShadow = true;
    junta(m, { tipo: "objeto", id: o.id, piso: o.piso });
  }
  return grupo;
}

function libertar(grupo) {
  const mats = new Set();
  grupo.traverse((o) => { if (o.geometry) o.geometry.dispose(); if (o.material) mats.add(o.material); });
  mats.forEach((m) => m.dispose());
  Object.values(grupo.userData.texturas || {}).forEach((t) => t.dispose());
}

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const DIA_DO_MES = [21, 52, 80, 111, 141, 172, 202, 233, 264, 294, 325, 355];        // dia 21 de cada mês
const VISTAS = [["perspetiva", "Perspetiva"], ["topo", "Topo"], ["frente", "Frente"], ["tardoz", "Tardoz"], ["esquerda", "Esquerda"], ["direita", "Direita"]];

export default function Estudio3D({ derivado, contexto = null, altura = 420, pisoVisivel = null, onSelecionar = null }) {
  const mount = useRef(null);
  const st = useRef({});
  const aoSelecionar = useRef(onSelecionar);
  aoSelecionar.current = onSelecionar;
  const [erro, setErro] = useState(false);
  const [mes, setMes] = useState(5);                   // junho
  const [hora, setHora] = useState(15);
  const [texturas, setTexturas] = useState(true);
  const [reais, setReais] = useState({});             // fotografias CC0 (/texturas), carregadas uma vez; sem elas: texturas desenhadas
  useEffect(() => { let vivo = true; texturasReais().then((t) => { if (vivo) setReais(t || {}); }); return () => { vivo = false; }; }, []);
  const [aExportar, setAExportar] = useState(false);
  const [visita, setVisita] = useState(false);         // visita virtual: câmara à altura dos olhos, dentro da casa
  const latitude = contexto?.latitude ?? 39.5;         // sem processo georreferenciado: centro de Portugal continental
  const azFrente = contexto?.azimute_frente ?? 180;
  const ps = posicaoSol(latitude, DIA_DO_MES[mes], hora);

  useEffect(() => {
    const el = mount.current;
    if (!el) return undefined;
    let renderer;
    try { renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true }); } catch { setErro(true); return undefined; }
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
    const ceu = new THREE.HemisphereLight(0xeaf3ff, 0x8a8a7a, 1.5);
    const lanterna = new THREE.PointLight(0xfff4e0, 0, 0, 0);        // luz interior da visita virtual (apagada fora dela)
    camera.add(lanterna);
    scene.add(sol, sol.target, ceu, camera);
    const chao = new THREE.Mesh(new THREE.CircleGeometry(120, 48), new THREE.MeshStandardMaterial({ color: 0xb9c7a4, roughness: 1 }));
    chao.rotation.x = -Math.PI / 2; chao.position.y = -0.22; chao.receiveShadow = true;
    scene.add(chao);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.maxPolarAngle = Math.PI / 2.02;
    let raf;
    const loop = () => {
      const v = st.current.visita;
      if (v) {      // à altura dos olhos: a câmara olha na direção (rumo, inclinação) a partir do ponto onde está
        camera.position.set(v.x, v.z + 1.65, -v.y);
        camera.lookAt(v.x + Math.cos(v.rumo) * Math.cos(v.incl), v.z + 1.65 + Math.sin(v.incl), -(v.y + Math.sin(v.rumo) * Math.cos(v.incl)));
      } else controls.update();
      renderer.render(scene, camera); raf = requestAnimationFrame(loop);
    };
    loop();
    const onResize = () => { const ww = el.clientWidth || w; renderer.setSize(ww, altura); camera.aspect = ww / altura; camera.updateProjectionMatrix(); };
    window.addEventListener("resize", onResize);

    // clique (sem arrastar) numa peça → selecionar essa peça no editor
    const raio = new THREE.Raycaster();
    let baixo = null;
    const down = (ev) => { baixo = [ev.clientX, ev.clientY]; ultimo = [ev.clientX, ev.clientY]; };
    let ultimo = null;
    const arrastar = (ev) => {      // na visita, arrastar roda o olhar
      const v = st.current.visita;
      if (!v || !ultimo || !(ev.buttons & 1)) return;
      v.rumo += (ev.clientX - ultimo[0]) * 0.006;      // arrastar para a direita puxa a cena: o olhar vai para a esquerda
      v.incl = Math.max(-1.2, Math.min(1.2, v.incl + (ev.clientY - ultimo[1]) * 0.005));
      ultimo = [ev.clientX, ev.clientY];
    };
    renderer.domElement.addEventListener("pointermove", arrastar);
    const up = (ev) => {
      ultimo = null;
      if (st.current.visita || !baixo || Math.hypot(ev.clientX - baixo[0], ev.clientY - baixo[1]) > 5 || !st.current.grupo) return;
      const r = renderer.domElement.getBoundingClientRect();
      raio.setFromCamera(new THREE.Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1), camera);
      const hit = raio.intersectObjects(st.current.grupo.children, false).find((x) => x.object.userData.alvo);
      if (hit && aoSelecionar.current) aoSelecionar.current(hit.object.userData.alvo);
    };
    renderer.domElement.addEventListener("pointerdown", down);
    renderer.domElement.addEventListener("pointerup", up);

    st.current = { renderer, scene, camera, controls, sol, ceu, lanterna, enquadrado: false };
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
      renderer.domElement.removeEventListener("pointerdown", down);
      renderer.domElement.removeEventListener("pointerup", up);
      renderer.domElement.removeEventListener("pointermove", arrastar);
      controls.dispose();
      if (st.current.grupo) libertar(st.current.grupo);
      if (st.current.lote) libertar(st.current.lote);
      chao.geometry.dispose(); chao.material.dispose();
      renderer.dispose();
      el.innerHTML = "";
      st.current = {};
      setVisita(false);
    };
  }, [altura]);

  useEffect(() => {
    const s = st.current;
    if (!s.scene || !derivado) return;
    if (s.grupo) { s.scene.remove(s.grupo); libertar(s.grupo); }
    s.grupo = construir(derivado, pisoVisivel, texturas, reais);
    s.scene.add(s.grupo);
    const lim = derivado.limites;
    s.centro = lim ? [(lim[0] + lim[2]) / 2, (lim[1] + lim[3]) / 2, Math.max(12, Math.hypot(lim[2] - lim[0], lim[3] - lim[1]) * 1.1)] : [5, 4, 14];
    if (lim && !s.enquadrado) {       // enquadra uma vez; depois a câmara fica onde o utilizador a deixou
      const cx = (lim[0] + lim[2]) / 2, cy = (lim[1] + lim[3]) / 2;
      const raio = Math.max(12, Math.hypot(lim[2] - lim[0], lim[3] - lim[1]) * 1.1);
      s.controls.target.set(cx, 2.5, -cy);
      s.camera.position.set(cx + raio * 0.8, raio * 0.6, -cy + raio * 0.9);
      s.controls.update();
      s.enquadrado = true;
    }
  }, [derivado, pisoVisivel, texturas, altura, reais]);

  // limite do lote do processo (mesmos eixos do modelo) e seta do norte
  useEffect(() => {
    const s = st.current;
    if (!s.scene) return;
    if (s.lote) { s.scene.remove(s.lote); libertar(s.lote); s.lote = null; }
    const g = new THREE.Group();
    const lote = contexto?.lote;
    if (lote?.length >= 3) {
      const pts = [...lote, lote[0]].map((p) => new THREE.Vector3(p[0], -0.19, -p[1]));
      g.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: 0xbe2828 })));
      const sh = new THREE.Shape(lote.map((p) => new THREE.Vector2(p[0], p[1])));
      const geo = new THREE.ShapeGeometry(sh); geo.rotateX(-Math.PI / 2);
      const relva = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: 0xa9c48c, roughness: 1 }));
      relva.position.y = -0.2; relva.receiveShadow = true;
      g.add(relva);
    }
    // norte: no modelo a frente (−y) olha para `azFrente`; o norte fica a (180 − azFrente) do +y
    const lim = derivado?.limites;
    if (lim) {
      const a = ((azFrente + 180) * Math.PI) / 180;          // rumo de +y; norte = rodar −a
      const nx = -Math.sin(a), ny = Math.cos(a);             // vetor norte nos eixos (x, y) do modelo
      const o = new THREE.Vector3(lim[0] - 2.5, 0.05, -(lim[1] - 2.5));
      g.add(new THREE.ArrowHelper(new THREE.Vector3(nx, 0, -ny).normalize(), o, 2.2, 0x1f2933, 0.6, 0.35));
    }
    s.lote = g;
    s.scene.add(g);
  }, [contexto, azFrente, derivado?.limites?.join(","), altura]);       // eslint-disable-line react-hooks/exhaustive-deps

  // sol do dia 21 do mês escolhido, à hora solar escolhida, para a latitude e o rumo do processo
  useEffect(() => {
    const s = st.current;
    if (!s.sol || !s.centro) return;
    const [cx, cy] = s.centro;
    const alt = Math.max(ps.altura, 1.5);
    const v = vetorSol(alt, ps.azimute, azFrente);
    s.sol.target.position.set(cx, 0, -cy);
    s.sol.position.set(cx + v[0] * 90, v[2] * 90, -cy - v[1] * 90);
    const dia = ps.altura > 0;
    s.sol.intensity = dia ? 0.6 + 2.2 * Math.min(1, ps.altura / 35) : 0;
    s.ceu.intensity = dia ? 1.1 + 0.5 * Math.min(1, ps.altura / 35) : 0.35;
    s.scene.background = new THREE.Color(dia ? (ps.altura < 8 ? 0xf2d9c4 : 0xe6eef4) : 0x1c2530);
  }, [ps.altura, ps.azimute, azFrente, derivado, altura]);

  // entra na maior divisão do piso visível (ou do rés-do-chão); sai para a perspetiva
  const alternarVisita = () => {
    const s = st.current;
    if (!s.camera) return;
    if (s.visita) { s.visita = null; s.lanterna.intensity = 0; s.controls.enabled = true; s.camera.fov = 40; s.camera.updateProjectionMatrix(); setVisita(false); verDe("perspetiva"); return; }
    const pid = (derivado.pisos || [])[pisoVisivel ?? 0]?.id;
    const dv = [...(derivado.divisoes || [])].filter((d) => d.piso === pid).sort((a, b) => b.area_m2 - a.area_m2)[0];
    if (!dv) return;
    // começa numa ponta da divisão, a olhar ao comprido dela
    const xs = dv.pts.map((q) => q[0]), ys = dv.pts.map((q) => q[1]);
    const lx = Math.max(...xs) - Math.min(...xs), ly = Math.max(...ys) - Math.min(...ys);
    s.visita = lx >= ly ? { x: Math.min(...xs) + Math.min(0.8, lx * 0.2), y: dv.centro[1], z: dv.z0 ?? 0, rumo: 0, incl: -0.08 }
      : { x: dv.centro[0], y: Math.min(...ys) + Math.min(0.8, ly * 0.2), z: dv.z0 ?? 0, rumo: Math.PI / 2, incl: -0.08 };
    s.lanterna.intensity = 1.6; s.controls.enabled = false; s.camera.fov = 68; s.camera.updateProjectionMatrix();
    setVisita(true);
  };
  const andar = (frente, lado, rodar = 0) => {
    const v = st.current.visita;
    if (!v) return;
    v.rumo += rodar;
    v.x += (Math.cos(v.rumo) * frente + Math.sin(v.rumo) * lado) * 0.4;
    v.y += (Math.sin(v.rumo) * frente - Math.cos(v.rumo) * lado) * 0.4;
  };
  const teclaVisita = (ev) => {
    if (!visita) return;
    const m = { ArrowUp: [1, 0, 0], w: [1, 0, 0], ArrowDown: [-1, 0, 0], s: [-1, 0, 0], ArrowLeft: [0, 0, 0.12], ArrowRight: [0, 0, -0.12], a: [0, -1, 0], d: [0, 1, 0] }[ev.key];
    if (m) { ev.preventDefault(); ev.stopPropagation(); andar(...m); }
  };
  const verDe = (k) => {
    const s = st.current;
    if (!s.camera || !s.centro) return;
    const [cx, cy, r] = s.centro;
    const d = r * 1.25;
    const pos = { perspetiva: [cx + r * 0.8, r * 0.6, -cy + r * 0.9], topo: [cx, d * 1.25, -cy + 0.01], frente: [cx, 3, -cy + d], tardoz: [cx, 3, -cy - d],
      esquerda: [cx - d, 3, -cy], direita: [cx + d, 3, -cy] }[k];
    s.controls.target.set(cx, k === "topo" ? 0 : 2.5, -cy);
    s.camera.position.set(...pos);
    s.controls.update();
  };
  const baixar = (blob, nome) => {
    const u = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = u; a.download = nome; a.click();
    setTimeout(() => URL.revokeObjectURL(u), 4000);
  };
  const imagem = () => {
    const s = st.current;
    if (!s.renderer) return;
    s.renderer.render(s.scene, s.camera);
    s.renderer.domElement.toBlob((b) => b && baixar(b, "estudio-vista-3d.png"), "image/png");
  };
  const capturar = () => new Promise((ok) => {          // vista atual, tal como está no ecrã, para o render fotorrealista
    const s = st.current;
    if (!s.renderer) { ok(null); return; }
    s.renderer.render(s.scene, s.camera);
    s.renderer.domElement.toBlob((b) => ok(b), "image/jpeg", 0.92);
  });
  const glb = async () => {
    const s = st.current;
    if (!s.grupo) return;
    setAExportar(true);
    try {
      const { GLTFExporter } = await import("three/examples/jsm/exporters/GLTFExporter.js");
      const dados = await new Promise((ok, falha) => new GLTFExporter().parse(s.grupo, ok, falha, { binary: true }));
      baixar(new Blob([dados], { type: "model/gltf-binary" }), "estudio-modelo.glb");
    } catch { /* o botão volta ao estado normal; o modelo no ecrã não é afetado */ }
    setAExportar(false);
  };

  if (erro) return <div className="p-6 text-sm text-muted-foreground border rounded">O seu navegador não suporta 3D (WebGL).</div>;
  return (
    <div className="space-y-2">
      <div className="relative outline-none" tabIndex={0} onKeyDown={teclaVisita}>
        <div ref={mount} style={{ width: "100%", height: altura }} className="rounded-lg overflow-hidden border" data-testid="estudio-3d" />
        {visita && (
          <div className="absolute bottom-3 right-3 grid grid-cols-3 gap-1" data-testid="estudio-3d-andar">
            <Button size="sm" variant="secondary" className="h-10 w-10 p-0" onClick={() => andar(0, 0, 0.26)} title="Rodar à esquerda">↺</Button>
            <Button size="sm" variant="secondary" className="h-10 w-10 p-0" onClick={() => andar(1, 0)} title="Avançar" data-andar="frente"><ArrowUp className="h-4 w-4" /></Button>
            <Button size="sm" variant="secondary" className="h-10 w-10 p-0" onClick={() => andar(0, 0, -0.26)} title="Rodar à direita">↻</Button>
            <Button size="sm" variant="secondary" className="h-10 w-10 p-0" onClick={() => andar(0, -1)} title="Passo à esquerda"><ArrowLeft className="h-4 w-4" /></Button>
            <Button size="sm" variant="secondary" className="h-10 w-10 p-0" onClick={() => andar(-1, 0)} title="Recuar"><ArrowDown className="h-4 w-4" /></Button>
            <Button size="sm" variant="secondary" className="h-10 w-10 p-0" onClick={() => andar(0, 1)} title="Passo à direita"><ArrowRight className="h-4 w-4" /></Button>
          </div>
        )}
        {visita && <p className="absolute top-2 left-3 text-[11px] bg-background/80 rounded px-2 py-0.5">Visita virtual · olhos a 1,65 m · arraste para olhar · setas ou botões para andar</p>}
      </div>
      <div className="flex flex-wrap items-center gap-1.5" data-testid="estudio-3d-vistas">
        <Button size="sm" variant={visita ? "default" : "outline"} className="h-7 px-2 text-xs" onClick={alternarVisita} data-testid="estudio-3d-visita"><Footprints className="h-3.5 w-3.5 mr-1" />{visita ? "Sair da visita" : "Visita virtual"}</Button>
        {!visita && VISTAS.map(([k, t]) => <Button key={k} size="sm" variant="outline" className="h-7 px-2 text-xs" onClick={() => verDe(k)} data-vista={k}>{t}</Button>)}
        <label className="text-xs flex items-center gap-1 ml-2"><input type="checkbox" checked={texturas} onChange={(e) => setTexturas(e.target.checked)} data-testid="estudio-3d-texturas" />Texturas</label>
        <span className="ml-auto flex gap-1.5">
          <Button size="sm" variant="outline" className="h-7 px-2 text-xs" onClick={imagem} data-testid="estudio-3d-imagem"><Camera className="h-3.5 w-3.5 mr-1" />Imagem (PNG)</Button>
          <Button size="sm" variant="outline" className="h-7 px-2 text-xs" onClick={glb} disabled={aExportar} data-testid="estudio-3d-glb"><Download className="h-3.5 w-3.5 mr-1" />Modelo 3D (GLB)</Button>
          <RenderFotorrealista capturar={capturar} derivado={derivado} lang="pt" />
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs" data-testid="estudio-3d-sol">
        <Sun className="h-4 w-4 text-amber-600" />
        <select className="border rounded h-7 px-1 bg-background text-foreground" value={mes} onChange={(e) => setMes(Number(e.target.value))} data-testid="estudio-3d-mes">
          {MESES.map((m, i) => <option key={m} value={i}>21 {m}</option>)}
        </select>
        <input type="range" min={5} max={21} step={0.25} value={hora} onChange={(e) => setHora(Number(e.target.value))} className="flex-1 max-w-xs" data-testid="estudio-3d-hora" />
        <span className="text-foreground w-12">{String(Math.floor(hora)).padStart(2, "0")}h{String(Math.round((hora % 1) * 60)).padStart(2, "0")}</span>
        <span className="text-muted-foreground" data-testid="estudio-3d-sol-texto">
          {ps.altura > 0 ? `Sol a ${fmt(ps.altura, 0)}° de altura, azimute ${fmt(ps.azimute, 0)}°` : "Sol abaixo do horizonte"} · hora solar · latitude {fmt(latitude, 2)}°
          {contexto?.azimute_frente == null ? " · frente assumida a sul (sem processo georreferenciado)" : ` · frente a ${fmt(azFrente, 0)}°`}
        </span>
      </div>
    </div>
  );
}
