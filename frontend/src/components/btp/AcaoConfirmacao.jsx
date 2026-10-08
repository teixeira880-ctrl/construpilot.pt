import React, { useEffect, useState } from "react";
import { AlertCircle, Share2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from "@/components/ui/dialog";

/**
 * Modal de confirmação para `tool_call` com `requires_user_confirmation=true`.
 * Mostra resumo PT-PT da acção pendente e botões Confirmar/Cancelar.
 *
 * Fase D — quando `nomeFerramenta === "criar_orcamento"`, inclui uma
 * checkbox "Enviar ligação ao cliente por e-mail" (default off). Se
 * marcada, pede o e-mail do cliente e injecta `convidar_cliente_portal`
 * + `cliente_email` nos argumentos finais ao confirmar.
 */
export default function AcaoConfirmacao({
  aberto,
  nomeFerramenta,
  argumentos = {},
  resumoPt,
  onConfirmar,
  onCancelar,
  pending = false,
}) {
  const resumo = resumoPt || _construirResumo(nomeFerramenta, argumentos);
  const ehCriarOrcamento = nomeFerramenta === "criar_orcamento";

  const [enviarEmail, setEnviarEmail] = useState(false);
  const [emailCliente, setEmailCliente] = useState("");

  useEffect(() => {
    if (aberto) {
      setEnviarEmail(false);
      setEmailCliente("");
    }
  }, [aberto]);

  const handleConfirmar = () => {
    const extra = {};
    if (ehCriarOrcamento && enviarEmail && emailCliente.trim()) {
      extra.convidar_cliente_portal = true;
      extra.cliente_email = emailCliente.trim();
    } else if (ehCriarOrcamento && enviarEmail) {
      // Marcou mas não forneceu e-mail → apenas gera o link sem enviar
      extra.convidar_cliente_portal = true;
    }
    onConfirmar?.(extra);
  };

  return (
    <Dialog open={aberto} onOpenChange={(v) => { if (!v) onCancelar?.(); }}>
      <DialogContent
        className="max-w-lg"
        data-testid="btp-acao-confirmacao"
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertCircle className="h-5 w-5 text-amber-600" />
            Confirmar acção
          </DialogTitle>
          <DialogDescription>
            O assistente precisa da sua autorização antes de executar.
          </DialogDescription>
        </DialogHeader>

        <div className="rounded-md border border-amber-300 bg-amber-50 dark:bg-amber-950/30 p-3 text-sm leading-relaxed text-amber-900 dark:text-amber-200">
          <div className="font-medium mb-1">
            Ferramenta: <code className="font-mono">{nomeFerramenta}</code>
          </div>
          <div>{resumo}</div>
          {Object.keys(argumentos).length > 0 && (
            <details className="mt-2">
              <summary className="cursor-pointer text-xs opacity-70">
                Ver detalhes técnicos
              </summary>
              <pre className="mt-2 text-[11px] overflow-x-auto bg-white dark:bg-slate-900 p-2 rounded">
{JSON.stringify(argumentos, null, 2)}
              </pre>
            </details>
          )}
        </div>

        {/* Fase D — convite ao cliente final */}
        {ehCriarOrcamento && (
          <div className="rounded-md border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50 p-3 space-y-2" data-testid="acao-portal-cliente">
            <label className="flex items-start gap-2 cursor-pointer">
              <Checkbox
                checked={enviarEmail}
                onCheckedChange={(v) => setEnviarEmail(!!v)}
                data-testid="acao-portal-toggle"
                className="mt-0.5"
              />
              <div className="text-sm">
                <div className="font-medium flex items-center gap-1.5">
                  <Share2 className="h-3.5 w-3.5 text-primary" />
                  Enviar ligação ao cliente por e-mail
                </div>
                <div className="text-[11px] text-muted-foreground mt-0.5">
                  Gera um link público (válido 60 dias) para o cliente ver o
                  orçamento sem conta ConstruPilot. Pode também copiar o link
                  depois.
                </div>
              </div>
            </label>
            {enviarEmail && (
              <Input
                type="email"
                value={emailCliente}
                onChange={(e) => setEmailCliente(e.target.value)}
                placeholder="email@cliente.pt"
                className="h-9"
                data-testid="acao-portal-email-input"
              />
            )}
          </div>
        )}

        <DialogFooter className="gap-2 sm:gap-2">
          <Button
            variant="outline"
            onClick={onCancelar}
            disabled={pending}
            data-testid="btp-acao-cancelar"
          >
            Cancelar
          </Button>
          <Button
            onClick={handleConfirmar}
            disabled={pending}
            data-testid="btp-acao-confirmar"
          >
            {pending ? "A executar…" : "Confirmar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


function _construirResumo(nome, args) {
  if (!nome) return "Pretende prosseguir?";
  if (nome === "criar_orcamento") {
    const n = (args.items || []).length;
    return `Criar orçamento “${args.titulo || "(sem título)"}” para o cliente ${args.cliente_nome || "(sem nome)"} com ${n} linha${n === 1 ? "" : "s"}.`;
  }
  if (nome === "adicionar_item_orcamento") {
    return `Adicionar linha ao orçamento ${args.orcamento_id}: ${args.descricao} · ${args.qtd} ${args.unidade} × ${args.preco_unit_eur} €.`;
  }
  if (nome === "exportar_excel") {
    return `Gerar ficheiro Excel do orçamento ${args.orcamento_id}.`;
  }
  return `Executar a acção “${nome}”.`;
}
