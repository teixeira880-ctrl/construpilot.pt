// ConstruPilot BIM Studio — modelos IFC, visualização 3D, medições rastreáveis e orçamento.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import BimViewer from "@/components/bim/BimViewer";
import { BTN_GHOST, BTN_PRIMARY, BudgetTab, ElementPanel, MeasurementsTab, VersionsTab } from "@/components/bim/BimPanels";
import { PROFILE_COPY, SIMPLE_STEPS, formatQty } from "@/components/bim/bimGeometry";

const FINAL = ["done", "failed", "cancelled"];
const TABS = [["modelo", "Modelo 3D"], ["medicoes", "Medições"], ["orcamento", "Orçamento"], ["versoes", "Versões"]];

export default function BimStudio() {
  const [cfg, setCfg] = useState(null);
  const [models, setModels] = useState([]);
  const [model, setModel] = useState(null);
  const [version, setVersion] = useState(null);
  const [tab, setTab] = useState("modelo");
  const [uploading, setUploading] = useState(false);
  const [selected, setSelected] = useState(null);
  const [meta, setMeta] = useState({});
  const [filters, setFilters] = useState({ storeys: new Set(), categories: new Set(), hidden: new Set(), isolated: new Set() });
  const [highlight, setHighlight] = useState(null);
  const [measuring, setMeasuring] = useState(false);
  const [measure, setMeasure] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const fileRef = useRef(null);
  const newVersionFor = useRef(null);
  const viewerRef = useRef(null);
  const pollRef = useRef(null);

  const profile = cfg?.profile || null;
  const canEdit = true; // o backend aplica as permissões; os erros 403 são mostrados ao utilizador
  const base = model && version ? `/bim/models/${model.model_id}/versions/${version.version}` : null;

  const loadModels = useCallback(() => api.get("/bim/models").then(({ data }) => setModels(data.items || [])).catch(() => {}), []);

  useEffect(() => {
    api.get("/bim/config").then(({ data }) => { setCfg(data); if (data.profile) setTab(PROFILE_COPY[data.profile]?.tab || "modelo"); })
      .catch(() => setCfg({ enabled: false }));
    loadModels();
    return () => clearTimeout(pollRef.current);
  }, [loadModels]);

  const openModel = useCallback(async (modelId, v = null) => {
    clearTimeout(pollRef.current);
    const { data } = await api.get(`/bim/models/${modelId}`);
    setModel(data);
    const target = v ? data.versions.find((x) => x.version === v) : (data.versions.find((x) => x.status === "done") || data.versions[0]);
    setVersion(target || null);
    setSelected(null);
    setFilters({ storeys: new Set(), categories: new Set(), hidden: new Set(), isolated: new Set() });
    if (target && !FINAL.includes(target.status)) {
      const poll = async () => {
        const { data: st } = await api.get(`/bim/models/${modelId}/versions/${target.version}`);
        setVersion(st);
        if (!FINAL.includes(st.status)) pollRef.current = setTimeout(poll, 1500);
        else { loadModels(); if (st.status === "done") openModel(modelId, st.version); else if (st.status === "failed") toast.error(st.error || "Processamento falhado"); }
      };
      pollRef.current = setTimeout(poll, 1000);
    }
  }, [loadModels]);

  // Metadados leves (categoria/piso) para filtros do visualizador
  useEffect(() => {
    if (!base || version?.status !== "done") { setMeta({}); return; }
    let cancelled = false;
    (async () => {
      const out = {};
      for (let skip = 0; skip < 60000; skip += 1000) {
        const { data } = await api.get(`${base}/elements?limit=1000&skip=${skip}`);
        data.items.forEach((e) => { out[e.gid] = { gid: e.gid, category: e.category, storey_gid: e.storey_gid }; });
        if (cancelled || skip + 1000 >= data.total) break;
      }
      if (!cancelled) setMeta(out);
    })().catch(() => {});
    return () => { cancelled = true; };
  }, [base, version?.status]);

  const upload = async (file) => {
    if (!file) return;
    if (cfg?.max_upload_mb && file.size > cfg.max_upload_mb * 1024 * 1024) { toast.error(`Ficheiro demasiado grande (máximo ${cfg.max_upload_mb} MB).`); return; }
    const fd = new FormData();
    fd.append("file", file);
    if (newVersionFor.current) fd.append("model_id", newVersionFor.current);
    setUploading(true);
    try {
      const { data } = await api.post("/bim/models", fd);
      toast.success(data.version > 1 ? `Versão ${data.version} carregada — em processamento` : "Modelo carregado — em processamento");
      await loadModels();
      await openModel(data.model_id, data.version);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Envio impossível");
    } finally {
      setUploading(false);
      newVersionFor.current = null;
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const setProfile = async (p) => {
    await api.put("/bim/prefs", { profile: p }).catch(() => {});
    setCfg((c) => ({ ...c, profile: p }));
    setTab(PROFILE_COPY[p].tab);
  };

  const toggleSet = (key, value) => setFilters((f) => {
    const s = new Set(f[key]);
    if (s.has(value)) s.delete(value); else s.add(value);
    return { ...f, [key]: s };
  });

  const highlighted = useMemo(() => (highlight ? new Set(highlight) : null), [highlight]);
  const categoriesPresent = useMemo(() => Object.entries(version?.stats?.by_category || {}), [version]);

  if (cfg && !cfg.enabled) {
    return <div className="max-w-3xl mx-auto p-8 text-center text-muted-foreground" data-testid="bim-disabled">O BIM Studio ainda não está disponível na sua conta.</div>;
  }

  return (
    <div className="max-w-[1500px] mx-auto px-4 py-6 space-y-5" data-testid="bim-studio-page">
      <header className="flex flex-wrap items-end gap-4 justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#c4733f]">ConstruPilot</p>
          <h1 className="text-2xl md:text-3xl font-semibold">BIM Studio</h1>
          <p className="text-sm text-muted-foreground max-w-2xl">{profile ? PROFILE_COPY[profile].intro : "Carregue um modelo IFC, veja o edifício em 3D, verifique as medições e gere o orçamento com os preços da sua empresa."}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex rounded-xl border p-0.5 text-xs" role="tablist" aria-label="Perfil">
            {Object.entries(PROFILE_COPY).map(([k, v]) => (
              <button key={k} type="button" onClick={() => setProfile(k)} className={`px-2.5 py-1.5 rounded-lg ${profile === k ? "bg-primary text-primary-foreground" : "hover:bg-accent"}`} data-testid={`bim-profile-${k}`}>{v.label}</button>
            ))}
          </div>
          <input ref={fileRef} type="file" accept=".ifc" className="hidden" onChange={(e) => upload(e.target.files?.[0])} data-testid="bim-file-input" />
          <button type="button" className={BTN_PRIMARY} disabled={uploading} onClick={() => fileRef.current?.click()} data-testid="bim-upload-btn">{uploading ? "A enviar…" : "Carregar modelo IFC"}</button>
        </div>
      </header>

      {profile === "simples" && (
        <ol className="grid md:grid-cols-5 gap-2 text-xs" data-testid="bim-simple-steps">
          {SIMPLE_STEPS.map((s, i) => <li key={s} className="rounded-xl border bg-card p-3"><span className="font-semibold text-[#c4733f] mr-1">{i + 1}.</span>{s}</li>)}
        </ol>
      )}

      <div className="grid lg:grid-cols-[260px_1fr] gap-5">
        <aside className="space-y-2" data-testid="bim-models-list">
          <h2 className="text-sm font-semibold">Os seus modelos</h2>
          {models.length === 0 && <p className="text-xs text-muted-foreground">Ainda não carregou nenhum modelo. Aceita ficheiros .ifc (IFC2x3 e IFC4) até {cfg?.max_upload_mb || 200} MB.</p>}
          {models.map((m) => (
            <button key={m.model_id} type="button" onClick={() => openModel(m.model_id)}
                    className={`w-full text-left rounded-xl border px-3 py-2 text-sm hover:bg-accent ${model?.model_id === m.model_id ? "border-primary bg-accent" : ""}`}>
              <div className="font-medium truncate">{m.name}</div>
              <div className="text-xs text-muted-foreground">v{m.latest_version} · {m.latest?.status === "done" ? `${m.latest.stats?.elements ?? 0} elementos` : (m.latest?.stage || m.latest?.status)}</div>
            </button>
          ))}
        </aside>

        <main className="min-w-0 space-y-4">
          {!model && <div className="rounded-2xl border border-dashed p-10 text-center text-sm text-muted-foreground">Selecione ou carregue um modelo para começar.</div>}
          {model && version && !FINAL.includes(version.status) && (
            <div className="rounded-xl border p-4 space-y-2" data-testid="bim-processing">
              <div className="flex justify-between text-sm"><span>{model.name} · v{version.version} — {version.stage || "em fila de espera"}</span>
                <button type="button" className="text-xs text-muted-foreground hover:text-red-600" onClick={() => api.post(`/bim/models/${model.model_id}/versions/${version.version}/cancel`).then(() => openModel(model.model_id, version.version))}>Anular</button></div>
              <div className="h-2 rounded-full bg-accent overflow-hidden"><div className="h-full bg-primary transition-all" style={{ width: `${Math.round((version.progress || 0) * 100)}%` }} /></div>
            </div>
          )}
          {model && version?.status === "failed" && (
            <div className="rounded-xl border border-red-300 bg-red-50 dark:bg-red-950/30 p-4 text-sm" data-testid="bim-failed">
              <p className="font-medium">O processamento falhou: {version.error}</p>
              <button type="button" className={`${BTN_GHOST} mt-2`} onClick={() => api.post(`/bim/models/${model.model_id}/versions/${version.version}/retry`).then(() => openModel(model.model_id, version.version)).catch((e) => toast.error(e?.response?.data?.detail || "Impossível"))}>Relançar</button>
            </div>
          )}
          {model && version?.status === "done" && (
            <>
              <div className="flex flex-wrap items-center gap-3">
                <h2 className="font-semibold text-lg">{model.name} <span className="text-sm text-muted-foreground font-normal">v{version.version} · {version.schema} · {version.stats?.elements} elementos</span></h2>
                {version.warnings?.length > 0 && <span className="text-xs rounded-full bg-amber-500/15 text-amber-700 px-2 py-0.5" title={version.warnings.join("\n")}>{version.warnings.length} aviso(s)</span>}
                {version.stats?.with_missing > 0 && <span className="text-xs rounded-full bg-red-500/15 text-red-700 px-2 py-0.5">{version.stats.with_missing} elemento(s) com dados em falta</span>}
              </div>
              <nav className="flex gap-1 border-b" role="tablist">
                {TABS.map(([k, label]) => (
                  <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
                          className={`px-3 py-2 text-sm -mb-px border-b-2 ${tab === k ? "border-primary font-medium" : "border-transparent text-muted-foreground"}`} data-testid={`bim-tab-${k}`}>{label}</button>
                ))}
              </nav>

              <div className={tab === "modelo" ? "grid xl:grid-cols-[1fr_340px] gap-4" : "hidden"}>
                <div className="space-y-3 min-w-0">
                  <div className="flex flex-wrap gap-2 text-xs">
                    {(version.storeys || []).map((s) => (
                      <button key={s.gid} type="button" onClick={() => toggleSet("storeys", s.gid)} className={`rounded-full border px-2.5 py-1 ${filters.storeys.has(s.gid) ? "bg-primary text-primary-foreground" : ""}`}>{s.name}</button>
                    ))}
                    <span className="w-px bg-border mx-1" />
                    {categoriesPresent.map(([k, n]) => (
                      <button key={k} type="button" onClick={() => toggleSet("categories", k)} className={`rounded-full border px-2.5 py-1 ${filters.categories.has(k) ? "bg-[#c4733f] text-white" : ""}`}>{cfg?.categories?.[k] || k} ({n})</button>
                    ))}
                  </div>
                  <BimViewer ref={viewerRef} modelId={model.model_id} version={version.version} chunks={version.chunks || 0}
                             meta={meta} filters={filters} selectedGid={selected} highlighted={highlighted}
                             onSelect={setSelected} measuring={measuring} onMeasure={setMeasure} />
                  {highlighted && (
                    <p className="text-xs">A destacar {highlighted.size} elemento(s) associados ao orçamento.{" "}
                      <button type="button" className="text-primary" onClick={() => { setHighlight(null); setFilters((f) => ({ ...f, isolated: new Set() })); }}>Limpar destaque</button></p>
                  )}
                  <div className="flex flex-wrap gap-2 items-center">
                    <button type="button" className={BTN_GHOST} onClick={() => viewerRef.current?.fit()}>Enquadrar</button>
                    <button type="button" className={BTN_GHOST} onClick={() => setFilters({ storeys: new Set(), categories: new Set(), hidden: new Set(), isolated: new Set() })}>Mostrar tudo</button>
                    <button type="button" className={`${BTN_GHOST} ${measuring ? "bg-[#c4733f] text-white" : ""}`} onClick={() => { setMeasuring(!measuring); setMeasure(null); }}>Medir distância</button>
                    {measure != null && <span className="text-sm font-medium" data-testid="bim-measure-value">≈ {formatQty(measure, "m")} <span className="text-xs text-muted-foreground">(medição visual, não verificada)</span></span>}
                  </div>
                </div>
                <div className="rounded-xl border bg-card max-h-[75vh] overflow-y-auto">
                  <ElementPanel base={base} gid={selected} profile={profile} canEdit={canEdit} onChanged={() => setRefreshKey((k) => k + 1)}
                                onHide={(g) => { toggleSet("hidden", g); setSelected(null); }}
                                onIsolate={(g) => setFilters((f) => ({ ...f, isolated: new Set([g]) }))} />
                </div>
              </div>
              {tab === "medicoes" && (
                <div className="grid xl:grid-cols-[1fr_340px] gap-4">
                  <MeasurementsTab base={base} version={version} categories={cfg?.categories} profile={profile} onSelect={setSelected} refreshKey={refreshKey} />
                  <div className="rounded-xl border bg-card max-h-[75vh] overflow-y-auto"><ElementPanel base={base} gid={selected} profile={profile} canEdit={canEdit} onChanged={() => setRefreshKey((k) => k + 1)} /></div>
                </div>
              )}
              {tab === "orcamento" && <BudgetTab base={base} canEdit={canEdit} profile={profile} refreshKey={refreshKey}
                                                onHighlight={(gids) => {
                                                  setHighlight(gids);
                                                  setFilters((f) => ({ ...f, isolated: new Set(gids) }));
                                                  setTab("modelo");
                                                  setTimeout(() => viewerRef.current?.fit(), 50);
                                                }} />}
              {tab === "versoes" && (
                <VersionsTab model={model} canEdit={canEdit} onOpenVersion={(v) => openModel(model.model_id, v)}
                             onUploadVersion={() => { newVersionFor.current = model.model_id; fileRef.current?.click(); }} />
              )}
            </>
          )}
        </main>
      </div>
    </div>
  );
}
