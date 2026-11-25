import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Building2, Cog, HardHat, CalendarRange, ShieldCheck, Layers, FileText, Search, ChevronDown, ChevronRight, Home, Menu } from "lucide-react";
import { api } from "@/lib/api";
import { ModuleIcon } from "./icons";

export const AREA_ICONS = { arquitetura: Building2, engenharia: Cog, preparacao: HardHat, gestao: CalendarRange, entrega: ShieldCheck };

export const STATUS_TEXT = {
  validado: "Validado", rascunho: "Rascunho", pendente: "Pendente", nao_aplicavel: "Não aplicável", rejeitado: "Rejeitado",
  por_fazer: "Por fazer", em_curso: "Em curso", bloqueado: "Bloqueado", concluido: "Concluído",
  por_iniciar: "Por iniciar", em_preparacao: "Em preparação", a_validar: "A validar",
  por_confirmar: "Por confirmar", confirmado: "Confirmado", corrigido: "Corrigido",
};

export const Pill = ({ s, children }) => <span className={`dob-pill dob-pill-${s}`}>{children || STATUS_TEXT[s] || s}</span>;

export const errMsg = (e, fallback = "Ocorreu um erro. Tente novamente.") => {
  const d = e?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (d?.message) return d.message;
  return fallback;
};

/** Contexto partilhado: obra, fase e local ficam na URL e são preservados ao navegar e ao abrir ferramentas. */
export function useDossierContext() {
  const { chantierId } = useParams();
  const [params, setParams] = useSearchParams();
  const fase = params.get("fase") || "";
  const local = params.get("local") || "";
  const qs = useCallback((extra = {}) => {
    const p = new URLSearchParams();
    const merged = { fase, local, ...extra };
    Object.entries(merged).forEach(([k, v]) => { if (v) p.set(k, v); });
    const s = p.toString();
    return s ? `?${s}` : "";
  }, [fase, local]);
  const setCtx = (patch) => {
    const next = new URLSearchParams(params);
    Object.entries(patch).forEach(([k, v]) => { if (v) next.set(k, v); else next.delete(k); });
    setParams(next, { replace: true });
  };
  const base = `/chantiers/${chantierId}/dossier`;
  /** Ligação para uma ferramenta existente, com obra/especialidade/fase/local. */
  const tool = (path, especialidade) => {
    const p = new URLSearchParams({ chantier: chantierId });
    if (especialidade) p.set("especialidade", especialidade);
    if (fase) p.set("fase", fase);
    if (local) p.set("local", local);
    return `${path}?${p.toString()}`;
  };
  return { chantierId, fase, local, qs, setCtx, base, tool };
}

export function useOverview(chantierId) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const load = useCallback(() => api.get(`/dossier-obra/${chantierId}`).then(({ data }) => { setData(data); setError(null); })
    .catch((e) => setError(e?.response?.status === 404 ? "notfound" : errMsg(e))), [chantierId]);
  useEffect(() => { load(); }, [load]);
  return { data, error, reload: load };
}

let catalogCache = null;
export function useCatalog() {
  const [cat, setCat] = useState(catalogCache);
  useEffect(() => {
    if (catalogCache) return;
    api.get("/dossier-obra/catalogo").then(({ data }) => { catalogCache = data; setCat(data); }).catch(() => {});
  }, []);
  return cat;
}

export function useMode() {
  const [mode, setMode] = useState("guiado");
  useEffect(() => { api.get("/dossier-obra/preferencias").then(({ data }) => setMode(data.mode)).catch(() => {}); }, []);
  const change = async (m) => { setMode(m); try { await api.put("/dossier-obra/preferencias", { mode: m }); } catch { /* o modo é só apresentação */ } };
  return [mode, change];
}

export function ModeToggle({ mode, onChange }) {
  return (
    <div className="dob-seg" role="group" aria-label="Modo de utilização" data-testid="dob-mode">
      <button type="button" aria-pressed={mode === "guiado"} onClick={() => onChange("guiado")} data-testid="dob-mode-guiado">Guiado</button>
      <button type="button" aria-pressed={mode === "tecnico"} onClick={() => onChange("tecnico")} data-testid="dob-mode-tecnico">Técnico</button>
    </div>
  );
}

export function PhaseLocalSelectors({ phases, locations, fase, local, onChange, testPrefix = "dob" }) {
  return (
    <>
      <label className="dob-select"><HardHat size={18} aria-hidden="true" />
        <span className="sr-only">Fase</span>
        <select value={fase} onChange={(e) => onChange({ fase: e.target.value })} data-testid={`${testPrefix}-fase`} aria-label="Fase">
          <option value="">Fase: todas</option>
          {phases.map((p) => <option key={p.key} value={p.key}>Fase: {p.label}</option>)}
        </select>
      </label>
      <label className="dob-select"><Home size={18} aria-hidden="true" />
        <span className="sr-only">Local</span>
        <select value={local} onChange={(e) => onChange({ local: e.target.value })} data-testid={`${testPrefix}-local`} aria-label="Local">
          <option value="">Local: toda a obra</option>
          {locations.map((l) => <option key={l.location_id} value={l.location_id}>Local: {l.path || l.name}</option>)}
        </select>
      </label>
    </>
  );
}

export function Breadcrumbs({ items }) {
  return (
    <nav aria-label="Caminho" className="dob-crumbs" data-testid="dob-breadcrumbs">
      <Link to="/chantiers" aria-label="Obras"><Home size={15} /></Link>
      {items.map((it, i) => (
        <span key={i} className="inline-flex items-center gap-1.5">
          <ChevronRight size={13} aria-hidden="true" />
          {it.to && i < items.length - 1 ? <Link to={it.to}>{it.label}</Link> : <span aria-current={i === items.length - 1 ? "page" : undefined}>{it.label}</span>}
        </span>
      ))}
    </nav>
  );
}

/** Navegação consistente do dossier (uma só barra, sem duplicar o menu global). */
export function DossierNav({ active }) {
  const { chantierId, base, qs, tool } = useDossierContext();
  const items = [
    ["overview", "Visão geral", `${base}${qs()}`],
    ["especialidades", "Especialidades", `${base}${qs({ vista: "especialidades" })}`],
    ["planeamento", "Planeamento", tool("/planning")],
    ["compras", "Materiais e compras", tool("/appro")],
    ["custos", "Custos e autos", `/chantiers/${chantierId}?tab=budget`],
    ["documentos", "Documentos", `/chantiers/${chantierId}?tab=documents`],
    ["final", "Documento final", `${base}/compilar${qs()}`],
  ];
  return (
    <nav className="dob-nav" aria-label="Secções do dossier" data-testid="dob-nav">
      {items.map(([k, l, to]) => <Link key={k} to={to} aria-current={active === k ? "page" : undefined} data-testid={`dob-nav-${k}`}>{l}</Link>)}
    </nav>
  );
}

/** Árvore expansível de áreas e especialidades ativas (lateral no computador, recolhível no telemóvel). */
export function DossierTree({ overview, activeKey }) {
  const { base, qs } = useDossierContext();
  const [open, setOpen] = useState({});
  const [mobileOpen, setMobileOpen] = useState(false);
  const [q, setQ] = useState("");
  const activeArea = useMemo(() => overview?.areas.find((a) => a.specialties.some((s) => s.key === activeKey))?.key, [overview, activeKey]);
  if (!overview) return null;
  const needle = q.trim().toLowerCase();
  const norm = (t) => (t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  return (
    <aside className="dob-tree" data-open={mobileOpen} aria-label="Áreas e especialidades" data-testid="dob-tree">
      <button type="button" className="dob-tree-toggle dob-tree-final" style={{ marginTop: 0 }} aria-expanded={mobileOpen} onClick={() => setMobileOpen(!mobileOpen)} data-testid="dob-tree-toggle">
        <Menu size={18} /> Especialidades {mobileOpen ? <ChevronDown size={16} className="ms-auto" /> : <ChevronRight size={16} className="ms-auto" />}
      </button>
      <div className="dob-tree-body">
        <p className="dob-tree-title">Especialidades</p>
        <label className="dob-tree-search"><Search size={14} aria-hidden="true" /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Procurar (ex.: capoto, tomadas)" aria-label="Procurar especialidade" /></label>
        {overview.areas.map((a) => {
          const list = needle ? a.specialties.filter((s) => norm(`${s.label} ${s.terms || ""} ${s.description || ""}`).includes(norm(needle))) : a.specialties;
          const isOpen = needle ? list.length > 0 : (open[a.key] ?? (a.key === activeArea || (!activeKey && a.specialties.length > 0)));
          return (
            <div key={a.key} className="dob-tree-area">
              <button type="button" aria-expanded={isOpen} onClick={() => setOpen({ ...open, [a.key]: !isOpen })} data-testid={`dob-tree-area-${a.key}`}>
                <ModuleIcon area={a.key} size={14} tile={26} /><span className="flex-1">{a.label.split(" e ")[0]}</span>
                {isOpen ? <ChevronDown size={16} aria-hidden="true" /> : <ChevronRight size={16} aria-hidden="true" />}
              </button>
              {isOpen && (
                <div className="dob-tree-list">
                  {list.length === 0 && <p className="dob-tree-empty">{needle ? "Sem resultados" : "Nenhuma ativa"}</p>}
                  {list.map((s) => (
                    <Link key={s.key} to={`${base}/especialidade/${s.key}${qs()}`} aria-current={s.key === activeKey ? "page" : undefined} data-testid={`dob-tree-${s.key}`}>
                      <ModuleIcon k={s.key} area={s.area} size={12} tile={22} copper={s.key === activeKey} /><span className="truncate">{s.label}</span>
                      {s.counts?.pending > 0 && <span className="dob-tree-count" aria-label={`${s.counts.pending} pendentes`}>{s.counts.pending}</span>}
                    </Link>
                  ))}
                </div>
              )}
            </div>
          );
        })}
        <Link to={`${base}/compilar${qs()}`} className="dob-tree-final" data-testid="dob-tree-final"><FileText size={18} /> Documento final</Link>
      </div>
    </aside>
  );
}

export function Loading({ children = "A carregar…" }) {
  return <div className="dob-card dob-card-pad text-sm text-muted-foreground" role="status" aria-live="polite">{children}</div>;
}
export function ErrorBox({ children, onRetry }) {
  return <div className="dob-card dob-card-pad text-sm" role="alert">{children} {onRetry && <button type="button" className="text-primary underline" onClick={onRetry}>Tentar novamente</button>}</div>;
}

/** Caminho legível de cada local (Edifício · Piso · Zona). */
export const withPaths = (locs = []) => {
  const by = Object.fromEntries(locs.map((l) => [l.location_id, l]));
  return locs.map((l) => { const p = []; let c = l; let g = 0; while (c && g < 6) { p.unshift(c.name); c = by[c.parent_id]; g++; } return { ...l, path: p.join(" · ") }; });
};
