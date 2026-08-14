import { useState } from "react";
import { FileDown, FileText, Sparkles, Sheet, AlertTriangle, Mail, CalendarRange, ShoppingCart, Settings2, MailCheck, MailX, Layers, BellRing } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import PcSendDialog from "@/components/planTakeoff/PcSendDialog";
import PcSettingsDialog from "@/components/planTakeoff/PcSettingsDialog";
import PcGantt from "@/components/planTakeoff/PcGantt";
import { eur, num } from "@/lib/api";

const RULES_LABELS = [
  "Semelles filantes 60 × 30 cm (périmètre + refends porteurs)",
  "Dalle / plancher ép. 15 cm",
  "Murs brique isobrique ép. 20 cm",
  "Escalier béton armé",
  "Aciers : semelles 15 kg/ml (3+3 HA10 + cadres HA6) · dalle 14 kg/m² (ST25C) · escalier 100 kg/m³",
];

export default function PcStudyDialog({ open, onClose, study, busy, onRun, onDownload, onDownloadXlsx, planId, onSent, onCompareSuppliers, sentReports = [], onRecompute }) {
  const [sendOpen, setSendOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [ganttStart, setGanttStart] = useState(() => new Date().toISOString().slice(0, 10));
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto" data-testid="pc-study-dialog">
        <DialogHeader>
          <DialogTitle>Étude Permis de Construire — Gros Œuvre</DialogTitle>
          <DialogDescription>
            L'IA lit le PC (texte + plans), comprend ce qui est demandé, puis calcule
            béton (m³), aciers (kg) et devis détaillé selon vos règles fixes.
          </DialogDescription>
        </DialogHeader>

        <div className="rounded-sm border border-border bg-muted/40 p-3 text-xs space-y-1">
          <p className="font-semibold">Règles appliquées :</p>
          {RULES_LABELS.map((r) => <p key={r} className="text-muted-foreground">• {r}</p>)}
        </div>

        <div className="flex gap-2 flex-wrap">
          <Button onClick={onRun} disabled={busy} data-testid="pc-study-run-btn"
                  className="rounded-sm gap-2 hover:bg-orange-600">
            <Sparkles className={`h-4 w-4 ${busy ? "animate-pulse" : ""}`} />
            {busy ? "Analyse du PC en cours… (peut prendre 1-2 min)" : study ? "Relancer l'analyse" : "Lancer l'analyse du PC"}
          </Button>
          <Button variant="outline" onClick={() => setSettingsOpen(true)} data-testid="pc-settings-open-btn"
                  className="rounded-sm gap-2">
            <Settings2 className="h-4 w-4" /> Réglages prix & équipe
          </Button>
          {study && (
            <>
              <Button variant="outline" onClick={() => onDownload("pdf", ganttStart)} data-testid="pc-study-download-pdf"
                      className="rounded-sm gap-2">
                <FileDown className="h-4 w-4" /> PDF
              </Button>
              <Button variant="outline" onClick={() => onDownload("docx", ganttStart)} data-testid="pc-study-download-docx"
                      className="rounded-sm gap-2">
                <FileText className="h-4 w-4" /> Word
              </Button>
              <Button variant="outline" onClick={onDownloadXlsx} data-testid="pc-study-download-xlsx"
                      className="rounded-sm gap-2">
                <Sheet className="h-4 w-4" /> Excel
              </Button>
              <Button variant="outline" onClick={() => setSendOpen(true)} data-testid="pc-study-send-btn"
                      className="rounded-sm gap-2 border-primary/60 text-primary hover:bg-primary hover:text-white">
                <Mail className="h-4 w-4" /> Envoyer au client
              </Button>
            </>
          )}
        </div>
        <PcSendDialog open={sendOpen} onClose={() => setSendOpen(false)}
                      planId={planId} onSent={onSent} startDate={ganttStart} />
        <PcSettingsDialog open={settingsOpen} onClose={() => setSettingsOpen(false)}
                          onSaved={() => study && onRecompute?.()} />

        {study && (
          <div className="space-y-4" data-testid="pc-study-result">
            {(!study.demandes || study.demandes.length === 0) && (
              <div className="rounded-sm border border-sky-500/40 bg-sky-500/10 p-2 text-xs text-muted-foreground"
                   data-testid="pc-study-fallback-note">
                L'IA n'a pas pu lire de texte exploitable sur ce document — les quantités
                ci-dessous sont déduites de la géométrie du plan et de valeurs estimées
                (voir la source de chaque hypothèse).
              </div>
            )}
            {study.demandes?.length > 0 && (
              <section>
                <h3 className="text-sm font-semibold mb-1">Ce que demande le permis
                  <Badge variant="outline" className="ml-2 text-[10px] rounded-sm">
                    confiance IA {Math.round((study.confidence || 0) * 100)} %
                  </Badge>
                </h3>
                <ul className="text-xs text-muted-foreground space-y-0.5">
                  {study.demandes.slice(0, 8).map((d, i) => <li key={i}>• {d}</li>)}
                </ul>
              </section>
            )}

            <section>
              <h3 className="text-sm font-semibold mb-1">Hypothèses retenues</h3>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                {[
                  ["Niveaux", study.inputs?.levels, study.input_sources?.levels],
                  ["Surface", `${num(study.inputs?.surface_m2, 1)} m²`, study.input_sources?.surface_m2],
                  ["Hauteur murs", `${num(study.inputs?.wall_height_m, 2)} m`, study.input_sources?.wall_height_m],
                  ["Périmètre", `${num(study.inputs?.perimeter_m, 1)} m`, study.input_sources?.perimeter_m],
                  ["Refends", `${num(study.inputs?.refends_m, 1)} m`, study.input_sources?.refends_m],
                  ["Ouvertures", `${study.inputs?.openings_count} u · ${num(study.inputs?.openings_area_m2, 1)} m²`, ""],
                  ["Escaliers", study.inputs?.stairs_count, ""],
                ].map(([k, v, s]) => (
                  <div key={k} className="rounded-sm border border-border p-2">
                    <p className="text-muted-foreground text-[10px]">{k}{s ? ` · ${s}` : ""}</p>
                    <p className="font-semibold num">{v}</p>
                  </div>
                ))}
              </div>
            </section>

            {(study.lots || []).map((lot) => (
              <section key={lot.lot}>
                <h3 className="text-sm font-semibold mb-1 text-primary">{lot.lot}</h3>
                <table className="w-full text-xs border border-border">
                  <thead>
                    <tr className="bg-muted text-left">
                      <th className="p-1.5">Désignation</th><th className="p-1.5">U</th>
                      <th className="p-1.5 text-right">Qté</th>
                      <th className="p-1.5 text-right">PU mat.</th>
                      <th className="p-1.5 text-right">PU MO</th>
                      <th className="p-1.5 text-right">Total HT</th>
                    </tr>
                  </thead>
                  <tbody>
                    {lot.lines.map((ln, i) => (
                      <tr key={i} className="border-t border-border align-top">
                        <td className="p-1.5">
                          <p className="font-medium">{ln.designation}</p>
                          <p className="text-[10px] text-muted-foreground">{ln.detail}</p>
                        </td>
                        <td className="p-1.5">{ln.unit}</td>
                        <td className="p-1.5 text-right num">{num(ln.qty)}</td>
                        <td className="p-1.5 text-right num">{eur(ln.pu_mat)}</td>
                        <td className="p-1.5 text-right num">{eur(ln.pu_mo)}</td>
                        <td className="p-1.5 text-right num font-semibold">{eur(ln.total)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            ))}

            <section className="rounded-sm border-2 border-primary/40 p-3 grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm"
                     data-testid="pc-study-totals">
              <div><p className="text-[10px] text-muted-foreground">Béton total</p>
                <p className="font-bold num">{num(study.totals?.beton_m3)} m³</p></div>
              <div><p className="text-[10px] text-muted-foreground">Aciers total</p>
                <p className="font-bold num">{num(study.totals?.acier_kg)} kg</p></div>
              <div><p className="text-[10px] text-muted-foreground">Briques isobrique</p>
                <p className="font-bold num">{study.totals?.briques_u} u</p></div>
              <div><p className="text-[10px] text-muted-foreground">Total HT</p>
                <p className="font-bold num">{eur(study.totals?.ht)}</p></div>
              <div><p className="text-[10px] text-muted-foreground">TVA 20 %</p>
                <p className="font-bold num">{eur(study.totals?.tva)}</p></div>
              <div><p className="text-[10px] text-muted-foreground">TOTAL TTC</p>
                <p className="font-bold num text-primary" data-testid="pc-study-total-ttc">{eur(study.totals?.ttc)}</p></div>
            </section>

            <Button variant="outline" onClick={() => onCompareSuppliers?.(study)}
                    data-testid="pc-study-compare-btn"
                    className="rounded-sm gap-2 w-full border-sky-500/60 text-sky-600 hover:bg-sky-500 hover:text-white">
              <ShoppingCart className="h-4 w-4" />
              Comparer les prix fournisseurs (briques, aciers, treillis, béton)
            </Button>

            {study.levels_breakdown?.length > 0 && (
              <section data-testid="pc-levels-breakdown">
                <h3 className="text-sm font-semibold mb-1 flex items-center gap-1.5">
                  <Layers className="h-4 w-4 text-primary" /> Quantités par niveau — pour phaser vos commandes
                </h3>
                <table className="w-full text-xs border border-border">
                  <thead>
                    <tr className="bg-muted text-left">
                      <th className="p-1.5">Niveau</th>
                      <th className="p-1.5 text-right">Béton</th>
                      <th className="p-1.5 text-right">Aciers</th>
                      <th className="p-1.5 text-right">Briques</th>
                      <th className="p-1.5 text-right">Murs</th>
                      <th className="p-1.5 text-right">Total HT</th>
                    </tr>
                  </thead>
                  <tbody>
                    {study.levels_breakdown.map((l, i) => (
                      <tr key={i} className="border-t border-border align-top" data-testid={`pc-level-${i}`}>
                        <td className="p-1.5">
                          <details>
                            <summary className="font-medium cursor-pointer select-none">{l.name}</summary>
                            <ul className="mt-1 text-[10px] text-muted-foreground space-y-0.5">
                              {l.lines.map((ln, j) => (
                                <li key={j}>• {ln.designation} — <span className="num">{num(ln.qty, 2)} {ln.unit}</span></li>
                              ))}
                            </ul>
                          </details>
                        </td>
                        <td className="p-1.5 text-right num">{num(l.beton_m3, 2)} m³</td>
                        <td className="p-1.5 text-right num">{num(l.acier_kg)} kg</td>
                        <td className="p-1.5 text-right num">{l.briques_u ? `${num(l.briques_u)} u` : "—"}</td>
                        <td className="p-1.5 text-right num">{l.murs_m2 ? `${num(l.murs_m2, 1)} m²` : "—"}</td>
                        <td className="p-1.5 text-right num font-semibold">{eur(l.ht)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="text-[10px] text-muted-foreground mt-1">
                  Cliquez sur un niveau pour voir le détail des lignes. Idéal pour commander
                  les matériaux phase par phase.
                </p>
              </section>
            )}

            {study.planning?.phases?.length > 0 && (
              <section data-testid="pc-study-planning">
                <h3 className="text-sm font-semibold mb-1 flex items-center gap-1.5">
                  <CalendarRange className="h-4 w-4 text-primary" /> Planning de chantier — gros œuvre
                  {study.custom_pricing && (
                    <Badge variant="outline" className="text-[10px] rounded-sm">prix personnalisés</Badge>
                  )}
                </h3>
                <PcGantt planning={study.planning} start={ganttStart} onStartChange={setGanttStart} />
                <table className="w-full text-xs border border-border">
                  <thead>
                    <tr className="bg-muted text-left">
                      <th className="p-1.5">Phase</th>
                      <th className="p-1.5 text-center">Jours ouvrés</th>
                      <th className="p-1.5 text-center">Séchage</th>
                      <th className="p-1.5 text-center">Début</th>
                      <th className="p-1.5 text-center">Fin</th>
                    </tr>
                  </thead>
                  <tbody>
                    {study.planning.phases.map((ph, i) => (
                      <tr key={i} className="border-t border-border" data-testid={`pc-planning-phase-${i}`}>
                        <td className="p-1.5">
                          <p className="font-medium">{ph.name}</p>
                          <p className="text-[10px] text-muted-foreground">{ph.hours} h d'équipe</p>
                        </td>
                        <td className="p-1.5 text-center num">{ph.work_days}</td>
                        <td className="p-1.5 text-center num">{ph.cure_days ? `+${ph.cure_days} j` : "—"}</td>
                        <td className="p-1.5 text-center num">J{ph.start_day}</td>
                        <td className="p-1.5 text-center num">J{ph.end_day}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="text-[11px] text-muted-foreground mt-1" data-testid="pc-planning-summary">
                  Équipe de {study.planning.crew_size} compagnons — {study.planning.total_work_days} jours
                  ouvrés + {study.planning.total_cure_days} jours de séchage béton,
                  soit ≈ <b>{study.planning.total_days} jours ({study.planning.total_weeks} semaines)</b> de chantier.
                </p>
              </section>
            )}

            {sentReports.length > 0 && (
              <section data-testid="pc-sent-list">
                <h3 className="text-sm font-semibold mb-1">Envois au client</h3>
                <div className="space-y-1">
                  {sentReports.slice(-5).reverse().map((s, i) => (
                    <div key={i} className="flex items-center justify-between gap-2 text-xs border border-border rounded-sm px-2 py-1.5"
                         data-testid={`pc-sent-${i}`}>
                      <span className="truncate">✉ {s.to_email}</span>
                      <span className="flex items-center gap-2 shrink-0">
                        <span className="num text-muted-foreground">
                          {new Date(s.sent_at).toLocaleDateString("fr-FR")}{" "}
                          {new Date(s.sent_at).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}
                        </span>
                        {s.opened ? (
                          <Badge className="rounded-sm gap-1 text-[10px] bg-emerald-500/15 text-emerald-600 border border-emerald-500/40 hover:bg-emerald-500/15"
                                 data-testid={`pc-sent-${i}-status`}>
                            <MailCheck className="h-3 w-3" />
                            Ouvert le {new Date(s.opened_at).toLocaleDateString("fr-FR")}
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="rounded-sm gap-1 text-[10px] text-muted-foreground"
                                 data-testid={`pc-sent-${i}-status`}>
                            <MailX className="h-3 w-3" /> Non ouvert
                          </Badge>
                        )}
                        {s.reminder_sent && (
                          <Badge variant="outline" className="rounded-sm gap-1 text-[10px] text-amber-600 border-amber-500/40"
                                 data-testid={`pc-sent-${i}-reminder`}>
                            <BellRing className="h-3 w-3" />
                            Relancé le {new Date(s.reminder_at).toLocaleDateString("fr-FR")}
                          </Badge>
                        )}
                      </span>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {study.warnings?.length > 0 && (
              <div className="rounded-sm border border-amber-500/40 bg-amber-500/10 p-2 text-xs">
                <p className="font-semibold flex items-center gap-1">
                  <AlertTriangle className="h-3 w-3 text-amber-500" /> Avertissements IA
                </p>
                {study.warnings.slice(0, 6).map((w, i) => (
                  <p key={i} className="text-muted-foreground">• {w}</p>
                ))}
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
