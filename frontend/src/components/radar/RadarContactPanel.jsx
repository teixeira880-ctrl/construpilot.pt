import { useState } from "react";
import { Pencil, Search, Trash2, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { ContactEditor, contactError } from "./ContactEditor";
import { CompanyContactSearch } from "./CompanyContactSearch";

export const RadarContactPanel = ({ opp, onUpdated }) => {
  const [mode, setMode] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const pr = opp.promoteur;
  const provenance = opp.contact_provenance;
  const business = ["ENTREPRISE", "PROMOTEUR", "SCI", "BAILLEUR", "COLLECTIVITE"].includes(opp.mo);
  const saved = (data) => { onUpdated(data); setMode(null); toast.success("Dados de contacto guardados na sua conta"); };
  const remove = async () => {
    if (!window.confirm("Remover os seus contactos guardados? Os dados do ficheiro importado serão conservados.")) return;
    setDeleting(true);
    try { const { data } = await api.delete(`/radar/opportunities/${opp.id}/contact`); onUpdated(data); setMode(null); }
    catch (e) { toast.error(contactError(e)); } finally { setDeleting(false); }
  };
  return <section className="border-y border-border py-4 mt-4 space-y-2 min-w-0" data-testid="radar-promoteur">
    <h3 className="text-xs uppercase text-muted-foreground">Contacto do dono de obra</h3>
    {opp.is_demo ? <p className="text-sm text-amber-700" data-testid="radar-contact-demo">Exemplo fictício: nenhum dono de obra real está associado a esta ficha. Importe licenças para prospetar.</p> : <>
      {pr && Object.values(pr).some(Boolean) ? <>
        <p className="font-semibold text-sm break-words" data-testid="radar-promoteur-nom">{pr.nom || "Nome não comunicado"}</p>
        <p className="text-sm break-words" data-testid="radar-promoteur-adresse">{[pr.adresse1, pr.adresse2, [pr.cp, pr.ville].filter(Boolean).join(" ")].filter(Boolean).join(", ") || "Morada não comunicada"}</p>
        {pr.siren && <p className="text-xs" data-testid="radar-promoteur-siren">SIREN {pr.siren}</p>}
        {(pr.email || pr.telephone) && <p className="text-xs break-words" data-testid="radar-promoteur-channels">{[pr.email, pr.telephone].filter(Boolean).join(" · ")}</p>}
        <p className="text-xs text-muted-foreground break-words" data-testid="radar-contact-provenance">{provenance?.label || (opp.source?.kind === "sitadel_official" ? "Requerente pessoa coletiva publicado pelo SDES · morada postal por completar" : "Dados do ficheiro importado · não verificados")}</p>
        {provenance?.source_url && /^https?:\/\//.test(provenance.source_url) && <a href={provenance.source_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs text-primary underline" data-testid="radar-contact-source-link">Consultar a fonte <ExternalLink className="h-3 w-3" /></a>}
        {provenance?.confirmed_at && <p className="text-xs text-muted-foreground" data-testid="radar-contact-confirmed-at">Confirmado por si em {new Date(provenance.confirmed_at).toLocaleDateString("fr-FR")} · privado à sua conta</p>}
      </> : <p className="text-sm text-amber-700" data-testid="radar-promoteur-absent">{business ? "Empresa não identificada no ficheiro importado. Indique a denominação social ou um SIREN conhecido." : "Identidade do requerente não comunicada. Nenhum nome nem morada pessoal será deduzido do terreno."}</p>}
      {opp.coordonnees_status !== "complet" && <p className="text-xs text-amber-700" data-testid="radar-contact-incomplete">Morada postal incompleta · completar antes do envio.</p>}
      {opp.coordonnees_status !== "complet" && opp.adresse && opp.cp && opp.commune && <p className="text-xs" data-testid="radar-terrain-fallback">Na ausência da morada do contacto, a carta será preparada para a morada do terreno, à atenção do dono de obra.</p>}
      <div className="flex flex-wrap gap-2 pt-1">
        <Button variant="outline" size="sm" className="gap-1" onClick={() => setMode(mode === "manual" ? null : "manual")} data-testid="radar-contact-edit"><Pencil className="h-3.5 w-3.5" />{pr ? "Completar / editar" : "Adicionar um contacto"}</Button>
        {business && <Button variant="outline" size="sm" className="gap-1" onClick={() => setMode(mode === "search" ? null : "search")} data-testid="radar-contact-search-toggle"><Search className="h-3.5 w-3.5" />Annuaire entreprises</Button>}
        {provenance && <Button variant="ghost" size="sm" disabled={deleting} onClick={remove} title="Remover os meus dados de contacto" aria-label="Remover os meus dados de contacto" data-testid="radar-contact-delete"><Trash2 className="h-4 w-4" /></Button>}
      </div>
      {mode === "manual" && <ContactEditor opp={opp} onSaved={saved} onCancel={() => setMode(null)} />}
      {mode === "search" && <CompanyContactSearch opp={opp} onSaved={saved} />}
    </>}
  </section>;
};