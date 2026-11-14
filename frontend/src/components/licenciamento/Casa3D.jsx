import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";

/**
 * Casa 3D — modelo à escala real (metros) gerado a partir do MESMO processo que as peças desenhadas:
 * volumes, pisos, cobertura, vãos (janelas/portas), garagem, limite do terreno e relevo.
 * Materiais com texturas procedimentais (granito, madeira, reboco, xisto, tijolo, betão, telha, zinco).
 * Sistema de eixos do processo: x = ao longo da frente, y = para o tardoz → three: x = x, z = -y, y = altura.
 */

function canvasTex(draw, size = 512, repeat = 1) {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const g = c.getContext("2d");
  draw(g, size);
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  t.userData.m = repeat;   // metros cobertos por uma repetição
  return t;
}

const rnd = (seed => () => ((seed = (seed * 16807) % 2147483647) / 2147483647))(42);

const TEX = {
  reboco_branco: () => canvasTex((g, s) => {
    g.fillStyle = "#f1efe9"; g.fillRect(0, 0, s, s);
    for (let i = 0; i < 6000; i++) { const v = 225 + rnd() * 25; g.fillStyle = `rgba(${v},${v},${v - 6},0.35)`; g.fillRect(rnd() * s, rnd() * s, 2, 2); }
  }, 256, 2),
  granito: () => canvasTex((g, s) => {
    // cantaria de granito do Minho: blocos irregulares cinza-amarelados com juntas
    g.fillStyle = "#8d8a82"; g.fillRect(0, 0, s, s);
    const rows = 6; const h = s / rows;
    for (let r = 0; r < rows; r++) {
      let x = -rnd() * 80;
      while (x < s) {
        const w = 70 + rnd() * 110;
        const base = 140 + rnd() * 45;
        g.fillStyle = `rgb(${base + 12},${base + 8},${base - 4})`;
        g.fillRect(x + 3, r * h + 3, w - 6, h - 6);
        for (let i = 0; i < 260; i++) {
          const v = base - 50 + rnd() * 100;
          g.fillStyle = `rgba(${v},${v - 4},${v - 12},0.55)`;
          g.fillRect(x + 3 + rnd() * (w - 6), r * h + 3 + rnd() * (h - 6), 2 + rnd() * 2, 2 + rnd() * 2);
        }
        x += w;
      }
    }
  }, 512, 2.4),
  xisto: () => canvasTex((g, s) => {
    g.fillStyle = "#4b4640"; g.fillRect(0, 0, s, s);
    for (let y = 0; y < s; y += 14 + rnd() * 10) {
      let x = -rnd() * 40;
      while (x < s) { const w = 30 + rnd() * 70; const v = 70 + rnd() * 50; g.fillStyle = `rgb(${v + 10},${v},${v - 10})`;
        g.fillRect(x + 2, y + 2, w - 4, 10 + rnd() * 6); x += w; }
    }
  }, 512, 1.6),
  madeira: () => canvasTex((g, s) => {
    const n = 10; const w = s / n;
    for (let i = 0; i < n; i++) {
      const v = 120 + rnd() * 40;
      g.fillStyle = `rgb(${v + 40},${v},${v - 50})`; g.fillRect(i * w, 0, w - 3, s);
      for (let k = 0; k < 40; k++) { g.strokeStyle = `rgba(80,45,20,${0.08 + rnd() * 0.12})`; g.beginPath();
        const x = i * w + rnd() * w; g.moveTo(x, 0); g.bezierCurveTo(x + 4, s / 3, x - 4, (2 * s) / 3, x + 2, s); g.stroke(); }
      g.fillStyle = "rgba(40,25,10,0.6)"; g.fillRect(i * w + w - 3, 0, 3, s);
    }
  }, 512, 1.5),
  tijolo: () => canvasTex((g, s) => {
    g.fillStyle = "#cfc6b8"; g.fillRect(0, 0, s, s);
    const h = s / 16, w = s / 4;
    for (let r = 0; r < 16; r++) for (let c = -1; c < 5; c++) {
      const v = 150 + rnd() * 40; g.fillStyle = `rgb(${v + 30},${v - 50},${v - 80})`;
      g.fillRect(c * w + (r % 2 ? w / 2 : 0) + 2, r * h + 2, w - 4, h - 4);
    }
  }, 512, 1.2),
  betao: () => canvasTex((g, s) => {
    g.fillStyle = "#a9a7a2"; g.fillRect(0, 0, s, s);
    for (let i = 0; i < 9000; i++) { const v = 150 + rnd() * 40; g.fillStyle = `rgba(${v},${v},${v},0.3)`; g.fillRect(rnd() * s, rnd() * s, 2, 2); }
    g.strokeStyle = "rgba(90,90,90,0.5)"; g.strokeRect(1, 1, s - 2, s / 2 - 2); g.strokeRect(1, s / 2, s - 2, s / 2 - 2);
    [[s * 0.25, s * 0.25], [s * 0.75, s * 0.25], [s * 0.25, s * 0.75], [s * 0.75, s * 0.75]].forEach(([x, y]) => {
      g.fillStyle = "rgba(70,70,70,0.6)"; g.beginPath(); g.arc(x, y, 4, 0, 7); g.fill(); });
  }, 512, 2.4),
  telha_ceramica: () => canvasTex((g, s) => {
    g.fillStyle = "#8c3b22"; g.fillRect(0, 0, s, s);
    const rows = 12, cols = 8, h = s / rows, w = s / cols;
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
      const v = rnd() * 30;
      const grd = g.createLinearGradient(c * w, 0, c * w + w, 0);
      grd.addColorStop(0, `rgb(${150 + v},${62 + v / 2},${38})`); grd.addColorStop(0.5, `rgb(${190 + v},${90 + v / 2},${55})`);
      grd.addColorStop(1, `rgb(${140 + v},${58 + v / 2},${34})`);
      g.fillStyle = grd; g.fillRect(c * w + 1, r * h + 1, w - 2, h - 3);
      g.fillStyle = "rgba(40,15,5,0.45)"; g.fillRect(c * w, r * h + h - 3, w, 3);
    }
  }, 512, 2.2),
  telha_preta: () => canvasTex((g, s) => {
    g.fillStyle = "#2a2b2d"; g.fillRect(0, 0, s, s);
    const rows = 12, cols = 8, h = s / rows, w = s / cols;
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
      const v = 40 + rnd() * 18; g.fillStyle = `rgb(${v},${v},${v + 3})`; g.fillRect(c * w + 1, r * h + 1, w - 2, h - 3);
      g.fillStyle = "rgba(0,0,0,0.5)"; g.fillRect(c * w, r * h + h - 3, w, 3);
    }
  }, 512, 2.2),
  zinco: () => canvasTex((g, s) => {
    g.fillStyle = "#7f8a90"; g.fillRect(0, 0, s, s);
    for (let x = 0; x < s; x += s / 8) { g.fillStyle = "rgba(220,230,235,0.5)"; g.fillRect(x, 0, 4, s); g.fillStyle = "rgba(40,50,55,0.4)"; g.fillRect(x + 4, 0, 2, s); }
  }, 512, 4),
  plana_seixo: () => canvasTex((g, s) => {
    g.fillStyle = "#b6b0a4"; g.fillRect(0, 0, s, s);
    for (let i = 0; i < 4000; i++) { const v = 130 + rnd() * 90; g.fillStyle = `rgb(${v},${v - 6},${v - 14})`; g.beginPath(); g.arc(rnd() * s, rnd() * s, 1 + rnd() * 3, 0, 7); g.fill(); }
  }, 256, 1.5),
  relva: () => canvasTex((g, s) => {
    g.fillStyle = "#5d7d3a"; g.fillRect(0, 0, s, s);
    for (let i = 0; i < 12000; i++) { const v = rnd(); g.fillStyle = `rgba(${60 + v * 60},${100 + v * 70},${40 + v * 30},0.5)`; g.fillRect(rnd() * s, rnd() * s, 1, 3); }
  }, 256, 3),
};

const CAIXILHO = { aluminio_antracite: 0x2f3235, aluminio_branco: 0xf2f2f0, madeira: 0x7a4b28, pvc_branco: 0xf5f5f3 };

function matFor(kind, cache) {
  if (!cache[kind]) {
    const make = TEX[kind] || TEX.reboco_branco;
    const map = make();
    cache[kind] = new THREE.MeshStandardMaterial({ map, roughness: kind.startsWith("telha") || kind === "granito" || kind === "xisto" ? 0.92 : 0.78,
      metalness: kind === "zinco" ? 0.55 : 0.0 });
  }
  return cache[kind];
}

// caixa com UV em metros (para as texturas ficarem à escala real)
function boxUV(geo, mPerRepeat) {
  const pos = geo.attributes.position, nrm = geo.attributes.normal, uv = geo.attributes.uv;
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i), y = pos.getY(i), z = pos.getZ(i);
    const nx = Math.abs(nrm.getX(i)), ny = Math.abs(nrm.getY(i));
    let u, v;
    if (ny > 0.5) { u = x; v = z; } else if (nx > 0.5) { u = z; v = y; } else { u = x; v = y; }
    uv.setXY(i, u / mPerRepeat, v / mPerRepeat);
  }
  uv.needsUpdate = true;
  return geo;
}

function fachadaMats(fachada, piso, cache) {
  if (fachada === "misto_granito_reboco") return piso === 0 ? ["granito"] : ["reboco_branco"];
  if (fachada === "misto_madeira_reboco") return ["reboco_branco"];
  return [fachada || "reboco_branco"];
}

function buildScene(scene, m, cache) {
  const group = new THREE.Group();
  const mats = m.materiais || {};
  const fach = mats.fachada || "reboco_branco";
  const cob = mats.cobertura || "telha_ceramica";
  const est = m.estilo || {};
  const frame = new THREE.MeshStandardMaterial({ color: est.cor_caixilharia || CAIXILHO[mats.caixilharia] || 0x2f3235, roughness: 0.4, metalness: 0.3 });
  const glass = new THREE.MeshPhysicalMaterial({ color: 0x2a3a46, roughness: 0.03, metalness: 0.9, envMapIntensity: 1.6, clearcoat: 1,
    clearcoatRoughness: 0.02 });
  const sh = m.piso_a_piso_m || 3.0;

  // terreno com relevo (cotas relativas à soleira) e relva
  const pts = m.terreno || [];
  if (pts.length >= 3) {
    const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
    const minx = Math.min(...xs) - 8, maxx = Math.max(...xs) + 8, miny = Math.min(...ys) - 8, maxy = Math.max(...ys) + 8;
    const geo = new THREE.PlaneGeometry(maxx - minx, maxy - miny, 48, 48);
    geo.rotateX(-Math.PI / 2);
    geo.translate((minx + maxx) / 2, 0, -(miny + maxy) / 2);
    const grid = m.terreno_grelha || [];
    const zAt = (x, y) => {
      if (!grid.length) return -0.15;
      let num = 0, den = 0;
      for (const q of grid) { const d2 = (q.x - x) ** 2 + (q.y - y) ** 2 + 0.01; const w = 1 / d2; num += w * q.z; den += w; }
      return num / den - 0.15;
    };
    const pos = geo.attributes.position;
    // por baixo das construções o terreno fica à cota da plataforma (escavação / aterro)
    const foot = (m.volumes || []).map(v => { const vx = v.pts.map(p => p[0]), vy = v.pts.map(p => p[1]);
      return [Math.min(...vx) - 0.6, Math.min(...vy) - 0.6, Math.max(...vx) + 0.6, Math.max(...vy) + 0.6]; });
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i), y = -pos.getZ(i);
      const inside = foot.some(([a, b, c, d]) => x >= a && x <= c && y >= b && y <= d);
      pos.setY(i, inside ? -0.15 : zAt(x, y));
    }
    geo.computeVertexNormals();
    const uv = geo.attributes.uv;
    for (let i = 0; i < uv.count; i++) uv.setXY(i, pos.getX(i) / 3, pos.getZ(i) / 3);
    const ground = new THREE.Mesh(geo, matFor("relva", cache));
    ground.receiveShadow = true;
    group.add(ground);
    // limite do terreno
    const line = new THREE.BufferGeometry().setFromPoints([...pts, pts[0]].map(p => new THREE.Vector3(p[0], zAt(p[0], p[1]) + 0.2, -p[1])));
    group.add(new THREE.Line(line, new THREE.LineBasicMaterial({ color: 0xd62828 })));
  }

  // volumes
  for (const v of m.volumes || []) {
    const vx = v.pts.map(p => p[0]), vy = v.pts.map(p => p[1]);
    const x0 = Math.min(...vx), x1 = Math.max(...vx), y0 = Math.min(...vy), y1 = Math.max(...vy);
    const L = x1 - x0, W = y1 - y0;
    const nPisos = v.anexo ? 1 : (m.pisos || 1);
    const hPiso = v.anexo ? v.altura_m : sh;
    for (let p = 0; p < nPisos; p++) {
      const kind = v.anexo ? (fach === "madeira" || fach === "misto_madeira_reboco" ? "madeira" : fach.startsWith("misto_granito") ? "granito" : fachadaMats(fach, 0)[0])
        : fachadaMats(fach, p)[0];
      const mat = matFor(kind, cache);
      if (est.cor_fachada && !v.anexo) mat.color.set(est.cor_fachada);
      const geo = boxUV(new THREE.BoxGeometry(L, hPiso, W), (mat.map.userData.m || 2));
      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set(x0 + L / 2, p * hPiso + hPiso / 2, -(y0 + W / 2));
      mesh.castShadow = mesh.receiveShadow = true;
      group.add(mesh);
      if (!v.anexo && p > 0) {   // friso de laje
        const fr = new THREE.Mesh(new THREE.BoxGeometry(L + 0.06, 0.12, W + 0.06), new THREE.MeshStandardMaterial({ color: 0xdedbd3 }));
        fr.position.set(x0 + L / 2, p * hPiso, -(y0 + W / 2)); group.add(fr);
      }
    }
    if (fach === "misto_madeira_reboco" && !v.anexo) {   // painel ripado na fachada do sol
      const pan = new THREE.Mesh(boxUV(new THREE.BoxGeometry(L * 0.35, nPisos * sh * 0.95, 0.06), 1.5), matFor("madeira", cache));
      pan.position.set(x0 + L * 0.2, nPisos * sh / 2, -(y0) + 0.04); group.add(pan);
    }
    // portão da garagem
    if (v.anexo) {
      const gw = Math.min(L - 0.6, 2.8 * Math.max(1, Math.round(L / 3.3))), gh = 2.3;
      const gate = new THREE.Mesh(new THREE.BoxGeometry(gw, gh, 0.05), new THREE.MeshStandardMaterial({ color: CAIXILHO[mats.caixilharia] || 0x2f3235, roughness: 0.6 }));
      gate.position.set(x0 + L / 2, gh / 2, -y0 + 0.03); group.add(gate);
      for (let k = 1; k < 8; k++) { const ln = new THREE.Mesh(new THREE.BoxGeometry(gw, 0.02, 0.06), new THREE.MeshStandardMaterial({ color: 0x1d1f21 }));
        ln.position.set(x0 + L / 2, (gh * k) / 8, -y0 + 0.04); group.add(ln); }
    }
    // cobertura
    const hTop = nPisos * hPiso;
    const tipoTel = v.anexo ? v.cobertura : (est.telhado || v.cobertura);
    const roofMat = matFor(tipoTel === "plana" ? "plana_seixo" : cob, cache);
    if (est.cor_cobertura && tipoTel !== "plana") roofMat.color.set(est.cor_cobertura);
    const beiralE = est.beiral_m ?? 0.5;
    const rhE = !v.anexo && est.inclinacao_pct != null ? (Math.min(L, W) / 2) * (est.inclinacao_pct / 100) : (v.altura_cobertura_m || 2.0);
    if (tipoTel === "quatro_aguas" && !v.anexo) {
      // telhado de 4 águas: cumeeira ao longo do lado maior, 2 trapézios + 2 triângulos (com beiral)
      const along = L >= W;
      const A = (along ? L : W) / 2 + beiralE, B = (along ? W : L) / 2 + beiralE, r = Math.max(0, A - B);
      const cx = x0 + L / 2, cz = -(y0 + W / 2), y = hTop;
      const P = (u, w_, h) => (along ? [cx + u, y + h, cz + w_] : [cx + w_, y + h, cz + u]);
      const c1 = P(-A, -B, 0), c2 = P(A, -B, 0), c3 = P(A, B, 0), c4 = P(-A, B, 0), r1 = P(-r, 0, rhE), r2 = P(r, 0, rhE);
      const tris = [c1, c2, r2, c1, r2, r1, c3, c4, r1, c3, r1, r2, c2, c3, r2, c4, c1, r1];
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(tris.flat(), 3));
      const rep = roofMat.map.userData.m || 2;
      g.setAttribute("uv", new THREE.Float32BufferAttribute(tris.flatMap(q => [q[0] / rep, (q[2] + q[1]) / rep]), 2));
      g.computeVertexNormals();
      const mesh = new THREE.Mesh(g, roofMat);
      mesh.material.side = THREE.DoubleSide; mesh.castShadow = true; group.add(mesh);
    } else if (tipoTel === "uma_agua" && !v.anexo) {
      const slope = Math.hypot(W + 2 * beiralE, rhE);
      const pl = new THREE.Mesh(boxUV(new THREE.BoxGeometry(L + 2 * beiralE, 0.08, slope), roofMat.map.userData.m || 2), roofMat);
      pl.rotation.x = -Math.atan2(rhE, W + 2 * beiralE);
      pl.position.set(x0 + L / 2, hTop + rhE / 2, -(y0 + W / 2)); pl.castShadow = true; group.add(pl);
    } else if (tipoTel === "plana" || v.altura_cobertura_m <= 0) {
      const plat = new THREE.Mesh(boxUV(new THREE.BoxGeometry(L + 0.1, 0.35, W + 0.1), 1.5), matFor("betao", cache));
      plat.position.set(x0 + L / 2, hTop + 0.17, -(y0 + W / 2)); plat.castShadow = true; group.add(plat);
    } else {
      const rh = v.anexo ? (v.altura_cobertura_m || 2.0) : rhE, beiral = v.anexo ? 0.5 : beiralE;
      const ridgeAlongX = L >= W;
      const half = (ridgeAlongX ? W : L) / 2 + beiral;
      const len = (ridgeAlongX ? L : W) + 2 * beiral;
      const slope = Math.hypot(half, rh);
      const rep = roofMat.map.userData.m || 2;
      const ang = Math.atan2(rh, half - beiral);
      for (const s of [-1, 1]) {
        const geo = ridgeAlongX ? boxUV(new THREE.BoxGeometry(len, 0.08, slope), rep) : boxUV(new THREE.BoxGeometry(slope, 0.08, len), rep);
        const pl = new THREE.Mesh(geo, roofMat);
        if (ridgeAlongX) { pl.rotation.x = s * ang; pl.position.set(x0 + L / 2, hTop + rh / 2, -(y0 + W / 2) + s * (half / 2)); }
        else { pl.rotation.z = -s * ang; pl.position.set(x0 + L / 2 + s * (half / 2), hTop + rh / 2, -(y0 + W / 2)); }
        pl.castShadow = true; group.add(pl);
      }
      // empenas (triângulos)
      const tri = new THREE.Shape();
      const b = ridgeAlongX ? W / 2 : L / 2;
      tri.moveTo(-b, 0); tri.lineTo(b, 0); tri.lineTo(0, rh); tri.lineTo(-b, 0);
      const gmat = matFor(fachadaMats(fach, nPisos - 1)[0], cache);
      for (const s of [-1, 1]) {
        const g = new THREE.Mesh(new THREE.ShapeGeometry(tri), gmat);
        g.material.side = THREE.DoubleSide;
        if (ridgeAlongX) { g.rotation.y = Math.PI / 2; g.position.set(s < 0 ? x0 : x1, hTop, -(y0 + W / 2)); }
        else { g.position.set(x0 + L / 2, hTop, s < 0 ? -y0 : -y1); }
        group.add(g);
      }
    }
  }

  // pavimentos em granito: acesso da garagem e caminho da porta de entrada até à frente do terreno
  const paveMat = matFor("betao", cache);
  const pave = (x0, x1, y0, y1) => {
    if (x1 - x0 < 0.3 || y1 - y0 < 0.3) return;
    const m_ = new THREE.Mesh(boxUV(new THREE.BoxGeometry(x1 - x0, 0.06, y1 - y0), 1.2), paveMat);
    m_.position.set((x0 + x1) / 2, -0.12, -(y0 + y1) / 2); m_.receiveShadow = true; group.add(m_);
  };
  const gar = (m.volumes || []).find(v => v.anexo);
  if (gar) { const gx = gar.pts.map(p => p[0]), gy = gar.pts.map(p => p[1]); pave(Math.min(...gx), Math.max(...gx), 0, Math.min(...gy)); }
  const porta = (m.vaos || []).find(o => o.tipo === "porta");
  const casaV = (m.volumes || []).find(v => !v.anexo);
  if (porta && casaV) { const cy0 = Math.min(...casaV.pts.map(p => p[1])); pave(porta.x0 - 0.3, porta.x1 + 0.3, 0, cy0); }

  // vãos (as mesmas posições das plantas)
  const casa = (m.volumes || []).find(v => !v.anexo);
  if (casa) {
    const vy = casa.pts.map(p => p[1]); const y0 = Math.min(...vy), y1 = Math.max(...vy);
    const vx_ = casa.pts.map(p => p[0]); const cx0 = Math.min(...vx_), cx1 = Math.max(...vx_);
    // frente/tardoz: x ao longo da frente (coordenadas do terreno); esquerda/direita: x = distância desde a frente da casa
    const place = (o, along, y, off) => {
      const lateral = o.fachada === "esquerda" || o.fachada === "direita";
      const s_ = o.fachada === "frente" || o.fachada === "direita" ? 1 : -1;
      const out = lateral ? (o.fachada === "direita" ? cx1 : cx0) + s_ * off : (o.fachada === "frente" ? -y0 : -y1) + s_ * off;
      return lateral ? [out, y, -(y0 + along)] : [along, y, out];
    };
    for (const o of m.vaos || []) {
      const w = o.x1 - o.x0, h = o.z1 - o.z0;
      const lateral = o.fachada === "esquerda" || o.fachada === "direita";
      const rotY = lateral ? Math.PI / 2 : 0;
      const add = (geo, mat, along, y, off) => { const me = new THREE.Mesh(geo, mat); me.position.set(...place(o, along, y, off)); me.rotation.y = rotY; group.add(me); return me; };
      const mid = (o.x0 + o.x1) / 2;
      add(new THREE.BoxGeometry(w + 0.12, h + 0.12, 0.06), frame, mid, o.z0 + h / 2, 0.02);
      add(new THREE.BoxGeometry(w, h, 0.07), o.tipo === "porta" ? new THREE.MeshStandardMaterial({ color: 0x5a3a22, roughness: 0.6 }) : glass, mid, o.z0 + h / 2, 0.03);
      if (o.tipo !== "porta") {   // caixilhos: folhas de ~1,2 m e travessa nas portadas altas
        const folhas = Math.max(1, Math.round(w / 1.2));
        for (let k = 1; k < folhas; k++) add(new THREE.BoxGeometry(0.06, h, 0.09), frame, o.x0 + (w * k) / folhas, o.z0 + h / 2, 0.02);
        if (h > 1.9) add(new THREE.BoxGeometry(w, 0.05, 0.09), frame, mid, o.z0 + h * 0.78, 0.02);
      }
      if (o.z0 > 0.5 && o.tipo !== "porta") {   // peitoril em pedra
        add(new THREE.BoxGeometry(w + 0.2, 0.05, 0.18), new THREE.MeshStandardMaterial({ color: 0xcfcac0 }), mid, o.z0 - 0.03, 0.08);
      }
    }
  }
  group.name = "casa";
  scene.add(group);
  return group;
}

const Casa3D = forwardRef(function Casa3D({ modelo, altura = 520 }, ref) {
  const mount = useRef(null);
  const state = useRef({});
  const [erro, setErro] = useState(false);

  useImperativeHandle(ref, () => ({
    snapshot: () => {
      const s = state.current;
      if (!s.renderer) return null;
      s.renderer.render(s.scene, s.camera);
      return s.renderer.domElement.toDataURL("image/png");
    },
    vista: (nome) => {
      const s = state.current; if (!s.camera) return;
      const c = s.centro || new THREE.Vector3();
      const d = s.raio || 25;
      const v = { frente: [0, 0.35, 1], tardoz: [0, 0.35, -1], aerea: [0.3, 1.4, 0.6], perspetiva: [0.9, 0.45, 1.1] }[nome] || [0.9, 0.45, 1.1];
      s.camera.position.set(c.x + v[0] * d, c.y + v[1] * d, c.z + v[2] * d);
      s.controls.target.copy(c); s.controls.update();
    },
  }));

  // 1) cena, luz, câmara e controlos: uma vez (ou quando muda a altura)
  useEffect(() => {
    const el = mount.current;
    if (!el) return undefined;
    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    } catch { setErro(true); return undefined; }
    const w = el.clientWidth || 800;
    const h0 = el.clientHeight || altura;
    renderer.setSize(w, h0);
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    el.innerHTML = "";
    el.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xcfe3f2);
    scene.fog = new THREE.Fog(0xcfe3f2, 80, 220);
    const camera = new THREE.PerspectiveCamera(40, w / h0, 0.1, 600);
    const pmrem = new THREE.PMREMGenerator(renderer);
    scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environmentIntensity = 0.45;
    renderer.toneMappingExposure = 0.9;
    const sun = new THREE.DirectionalLight(0xfff3df, 2.2);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    Object.assign(sun.shadow.camera, { left: -40, right: 40, top: 40, bottom: -40, near: 1, far: 150 });
    scene.add(sun); scene.add(sun.target);
    scene.add(new THREE.HemisphereLight(0xdfefff, 0x6b7a4a, 0.45));
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.maxPolarAngle = Math.PI / 2.05;
    state.current = { renderer, scene, camera, controls, sun, cache: {}, posta: false };
    let raf;
    const loop = () => { controls.update(); renderer.render(scene, camera); raf = requestAnimationFrame(loop); };
    loop();
    const onResize = () => { const ww = el.clientWidth || w, hh = el.clientHeight || altura; renderer.setSize(ww, hh); camera.aspect = ww / hh; camera.updateProjectionMatrix(); };
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(onResize) : null;
    if (ro) ro.observe(el); else window.addEventListener("resize", onResize);
    return () => {
      cancelAnimationFrame(raf);
      if (ro) ro.disconnect(); else window.removeEventListener("resize", onResize);
      controls.dispose();
      Object.values(state.current.cache || {}).forEach(mt => { mt.map?.dispose(); mt.dispose(); });
      scene.environment?.dispose(); pmrem.dispose();
      renderer.dispose();
      el.innerHTML = "";
      state.current = {};
    };
  }, [altura]);

  // 2) a casa: reconstruída a cada alteração do modelo (a câmara fica onde o utilizador a deixou)
  useEffect(() => {
    const s = state.current;
    if (!s.scene || !modelo) return;
    const old = s.scene.getObjectByName("casa");
    if (old) {
      s.scene.remove(old);
      old.traverse(o => { o.geometry?.dispose(); });
    }
    Object.values(s.cache).forEach(mt => { mt.map?.dispose(); mt.dispose(); });
    s.cache = {};
    buildScene(s.scene, modelo, s.cache);
    const az = (modelo.azimutes || {}).frente ?? 180;
    const rel = THREE.MathUtils.degToRad(180 - az);
    s.sun.position.set(Math.sin(rel) * 40, 38, Math.cos(rel) * 40);
    const casa = (modelo.volumes || [])[0];
    const xs = (modelo.terreno || []).map(p => p[0]), ys = (modelo.terreno || []).map(p => p[1]);
    const centro = casa ? new THREE.Vector3(
      (Math.min(...casa.pts.map(p => p[0])) + Math.max(...casa.pts.map(p => p[0]))) / 2, 3,
      -(Math.min(...casa.pts.map(p => p[1])) + Math.max(...casa.pts.map(p => p[1]))) / 2) : new THREE.Vector3();
    const raio = Math.max(18, Math.max(...xs, 20) * 0.9, Math.max(...ys, 20) * 0.6);
    s.sun.target.position.copy(centro);
    s.centro = centro; s.raio = raio;
    if (!s.posta) {
      s.camera.position.set(centro.x + raio * 0.9, centro.y + raio * 0.45, centro.z + raio * 1.1);
      s.controls.target.copy(centro); s.controls.update();
      s.posta = true;
    }
  }, [modelo]);

  if (erro) return <div className="p-6 text-sm text-muted-foreground border rounded">O seu navegador não suporta 3D (WebGL).</div>;
  return <div ref={mount} style={{ width: "100%", height: altura === "100%" ? "100%" : altura }} className="rounded-lg overflow-hidden border" data-testid="casa-3d" />;
});

export default Casa3D;
