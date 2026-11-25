import { Fragment } from "react";
import { Link } from "react-router-dom";
import { Home, ChevronRight, ChevronDown, MapPin, HardHat } from "lucide-react";
import { ModuleIcon } from "./icons";

export function Crumbs({ items }) {
  return (
    <nav aria-label="Caminho" className="dob-crumbs" data-testid="dob-breadcrumbs">
      <Link to="/chantiers" aria-label="Obras"><Home size={17} /></Link>
      <ChevronRight size={14} aria-hidden="true" />
      {items.map((it, i) => (
        <Fragment key={i}>
          {i > 0 && <span aria-hidden="true">/</span>}
          {it.to ? <Link to={it.to}>{it.label}</Link> : <span aria-current="page">{it.label}</span>}
        </Fragment>
      ))}
    </nav>
  );
}

export function DossierHeader({ icon: Icon, moduleKey, moduleArea, title, subtitle, extra, demo, action, testId, side }) {
  return (
    <header className="dob-header">
      <div className="dob-title">
        {moduleKey ? <ModuleIcon k={moduleKey} area={moduleArea} size={32} tile={66} radius={18} className="dob-title-logo" />
          : <span className="dob-title-icon"><Icon size={34} strokeWidth={1.7} aria-hidden="true" /></span>}
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3"><h1 data-testid={testId}>{title}</h1>{demo && <span className="dob-demo">Exemplo demonstrativo</span>}</div>
          {subtitle && <p className="dob-sub">{subtitle}</p>}
          {extra}
        </div>
      </div>
      {side}
      {action}
    </header>
  );
}

/** Seletores «Fase: …» e «Local: …» (o local mostra o nome curto; o caminho completo fica no título). */
export function ContextSelects({ cat, locations, fase, local, onChange, testPrefix = "dob" }) {
  const phase = cat.phases.find((p) => p.key === fase);
  const loc = locations.find((l) => l.location_id === local);
  const locName = loc ? (loc.kind === "zona" && loc.path.split(" · ").length > 2 ? loc.path.split(" · ").slice(1).join(" · ") : loc.name) : null;
  return (
    <div className="dob-selects">
      <label className="dob-pick" title={phase?.label || "Todas as fases"}>
        <HardHat size={20} aria-hidden="true" /><span>Fase: {phase?.label || "Todas"}</span><ChevronDown size={18} aria-hidden="true" />
        <select value={fase} onChange={(e) => onChange({ fase: e.target.value })} data-testid={`${testPrefix}-fase`} aria-label="Fase">
          <option value="">Todas as fases</option>{cat.phases.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
        </select>
      </label>
      <label className="dob-pick dob-pick-wide" title={loc?.path || "Toda a obra"}>
        <MapPin size={20} aria-hidden="true" /><span>Local: {locName || "Toda a obra"}</span><ChevronDown size={18} aria-hidden="true" />
        <select value={local} onChange={(e) => onChange({ local: e.target.value })} data-testid={`${testPrefix}-local`} aria-label="Local">
          <option value="">Toda a obra</option>{locations.map((l) => <option key={l.location_id} value={l.location_id}>{l.path || l.name}</option>)}
        </select>
      </label>
    </div>
  );
}

const FMT = { pdf: ["PDF", "#d92d20"], docx: ["Word", "#1d64d8"], xlsx: ["Excel", "#15803d"], zip: ["ZIP", "#c2620a"] };
export function FormatIcon({ f, size = 26 }) {
  const [l, c] = FMT[f];
  return (
    <svg width={size} height={size * 1.15} viewBox="0 0 24 28" aria-hidden="true">
      <path d="M4 1h11l6 6v18a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V3a2 2 0 0 1 2-2z" fill="#fff" stroke={c} strokeWidth="1.6" />
      <path d="M15 1v6h6" fill="none" stroke={c} strokeWidth="1.6" />
      <rect x="4.5" y="14" width="15" height="8" rx="1.5" fill={c} />
      <text x="12" y="20.3" textAnchor="middle" fontSize="5.6" fontWeight="700" fill="#fff" fontFamily="Arial">{l === "Word" ? "W" : l === "Excel" ? "X" : l}</text>
    </svg>
  );
}
export function FormatChip({ f }) {
  return <span className="dob-fchip"><FormatIcon f={f} size={14} /> {FMT[f][0]}</span>;
}
