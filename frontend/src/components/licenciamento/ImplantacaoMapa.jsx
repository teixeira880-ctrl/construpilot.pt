import { useCallback, useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { Camera, Check, Crosshair, ExternalLink, Loader2, Move, PenLine, RotateCcw, Wand2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

/**
 * Editor de implantação sobre o ortofotomapa real.
 * - Imagem oficial (DGT Ortos 2021, WMS) ou satélite (Esri); Street View e Google Earth no ponto exato.
 * - Parcela: vem do processo (cadastro ou hipótese), pode ser detetada na imagem com um clique, desenhada ou acertada.
 * - Casa + garagem arrastáveis; verificação em direto dos afastamentos com a MESMA regra do motor
 *   (frente e tardoz medidos no sentido da profundidade, laterais ao limite), linhas vermelhas com a medida em falta.
 * - «Aplicar ao processo» manda a parcela, a frente e a posição ao motor, que refaz plantas, 3D, quadro e peças.
 */

const CORES = { limite: "#f5efe3", frente: "#b8733a", zona: "#f0b429", ok: "#2f7d5f", mal: "#c43c33" };

// --- geometria em metros (projeção local, erro < 1 cm a 100 m) ----------------------------------
function proj(o) {
  const kx = 111320 * Math.cos((o[0] * Math.PI) / 180), ky = 111320;
  return { xy: ([la, lo]) => [(lo - o[1]) * kx, (la - o[0]) * ky], ll: ([x, y]) => [o[0] + y / ky, o[1] + x / kx] };
}
const sub = (a, b) => [a[0] - b[0], a[1] - b[1]];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1];
const len = (a) => Math.hypot(a[0], a[1]);
const unit = (a) => { const l = len(a) || 1; return [a[0] / l, a[1] / l]; };
function closest(p, a, b) {
  const ab = sub(b, a), t = Math.max(0, Math.min(1, dot(sub(p, a), ab) / (dot(ab, ab) || 1)));
  return [a[0] + ab[0] * t, a[1] + ab[1] * t];
}
function cruza(p1, p2, p3, p4) {
  const d = (p2[0] - p1[0]) * (p4[1] - p3[1]) - (p2[1] - p1[1]) * (p4[0] - p3[0]);
  if (!d) return false;
  const u = ((p3[0] - p1[0]) * (p4[1] - p3[1]) - (p3[1] - p1[1]) * (p4[0] - p3[0])) / d;
  const v = ((p3[0] - p1[0]) * (p2[1] - p1[1]) - (p3[1] - p1[1]) * (p2[0] - p1[0])) / d;
  return u > 0 && u < 1 && v > 0 && v < 1;
}
function dentro(p, poly) {
  let r = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const a = poly[i], b = poly[j];
    if ((a[1] > p[1]) !== (b[1] > p[1]) && p[0] < ((b[0] - a[0]) * (p[1] - a[1])) / (b[1] - a[1]) + a[0]) r = !r;
  }
  return r;
}
const area = (poly) => Math.abs(poly.reduce((s, p, i) => { const q = poly[(i + 1) % poly.length]; return s + p[0] * q[1] - q[0] * p[1]; }, 0)) / 2;

/** Referencial da frente (igual ao motor): ey = normal ao limite da frente, para dentro do terreno. */
function referencial(P, fi) {
  const n = P.length, a = P[fi], b = P[(fi + 1) % n], u = unit(sub(b, a));
  const c = [P.reduce((s, p) => s + p[0], 0) / n, P.reduce((s, p) => s + p[1], 0) / n];
  let ey = [-u[1], u[0]];
  if (dot(sub(c, [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]), ey) < 0) ey = [u[1], -u[0]];
  const ex = [ey[1], -ey[0]];
  return { ex, ey, loc: (p) => [dot(p, ex), dot(p, ey)], en: ([x, y]) => [ex[0] * x + ey[0] * y, ex[1] * x + ey[1] * y] };
}

/** Verificação com a regra do motor: dentro do terreno, frente/tardoz na profundidade, laterais ao limite. */
function verificar(P, fi, casas, af) {
  if (P.length < 3 || !casas.length) return null;
  const R = referencial(P, fi), PL = P.map(R.loc), HL = casas.flat().map(R.loc);
  const pMin = Math.min(...PL.map((p) => p[1])), pMax = Math.max(...PL.map((p) => p[1]));
  const hMin = Math.min(...HL.map((p) => p[1])), hMax = Math.max(...HL.map((p) => p[1]));
  const arestas = P.map((a, i) => [a, P[(i + 1) % P.length]]);
  const fora = casas.some((c) => c.some((p) => !dentro(p, P)) || c.some((p, i) => arestas.some(([a, b]) => cruza(p, c[(i + 1) % c.length], a, b))));
  let lat = { d: Infinity };
  for (const c of casas) for (const [a, b] of arestas) {
    for (const p of c) { const q = closest(p, a, b), d = len(sub(p, q)); if (d < lat.d) lat = { d, p, q }; }
    for (const p of [a, b]) for (let i = 0; i < c.length; i++) { const q = closest(p, c[i], c[(i + 1) % c.length]), d = len(sub(p, q)); if (d < lat.d) lat = { d, p: q, q: p }; }
  }
  // pontos para desenhar as cotas de frente e tardoz (do ponto da casa mais próximo, a direito)
  const pFr = HL.reduce((m, p) => (p[1] < m[1] ? p : m)), pTz = HL.reduce((m, p) => (p[1] > m[1] ? p : m));
  const items = [
    { k: "frente", nome: "Afastamento à frente (via)", d: hMin - pMin, min: af.frontal, a: R.en(pFr), b: R.en([pFr[0], pMin]) },
    { k: "lateral", nome: "Afastamento lateral (o menor)", d: lat.d, min: af.lateral, a: lat.p, b: lat.q },
    { k: "tardoz", nome: "Afastamento ao tardoz", d: pMax - hMax, min: af.tardoz, a: R.en(pTz), b: R.en([pTz[0], pMax]) },
  ].map((x) => ({ ...x, ok: !fora && x.d >= x.min - 0.01 }));
  return { fora, items, ok: !fora && items.every((x) => x.ok), centro: R.en([(Math.min(...HL.map((p) => p[0])) + Math.max(...HL.map((p) => p[0]))) / 2, (hMin + hMax) / 2]) };
}

const fmt = (n) => (Number.isFinite(n) ? n.toLocaleString("pt-PT", { maximumFractionDigits: 2 }) : "—");

export default function ImplantacaoMapa({ pid, auto, onAplicado }) {
  const el = useRef(null), mapa = useRef(null), camadas = useRef({}), grupos = useRef(null);
  const o = useRef(null), st = useRef({});
  const [P, setP] = useState([]);                 // parcela em metros
  const [fi, setFi] = useState(0);                // índice do limite da frente
  const [casas, setCasas] = useState([]);         // polígonos casa + garagem em metros
  const [zona, setZona] = useState([]);           // zona edificável (lat/lon) — calculada pelo motor
  const [base, setBase] = useState("dgt");
  const [modo, setModo] = useState(null);         // varinha | desenhar | frente
  const [desenho, setDesenho] = useState([]);
  const [tol, setTol] = useState(38);
  const [msg, setMsg] = useState("");
  const [mudou, setMudou] = useState(false);
  const [aplicar, setAplicar] = useState(false);
  const [sv, setSv] = useState(null);             // fotografia real da rua
  const alv = auto?.alvos?.valores || {};
  const af = { frontal: alv.afastamento_frontal_min_m ?? 5, lateral: alv.afastamento_lateral_min_m ?? 3, tardoz: alv.afastamento_tardoz_min_m ?? 6 };
  st.current = { P, fi, casas, modo, desenho, tol, base };

  // --- dados do processo → estado local -----------------------------------------------------------
  useEffect(() => {
    const pll = auto?.terreno?.poligono_latlon || [];
    if (pll.length < 3) return;
    o.current = proj(pll[0]);
    setP(pll.map(o.current.xy));
    const pm = auto.terreno.poligono_m || [];      // a frente é o limite em y ≈ 0 do referencial do motor
    let best = 0, bd = Infinity;
    pm.forEach((p, i) => { const q = pm[(i + 1) % pm.length], d = Math.max(Math.abs(p[1]), Math.abs(q[1])); if (d < bd) { bd = d; best = i; } });
    setFi(best);
    setCasas((auto.casa_latlon || []).map((c) => c.map(o.current.xy)));
    setMudou(false);
  }, [auto]);

  // --- mapa -------------------------------------------------------------------------------------
  useEffect(() => {
    if (!el.current || mapa.current) return;
    const m = L.map(el.current, { maxZoom: 21, zoomControl: true });
    camadas.current = {
      dgt: L.tileLayer.wms("https://ortos.dgterritorio.gov.pt/wms/ortosat2023?", { layers: "ortoSat2023-CorVerdadeira", format: "image/jpeg", version: "1.3.0", crossOrigin: true, maxZoom: 21, attribution: "© DGT — OrtoSat 2023 (30 cm, CC BY 4.0)" }),
      o21: L.tileLayer.wms("https://cartografia.dgterritorio.gov.pt/wms/ortos2021?", { layers: "Ortos2021-RGB", format: "image/jpeg", version: "1.3.0", crossOrigin: true, maxZoom: 21, attribution: "© DGT — Ortofotomapas 2021" }),
      esri: L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", { crossOrigin: true, maxNativeZoom: 19, maxZoom: 21, attribution: "Imagem © Esri, Maxar" }),
    };
    camadas.current.dgt.addTo(m);
    let falhas = 0;   // OrtoSat 2023 em baixo (ou sem CORS) → passa sozinho para os Ortos 2021 da DGT
    camadas.current.dgt.on("tileerror", () => { if (st.current.base === "dgt" && ++falhas === 4) { setBase("o21"); setMsg("O OrtoSat 2023 da DGT não respondeu: a mostrar os Ortos 2021 (DGT)."); } });
    grupos.current = { base: L.layerGroup().addTo(m), zona: L.layerGroup().addTo(m), casa: L.layerGroup().addTo(m), cotas: L.layerGroup().addTo(m), pontos: L.layerGroup().addTo(m) };
    mapa.current = m;
    const pll = auto?.terreno?.poligono_latlon;
    if (pll?.length) m.fitBounds(L.latLngBounds(pll).pad(0.6)); else m.setView([39.6, -8.0], 7);
    m.on("click", (ev) => clique(ev));
    return () => { m.remove(); mapa.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const m = mapa.current; if (!m) return;
    Object.entries(camadas.current).forEach(([k, l]) => { if (k === base) { if (!m.hasLayer(l)) l.addTo(m).bringToBack(); } else if (m.hasLayer(l)) m.removeLayer(l); });
  }, [base]);

  // --- zona edificável: pedida ao motor (mesma regra), quando a parcela ou a frente mudam ------------
  useEffect(() => {
    if (P.length < 3 || !o.current) return undefined;
    const t = setTimeout(() => {
      api.post("/urbanismo-auto/zona", { parcela_latlon: P.map(o.current.ll), frente_idx: fi, frontal_m: af.frontal, lateral_m: af.lateral, tardoz_m: af.tardoz })
        .then(({ data }) => setZona(data.zona_latlon || [])).catch(() => setZona([]));
    }, 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [P, fi, af.frontal, af.lateral, af.tardoz]);

  // --- fotografia real da rua -----------------------------------------------------------------------
  useEffect(() => {
    let u = null, vivo = true;
    api.get(`/urbanismo-auto/processos/${pid}/streetview.jpg`, { responseType: "blob", timeout: 60000 })
      .then((r) => { if (!vivo) return; u = URL.createObjectURL(r.data); setSv({ url: u, data: r.headers?.["x-streetview-data"] }); })
      .catch(() => setSv(false));
    return () => { vivo = false; if (u) URL.revokeObjectURL(u); };
  }, [pid]);

  const v = verificar(P, fi, casas, af);

  // --- desenho ----------------------------------------------------------------------------------------
  useEffect(() => {
    const m = mapa.current, g = grupos.current, pr = o.current;
    if (!m || !g || !pr) return;
    Object.values(g).forEach((l) => l.clearLayers());
    if (P.length >= 3) {
      L.polygon(P.map(pr.ll), { color: CORES.limite, weight: 2, fillOpacity: 0.05, interactive: false }).addTo(g.base);
      L.polyline([P[fi], P[(fi + 1) % P.length]].map(pr.ll), { color: CORES.frente, weight: 6, interactive: false }).addTo(g.base)
        .bindTooltip("Frente (via)", { permanent: true, direction: "center", className: "cp-lbl" });
      P.forEach((p, i) => {
        const mk = L.marker(pr.ll(p), { draggable: true, icon: L.divIcon({ className: "", html: '<div class="cp-vtx"></div>', iconSize: [14, 14], iconAnchor: [7, 7] }) }).addTo(g.pontos);
        mk.on("dragend", (e) => { const q = pr.xy([e.target.getLatLng().lat, e.target.getLatLng().lng]); setP((old) => old.map((x, j) => (j === i ? q : x))); setMudou(true); });
      });
    }
    zona.forEach((a) => L.polygon(a, { color: CORES.zona, weight: 2, dashArray: "6 5", fillColor: CORES.zona, fillOpacity: 0.1, interactive: false }).addTo(g.zona));
    if (desenho.length) L.polyline(desenho.map(pr.ll), { color: CORES.frente, weight: 2, dashArray: "4 4" }).addTo(g.base);
    if (casas.length) {
      const cor = v?.ok ? CORES.ok : CORES.mal;
      casas.forEach((c, i) => {
        const pg = L.polygon(c.map(pr.ll), { color: "#fff", weight: 2, fillColor: cor, fillOpacity: i === 0 ? 0.65 : 0.45 }).addTo(g.casa);
        pg.bindTooltip(i === 0 ? "Casa — arraste para mover" : "Garagem", { sticky: true });
        pg.on("mousedown", (e) => arrastar(e));
      });
      (v?.items || []).forEach((x) => {
        if (!Number.isFinite(x.d)) return;
        const linha = L.polyline([x.a, x.b].map(pr.ll), { color: x.ok ? "#ffffff" : CORES.mal, weight: x.ok ? 1.5 : 3, dashArray: "4 4", interactive: false }).addTo(g.cotas);
        linha.bindTooltip(x.ok ? `${fmt(x.d)} m` : `${fmt(x.d)} m < ${fmt(x.min)} m`, { permanent: true, direction: "center", className: x.ok ? "cp-lbl" : "cp-lbl cp-mal" });
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [P, fi, casas, zona, desenho, v?.ok, JSON.stringify(v?.items?.map((x) => x.d))]);

  // --- arrastar a casa e a garagem em conjunto (alinhadas com a via, como nas peças desenhadas) ----------
  const arrastar = useCallback((e) => {
    const m = mapa.current, pr = o.current;
    L.DomEvent.stop(e); m.dragging.disable();
    const ini = pr.xy([e.latlng.lat, e.latlng.lng]), orig = st.current.casas;
    const mover = (ev) => { const p = pr.xy([ev.latlng.lat, ev.latlng.lng]), d = sub(p, ini); setCasas(orig.map((c) => c.map((q) => [q[0] + d[0], q[1] + d[1]]))); };
    const largar = () => { m.off("mousemove", mover); m.off("mouseup", largar); document.removeEventListener("mouseup", largar); m.dragging.enable(); setMudou(true); };
    m.on("mousemove", mover); m.on("mouseup", largar); document.addEventListener("mouseup", largar);
  }, []);

  // --- cliques no mapa conforme o modo ---------------------------------------------------------------
  function clique(ev) {
    const { modo: md, P: PP } = st.current, pr = o.current || (o.current = proj([ev.latlng.lat, ev.latlng.lng]));
    const p = pr.xy([ev.latlng.lat, ev.latlng.lng]);
    if (md === "varinha") detetar(ev.containerPoint);
    else if (md === "desenhar") setDesenho((d) => [...d, p]);
    else if (md === "frente" && PP.length > 2) {
      let b = 0, bd = Infinity;
      PP.forEach((a, i) => { const d = len(sub(p, closest(p, a, PP[(i + 1) % PP.length]))); if (d < bd) { bd = d; b = i; } });
      setFi(b); setModo(null); setMudou(true); setMsg("Frente definida: os afastamentos foram recalculados.");
    }
  }

  // deteção da parcela na imagem: cresce a região de cor/textura semelhante a partir do clique até muros e sebes
  function detetar(cp) {
    const m = mapa.current;
    if (m.getZoom() < 18) { setMsg("Aproxime o mapa (zoom 18 ou mais) e clique de novo no meio do terreno."); return; }
    const sz = m.getSize(), cv = document.createElement("canvas"); cv.width = sz.x; cv.height = sz.y;
    const ctx = cv.getContext("2d"), R = m.getContainer().getBoundingClientRect();
    camadas.current[st.current.base].getContainer().querySelectorAll("img.leaflet-tile-loaded").forEach((img) => {
      const r = img.getBoundingClientRect(); ctx.drawImage(img, r.left - R.left, r.top - R.top, r.width, r.height);
    });
    let dados;
    try { dados = ctx.getImageData(0, 0, cv.width, cv.height); } catch { setMsg("Esta imagem não permite a deteção automática: mude para «Satélite» e clique de novo."); return; }
    const W = cv.width, H = cv.height, px = dados.data, x0 = Math.round(cp.x), y0 = Math.round(cp.y);
    let sr = 0, sg = 0, sb = 0, n = 0;
    for (let dy = -3; dy <= 3; dy++) for (let dx = -3; dx <= 3; dx++) { const k = ((y0 + dy) * W + x0 + dx) * 4; sr += px[k]; sg += px[k + 1]; sb += px[k + 2]; n++; }
    sr /= n; sg /= n; sb /= n;
    const t2 = st.current.tol ** 2, visto = new Uint8Array(W * H), pilha = [y0 * W + x0], max = W * H * 0.6;
    let cont = 0;
    while (pilha.length) {
      const i = pilha.pop(); if (visto[i]) continue;
      const k = i * 4, r = px[k] - sr, g = px[k + 1] - sg, b = px[k + 2] - sb;
      if (r * r + g * g + b * b > t2) continue;
      visto[i] = 1; if (++cont > max) break;
      const x = i % W, y = (i / W) | 0;
      if (x > 0) pilha.push(i - 1); if (x < W - 1) pilha.push(i + 1); if (y > 0) pilha.push(i - W); if (y < H - 1) pilha.push(i + W);
    }
    if (cont < 300 || cont > max) { setMsg(cont > max ? "A zona encontrada é grande demais: baixe a sensibilidade." : "Zona demasiado pequena: suba a sensibilidade ou clique numa parte mais uniforme do terreno."); return; }
    const pr = o.current, pts = [];
    for (let y = 1; y < H - 1; y += 2) for (let x = 1; x < W - 1; x += 2) {
      const i = y * W + x;
      if (visto[i] && (!visto[i - 1] || !visto[i + 1] || !visto[i - W] || !visto[i + W])) { const l = m.containerPointToLatLng([x, y]); pts.push(pr.xy([l.lat, l.lng])); }
    }
    const casco = simplificar(envolvente(pts), 0.8);
    if (casco.length < 3) { setMsg("Não consegui fechar o contorno: desenhe a parcela à mão."); return; }
    aplicarParcela(casco);
    setMsg(`Parcela detetada na imagem (${fmt(area(casco))} m²). Acerte os pontos se for preciso e confirme com a caderneta.`);
  }

  function aplicarParcela(nova) {
    const pr = o.current, c = st.current.casas;
    setP(nova); setModo(null); setDesenho([]); setMudou(true);
    let b = 0, bd = Infinity;             // frente: limite mais próximo da morada
    const mo = auto?.localizacao ? pr.xy([auto.localizacao.lat, auto.localizacao.lon]) : nova[0];
    nova.forEach((a, i) => { const d = len(sub(mo, closest(mo, a, nova[(i + 1) % nova.length]))); if (d < bd) { bd = d; b = i; } });
    setFi(b);
    if (c.length) { // leva a casa para o centro da nova parcela, mantendo a forma
      const cx = nova.reduce((s, p) => s + p[0], 0) / nova.length, cy = nova.reduce((s, p) => s + p[1], 0) / nova.length;
      const pts = c.flat(), hx = pts.reduce((s, p) => s + p[0], 0) / pts.length, hy = pts.reduce((s, p) => s + p[1], 0) / pts.length;
      setCasas(c.map((h) => h.map((q) => [q[0] + cx - hx, q[1] + cy - hy])));
    }
  }

  async function enviar(posicaoAuto) {
    setAplicar(true); setMsg("");
    try {
      const pr = o.current;
      const body = { parcela_latlon: P.map(pr.ll), frente_idx: fi, casa_centro_latlon: posicaoAuto || !v ? [] : pr.ll(v.centro) };
      const { data } = await api.post(`/urbanismo-auto/processos/${pid}/refazer`, body, { timeout: 180000 });
      if (!data.ok) setMsg(data.motivo || (data.perguntas || []).join(" ") || "O motor não aceitou esta implantação.");
      else { setMsg(posicaoAuto ? "Casa posicionada pelo motor: plantas, 3D e peças atualizados." : "Implantação aplicada: plantas, 3D e peças atualizados."); setMudou(false); await onAplicado?.(); }
    } catch (e) { setMsg(e?.response?.data?.detail || "Não foi possível aplicar agora."); }
    setAplicar(false);
  }

  function captar() {
    const m = mapa.current, sz = m.getSize(), cv = document.createElement("canvas"); cv.width = sz.x; cv.height = sz.y;
    const ctx = cv.getContext("2d"), R = m.getContainer().getBoundingClientRect(), pr = o.current;
    camadas.current[base].getContainer().querySelectorAll("img.leaflet-tile-loaded").forEach((img) => { const r = img.getBoundingClientRect(); ctx.drawImage(img, r.left - R.left, r.top - R.top, r.width, r.height); });
    const caminho = (pts) => { ctx.beginPath(); pts.forEach((p, i) => { const c = m.latLngToContainerPoint(pr.ll(p)); i ? ctx.lineTo(c.x, c.y) : ctx.moveTo(c.x, c.y); }); ctx.closePath(); };
    if (P.length > 2) { caminho(P); ctx.strokeStyle = CORES.limite; ctx.lineWidth = 3; ctx.stroke(); }
    casas.forEach((c) => { caminho(c); ctx.fillStyle = v?.ok ? "rgba(47,125,95,.7)" : "rgba(196,60,51,.7)"; ctx.fill(); ctx.strokeStyle = "#fff"; ctx.lineWidth = 2; ctx.stroke(); });
    ctx.fillStyle = "rgba(20,27,24,.85)"; ctx.fillRect(0, cv.height - 26, cv.width, 26); ctx.fillStyle = "#fff"; ctx.font = "12px sans-serif";
    const c = m.getCenter();
    ctx.fillText(`ConstruPilot · ${base === "dgt" ? "DGT OrtoSat 2023" : base === "o21" ? "Ortofotomapa DGT 2021" : "Imagem Esri"} · ${c.lat.toFixed(6)}, ${c.lng.toFixed(6)} · ${new Date().toLocaleDateString("pt-PT")}`, 10, cv.height - 9);
    try {
      cv.toBlob((b) => { const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = "implantacao-ortofoto.png"; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 4000); });
    } catch { setMsg("Esta imagem não permite captura: mude para «Satélite» e tente de novo."); }
  }

  const centro = P.length && o.current ? o.current.ll([P.reduce((s, p) => s + p[0], 0) / P.length, P.reduce((s, p) => s + p[1], 0) / P.length]) : null;
  const toggle = (k, texto) => { setModo((m) => (m === k ? null : k)); setDesenho([]); if (texto) setMsg(texto); };

  return (
    <div className="grid lg:grid-cols-3 gap-0" data-testid="lic-auto-implantacao">
      <style>{`.cp-lbl{background:rgba(20,27,24,.85);color:#fff;border:0;font:600 11px ui-monospace,monospace;padding:2px 6px;border-radius:4px;box-shadow:none}
        .cp-lbl:before{display:none}.cp-mal{background:${CORES.mal}}
        .cp-vtx{width:14px;height:14px;border-radius:50%;background:#fff;border:2px solid ${CORES.frente};cursor:grab}`}</style>
      <div className="lg:col-span-2 relative">
        <div ref={el} className="h-[460px] w-full" style={{ cursor: modo ? "crosshair" : undefined }} />
        <div className="absolute top-2 right-2 z-[500] flex rounded-md overflow-hidden border bg-background text-xs">
          {[["dgt", "OrtoSat 2023"], ["o21", "Ortos 2021"], ["esri", "Satélite"]].map(([k, t]) => (
            <button type="button" key={k} onClick={() => setBase(k)} className={`px-2 py-1 ${base === k ? "bg-primary text-primary-foreground" : ""}`}>{t}</button>
          ))}
        </div>
      </div>
      <div className="p-4 space-y-4 border-t lg:border-t-0 lg:border-l text-sm">
        <div className={`rounded-md px-3 py-2 font-medium text-white ${v ? (v.ok ? "bg-emerald-700" : "bg-red-700") : "bg-muted-foreground"}`} data-testid="lic-auto-implantacao-estado">
          {!v ? "Sem casa no terreno" : v.ok ? "Cumpre os afastamentos" : v.fora ? "A casa sai do terreno" : "Não cumpre os afastamentos"}
        </div>
        {v && (
          <div className="space-y-1">
            {v.items.map((x) => (
              <div key={x.k} className={`flex justify-between gap-2 ${x.ok ? "" : "text-red-600 font-medium"}`}>
                <span>{x.nome}</span><span className="tabular-nums">{fmt(x.d)} / {fmt(x.min)} m</span>
              </div>
            ))}
            <p className="text-xs text-muted-foreground">Linha amarela tracejada: até onde pode construir. {P.length > 2 && `Terreno ${fmt(area(P))} m².`}</p>
          </div>
        )}
        <div className="space-y-2">
          <div className="font-medium">Terreno</div>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant={modo === "varinha" ? "default" : "outline"} onClick={() => toggle("varinha", "Clique no meio do seu terreno: a deteção segue a imagem até aos muros, caminhos e sebes.")}><Wand2 className="h-4 w-4 mr-1" />Detetar</Button>
            <Button size="sm" variant={modo === "desenhar" ? "default" : "outline"} onClick={() => toggle("desenhar", "Clique em cada canto do terreno, por ordem, e depois em «Concluir».")}><PenLine className="h-4 w-4 mr-1" />Desenhar</Button>
            {modo === "desenhar" && <Button size="sm" disabled={desenho.length < 3} onClick={() => aplicarParcela(desenho)}><Check className="h-4 w-4 mr-1" />Concluir</Button>}
            <Button size="sm" variant={modo === "frente" ? "default" : "outline"} onClick={() => toggle("frente", "Clique junto ao limite que dá para a rua.")}><Crosshair className="h-4 w-4 mr-1" />Frente</Button>
          </div>
          {modo === "varinha" && (
            <label className="flex items-center gap-2 text-xs text-muted-foreground">Sensibilidade
              <input type="range" min="15" max="80" value={tol} onChange={(e) => setTol(+e.target.value)} className="flex-1" /></label>
          )}
          <p className="text-xs text-muted-foreground">Arraste os pontos brancos para acertar os limites. Confirme sempre com a caderneta predial ou o BUPi.</p>
        </div>
        <div className="space-y-2">
          <div className="font-medium flex items-center gap-1"><Move className="h-4 w-4" />Casa</div>
          <p className="text-xs text-muted-foreground">Arraste a casa no mapa. Fica sempre alinhada com a rua, como nas peças desenhadas.</p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => enviar(false)} disabled={aplicar || !mudou || !v?.ok} data-testid="lic-auto-implantacao-aplicar">
              {aplicar ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Check className="h-4 w-4 mr-1" />}Aplicar ao processo</Button>
            <Button size="sm" variant="outline" onClick={() => enviar(true)} disabled={aplicar || P.length < 3}><RotateCcw className="h-4 w-4 mr-1" />Posicionar automaticamente</Button>
          </div>
          {mudou && v && !v.ok && <p className="text-xs text-red-600">Mova a casa para dentro da zona amarela para poder aplicar, ou use «Posicionar automaticamente».</p>}
        </div>
        {msg && <p className="text-xs rounded border-l-2 border-amber-500 bg-amber-50 dark:bg-amber-950/30 px-2 py-1.5">{msg}</p>}
        <div className="space-y-2">
          <div className="font-medium">Imagens reais</div>
          {sv && <figure><img src={sv.url} alt="Fotografia da rua virada para o terreno" className="w-full rounded" />
            <figcaption className="text-[11px] text-muted-foreground mt-1">Google Street View{sv.data ? ` · ${sv.data}` : ""}</figcaption></figure>}
          <div className="flex flex-wrap gap-2">
            {centro && <Button asChild size="sm" variant="outline"><a href={`https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${centro[0].toFixed(6)},${centro[1].toFixed(6)}`} target="_blank" rel="noopener noreferrer"><ExternalLink className="h-4 w-4 mr-1" />Street View</a></Button>}
            {centro && <Button asChild size="sm" variant="outline"><a href={`https://earth.google.com/web/@${centro[0].toFixed(6)},${centro[1].toFixed(6)},150a,300d,35y,0h,45t,0r`} target="_blank" rel="noopener noreferrer"><ExternalLink className="h-4 w-4 mr-1" />Google Earth</a></Button>}
            <Button size="sm" variant="outline" onClick={captar}><Camera className="h-4 w-4 mr-1" />Captar vista aérea</Button>
          </div>
        </div>
        <p className="text-[11px] text-muted-foreground">Afastamentos {fmt(af.frontal)} / {fmt(af.lateral)} / {fmt(af.tardoz)} m: {auto?.alvos?.origem?.afastamento_frontal_min_m === "PDM" ? "valores do PDM" : "alvos prudentes, a confirmar no regulamento do PDM"}. Nunca menos de 1,5 m ao vizinho com janelas (Código Civil, art. 1360.º).</p>
      </div>
    </div>
  );
}

/** Envolvente convexa (Andrew) e simplificação Douglas-Peucker, em metros. */
function envolvente(pts) {
  const p = [...pts].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  if (p.length < 3) return p;
  const x = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lo = [], hi = [];
  for (const q of p) { while (lo.length >= 2 && x(lo[lo.length - 2], lo[lo.length - 1], q) <= 0) lo.pop(); lo.push(q); }
  for (const q of [...p].reverse()) { while (hi.length >= 2 && x(hi[hi.length - 2], hi[hi.length - 1], q) <= 0) hi.pop(); hi.push(q); }
  return lo.slice(0, -1).concat(hi.slice(0, -1));
}
function simplificar(anel, tol) {
  if (anel.length < 4) return anel;
  const dp = (pts) => {
    if (pts.length < 3) return pts;
    let im = 0, dm = 0;
    for (let i = 1; i < pts.length - 1; i++) { const d = len(sub(pts[i], closest(pts[i], pts[0], pts[pts.length - 1]))); if (d > dm) { dm = d; im = i; } }
    return dm > tol ? dp(pts.slice(0, im + 1)).slice(0, -1).concat(dp(pts.slice(im))) : [pts[0], pts[pts.length - 1]];
  };
  return dp([...anel, anel[0]]).slice(0, -1);
}
