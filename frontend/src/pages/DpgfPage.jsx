import { DpgfImport } from "@/components/DpgfImport";

export default function DpgfPage() {
  return (
    <div className="max-w-6xl mx-auto px-5 py-8 space-y-4" data-testid="dpgf-page">
      <div>
        <p className="overline text-primary">Chiffrage architecte</p>
        <h1 className="font-display text-3xl sm:text-4xl font-bold">DPGF · BPU · DQE</h1>
        <p className="text-sm text-muted-foreground mt-2 max-w-3xl">
          Déposez les bordereaux Excel et les CCTP : ConstruPilot détecte les lots, chiffre avec vos
          prix puis l'IA, applique vos consignes, signale les oublis du CCTP, consulte vos
          sous-traitants et transforme le tout en devis.
        </p>
      </div>
      <DpgfImport />
    </div>
  );
}
