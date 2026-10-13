import { useEffect, useState } from "react";
import { MapPin, Layers, Check, Loader2, X, SlidersHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const IDF = ["75", "77", "78", "91", "92", "93", "94", "95"];
export const RadarZoneFilter = ({ zone, options, km, onRadius, onApply, busy }) => {
  const [mode, setMode] = useState(zone.mode);
  const [selected, setSelected] = useState(zone.departments);
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState(false);
  useEffect(() => { setMode(zone.mode); setSelected(zone.departments); }, [zone]);
  const toggle = (code) => setSelected((prev) => prev.includes(code) ? prev.filter((d) => d !== code) : [...prev, code]);
  const filtered = options.filter((d) => `${d.code} ${d.name}`.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().includes(query.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase()));
  const changed = mode !== zone.mode || [...selected].sort().join() !== [...zone.departments].sort().join();
  return <section className="border-y border-border py-4 my-5 space-y-3" data-testid="radar-zone-filter">
    <div role="radiogroup" aria-label="Zona de pesquisa" className="flex flex-wrap gap-2">
      {[["radius", "Rayon", MapPin], ["departments", "Departamentos", Layers]].map(([value, label, Icon]) => <button key={value} role="radio" aria-checked={mode === value}
        disabled={busy} onClick={() => { setMode(value); if (value === "departments") setEditing(true); }} data-testid={`radar-zone-${value}`} className={`inline-flex gap-2 items-center px-3 py-2 border rounded-md text-sm transition-colors ${mode === value ? "bg-primary text-white border-primary" : "border-border hover:border-primary"}`}><Icon className="h-4 w-4" />{label}</button>)}
      {mode === "departments" && <Button variant="ghost" size="sm" onClick={() => setEditing((v) => !v)} aria-expanded={editing} className="gap-1" data-testid="radar-departments-edit"><SlidersHorizontal className="h-4 w-4" />{editing ? "Reduzir" : "Alterar os distritos"}</Button>}
    </div>
    {mode === "radius" ? <div className="flex flex-wrap gap-2">
      {[10, 20, 30, 50, 100].map((r) => <button key={r} disabled={busy} onClick={() => onRadius(r)} data-testid={`radar-km-${r}`}
        className={`px-3 py-1 rounded-full text-xs font-bold border transition-colors ${km === r && zone.mode === "radius" ? "bg-primary text-white border-primary" : "border-border hover:border-primary"}`}>{r} km</button>)}
    </div> : <>
      {editing && <div className="flex flex-wrap gap-2 items-center">
        <Button variant="outline" size="sm" disabled={busy} onClick={() => setSelected((old) => [...new Set([...old, ...IDF])])} data-testid="radar-departments-idf">Île-de-France</Button>
        <Button variant="ghost" size="sm" disabled={busy} onClick={() => setSelected([])} data-testid="radar-departments-clear">Remover todos</Button>
        <span className="text-xs text-muted-foreground" data-testid="radar-departments-count">{selected.length} distrito(s)</span>
      </div>}
      {selected.length > 0 && <div className="flex flex-wrap gap-2" data-testid="radar-departments-selected">{selected.map((d) => <button key={d} disabled={busy} onClick={() => toggle(d)} aria-label={`Retirer ${d}`} title={options.find((o) => o.code === d)?.name}
        className="flex items-center gap-1 text-xs px-2 py-1 border border-primary rounded-md text-primary" data-testid={`radar-department-remove-${d}`}>{d}<X className="h-3 w-3" /></button>)}</div>}
      {editing && <><Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Pesquisar um código ou departamento" aria-label="Pesquisar um departamento" className="max-w-md" data-testid="radar-department-query" />
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2 max-h-44 overflow-y-auto border border-border rounded-md p-3" data-testid="radar-department-options">
        {filtered.map((d) => <label key={d.code} className="flex items-center gap-2 text-xs min-w-0 cursor-pointer">
          <input type="checkbox" checked={selected.includes(d.code)} disabled={busy} onChange={() => toggle(d.code)} data-testid={`radar-department-${d.code}`} className="shrink-0" />
          <span>{d.code} — {d.name}</span>
        </label>)}
        {!filtered.length && <p className="text-xs" data-testid="radar-department-no-match">Nenhum departamento correspondente.</p>}
      </div></>}
    </>}
    <div className="flex flex-wrap gap-3 items-center">
      <Button size="sm" disabled={busy || (mode === "departments" && !selected.length) || !changed} onClick={async () => { await onApply({ mode, departments: selected }); setEditing(false); }} className="gap-1" data-testid="radar-zone-apply">
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} Aplicar e guardar
      </Button>
      <p className="text-xs text-muted-foreground" data-testid="radar-zone-status">{changed ? "Seleção não aplicada" : zone.mode === "departments" ? `Distritos:${zone.departments.join(", ")}· sem limite de raio` : `Rayon actif : ${km} km`}</p>
    </div>
  </section>;
};