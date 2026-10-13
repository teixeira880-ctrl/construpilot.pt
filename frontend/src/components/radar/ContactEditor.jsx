import { useState } from "react";
import { Save, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const FIELDS = [["nom", "Nom / raison sociale"], ["societe", "Sociedade"], ["adresse1", "Adresse postale"],
  ["adresse2", "Complemento"], ["cp", "Code postal"], ["ville", "Ville"], ["siren", "SIREN"],
  ["siret", "SIRET"], ["email", "E-mail"], ["telephone", "Telefone"]];
export const contactError = (e) => typeof e?.response?.data?.detail === "string" ? e.response.data.detail : "Verifique os contactos e a sua origem.";

export const ContactEditor = ({ opp, onSaved, onCancel }) => {
  const [form, setForm] = useState(() => Object.fromEntries(FIELDS.map(([key]) => [key, String(opp.promoteur?.[key] || "")])));
  const [note, setNote] = useState(opp.contact_provenance?.kind === "manual" ? opp.contact_provenance.label : "");
  const [url, setUrl] = useState(opp.contact_provenance?.source_url || "");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const save = async (e) => {
    e.preventDefault(); setBusy(true); setError("");
    try {
      const { data } = await api.put(`/radar/opportunities/${opp.id}/contact`, {
        contact: form, source_note: note.trim(), source_url: url.trim() || null, confirmed,
      });
      onSaved(data);
    } catch (e) { setError(contactError(e)); }
    finally { setBusy(false); }
  };
  return <form onSubmit={save} className="mt-4 space-y-3" data-testid="radar-contact-form">
    <div className="grid grid-cols-2 gap-3">
      {FIELDS.map(([key, label]) => <label key={key} className={`text-xs min-w-0 ${["nom", "societe", "adresse1", "adresse2", "email"].includes(key) ? "col-span-2" : ""}`}>
        {label}<Input className="mt-1 min-w-0" data-testid={`radar-contact-${key}`} value={form[key]}
          type={key === "email" ? "email" : "text"} maxLength={key === "siren" ? 9 : key === "siret" ? 14 : 160}
          onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
      </label>)}
    </div>
    <label className="block text-xs">Origem dos dados de contacto *
      <Input className="mt-1" value={note} onChange={(e) => setNote(e.target.value)} required minLength={3} maxLength={240}
        placeholder="Ex.: contactos transmitidos pelo cliente" data-testid="radar-contact-source-note" />
    </label>
    <label className="block text-xs">Lien source (facultatif)
      <Input className="mt-1" type="url" value={url} onChange={(e) => setUrl(e.target.value)} data-testid="radar-contact-source-url" />
    </label>
    <label className="flex items-start gap-2 text-xs">
      <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} required className="mt-0.5 shrink-0" data-testid="radar-contact-consent" />
      Confirmo dispor legitimamente destes dados de contacto para este projeto.
    </label>
    {error && <p role="alert" className="text-xs text-red-600" data-testid="radar-contact-error">{error}</p>}
    <div className="flex flex-wrap gap-2">
      <Button type="submit" size="sm" disabled={!confirmed || note.trim().length < 3 || busy} className="gap-1" data-testid="radar-contact-save">
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Guardar
      </Button>
      <Button type="button" variant="ghost" size="sm" disabled={busy} onClick={onCancel} data-testid="radar-contact-cancel">Cancelar</Button>
    </div>
  </form>;
};