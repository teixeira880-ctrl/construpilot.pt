import { useState } from "react";
import { Check, Loader2, Pencil, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { contactError } from "./ContactEditor";

export const RadarQualification = ({ opp, options, onUpdated }) => {
  const [editing, setEditing] = useState(false);
  const [category, setCategory] = useState(opp.qualification?.category || opp.classification?.client_type || "inconnu");
  const [note, setNote] = useState(opp.qualification?.source_note || "");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const selectedLabel = options.find((item) => item.value === opp.classification?.client_type)?.label || "Não identificado";

  const save = async () => {
    if (!confirmed || note.trim().length < 3 || busy) return;
    setBusy(true); setError("");
    try {
      const { data } = await api.put(`/radar/opportunities/${opp.id}/qualification`, { category, source_note: note.trim(), confirmed: true });
      onUpdated(data); setEditing(false); setConfirmed(false);
    } catch (e) { setError(contactError(e)); } finally { setBusy(false); }
  };
  const remove = async () => {
    if (!window.confirm("Remover a sua qualificação? Os dados oficiais serão conservados.")) return;
    setBusy(true); setError("");
    try {
      const { data } = await api.delete(`/radar/opportunities/${opp.id}/qualification`);
      onUpdated(data); setEditing(false); setNote(""); setConfirmed(false); setCategory(data.classification?.client_type || "inconnu");
    } catch (e) { setError(contactError(e)); } finally { setBusy(false); }
  };

  return <section className="border-b border-border py-4 space-y-3" data-testid="radar-qualification">
    <div className="flex flex-wrap items-center gap-2 justify-between">
      <p className="text-sm" data-testid="radar-client-category">Contact : <strong>{selectedLabel}</strong></p>
      <Button size="sm" variant="outline" disabled={busy} data-testid="radar-qualification-edit" className="gap-1" onClick={() => { setEditing((value) => !value); setConfirmed(false); }}><Pencil className="h-3 w-3" />Qualifier</Button>
    </div>
    <p className="text-xs text-muted-foreground break-words" data-testid="radar-qualification-source">{opp.qualification ? `Confirmado por si ·${opp.qualification.source_note}` : opp.classification?.client_source === "sitadel" ? "Pessoa coletiva publicada nos dados oficiais. Atividade precisa não qualificada." : "Categoria não identificada nos dados públicos."}</p>
    {editing && <div className="space-y-3">
      <label className="grid gap-1 text-xs">Categoria
        <select value={category} disabled={busy} onChange={(e) => { setCategory(e.target.value); setConfirmed(false); }} data-testid="radar-qualification-category" className="w-full h-10 rounded-md border border-input bg-background px-2 text-sm">
          {options.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
        </select>
      </label>
      <label className="grid gap-1 text-xs">Origem da qualificação
        <Input value={note} disabled={busy} maxLength={240} onChange={(e) => { setNote(e.target.value); setConfirmed(false); }} placeholder="Ex.: conversa com o contacto, site profissional…" data-testid="radar-qualification-note" />
      </label>
      <label className="flex items-start gap-2 text-xs">
        <input type="checkbox" checked={confirmed} disabled={busy} onChange={(e) => setConfirmed(e.target.checked)} data-testid="radar-qualification-confirm" className="shrink-0 mt-0.5" />Confirmo esta categoria a partir da fonte indicada. Qualificação privada à minha conta.
      </label>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" disabled={busy || !confirmed || note.trim().length < 3} data-testid="radar-qualification-save" onClick={save} className="gap-1">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}Guardar</Button>
        {opp.qualification && <Button size="sm" variant="outline" disabled={busy} data-testid="radar-qualification-remove" onClick={remove} className="gap-1"><Trash2 className="h-4 w-4" />Retirer</Button>}
      </div>
    </div>}
    {error && <p role="alert" className="text-xs text-red-700" data-testid="radar-qualification-error">{error}</p>}
  </section>;
};