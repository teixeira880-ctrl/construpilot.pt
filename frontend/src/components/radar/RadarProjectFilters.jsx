import { useEffect, useState } from "react";
import { Building2, Check, ChevronDown, Hammer, Loader2, RotateCcw, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

const GROUPS = [
  ["work_types", "Tipo de obras", Hammer],
  ["building_types", "Tipo de edifício", Building2],
  ["client_types", "Dono de obra / contacto", Users],
];
const EMPTY = { work_types: [], building_types: [], client_types: [] };
const signature = (value) => JSON.stringify(GROUPS.map(([key]) => [...(value?.[key] || [])].sort()));

export const RadarProjectFilters = ({ value, options, facets, busy, onApply, count }) => {
  const [draft, setDraft] = useState(value);
  useEffect(() => { setDraft(value); }, [value]);
  const toggle = (group, option) => setDraft((old) => ({ ...old,
    [group]: old[group].includes(option) ? old[group].filter((x) => x !== option) : [...old[group], option] }));
  const changed = signature(draft) !== signature(value);
  const anySelected = GROUPS.some(([key]) => value[key].length || draft[key].length);

  return <section className="border-b border-border pb-5 mb-5 space-y-3" data-testid="radar-project-filters">
    <div className="flex flex-wrap gap-2">
      {GROUPS.map(([group, label, Icon]) => <Popover key={group}>
        <PopoverTrigger asChild>
          <Button variant="outline" disabled={busy} className="gap-2 h-auto min-h-10 py-2 max-w-full whitespace-normal" data-testid={`radar-filter-${group.replaceAll("_", "-")}-open`}>
            <Icon className="h-4 w-4 shrink-0" /><span className="text-left">{label}{draft[group].length ? ` (${draft[group].length})` : ""}</span><ChevronDown className="h-3 w-3 shrink-0" />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-80 max-w-[calc(100vw-2rem)] p-3" data-testid={`radar-filter-${group.replaceAll("_", "-")}-options`}>
          <fieldset className="grid gap-1">
            <legend className="font-semibold text-sm mb-2">{label}</legend>
            {(options[group] || []).map((option) => {
              const total = facets?.[group]?.find((item) => item.value === option.value)?.count;
              return <label key={option.value} className="flex items-center gap-3 text-sm py-2 px-1 cursor-pointer hover:bg-secondary/50 rounded-md transition-colors">
                <input type="checkbox" checked={draft[group].includes(option.value)} disabled={busy} onChange={() => toggle(group, option.value)}
                  data-testid={`radar-filter-${group.replaceAll("_", "-")}-${option.value}`} className="h-4 w-4 shrink-0 accent-primary" />
                <span className="flex-1 min-w-0">{option.label}</span>
                {typeof total === "number" && <span className="text-xs tabular-nums text-muted-foreground" data-testid={`radar-filter-count-${group.replaceAll("_", "-")}-${option.value}`}>{total}</span>}
              </label>;
            })}
          </fieldset>
        </PopoverContent>
      </Popover>)}
      <Button size="sm" className="h-10 gap-2" disabled={busy || !changed} onClick={() => onApply(draft)} data-testid="radar-filters-apply">
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}Aplicar e guardar
      </Button>
      <Button size="sm" variant="ghost" className="h-10 gap-2" disabled={busy || !anySelected} onClick={() => { setDraft(EMPTY); onApply(EMPTY); }} data-testid="radar-filters-reset"><RotateCcw className="h-4 w-4" />Reiniciar</Button>
    </div>
    <p role="status" className="text-xs text-muted-foreground" data-testid="radar-filters-status">{changed ? "Seleção não aplicada" : typeof count === "number" ? `${count} permis correspondant${count > 1 ? "s" : ""}` : "A carregar as licenças…"}</p>
  </section>;
};