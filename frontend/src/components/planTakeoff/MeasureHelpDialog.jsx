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
            <HelpCircle className="h-4 w-4" /> Guia: do plano ao orçamento
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="rounded-sm max-w-2xl max-h-[88vh] overflow-y-auto" data-testid="measure-help-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-xl">
            <Ruler className="h-5 w-5 text-primary" /> Guia completo: do plano ao orçamento
          </DialogTitle>
          <DialogDescription>
            Segue estes passos por ordem para transformar um plano ou uma Licença de Construção (LC)
            num orçamento com preços e enviado. A regra de ouro: <b className="text-foreground">calibrar sempre antes de medir.</b>
          </DialogDescription>
        </DialogHeader>

        <div className="mt-2">
          <Step n={1} icon={Upload} title="Importar a planta ou a Licença de Construção (LC)">
            <ul className="list-disc pl-5 space-y-0.5">
              <li>Clica em <b>«Importar planta»</b> (ou arrasta o ficheiro para a zona).</li>
              <li>Importa a <b>planta do projeto</b> ou diretamente as plantas da tua <b>Licença de Construção (LC)</b>.</li>
              <li>Formatos aceites: <b>PDF, DXF, JPG, PNG, WEBP</b> — até <b>20 MB</b>.</li>
              <li>Planta de arquiteto, planta digitalizada ou até foto de telemóvel: tudo funciona.</li>
              <li>O documento aparece; se tiver várias páginas (frequente numa LC), usa as setas para mudar de página.</li>
            </ul>
          </Step>

          <Step n={2} icon={Ruler} title="Calibrar a escala (indispensável, em primeiro lugar)">
            <p>Sem escala, a app não conhece o tamanho real da planta. As ferramentas Distância, Área, Compartimento… ficam <b>cinzentas</b> até isso estar feito.</p>
            <ul className="list-disc pl-5 space-y-0.5">
              <li>Clica na ferramenta <b>«Calibrar»</b> (ícone régua).</li>
              <li>Clica <b>2 pontos</b> numa distância <b>conhecida</b> (ex: uma cota escrita «4,25 m», uma parede cotada).</li>
              <li>Insere a <b>distância real em metros</b> e confirma.</li>
              <li>✅ A escala fica guardada e todas as ferramentas ficam disponíveis.</li>
            </ul>
            <p className="flex items-start gap-1.5 text-primary">
              <Sparkles className="h-4 w-4 mt-0.5 shrink-0" />
              Dica: o botão <b>«Calibrar pelas cotas»</b> deixa a IA detetar a escala automaticamente a partir das cotas escritas na planta.
            </p>
          </Step>

          <Step n={3} icon={Move} title="Medir (manual) — distância, área, compartimento">
            <ul className="list-disc pl-5 space-y-0.5">
              <li><b><Move className="h-3.5 w-3.5 inline text-primary" /> Distância</b>: clica o ponto de partida e depois o de chegada → <b>duplo-clique</b> para validar (comprimento em m).</li>
              <li><b><Hexagon className="h-3.5 w-3.5 inline text-primary" /> Área</b>: clica em cada canto da zona → <b>duplo-clique</b> para fechar (m² + perímetro).</li>
              <li><b><Square className="h-3.5 w-3.5 inline text-primary" /> Compartimento</b>: desenha os cantos de um compartimento → área de pavimento + paredes.</li>
              <li><b><Wand2 className="h-3.5 w-3.5 inline text-primary" /> Auto-compartimento</b>: clica uma vez <b>dentro</b> de um compartimento fechado → deteção automática dos contornos.</li>
            </ul>
          </Step>

          <Step n={4} icon={Bot} title="Ou deixa a IA analisar a planta (automático)">
            <ul className="list-disc pl-5 space-y-0.5">
              <li>Depois de a planta estar <b>calibrada</b>, clica em <b>«Analisar a planta»</b>.</li>
              <li>A IA deteta automaticamente: <b>lajes, paredes (ml + m²), vãos, vigas/pilares</b> e propõe uma <b>descrição orçamentada</b> (estrutura / betão).</li>
              <li>Podes depois ajustar os preços (betão €/m³, aço €/kg, mão de obra, margem %).</li>
            </ul>
          </Step>

          <Step n={5} icon={FileDown} title="Gerar o orçamento">
            <ul className="list-disc pl-5 space-y-0.5">
              <li><b>«Estimar o orçamento (PDF)»</b>: gera diretamente o cálculo em PDF.</li>
              <li><b>«Abrir no editor»</b>: transfere as quantidades para o editor de orçamento para ajustar tudo linha a linha.</li>
            </ul>
          </Step>

          <Step n={6} icon={Send} title="Finalizar e enviar o orçamento">
            <ul className="list-disc pl-5 space-y-0.5">
              <li>No <b>editor de orçamento</b>: ajusta as linhas, quantidades, preços unitários e o IVA (6 % / 13 % / 23 %).</li>
              <li>Escolhe o <b>cliente</b> e clica em <b>«Enviar orçamento»</b>.</li>
              <li>A <b>mensagem de email</b> e o <b>número do orçamento</b> preenchem-se automaticamente.</li>
              <li>O orçamento segue com o teu <b>logótipo e contactos</b> e fica em <b>«Acompanhamento de orçamentos»</b>.</li>
            </ul>
          </Step>

          <div className="rounded-sm border border-border bg-muted/40 p-4 mt-1 space-y-2">
            <p className="font-semibold flex items-center gap-2"><MousePointerClick className="h-4 w-4 text-primary" /> Os gestos essenciais</p>
            <ul className="text-sm text-muted-foreground space-y-1">
              <li><b>Duplo-clique</b> = terminar a medição em curso.</li>
              <li><Key>Esc</Key> = cancelar a medição em curso (nada é guardado).</li>
              <li><b>«Cancelar tudo»</b> = apaga os pontos da medição em curso.</li>
              <li>Roda do rato ou botões <Key>+</Key>/<Key>−</Key> = zoom; clicar e arrastar = deslocar a planta.</li>
              <li><MousePointer2 className="h-3.5 w-3.5 inline" /> Ferramenta <b>«Seleção»</b> = voltar ao modo normal para clicar/arrastar elementos.</li>
            </ul>
          </div>

          <div className="rounded-sm border border-amber-500/40 bg-amber-500/10 p-4 mt-3 space-y-1.5">
            <p className="font-semibold flex items-center gap-2 text-amber-700"><Lightbulb className="h-4 w-4" /> Conselhos para ser preciso</p>
            <ul className="text-sm text-amber-800 space-y-1 list-disc pl-5">
              <li><b>Faz zoom</b> antes de clicar nos cantos: quanto mais zoom, mais preciso.</li>
              <li>Para calibrar, escolhe a <b>maior cota possível</b> (uma referência longa reduz o erro).</li>
              <li><b>Cada página tem a sua própria escala</b>: se mudares de página/planta, recalibra.</li>
              <li>No painel da direita, podes <b>renomear</b>, <b>converter em compartimento</b>, <b>deduzir</b> (poço, abertura) ou <b>eliminar</b> uma medição.</li>
            </ul>
          </div>
        </div>

        <div className="flex justify-end pt-2">
          <Button onClick={() => setOpen(false)} className="rounded-sm gap-2 bg-primary" data-testid="measure-help-close">
            <CornerDownLeft className="h-4 w-4" /> Percebi, começar
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default MeasureHelpDialog;
