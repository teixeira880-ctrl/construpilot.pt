import { DpgfImport } from "@/components/DpgfImport";

export default function DpgfPage() {
  return (
    <div className="max-w-6xl mx-auto px-5 py-8 space-y-4" data-testid="dpgf-page">
      <div>
        <p className="overline text-primary">Orçamentação do arquiteto</p>
        <h1 className="font-display text-3xl sm:text-4xl font-bold">DPGF · BPU · DQE</h1>
        <p className="text-sm text-muted-foreground mt-2 max-w-3xl">
          Carregue os mapas de quantidades Excel e os cadernos de encargos: o ConstruPilot deteta os capítulos, orçamenta com os seus preços e depois com a IA, aplica as suas instruções, assinala as omissões do caderno de encargos, consulta os seus subempreiteiros e transforma tudo num orçamento.
        </p>
      </div>
      <DpgfImport />
    </div>
  );
}
