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
  const saved = (data) => { onUpdated(data); setMode(null); toast.success("Coordonnées enregistrées dans votre compte"); };
  const remove = async () => {
    if (!window.confirm("Retirer vos coordonnées enregistrées ? Les données du fichier importé seront conservées.")) return;
    setDeleting(true);
    try { const { data } = await api.delete(`/radar/opportunities/${opp.id}/contact`); onUpdated(data); setMode(null); }
    catch (e) { toast.error(contactError(e)); } finally { setDeleting(false); }
  };
  return <section className="border-y border-border py-4 mt-4 space-y-2 min-w-0" data-testid="radar-promoteur">
    <h3 className="text-xs uppercase text-muted-foreground">Contact du maître d'ouvrage</h3>
    {opp.is_demo ? <p className="text-sm text-amber-700" data-testid="radar-contact-demo">Exemple fictif : aucun maître d'ouvrage réel n'est associé à cette fiche. Importez des permis pour prospecter.</p> : <>
      {pr && Object.values(pr).some(Boolean) ? <>
        <p className="font-semibold text-sm break-words" data-testid="radar-promoteur-nom">{pr.nom || "Nom non communiqué"}</p>
        <p className="text-sm break-words" data-testid="radar-promoteur-adresse">{[pr.adresse1, pr.adresse2, [pr.cp, pr.ville].filter(Boolean).join(" ")].filter(Boolean).join(", ") || "Adresse non communiquée"}</p>
        {pr.siren && <p className="text-xs" data-testid="radar-promoteur-siren">SIREN {pr.siren}</p>}
        {(pr.email || pr.telephone) && <p className="text-xs break-words" data-testid="radar-promoteur-channels">{[pr.email, pr.telephone].filter(Boolean).join(" · ")}</p>}
        <p className="text-xs text-muted-foreground break-words" data-testid="radar-contact-provenance">{provenance?.label || (opp.source?.kind === "sitadel_official" ? "Demandeur personne morale publié par le SDES · adresse postale à compléter" : "Coordonnées du fichier importé · non vérifiées")}</p>
        {provenance?.source_url && /^https?:\/\//.test(provenance.source_url) && <a href={provenance.source_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs text-primary underline" data-testid="radar-contact-source-link">Consulter la source <ExternalLink className="h-3 w-3" /></a>}
        {provenance?.confirmed_at && <p className="text-xs text-muted-foreground" data-testid="radar-contact-confirmed-at">Confirmé par vous le {new Date(provenance.confirmed_at).toLocaleDateString("fr-FR")} · privé à votre compte</p>}
      </> : <p className="text-sm text-amber-700" data-testid="radar-promoteur-absent">{business ? "Entreprise non identifiée dans le fichier importé. Renseignez une raison sociale ou un SIREN connu." : "Identité du demandeur non communiquée. Aucun nom ni adresse personnelle ne sera déduit du terrain."}</p>}
      {opp.coordonnees_status !== "complet" && <p className="text-xs text-amber-700" data-testid="radar-contact-incomplete">Adresse postale incomplète · à compléter avant envoi.</p>}
      {opp.coordonnees_status !== "complet" && opp.adresse && opp.cp && opp.commune && <p className="text-xs" data-testid="radar-terrain-fallback">À défaut d'adresse du contact, le courrier sera préparé à l'adresse du terrain, à l'attention du maître d'ouvrage.</p>}
      <div className="flex flex-wrap gap-2 pt-1">
        <Button variant="outline" size="sm" className="gap-1" onClick={() => setMode(mode === "manual" ? null : "manual")} data-testid="radar-contact-edit"><Pencil className="h-3.5 w-3.5" />{pr ? "Compléter / modifier" : "Ajouter un contact"}</Button>
        {business && <Button variant="outline" size="sm" className="gap-1" onClick={() => setMode(mode === "search" ? null : "search")} data-testid="radar-contact-search-toggle"><Search className="h-3.5 w-3.5" />Annuaire entreprises</Button>}
        {provenance && <Button variant="ghost" size="sm" disabled={deleting} onClick={remove} title="Retirer mes coordonnées" aria-label="Retirer mes coordonnées" data-testid="radar-contact-delete"><Trash2 className="h-4 w-4" /></Button>}
      </div>
      {mode === "manual" && <ContactEditor opp={opp} onSaved={saved} onCancel={() => setMode(null)} />}
      {mode === "search" && <CompanyContactSearch opp={opp} onSaved={saved} />}
    </>}
  </section>;
};