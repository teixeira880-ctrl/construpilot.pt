import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { Box, CheckCircle2, Compass, Cpu, Download, Globe2, Layers, Loader2, MapPin, Mountain, Server, Sparkles, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import VisualizadorGLB from "@/components/edificio3d/VisualizadorGLB";

const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
const ESRI_ATTR = "Imagens © Esri, Maxar, Earthstar Geographics";

const VISTAS = [
  ["perspetiva", "Perspetiva"], ["fachada_frente", "Fachada principal"], ["fachada_tardoz", "Fachada de tardoz"],
  ["fachada_esquerda", "Fachada lateral esquerda"], ["fachada_direita", "Fachada lateral direita"],
  ["aerea_telhado", "Vista aérea do telhado"], ["aerea_envolvente", "Implantação na paisagem"],
];
const ANTES_DEPOIS = [
  ["antes_perspetiva.jpg", "perspetiva.jpg", "Blender — perspetiva"],
  ["antes_aerea.jpg", "aerea_envolvente.jpg", "Blender — vista aérea"],
  ["arcgis_perspetiva_antes.jpg", "arcgis_perspetiva_depois.jpg", "ArcGIS Pro — cena 3D com terreno"],
  ["arcgis_aerea_antes.jpg", "arcgis_aerea_depois.jpg", "ArcGIS Pro — ortofotomapa"],
];
const RUMOS = [["Norte", 0], ["Nordeste", 45], ["Este", 90], ["Sudeste", 135], ["Sul", 180], ["Sudoeste", 225], ["Oeste", 270], ["Noroeste", 315]];

function cantos(lat, lon, w, d, az) {
  const a = (az * Math.PI) / 180;
  const fx = Math.sin(a), fy = Math.cos(a), lx = fy, ly = -fx;
  const m = 111320, mx = m * Math.cos((lat * Math.PI) / 180);
  return [[-1, 1], [1, 1], [1, -1], [-1, -1]].map(([su, sv]) => {
    const x = su * (w / 2) * lx + sv * (d / 2) * fx, y = su * (w / 2) * ly + sv * (d / 2) * fy;
    return [lat + y / m, lon + x / mx];
  });
}

function useBlob(path, tipo = "url") {
  const [v, setV] = useState(null);
  useEffect(() => {
    if (!path) return undefined;
    let vivo = true, u = null;
    api.get(path, { responseType: tipo === "url" ? "blob" : "arraybuffer", timeout: 180000 })
      .then(r => { if (!vivo) return; if (tipo === "url") { u = URL.createObjectURL(r.data); setV(u); } else setV(r.data); })
      .catch(() => {});
    return () => { vivo = false; if (u) URL.revokeObjectURL(u); };
  }, [path, tipo]);
  return v;
}

function Img({ base, nome, alt, className = "" }) {
  const u = useBlob(base && nome ? `${base}/${nome}` : null);
  if (!u) return <div className={`bg-muted animate-pulse ${className}`} style={{ aspectRatio: "3 / 2" }} />;
  return <img src={u} alt={alt} className={className} />;
}

function AntesDepois({ base, antes, depois, titulo, legendas = ["Antes", "Depois"] }) {
  const [x, setX] = useState(50);
  const ua = useBlob(`${base}/${antes}`), ud = useBlob(`${base}/${depois}`);
  if (!ua || !ud) return null;
  return (
    <Card className="p-3 space-y-2" data-testid="ed3d-antes-depois">
      <div className="text-sm font-medium">{titulo}</div>
      <div className="relative w-full overflow-hidden rounded select-none" style={{ aspectRatio: "3 / 2" }}>
        <img src={ud} alt="depois" className="absolute inset-0 w-full h-full object-cover" />
        <img src={ua} alt="antes" className="absolute inset-0 w-full h-full object-cover" style={{ clipPath: `inset(0 ${100 - x}% 0 0)` }} />
        <div className="absolute top-0 bottom-0 w-0.5 bg-white shadow" style={{ left: `${x}%` }} />
        <span className="absolute left-2 top-2 text-xs bg-black/60 text-white px-2 py-0.5 rounded">{legendas[0]}</span>
        <span className="absolute right-2 top-2 text-xs bg-black/60 text-white px-2 py-0.5 rounded">{legendas[1]}</span>
        <input type="range" min="0" max="100" value={x} onChange={e => setX(+e.target.value)} aria-label="antes/depois"
          className="absolute inset-0 w-full h-full opacity-0 cursor-ew-resize" />
      </div>
    </Card>
  );
}

function Mapa({ lat, lon, w, d, az, onClick, altura = 360 }) {
  const el = useRef(null), mapa = useRef(null), poli = useRef(null), mk = useRef(null);
  useEffect(() => {
    if (mapa.current || !el.current) return;
    mapa.current = L.map(el.current, { zoomControl: true }).setView([lat || 39.5, lon || -8.0], lat ? 19 : 7);
    L.tileLayer(ESRI, { maxZoom: 20, attribution: ESRI_ATTR }).addTo(mapa.current);
    if (onClick) mapa.current.on("click", e => onClick(e.latlng.lat, e.latlng.lng));
    setTimeout(() => mapa.current?.invalidateSize(), 200);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!mapa.current || lat == null || lon == null || Number.isNaN(lat)) return;
    const pts = cantos(lat, lon, w, d, az);
    poli.current?.remove(); mk.current?.remove();
    poli.current = L.polygon(pts, { color: "#c8763a", weight: 2, fillColor: "#ffffff", fillOpacity: 0.55 }).addTo(mapa.current);
    // fachada principal a vermelho
    mk.current = L.polyline([pts[3], pts[2]], { color: "#d62828", weight: 5 }).addTo(mapa.current);
    if (mapa.current.getZoom() < 17) mapa.current.setView([lat, lon], 19);
  }, [lat, lon, w, d, az]);
  return <div ref={el} style={{ height: altura }} className="w-full rounded z-0" data-testid="ed3d-mapa" />;
}

function EstadoSistema({ s }) {
  if (!s) return null;
  const ok = (v, t) => <span className="flex items-center gap-1">{v ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : <XCircle className="h-4 w-4 text-muted-foreground" />}{t}</span>;
  return (
    <div className="flex flex-wrap gap-4 text-sm" data-testid="ed3d-sistema">
      {ok(s.blender_servidor, "Blender no servidor")}
      {ok(s.postos?.some(p => p.blender), `Posto Blender ligado${s.postos?.length ? ` (${s.postos.map(p => p.nome).join(", ")})` : ""}`)}
      {ok(s.arcgis_disponivel, "ArcGIS Pro ligado")}
    </div>
  );
}

function Novo() {
  const nav = useNavigate();
  const [f, setF] = useState({ nome: "Moradia contemporânea", morada: "", latitude: "", longitude: "", altitude_m: "",
    azimute_fachada_graus: 180, largura_m: 12, profundidade_m: 9, pisos: 2, pe_direito_m: 3, inclinacao_telhado_graus: 30,
    beiral_m: 0.6, usar_arcgis: false, qualidade: "normal" });
  const [sis, setSis] = useState(null);
  const [aEnviar, setAEnviar] = useState(false);
  const [erro, setErro] = useState(null);
  useEffect(() => { api.get("/edificio3d/sistema").then(r => setSis(r.data)).catch(() => {}); }, []);
  const set = (k, v) => setF(o => ({ ...o, [k]: v }));
  const num = v => (v === "" || v == null ? null : Number(String(v).replace(",", ".")));

  const enviar = async () => {
    setErro(null); setAEnviar(true);
    try {
      const body = { ...f, latitude: num(f.latitude), longitude: num(f.longitude), altitude_m: num(f.altitude_m) };
      ["largura_m", "profundidade_m", "pisos", "pe_direito_m", "inclinacao_telhado_graus", "beiral_m", "azimute_fachada_graus"].forEach(k => { body[k] = num(body[k]); });
      const { data } = await api.post("/edificio3d/projetos", body);
      nav(`/edificio-3d/${data.job_id}`);
    } catch (e) { setErro(e?.response?.data?.detail?.toString?.() || "Não foi possível criar o projeto."); }
    setAEnviar(false);
  };

  const campo = (k, lbl, extra = {}) => (
    <label className="block text-sm">{lbl}
      <Input className="mt-1" value={f[k]} onChange={e => set(k, e.target.value)} data-testid={`ed3d-${k}`} {...extra} />
    </label>
  );
  const lat = num(f.latitude), lon = num(f.longitude);

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-5" data-testid="ed3d-novo">
      <div>
        <h1 className="text-2xl font-semibold flex items-center gap-2"><Globe2 className="h-6 w-6" />Edifício 3D georreferenciado</h1>
        <p className="text-muted-foreground mt-1 text-sm max-w-3xl">
          O Blender constrói o edifício com geometria 3D real (paredes, vãos, caixilharia, cobertura de duas águas) e produz os renders;
          o ArcGIS Pro implanta-o nas coordenadas, com o terreno e o ortofotomapa. Tudo o que vê aqui é produzido por esses programas.
        </p>
        <div className="mt-3"><EstadoSistema s={sis} /></div>
      </div>
      <div className="grid lg:grid-cols-5 gap-4">
        <Card className="p-0 overflow-hidden lg:col-span-3">
          <Mapa lat={lat} lon={lon} w={num(f.largura_m) || 12} d={num(f.profundidade_m) || 9} az={num(f.azimute_fachada_graus) || 0}
            onClick={(a, b) => { set("latitude", a.toFixed(7)); set("longitude", b.toFixed(7)); }} altura={440} />
          <div className="p-2 text-xs text-muted-foreground border-t flex items-center gap-1"><MapPin className="h-3.5 w-3.5" />
            Clique no mapa para implantar o edifício. A linha vermelha é a fachada principal.</div>
        </Card>
        <Card className="p-4 space-y-3 lg:col-span-2">
          {campo("nome", "Nome do projeto")}
          {campo("morada", "Morada (opcional, se não tiver coordenadas)")}
          <div className="grid grid-cols-2 gap-2">{campo("latitude", "Latitude (WGS84)")}{campo("longitude", "Longitude (WGS84)")}</div>
          <div className="grid grid-cols-2 gap-2">
            {campo("altitude_m", "Altitude (m) — vazio = automática")}
            <label className="block text-sm">Fachada principal virada a
              <select className="mt-1 w-full border rounded h-9 px-2 bg-background" value={f.azimute_fachada_graus}
                onChange={e => set("azimute_fachada_graus", e.target.value)} data-testid="ed3d-azimute">
                {RUMOS.map(([t, v]) => <option key={v} value={v}>{t} ({v}°)</option>)}
              </select>
            </label>
          </div>
          <div className="grid grid-cols-3 gap-2">
            {campo("largura_m", "Frente (m)")}{campo("profundidade_m", "Profund. (m)")}{campo("pisos", "Pisos")}
          </div>
          <div className="grid grid-cols-3 gap-2">
            {campo("pe_direito_m", "Altura/piso (m)")}{campo("inclinacao_telhado_graus", "Telhado (°)")}{campo("beiral_m", "Beiral (m)")}
          </div>
          <div className="grid grid-cols-2 gap-2 items-end">
            <label className="block text-sm">Qualidade dos renders
              <select className="mt-1 w-full border rounded h-9 px-2 bg-background" value={f.qualidade} onChange={e => set("qualidade", e.target.value)}>
                <option value="rapida">Rápida</option><option value="normal">Normal</option><option value="alta">Alta (lenta)</option>
              </select>
            </label>
            <label className="flex items-center gap-2 text-sm h-9">
              <input type="checkbox" checked={f.usar_arcgis} onChange={e => set("usar_arcgis", e.target.checked)} data-testid="ed3d-arcgis" />
              Implantar no ArcGIS Pro
            </label>
          </div>
          {f.usar_arcgis && sis && !sis.arcgis_disponivel && (
            <p className="text-xs text-amber-700">Nenhum posto com ArcGIS Pro está ligado agora: o trabalho fica em fila até um posto se ligar.</p>
          )}
          {erro && <p className="text-sm text-destructive">{erro}</p>}
          <Button className="w-full" onClick={enviar} disabled={aEnviar || (lat == null && !f.morada.trim())} data-testid="ed3d-gerar">
            {aEnviar ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Box className="h-4 w-4 mr-2" />}Gerar edifício 3D
          </Button>
        </Card>
      </div>
      <Historico />
    </div>
  );
}

function Historico() {
  const [l, setL] = useState([]);
  useEffect(() => { api.get("/edificio3d/projetos").then(r => setL(r.data.projetos || [])).catch(() => {}); }, []);
  if (!l.length) return null;
  return (
    <Card className="p-4">
      <div className="font-medium mb-2">Projetos anteriores</div>
      <div className="divide-y">
        {l.map(p => (
          <Link key={p.job_id} to={`/edificio-3d/${p.job_id}`} className="flex justify-between py-2 text-sm hover:underline">
            <span>{p.nome}</span><span className="text-muted-foreground">{p.estado} · {new Date(p.criado_em).toLocaleString("pt-PT")}</span>
          </Link>
        ))}
      </div>
    </Card>
  );
}

function Resultado({ id }) {
  const [j, setJ] = useState(null);
  const [vista, setVista] = useState("perspetiva");
  const [aFoto, setAFoto] = useState(false);
  const [erroFoto, setErroFoto] = useState(null);
  const viz = useRef(null);
  useEffect(() => {
    let vivo = true, t;
    const ler = async () => {
      try {
        const { data } = await api.get(`/edificio3d/projetos/${id}`);
        if (!vivo) return;
        setJ(data);
        if (!["concluido", "erro"].includes(data.estado)) t = setTimeout(ler, 3000);
      } catch { t = setTimeout(ler, 6000); }
    };
    ler();
    return () => { vivo = false; clearTimeout(t); };
  }, [id]);
  const base = `/edificio3d/projetos/${id}/ficheiros`;
  const pronto = j?.estado === "concluido";
  const glb = useBlob(pronto && j.ficheiros?.includes("edificio.glb") ? `${base}/edificio.glb` : null, "buffer");
  if (!j) return <div className="p-10 grid place-items-center"><Loader2 className="h-6 w-6 animate-spin" /></div>;
  const p = j.params || {}, m = j.manifesto || {}, arc = j.arcgis || {}, fich = new Set(j.ficheiros || []);
  const imgs = m.imagens || {};
  const arcImgs = Object.entries(arc.imagens || {});

  const fotos = j.fotorrealistas || {};
  const fotorrealista = async () => {
    setAFoto(true); setErroFoto(null);
    try {
      const { data } = await api.post(`/edificio3d/projetos/${id}/fotorrealista`, { vista }, { timeout: 180000 });
      setJ(o => ({ ...o, fotorrealistas: { ...(o.fotorrealistas || {}), [vista]: data.ficheiro },
        ficheiros: [...new Set([...(o.ficheiros || []), data.ficheiro])] }));
    } catch (e) { setErroFoto(e?.response?.data?.detail?.toString?.() || "Não foi possível gerar o acabamento."); }
    setAFoto(false);
  };

  const baixar = async (nome) => {
    const r = await api.get(`${base}/${nome}`, { responseType: "blob", timeout: 300000 });
    const u = URL.createObjectURL(r.data); const a = document.createElement("a"); a.href = u; a.download = nome; a.click(); URL.revokeObjectURL(u);
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-5" data-testid="ed3d-resultado">
      <div className="flex flex-wrap justify-between gap-3 items-start">
        <div>
          <h1 className="text-2xl font-semibold">{j.nome}</h1>
          <p className="text-sm text-muted-foreground flex items-center gap-1 flex-wrap">
            <MapPin className="h-4 w-4" />{p.latitude?.toFixed?.(6)}, {p.longitude?.toFixed?.(6)}
            {p.altitude_m != null && <><Mountain className="h-4 w-4 ml-2" />{p.altitude_m} m</>}
            <Compass className="h-4 w-4 ml-2" />fachada a {p.azimute_fachada_graus}°
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Badge variant={j.estado === "erro" ? "destructive" : "default"} data-testid="ed3d-estado">{j.estado}</Badge>
          {j.modo && <Badge variant="outline">{j.modo === "servidor" ? <Server className="h-3 w-3 mr-1" /> : <Cpu className="h-3 w-3 mr-1" />}{j.modo === "servidor" ? "Blender no servidor" : `Posto ${j.posto || ""}`}</Badge>}
          {m.motor && <Badge variant="outline">{m.motor}</Badge>}
        </div>
      </div>

      {!pronto && (
        <Card className="p-4 space-y-2">
          <div className="flex items-center gap-2 font-medium">{j.estado !== "erro" && <Loader2 className="h-4 w-4 animate-spin" />}A produzir…</div>
          <ol className="text-sm space-y-1 text-muted-foreground">
            {(j.etapas || []).map((e, i) => <li key={i}>• {e.texto}</li>)}
          </ol>
          {j.erro && <pre className="text-xs text-destructive whitespace-pre-wrap">{j.erro}</pre>}
        </Card>
      )}

      {pronto && (
        <>
          <div className="grid lg:grid-cols-3 gap-4">
            <Card className="p-0 overflow-hidden lg:col-span-2">
              {glb ? <VisualizadorGLB ref={viz} dados={glb} azimute={p.azimute_fachada_graus} altura={480} />
                : <div className="h-[480px] grid place-items-center"><Loader2 className="h-6 w-6 animate-spin" /></div>}
              <div className="p-2 border-t flex flex-wrap gap-2">
                {[["perspetiva", "Perspetiva"], ["frente", "Frente"], ["tardoz", "Tardoz"], ["esquerda", "Esquerda"], ["direita", "Direita"], ["aerea", "Aérea"]]
                  .map(([k, t]) => <Button key={k} size="sm" variant="outline" onClick={() => viz.current?.vista(k)}>{t}</Button>)}
              </div>
            </Card>
            <Card className="p-0 overflow-hidden">
              <Mapa lat={p.latitude} lon={p.longitude} w={p.largura_m} d={p.profundidade_m} az={p.azimute_fachada_graus} altura={300} />
              <div className="p-3 text-sm space-y-1 border-t">
                <div className="font-medium flex items-center gap-1"><Layers className="h-4 w-4" />Implantação</div>
                <div>{p.largura_m} × {p.profundidade_m} m · {p.pisos} pisos × {p.pe_direito_m} m</div>
                <div>Cumeeira {m.dimensoes?.altura_cumeeira_m} m · telhado {p.inclinacao_telhado_graus}° · beiral {p.beiral_m} m</div>
                {m.geometria && <div className="text-muted-foreground">{m.geometria.vertices} vértices · {m.geometria.faces} faces · {m.geometria.objetos} materiais</div>}
                {arc.implantacao && <div className="text-muted-foreground">ArcGIS: {arc.implantacao.sr_nome} · X {arc.implantacao.x?.toFixed(2)} · Y {arc.implantacao.y?.toFixed(2)} · Z {arc.implantacao.z?.toFixed(2)}</div>}
                {p.fonte_ortofoto && <div className="text-xs text-muted-foreground">Ortofoto: {p.fonte_ortofoto}</div>}
              </div>
            </Card>
          </div>

          <Card className="p-3 space-y-3" data-testid="ed3d-renders">
            <div className="flex flex-wrap gap-2">
              {VISTAS.filter(([k]) => imgs[k]).map(([k, t]) => (
                <Button key={k} size="sm" variant={vista === k ? "default" : "outline"} onClick={() => setVista(k)}>{t}</Button>
              ))}
            </div>
            {imgs[vista] && (fotos[vista]
              ? <AntesDepois base={base} antes={imgs[vista]} depois={fotos[vista]} legendas={["Render Blender", "Fotorrealista"]}
                  titulo="Render Blender (referência técnica) ↔ acabamento fotorrealista sobre o mesmo render" />
              : <Img base={base} nome={imgs[vista]} alt={vista} className="w-full rounded" />)}
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" onClick={fotorrealista} disabled={aFoto || !imgs[vista]} data-testid="ed3d-fotorrealista">
                {aFoto ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Sparkles className="h-4 w-4 mr-1" />}
                {fotos[vista] ? "Refazer acabamento fotorrealista" : "Acabamento fotorrealista desta vista"}
              </Button>
              {fotos[vista] && <Button size="sm" variant="outline" onClick={() => baixar(fotos[vista])}><Download className="h-4 w-4 mr-1" />Imagem fotorrealista</Button>}
              {erroFoto && <span className="text-sm text-destructive">{erroFoto}</span>}
            </div>
            <p className="text-xs text-muted-foreground">Renders Cycles produzidos pelo {m.motor || "Blender"} a partir do modelo 3D. O acabamento fotorrealista
              (motor de imagem ConstruPilot) é aplicado sobre o render Blender, com a mesma câmara e geometria; o original fica sempre disponível.</p>
          </Card>

          <div className="grid md:grid-cols-2 gap-4">
            {ANTES_DEPOIS.filter(([a, d]) => fich.has(a) && fich.has(d)).map(([a, d, t]) => <AntesDepois key={a} base={base} antes={a} depois={d} titulo={t} />)}
          </div>

          {arcImgs.length > 0 && (
            <Card className="p-3 space-y-2">
              <div className="font-medium">Cena ArcGIS Pro (terreno e ortofotomapa reais)</div>
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
                {arcImgs.filter(([k]) => !k.endsWith("_antes")).map(([k, n]) => <div key={k}><Img base={base} nome={n} alt={k} className="w-full rounded" /><div className="text-xs text-muted-foreground mt-1">{k.replace(/_/g, " ")}</div></div>)}
              </div>
            </Card>
          )}
          {j.usar_arcgis && arc.ok === false && <p className="text-sm text-amber-700">ArcGIS Pro: {arc.erro}</p>}

          <Card className="p-3 flex flex-wrap gap-2">
            {[["edificio.glb", "Modelo GLB"], ["edificio.blend", "Ficheiro Blender"], ["edificio.slpk", "Scene Layer Package"],
              ["construpilot_gdb.zip", "Geodatabase ArcGIS"], ["construpilot_cena.aprx", "Projeto ArcGIS Pro"]]
              .filter(([n]) => fich.has(n)).map(([n, t]) => (
                <Button key={n} size="sm" variant="outline" onClick={() => baixar(n)}><Download className="h-4 w-4 mr-1" />{t}</Button>
              ))}
            <Link to="/edificio-3d" className="ml-auto"><Button size="sm">Novo edifício</Button></Link>
          </Card>
        </>
      )}
    </div>
  );
}

export default function Edificio3D() {
  const { id } = useParams();
  return id ? <Resultado id={id} /> : <Novo />;
}
