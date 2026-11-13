import { useCallback, useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import {
  AlertTriangle, CheckCircle2, Crosshair, Download, ExternalLink, FileUp, Info, Layers, Loader2, MapPin, MousePointerClick,
  PenLine, Plus, Radar, RotateCcw, Save, Search, Trash2, Undo2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { api, num } from "@/lib/api";

/**
 * Terrenos — identificação e análise de prédios sobre fontes oficiais.
 * Mapa: OrtoSat 2023 da DGT (cobertura oficial mais recente, 30 cm) + RGG do BUPi (eBUPi, dados abertos, atualização diária).
 * Delimitação: desenho no mapa, GPS no local (média de leituras), importação KML/KMZ/GPX/GeoJSON, limite do cadastro.
 * Análise do polígono inteiro: CAOP/DICOFRE, cadastro, RGG já existentes, PDM, RAN/REN/domínio hídrico, declives.
 * Exportação KML (a importar no BUPi), GeoJSON e quadro de vértices PT-TM06.
 */

const COR = { limite: "#b8733a", cad: "#38bdf8", ok: "#2f7d5f", mal: "#c43c33" };
const BUPI_WMS = "https://geo.bupi.gov.pt/gisbupi/services/opendata/RGG_DadosGovPT/MapServer/WMSServer";
const BUPI_WMS_MADEIRA = "https://geo.bupi.gov.pt/gisbupi/services/opendata/RGG_DadosGovPT_Madeira/MapServer/WMSServer";
const ORIGEM = { desenho: "Desenhado no mapa", gps: "Percorrido com GPS", importacao: "Importado", cadastro: "Limite do cadastro", rgg: "RGG" };
const TEMAS = [["caop", "Freguesia (CAOP)"], ["cadastro", "Cadastro"], ["bupi", "RGG do BUPi"], ["pdm", "PDM"], ["servidoes", "RAN, REN e servidões"], ["declives", "Declives"]];
const pct = (f) => `${num((f || 0) * 100, 1)} %`;

async function descarregar(path, nome) {
  const r = await api.get(path, { responseType: "blob", timeout: 60000 });
  const u = URL.createObjectURL(r.data);
  const a = document.createElement("a");
  a.href = u; a.download = nome; a.click();
  setTimeout(() => URL.revokeObjectURL(u), 4000);
}

const erroTxt = (e, d) => e?.response?.data?.detail && typeof e.response.data.detail === "string" ? e.response.data.detail : d;

export default function Terrenos() {
  const el = useRef(null), mapa = useRef(null), grupos = useRef(null), camadas = useRef({}), modoRef = useRef("ver");
  const [lista, setLista] = useState([]);
  const [sel, setSel] = useState(null);            // terreno gravado aberto
  const [pts, setPts] = useState([]);              // vértices em edição [lat, lon]
  const [nome, setNome] = useState("");
  const [artigo, setArtigo] = useState("");
  const [origem, setOrigem] = useState("desenho");
  const [modo, setModo] = useState("ver");         // ver | desenhar | consultar | gps
  const [med, setMed] = useState(null);
  const [medErro, setMedErro] = useState(null);
  const [mudou, setMudou] = useState(false);
  const [base, setBase] = useState("dgt");
  const [verRgg, setVerRgg] = useState(true);
  const [ocupado, setOcupado] = useState("");
  const [msg, setMsg] = useState(null);
  const [consulta, setConsulta] = useState(null);
  const [importados, setImportados] = useState(null);
  const [gps, setGps] = useState(null);            // {lat, lon, acc}
  const leituras = useRef([]);
  const watch = useRef(null);
  const ficheiro = useRef(null);

  const carregarLista = useCallback(() => api.get("/terrenos").then(({ data }) => setLista(data.terrenos || [])).catch(() => {}), []);
  useEffect(() => { carregarLista(); }, [carregarLista]);
  useEffect(() => { modoRef.current = modo; }, [modo]);

  // ---------------------------------------------------------------- mapa
  useEffect(() => {
    if (!el.current || mapa.current) return undefined;
    const m = L.map(el.current, { maxZoom: 21, zoomControl: true }).setView([39.6, -8.0], 7);
    camadas.current = {
      dgt: L.tileLayer.wms("https://ortos.dgterritorio.gov.pt/wms/ortosat2023?", { layers: "ortoSat2023-CorVerdadeira", format: "image/jpeg", version: "1.3.0", maxZoom: 21, attribution: "© DGT — OrtoSat 2023 (30 cm, CC BY 4.0)" }),
      o21: L.tileLayer.wms("https://cartografia.dgterritorio.gov.pt/wms/ortos2021?", { layers: "Ortos2021-RGB", format: "image/jpeg", version: "1.3.0", crossOrigin: true, maxZoom: 21, attribution: "© DGT — Ortofotomapas 2021" }),
      esri: L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", { crossOrigin: true, maxNativeZoom: 19, maxZoom: 21, attribution: "Imagem © Esri, Maxar" }),
      rgg: L.layerGroup([
        L.tileLayer.wms(`${BUPI_WMS}?`, { layers: "0", format: "image/png", transparent: true, version: "1.3.0", crs: L.CRS.EPSG4326, minZoom: 13, maxZoom: 21, opacity: 0.85, attribution: "RGG © eBUPi (dados abertos)" }),
        L.tileLayer.wms(`${BUPI_WMS_MADEIRA}?`, { layers: "0", format: "image/png", transparent: true, version: "1.3.0", crs: L.CRS.EPSG4326, minZoom: 13, maxZoom: 21, opacity: 0.85 }),
      ]),
    };
    camadas.current.dgt.addTo(m);
    camadas.current.rgg.addTo(m);
    let falhas = 0;   // OrtoSat 2023 em baixo → passa sozinho para os Ortos 2021 (DGT)
    camadas.current.dgt.on("tileerror", () => { if (++falhas === 4) { setBase("o21"); setMsg({ t: "info", x: "O OrtoSat 2023 da DGT não respondeu: a mostrar os Ortos 2021 (DGT)." }); } });
    grupos.current = { terreno: L.layerGroup().addTo(m), vertices: L.layerGroup().addTo(m), extra: L.layerGroup().addTo(m), gps: L.layerGroup().addTo(m) };
    m.on("click", (ev) => clique(ev.latlng));
    mapa.current = m;
    return () => { m.remove(); mapa.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const m = mapa.current; if (!m) return;
    ["dgt", "o21", "esri"].forEach((k) => { const l = camadas.current[k]; if (k === base) { if (!m.hasLayer(l)) l.addTo(m).bringToBack(); } else if (m.hasLayer(l)) m.removeLayer(l); });
  }, [base]);
  useEffect(() => {
    const m = mapa.current, l = camadas.current.rgg; if (!m || !l) return;
    if (verRgg && !m.hasLayer(l)) l.addTo(m); else if (!verRgg && m.hasLayer(l)) m.removeLayer(l);
  }, [verRgg]);

  // ---------------------------------------------------------------- desenho do terreno
  useEffect(() => {
    const g = grupos.current; if (!g) return;
    g.terreno.clearLayers(); g.vertices.clearLayers();
    if (pts.length >= 2) {
      const forma = pts.length >= 3 ? L.polygon(pts, { color: COR.limite, weight: 3, fillOpacity: 0.12, interactive: false })
        : L.polyline(pts, { color: COR.limite, weight: 3, dashArray: "6 6", interactive: false });
      forma.addTo(g.terreno);
    }
    const lados = med?.vertices_tm06 || [];
    pts.forEach((p, i) => {
      const mk = L.marker(p, { draggable: modo !== "consultar", icon: L.divIcon({ className: "", html: `<div class="tp-vtx">${i + 1}</div>`, iconSize: [20, 20], iconAnchor: [10, 10] }) }).addTo(g.vertices);
      mk.on("dragend", (e) => { const q = e.target.getLatLng(); setPts((o) => o.map((x, j) => (j === i ? [q.lat, q.lng] : x))); setMudou(true); });
      mk.on("contextmenu", () => { setPts((o) => o.filter((_, j) => j !== i)); setMudou(true); });
      if (pts.length >= 3 && lados[i]) {
        const q = pts[(i + 1) % pts.length];
        L.marker([(p[0] + q[0]) / 2, (p[1] + q[1]) / 2], { interactive: false, icon: L.divIcon({ className: "", html: `<div class="tp-lbl">${num(lados[i].lado_m, 2)} m</div>`, iconSize: [0, 0] }) }).addTo(g.vertices);
      }
    });
  }, [pts, med, modo]);

  // medição oficial (PT-TM06) em direto
  useEffect(() => {
    if (pts.length < 3) { setMed(null); setMedErro(null); return undefined; }
    const t = setTimeout(() => {
      api.post("/terrenos/medir", { anel_latlon: pts })
        .then(({ data }) => { setMed(data); setMedErro(null); })
        .catch((e) => { setMed(null); setMedErro(erroTxt(e, "Limites inválidos.")); });
    }, 300);
    return () => clearTimeout(t);
  }, [pts]);

  const enquadrar = (p) => { if (mapa.current && p?.length) mapa.current.fitBounds(L.latLngBounds(p).pad(0.5), { maxZoom: 19 }); };

  // ---------------------------------------------------------------- cliques
  const clique = useCallback(async (ll) => {
    const md = modoRef.current;
    if (md === "desenhar") {
      if ((mapa.current?.getZoom() ?? 0) < 15) { setMsg({ t: "info", x: "Aproxime o mapa até ver as estremas do terreno (zoom de rua) antes de marcar os vértices." }); return; }
      setPts((o) => [...o, [ll.lat, ll.lng]]); setMudou(true); return;
    }
    if (md !== "consultar") return;
    setConsulta({ aCarregar: true, latlon: [ll.lat, ll.lng] });
    try {
      const { data } = await api.get("/terrenos/consulta/ponto", { params: { lat: ll.lat, lon: ll.lng }, timeout: 60000 });
      setConsulta({ ...data, latlon: [ll.lat, ll.lng] });
      const g = grupos.current;
      g.extra.clearLayers();
      if (data.cadastro?.anel_latlon?.length) L.polygon(data.cadastro.anel_latlon, { color: COR.cad, weight: 2, dashArray: "4 4", fillOpacity: 0.08, interactive: false }).addTo(g.extra);
      L.circleMarker([ll.lat, ll.lng], { radius: 5, color: "#fff", fillColor: COR.cad, fillOpacity: 1 }).addTo(g.extra);
    } catch (e) {
      setConsulta({ erro: erroTxt(e, "Consulta indisponível."), latlon: [ll.lat, ll.lng] });
    }
  }, []);

  // ---------------------------------------------------------------- GPS no local
  const pararGps = () => { if (watch.current != null) navigator.geolocation.clearWatch(watch.current); watch.current = null; setGps(null); grupos.current?.gps.clearLayers(); };
  const iniciarGps = () => {
    if (!navigator.geolocation) { setMsg({ t: "erro", x: "Este dispositivo não tem GPS disponível no navegador." }); return; }
    setModo("gps"); setOrigem("gps"); leituras.current = [];
    watch.current = navigator.geolocation.watchPosition((p) => {
      const g = { lat: p.coords.latitude, lon: p.coords.longitude, acc: p.coords.accuracy };
      leituras.current = [...leituras.current.slice(-9), g];
      setGps(g);
      const gr = grupos.current; if (!gr) return;
      gr.gps.clearLayers();
      L.circle([g.lat, g.lon], { radius: g.acc, color: "#3b82f6", weight: 1, fillOpacity: 0.12, interactive: false }).addTo(gr.gps);
      L.circleMarker([g.lat, g.lon], { radius: 6, color: "#fff", weight: 2, fillColor: "#3b82f6", fillOpacity: 1 }).addTo(gr.gps);
      if (mapa.current && mapa.current.getZoom() < 17) mapa.current.setView([g.lat, g.lon], 19);
    }, (e) => setMsg({ t: "erro", x: `GPS: ${e.message}` }), { enableHighAccuracy: true, maximumAge: 0, timeout: 20000 });
  };
  const marcarVertice = () => {
    // média pesada (1/precisão²) das últimas leituras: reduz o erro de um telemóvel parado no marco
    const ls = leituras.current.filter((g) => g.acc <= 30);
    if (!ls.length) { setMsg({ t: "erro", x: "Precisão do GPS insuficiente (> 30 m). Aguarde uns segundos ao ar livre." }); return; }
    let sw = 0, la = 0, lo = 0;
    ls.forEach((g) => { const w = 1 / Math.max(1, g.acc) ** 2; sw += w; la += g.lat * w; lo += g.lon * w; });
    setPts((o) => [...o, [la / sw, lo / sw]]); setMudou(true);
    leituras.current = [];
  };
  useEffect(() => () => { if (watch.current != null) navigator.geolocation.clearWatch(watch.current); }, []);

  // ---------------------------------------------------------------- terrenos
  const novo = () => {
    pararGps(); setSel(null); setPts([]); setNome(""); setArtigo(""); setOrigem("desenho"); setMudou(false); setConsulta(null); setImportados(null);
    grupos.current?.extra.clearLayers(); setModo("desenhar"); setMsg({ t: "info", x: "Clique no mapa para marcar os vértices do terreno, pela ordem. Arraste para acertar; clique direito apaga." });
  };
  const abrir = async (tid) => {
    pararGps(); setOcupado("abrir");
    try {
      const { data } = await api.get(`/terrenos/${tid}`);
      setSel(data); setPts(data.anel_latlon); setNome(data.nome); setArtigo(data.artigo_matricial || ""); setOrigem(data.origem); setMudou(false);
      setModo("ver"); setConsulta(null); setImportados(null); grupos.current?.extra.clearLayers(); setMsg(null);
      enquadrar(data.anel_latlon);
    } catch (e) { setMsg({ t: "erro", x: erroTxt(e, "Não foi possível abrir o terreno.") }); }
    setOcupado("");
  };
  const gravar = async () => {
    if (!med) return;
    setOcupado("gravar");
    try {
      const body = { nome, anel_latlon: pts, origem, artigo_matricial: artigo };
      const { data } = sel ? await api.put(`/terrenos/${sel.terreno_id}`, body) : await api.post("/terrenos", body);
      setSel(data); setMudou(false); setModo("ver"); pararGps(); await carregarLista();
      setMsg({ t: "ok", x: "Terreno gravado. Faça agora a análise oficial." });
    } catch (e) { setMsg({ t: "erro", x: erroTxt(e, "Não foi possível gravar.") }); }
    setOcupado("");
  };
  const analisar = async () => {
    if (!sel) return;
    setOcupado("analise"); setMsg({ t: "info", x: "A consultar DGT (CAOP, cadastro, PDM, RAN, REN, domínio hídrico), RGG do BUPi e altimetria… pode demorar até 1 minuto." });
    try {
      const { data } = await api.post(`/terrenos/${sel.terreno_id}/analise`, {}, { timeout: 180000 });
      setSel((s) => ({ ...s, analise: data.analise, analisado_em: data.analisado_em })); setMsg(null); carregarLista();
    } catch (e) { setMsg({ t: "erro", x: erroTxt(e, "A análise não terminou. Tente de novo.") }); }
    setOcupado("");
  };
  const apagar = async () => {
    if (!sel || !window.confirm(`Apagar o terreno «${sel.nome}»?`)) return;
    try { await api.delete(`/terrenos/${sel.terreno_id}`); setSel(null); setPts([]); setNome(""); carregarLista(); } catch (e) { setMsg({ t: "erro", x: erroTxt(e, "Não foi possível apagar.") }); }
  };
  const importar = async (f) => {
    if (!f) return;
    const fd = new FormData(); fd.append("ficheiro", f);
    setOcupado("importar");
    try {
      const { data } = await api.post("/terrenos/importar", fd, { timeout: 60000 });
      const ps = data.poligonos || [];
      if (ps.length === 1) usarImportado(ps[0]); else setImportados(ps);
    } catch (e) { setMsg({ t: "erro", x: erroTxt(e, "Ficheiro não reconhecido.") }); }
    setOcupado(""); if (ficheiro.current) ficheiro.current.value = "";
  };
  const usarImportado = (p) => {
    pararGps(); setSel(null); setPts(p.anel_latlon); setNome(p.nome || ""); setOrigem("importacao"); setMudou(true); setImportados(null); setModo("ver");
    enquadrar(p.anel_latlon); setMsg({ t: "info", x: "Polígono importado. Confirme os limites no ortofotomapa e grave." });
  };
  const usarCadastro = () => {
    const c = consulta?.cadastro; if (!c?.anel_latlon) return;
    pararGps(); setSel(null); setPts(c.anel_latlon.slice(0, -1)); setOrigem("cadastro"); setMudou(true); setModo("ver");
    const ref = c.atributos?.nic || c.atributos?.NIC || "";
    if (!nome) setNome(ref ? `Prédio ${ref}` : "Prédio do cadastro");
    grupos.current?.extra.clearLayers(); enquadrar(c.anel_latlon);
  };
  const procurar = async (q) => {
    if (!q.trim()) return;
    setOcupado("procurar");
    try {
      const r = await fetch(`https://nominatim.openstreetmap.org/search?format=json&countrycodes=pt&limit=1&q=${encodeURIComponent(q)}`);
      const js = await r.json();
      if (js[0]) mapa.current?.setView([+js[0].lat, +js[0].lon], 18); else setMsg({ t: "erro", x: "Local não encontrado." });
    } catch { setMsg({ t: "erro", x: "Pesquisa indisponível." }); }
    setOcupado("");
  };

  const a = sel?.analise;
  const nomeFich = (nome || "terreno").replace(/[^\w-]+/g, "_");

  return (
    <div className="p-4 md:p-6 space-y-4" data-testid="terrenos-page">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold flex items-center gap-2"><MapPin className="h-6 w-6 text-primary" /> Terrenos</h1>
          <p className="text-sm text-muted-foreground max-w-3xl">
            Identifique o terreno sobre o ortofotomapa oficial, veja as RGG já submetidas no BUPi e o cadastro, e obtenha numa só análise a freguesia, o PDM, a RAN, a REN, o domínio hídrico e os declives. Exporte o KML para submeter no BUPi.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={novo} data-testid="terrenos-novo"><Plus className="h-4 w-4 mr-1" /> Novo terreno</Button>
          <Button variant="outline" onClick={() => ficheiro.current?.click()} disabled={ocupado === "importar"}>
            {ocupado === "importar" ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <FileUp className="h-4 w-4 mr-1" />} Importar KML / GPX
          </Button>
          <input ref={ficheiro} type="file" accept=".kml,.kmz,.gpx,.geojson,.json" className="hidden" onChange={(e) => importar(e.target.files?.[0])} />
        </div>
      </div>

      {msg && (
        <div className={`rounded-md border px-3 py-2 text-sm flex gap-2 items-start ${msg.t === "erro" ? "border-red-500/40 bg-red-500/10" : msg.t === "ok" ? "border-emerald-500/40 bg-emerald-500/10" : "border-sky-500/40 bg-sky-500/10"}`}>
          {msg.t === "erro" ? <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" /> : msg.t === "ok" ? <CheckCircle2 className="h-4 w-4 mt-0.5 shrink-0" /> : <Info className="h-4 w-4 mt-0.5 shrink-0" />}
          <span className="flex-1">{msg.x}</span>
          <button className="text-xs opacity-60 hover:opacity-100" onClick={() => setMsg(null)}>×</button>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[320px_1fr_380px]">
        {/* lista */}
        <Card className="p-3 space-y-2 max-h-[72vh] overflow-auto order-3 lg:order-1">
          <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Os meus terrenos ({lista.length})</div>
          {!lista.length && <p className="text-sm text-muted-foreground">Ainda não tem terrenos. Desenhe, percorra com o GPS ou importe um ficheiro.</p>}
          {lista.map((t) => (
            <button key={t.terreno_id} onClick={() => abrir(t.terreno_id)} data-testid={`terreno-${t.terreno_id}`}
              className={`w-full text-left rounded-md border p-2 hover:bg-muted/60 transition ${sel?.terreno_id === t.terreno_id ? "border-primary bg-primary/5" : ""}`}>
              <div className="font-medium text-sm truncate">{t.nome}</div>
              <div className="text-xs text-muted-foreground">{num(t.area_m2, 0)} m² · {[t.freguesia, t.concelho].filter(Boolean).join(", ") || ORIGEM[t.origem]}</div>
              {t.alertas_criticos > 0 && <Badge variant="destructive" className="mt-1 text-[10px]">{t.alertas_criticos} alerta(s) crítico(s)</Badge>}
            </button>
          ))}
        </Card>

        {/* mapa */}
        <div className="space-y-2 order-1 lg:order-2">
          <div className="flex flex-wrap gap-2 items-center">
            <Button size="sm" variant={modo === "desenhar" ? "default" : "outline"} onClick={() => { pararGps(); setModo(modo === "desenhar" ? "ver" : "desenhar"); if (!pts.length) setOrigem("desenho"); }}><PenLine className="h-4 w-4 mr-1" /> Desenhar</Button>
            <Button size="sm" variant={modo === "gps" ? "default" : "outline"} onClick={() => (modo === "gps" ? (pararGps(), setModo("ver")) : iniciarGps())}><Crosshair className="h-4 w-4 mr-1" /> GPS no local</Button>
            <Button size="sm" variant={modo === "consultar" ? "default" : "outline"} onClick={() => { pararGps(); setModo(modo === "consultar" ? "ver" : "consultar"); }}><MousePointerClick className="h-4 w-4 mr-1" /> Consultar RGG / cadastro</Button>
            <Button size="sm" variant="ghost" disabled={!pts.length} onClick={() => { setPts((o) => o.slice(0, -1)); setMudou(true); }}><Undo2 className="h-4 w-4 mr-1" /> Anular</Button>
            <Button size="sm" variant="ghost" disabled={!pts.length} onClick={() => { setPts([]); setMudou(true); }}><RotateCcw className="h-4 w-4 mr-1" /> Limpar</Button>
            <div className="ml-auto flex gap-1 items-center text-xs">
              <Layers className="h-4 w-4 text-muted-foreground" />
              {[["dgt", "OrtoSat 2023"], ["o21", "Ortos 2021"], ["esri", "Satélite"]].map(([k, t]) => (
                <button key={k} className={`px-2 py-1 rounded ${base === k ? "bg-primary text-primary-foreground" : "bg-muted"}`} onClick={() => setBase(k)}>{t}</button>
              ))}
              <label className="flex items-center gap-1 px-2"><input type="checkbox" checked={verRgg} onChange={(e) => setVerRgg(e.target.checked)} /> RGG BUPi</label>
            </div>
          </div>
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); procurar(e.target.q.value); }}>
            <Input name="q" placeholder="Procurar lugar, rua ou freguesia…" className="h-8" />
            <Button size="sm" variant="outline" type="submit" disabled={ocupado === "procurar"}><Search className="h-4 w-4" /></Button>
          </form>
          {modo === "gps" && (
            <div className="rounded-md border border-sky-500/40 bg-sky-500/10 p-2 flex flex-wrap items-center gap-3 text-sm">
              <span>{gps ? <>Precisão: <b>{num(gps.acc, 0)} m</b> {gps.acc > 10 ? "— aguarde, ao ar livre" : "— boa"}</> : "A obter posição…"}</span>
              <Button size="sm" onClick={marcarVertice} disabled={!gps}><MapPin className="h-4 w-4 mr-1" /> Marcar vértice aqui ({pts.length + 1})</Button>
              <span className="text-xs text-muted-foreground">Pare em cada marco/esquina uns segundos antes de marcar (é feita a média das leituras).</span>
            </div>
          )}
          <div ref={el} className="h-[62vh] min-h-[380px] w-full rounded-lg border overflow-hidden" data-testid="terrenos-mapa" />
          <p className="text-[11px] text-muted-foreground">RGG: eBUPi — dados abertos (atualização diária), visíveis a partir do zoom de rua. Imagem: DGT OrtoSat 2023 (a mais recente cobertura oficial; Ortos 2021 aérea, 25 cm, como alternativa). A posição exata no BUPi prevalece.</p>
        </div>

        {/* painel */}
        <div className="space-y-3 order-2 lg:order-3 lg:max-h-[80vh] lg:overflow-auto">
          {importados && (
            <Card className="p-3 space-y-2">
              <div className="font-medium text-sm">Polígonos no ficheiro ({importados.length})</div>
              {importados.map((p, i) => (
                <button key={i} onClick={() => usarImportado(p)} className="w-full text-left rounded border p-2 text-sm hover:bg-muted/60">{p.nome} — {num(p.area_m2, 0)} m²</button>
              ))}
            </Card>
          )}

          {modo === "consultar" && consulta && (
            <Card className="p-3 space-y-2 text-sm" data-testid="terrenos-consulta">
              <div className="font-medium">Neste ponto</div>
              {consulta.aCarregar ? <div className="flex items-center gap-2 text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> A consultar BUPi e DGT…</div> : consulta.erro ? <p>{consulta.erro}</p> : (
                <>
                  <div>
                    <div className="text-xs font-semibold text-muted-foreground">RGG do BUPi</div>
                    {!consulta.rgg?.ok ? <p className="text-amber-600">Serviço do BUPi indisponível — por confirmar.</p>
                      : consulta.rgg.data.rgg.length ? consulta.rgg.data.rgg.map((r) => (
                        <div key={r.id} className="rounded bg-amber-500/10 border border-amber-500/30 p-2 mt-1">
                          {Object.entries(r.atributos).slice(0, 8).map(([k, v]) => <div key={k} className="text-xs"><span className="text-muted-foreground">{k}:</span> {v}</div>)}
                        </div>)) : <p>Sem RGG submetida neste ponto{consulta.rgg.data.cobertura ? "" : " (região sem dados da eBUPi)"}.</p>}
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-muted-foreground">Carta Cadastral (DGT)</div>
                    {consulta.cadastro ? (
                      <>
                        {Object.entries(consulta.cadastro.atributos).slice(0, 6).map(([k, v]) => <div key={k} className="text-xs"><span className="text-muted-foreground">{k}:</span> {v}</div>)}
                        <Button size="sm" className="mt-2" onClick={usarCadastro}>Usar este limite oficial</Button>
                      </>
                    ) : <p>{consulta.cadastro_nota || "Sem prédio cadastrado neste ponto."}</p>}
                  </div>
                </>
              )}
            </Card>
          )}

          {(pts.length > 0 || sel) && (
            <Card className="p-3 space-y-3" data-testid="terrenos-editor">
              <div className="grid grid-cols-2 gap-2">
                <Input value={nome} onChange={(e) => { setNome(e.target.value); setMudou(true); }} placeholder="Nome do terreno" className="col-span-2" />
                <Input value={artigo} onChange={(e) => { setArtigo(e.target.value); setMudou(true); }} placeholder="Artigo matricial (opcional)" className="col-span-2" />
              </div>
              {med ? (
                <div className="grid grid-cols-3 gap-2 text-center">
                  <div className="rounded bg-muted p-2 min-w-0">
                    <div className="text-lg font-semibold break-words">{med.area_m2 >= 10000 ? `${num(med.area_ha, 2)} ha` : `${num(med.area_m2, 1)} m²`}</div>
                    <div className="text-[11px] text-muted-foreground break-words">{med.area_m2 >= 10000 ? `${num(med.area_m2, 0)} m²` : `${num(med.area_ha, 4)} ha`}</div>
                  </div>
                  <div className="rounded bg-muted p-2 min-w-0"><div className="text-lg font-semibold break-words">{num(med.perimetro_m, 1)} m</div><div className="text-[11px] text-muted-foreground">perímetro</div></div>
                  <div className="rounded bg-muted p-2 min-w-0"><div className="text-lg font-semibold">{med.vertices_tm06.length}</div><div className="text-[11px] text-muted-foreground">vértices</div></div>
                </div>
              ) : <p className="text-sm text-muted-foreground">{medErro || "Marque pelo menos 3 vértices."}</p>}
              {med?.avisos?.map((w) => <p key={w} className="text-xs text-amber-600">{w}</p>)}
              <div className="text-[11px] text-muted-foreground">{ORIGEM[origem]} · medição em {med?.sistema || "PT-TM06/ETRS89"}</div>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" onClick={gravar} disabled={!med || ocupado === "gravar" || (!mudou && !!sel)} data-testid="terrenos-gravar">
                  {ocupado === "gravar" ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Save className="h-4 w-4 mr-1" />} {sel ? "Gravar alterações" : "Gravar terreno"}
                </Button>
                {sel && <Button size="sm" variant="secondary" onClick={analisar} disabled={ocupado === "analise" || mudou} data-testid="terrenos-analisar">
                  {ocupado === "analise" ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Radar className="h-4 w-4 mr-1" />} {a ? "Refazer análise" : "Analisar (fontes oficiais)"}
                </Button>}
                {sel && <Button size="sm" variant="ghost" onClick={apagar}><Trash2 className="h-4 w-4" /></Button>}
              </div>
              {sel && !mudou && (
                <div className="flex flex-wrap gap-2 pt-1 border-t">
                  <Button size="sm" variant="outline" onClick={() => descarregar(`/terrenos/${sel.terreno_id}/exportar.kml`, `${nomeFich}.kml`)}><Download className="h-4 w-4 mr-1" /> KML (BUPi)</Button>
                  <Button size="sm" variant="outline" onClick={() => descarregar(`/terrenos/${sel.terreno_id}/exportar.geojson`, `${nomeFich}.geojson`)}>GeoJSON</Button>
                  <Button size="sm" variant="outline" onClick={() => descarregar(`/terrenos/${sel.terreno_id}/exportar.csv`, `${nomeFich}_vertices_PTTM06.csv`)}>Vértices PT-TM06</Button>
                  <a className="text-xs inline-flex items-center gap-1 text-primary underline" href="https://bupi.gov.pt" target="_blank" rel="noreferrer">Submeter no BUPi (importe o KML) <ExternalLink className="h-3 w-3" /></a>
                </div>
              )}
            </Card>
          )}

          {a && <Analise a={a} quando={sel?.analisado_em} />}
        </div>
      </div>

      <style>{`.tp-lbl{background:rgba(20,27,24,.85);color:#fff;font:600 10px ui-monospace,monospace;padding:1px 5px;border-radius:4px;white-space:nowrap;transform:translate(-50%,-50%);display:inline-block}
        .tp-vtx{width:20px;height:20px;border-radius:50%;background:#fff;border:2px solid ${COR.limite};cursor:grab;font:700 10px/16px system-ui;text-align:center;color:#3a2a1a}`}</style>
    </div>
  );
}

function Estado({ r }) {
  if (!r) return null;
  if (!r.ok) return <Badge variant="outline" className="text-amber-600 border-amber-500/50">por confirmar</Badge>;
  if (r.data?.incompleta) return <Badge variant="outline" className="text-amber-600 border-amber-500/50">parcial</Badge>;
  return <Badge variant="outline" className="text-emerald-600 border-emerald-500/50">oficial</Badge>;
}

function Fonte({ r }) {
  if (!r) return null;
  return <div className="text-[10px] text-muted-foreground mt-1">{r.fonte || ""}{r.nota ? ` — ${r.nota}` : ""}</div>;
}

function Analise({ a, quando }) {
  const caop = a.caop?.data, cad = a.cadastro?.data, rgg = a.bupi?.data, pdm = a.pdm?.data, srv = a.servidoes?.data, dcl = a.declives?.data;
  const cor = { critico: "border-red-500/50 bg-red-500/10", aviso: "border-amber-500/50 bg-amber-500/10", info: "border-sky-500/40 bg-sky-500/10" };
  return (
    <Card className="p-3 space-y-3 text-sm" data-testid="terrenos-analise">
      <div className="flex items-center justify-between">
        <div className="font-semibold">Ficha do terreno</div>
        {quando && <div className="text-[11px] text-muted-foreground">{new Date(quando).toLocaleString("pt-PT")}</div>}
      </div>
      <div className="flex flex-wrap gap-1">
        {TEMAS.map(([k, l]) => <span key={k} className="text-[11px] inline-flex items-center gap-1">{l} <Estado r={a[k]} /></span>)}
      </div>

      {a.alertas?.length > 0 && (
        <div className="space-y-1">
          {a.alertas.map((x, i) => <div key={i} className={`rounded border px-2 py-1 text-xs ${cor[x.nivel] || ""}`}>{x.texto}</div>)}
        </div>
      )}

      <section>
        <div className="text-xs font-semibold text-muted-foreground">Localização administrativa</div>
        {caop ? caop.freguesias.map((f) => (
          <div key={f.dicofre || f.freguesia}>{f.freguesia}, {f.concelho}{f.distrito ? ` (${f.distrito})` : ""} · DICOFRE <b>{f.dicofre || "—"}</b>{caop.freguesias.length > 1 ? ` · ${pct(f.fracao)}` : ""}</div>
        )) : <p className="text-amber-600">Por confirmar.</p>}
        <Fonte r={a.caop} />
      </section>

      <section>
        <div className="text-xs font-semibold text-muted-foreground">RGG no BUPi</div>
        {!a.bupi?.ok ? <p className="text-amber-600">Por confirmar (serviço indisponível).</p>
          : !rgg.cobertura ? <p>Região sem RGG publicadas pela eBUPi.</p>
          : rgg.rgg.length ? rgg.rgg.map((r) => <div key={r.id}>RGG <b>{r.id}</b> em ~{pct(r.fracao_amostras)} do terreno</div>)
          : <p className="text-emerald-700">Nenhuma RGG submetida sobre este terreno ({rgg.amostras} pontos verificados).</p>}
        <Fonte r={a.bupi} />
      </section>

      <section>
        <div className="text-xs font-semibold text-muted-foreground">Carta Cadastral</div>
        {!a.cadastro?.ok ? <p className="text-amber-600">Por confirmar.</p>
          : cad.sem_cadastro ? <p>Sem cadastro geométrico neste local.</p>
          : cad.predios.slice(0, 5).map((p, i) => <div key={i}>{p.referencia || "Prédio"} · {num(p.area_predio_m2, 0)} m² · coincidência {pct(p.iou)}</div>)}
        <Fonte r={a.cadastro} />
      </section>

      <section>
        <div className="text-xs font-semibold text-muted-foreground">PDM (regime de uso do solo)</div>
        {pdm ? pdm.classes.map((c, i) => <div key={i}>{c.classe || (c.solo === "urbano" ? "Solo urbano" : c.solo === "rustico" ? "Solo rústico" : "—")}{c.categoria ? ` — ${c.categoria}` : ""} · {pct(c.fracao)}</div>)
          : <p className="text-amber-600">{a.pdm?.nota || "Por confirmar."}</p>}
        <Fonte r={a.pdm} />
      </section>

      <section>
        <div className="text-xs font-semibold text-muted-foreground">RAN, REN, recursos hídricos e servidões</div>
        {!srv ? <p className="text-amber-600">Por confirmar.</p> : (
          <>
            {srv.afeta.length ? srv.afeta.map((e) => (
              <div key={e.id} className="flex justify-between gap-2"><span>{e.titulo}</span><span className="font-medium whitespace-nowrap">{e.area_afetada_m2 > 0.5 ? `${pct(e.fracao)} · ${num(e.area_afetada_m2, 0)} m²` : "toca"}</span></div>
            )) : <p className="text-emerald-700">Nenhuma servidão consultada afeta o terreno.</p>}
            {srv.proximas_60m.length > 0 && <div className="text-xs text-muted-foreground mt-1">A menos de 60 m: {srv.proximas_60m.map((e) => `${e.titulo} (${num(e.distancia_m, 0)} m)`).join("; ")}</div>}
            {srv.incompleta && <div className="text-xs text-amber-600 mt-1">Por confirmar: {srv.por_confirmar.map((e) => e.titulo).join("; ")}</div>}
            {srv.ren?.length > 0 && <div className="text-[11px] text-muted-foreground mt-1">{srv.nota_ren}</div>}
          </>
        )}
        <Fonte r={a.servidoes} />
      </section>

      <section>
        <div className="text-xs font-semibold text-muted-foreground">Relevo e declives</div>
        {dcl ? (
          <div>Declive médio <b>{num(dcl.declive_medio_pct, 1)} %</b> ({dcl.classe}) · máx. {num(dcl.declive_max_pct, 1)} % · desnível {num(dcl.desnivel_m, 1)} m · exposição {dcl.exposicao}
            <div className="text-xs text-muted-foreground">Modelo: {dcl.tipo_modelo === "MDT" ? "terreno (solo nu)" : dcl.tipo_modelo === "DSM" ? "superfície (inclui edifícios e árvores)" : "terreno"}{dcl.resolucao_m ? ` · ${num(dcl.resolucao_m, 1)} m` : ""}</div>
            {dcl.verificacao && <div className="text-xs text-muted-foreground">Verificação cruzada com Copernicus: diferença média {num(dcl.verificacao.dif_media_m, 2)} m (máx. {num(dcl.verificacao.dif_max_abs_m, 2)} m, {dcl.verificacao.pontos} pontos).</div>}
            {dcl.aviso_resolucao && <div className="text-xs text-amber-600">Terreno pequeno para a resolução do modelo de terreno: valores grosseiros.</div>}
          </div>
        ) : <p className="text-amber-600">Por confirmar.</p>}
        <Fonte r={a.declives} />
      </section>

      <p className="text-[11px] text-muted-foreground border-t pt-2">{a.aviso_legal}</p>
    </Card>
  );
}
