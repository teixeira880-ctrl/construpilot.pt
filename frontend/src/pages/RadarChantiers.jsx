import { useEffect, useRef, useState, useCallback } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import {
  Radar, MapPin, Star, Flame, TrendingUp, Building2, X, Loader2,
  Settings, Mail, Copy, Download, Check, Crosshair,
} from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

const eur = (n) => (Number(n) || 0).toLocaleString("fr-FR") + " €";
const scoreColor = (s) => (s >= 85 ? "#ef4444" : s >= 65 ? "#f59e0b" : "#16a34a");
const RADII = [10, 20, 30, 50, 100];

function b64ToBlob(dataUrl) {
  const [meta, b64] = dataUrl.split(",");
  const mime = /:(.*?);/.exec(meta)?.[1] || "application/octet-stream";
  const bin = atob(b64);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  return new Blob([arr], { type: mime });
}

export default function RadarChantiers() {
  const [data, setData] = useState(null);
  const [km, setKm] = useState(30);
  const [sel, setSel] = useState(null);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [profile, setProfile] = useState(null);
  const [showSettings, setShowSettings] = useState(false);
  const [pickZone, setPickZone] = useState(false);
  const [draftMetiers, setDraftMetiers] = useState([]);
  const [draftBase, setDraftBase] = useState(null);
  const [savingProfile, setSavingProfile] = useState(false);
  const [campaign, setCampaign] = useState(null);
  const [genLoading, setGenLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const mapRef = useRef(null);
  const mapObj = useRef(null);
  const layer = useRef(null);
  const pickRef = useRef(false);
  useEffect(() => { pickRef.current = pickZone; }, [pickZone]);

  const load = useCallback(async (radius) => {
    setLoading(true);
    try {
      const [{ data: d }, { data: st }] = await Promise.all([
        api.get(`/radar/opportunities?km=${radius}`),
        api.get("/radar/stats"),
      ]);
      setData(d); setStats(st);
    } catch { toast.error("Impossible de charger le Radar"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    api.get("/radar/profile").then(({ data: p }) => {
      setProfile(p); setKm(p.km); setDraftMetiers(p.metiers || []); setDraftBase(p.base);
    }).catch(() => {});
  }, []);

  useEffect(() => { load(km); }, [km, load]);

  // Init map once
  useEffect(() => {
    if (!mapRef.current || mapObj.current || !data) return;
    mapObj.current = L.map(mapRef.current).setView([data.base.lat, data.base.lon], 11);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      { attribution: "© OpenStreetMap", maxZoom: 19 }).addTo(mapObj.current);
    mapObj.current.on("click", (e) => {
      if (!pickRef.current) return;
      setDraftBase({ lat: +e.latlng.lat.toFixed(5), lon: +e.latlng.lng.toFixed(5), label: "Zone personnalisée" });
      setPickZone(false);
      toast.success("Zone repositionnée — pensez à enregistrer");
    });
    setTimeout(() => mapObj.current?.invalidateSize(), 200);
  }, [data]);

  // Redraw markers
  useEffect(() => {
    if (!mapObj.current || !data) return;
    if (layer.current) layer.current.remove();
    layer.current = L.layerGroup().addTo(mapObj.current);
    const base = draftBase || data.base;
    L.circleMarker([base.lat, base.lon], { radius: 8, color: "#2563eb", fillColor: "#2563eb", fillOpacity: 1 })
      .bindPopup("Votre entreprise").addTo(layer.current);
    data.opportunities.forEach((o) => {
      L.circleMarker([o.lat, o.lon], { radius: 9, color: scoreColor(o.score), fillColor: scoreColor(o.score), fillOpacity: 0.85, weight: 2 })
        .bindPopup(`<b>${o.commune}</b><br/>${o.batiment}<br/>Score ${o.score}/100`)
        .on("click", () => openDetail(o.id)).addTo(layer.current);
    });
  }, [data, draftBase]);

  const openDetail = async (id) => {
    setCampaign(null);
    try { const { data: o } = await api.get(`/radar/opportunities/${id}`); setSel(o); }
    catch { toast.error("Fiche indisponible"); }
  };

  const toggleFav = async (id) => {
    try {
      const { data: r } = await api.post(`/radar/opportunities/${id}/favorite`);
      if (sel && sel.id === id) setSel({ ...sel, is_favorite: r.is_favorite });
      load(km);
    } catch { toast.error("Action impossible"); }
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
      toast.success("Profil Radar enregistré");
      load(km);
    } catch { toast.error("Enregistrement impossible"); }
    finally { setSavingProfile(false); }
  };

  const generateLetter = async () => {
    if (!sel) return;
    setGenLoading(true);
    try {
      const { data: c } = await api.post(`/radar/opportunities/${sel.id}/prospection`, { message: "" });
      setCampaign(c);
    } catch { toast.error("Génération impossible"); }
    finally { setGenLoading(false); }
  };

  const copyLink = async () => {
    try { await navigator.clipboard.writeText(campaign.public_url); setCopied(true); setTimeout(() => setCopied(false), 1500); }
    catch { toast.error("Copie impossible"); }
  };

  const downloadLetter = () => {
    const url = URL.createObjectURL(b64ToBlob(campaign.letter_b64));
    const a = document.createElement("a");
    a.href = url; a.download = `courrier-${campaign.token}.pdf`; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  };

  return (
    <div className="mx-auto max-w-[1500px] px-5 lg:px-8 py-8" data-testid="radar-page">
      <div className="flex items-center gap-3 mb-1">
        <span className="h-10 w-10 grid place-items-center rounded-xl bg-primary/10"><Radar className="h-5 w-5 text-primary" /></span>
        <div className="flex-1">
          <h1 className="font-display text-2xl font-extrabold tracking-tight">Radar Chantiers</h1>
          <p className="text-xs text-muted-foreground">Détecte les futurs chantiers autour de votre entreprise et estime leur potentiel.</p>
        </div>
        <Button variant="outline" size="sm" className="rounded-sm gap-1" onClick={() => setShowSettings((s) => !s)} data-testid="radar-settings-btn">
          <Settings className="h-4 w-4" /> Réglages
        </Button>
      </div>

      {showSettings && profile && (
        <div className="surface rounded-xl p-4 my-4 grid gap-4" data-testid="radar-settings">
          <div>
            <div className="text-xs font-bold uppercase text-muted-foreground mb-2">Vos métiers (adéquation & estimation)</div>
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
            <div className="text-xs font-bold uppercase text-muted-foreground mb-2">Votre zone (base)</div>
            <div className="flex items-center gap-2 flex-wrap text-sm">
              <span className="inline-flex items-center gap-1 text-muted-foreground"><MapPin className="h-3.5 w-3.5" />
                {(draftBase || profile.base).label || "—"} · {(draftBase || profile.base).lat}, {(draftBase || profile.base).lon}</span>
              <Button variant={pickZone ? "default" : "outline"} size="sm" className="rounded-sm gap-1" onClick={() => { setShowSettings(true); setPickZone((p) => !p); }} data-testid="radar-pick-zone">
                <Crosshair className="h-3.5 w-3.5" /> {pickZone ? "Cliquez sur la carte…" : "Repositionner sur la carte"}
              </Button>
            </div>
          </div>
          <div className="flex justify-end">
            <Button size="sm" className="rounded-sm gap-1" onClick={saveProfile} disabled={savingProfile} data-testid="radar-save-profile">
              {savingProfile ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} Enregistrer
            </Button>
          </div>
        </div>
      )}

      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 my-5">
          {[["Opportunités", stats.detected], ["Fortes (≥85)", stats.strong], ["Potentiel (votre lot)", eur(stats.potential_ttc)], ["Favoris", stats.favorites]].map(([l, v], i) => (
            <div key={i} className="surface rounded-xl p-3" data-testid={`radar-kpi-${i}`}>
              <div className="text-lg font-extrabold text-primary">{v}</div>
              <div className="text-[11px] text-muted-foreground">{l}</div>
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <span className="text-xs font-bold uppercase text-muted-foreground">Rayon</span>
        {RADII.map((r) => (
          <button key={r} onClick={() => setKm(r)} data-testid={`radar-km-${r}`}
            className={`px-3 py-1 rounded-full text-xs font-bold border ${km === r ? "bg-primary text-white border-primary" : "border-border text-muted-foreground hover:border-primary"}`}>
            {r} km
          </button>
        ))}
      </div>

      <div className="grid lg:grid-cols-2 gap-5">
        <div className="rounded-xl overflow-hidden border border-border h-[360px] lg:h-[560px] relative z-0" ref={mapRef} data-testid="radar-map" />

        <div className="grid gap-3 max-h-[560px] overflow-auto pr-1" data-testid="radar-list">
          {loading && <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Chargement…</div>}
          {!loading && data?.opportunities.map((o) => (
            <button key={o.id} onClick={() => openDetail(o.id)} data-testid={`radar-opp-${o.id}`}
              className="surface rounded-xl p-4 text-left hover:border-primary transition-colors">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-muted-foreground">{o.id}</span>
                    {o.is_favorite && <Star className="h-3.5 w-3.5 fill-primary text-primary" />}
                  </div>
                  <div className="font-bold text-sm mt-0.5">{o.batiment}</div>
                  <div className="text-xs text-muted-foreground flex items-center gap-2 mt-1">
                    <MapPin className="h-3 w-3" /> {o.commune} · {o.distance_km} km · {o.surf_created} m²
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <div className="inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-extrabold text-white" style={{ background: scoreColor(o.score) }}>
                    <Flame className="h-3 w-3" /> {o.score}
                  </div>
                  <div className="text-[11px] text-muted-foreground mt-1">Votre lot</div>
                  <div className="text-xs font-bold">{eur(o.my_lot_low)}–{eur(o.my_lot_high)}</div>
                </div>
              </div>
            </button>
          ))}
          {!loading && data?.count === 0 && <p className="text-sm text-muted-foreground">Aucune opportunité dans ce rayon.</p>}
        </div>
      </div>

      {sel && typeof sel === "object" && (
        <div className="fixed inset-0 z-[70] bg-black/50 flex justify-end" onClick={() => setSel(null)} data-testid="radar-detail">
          <div className="w-full max-w-md bg-background h-full overflow-auto p-6" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono text-muted-foreground">{sel.id}</span>
              <button onClick={() => setSel(null)} data-testid="radar-detail-close"><X className="h-5 w-5" /></button>
            </div>
            <div className="flex items-center gap-2 mt-2 flex-wrap">
              <span className="rounded-full px-2.5 py-1 text-sm font-extrabold text-white" style={{ background: scoreColor(sel.score) }}>{sel.score}/100</span>
              <span className="text-[11px] rounded-full px-2 py-0.5 border border-border">{sel.mo}</span>
              <span className={`text-[11px] rounded-full px-2 py-0.5 ${sel.contact_status === "green" ? "bg-emerald-500/15 text-emerald-600" : "bg-amber-500/15 text-amber-600"}`}>
                {sel.contact_status === "green" ? "🟢 Contact possible" : "🟠 Contact sous conditions"}
              </span>
            </div>
            <h2 className="font-display text-xl font-bold mt-3">{sel.batiment}</h2>
            <p className="text-sm text-muted-foreground flex items-center gap-2 mt-1"><MapPin className="h-4 w-4" /> {sel.commune} ({sel.cp}) · {sel.distance_km} km</p>
            <div className="grid grid-cols-2 gap-2 mt-4 text-sm">
              {[["Type", sel.type], ["Nature", sel.nature], ["Surface créée", `${sel.surf_created} m²`], ["Logements", sel.logements], ["Autorisation", sel.date_auth], ["N°", sel.num]].map(([l, v], i) => (
                <div key={i} className="surface rounded-md p-2"><div className="text-[10px] uppercase text-muted-foreground">{l}</div><div className="font-semibold">{v}</div></div>
              ))}
            </div>
            <div className="surface rounded-xl p-3 mt-4">
              <div className="flex items-center gap-2 text-sm font-bold"><TrendingUp className="h-4 w-4 text-primary" /> Estimation préliminaire</div>
              <div className="text-xs text-muted-foreground mt-1">Projet total : <b>{eur(sel.estimate_low)}–{eur(sel.estimate_high)}</b></div>
              <div className="text-xs mt-1">Votre marché potentiel : <b className="text-primary">{eur(sel.my_lot_low)}–{eur(sel.my_lot_high)}</b></div>
              <div className="mt-3 grid gap-1">
                {sel.lots.map((l) => (
                  <div key={l.metier} className="flex justify-between text-xs"><span>{l.label}</span><span className="text-muted-foreground">{eur(l.low)}–{eur(l.high)}</span></div>
                ))}
              </div>
              <p className="text-[10px] text-muted-foreground mt-2">Estimation indicative basée sur les données publiques disponibles — à confirmer.</p>
            </div>

            <div className="flex gap-2 mt-4">
              <Button variant="outline" className="rounded-sm gap-1 flex-1" onClick={() => toggleFav(sel.id)} data-testid="radar-detail-fav">
                <Star className={`h-4 w-4 ${sel.is_favorite ? "fill-primary text-primary" : ""}`} /> {sel.is_favorite ? "Favori" : "Ajouter aux favoris"}
              </Button>
              <Button className="rounded-sm gap-1 flex-1" onClick={generateLetter} disabled={genLoading} data-testid="radar-generate-letter">
                {genLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mail className="h-4 w-4" />} Courrier de prospection
              </Button>
            </div>

            {campaign && (
              <div className="surface rounded-xl p-4 mt-4" data-testid="radar-campaign">
                <div className="text-sm font-bold mb-2">Courrier + QR prêts</div>
                <div className="flex gap-4 items-center">
                  <img src={campaign.qr_b64} alt="QR" className="h-28 w-28 rounded-md bg-white p-1 border border-border" data-testid="radar-campaign-qr" />
                  <div className="text-xs flex-1 break-all">
                    <div className="text-muted-foreground mb-1">Lien de la landing (dans le QR) :</div>
                    <div className="font-mono">{campaign.public_url}</div>
                  </div>
                </div>
                <div className="flex gap-2 mt-3">
                  <Button variant="outline" size="sm" className="rounded-sm gap-1 flex-1" onClick={copyLink} data-testid="radar-campaign-copy">
                    {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />} {copied ? "Copié" : "Copier le lien"}
                  </Button>
                  <Button size="sm" className="rounded-sm gap-1 flex-1" onClick={downloadLetter} data-testid="radar-campaign-download">
                    <Download className="h-3.5 w-3.5" /> Télécharger le courrier
                  </Button>
                </div>
                <p className="text-[10px] text-muted-foreground mt-2">Imprimez et postez le courrier. Le prospect qui scanne le QR ou ouvre le lien peut demander une estimation — sa demande arrive dans « Mes demandes ».</p>
              </div>
            )}

            <p className="text-[10px] text-muted-foreground mt-3 flex items-center gap-1"><Building2 className="h-3 w-3" /> Source : {sel.source?.name} · donnée publique</p>
          </div>
        </div>
      )}
    </div>
  );
}
