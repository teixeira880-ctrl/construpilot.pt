import { useState } from "react";
import { Search, ExternalLink, Loader2, Check } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { contactError } from "./ContactEditor";

export const CompanyContactSearch = ({ opp, onSaved }) => {
  const [query, setQuery] = useState(opp.promoteur?.siren || opp.promoteur?.nom || "");
  const [result, setResult] = useState(null);
  const [selected, setSelected] = useState(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const search = async (e) => {
    e.preventDefault(); setBusy(true); setError(""); setSelected(null); setResult(null); setConfirmed(false);
    try { const { data } = await api.post(`/radar/opportunities/${opp.id}/contact/search`, { query: query.trim() }); setResult(data); }
    catch (e) { setError(contactError(e)); } finally { setBusy(false); }
  };
  const save = async () => {
    setBusy(true); setError("");
    try {
      const { data } = await api.post(`/radar/opportunities/${opp.id}/contact/confirm`, { search_id: result.search_id, siren: selected.siren, confirmed });
      onSaved(data);
    } catch (e) { setError(contactError(e)); } finally { setBusy(false); }
  };
  return <div className="mt-4 space-y-3" data-testid="radar-company-search">
    <form onSubmit={search} className="space-y-2">
      <label className="text-xs block">Denominação social ou SIREN conhecido
        <Input className="mt-1" value={query} onChange={(e) => setQuery(e.target.value)} minLength={2} maxLength={120} required data-testid="radar-company-query" />
      </label>
      <Button size="sm" type="submit" disabled={busy || query.trim().length < 2} className="gap-1" data-testid="radar-company-search-btn">
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />} Pesquisar no diretório
      </Button>
    </form>
    <p className="text-xs text-muted-foreground" data-testid="radar-company-disclaimer">Apenas sedes de empresas com dados públicos. A morada da sede não comprova a ligação a esta licença.</p>
    {error && <p role="alert" className="text-xs text-red-600" data-testid="radar-company-error">{error}</p>}
    {result && !result.candidates.length && <p className="text-xs" data-testid="radar-company-empty">Nenhuma empresa ativa com dados públicos encontrada. Verifique a denominação social ou indique um contacto conhecido.</p>}
    {result?.candidates.map((c) => <div key={c.siren} className="border-t border-border py-3 space-y-1 break-words" data-testid={`radar-company-candidate-${c.siren}`}>
      <p className="font-semibold text-sm" data-testid={`radar-company-name-${c.siren}`}>{c.nom}</p>
      <p className="text-xs" data-testid={`radar-company-address-${c.siren}`}>{c.adresse_complete}</p>
      <p className="text-xs text-muted-foreground" data-testid={`radar-company-siren-${c.siren}`}>NIPC {c.siren}</p>
      <a href={c.source_url} target="_blank" rel="noopener noreferrer" className="text-xs text-primary inline-flex gap-1 underline" data-testid={`radar-company-source-${c.siren}`}>
        Diretório oficial <ExternalLink className="h-3 w-3" />
      </a>
      <div><Button size="sm" variant={selected?.siren === c.siren ? "default" : "outline"} disabled={busy}
        onClick={() => { setSelected(c); setConfirmed(false); }} className="gap-1" data-testid={`radar-company-select-${c.siren}`}>
        <Check className="h-3.5 w-3.5" /> Selecionar esta empresa
      </Button></div>
    </div>)}
    {selected && <div className="border-t border-border pt-3 space-y-3" data-testid="radar-company-confirmation">
      <p className="text-sm font-semibold break-words" data-testid="radar-company-selected-name">{selected.nom}</p>
      <label className="flex items-start gap-2 text-xs"><input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} className="mt-0.5 shrink-0" data-testid="radar-company-confirm-check" />Confirmo que esta empresa corresponde ao dono de obra desta licença.</label>
      <Button size="sm" onClick={save} disabled={!confirmed || busy} className="whitespace-normal h-auto min-h-9" data-testid="radar-company-confirm-save">Confirmar e guardar</Button>
    </div>}
  </div>;
};