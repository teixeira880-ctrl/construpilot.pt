import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import {
  AlertTriangle, Box, CircleDot, Download, Droplets, FileText, Layers, Loader2, MapPin, Mountain, PenLine, Ruler,
  Search, ShieldCheck, Trash2, TrendingUp,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import Terreno3D from "@/components/mdt/Terreno3D";

/**
 * MDT Portugal — modelo digital do terreno de Portugal continental.
 * Fonte principal: levantamento LiDAR da DGT (MDT 50 cm / 2 m, oficial). Recurso: altimetria indicativa (EU-DEM 25 m).
 * Desenhe o terreno (ou um ponto + raio) → cotas, carta de declives, curvas de nível, linhas de água potenciais,
 * movimentos de terras, perfil e 3D; exportação PDF (cartas), DXF (curvas 3D), GeoTIFF e GeoJSON.
 */

const PT_CENTRO = [39.6, -8.0];
const fmt = (n, d = 2) => (Number.isFinite(n) ? n.toLocaleString("pt-PT", { maximumFractionDigits: d }) : "—");
const CAMADAS = [
  { k: "hipsometria", nome: "Hipsometria", icon: Mountain },
  { k: "declives", nome: "Declives", icon: TrendingUp },
  { k: "sombreado", nome: "Sombreado", icon: Layers },
];

async function descarregar(path, body, nome) {
  const r = await api.post(path, body, { responseType: "blob", timeout: 240000 });
  const u = URL.createObjectURL(r.data);
  const a = document.createElement("a");
  a.href = u; a.download = nome; a.click();
  setTimeout(() => URL.revokeObjectURL(u), 4000);
}

function Stat({ rotulo, valor, sub }) {
  return (
    <div className="rounded-xl border border-border bg-card/70 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{rotulo}</div>
      <div className="text-lg font-semibold leading-tight">{valor}</div>
      {sub && <div className="text-[11px] text-muted-foreground">{sub}</div>}
    </div>
  );
}

export default function MdtPortugal() {
  const el = useRef(null), mapa = useRef(null), grupos = useRef(null), bases = useRef({}), relevoPt = useRef(null);
  const st = useRef({});
  const [estado, setEstado] = useState(null);
  const [modo, setModo] = useState(null);             // terreno | ponto | perfil
  const [pontos, setPontos] = useState([]);           // vértices do terreno em desenho
  const [poligono, setPoligono] = useState(null);     // terreno fechado [[lat, lon]…]
  const [centro, setCentro] = useState(null);
  const [raio, setRaio] = useState(80);
  const [linha, setLinha] = useState([]);
  const [base, setBase] = useState("dgt");
  const [relevo, setRelevo] = useState(true);
  const [q, setQ] = useState("");
  const [local, setLocal] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [camada, setCamada] = useState("hipsometria");
  const [opac, setOpac] = useState(0.75);
  const [verCurvas, setVerCurvas] = useState(true);
  const [verAgua, setVerAgua] = useState(true);
  const [perfil, setPerfil] = useState(null);
  const [malha, setMalha] = useState(null);
  const [exagero, setExagero] = useState(1.5);
  const [cotaPlat, setCotaPlat] = useState("");
  const [exp, setExp] = useState(null);
  st.current = { modo, pontos, linha };

  useEffect(() => { api.get("/mdt/estado").then(({ data }) => setEstado(data)).catch(() => setEstado(null)); }, []);

  // terreno vindo do licenciamento automático (mesmo polígono do processo)
  const loc = useLocation();
  useEffect(() => {
    const pol = loc.state?.poligono;
    if (Array.isArray(pol) && pol.length >= 3) {
      setPoligono(pol.map(([a, b]) => [Number(a), Number(b)]));
      if (loc.state.local) setLocal(loc.state.local);
      const t = setTimeout(() => mapa.current?.fitBounds(L.latLngBounds(pol).pad(0.6)), 50);
      return () => clearTimeout(t);
    }
    return undefined;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const zona = useMemo(() => (poligono ? { poligono } : centro ? { centro, raio_m: raio } : null), [poligono, centro, raio]);

  // --- mapa ------------------------------------------------------------------------------------------
  useEffect(() => {
    if (!el.current || mapa.current) return undefined;
    const m = L.map(el.current, { maxZoom: 21, zoomControl: true, doubleClickZoom: false }).setView(PT_CENTRO, 7);
    bases.current = {
      dgt: L.tileLayer.wms("https://cartografia.dgterritorio.gov.pt/wms/ortos2021?", { layers: "Ortos2021-RGB", format: "image/jpeg", version: "1.3.0", crossOrigin: true, maxZoom: 21, attribution: "© DGT — Ortofotomapas 2021" }),
      esri: L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", { crossOrigin: true, maxNativeZoom: 19, maxZoom: 21, attribution: "Imagem © Esri, Maxar" }),
      mapa: L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 21, maxNativeZoom: 19, attribution: "© OpenStreetMap" }),
    };
    bases.current.dgt.addTo(m);
    // relevo de Portugal inteiro (vista nacional): hipsometria oficial da DGT (WMS); sombreado Esri se a DGT não responder
    const esriRelevo = () => L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Elevation/World_Hillshade/MapServer/tile/{z}/{y}/{x}",
      { maxNativeZoom: 16, maxZoom: 21, opacity: 0.45, attribution: "Relevo © Esri" });
    relevoPt.current = esriRelevo().addTo(m);
    api.get("/mdt/relevo-nacional").then(({ data }) => {
      if (!data?.ok || !mapa.current) return;
      const dgt = L.tileLayer.wms(`${data.url}?`, { layers: data.camada, format: "image/png", transparent: true, version: data.versao, opacity: 0.55, maxZoom: 21, attribution: `© ${data.fonte}` });
      const ativo = mapa.current.hasLayer(relevoPt.current);
      if (ativo) mapa.current.removeLayer(relevoPt.current);
      relevoPt.current = dgt;
      if (ativo) dgt.addTo(mapa.current);
    }).catch(() => {});
    grupos.current = { zona: L.layerGroup().addTo(m), img: L.layerGroup().addTo(m), curvas: L.layerGroup().addTo(m), agua: L.layerGroup().addTo(m), perfil: L.layerGroup().addTo(m) };
    mapa.current = m;
    m.on("click", (e) => {
      const p = [e.latlng.lat, e.latlng.lng], s = st.current;
      if (s.modo === "terreno") setPontos((o) => [...o, p]);
      else if (s.modo === "ponto") { setCentro(p); setPoligono(null); setModo(null); setRes(null); setMalha(null); }
      else if (s.modo === "perfil") setLinha((o) => [...o, p]);
    });
    m.on("dblclick", () => {
      const s = st.current;
      // o duplo clique também gera cliques simples: retirar vértices repetidos (< 0,5 m)
      const pts = s.pontos.filter((p, i, a) => i === 0 || L.latLng(p).distanceTo(L.latLng(a[i - 1])) > 0.5);
      if (s.modo === "terreno" && pts.length >= 3) { setPoligono(pts); setCentro(null); setPontos([]); setModo(null); setRes(null); setMalha(null); }
    });
    return () => { m.remove(); mapa.current = null; };
  }, []);

  useEffect(() => {
    const m = mapa.current; if (!m) return;
    Object.entries(bases.current).forEach(([k, l]) => { if (k === base) { if (!m.hasLayer(l)) l.addTo(m).bringToBack(); } else if (m.hasLayer(l)) m.removeLayer(l); });
  }, [base]);
  useEffect(() => {
    const m = mapa.current, l = relevoPt.current; if (!m || !l) return;
    if (relevo && !m.hasLayer(l)) l.addTo(m); else if (!relevo && m.hasLayer(l)) m.removeLayer(l);
  }, [relevo]);

  // zona desenhada / ponto + raio
  useEffect(() => {
    const g = grupos.current; if (!g) return;
    g.zona.clearLayers();
    if (pontos.length) {
      L.polyline(pontos, { color: "#f0b429", weight: 2, dashArray: "4 4" }).addTo(g.zona);
      pontos.forEach((p) => L.circleMarker(p, { radius: 4, color: "#f0b429", fillOpacity: 1 }).addTo(g.zona));
    }
    if (poligono) L.polygon(poligono, { color: "#d32f2f", weight: 2.5, fillOpacity: 0 }).addTo(g.zona);
    if (centro) {
      L.circle(centro, { radius: raio, color: "#d32f2f", weight: 2, fillOpacity: 0 }).addTo(g.zona);
      L.circleMarker(centro, { radius: 4, color: "#d32f2f", fillOpacity: 1 }).addTo(g.zona);
    }
  }, [pontos, poligono, centro, raio]);

  // resultados no mapa
  useEffect(() => {
    const g = grupos.current; if (!g) return;
    g.img.clearLayers(); g.curvas.clearLayers(); g.agua.clearLayers();
    if (!res) return;
    const c = res.camadas?.[camada];
    if (c) L.imageOverlay(c.png, c.bounds, { opacity: opac, interactive: false }).addTo(g.img);
    if (verCurvas) res.curvas.forEach((cv) => {
      const pl = L.polyline(cv.ll, { color: cv.mestra ? "#3b2f22" : "#6b5a45", weight: cv.mestra ? 1.6 : 0.7, opacity: 0.9 }).addTo(g.curvas);
      pl.bindTooltip(`${fmt(cv.cota)} m`, { sticky: true });
    });
    if (verAgua) {
      const bmax = Math.max(1, ...res.linhas_agua.map((l) => l.bacia_m2));
      res.linhas_agua.forEach((l) => L.polyline(l.ll, { color: "#1565c0", weight: 1.5 + 4 * Math.sqrt(l.bacia_m2 / bmax), opacity: 0.95 })
        .bindTooltip(`Linha de água potencial · bacia ${fmt(l.bacia_m2, 0)} m²`, { sticky: true }).addTo(g.agua));
    }
  }, [res, camada, opac, verCurvas, verAgua]);

  useEffect(() => {
    const g = grupos.current; if (!g) return;
    g.perfil.clearLayers();
    if (linha.length) {
      L.polyline(linha, { color: "#7b1fa2", weight: 3 }).addTo(g.perfil);
      linha.forEach((p, i) => L.circleMarker(p, { radius: 4, color: "#7b1fa2", fillOpacity: 1 }).bindTooltip(i === 0 ? "A" : String.fromCharCode(65 + i)).addTo(g.perfil));
    }
  }, [linha]);

  // --- ações --------------------------------------------------------------------------------------------
  const procurar = async () => {
    if (!q.trim()) return;
    try {
      const { data } = await api.get("/mdt/morada", { params: { q } });
      mapa.current?.setView([data.lat, data.lon], 18);
      setLocal(data.nome || q);
      setCentro([data.lat, data.lon]); setPoligono(null); setRes(null); setMalha(null);
    } catch { toast.error("Morada não encontrada. Indique o ponto diretamente no mapa."); }
  };

  const analisar = useCallback(async (extra = {}) => {
    if (!zona) { toast.error("Desenhe o terreno ou indique um ponto no mapa."); return; }
    setBusy(true); setMalha(null);
    try {
      const body = { ...zona, local, ...extra };
      const { data } = await api.post("/mdt/analise", body, { timeout: 240000 });
      setRes(data);
      setCotaPlat(String(data.movimento_terras?.cota_plataforma ?? ""));
      const b = L.latLngBounds(data.zona);
      mapa.current?.fitBounds(b.pad(0.25));
      (data.meta?.avisos || []).forEach((a) => toast.warning(a));
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Não foi possível calcular o MDT desta zona.");
    } finally { setBusy(false); }
  }, [zona, local]);

  const calcularPerfil = async () => {
    if (linha.length < 2) { toast.error("Marque pelo menos dois pontos da linha de perfil."); return; }
    try {
      const { data } = await api.post("/mdt/perfil", { linha }, { timeout: 180000 });
      setPerfil(data); setModo(null);
    } catch (e) { toast.error(e?.response?.data?.detail || "Perfil indisponível."); }
  };

  const ver3d = async () => {
    if (!zona) return;
    try {
      const { data } = await api.post("/mdt/3d", { ...zona }, { timeout: 240000 });
      setMalha(data);
    } catch (e) { toast.error(e?.response?.data?.detail || "Modelo 3D indisponível."); }
  };

  const exportar = async (fmtx, nome) => {
    if (!zona) return;
    setExp(fmtx);
    try { await descarregar(`/mdt/exportar/${fmtx}`, { ...zona, local, cota_plataforma: cotaPlat ? Number(cotaPlat) : undefined }, nome); }
    catch { toast.error("Exportação falhou."); }
    finally { setExp(null); }
  };

  const limpar = () => { setPontos([]); setPoligono(null); setCentro(null); setLinha([]); setRes(null); setPerfil(null); setMalha(null); setModo(null); };

  const est = res?.estatisticas, mt = res?.movimento_terras, meta = res?.meta;

  return (
    <div className="space-y-4 p-4 md:p-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-widest text-[#b8733a]"><Mountain className="h-4 w-4" /> Modelo digital do terreno</div>
          <h1 className="text-2xl md:text-3xl font-bold">MDT Portugal</h1>
          <p className="text-sm text-muted-foreground max-w-3xl">
            Todo o território de Portugal continental com o levantamento LiDAR da DGT (50 cm / 2 m). Desenhe o terreno e obtenha cotas,
            carta de declives, curvas de nível, linhas de água, movimentos de terras, perfil e 3D.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {estado?.lidar_dgt
            ? <Badge className="bg-emerald-700 hover:bg-emerald-700"><ShieldCheck className="mr-1 h-3.5 w-3.5" />LiDAR DGT oficial ativo</Badge>
            : estado && <Badge variant="outline" className="border-amber-500 text-amber-700"><AlertTriangle className="mr-1 h-3.5 w-3.5" />LiDAR DGT por configurar · altimetria indicativa</Badge>}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
        <Card className="overflow-hidden p-0">
          <div className="flex flex-wrap items-center gap-2 border-b border-border p-2">
            <div className="flex min-w-[260px] flex-1 gap-1">
              <Input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && procurar()} placeholder="Morada, localidade ou concelho…" className="h-9" />
              <Button size="sm" variant="outline" onClick={procurar}><Search className="h-4 w-4" /></Button>
            </div>
            <Button size="sm" variant={modo === "terreno" ? "default" : "outline"} onClick={() => { setModo(modo === "terreno" ? null : "terreno"); setPontos([]); }}>
              <PenLine className="mr-1 h-4 w-4" />Desenhar terreno
            </Button>
            <Button size="sm" variant={modo === "ponto" ? "default" : "outline"} onClick={() => setModo(modo === "ponto" ? null : "ponto")}>
              <CircleDot className="mr-1 h-4 w-4" />Ponto + raio
            </Button>
            <Button size="sm" variant={modo === "perfil" ? "default" : "outline"} onClick={() => { setModo(modo === "perfil" ? null : "perfil"); setLinha([]); setPerfil(null); }}>
              <Ruler className="mr-1 h-4 w-4" />Perfil
            </Button>
            <Button size="sm" variant="ghost" onClick={limpar}><Trash2 className="h-4 w-4" /></Button>
          </div>
          <div className="relative">
            <div ref={el} className="h-[560px] w-full" data-testid="mdt-mapa" />
            {modo && (
              <div className="absolute left-1/2 top-3 z-[500] -translate-x-1/2 rounded-full bg-black/75 px-4 py-1.5 text-xs text-white">
                {modo === "terreno" && (pontos.length < 3 ? "Clique nos vértices do terreno…" : "Duplo clique para fechar o terreno")}
                {modo === "ponto" && "Clique no centro da zona a analisar"}
                {modo === "perfil" && (linha.length < 2 ? "Clique no início e no fim do perfil…" : (
                  <button type="button" className="underline" onClick={calcularPerfil}>Calcular perfil ({linha.length} pontos)</button>))}
              </div>
            )}
            <div className="absolute bottom-3 left-3 z-[500] flex flex-col gap-1 rounded-lg bg-white/90 p-2 text-xs shadow">
              <div className="flex gap-1">
                {[["dgt", "Ortofoto DGT"], ["esri", "Satélite"], ["mapa", "Mapa"]].map(([k, n]) => (
                  <button key={k} type="button" onClick={() => setBase(k)} className={`rounded px-2 py-0.5 ${base === k ? "bg-[#1F4D3A] text-white" : "bg-muted"}`}>{n}</button>
                ))}
              </div>
              <label className="flex items-center gap-1"><input type="checkbox" checked={relevo} onChange={(e) => setRelevo(e.target.checked)} /> Relevo de Portugal</label>
            </div>
          </div>
          {centro && !poligono && (
            <div className="flex items-center gap-3 border-t border-border px-3 py-2 text-sm">
              <span className="text-muted-foreground">Raio</span>
              <input type="range" min={20} max={1400} step={10} value={raio} onChange={(e) => setRaio(Number(e.target.value))} className="flex-1" />
              <span className="w-16 text-right font-medium">{raio} m</span>
            </div>
          )}
        </Card>

        <div className="space-y-3">
          <Card className="p-4 space-y-3">
            <Button className="w-full bg-[#1F4D3A] hover:bg-[#173b2c]" disabled={!zona || busy} onClick={() => analisar()}>
              {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Mountain className="mr-2 h-4 w-4" />}
              {busy ? "A calcular o MDT…" : "Analisar o terreno"}
            </Button>
            {!zona && <p className="text-xs text-muted-foreground">Procure a morada ou use «Desenhar terreno» / «Ponto + raio» no mapa.</p>}
            {meta && (
              <div className={`rounded-lg p-2 text-xs ${meta.oficial ? "bg-emerald-50 text-emerald-900" : "bg-amber-50 text-amber-900"}`}>
                <div className="font-semibold">{meta.oficial ? `MDT LiDAR DGT · ${meta.colecao}` : "Altimetria indicativa"}</div>
                <div>{meta.fonte} · grelha {fmt(meta.resolucao_m)} m</div>
              </div>
            )}
          </Card>

          {est && (
            <Card className="p-4 space-y-3">
              <div className="grid grid-cols-2 gap-2">
                <Stat rotulo="Cota mín. / máx." valor={`${fmt(est.cota_min, 1)} / ${fmt(est.cota_max, 1)} m`} />
                <Stat rotulo="Desnível" valor={`${fmt(est.desnivel)} m`} />
                <Stat rotulo="Declive médio" valor={`${fmt(est.declive_medio_pct, 1)} %`} sub={`máx. ${fmt(est.declive_max_pct, 1)} %`} />
                <Stat rotulo="Exposição" valor={est.exposicao} sub={`${fmt(est.area_m2, 0)} m²`} />
              </div>
              <div>
                <div className="mb-1 text-xs font-semibold">Carta de declives</div>
                <div className="flex h-3 w-full overflow-hidden rounded-full">
                  {res.classes_declive.map((c) => <div key={c.classe} style={{ width: `${c.pct}%`, background: c.cor }} title={`${c.classe}: ${c.pct} %`} />)}
                </div>
                <div className="mt-1 grid grid-cols-2 gap-x-2 text-[11px]">
                  {res.classes_declive.filter((c) => c.pct > 0).map((c) => (
                    <div key={c.classe} className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-sm" style={{ background: c.cor }} />{c.classe.split(" · ")[0]} · {c.pct} %</div>
                  ))}
                </div>
              </div>
              <div className="flex flex-wrap gap-1">
                {CAMADAS.map(({ k, nome, icon: I }) => (
                  <Button key={k} size="sm" variant={camada === k ? "default" : "outline"} className="h-7 px-2 text-xs" onClick={() => setCamada(k)}><I className="mr-1 h-3 w-3" />{nome}</Button>
                ))}
              </div>
              <div className="flex items-center gap-2 text-xs">
                <span>Opacidade</span>
                <input type="range" min={0} max={1} step={0.05} value={opac} onChange={(e) => setOpac(Number(e.target.value))} className="flex-1" />
              </div>
              <div className="flex gap-3 text-xs">
                <label className="flex items-center gap-1"><input type="checkbox" checked={verCurvas} onChange={(e) => setVerCurvas(e.target.checked)} /> Curvas de nível ({fmt(meta?.equidistancia)} m)</label>
                <label className="flex items-center gap-1"><input type="checkbox" checked={verAgua} onChange={(e) => setVerAgua(e.target.checked)} /><Droplets className="h-3 w-3 text-blue-700" /> Linhas de água ({res.linhas_agua.length})</label>
              </div>
            </Card>
          )}

          {mt?.ok && (
            <Card className="p-4 space-y-2">
              <div className="text-sm font-semibold">Movimento de terras (plataforma)</div>
              <div className="flex items-center gap-2 text-sm">
                <span className="text-muted-foreground">Cota da plataforma</span>
                <Input className="h-8 w-24" value={cotaPlat} onChange={(e) => setCotaPlat(e.target.value)} />
                <span>m</span>
                <Button size="sm" variant="outline" className="h-8" onClick={() => analisar({ cota_plataforma: Number(cotaPlat) })}>Recalcular</Button>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <Stat rotulo="Escavação" valor={`${fmt(mt.escavacao_m3, 0)} m³`} sub={`até ${fmt(mt.altura_max_escavacao)} m`} />
                <Stat rotulo="Aterro" valor={`${fmt(mt.aterro_m3, 0)} m³`} sub={`até ${fmt(mt.altura_max_aterro)} m`} />
              </div>
              <div className="text-[11px] text-muted-foreground">Cota de equilíbrio: {fmt(mt.cota_equilibrio)} m. {mt.nota}</div>
            </Card>
          )}

          {res && (
            <Card className="p-4 space-y-2">
              {res.recomendacoes.map((r) => <div key={r} className="flex gap-2 text-xs"><AlertTriangle className="h-4 w-4 shrink-0 text-amber-600" />{r}</div>)}
              <div className="grid grid-cols-2 gap-2 pt-1">
                <Button size="sm" onClick={() => exportar("pdf", "Carta_declives_e_recursos_hidricos.pdf")} disabled={!!exp}>
                  {exp === "pdf" ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <FileText className="mr-1 h-4 w-4" />}Cartas PDF
                </Button>
                <Button size="sm" variant="outline" onClick={() => exportar("dxf", "Curvas_de_nivel.dxf")} disabled={!!exp}><Download className="mr-1 h-4 w-4" />DXF</Button>
                <Button size="sm" variant="outline" onClick={() => exportar("tif", "MDT.tif")} disabled={!!exp}><Download className="mr-1 h-4 w-4" />GeoTIFF</Button>
                <Button size="sm" variant="outline" onClick={() => exportar("geojson", "Terreno_MDT.geojson")} disabled={!!exp}><Download className="mr-1 h-4 w-4" />GeoJSON</Button>
              </div>
              <Button size="sm" variant="secondary" className="w-full" onClick={ver3d}><Box className="mr-1 h-4 w-4" />Ver em 3D</Button>
            </Card>
          )}
        </div>
      </div>

      {perfil && (
        <Card className="p-4">
          <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
            <div className="font-semibold">Perfil longitudinal</div>
            <div className="text-xs text-muted-foreground">
              {fmt(perfil.comprimento_m, 1)} m · cotas {fmt(perfil.z_min, 1)}–{fmt(perfil.z_max, 1)} m · declive médio {fmt(perfil.declive_medio_pct, 1)} % · {perfil.meta?.oficial ? "LiDAR DGT" : "indicativo"}
            </div>
          </div>
          <div className="h-56">
            <ResponsiveContainer>
              <AreaChart data={perfil.pontos} margin={{ left: 0, right: 12, top: 6, bottom: 0 }}>
                <defs><linearGradient id="gp" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#b8733a" stopOpacity={0.7} /><stop offset="100%" stopColor="#1F4D3A" stopOpacity={0.15} /></linearGradient></defs>
                <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                <XAxis dataKey="d" type="number" domain={["dataMin", "dataMax"]} tickFormatter={(v) => `${Math.round(v)} m`} fontSize={11} />
                <YAxis domain={["auto", "auto"]} tickFormatter={(v) => `${Math.round(v)}`} fontSize={11} width={44} />
                <Tooltip formatter={(v) => [`${fmt(v)} m`, "Cota"]} labelFormatter={(d) => `${fmt(d, 1)} m`} />
                <Area type="monotone" dataKey="z" stroke="#1F4D3A" fill="url(#gp)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}

      {malha && (
        <Card className="p-4 space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="font-semibold flex items-center gap-2"><Box className="h-4 w-4" />Terreno 3D <span className="text-xs font-normal text-muted-foreground">{fmt(malha.largura_m, 0)} × {fmt(malha.altura_m, 0)} m · grelha {fmt(malha.dx)} m</span></div>
            <label className="flex items-center gap-2 text-xs">Exagero vertical
              <input type="range" min={1} max={5} step={0.5} value={exagero} onChange={(e) => setExagero(Number(e.target.value))} /> ×{exagero}
            </label>
          </div>
          <Terreno3D malha={malha} exagero={exagero} />
        </Card>
      )}

      <p className="text-[11px] text-muted-foreground flex items-center gap-1">
        <MapPin className="h-3 w-3" />
        Fonte: DGT — levantamento LiDAR de Portugal continental (CC-BY-4.0), ETRS89/PT-TM06. As linhas de água são talvegues potenciais derivados do MDT;
        confirmar a rede hidrográfica e o domínio hídrico junto da APA. Não substitui o levantamento topográfico do projeto.
      </p>
    </div>
  );
}
