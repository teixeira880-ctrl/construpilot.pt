import { Sparkles, FileDown, Film } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Interactive3D } from "@/components/Interactive3D";

/**
 * Dialog : Rendu 3D IA (Nano Banana), maquette Three.js interactive, ET tour vidéo 3D.
 */
export function Render3dDialog({
  open, onOpenChange,
  render3dMode, setRender3dMode,
  plan, detectedWalls, pageIndex,
  structure, dalleEp, voileEp, wallHeight, poutreL, poutreH, onAttach3d,
  render3dStyle, setRender3dStyle,
  render3dFurniture, setRender3dFurniture,
  render3dBusy, render3dImg,
  runRender3d, downloadRender3d,
  render3dHistory, openRender3dHistory,
  // Vidéo tour
  videoBusy, videoUrl,
  runRenderVideo, downloadVideo,
  videoHistory, openVideoHistory,
  videoAddWatermark, setVideoAddWatermark,
  videoAddMusic, setVideoAddMusic,
  credits3d, creditPaywall, setCreditPaywall, buyCredit, onInteractiveMode,
}) {
  const unlimited = credits3d?.unlimited;
  const creditFor = (k) => credits3d?.credits?.[k] ?? 0;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="rounded-sm max-w-4xl max-h-[90vh] overflow-y-auto"
                      data-testid="render-3d-dialog">
        <DialogHeader>
          <DialogTitle>Converter a planta 2D em 3D</DialogTitle>
          <DialogDescription>
            Três modos: <b>IA</b> para uma renderização fotorrealista (Nano Banana),
            <b> Interativo</b> para uma maquete 3D navegável, ou
            <b> Vídeo</b> para um mini-tour multi-estilos a anexar ao orçamento.
          </DialogDescription>
        </DialogHeader>

        {credits3d && (
          <div className="text-xs border border-border rounded-sm p-2 bg-secondary/30 flex flex-wrap gap-x-4 gap-y-1"
               data-testid="credits-3d-counter">
            {unlimited ? (
              <span className="text-primary font-semibold">✓ Renders, vídeos e maquetes ilimitados (Pro / Pro Business)</span>
            ) : (
              <>
                <span data-testid="credits-free-render">🎁 Renders oferecidos restantes: <b>{credits3d.free_render_remaining ?? 0}</b></span>
                <span>Créditos — renderização: <b>{creditFor("render")}</b> · vídeo: <b>{creditFor("video")}</b> · maquete : <b>{creditFor("mockup")}</b></span>
                <span className="text-muted-foreground">Preços unitários: render 5 € · vídeo 10 € · maqueta 5 €</span>
              </>
            )}
          </div>
        )}

        {creditPaywall && (
          <div className="border border-primary/50 bg-primary/5 rounded-sm p-4 space-y-3 text-center"
               data-testid="credit-paywall">
            <p className="font-display font-bold">{creditPaywall.message}</p>
            <p className="text-xs text-muted-foreground">
              Pagamento único seguro. O crédito é adicionado à sua conta assim que o pagamento for validado.
            </p>
            <div className="flex gap-2 justify-center">
              <Button variant="outline" className="rounded-sm"
                      onClick={() => setCreditPaywall(null)}>Cancelar</Button>
              <Button className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white"
                      data-testid="credit-buy-btn"
                      onClick={() => buyCredit(creditPaywall.credit_plan_id)}>
                Comprar ({Number(creditPaywall.price_eur).toFixed(0)} €)
              </Button>
            </div>
          </div>
        )}

        <div className="flex gap-2 border-b border-border pb-2 flex-wrap">
          <Button size="sm" variant={render3dMode === "ai" ? "default" : "ghost"}
                  onClick={() => setRender3dMode("ai")}
                  data-testid="render-3d-mode-ai"
                  className={`rounded-sm gap-1 ${render3dMode === "ai" ? "bg-primary text-white hover:bg-orange-600" : ""}`}>
            <Sparkles className="h-3 w-3" /> Renderização IA
          </Button>
          <Button size="sm" variant={render3dMode === "interactive" ? "default" : "ghost"}
                  onClick={() => (onInteractiveMode ? onInteractiveMode() : setRender3dMode("interactive"))}
                  data-testid="render-3d-mode-interactive"
                  className={`rounded-sm gap-1 ${render3dMode === "interactive" ? "bg-primary text-white hover:bg-orange-600" : ""}`}>
            <Sparkles className="h-3 w-3" /> Maqueta interativa
          </Button>
          <Button size="sm" variant={render3dMode === "video" ? "default" : "ghost"}
                  onClick={() => setRender3dMode("video")}
                  data-testid="render-3d-mode-video"
                  className={`rounded-sm gap-1 ${render3dMode === "video" ? "bg-primary text-white hover:bg-orange-600" : ""}`}>
            <Film className="h-3 w-3" /> Tour vídeo
          </Button>
        </div>

        {render3dMode === "interactive" && (
          <Interactive3D
            rooms={plan?.rooms || []}
            walls={detectedWalls?.segments || []}
            structure={structure || null}
            dalleEpM={dalleEp ?? 0.2}
            voileEpM={voileEp ?? 0.2}
            poutreLM={poutreL ?? 0.2}
            poutreHM={poutreH ?? 0.4}
            wallHeightM={wallHeight ?? 2.5}
            scaleMperPx={plan?.calibrations?.[pageIndex]?.scale_m_per_px || 0.01}
            imageHeight={520}
            onAttach={onAttach3d}
          />
        )}

        {render3dMode === "ai" && (
          <div className="grid gap-4">
            <div className="flex items-start gap-2 border border-amber-300/60 bg-amber-50 text-amber-900 rounded-sm p-3 text-xs"
                 data-testid="render-3d-ai-hint">
              <Sparkles className="h-4 w-4 shrink-0 mt-0.5" />
              <p>
                Le <strong>Renderização IA</strong> produz uma imagem colorida vista de cima (ilustração). Para uma
                <strong> vraie 3D navigable</strong> (paredes em volume, órbita, zoom, altura ajustável), utilize a{" "}
                <button type="button" className="underline font-semibold hover:text-amber-700"
                        data-testid="render-3d-ai-hint-interactive"
                        onClick={() => (onInteractiveMode ? onInteractiveMode() : setRender3dMode("interactive"))}>
                  Maqueta interativa
                </button>.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-1">
                <Label className="text-xs">Estilo de visualização</Label>
                <Select value={render3dStyle} onValueChange={setRender3dStyle}>
                  <SelectTrigger data-testid="render-3d-style" className="rounded-sm h-10">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="isometric">Isométrico (de cima, colorido)</SelectItem>
                    <SelectItem value="photoreal">Fotorrealista (renderização materiais)</SelectItem>
                    <SelectItem value="axonometric">Axonométrico (paredes em corte)</SelectItem>
                    <SelectItem value="interior">Vista interior (sala principal)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-1">
                <Label className="text-xs opacity-0">.</Label>
                <label className="flex items-center gap-2 h-10 px-3 border border-border rounded-sm cursor-pointer bg-secondary/30"
                       data-testid="render-3d-furniture-toggle">
                  <input type="checkbox" checked={render3dFurniture}
                         onChange={(e) => setRender3dFurniture(e.target.checked)}
                         className="accent-primary h-4 w-4" />
                  <span className="text-sm">Adicionar mobiliário</span>
                </label>
              </div>
            </div>

            {!render3dImg && !render3dBusy && (
              <Button onClick={runRender3d} disabled={render3dBusy}
                      data-testid="render-3d-run-btn"
                      className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                <Sparkles className="h-4 w-4" />
                Gerar a renderização 3D
              </Button>
            )}
            {render3dBusy && (
              <div className="border border-primary/40 bg-primary/5 rounded-sm p-8 text-center space-y-3">
                <Sparkles className="h-10 w-10 mx-auto text-primary animate-pulse" />
                <p className="font-display font-bold">A IA gera a sua renderização 3D…</p>
                <p className="text-xs text-muted-foreground">
                  Isto demora 30-60 segundos. Não feche a janela.
                </p>
              </div>
            )}
            {render3dImg && !render3dBusy && (
              <div className="space-y-3" data-testid="render-3d-result">
                <img src={render3dImg} alt="Renderização 3D"
                     className="w-full rounded-sm border border-border" />
                <div className="flex gap-2 justify-end">
                  <Button variant="outline" onClick={runRender3d} disabled={render3dBusy}
                          data-testid="render-3d-redo-btn"
                          className="rounded-sm gap-2">
                    <Sparkles className="h-3 w-3" /> Regenerar
                  </Button>
                  <Button onClick={downloadRender3d} data-testid="render-3d-download-btn"
                          className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                    <FileDown className="h-4 w-4" /> Descarregar
                  </Button>
                </div>
              </div>
            )}

            {render3dHistory.length > 0 && (
              <div className="border border-border rounded-sm p-3">
                <p className="overline mb-2">Renderizações anteriores ({render3dHistory.length})</p>
                <div className="flex flex-wrap gap-1">
                  {render3dHistory.slice().reverse().map(r => (
                    <button key={r.render_id}
                            onClick={() => openRender3dHistory(r.render_id)}
                            data-testid={`render-3d-history-${r.render_id}`}
                            className="text-[10px] px-2 py-1 border border-border rounded-sm
                                       hover:bg-primary/10 hover:border-primary">
                      {r.style} · {new Date(r.created_at).toLocaleDateString("pt-PT")}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <p className="text-[11px] text-muted-foreground border border-border p-2 rounded-sm bg-secondary/30">
              💡 Dica: experimente primeiro <b>Isométrico</b> para uma renderização global, depois <b>Vista interior</b> para imergir o seu cliente na sala.
            </p>
          </div>
        )}

        {render3dMode === "video" && (
          <div className="grid gap-4" data-testid="render-video-panel">
            <p className="text-xs text-muted-foreground border border-primary/30 p-3 rounded-sm bg-primary/5">
              Gera 4 renders IA da planta (isométrico, fotorrealista, axonométrico, interior) e junta-os num vídeo MP4 de 20 segundos para anexar ao seu orçamento. Um render visual para juntar aos orçamentos dos clientes.
            </p>

            <div className="grid grid-cols-2 gap-2">
              <label className="flex items-center gap-2 h-10 px-3 border border-border rounded-sm cursor-pointer bg-secondary/30"
                     data-testid="video-watermark-toggle">
                <input type="checkbox" checked={videoAddWatermark}
                       onChange={(e) => setVideoAddWatermark(e.target.checked)}
                       className="accent-primary h-4 w-4" />
                <span className="text-xs">Marca de água logótipo (imagem de marca)</span>
              </label>
              <label className="flex items-center gap-2 h-10 px-3 border border-border rounded-sm cursor-pointer bg-secondary/30"
                     data-testid="video-music-toggle">
                <input type="checkbox" checked={videoAddMusic}
                       onChange={(e) => setVideoAddMusic(e.target.checked)}
                       className="accent-primary h-4 w-4" />
                <span className="text-xs">Música ambiente</span>
              </label>
            </div>

            {!videoUrl && !videoBusy && (
              <Button onClick={runRenderVideo} disabled={videoBusy}
                      data-testid="render-video-run-btn"
                      className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                <Film className="h-4 w-4" />
                Gerar o tour vídeo 3D
              </Button>
            )}
            {videoBusy && (
              <div className="border border-primary/40 bg-primary/5 rounded-sm p-8 text-center space-y-3">
                <Film className="h-10 w-10 mx-auto text-primary animate-pulse" />
                <p className="font-display font-bold">Montagem do seu tour vídeo…</p>
                <p className="text-xs text-muted-foreground">
                  4 imagens IA + montagem MP4 · 2 a 4 minutos. Não feche a janela.
                </p>
              </div>
            )}
            {videoUrl && !videoBusy && (
              <div className="space-y-3" data-testid="render-video-result">
                <video src={videoUrl} controls autoPlay loop muted
                       className="w-full rounded-sm border border-border bg-black" />
                <div className="flex gap-2 justify-end">
                  <Button variant="outline" onClick={runRenderVideo} disabled={videoBusy}
                          data-testid="render-video-redo-btn"
                          className="rounded-sm gap-2">
                    <Film className="h-3 w-3" /> Regenerar
                  </Button>
                  <Button onClick={downloadVideo} data-testid="render-video-download-btn"
                          className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                    <FileDown className="h-4 w-4" /> Descarregar MP4
                  </Button>
                </div>
              </div>
            )}

            {videoHistory.length > 0 && (
              <div className="border border-border rounded-sm p-3">
                <p className="overline mb-2">Vídeos anteriores ({videoHistory.length})</p>
                <div className="flex flex-wrap gap-1">
                  {videoHistory.slice().reverse().map(v => (
                    <button key={v.video_id}
                            onClick={() => openVideoHistory(v.video_id)}
                            data-testid={`render-video-history-${v.video_id}`}
                            className="text-[10px] px-2 py-1 border border-border rounded-sm
                                       hover:bg-primary/10 hover:border-primary">
                      {new Date(v.created_at).toLocaleDateString("pt-PT")} · {v.duration_s}s
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} className="rounded-sm">
            Fechar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
