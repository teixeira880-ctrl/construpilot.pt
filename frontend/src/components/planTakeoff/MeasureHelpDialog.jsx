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
            <HelpCircle className="h-4 w-4" /> Guia: da planta ao orçamento
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="rounded-sm max-w-2xl max-h-[88vh] overflow-y-auto" data-testid="measure-help-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-xl">
            <Ruler className="h-5 w-5 text-primary" /> Guia completo: da planta ao orçamento
          </DialogTitle>
          <DialogDescription>
            Siga estes passos por ordem para transformar uma planta ou uma Licença de Construção em orçamento orçamentado e enviado. A regra de ouro: <b className="text-foreground">calibra-se sempre antes de medir.</b>
          </DialogDescription>
        </DialogHeader>

        <div className="mt-2">
          <Step n={1} icon={Upload} title="Importar a sua planta ou a sua licença de construção (LC)">
            <ul className="list-disc pl-5 space-y-0.5">
              <li>Clique em <b>« Importar a minha planta »</b> (ou arraste e largue o ficheiro na zona).</li>
              <li>Importe o <b>planta do projeto</b> ou diretamente as plantas da sua <b>Licença de Construção (LC)</b>.</li>
              <li>Formatos aceites: <b>PDF, DXF, JPG, PNG, WEBP</b> — até <b>20 MB</b>.</li>
              <li>Planta de arquiteto, planta digitalizada ou até foto do smartphone: tudo funciona.</li>
              <li>O documento é apresentado; se tiver várias páginas (frequente num projeto de licenciamento), utilize as setas para mudar de página.</li>
            </ul>
          </Step>

          <Step n={2} icon={Ruler} title="Calibrar a escala (indispensável, em primeiro)">
            <p>Sem escala, a app não conhece o tamanho real da planta. As ferramentas Distância, Superfície, Divisão… permanecem <b>esbatidos</b> enquanto não estiver feito.</p>
            <ul className="list-disc pl-5 space-y-0.5">
              <li>Clique na ferramenta <b>« Calibrar »</b> (ícone régua).</li>
              <li>Clique <b>2 pontos</b> numa distância <b>connue</b> (ex. uma cota escrita « 4,25 m », uma parede cotada).</li>
              <li>Insira a <b>distância real em metros</b> depois valide.</li>
              <li>✅ A escala está guardada e todas as ferramentas desbloqueiam.</li>
            </ul>
            <p className="flex items-start gap-1.5 text-primary">
              <Sparkles className="h-4 w-4 mt-0.5 shrink-0" />
              Dica: o botão <b>« Calibrar pelas cotas »</b> deixe a IA detetar a escala automaticamente a partir das cotas escritas na planta.
            </p>
          </Step>

          <Step n={3} icon={Move} title="Medir (manual) — distância, superfície, divisão">
            <ul className="list-disc pl-5 space-y-0.5">
              <li><b><Move className="h-3.5 w-3.5 inline text-primary" /> Distância</b> : clique no ponto de partida e depois de chegada → <b>double-clic</b> para validar (comprimento em m).</li>
              <li><b><Hexagon className="h-3.5 w-3.5 inline text-primary" /> Superfície</b> : clique em cada canto da zona → <b>double-clic</b> para fechar (m² + perímetro).</li>
              <li><b><Square className="h-3.5 w-3.5 inline text-primary" /> Divisão</b> : desenhe os cantos de uma divisão → superfície no chão + paredes.</li>
              <li><b><Wand2 className="h-3.5 w-3.5 inline text-primary" /> Auto-divisão</b> : clique uma vez <b>no interior</b> de uma divisão fechada → deteção auto dos contornos.</li>
            </ul>
          </Step>

          <Step n={4} icon={Bot} title="Ou deixar a IA analisar a planta (automático)">
            <ul className="list-disc pl-5 space-y-0.5">
              <li>Uma vez a planta <b>calibrado</b>, clique em <b>« Analisar a planta »</b>.</li>
              <li>A IA deteta automaticamente: <b>pavimentos, paredes (ml + m²), aberturas, vigas/pilares</b> e propõe um <b>descritivo orçamentado</b> (estrutura / betão).</li>
              <li>Pode depois ajustar os preços (betão €/m³, aços €/kg, mão de obra, margem %).</li>
            </ul>
          </Step>

          <Step n={5} icon={FileDown} title="Gerar o orçamento">
            <ul className="list-disc pl-5 space-y-0.5">
              <li><b>« Estimar o orçamento (PDF) »</b> : gera diretamente o orçamento em PDF.</li>
              <li><b>« Abrir no editor »</b> : transfere as quantidades para o editor de orçamentos para ajustar tudo linha a linha.</li>
            </ul>
          </Step>

          <Step n={6} icon={Send} title="Finalizar e enviar o orçamento">
            <ul className="list-disc pl-5 space-y-0.5">
              <li>Em <b>o editor de orçamentos</b> : ajuste as linhas, quantidades, preços unitários e o IVA (6 % / 13 % / 23 %).</li>
              <li>Escolha o <b>client</b>, depois clique em <b>« Enviar orçamento »</b>.</li>
              <li>Le <b>mensagem e-mail</b> e o <b>número de orçamento</b> são preenchidos automaticamente; para as taxas reduzidas (6 % / 13 %), <b>a declaração de IVA é anexada automaticamente</b>.</li>
              <li>O orçamento parte com a sua <b>logotipo e os seus contactos</b>, e encontra-se em <b>« Seguimento dos orçamentos »</b>.</li>
            </ul>
          </Step>

          <div className="rounded-sm border border-border bg-muted/40 p-4 mt-1 space-y-2">
            <p className="font-semibold flex items-center gap-2"><MousePointerClick className="h-4 w-4 text-primary" /> Os gestos essenciais</p>
            <ul className="text-sm text-muted-foreground space-y-1">
              <li><b>Duplo clique</b> = terminar a medição em curso.</li>
              <li><Key>Esc</Key> = anular a medição em curso (nada é guardado).</li>
              <li><b>« Cancelar tudo »</b> = apaga os pontos da medição em curso.</li>
              <li>Roda ou botões <Key>+</Key>/<Key>−</Key> = zoom; clicar e arrastar = deslocar a planta.</li>
              <li><MousePointer2 className="h-3.5 w-3.5 inline" /> Ferramenta <b>« Seleção »</b> = voltar ao modo normal para clicar/deslocar os elementos.</li>
            </ul>
          </div>

          <div className="rounded-sm border border-amber-500/40 bg-amber-500/10 p-4 mt-3 space-y-1.5">
            <p className="font-semibold flex items-center gap-2 text-amber-700"><Lightbulb className="h-4 w-4" /> Conselhos para ser preciso</p>
            <ul className="text-sm text-amber-800 space-y-1 list-disc pl-5">
              <li><b>Amplie</b> antes de clicar nos cantos: quanto mais zoom, mais preciso.</li>
              <li>Para calibrar, escolha a <b>maior cota possível</b> (uma referência longa reduz o erro).</li>
              <li><b>Cada página tem a sua própria escala</b> : se mudar de página/planta, recalibre.</li>
              <li>No painel da direita, pode <b>renommer</b>, <b>converter em divisão</b>, <b>deduzir</b> (vão, abertura) ou <b>supprimer</b> uma medida.</li>
            </ul>
          </div>
        </div>

        <div className="flex justify-end pt-2">
          <Button onClick={() => setOpen(false)} className="rounded-sm gap-2 bg-primary" data-testid="measure-help-close">
            <CornerDownLeft className="h-4 w-4" /> Compreendi, começar
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default MeasureHelpDialog;
