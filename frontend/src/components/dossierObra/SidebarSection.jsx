import { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, ChevronUp, FileText } from "lucide-react";
import { useDossierSidebar } from "./sidebarStore";
import { AREA_ICONS, AREA_SHORT, specIcon } from "./icons";

/** «ESPECIALIDADES» no menu lateral verde: só aparece com um dossier de obra aberto. */
export function DossierSidebarSection() {
  const d = useDossierSidebar();
  const [open, setOpen] = useState({});
  if (!d) return null;
  const { overview, activeKey, base, qs } = d;
  const activeArea = overview.areas.find((a) => a.specialties.some((s) => s.key === activeKey))?.key;
  return (
    <div className="workspace-nav-group cp-spec-tree" data-testid="sidebar-specialties">
      <p>Especialidades</p>
      {overview.areas.map((a) => {
        const Icon = AREA_ICONS[a.key];
        const has = a.specialties.length > 0;
        const isOpen = open[a.key] ?? (a.key === activeArea || (!activeKey && has && a.key === "arquitetura"));
        return (
          <div key={a.key}>
            <button type="button" className="cp-spec-area" aria-expanded={isOpen} onClick={() => setOpen({ ...open, [a.key]: !isOpen })} data-testid={`sidebar-area-${a.key}`}>
              <Icon size={19} aria-hidden="true" /><span>{AREA_SHORT[a.key]}</span>
              {isOpen ? <ChevronUp size={16} className="cp-chev" aria-hidden="true" /> : <ChevronDown size={16} className="cp-chev" aria-hidden="true" />}
            </button>
            {isOpen && (
              <div className="cp-spec-list">
                {!has && <Link to={`${base}${qs({ vista: "especialidades" })}`} className="cp-spec-link"><span>Ativar especialidades…</span></Link>}
                {a.specialties.map((s) => {
                  const SIcon = specIcon(s.key);
                  return (
                    <Link key={s.key} to={`${base}/especialidade/${s.key}${qs()}`} className="cp-spec-link" aria-current={s.key === activeKey ? "page" : undefined} data-testid={`sidebar-spec-${s.key}`} title={s.label}>
                      <SIcon size={16} aria-hidden="true" /><span>{s.short || s.label}</span>
                      {s.counts?.pending > 0 && <span className="cp-spec-count" aria-label={`${s.counts.pending} pendentes`}>{s.counts.pending}</span>}
                    </Link>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function DossierFinalLink() {
  const d = useDossierSidebar();
  if (!d) return null;
  return <Link to={`${d.base}/compilar${d.qs()}`} className="cp-doc-final" aria-current={d.compile ? "page" : undefined} data-testid="sidebar-documento-final"><FileText size={20} aria-hidden="true" /> Documento final</Link>;
}
