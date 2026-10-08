import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import {
  Loader2, Paperclip, Send, Sparkles, X, ArrowRight,
  FileText, Image as ImageIcon, Zap, Wrench, Search, FileSpreadsheet,
  Calculator, Library, HelpCircle, FolderOpen, DollarSign,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";
import AcaoConfirmacao from "./AcaoConfirmacao";
import MissingDataCard from "./MissingDataCard";
import { confirmTool, fileToBase64, streamChat } from "./sseClient";
import "./assistente-btp.css";

const ICONES_TOOL = {
  abrir_app: FolderOpen,
  criar_orcamento: FileSpreadsheet,
  adicionar_item_orcamento: FileSpreadsheet,
  calcular_metrado: Calculator,
  estimar_custo: Calculator,
  pesquisar_norma: Search,
  obter_preco_material: DollarSign,
  exportar_excel: FileSpreadsheet,
  calcular_escada: Calculator,
  pesquisar_biblioteca: Library,
  pedir_precisao: HelpCircle,
};

const LIMITE_ANEXO_MB = 20;
const MAX_ANEXOS = 5;


export default function AssistenteBTPChat({ conversationId: initialConvId = null }) {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [mensagens, setMensagens] = useState([]); // [{role, text?, pills?, missing?, meta?}]
  const [prompt, setPrompt] = useState("");
  const [anexos, setAnexos] = useState([]);       // [{filename, mime, base64, size}]
  const [envio, setEnvio] = useState(false);
  const [conversationId, setConversationId] = useState(initialConvId);
  const [confirmacao, setConfirmacao] = useState(null); // {toolCallId, name, args}
  const [confirmPending, setConfirmPending] = useState(false);
  const [linkPublicoGerado, setLinkPublicoGerado] = useState(null); // {url, titulo}
  const abortRef = useRef(null);
  const scrollRef = useRef(null);

  // Autoscroll
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [mensagens]);

  // Cleanup em unmount
  useEffect(() => () => { try { abortRef.current?.abort(); } catch {} }, []);

  const anexarFicheiros = async (files) => {
    const novos = [];
    for (const f of Array.from(files || [])) {
      if (anexos.length + novos.length >= MAX_ANEXOS) {
        toast({ title: `Máximo ${MAX_ANEXOS} anexos por turno.`, variant: "destructive" });
        break;
      }
      if (f.size > LIMITE_ANEXO_MB * 1024 * 1024) {
        toast({ title: `“${f.name}” excede ${LIMITE_ANEXO_MB} MB.`, variant: "destructive" });
        continue;
      }
      try {
        const base64 = await fileToBase64(f);
        novos.push({
          filename: f.name,
          mime_type: f.type || "application/octet-stream",
          data_b64: base64,
          size: f.size,
        });
      } catch (e) {
        toast({ title: `Falha a ler “${f.name}”.`, variant: "destructive" });
      }
    }
    if (novos.length) setAnexos((prev) => [...prev, ...novos]);
  };

  const enviar = async (textoOverride) => {
    const texto = (textoOverride ?? prompt).trim();
    if (!texto || envio) return;
    setEnvio(true);
    const anexosEnvio = anexos;
    setMensagens((prev) => [
      ...prev,
      {
        role: "user",
        text: texto,
        anexos_meta: anexosEnvio.map((a) => ({
          filename: a.filename, mime: a.mime_type,
        })),
      },
      {
        role: "agent",
        text: "",
        pills: [],         // tool_call pills
        missing: [],       // missing_data cards
        meta: { mode: null, model: null, duracao: null },
      },
    ]);
    setPrompt("");
    setAnexos([]);

    const ac = new AbortController();
    abortRef.current = ac;
    try {
      for await (const ev of streamChat({
        prompt: texto,
        attachments: anexosEnvio,
        conversationId,
        signal: ac.signal,
      })) {
        _processarEvento(ev);
      }
    } catch (e) {
      _append({ pills: [{ nome: "erro", estado: "erro", mensagem: "Falha de comunicação. Tente novamente." }] });
      toast({
        title: "Falha a contactar o assistente",
        description: String(e?.message || e).slice(0, 180),
        variant: "destructive",
      });
    } finally {
      setEnvio(false);
      abortRef.current = null;
    }
  };

  // Mutar a última mensagem do agente
  const _append = (patch) => {
    setMensagens((prev) => {
      if (!prev.length) return prev;
      const out = prev.slice();
      const last = { ...out[out.length - 1] };
      if (patch.textChunk != null) {
        last.text = (last.text || "") + patch.textChunk;
      }
      if (patch.pills) {
        last.pills = (last.pills || []).concat(patch.pills);
      }
      if (patch.pillPatch) {
        last.pills = (last.pills || []).map((p) =>
          p.id === patch.pillPatch.id ? { ...p, ...patch.pillPatch.change } : p,
        );
      }
      if (patch.missing) {
        last.missing = (last.missing || []).concat(patch.missing);
      }
      if (patch.meta) {
        last.meta = { ...(last.meta || {}), ...patch.meta };
      }
      if (patch.navigate) {
        last.navigate = patch.navigate;
      }
      out[out.length - 1] = last;
      return out;
    });
  };

  const _processarEvento = (ev) => {
    switch (ev.type) {
      case "thinking":
        _append({
          pills: [{
            id: "thinking", nome: "A pensar…",
            estado: "pending", icone: Sparkles,
            modo: ev.data?.mode, modelo: ev.data?.model,
          }],
          meta: { mode: ev.data?.mode, model: ev.data?.model },
        });
        break;
      case "text_chunk":
        _append({
          textChunk: ev.data?.text || "",
          pillPatch: { id: "thinking", change: { estado: "done", nome: "Responde…" } },
        });
        break;
      case "tool_call": {
        const Icone = ICONES_TOOL[ev.data?.name] || Wrench;
        _append({
          pills: [{
            id: `tc_${ev.data?.id}`,
            nome: `A executar: ${ev.data?.name}`,
            estado: "pending",
            icone: Icone,
          }],
        });
        break;
      }
      case "tool_result": {
        const okFinal = ev.data?.status === "ok";
        const pendConf = ev.data?.status === "needs_user_confirmation";
        const isNavigate = ev.data?.payload?.action === "navigate";
        _append({
          pillPatch: {
            id: `tc_${ev.data?.tool_call_id}`,
            change: {
              estado: pendConf ? "confirm" : (okFinal ? "done" : "erro"),
              nome: pendConf ? "Aguarda confirmação" : (okFinal ? "✓ Concluído" : "Falha"),
              mensagem: ev.data?.user_message_pt,
              payload: ev.data?.payload,
            },
          },
        });
        if (isNavigate) {
          _append({ navigate: ev.data.payload });
        }
        if (pendConf) {
          const call = ev.data?.payload?.call;
          if (call) {
            setConfirmacao({
              toolCallId: call.id,
              name: call.name,
              args: call.arguments || {},
            });
          }
        }
        break;
      }
      case "missing_data":
        _append({ missing: [ev.data] });
        break;
      case "final":
        if (ev.data?.conversation_id && ev.data.conversation_id !== conversationId) {
          setConversationId(ev.data.conversation_id);
        }
        _append({
          meta: {
            mode: ev.data?.mode, model: ev.data?.model,
            duracao: ev.data?.duration_s,
          },
          pillPatch: { id: "thinking", change: { estado: "done", nome: "✓" } },
        });
        break;
      case "error":
        _append({ pills: [{
          nome: "Erro", estado: "erro",
          mensagem: ev.data?.message_pt || "Falha interna.",
        }] });
        break;
      default:
        break;
    }
  };

  const executarConfirmacao = async (confirmed) => {
    if (!confirmacao) return;
    setConfirmPending(true);
    try {
      const r = await confirmTool({
        conversationId,
        toolCallId: confirmacao.toolCallId,
        name: confirmacao.name,
        args: confirmacao.args,
        confirmed,
      });
      if (confirmed) {
        _append({ pills: [{
          nome: `✓ ${confirmacao.name} concluído`,
          estado: "done",
          mensagem: r?.user_message_pt || "Executado.",
          payload: r?.payload,
        }] });
        toast({
          title: "Acção executada",
          description: r?.user_message_pt || "Concluído.",
        });
        // Fase C — se gerou link público, mantém o modal aberto a mostrar
        // o link + botões Copiar/WhatsApp. Caso contrário, fecha.
        const publicUrl = r?.payload?.public_link_url;
        if (publicUrl) {
          setLinkPublicoGerado({
            url: publicUrl,
            titulo: confirmacao?.args?.titulo || "",
          });
          setConfirmPending(false);
          return;
        }
      } else {
        _append({ pills: [{
          nome: `✗ ${confirmacao.name} cancelado`, estado: "erro",
          mensagem: "Cancelado pelo utilizador.",
        }] });
      }
    } catch (e) {
      toast({
        title: "Falha a executar a acção",
        description: String(e?.message || e).slice(0, 180),
        variant: "destructive",
      });
    } finally {
      setConfirmPending(false);
      // Só fecha o modal se não ficou nenhum link para apresentar.
      // (Em caso de erro / cancelamento, fecha sempre.)
      setConfirmacao((prev) => (linkPublicoGerado ? prev : null));
    }
  };

  const fecharModalConfirmacao = () => {
    setLinkPublicoGerado(null);
    setConfirmacao(null);
  };


  return (
    <div className="btp-chat" data-testid="btp-chat-root">
      {/* Scroll area */}
      <div
        ref={scrollRef}
        className="btp-chat__scroll px-4 py-6"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          if (e.dataTransfer?.files?.length) anexarFicheiros(e.dataTransfer.files);
        }}
      >
        {mensagens.length === 0 ? (
          <EstadoVazio />
        ) : (
          <div className="space-y-4 max-w-3xl mx-auto">
            {mensagens.map((m, i) => (
              <MensagemBubble
                key={i}
                mensagem={m}
                onNavegar={(url) => navigate(url)}
                onResponderMissing={(texto) => enviar(texto)}
                sending={envio}
              />
            ))}
          </div>
        )}
      </div>

      {/* Composer */}
      <div className="btp-composer">
        <div className="max-w-3xl mx-auto">
          {anexos.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-2">
              {anexos.map((a, idx) => (
                <AnexoChip key={idx} anexo={a} onRemover={() =>
                  setAnexos((prev) => prev.filter((_, j) => j !== idx))
                } />
              ))}
            </div>
          )}
          <div className="flex gap-2 items-end">
            <label
              className="shrink-0 cursor-pointer rounded-md border border-slate-300 dark:border-slate-700 p-2 hover:bg-slate-50 dark:hover:bg-slate-800"
              data-testid="btp-anexar-btn"
              title="Anexar imagem, PDF ou plano"
            >
              <Paperclip className="h-5 w-5" />
              <input
                type="file"
                multiple
                accept="image/*,application/pdf,.dwg,.dxf,.ifc"
                className="hidden"
                onChange={(e) => anexarFicheiros(e.target.files)}
              />
            </label>
            <Textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  enviar();
                }
              }}
              placeholder="Faça uma pergunta, peça um orçamento, anexe uma planta…"
              rows={1}
              disabled={envio}
              data-testid="btp-prompt-input"
              className="flex-1 resize-none min-h-[42px] max-h-[200px]"
            />
            <Button
              size="icon"
              onClick={() => enviar()}
              disabled={envio || !prompt.trim()}
              data-testid="btp-enviar-btn"
            >
              {envio ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </Button>
          </div>
          <div className="text-xs opacity-60 mt-1 px-1">
            Enter envia · Shift+Enter nova linha · Suporta PT-PT, imagens, PDF
          </div>
        </div>
      </div>

      <AcaoConfirmacao
        aberto={!!confirmacao}
        nomeFerramenta={confirmacao?.name}
        argumentos={confirmacao?.args}
        pending={confirmPending}
        linkPublico={linkPublicoGerado}
        onConfirmar={() => executarConfirmacao(true)}
        onCancelar={() => executarConfirmacao(false)}
        onFechar={fecharModalConfirmacao}
      />
    </div>
  );
}


// =======================================================================
// Sub-componentes
// =======================================================================
function EstadoVazio() {
  const sugestoes = [
    "Faz-me um orçamento para uma moradia T3 em Sintra.",
    "Qual é a altura mínima de pé-direito segundo o RGEU?",
    "Preço actual do cimento CEM II 42,5 em Lisboa?",
    "Abre-me o módulo de orçamentos.",
  ];
  return (
    <div className="max-w-2xl mx-auto text-center py-12">
      <div className="inline-flex items-center gap-2 bg-indigo-500/10 border border-indigo-500/30 rounded-full px-3 py-1 text-xs font-medium text-indigo-700 dark:text-indigo-300 mb-4">
        <Zap className="h-3.5 w-3.5" /> Assistente autónomo · Gemini
      </div>
      <h2 className="text-2xl font-bold mb-2">
        Diga-me o que precisa.
      </h2>
      <p className="text-sm opacity-70 mb-8">
        Analiso plantas, crio orçamentos, pesquiso normas PT, estimo custos.
        Em Português Europeu, sempre.
      </p>
      <div className="grid gap-2 sm:grid-cols-2">
        {sugestoes.map((s, i) => (
          <SugestaoCartao key={i} texto={s} />
        ))}
      </div>
    </div>
  );
}

function SugestaoCartao({ texto }) {
  return (
    <div
      className="text-left text-sm rounded-lg border border-slate-200 dark:border-slate-700 p-3 bg-white/50 dark:bg-slate-900/50 hover:bg-white dark:hover:bg-slate-800 cursor-pointer transition"
      data-testid="btp-sugestao"
      onClick={() => {
        const input = document.querySelector('[data-testid="btp-prompt-input"]');
        if (input) {
          input.value = texto;
          input.focus();
          const ev = new Event("input", { bubbles: true });
          input.dispatchEvent(ev);
        }
      }}
    >
      “{texto}”
    </div>
  );
}

function AnexoChip({ anexo, onRemover }) {
  const Icone = anexo.mime_type?.startsWith("image/") ? ImageIcon : FileText;
  const kb = Math.round((anexo.size || 0) / 1024);
  return (
    <div className="flex items-center gap-2 bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-md px-2 py-1 text-xs">
      <Icone className="h-3.5 w-3.5" />
      <span className="max-w-[160px] truncate">{anexo.filename}</span>
      <span className="opacity-60">{kb} KB</span>
      <button
        type="button"
        className="hover:text-red-600"
        onClick={onRemover}
        data-testid="btp-anexo-remover"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}


function MensagemBubble({ mensagem, onNavegar, onResponderMissing, sending }) {
  if (mensagem.role === "user") {
    return (
      <div className="flex flex-col items-end gap-1">
        <div className="btp-bubble btp-bubble--user">
          {mensagem.text}
        </div>
        {mensagem.anexos_meta?.length > 0 && (
          <div className="flex gap-2 flex-wrap">
            {mensagem.anexos_meta.map((a, i) => (
              <span key={i} className="text-[11px] opacity-70">
                📎 {a.filename}
              </span>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col items-start gap-2">
      {/* Pills de thinking / tools */}
      {mensagem.pills?.length > 0 && (
        <div className="flex gap-2 flex-wrap">
          {mensagem.pills.map((p, i) => {
            const Icone = p.icone || Sparkles;
            const cls = p.estado === "done" ? "btp-pill btp-pill--done"
                      : p.estado === "erro" ? "btp-pill btp-pill--error"
                      : "btp-pill";
            return (
              <span key={i} className={cls} title={p.mensagem || ""}>
                <Icone className="h-3 w-3" />
                {p.nome}
              </span>
            );
          })}
        </div>
      )}

      {/* Markdown */}
      {mensagem.text && (
        <div className="btp-bubble btp-bubble--agent prose prose-sm max-w-none dark:prose-invert">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeHighlight]}
          >
            {mensagem.text}
          </ReactMarkdown>
        </div>
      )}

      {/* Navigate button */}
      {mensagem.navigate?.url && (
        <Button
          size="sm"
          variant="secondary"
          onClick={() => onNavegar(mensagem.navigate.url)}
          className="gap-2"
          data-testid="btp-navigate-btn"
        >
          Abrir {mensagem.navigate.url} <ArrowRight className="h-4 w-4" />
        </Button>
      )}

      {/* Missing data cards */}
      {mensagem.missing?.map((md, i) => (
        <MissingDataCard
          key={i}
          pedido={md}
          onResponder={onResponderMissing}
          pending={sending}
        />
      ))}

      {/* Meta (modo + modelo) */}
      {mensagem.meta?.mode && (
        <div className="text-[10px] opacity-50 px-2">
          {mensagem.meta.mode} · {mensagem.meta.model}
          {mensagem.meta.duracao != null && ` · ${mensagem.meta.duracao}s`}
        </div>
      )}
    </div>
  );
}
