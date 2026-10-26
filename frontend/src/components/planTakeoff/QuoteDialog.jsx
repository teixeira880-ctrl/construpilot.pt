import { FileDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

/**
 * Devis dialog extrait de PlanTakeoff pour maintenabilité.
 * Reçoit tous les états et callbacks via props (état géré par le parent).
 */
export function QuoteDialog({
  open, onOpenChange,
  quoteMode, setQuoteMode,
  templates, applyTemplate, deleteTemplate,
  quoteFinish, setQuoteFinish,
  quoteFloor, setQuoteFloor,
  quoteSubject, setQuoteSubject,
  quoteIntro, setQuoteIntro,
  quoteClientEmail, setQuoteClientEmail,
  quoteClientName, setQuoteClientName,
  quoteClientAddress, setQuoteClientAddress,
  quoteMessage, setQuoteMessage,
  quoteIncludeTva, setQuoteIncludeTva,
  quoteAttachVideo, setQuoteAttachVideo,
  latestVideo,
  quoteSends, createSignatureLink,
  templateName, setTemplateName,
  templateShared, setTemplateShared,
  saveTemplate,
  quoteBusy, downloadQuotePdf, sendQuotePdf,
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="rounded-sm max-w-md" data-testid="quote-dialog">
        <DialogHeader>
          <DialogTitle>
            {quoteMode === "send" ? "Enviar o orçamento por email" : "Gerar um orçamento PDF"}
          </DialogTitle>
          <DialogDescription>
            O orçamento retoma automaticamente as áreas medidas e aplica a mão de obra & os preços médios de materiais de referência 2026.
          </DialogDescription>
        </DialogHeader>
        <div className="flex gap-2 border-b border-border pb-2">
          <Button size="sm" variant={quoteMode === "download" ? "default" : "ghost"}
                  onClick={() => setQuoteMode("download")}
                  data-testid="quote-mode-download"
                  className={`rounded-sm gap-1 ${quoteMode === "download" ? "bg-primary text-white hover:bg-orange-600" : ""}`}>
            <FileDown className="h-3 w-3" /> Descarregar
          </Button>
          <Button size="sm" variant={quoteMode === "send" ? "default" : "ghost"}
                  onClick={() => setQuoteMode("send")}
                  data-testid="quote-mode-send"
                  className={`rounded-sm gap-1 ${quoteMode === "send" ? "bg-primary text-white hover:bg-orange-600" : ""}`}>
            Enviar ao cliente
          </Button>
        </div>

        {templates.length > 0 && (
          <div className="border border-border rounded-sm p-3 bg-secondary/30" data-testid="templates-picker">
            <p className="overline mb-2">Modelos de orçamento</p>
            <div className="flex flex-wrap gap-1">
              {templates.map(t => (
                <div key={t.template_id}
                     className="flex items-center bg-background border border-border rounded-sm text-[10px]">
                  <button onClick={() => applyTemplate(t)}
                          data-testid={`apply-template-${t.template_id}`}
                          className="px-2 py-1 hover:bg-primary/10 flex items-center gap-1">
                    {t.organization_id && <span className="text-primary">◈</span>}
                    {t.name}
                    <span className="text-muted-foreground">
                      · {t.finish} · {t.floor_material}
                    </span>
                  </button>
                  {t.user_id && (
                    <button onClick={() => deleteTemplate(t.template_id)}
                            data-testid={`delete-template-${t.template_id}`}
                            className="px-1.5 py-1 text-muted-foreground hover:text-destructive border-l border-border">
                      ×
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label>Gama de acabamento</Label>
            <Select value={quoteFinish} onValueChange={setQuoteFinish}>
              <SelectTrigger data-testid="quote-finish-select" className="rounded-sm h-11">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="eco">Eco (orçamento reduzido)</SelectItem>
                <SelectItem value="std">Standard (recomendado)</SelectItem>
                <SelectItem value="premium">Premium (topo de gama)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label>Material do pavimento</Label>
            <Select value={quoteFloor} onValueChange={setQuoteFloor}>
              <SelectTrigger data-testid="quote-floor-select" className="rounded-sm h-11">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="carrelage">Revestimento cerâmico</SelectItem>
                <SelectItem value="parquet">Soalho</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {quoteMode === "send" && (
            <>
              <div className="grid gap-2">
                <Label>Assunto email (opcional)</Label>
                <Input value={quoteSubject} onChange={(e) => setQuoteSubject(e.target.value)}
                       placeholder="Ex: O seu orçamento para a renovação do apartamento em Lisboa"
                       maxLength={180}
                       data-testid="quote-subject-input" className="rounded-sm h-11" />
                <p className="text-[10px] text-muted-foreground">
                  Vazio → « Orçamento · {`{société}`} ». Personalize para um resultado mais profissional.
                </p>
              </div>
              <div className="grid gap-2">
                <Label>Introdução personalizada (opcional)</Label>
                <textarea value={quoteIntro} onChange={(e) => setQuoteIntro(e.target.value)}
                       placeholder="Na sequência da nossa conversa telefónica, segue a nossa proposta detalhada para..."
                       rows={2} maxLength={500}
                       data-testid="quote-intro-input"
                       className="rounded-sm text-sm p-2 border border-border bg-background" />
              </div>
              <div className="grid gap-2">
                <Label>Email do cliente *</Label>
                <Input value={quoteClientEmail} onChange={(e) => setQuoteClientEmail(e.target.value)}
                       placeholder="client@exemple.fr" type="email"
                       data-testid="quote-client-email" className="rounded-sm h-11" />
              </div>
              <div className="grid gap-2">
                <Label>Nome do cliente (opcional)</Label>
                <Input value={quoteClientName} onChange={(e) => setQuoteClientName(e.target.value)}
                       placeholder="Sr. Silva"
                       data-testid="quote-client-name" className="rounded-sm h-11" />
              </div>
              <div className="grid gap-2">
                <Label>
                  Morada do cliente{quoteIncludeTva && <span className="text-primary"> *</span>}
                </Label>
                <textarea value={quoteClientAddress} onChange={(e) => setQuoteClientAddress(e.target.value)}
                       placeholder="Rua Augusta, 12 — 1100-053 Lisboa"
                       rows={2} maxLength={200}
                       data-testid="quote-client-address"
                       className="rounded-sm text-sm p-2 border border-border bg-background" />
              </div>
              <div className="grid gap-2">
                <Label>Mensagem complementar (opcional)</Label>
                <textarea value={quoteMessage} onChange={(e) => setQuoteMessage(e.target.value)}
                       placeholder="Ficamos disponíveis para qualquer questão..."
                       rows={2} maxLength={500}
                       data-testid="quote-message"
                       className="rounded-sm text-sm p-2 border border-border bg-background" />
              </div>
              <label className="flex items-start gap-2 p-3 border border-primary/40 rounded-sm bg-primary/5 cursor-pointer"
                     data-testid="quote-tva-toggle">
                <input type="checkbox" checked={quoteIncludeTva}
                       onChange={(e) => setQuoteIncludeTva(e.target.checked)}
                       data-testid="quote-tva-checkbox"
                       className="accent-primary h-4 w-4 mt-0.5" />
                <div className="flex-1">
                  <p className="text-xs font-bold">Anexar a declaração de IVA a taxa reduzida (6 %)</p>
                  <p className="text-[10px] text-muted-foreground mt-1">
                    Necessária para beneficiar da taxa de 6 % nas empreitadas de reabilitação de habitação (verba 2.27 da Lista I do CIVA). O cliente assina-a e devolve-lha antes da faturação.
                  </p>
                </div>
              </label>

              {/* Auto-attach latest 3D tour video */}
              {latestVideo && (
                <label className="flex items-start gap-2 p-3 border border-primary/40 rounded-sm bg-primary/5 cursor-pointer"
                       data-testid="quote-video-toggle">
                  <input type="checkbox" checked={quoteAttachVideo}
                         onChange={(e) => setQuoteAttachVideo(e.target.checked)}
                         data-testid="quote-video-checkbox"
                         className="accent-primary h-4 w-4 mt-0.5" />
                  <div className="flex-1">
                    <p className="text-xs font-bold">
                      🎬 Anexar o tour vídeo 3D ({(latestVideo.size_bytes / 1024 / 1024).toFixed(1)} MB)
                    </p>
                    <p className="text-[10px] text-muted-foreground mt-1">
                      {latestVideo.duration_s}s · Estilos : {(latestVideo.styles || []).join(", ") || "—"}
                      {latestVideo.has_watermark && " · com marca de água"}
                      {latestVideo.has_audio && " · com música"}
                    </p>
                  </div>
                </label>
              )}
              <p className="text-[11px] text-muted-foreground border border-border p-2 rounded-sm">
                Uma cópia será enviada para o seu endereço para registo. O envio fica registado no histórico.
              </p>

              {quoteSends.length > 0 && (
                <div className="border border-border rounded-sm p-3" data-testid="sends-history">
                  <p className="overline mb-2">Histórico de envios ({quoteSends.length})</p>
                  <div className="grid gap-1 max-h-40 overflow-y-auto">
                    {quoteSends.map(s => (
                      <div key={s.log_id}
                           className="text-[10px] flex items-center justify-between border-b border-border py-1"
                           data-testid={`send-log-${s.log_id}`}>
                        <div className="min-w-0">
                          <p className="font-bold truncate">{s.client_name || s.client_email}</p>
                          <p className="num text-muted-foreground">
                            {new Date(s.created_at).toLocaleDateString("pt-PT")} · {s.total_ttc?.toLocaleString("pt-PT")} € c/ IVA
                          </p>
                        </div>
                        <div className="flex gap-1 shrink-0">
                          {s.signed && (
                            <span className="bg-primary text-white px-1.5 py-0.5 rounded-sm text-[9px]"
                                  data-testid={`sign-badge-${s.log_id}`}>Assinado</span>
                          )}
                          {!s.signed && s.opened && (
                            <span className="bg-emerald-500/10 text-emerald-600 border border-emerald-500/30 px-1.5 py-0.5 rounded-sm text-[9px]"
                                  data-testid={`open-badge-${s.log_id}`}>
                              Aberto ({s.open_count || 1})
                            </span>
                          )}
                          {!s.signed && (
                            <button onClick={() => createSignatureLink(s.log_id)}
                                    data-testid={`sign-link-${s.log_id}`}
                                    className="text-primary hover:underline text-[10px]">
                              Ligação de assinatura
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}

          <div className="border border-dashed border-border rounded-sm p-3">
            <p className="overline mb-2">Guardar como modelo</p>
            <div className="flex gap-2 items-center">
              <Input value={templateName} onChange={(e) => setTemplateName(e.target.value)}
                     placeholder="Ex: Renovação T3 standard"
                     maxLength={80}
                     data-testid="template-name-input"
                     className="rounded-sm h-9 text-xs" />
              <Button size="sm" onClick={saveTemplate} disabled={!templateName.trim()}
                      data-testid="template-save-btn"
                      className="rounded-sm hover:bg-orange-600 hover:text-white">
                Guardar
              </Button>
            </div>
            <label className="flex items-center gap-1 text-[10px] mt-2 cursor-pointer text-muted-foreground">
              <input type="checkbox" checked={templateShared}
                     onChange={(e) => setTemplateShared(e.target.checked)}
                     data-testid="template-shared-checkbox"
                     className="accent-primary h-3 w-3" />
              Partilhar com toda a minha equipa (organização)
            </label>
          </div>

          <p className="text-xs text-muted-foreground border border-border p-3 rounded-sm bg-secondary/30">
            Incluído por omissão: pladur/estuque, pintura, pavimento, rodapés. IVA a 6 % (reabilitação de habitação, verba 2.27 CIVA).
          </p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} className="rounded-sm">
            Cancelar
          </Button>
          {quoteMode === "download" ? (
            <Button onClick={downloadQuotePdf} disabled={quoteBusy} data-testid="quote-download-btn"
                    className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
              <FileDown className="h-4 w-4" />
              {quoteBusy ? "Geração…" : "Descarregar"}
            </Button>
          ) : (
            <Button onClick={sendQuotePdf} disabled={quoteBusy || !quoteClientEmail}
                    data-testid="quote-send-btn"
                    className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
              {quoteBusy ? "A enviar…" : "Enviar ao cliente"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
