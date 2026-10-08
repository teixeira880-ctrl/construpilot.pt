import React, { useEffect, useState } from "react";
import { AlertCircle, Share2, Copy, CheckCircle2, Link as LinkIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { BotaoWhatsApp } from "./BotaoWhatsApp";

/**
 * Modal de confirmação para `tool_call` com `requires_user_confirmation=true`.
 *
 * Mostra resumo PT-PT da acção pendente e botões Confirmar/Cancelar.
 *
 * - Fase D: para `criar_orcamento`, inclui checkbox "Enviar ligação ao
 *   cliente por e-mail" (default off); se marcada, pede e-mail e injecta
 *   `convidar_cliente_portal` + `cliente_email` nos argumentos finais.
 *
 * - Fase C (WhatsApp share): quando a confirmação devolve um
 *   `public_link_url`, o pai injecta `linkPublico={url, titulo}` e o modal
 *   passa ao estado "sucesso": mostra o link gerado + 2 botões
 *   (Copiar · Partilhar WhatsApp). O utilizador fecha o modal
 *   manualmente clicando em "Fechar".
 */
export default function AcaoConfirmacao({
  aberto,
  nomeFerramenta,
  argumentos = {},
  resumoPt,
  linkPublico = null,     // Fase C: {url, titulo} depois de criação
  onConfirmar,
  onCancelar,
  onFechar,               // Fase C: fechar quando mostramos link gerado
  pending = false,
}) {
  const resumo = resumoPt || _construirResumo(nomeFerramenta, argumentos);
  const ehCriarOrcamento = nomeFerramenta === "criar_orcamento";
  const mostrarLinkGerado = !!linkPublico?.url;

  const [enviarEmail, setEnviarEmail] = useState(false);
  const [emailCliente, setEmailCliente] = useState("");

  useEffect(() => {
    if (aberto && !mostrarLinkGerado) {
      setEnviarEmail(false);
      setEmailCliente("");
    }
  }, [aberto, mostrarLinkGerado]);

  const copiarLinkPublico = async () => {
    if (!linkPublico?.url) return;
    try {
      await navigator.clipboard.writeText(linkPublico.url);
      toast.success("Link copiado");
    } catch {
      toast.error("Não foi possível copiar.");
    }
  };

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

  // Fecho controlado — se estamos a mostrar link gerado, usa onFechar;
  // caso contrário, cancela a acção pendente.
  const onOpenChangeHandler = (v) => {
    if (v) return;
    if (mostrarLinkGerado) onFechar?.();
    else onCancelar?.();
  };

  return (
    <Dialog open={aberto} onOpenChange={onOpenChangeHandler}>
      <DialogContent
        className="max-w-lg"
        data-testid="btp-acao-confirmacao"
      >
        {mostrarLinkGerado ? (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5 text-emerald-600" />
                Link do cliente gerado
              </DialogTitle>
              <DialogDescription>
                O orçamento{linkPublico.titulo ? ` "${linkPublico.titulo}"` : ""} está pronto.
                Partilhe a ligação com o cliente pelo canal preferido.
              </DialogDescription>
            </DialogHeader>

            <div
              className="rounded-md border border-emerald-200 bg-emerald-50 dark:bg-emerald-950/30 dark:border-emerald-900/50 p-3 space-y-2"
              data-testid="acao-link-gerado"
            >
              <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-emerald-900 dark:text-emerald-200">
                <LinkIcon className="h-3.5 w-3.5" />
                Ligação pública (válida 60 dias)
              </div>
              <div className="font-mono text-xs break-all bg-white dark:bg-slate-900 border border-emerald-200 dark:border-emerald-900/40 rounded px-2 py-1.5"
                   data-testid="acao-link-gerado-url">
                {linkPublico.url}
              </div>
            </div>

            <div className="flex flex-col sm:flex-row gap-2 pt-1">
              <Button
                variant="outline"
                className="rounded-sm gap-2 sm:flex-1"
                onClick={copiarLinkPublico}
                data-testid="acao-link-copiar"
              >
                <Copy className="h-4 w-4" /> Copiar link
              </Button>
              <BotaoWhatsApp
                url={linkPublico.url}
                mensagem={
                  linkPublico.titulo
                    ? `Orçamento ${linkPublico.titulo} — ConstruPilot`
                    : "Orçamento para o cliente — ConstruPilot"
                }
                className="sm:flex-1 justify-center"
                testid="acao-link-whatsapp"
              />
            </div>

            <DialogFooter className="gap-2 sm:gap-2">
              <Button
                onClick={() => onFechar?.()}
                data-testid="acao-link-fechar"
              >
                Fechar
              </Button>
            </DialogFooter>
          </>
        ) : (
          <>
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
                      orçamento sem conta ConstruPilot. Após a criação, poderá
                      também partilhar por WhatsApp ou copiar a ligação.
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
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}


function _construirResumo(nome, args) {
  if (!nome) return "Pretende prosseguir?";
  if (nome === "criar_orcamento") {
    const n = (args.items || []).length;
    return `Criar orçamento "${args.titulo || "(sem título)"}" para o cliente ${args.cliente_nome || "(sem nome)"} com ${n} linha${n === 1 ? "" : "s"}.`;
  }
  if (nome === "adicionar_item_orcamento") {
    return `Adicionar linha ao orçamento ${args.orcamento_id}: ${args.descricao} · ${args.qtd} ${args.unidade} × ${args.preco_unit_eur} €.`;
  }
  if (nome === "exportar_excel") {
    return `Gerar ficheiro Excel do orçamento ${args.orcamento_id}.`;
  }
  return `Executar a acção "${nome}".`;
}
