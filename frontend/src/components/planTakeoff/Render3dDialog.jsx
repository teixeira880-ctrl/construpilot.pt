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
  structure, dalleEp, voileEp, wallHeight,
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
          <DialogTitle>Convertir le plan 2D en 3D</DialogTitle>
          <DialogDescription>
            Trois modes : <b>IA</b> pour un rendu photo-réaliste (Nano Banana),
            <b> Interactif</b> pour une maquette 3D navigable, ou
            <b> Vidéo</b> pour un mini-tour multi-styles à joindre au devis.
          </DialogDescription>
        </DialogHeader>

        {credits3d && (
          <div className="text-xs border border-border rounded-sm p-2 bg-secondary/30 flex flex-wrap gap-x-4 gap-y-1"
               data-testid="credits-3d-counter">
            {unlimited ? (
              <span className="text-primary font-semibold">✓ Rendus, vidéos et maquettes illimités (Pro / Pro Business)</span>
            ) : (
              <>
                <span data-testid="credits-free-render">🎁 Rendus offerts restants : <b>{credits3d.free_render_remaining ?? 0}</b></span>
                <span>Crédits — rendu : <b>{creditFor("render")}</b> · vidéo : <b>{creditFor("video")}</b> · maquette : <b>{creditFor("mockup")}</b></span>
                <span className="text-muted-foreground">Tarifs à l'unité : rendu 5 € · vidéo 10 € · maquette 5 €</span>
              </>
            )}
          </div>
        )}

        {creditPaywall && (
          <div className="border border-primary/50 bg-primary/5 rounded-sm p-4 space-y-3 text-center"
               data-testid="credit-paywall">
            <p className="font-display font-bold">{creditPaywall.message}</p>
            <p className="text-xs text-muted-foreground">
              Paiement unique sécurisé. Le crédit est ajouté à votre compte dès le paiement validé.
            </p>
            <div className="flex gap-2 justify-center">
              <Button variant="outline" className="rounded-sm"
                      onClick={() => setCreditPaywall(null)}>Annuler</Button>
              <Button className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white"
                      data-testid="credit-buy-btn"
                      onClick={() => buyCredit(creditPaywall.credit_plan_id)}>
                Acheter ({Number(creditPaywall.price_eur).toFixed(0)} €)
              </Button>
            </div>
          </div>
        )}

        <div className="flex gap-2 border-b border-border pb-2 flex-wrap">
          <Button size="sm" variant={render3dMode === "ai" ? "default" : "ghost"}
                  onClick={() => setRender3dMode("ai")}
                  data-testid="render-3d-mode-ai"
                  className={`rounded-sm gap-1 ${render3dMode === "ai" ? "bg-primary text-white hover:bg-orange-600" : ""}`}>
            <Sparkles className="h-3 w-3" /> Rendu IA
          </Button>
          <Button size="sm" variant={render3dMode === "interactive" ? "default" : "ghost"}
                  onClick={() => (onInteractiveMode ? onInteractiveMode() : setRender3dMode("interactive"))}
                  data-testid="render-3d-mode-interactive"
                  className={`rounded-sm gap-1 ${render3dMode === "interactive" ? "bg-primary text-white hover:bg-orange-600" : ""}`}>
            <Sparkles className="h-3 w-3" /> Maquette interactive
          </Button>
          <Button size="sm" variant={render3dMode === "video" ? "default" : "ghost"}
                  onClick={() => setRender3dMode("video")}
                  data-testid="render-3d-mode-video"
                  className={`rounded-sm gap-1 ${render3dMode === "video" ? "bg-primary text-white hover:bg-orange-600" : ""}`}>
            <Film className="h-3 w-3" /> Tour vidéo
          </Button>
        </div>

        {render3dMode === "interactive" && (
          <Interactive3D
            rooms={plan?.rooms || []}
            walls={detectedWalls?.segments || []}
            structure={structure || null}
            dalleEpM={dalleEp ?? 0.2}
            voileEpM={voileEp ?? 0.2}
            wallHeightM={wallHeight ?? 2.5}
            scaleMperPx={plan?.calibrations?.[pageIndex]?.scale_m_per_px || 0.01}
            imageHeight={520}
          />
        )}

        {render3dMode === "ai" && (
          <div className="grid gap-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-1">
                <Label className="text-xs">Style de rendu</Label>
                <Select value={render3dStyle} onValueChange={setRender3dStyle}>
                  <SelectTrigger data-testid="render-3d-style" className="rounded-sm h-10">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="isometric">Isométrique (dessus, coloré)</SelectItem>
                    <SelectItem value="photoreal">Photoréaliste (rendu matériaux)</SelectItem>
                    <SelectItem value="axonometric">Axonométrique (murs en coupe)</SelectItem>
                    <SelectItem value="interior">Vue intérieur (salon principal)</SelectItem>
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
                  <span className="text-sm">Ajouter du mobilier</span>
                </label>
              </div>
            </div>

            {!render3dImg && !render3dBusy && (
              <Button onClick={runRender3d} disabled={render3dBusy}
                      data-testid="render-3d-run-btn"
                      className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                <Sparkles className="h-4 w-4" />
                Générer le rendu 3D
              </Button>
            )}
            {render3dBusy && (
              <div className="border border-primary/40 bg-primary/5 rounded-sm p-8 text-center space-y-3">
                <Sparkles className="h-10 w-10 mx-auto text-primary animate-pulse" />
                <p className="font-display font-bold">L'IA génère votre rendu 3D…</p>
                <p className="text-xs text-muted-foreground">
                  Cela prend 30-60 secondes. Ne fermez pas la fenêtre.
                </p>
              </div>
            )}
            {render3dImg && !render3dBusy && (
              <div className="space-y-3" data-testid="render-3d-result">
                <img src={render3dImg} alt="Rendu 3D"
                     className="w-full rounded-sm border border-border" />
                <div className="flex gap-2 justify-end">
                  <Button variant="outline" onClick={runRender3d} disabled={render3dBusy}
                          data-testid="render-3d-redo-btn"
                          className="rounded-sm gap-2">
                    <Sparkles className="h-3 w-3" /> Régénérer
                  </Button>
                  <Button onClick={downloadRender3d} data-testid="render-3d-download-btn"
                          className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                    <FileDown className="h-4 w-4" /> Télécharger
                  </Button>
                </div>
              </div>
            )}

            {render3dHistory.length > 0 && (
              <div className="border border-border rounded-sm p-3">
                <p className="overline mb-2">Rendus précédents ({render3dHistory.length})</p>
                <div className="flex flex-wrap gap-1">
                  {render3dHistory.slice().reverse().map(r => (
                    <button key={r.render_id}
                            onClick={() => openRender3dHistory(r.render_id)}
                            data-testid={`render-3d-history-${r.render_id}`}
                            className="text-[10px] px-2 py-1 border border-border rounded-sm
                                       hover:bg-primary/10 hover:border-primary">
                      {r.style} · {new Date(r.created_at).toLocaleDateString("fr-FR")}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <p className="text-[11px] text-muted-foreground border border-border p-2 rounded-sm bg-secondary/30">
              💡 Astuce : essayez d'abord <b>Isométrique</b> pour un rendu global,
              puis <b>Vue intérieur</b> pour immerger votre client dans le salon.
            </p>
          </div>
        )}

        {render3dMode === "video" && (
          <div className="grid gap-4" data-testid="render-video-panel">
            <p className="text-xs text-muted-foreground border border-primary/30 p-3 rounded-sm bg-primary/5">
              Génère 4 rendus IA du plan (isométrique, photoréaliste, axonométrique, intérieur)
              et les assemble en une vidéo MP4 de 20 secondes à joindre à votre devis.
              Effet <b>wow</b> garanti auprès de vos clients.
            </p>

            <div className="grid grid-cols-2 gap-2">
              <label className="flex items-center gap-2 h-10 px-3 border border-border rounded-sm cursor-pointer bg-secondary/30"
                     data-testid="video-watermark-toggle">
                <input type="checkbox" checked={videoAddWatermark}
                       onChange={(e) => setVideoAddWatermark(e.target.checked)}
                       className="accent-primary h-4 w-4" />
                <span className="text-xs">Filigrane logo (branding)</span>
              </label>
              <label className="flex items-center gap-2 h-10 px-3 border border-border rounded-sm cursor-pointer bg-secondary/30"
                     data-testid="video-music-toggle">
                <input type="checkbox" checked={videoAddMusic}
                       onChange={(e) => setVideoAddMusic(e.target.checked)}
                       className="accent-primary h-4 w-4" />
                <span className="text-xs">Musique d'ambiance</span>
              </label>
            </div>

            {!videoUrl && !videoBusy && (
              <Button onClick={runRenderVideo} disabled={videoBusy}
                      data-testid="render-video-run-btn"
                      className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                <Film className="h-4 w-4" />
                Générer le tour vidéo 3D
              </Button>
            )}
            {videoBusy && (
              <div className="border border-primary/40 bg-primary/5 rounded-sm p-8 text-center space-y-3">
                <Film className="h-10 w-10 mx-auto text-primary animate-pulse" />
                <p className="font-display font-bold">Assemblage de votre tour vidéo…</p>
                <p className="text-xs text-muted-foreground">
                  4 rendus IA + montage MP4 · 2 à 4 minutes. Ne fermez pas la fenêtre.
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
                    <Film className="h-3 w-3" /> Régénérer
                  </Button>
                  <Button onClick={downloadVideo} data-testid="render-video-download-btn"
                          className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                    <FileDown className="h-4 w-4" /> Télécharger MP4
                  </Button>
                </div>
              </div>
            )}

            {videoHistory.length > 0 && (
              <div className="border border-border rounded-sm p-3">
                <p className="overline mb-2">Vidéos précédentes ({videoHistory.length})</p>
                <div className="flex flex-wrap gap-1">
                  {videoHistory.slice().reverse().map(v => (
                    <button key={v.video_id}
                            onClick={() => openVideoHistory(v.video_id)}
                            data-testid={`render-video-history-${v.video_id}`}
                            className="text-[10px] px-2 py-1 border border-border rounded-sm
                                       hover:bg-primary/10 hover:border-primary">
                      {new Date(v.created_at).toLocaleDateString("fr-FR")} · {v.duration_s}s
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} className="rounded-sm">
            Fermer
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
