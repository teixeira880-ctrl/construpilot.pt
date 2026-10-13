import { useEffect, useRef, useState, useCallback } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import {
  Radar, MapPin, Star, Flame, TrendingUp, Building2, X, Loader2,
  Settings, Mail, Copy, Download, Check, Crosshair, BarChart3, Eye, Users, Sparkles, Truck,
} from "lucide-react";
import PostalSendDialog from "@/components/radar/PostalSendDialog";
import { PostalTrackingPanel } from "@/components/radar/PostalTracking";
import { RadarContactPanel } from "@/components/radar/RadarContactPanel";
import { RadarZoneFilter } from "@/components/radar/RadarZoneFilter";
import { RadarOfficialSource } from "@/components/radar/RadarOfficialSource";
import { RadarProjectFilters } from "@/components/radar/RadarProjectFilters";
import { RadarQualification } from "@/components/radar/RadarQualification";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";

const eur = (n) => (Number(n) || 0).toLocaleString("fr-FR") + " €";
const scoreColor = (s) => (s >= 85 ? "#ef4444" : s >= 65 ? "#f59e0b" : "#16a34a");

function b64ToBlob(dataUrl) {
  const [meta, b64] = dataUrl.split(",");
  const mime = /:(.*?);/.exec(meta)?.[1] || "application/octet-stream";
  const bin = atob(b64);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  return new Blob([arr], { type: mime });
}

export default function RadarChantiers() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [km, setKm] = useState(30);
  const [sel, setSel] = useState(null);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [profile, setProfile] = useState(null);
  const [zone, setZone] = useState(null);
  const [zoneBusy, setZoneBusy] = useState(false);
  const [filters, setFilters] = useState(null);
  const [filtersBusy, setFiltersBusy] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [pageNumber, setPageNumber] = useState(1);
  const loadVersion = useRef(0);
  const [showSettings, setShowSettings] = useState(false);
  const [pickZone, setPickZone] = useState(false);
  const [draftMetiers, setDraftMetiers] = useState([]);
  const [draftBase, setDraftBase] = useState(null);
  const [savingProfile, setSavingProfile] = useState(false);
  const [campaign, setCampaign] = useState(null);
  const [postalOpen, setPostalOpen] = useState(false);
  const [genLoading, setGenLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [letterMsg, setLetterMsg] = useState("");
  const [aiTone, setAiTone] = useState("formel");
  const [aiLength, setAiLength] = useState("moyen");
  const [aiLoading, setAiLoading] = useState(false);
  const [showCampaigns, setShowCampaigns] = useState(false);
  const [campaigns, setCampaigns] = useState(null);

  const mapRef = useRef(null);
  const mapObj = useRef(null);
  const layer = useRef(null);
  const pickRef = useRef(false);
  useEffect(() => { pickRef.current = pickZone; }, [pickZone]);

  const load = useCallback(async (radius, silent = false) => {
    if (!zone || !filters) return;
    const version = ++loadVersion.current;
    if (!silent) setLoading(true);
    setLoadError(false);
    const query = new URLSearchParams({ km: radius, zone_mode: zone.mode, departments: zone.departments.join(","), page: pageNumber, page_size: 50 });
    Object.entries(filters).forEach(([key, values]) => query.set(key, values.join(",")));
    try {
      const { data: d } = await api.get(`/radar/opportunities?${query}`);
      if (version === loadVersion.current) { setData(d); setStats(d.stats); }
    } catch {
      if (version === loadVersion.current) { setLoadError(true); if (!silent) { setData(null); setStats(null); } }
    }
    finally { if (version === loadVersion.current) setLoading(false); }
  }, [zone, pageNumber, filters]);

  useEffect(() => {
    if (!user) { setLoading(false); return; }
    api.get("/radar/profile").then(({ data: p }) => {
      setProfile(p); setKm(p.km); setDraftMetiers(p.metiers || []); setDraftBase(p.base);
      setZone({ mode: p.zone_mode, departments: p.departments });
      setFilters(p.filters || { work_types: [], building_types: [], client_types: [] });
    }).catch(() => { setLoading(false); toast.error("Perfil Radar indisponível"); });
  }, [user]);

  useEffect(() => { if (user) load(km); }, [km, load, user]);
  const syncRunning = data?.sync?.departments?.some((d) => d.status === "running");
  useEffect(() => {
    if (!syncRunning) return;
    const timer = setInterval(() => load(km, true), 3000);
    return () => clearInterval(timer);
  }, [syncRunning, load, km]);

  // Init map once
  useEffect(() => {
    if (!mapRef.current || mapObj.current || !data) return;
    mapObj.current = L.map(mapRef.current).setView([data.base.lat, data.base.lon], 11);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      { attribution: "© OpenStreetMap", maxZoom: 19 }).addTo(mapObj.current);
    mapObj.current.on("click", (e) => {
      if (!pickRef.current) return;
      setDraftBase({ lat: +e.latlng.lat.toFixed(5), lon: +e.latlng.lng.toFixed(5), label: "Zona personalizada" });
      setPickZone(false);
      toast.success("Zona reposicionada — não se esqueça de guardar");
    });
    setTimeout(() => mapObj.current?.invalidateSize(), 200);
  }, [data]);

  // Redraw markers
  useEffect(() => {
    if (!mapObj.current) return;
    if (!data) { layer.current?.remove(); return; }
    if (layer.current) layer.current.remove();
    layer.current = L.layerGroup().addTo(mapObj.current);
    const base = draftBase || data.base;
    L.circleMarker([base.lat, base.lon], { radius: 8, color: "#2563eb", fillColor: "#2563eb", fillOpacity: 1 })
      .bindPopup("A sua empresa").addTo(layer.current);
    const points = data.map_points || [];
    points.forEach((o) => {
      const popup = document.createElement("div");
      popup.textContent = `${o.commune} · ${o.count} licenças · centro do concelho`;
      L.circleMarker([o.lat, o.lon], { radius: 9, color: scoreColor(o.score), fillColor: scoreColor(o.score), fillOpacity: 0.85, weight: 2 })
        .bindPopup(popup)
        .on("click", () => openDetail(o.id)).addTo(layer.current);
    });
    if (points.length) {
      mapObj.current.fitBounds(points.map((o) => [o.lat, o.lon]), { padding: [35, 35], maxZoom: 12 });
    } else {
      mapObj.current.setView([data.base.lat, data.base.lon], data.zone_mode === "departments" ? 6 : 11);
    }
  }, [data, draftBase]);

  const openDetail = async (id) => {
    setPostalOpen(false); setCampaign(null); setLetterMsg("");
    try {
      const { data: o } = await api.get(`/radar/opportunities/${id}`);
      setSel(o); setLetterMsg(o.suggested_message || "");
    } catch { toast.error("Ficha indisponível"); }
  };

  const loadCampaigns = useCallback(async () => {
    try { const { data } = await api.get("/radar/campaigns"); setCampaigns(data); }
    catch { toast.error("Acompanhamento indisponível"); }
  }, []);

  const toggleFav = async (id) => {
    try {
      const { data: r } = await api.post(`/radar/opportunities/${id}/favorite`);
      if (sel && sel.id === id) setSel({ ...sel, is_favorite: r.is_favorite });
      load(km);
    } catch { toast.error("Ação impossível"); }
  };

  const toggleMetier = (key) =>
    setDraftMetiers((m) => (m.includes(key) ? m.filter((x) => x !== key) : [...m, key]));

  const saveProfile = async () => {
    setSavingProfile(true);
    try {
      const { data: p } = await api.put("/radar/profile", {
        km, metiers: draftMetiers,
        base: draftBase ? { lat: draftBase.lat, lon: draftBase.lon, label: draftBase.label } : undefined,
      });
      setProfile(p); setDraftMetiers(p.metiers || []); setDraftBase(p.base);
      if (mapObj.current && p.base) mapObj.current.setView([p.base.lat, p.base.lon], 11);
      setShowSettings(false); setPickZone(false);
      toast.success("Perfil Radar guardado");
      load(km);
    } catch { toast.error("Não foi possível guardar"); }
    finally { setSavingProfile(false); }
  };

  const saveZone = async (next, radius = km) => {
    setZoneBusy(true);
    try {
      const { data: p } = await api.put("/radar/profile", { zone_mode: next.mode, departments: next.departments, km: radius });
      setProfile(p); setKm(p.km); setZone({ mode: p.zone_mode, departments: p.departments });
      setPageNumber(1);
      setSel(null); setPostalOpen(false); setCampaign(null);
      toast.success("Zona de pesquisa guardada");
    } catch { toast.error("Impossível memorizar esta zona"); }
    finally { setZoneBusy(false); }
  };

  const saveFilters = async (next) => {
    setFiltersBusy(true);
    try {
      const { data: p } = await api.put("/radar/profile", { filters: next });
      setProfile(p); setFilters(p.filters); setPageNumber(1);
      setSel(null); setPostalOpen(false); setCampaign(null);
    } catch { toast.error("Impossível memorizar os filtros"); }
    finally { setFiltersBusy(false); }
  };

  const categoryLabel = (group, value) => profile?.filter_options?.[group]?.find((item) => item.value === value)?.label || "Não identificado";

  const generateLetter = async () => {
    if (!sel) return;
    setGenLoading(true);
    try {
      const { data: c } = await api.post(`/radar/opportunities/${sel.id}/prospection`, { message: letterMsg });
      setCampaign(c);
      if (showCampaigns) loadCampaigns();
    } catch { toast.error("Impossível gerar"); }
    finally { setGenLoading(false); }
  };

  const writeWithAI = async () => {
    if (!sel) return;
    setAiLoading(true);
    try {
      const { data } = await api.post(`/radar/opportunities/${sel.id}/prospection/ai`, { tone: aiTone, length: aiLength });
      if (data.message) { setLetterMsg(data.message); toast.success("Texto redigido pela IA"); }
    } catch { toast.error("Redação IA indisponível"); }
    finally { setAiLoading(false); }
  };

  const copyLink = async () => {
    try { await navigator.clipboard.writeText(campaign.public_url); setCopied(true); setTimeout(() => setCopied(false), 1500); }
    catch { toast.error("Cópia impossível"); }
  };

  const downloadLetter = () => {
    const url = URL.createObjectURL(b64ToBlob(campaign.letter_b64));
    const a = document.createElement("a");
    a.href = url; a.download = `courrier-${campaign.token}.pdf`; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  };

  if (!user) {
    return (
      <div className="mx-auto max-w-2xl px-5 py-16 text-center grid gap-4" data-testid="radar-page-guest">
        <span className="h-12 w-12 mx-auto grid place-items-center rounded-xl bg-primary/10">
          <Radar className="h-6 w-6 text-primary" />
        </span>
        <h1 className="font-display text-3xl sm:text-4xl font-extrabold tracking-tight">Radar Obras</h1>
        <p className="text-base text-muted-foreground">
          O Radar identifica as licenças de construção publicadas à volta da sua empresa e estima o seu potencial de obra. Precisa da sua zona de atividade e das suas especialidades: crie uma conta profissional para o utilizar.
        </p>
        <div className="flex flex-wrap gap-3 justify-center mt-2">
          <Button asChild className="rounded-sm" data-testid="radar-guest-signup">
            <Link to="/inscription">Criar a minha conta profissional</Link>
          </Button>
          <Button asChild variant="outline" className="rounded-sm" data-testid="radar-guest-login">
            <Link to="/login">Já tenho uma conta</Link>
          </Button>
        </div>
        <p className="text-xs text-muted-foreground mt-2">
          Dados provenientes das licenças de construção publicadas pelas administrações. O potencial apresentado é uma estimativa, não um compromisso de obra.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1500px] px-5 lg:px-8 py-8" data-testid="radar-page">
      <div className="flex items-center gap-3 mb-1 flex-wrap">
        <span className="h-10 w-10 grid place-items-center rounded-xl bg-primary/10"><Radar className="h-5 w-5 text-primary" /></span>
        <div className="flex-1">
          <h1 className="font-display text-2xl font-extrabold tracking-tight">Radar Obras</h1>
          <p className="text-xs text-muted-foreground">Deteta as futuras obras em redor da sua empresa e estima o seu potencial.</p>
        </div>
        <Button variant="outline" size="sm" className="rounded-sm gap-1" onClick={() => { const n = !showCampaigns; setShowCampaigns(n); if (n) loadCampaigns(); }} data-testid="radar-campaigns-btn">
          <BarChart3 className="h-4 w-4" /> Acompanhamento
        </Button>
        <Button variant="outline" size="sm" className="rounded-sm gap-1" onClick={() => setShowSettings((s) => !s)} data-testid="radar-settings-btn">
          <Settings className="h-4 w-4" /> Definições
        </Button>
      </div>

      <RadarOfficialSource sync={data?.sync} onRefresh={() => load(km, true)} />

      {showCampaigns && (
        <div className="surface rounded-xl p-4 my-4" data-testid="radar-campaigns">
          <div className="flex items-center gap-4 mb-3 text-sm">
            <span className="font-bold">Acompanhamento das campanhas</span>
            {campaigns && (
              <span className="text-muted-foreground flex items-center gap-3">
                <span className="inline-flex items-center gap-1"><Eye className="h-3.5 w-3.5" /> {campaigns.total_opens} ouvertures</span>
                <span className="inline-flex items-center gap-1"><Users className="h-3.5 w-3.5" /> {campaigns.total_leads} respostas</span>
              </span>
            )}
          </div>
          {!campaigns && <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> A carregar…</div>}
          {campaigns && campaigns.count === 0 && <p className="text-sm text-muted-foreground">Nenhuma campanha ainda. Gere uma carta de prospeção a partir de uma oportunidade.</p>}
          {campaigns && campaigns.count > 0 && (
            <div className="grid gap-2">
              {campaigns.campaigns.map((c) => (
                <div key={c.token} className="flex items-center justify-between gap-3 rounded-md border border-border p-2.5 text-sm" data-testid={`radar-campaign-row-${c.token}`}>
                  <div className="min-w-0">
                    <div className="font-semibold truncate">{c.batiment}</div>
                    <div className="text-xs text-muted-foreground flex items-center gap-1"><MapPin className="h-3 w-3" /> {c.commune}</div>
                  </div>
                  <div className="flex items-center gap-4 shrink-0">
                    <span className="inline-flex items-center gap-1 text-muted-foreground" title="Aberturas / scans QR"><Eye className="h-3.5 w-3.5" /> {c.open_count}</span>
                    <span className="inline-flex items-center gap-1 font-bold text-primary" title="Potenciais clientes captados"><Users className="h-3.5 w-3.5" /> {c.lead_count}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
          <PostalTrackingPanel />
        </div>
      )}

      {showSettings && profile && (
        <div className="surface rounded-xl p-4 my-4 grid gap-4" data-testid="radar-settings">
          <div>
            <div className="text-xs font-bold uppercase text-muted-foreground mb-2">As suas especialidades (adequação & estimativa)</div>
            <div className="flex flex-wrap gap-1.5">
              {profile.metier_options.map((m) => (
                <button key={m.key} onClick={() => toggleMetier(m.key)} data-testid={`radar-metier-${m.key}`}
                  className={`px-2.5 py-1 rounded-full text-xs font-semibold border transition-colors ${draftMetiers.includes(m.key) ? "bg-primary text-white border-primary" : "border-border text-muted-foreground hover:border-primary"}`}>
                  {m.label}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="text-xs font-bold uppercase text-muted-foreground mb-2">A sua zona (base)</div>
            <div className="flex items-center gap-2 flex-wrap text-sm">
              <span className="inline-flex items-center gap-1 text-muted-foreground"><MapPin className="h-3.5 w-3.5" />
                {(draftBase || profile.base).label || "—"} · {(draftBase || profile.base).lat}, {(draftBase || profile.base).lon}</span>
              <Button variant={pickZone ? "default" : "outline"} size="sm" className="rounded-sm gap-1" onClick={() => { setShowSettings(true); setPickZone((p) => !p); }} data-testid="radar-pick-zone">
                <Crosshair className="h-3.5 w-3.5" /> {pickZone ? "Clique no mapa…" : "Reposicionar no mapa"}
              </Button>
            </div>
          </div>
          <div className="flex justify-end">
            <Button size="sm" className="rounded-sm gap-1" onClick={saveProfile} disabled={savingProfile} data-testid="radar-save-profile">
              {savingProfile ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} Guardar
            </Button>
          </div>
        </div>
      )}

      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 my-5">
          {[["Oportunidades", stats.detected], ["Fortes (≥85)", stats.strong], ["Potencial (o seu lote)", eur(stats.potential_ttc)], ["Favoritos", stats.favorites]].map(([l, v], i) => (
            <div key={i} className="surface rounded-xl p-3 min-w-0" data-testid={`radar-kpi-${i}`}>
              <div className="text-lg font-extrabold text-primary break-words" title={String(v)}>{i === 2 ? <><span className="sm:hidden">{new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", notation: "compact", maximumFractionDigits: 1 }).format(stats.potential_ttc)}</span><span className="hidden sm:inline">{v}</span></> : v}</div>
              <div className="text-[11px] text-muted-foreground">{l}</div>
            </div>
          ))}
        </div>
      )}

      {zone && <RadarZoneFilter zone={zone} options={profile?.department_options || []} km={km} busy={zoneBusy}
        onApply={saveZone} onRadius={(r) => saveZone({ ...zone, mode: "radius" }, r)} />}

      {filters && <RadarProjectFilters value={filters} options={profile?.filter_options || {}} facets={data?.facets} busy={filtersBusy} onApply={saveFilters} count={loading ? undefined : data?.count} />}
      {loadError && <div role="alert" className="flex flex-wrap gap-3 items-center py-4 text-sm" data-testid="radar-load-error">Impossível carregar os resultados.<Button variant="outline" size="sm" onClick={() => load(km)} data-testid="radar-load-retry">Tentar novamente</Button></div>}

      <div className="grid lg:grid-cols-2 gap-5">
        <div className={`rounded-xl overflow-hidden border border-border h-[360px] lg:h-[560px] relative z-0 ${loading ? "opacity-50 pointer-events-none" : ""}`} aria-busy={loading} ref={mapRef} data-testid="radar-map" />

        <div className="grid gap-3 max-h-[560px] overflow-auto pr-1 min-w-0" data-testid="radar-list">
          {loading && <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> A carregar…</div>}
          {!loading && data?.opportunities.map((o) => (
            <button key={o.id} onClick={() => openDetail(o.id)} data-testid={`radar-opp-${o.id}`}
              className="surface rounded-xl p-4 text-left hover:border-primary transition-colors min-w-0 max-w-full">
              <div className="flex items-start justify-between gap-3 flex-wrap sm:flex-nowrap">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-muted-foreground break-all">{o.id}</span>
                    {o.is_demo && <span className="text-[10px] text-amber-700" data-testid={`radar-demo-${o.id}`}>FICTÍCIO</span>}
                    {o.is_favorite && <Star className="h-3.5 w-3.5 fill-primary text-primary" />}
                  </div>
                  <div className="font-bold text-sm mt-0.5">{o.batiment}</div>
                  <p className="text-xs text-primary mt-1 break-words" data-testid={`radar-categories-${o.id}`}>{(o.classification?.building_types || []).map((value) => categoryLabel("building_types", value)).join(" · ")} · {categoryLabel("client_types", o.classification?.client_type)}</p>
                  <div className="text-xs text-muted-foreground flex items-center gap-2 mt-1" data-testid={`radar-location-${o.id}`}>
                    <MapPin className="h-3 w-3 shrink-0" /> {o.commune} · {o.distance_km == null ? "Posição não localizada" : `≈ ${o.distance_km} km`} · {o.surf_created ? `${o.surf_created} m²` : "Área não utilizável"}
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <div className="inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-extrabold text-white" style={{ background: scoreColor(o.score) }} title="Pontuação indicativa ConstruPilot" data-testid={`radar-score-${o.id}`}>
                    <Flame className="h-3 w-3" /> {o.score}
                  </div>
                  <div className="text-[11px] text-muted-foreground mt-1">A sua especialidade</div>
                  <div className="text-xs font-bold" data-testid={`radar-estimate-${o.id}`}>{o.my_lot_high ? `${eur(o.my_lot_low)}–${eur(o.my_lot_high)}` : "Não estimado"}</div>
                </div>
              </div>
            </button>
          ))}
          {!loading && data?.count === 0 && <p className="text-sm text-muted-foreground" data-testid="radar-empty-zone">{syncRunning ? "A obter as licenças oficiais…" : data?.unfiltered_count > 0 ? "Nenhuma licença corresponde a estes filtros na zona selecionada." : "Nenhuma licença oficial disponível nesta zona e período. Não serão apresentados exemplos fictícios."}</p>}
        </div>
      </div>

      {data && data.count > 0 && <nav className="flex flex-wrap items-center justify-end gap-3 mt-4" aria-label="Páginas das licenças" data-testid="radar-pagination">
        <Button size="sm" variant="outline" disabled={loading || pageNumber <= 1} onClick={() => setPageNumber((p) => p - 1)} data-testid="radar-page-previous">Anterior</Button>
        <span className="text-xs" data-testid="radar-page-number">Página {pageNumber} / {Math.max(1, Math.ceil(data.count / data.page_size))} · {data.count} permis</span>
        <Button size="sm" variant="outline" disabled={loading || pageNumber * data.page_size >= data.count} onClick={() => setPageNumber((p) => p + 1)} data-testid="radar-page-next">Seguinte</Button>
      </nav>}

      {sel && typeof sel === "object" && (
        <div className="fixed inset-0 z-[110] bg-black/50 flex justify-end" onClick={() => setSel(null)} data-testid="radar-detail">
          <div className="w-full max-w-md bg-background h-full overflow-auto p-6" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono text-muted-foreground break-all" data-testid="radar-detail-permit-id">{sel.id}</span>
              <button onClick={() => setSel(null)} data-testid="radar-detail-close"><X className="h-5 w-5" /></button>
            </div>
            <div className="flex items-center gap-2 mt-2 flex-wrap">
              <span className="rounded-full px-2.5 py-1 text-sm font-extrabold text-white" style={{ background: scoreColor(sel.score) }} title="Pontuação indicativa ConstruPilot" data-testid="radar-detail-score">{sel.score}/100</span>
              <span className="text-[11px] rounded-full px-2 py-0.5 border border-border" data-testid="radar-detail-client-type">{categoryLabel("client_types", sel.classification?.client_type)}</span>
              <span data-testid="radar-contact-status" className={`text-[11px] rounded-full px-2 py-0.5 ${sel.contact_status === "green" ? "bg-emerald-500/15 text-emerald-600" : "bg-amber-500/15 text-amber-600"}`}>
                {sel.is_demo ? "FICHA FICTÍCIA" : sel.contact_status === "green" ? "Dados completos · por verificar" : "Contacto por completar / verificar"}
              </span>
            </div>
            <h2 className="font-display text-xl font-bold mt-3">{sel.batiment}</h2>
            <p className="text-sm text-muted-foreground flex items-center gap-2 mt-1" data-testid="radar-detail-location"><MapPin className="h-4 w-4 shrink-0" /> {sel.commune} ({sel.cp}) · {sel.distance_km == null ? "Não localizado" : `≈ ${sel.distance_km} km · centre communal`}</p>
            <p className="text-sm mt-2 break-words" data-testid="radar-real-site-address">Terrain : {[sel.adresse, sel.adresse_complement, sel.cp, sel.commune].filter(Boolean).join(", ")}</p>
            {Object.keys(sel.source_text_corrections || {}).length > 0 && <p className="text-xs text-muted-foreground" data-testid="radar-address-encoding-note">Codificação do texto normalizada · original conservado na fonte.</p>}
            <RadarQualification key={`qualification-${sel.id}`} opp={sel} options={profile?.filter_options?.client_types || []} onUpdated={(o) => { setSel(o); load(km); }} />
            <RadarContactPanel key={sel.id} opp={sel} onUpdated={(o) => { setSel(o); load(km); }} />
            <div className="grid grid-cols-2 gap-2 mt-4 text-sm">
              {[["Tipo", sel.type], ["Natureza", sel.nature], ["Área publicada", sel.surf_created ? `${sel.surf_created} m²` : "Não utilizável"], ["Habitações", sel.logements], ["Autorização", sel.date_auth || "Não comunicada"], ["N°", sel.num], ["Estado SDES", sel.statut]].map(([l, v], i) => (
                <div key={i} className="surface rounded-md p-2 min-w-0" data-testid={`radar-permit-field-${i}`}><div className="text-[10px] uppercase text-muted-foreground">{l}</div><div className="font-semibold break-words">{v}</div></div>
              ))}
            </div>
            <p className="text-xs text-muted-foreground mt-2" data-testid="radar-surface-basis">{sel.surface_basis}</p>
            <div className="surface rounded-xl p-3 mt-4">
              <div className="flex items-center gap-2 text-sm font-bold"><TrendingUp className="h-4 w-4 text-primary" /> Estimativa preliminar</div>
              <div className="text-xs text-muted-foreground mt-1" data-testid="radar-project-estimate">Projeto total: <b>{sel.estimate_high ? `${eur(sel.estimate_low)}–${eur(sel.estimate_high)}` : "Não estimado — área não utilizável"}</b></div>
              <div className="text-xs mt-1" data-testid="radar-personal-estimate">O seu mercado potencial: <b className="text-primary">{sel.my_lot_high ? `${eur(sel.my_lot_low)}–${eur(sel.my_lot_high)}` : "Não estimado"}</b></div>
              <div className="mt-3 grid gap-1">
                {sel.lots.map((l) => (
                  <div key={l.metier} className="flex justify-between text-xs"><span>{l.label}</span><span className="text-muted-foreground">{eur(l.low)}–{eur(l.high)}</span></div>
                ))}
              </div>
              <p className="text-[10px] text-muted-foreground mt-2">Estimativa indicativa baseada nos dados públicos disponíveis — a confirmar.</p>
            </div>

            <div className="mt-4">
              <label className="text-xs font-bold uppercase text-muted-foreground">Texto da carta (personalizável)</label>
              <div className="flex items-center gap-2 mt-1.5 flex-wrap" data-testid="radar-ai-controls">
                <select value={aiTone} onChange={(e) => setAiTone(e.target.value)} data-testid="radar-ai-tone"
                  className="h-8 rounded-md border border-border bg-background text-xs px-2">
                  <option value="formel">Tom: formal</option>
                  <option value="chaleureux">Tom: caloroso</option>
                  <option value="direct">Tom: direto</option>
                  <option value="commercial">Tom: comercial</option>
                </select>
                <select value={aiLength} onChange={(e) => setAiLength(e.target.value)} data-testid="radar-ai-length"
                  className="h-8 rounded-md border border-border bg-background text-xs px-2">
                  <option value="court">Comprimento: curto</option>
                  <option value="moyen">Comprimento: médio</option>
                  <option value="long">Comprimento: longo</option>
                </select>
                <Button variant="outline" size="sm" className="rounded-sm gap-1 h-8" onClick={writeWithAI} disabled={aiLoading || sel.is_demo} data-testid="radar-ai-write">
                  {aiLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />} Redigir com a IA
                </Button>
              </div>
              <Textarea value={letterMsg} onChange={(e) => setLetterMsg(e.target.value)} rows={6}
                className="mt-2 text-sm" data-testid="radar-letter-message"
                placeholder="Redija o texto da sua carta de prospeção…" />
              <p className="text-[10px] text-muted-foreground mt-1">Este texto aparecerá no correio PDF. Pode adaptá-lo e depois (re)gerar.</p>
            </div>

            <div className="flex flex-wrap gap-2 mt-3">
              <Button variant="outline" className="rounded-sm gap-1 flex-1" onClick={() => toggleFav(sel.id)} data-testid="radar-detail-fav">
                <Star className={`h-4 w-4 ${sel.is_favorite ? "fill-primary text-primary" : ""}`} /> {sel.is_favorite ? "Favorito" : "Adicionar aos favoritos"}
              </Button>
              <Button className="rounded-sm gap-1 flex-1 whitespace-normal h-auto min-h-9" onClick={generateLetter} disabled={genLoading || sel.is_demo} data-testid="radar-generate-letter">
                {genLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mail className="h-4 w-4" />} {campaign ? "Regenerar" : "Gerar a carta"}
              </Button>
            </div>

            {campaign && (
              <div className="surface rounded-xl p-4 mt-4" data-testid="radar-campaign">
                <div className="text-sm font-bold mb-2">Carta + QR prontos</div>
                <div className="flex gap-4 items-center">
                  <img src={campaign.qr_b64} alt="QR" className="h-28 w-28 rounded-md bg-white p-1 border border-border" data-testid="radar-campaign-qr" />
                  <div className="text-xs flex-1 break-all">
                    <div className="text-muted-foreground mb-1">Link da landing (no QR):</div>
                    <div className="font-mono">{campaign.public_url}</div>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2 mt-3">
                  <Button variant="outline" size="sm" className="rounded-sm gap-1 flex-1" onClick={copyLink} data-testid="radar-campaign-copy">
                    {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />} {copied ? "Copiado" : "Copiar o link"}
                  </Button>
                  <Button size="sm" className="rounded-sm gap-1 flex-1" onClick={downloadLetter} data-testid="radar-campaign-download">
                    <Download className="h-3.5 w-3.5" /> Descarregar a carta
                  </Button>
                </div>
                <Button size="sm" variant="outline" className="rounded-sm gap-1 w-full mt-2 border-primary/40 text-primary" onClick={() => setPostalOpen(true)} data-testid="radar-campaign-postal">
                  <Truck className="h-3.5 w-3.5" /> Enviar por correio (Merci Facteur)
                </Button>
                <PostalSendDialog open={postalOpen} onClose={() => setPostalOpen(false)} campaign={campaign} opp={sel} />
                <p className="text-[10px] text-muted-foreground mt-2">Imprima e envie a correspondência, ou deixe o Merci Facteur fazê-lo. O potencial cliente que digitaliza o QR ou abre o link pode pedir uma estimativa — o seu pedido chega a «Os meus pedidos».</p>
              </div>
            )}

            <p className="text-xs text-muted-foreground mt-3" data-testid="radar-permit-source">Fonte: {sel.source?.name} · publication {sel.source?.millesime}</p>
            {sel.source?.record_url && <a href={sel.source.record_url} target="_blank" rel="noopener noreferrer" className="inline-block text-xs text-primary underline mt-1" data-testid="radar-record-source-link">Ver a licença na fonte oficial</a>}
          </div>
        </div>
      )}
    </div>
  );
}
