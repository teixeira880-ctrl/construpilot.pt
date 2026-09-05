import { useState } from "react";
import {
  HelpCircle, Ruler, Move, Hexagon, Square, Wand2, MousePointer2,
  MousePointerClick, CornerDownLeft, Lightbulb, Sparkles, Upload, Bot,
  FileDown, Send,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogDescription,
} from "@/components/ui/dialog";

const Step = ({ n, icon: Icon, title, children }) => (
  <div className="flex gap-3" data-testid={`measure-help-step-${n}`}>
    <div className="shrink-0">
      <div className="h-8 w-8 rounded-full bg-primary text-white flex items-center justify-center font-bold text-sm">
        {n}
      </div>
    </div>
    <div className="flex-1 pb-4 border-b border-border/60">
      <p className="font-semibold flex items-center gap-2 text-[15px]">
        {Icon && <Icon className="h-4 w-4 text-primary" />} {title}
      </p>
      <div className="text-sm text-muted-foreground mt-1 leading-relaxed space-y-1">{children}</div>
    </div>
  </div>
);

const Key = ({ children }) => (
  <span className="inline-block rounded border border-border bg-muted px-1.5 py-0.5 text-xs font-mono mx-0.5">
    {children}
  </span>
);

/** Guide intégré complet : de l'import du plan jusqu'au devis envoyé. */
export function MeasureHelpDialog({ trigger }) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger || (
          <Button variant="outline" size="sm" data-testid="measure-help-btn"
                  className="rounded-sm gap-2 border-primary/40 text-primary hover:bg-primary/10">
            <HelpCircle className="h-4 w-4" /> Guide : du plan au devis
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="rounded-sm max-w-2xl max-h-[88vh] overflow-y-auto" data-testid="measure-help-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-xl">
            <Ruler className="h-5 w-5 text-primary" /> Guide complet : du plan au devis
          </DialogTitle>
          <DialogDescription>
            Suivez ces étapes dans l'ordre pour transformer un plan ou un Permis de Construire (PC)
            en devis chiffré et envoyé. La règle d'or : <b className="text-foreground">on calibre toujours avant de mesurer.</b>
          </DialogDescription>
        </DialogHeader>

        <div className="mt-2">
          <Step n={1} icon={Upload} title="Importer votre plan ou votre Permis de Construire (PC)">
            <ul className="list-disc pl-5 space-y-0.5">
              <li>Cliquez sur <b>« Importer mon plan »</b> (ou glissez-déposez le fichier dans la zone).</li>
              <li>Importez le <b>plan du projet</b> ou directement les plans de votre <b>Permis de Construire (PC)</b>.</li>
              <li>Formats acceptés : <b>PDF, DXF, JPG, PNG, WEBP</b> — jusqu'à <b>20 Mo</b>.</li>
              <li>Plan d'architecte, plan scanné ou même photo au smartphone : tout fonctionne.</li>
              <li>Le document s'affiche ; s'il a plusieurs pages (fréquent pour un PC), utilisez les flèches pour changer de page.</li>
            </ul>
          </Step>

          <Step n={2} icon={Ruler} title="Calibrer l'échelle (indispensable, en premier)">
            <p>Sans échelle, l'app ne connaît pas la taille réelle du plan. Les outils Distance, Surface, Pièce… restent <b>grisés</b> tant que ce n'est pas fait.</p>
            <ul className="list-disc pl-5 space-y-0.5">
              <li>Cliquez sur l'outil <b>« Calibrer »</b> (icône règle).</li>
              <li>Cliquez <b>2 points</b> sur une distance <b>connue</b> (ex. une cote écrite « 4,25 m », un mur coté).</li>
              <li>Saisissez la <b>distance réelle en mètres</b> puis validez.</li>
              <li>✅ L'échelle est enregistrée et tous les outils se débloquent.</li>
            </ul>
            <p className="flex items-start gap-1.5 text-primary">
              <Sparkles className="h-4 w-4 mt-0.5 shrink-0" />
              Astuce : le bouton <b>« Calibrer par les cotes »</b> laisse l'IA détecter l'échelle automatiquement à partir des cotes écrites sur le plan.
            </p>
          </Step>

          <Step n={3} icon={Move} title="Mesurer (manuel) — distance, surface, pièce">
            <ul className="list-disc pl-5 space-y-0.5">
              <li><b><Move className="h-3.5 w-3.5 inline text-primary" /> Distance</b> : cliquez le point de départ puis d'arrivée → <b>double-clic</b> pour valider (longueur en m).</li>
              <li><b><Hexagon className="h-3.5 w-3.5 inline text-primary" /> Surface</b> : cliquez chaque coin de la zone → <b>double-clic</b> pour fermer (m² + périmètre).</li>
              <li><b><Square className="h-3.5 w-3.5 inline text-primary" /> Pièce</b> : dessinez les coins d'une pièce → surface au sol + murs.</li>
              <li><b><Wand2 className="h-3.5 w-3.5 inline text-primary" /> Auto-pièce</b> : cliquez une fois <b>à l'intérieur</b> d'une pièce fermée → détection auto des contours.</li>
            </ul>
          </Step>

          <Step n={4} icon={Bot} title="Ou laisser l'IA analyser le plan (automatique)">
            <ul className="list-disc pl-5 space-y-0.5">
              <li>Une fois le plan <b>calibré</b>, cliquez sur <b>« Analyser le plan »</b>.</li>
              <li>L'IA détecte automatiquement : <b>planchers, murs (ml + m²), ouvertures, poutres/poteaux</b> et propose un <b>descriptif chiffré</b> (gros œuvre / béton).</li>
              <li>Vous pouvez ensuite ajuster les prix (béton €/m³, aciers €/kg, main d'œuvre, marge %).</li>
            </ul>
          </Step>

          <Step n={5} icon={FileDown} title="Générer le devis">
            <ul className="list-disc pl-5 space-y-0.5">
              <li><b>« Estimer le devis (PDF) »</b> : génère directement le chiffrage en PDF.</li>
              <li><b>« Ouvrir dans l'éditeur »</b> : bascule les quantités dans l'éditeur de devis pour tout ajuster ligne par ligne.</li>
            </ul>
          </Step>

          <Step n={6} icon={Send} title="Finaliser et envoyer le devis">
            <ul className="list-disc pl-5 space-y-0.5">
              <li>Dans <b>l'éditeur de devis</b> : ajustez les lignes, quantités, prix unitaires et la TVA (5,5 % / 10 % / 20 %).</li>
              <li>Choisissez le <b>client</b>, puis cliquez sur <b>« Envoyer devis »</b>.</li>
              <li>Le <b>message e-mail</b> et le <b>numéro de devis</b> se remplissent automatiquement ; pour les taux réduits (5,5 % / 10 %), <b>l'attestation de TVA est jointe automatiquement</b>.</li>
              <li>Le devis part avec votre <b>logo et vos coordonnées</b>, et se retrouve dans <b>« Suivi des devis »</b>.</li>
            </ul>
          </Step>

          <div className="rounded-sm border border-border bg-muted/40 p-4 mt-1 space-y-2">
            <p className="font-semibold flex items-center gap-2"><MousePointerClick className="h-4 w-4 text-primary" /> Les gestes essentiels</p>
            <ul className="text-sm text-muted-foreground space-y-1">
              <li><b>Double-clic</b> = terminer la mesure en cours.</li>
              <li><Key>Échap</Key> = annuler la mesure en cours (rien n'est enregistré).</li>
              <li><b>« Annuler tout »</b> = efface les points de la mesure en cours.</li>
              <li>Molette ou boutons <Key>+</Key>/<Key>−</Key> = zoom ; cliquer-glisser = déplacer le plan.</li>
              <li><MousePointer2 className="h-3.5 w-3.5 inline" /> Outil <b>« Sélection »</b> = revenir en mode normal pour cliquer/déplacer les éléments.</li>
            </ul>
          </div>

          <div className="rounded-sm border border-amber-500/40 bg-amber-500/10 p-4 mt-3 space-y-1.5">
            <p className="font-semibold flex items-center gap-2 text-amber-700"><Lightbulb className="h-4 w-4" /> Conseils pour être précis</p>
            <ul className="text-sm text-amber-800 space-y-1 list-disc pl-5">
              <li><b>Zoomez</b> avant de cliquer sur les coins : plus c'est zoomé, plus c'est précis.</li>
              <li>Pour calibrer, choisissez la <b>plus grande cote possible</b> (une longue référence réduit l'erreur).</li>
              <li><b>Chaque page a sa propre échelle</b> : si vous changez de page/plan, recalibrez.</li>
              <li>Dans le panneau de droite, vous pouvez <b>renommer</b>, <b>convertir en pièce</b>, <b>déduire</b> (trémie, ouverture) ou <b>supprimer</b> une mesure.</li>
            </ul>
          </div>
        </div>

        <div className="flex justify-end pt-2">
          <Button onClick={() => setOpen(false)} className="rounded-sm gap-2 bg-primary" data-testid="measure-help-close">
            <CornerDownLeft className="h-4 w-4" /> J'ai compris, commencer
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default MeasureHelpDialog;
