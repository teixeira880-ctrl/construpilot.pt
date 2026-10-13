/**
 * ObjectPanel — Volet Objets (Vague B, inspiré QuoterPlan).
 * Liste toutes les mesures de la page courante :
 *  - Pièces (rooms) : m², périmètre, hauteur
 *  - Ouvertures (openings) : type, dimensions
 *  - Compteurs : label + total markers
 *  - Notes : texte
 *  - Angles : degrés + pente x/12
 *  - Toitures pentées : surface projetée / réelle
 *  - Mesures ad-hoc (measurements) : distance / polyligne
 *
 * Chaque ligne : icône type + label + valeur + bouton édition + bouton supprimer.
 * Clic sur une ligne : centre la vue sur l'objet (via onFocus callback).
 */
import React, { useState, useMemo, useEffect } from "react";
import { Square, DoorOpen, Hash, StickyNote, Triangle, MountainSnow, Ruler, Trash2, Edit3, X, Calculator, Layers, Home, Scissors, FileText, ArrowRight } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";

const TABS = [
  { id: "rooms", label: "Pièces", icon: Square },
  { id: "openings", label: "Ouvertures", icon: DoorOpen },
  { id: "counters", label: "Compteurs", icon: Hash },
  { id: "notes", label: "Notes", icon: StickyNote },
  { id: "angles", label: "Angles", icon: Triangle },
  { id: "pitched", label: "Toitures", icon: MountainSnow },
  { id: "measures", label: "Mesures", icon: Ruler },
];

function Row({ icon: Icon, testId, primary, secondary, badge, onFocus, onEdit, onDelete, onExtra, extraLabel, extraIcon: ExtraIcon, onExtra2, extra2Label, extra2Icon: Extra2Icon, badgeColor, className = "", trailing = null }) {
  return (
    <div
      data-testid={testId}
      className={`flex items-center gap-2 px-3 py-2 hover:bg-muted/40 rounded-sm cursor-pointer group ${className}`}
      onClick={onFocus}
    >
      <Icon className="h-4 w-4 shrink-0" style={{ color: badgeColor || undefined }} />
      <div className="min-w-0 flex-1">
        <p className="text-xs font-medium truncate">{primary}</p>
        {secondary && <p className="text-[10px] text-muted-foreground truncate">{secondary}</p>}
      </div>
      {badge && (
        typeof badge === "string" ? (
          <Badge variant="outline" className="text-[10px] rounded-sm num shrink-0"
                 style={{ borderColor: badgeColor, color: badgeColor }}>
            {badge}
          </Badge>
        ) : (
          <span className="shrink-0">{badge}</span>
        )
      )}
      {onExtra && ExtraIcon && (
        <Button size="icon" variant="ghost" onClick={(e) => { e.stopPropagation(); onExtra(); }}
                className="h-6 w-6 shrink-0 opacity-0 group-hover:opacity-100 transition text-primary"
                data-testid={`${testId}-extra`}
                title={extraLabel}>
          <ExtraIcon className="h-3 w-3" />
        </Button>
      )}
      {onExtra2 && Extra2Icon && (
        <Button size="icon" variant="ghost" onClick={(e) => { e.stopPropagation(); onExtra2(); }}
                className="h-6 w-6 shrink-0 opacity-0 group-hover:opacity-100 transition text-red-500"
                data-testid={`${testId}-extra2`}
                title={extra2Label}>
          <Extra2Icon className="h-3 w-3" />
        </Button>
      )}
      {onEdit && (
        <Button size="icon" variant="ghost" onClick={(e) => { e.stopPropagation(); onEdit(); }}
                className="h-6 w-6 shrink-0 opacity-0 group-hover:opacity-100 transition"
                data-testid={`${testId}-edit`}>
          <Edit3 className="h-3 w-3" />
        </Button>
      )}
      {onDelete && (
        <Button size="icon" variant="ghost" onClick={(e) => { e.stopPropagation(); onDelete(); }}
                className="h-6 w-6 shrink-0 opacity-0 group-hover:opacity-100 transition text-destructive"
                data-testid={`${testId}-delete`}>
          <Trash2 className="h-3 w-3" />
        </Button>
      )}
      {trailing}
    </div>
  );
}

export default function ObjectPanel({
  open, onClose,
  rooms = [], measurements = [], annotations = {},
  onFocusObject,
  onRenameRoom, onDeleteRoom, onEstimateRoom, onAttachPreset,
  onDeleteMeasure,
  onClearMeasures,
  onRenameMeasure,
  onConvertMeasure,
  onDeductMeasure,
  onDeleteCounter, onRenameCounter,
  onDeleteNote, onEditNote,
  onDeleteAngle,
  onDeletePitched,
  focusTab = null,
  onExportCotesPdf = null,
  onColorMeasure = null,
  onDeductOpening = null,
  onReportToDevis = null,
  onMergeMeasures = null,
  onReportAllWallAreas = null,
  onChiffrer = null,
  onSetWallHeight = null,
  onSetMeasureSurface = null,
  onSetMeasureLength = null,
  onChiffrerPage = null,
  onOpenPriceLib = null,
  onOpenRoomPreset = null,
}) {
  const [tab, setTab] = useState("rooms");
  const [mergeSel, setMergeSel] = useState([]);
  const toggleMergeSel = (id) => setMergeSel((s) =>
    s.includes(id) ? s.filter((x) => x !== id) : [...s, id]);
  useEffect(() => { if (open && focusTab) setTab(focusTab); }, [open, focusTab]);
  const [editingId, setEditingId] = useState(null);
  const [editValue, setEditValue] = useState("");
  const [presetPickerRoomId, setPresetPickerRoomId] = useState(null);
  const [presets, setPresets] = useState([]);

  // Charge les presets user à l'ouverture (pour l'attach inline)
  useEffect(() => {
    if (!open) return;
    api.get("/tool-presets").then(({ data }) => setPresets(data.presets || []))
      .catch(() => { /* silent */ });
  }, [open]);

  const counts = useMemo(() => ({
    rooms: rooms.length,
    openings: rooms.reduce((n, r) => n + (r.openings?.length || 0), 0),
    counters: (annotations.counters || []).length,
    notes: (annotations.notes || []).length,
    angles: (annotations.angles || []).length,
    pitched: (annotations.pitched_surfaces || []).length,
    measures: measurements.length,
  }), [rooms, measurements, annotations]);

  const totalObjects = Object.values(counts).reduce((a, b) => a + b, 0);

  if (!open) return null;

  const startEdit = (id, current) => { setEditingId(id); setEditValue(current || ""); };
  const commitEdit = (commitFn) => { commitFn(editValue.trim()); setEditingId(null); setEditValue(""); };

  return (
    <div
      className="fixed right-0 top-0 bottom-0 w-80 bg-background border-l border-border shadow-xl z-[999] flex flex-col"
      data-testid="object-panel"
    >
      <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-background sticky top-0 z-10">
        <div>
          <p className="font-display font-bold text-sm">Objets ({totalObjects})</p>
          <p className="text-[10px] text-muted-foreground">Volet Objets — édition inline</p>
        </div>
        <Button size="icon" variant="ghost" onClick={onClose} data-testid="object-panel-close" className="h-7 w-7 relative z-20">
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Tabs */}
      <div className="flex overflow-x-auto border-b border-border px-2 gap-1 py-1">
        {TABS.map((t) => {
          const Ic = t.icon;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              data-testid={`object-panel-tab-${t.id}`}
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-sm text-[10px] transition whitespace-nowrap ${
                tab === t.id ? "bg-primary text-white" : "text-muted-foreground hover:bg-muted"
              }`}
            >
              <Ic className="h-3 w-3" />
              {t.label}
              {counts[t.id] > 0 && (
                <span className="num opacity-70">({counts[t.id]})</span>
              )}
            </button>
          );
        })}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto py-1">
        {tab === "rooms" && (
          <>
            {rooms.length === 0 && <EmptyState label="Aucune pièce" />}
            {rooms.map((r) => {
              const attachedPreset = presets.find((p) => p.preset_id === r.preset_id);
              return (
              <div key={r.room_id || r.name} data-testid={`object-row-room-${r.room_id}`}>
                {editingId === r.room_id ? (
                  <div className="px-3 py-2 flex items-center gap-2">
                    <Input value={editValue} onChange={(e) => setEditValue(e.target.value)}
                           autoFocus className="h-7 text-xs"
                           onKeyDown={(e) => {
                             if (e.key === "Enter") commitEdit((v) => onRenameRoom?.(r.room_id, v));
                             if (e.key === "Escape") { setEditingId(null); setEditValue(""); }
                           }}
                           data-testid={`object-row-room-${r.room_id}-input`} />
                    <Button size="sm" onClick={() => commitEdit((v) => onRenameRoom?.(r.room_id, v))}
                            className="h-7 text-xs">OK</Button>
                  </div>
                ) : (
                  <>
                    <Row
                      icon={Square}
                      testId={`object-row-room-${r.room_id}`}
                      primary={r.name || "Pièce"}
                      secondary={
                        attachedPreset
                          ? `Modèle : ${attachedPreset.name} · ${r.surface_m2 ?? 0} m²`
                          : `${r.perimeter_m || 0} m linéaires · ${r.ceiling_height_m || r.height_m || 2.5} m HSP`
                      }
                      badge={`${r.surface_m2 ?? 0} m²`}
                      badgeColor={attachedPreset ? attachedPreset.color : "#f97316"}
                      onFocus={() => onFocusObject?.({ kind: "room", data: r })}
                      onExtra={onEstimateRoom ? () => onEstimateRoom(r.room_id) : null}
                      extraIcon={Calculator}
                      extraLabel="Générer devis pièce"
                      onEdit={onRenameRoom ? () => startEdit(r.room_id, r.name) : null}
                      onDelete={onDeleteRoom ? () => onDeleteRoom(r.room_id) : null}
                    />
                    {onAttachPreset && (
                      <div className="px-6 pb-2 -mt-1 flex items-center gap-1.5 flex-wrap"
                           data-testid={`room-preset-attach-${r.room_id}`}>
                        <button
                          onClick={() => setPresetPickerRoomId(
                            presetPickerRoomId === r.room_id ? null : r.room_id
                          )}
                          className="inline-flex items-center gap-1 text-[10px] text-muted-foreground hover:text-primary transition"
                          data-testid={`room-preset-toggle-${r.room_id}`}
                        >
                          <Layers className="h-3 w-3" />
                          {attachedPreset ? "Changer modèle" : "Attacher un modèle"}
                        </button>
                        {attachedPreset && (
                          <button
                            onClick={() => onAttachPreset(r.room_id, null)}
                            className="text-[10px] text-destructive hover:underline"
                            data-testid={`room-preset-detach-${r.room_id}`}
                          >
                            Retirer
                          </button>
                        )}
                        {presetPickerRoomId === r.room_id && (
                          <div className="w-full mt-1 grid gap-1 max-h-40 overflow-y-auto border border-border rounded-sm p-1">
                            {presets.length === 0 && (
                              <p className="text-[10px] text-muted-foreground text-center py-2">
                                Aucun modèle. Créez-en depuis la toolbar Pièce.
                              </p>
                            )}
                            {presets.map((p) => (
                              <button
                                key={p.preset_id}
                                onClick={() => {
                                  onAttachPreset(r.room_id, p.preset_id);
                                  setPresetPickerRoomId(null);
                                }}
                                data-testid={`room-preset-option-${r.room_id}-${p.preset_id}`}
                                className={`flex items-center gap-2 px-2 py-1 rounded-sm hover:bg-muted text-xs text-left ${
                                  r.preset_id === p.preset_id ? "bg-primary/10" : ""
                                }`}
                              >
                                <span className="h-2 w-2 rounded-full shrink-0" style={{ background: p.color }} />
                                <span className="truncate flex-1">{p.name}</span>
                                <span className="text-[9px] text-muted-foreground shrink-0">
                                  {p.kind}
                                </span>
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </>
                )}
              </div>
            );})}
          </>
        )}

        {tab === "openings" && (
          <>
            {counts.openings === 0 && <EmptyState label="Aucune ouverture" />}
            {rooms.flatMap((r) => (r.openings || []).map((o, idx) => (
              <Row
                key={`${r.room_id}-op-${idx}`}
                icon={DoorOpen}
                testId={`object-row-opening-${r.room_id}-${idx}`}
                primary={`${o.kind || "Ouverture"} — ${r.name}`}
                secondary={`${o.width_m || "?"} × ${o.height_m || "?"} m`}
                badge={`${((o.width_m || 0) * (o.height_m || 0)).toFixed(2)} m²`}
                badgeColor="#a855f7"
                onFocus={() => onFocusObject?.({ kind: "opening", room: r, opening: o })}
              />
            )))}
          </>
        )}

        {tab === "counters" && (
          <>
            {counts.counters === 0 && <EmptyState label="Aucun compteur" />}
            {(annotations.counters || []).map((c) => (
              <div key={c.id} data-testid={`object-row-counter-${c.id}`}>
                {editingId === c.id ? (
                  <div className="px-3 py-2 flex items-center gap-2">
                    <Input value={editValue} onChange={(e) => setEditValue(e.target.value)}
                           autoFocus className="h-7 text-xs"
                           onKeyDown={(e) => {
                             if (e.key === "Enter") commitEdit((v) => onRenameCounter?.(c.id, v));
                             if (e.key === "Escape") { setEditingId(null); setEditValue(""); }
                           }} />
                    <Button size="sm" onClick={() => commitEdit((v) => onRenameCounter?.(c.id, v))}
                            className="h-7 text-xs">OK</Button>
                  </div>
                ) : (
                  <Row
                    icon={Hash}
                    testId={`object-row-counter-${c.id}`}
                    primary={c.label}
                    secondary={`${c.markers?.length || 0} marqueur${(c.markers?.length || 0) > 1 ? "s" : ""}`}
                    badge={`×${c.markers?.length || 0}`}
                    badgeColor={c.color}
                    onFocus={() => onFocusObject?.({ kind: "counter", data: c })}
                    onEdit={onRenameCounter ? () => startEdit(c.id, c.label) : null}
                    onDelete={onDeleteCounter ? () => onDeleteCounter(c.id) : null}
                  />
                )}
              </div>
            ))}
          </>
        )}

        {tab === "notes" && (
          <>
            {counts.notes === 0 && <EmptyState label="Aucune note" />}
            {(annotations.notes || []).map((n) => (
              <div key={n.id} data-testid={`object-row-note-${n.id}`}>
                {editingId === n.id ? (
                  <div className="px-3 py-2 flex items-center gap-2">
                    <Input value={editValue} onChange={(e) => setEditValue(e.target.value)}
                           autoFocus className="h-7 text-xs" maxLength={60}
                           onKeyDown={(e) => {
                             if (e.key === "Enter") commitEdit((v) => onEditNote?.(n.id, v));
                             if (e.key === "Escape") { setEditingId(null); setEditValue(""); }
                           }} />
                    <Button size="sm" onClick={() => commitEdit((v) => onEditNote?.(n.id, v))}
                            className="h-7 text-xs">OK</Button>
                  </div>
                ) : (
                  <Row
                    icon={StickyNote}
                    testId={`object-row-note-${n.id}`}
                    primary={n.text || "Note vide"}
                    secondary={`Position ${Math.round(n.x)}, ${Math.round(n.y)} px`}
                    badgeColor="#eab308"
                    onFocus={() => onFocusObject?.({ kind: "note", data: n })}
                    onEdit={onEditNote ? () => startEdit(n.id, n.text) : null}
                    onDelete={onDeleteNote ? () => onDeleteNote(n.id) : null}
                  />
                )}
              </div>
            ))}
          </>
        )}

        {tab === "angles" && (
          <>
            {counts.angles === 0 && <EmptyState label="Aucun angle mesuré" />}
            {(annotations.angles || []).map((a) => {
              const rise = (Math.tan((a.degrees * Math.PI) / 180) * 12).toFixed(1);
              return (
                <Row
                  key={a.id}
                  icon={Triangle}
                  testId={`object-row-angle-${a.id}`}
                  primary={a.label || `Angle ${a.degrees.toFixed(1)}°`}
                  secondary={`Pente ${rise}/12 (US)`}
                  badge={`${a.degrees.toFixed(1)}°`}
                  badgeColor="#a855f7"
                  onFocus={() => onFocusObject?.({ kind: "angle", data: a })}
                  onDelete={onDeleteAngle ? () => onDeleteAngle(a.id) : null}
                />
              );
            })}
          </>
        )}

        {tab === "pitched" && (
          <>
            {counts.pitched === 0 && <EmptyState label="Aucune toiture pentée" />}
            {(annotations.pitched_surfaces || []).map((s) => (
              <Row
                key={s.id}
                icon={MountainSnow}
                testId={`object-row-pitched-${s.id}`}
                primary={s.label || `Toiture ${s.pitch_degrees}°`}
                secondary={`Projeté ${s.projected_area_m2} m² → Réel ${s.real_area_m2} m²`}
                badge={`${s.real_area_m2} m²`}
                badgeColor="#3b82f6"
                onFocus={() => onFocusObject?.({ kind: "pitched", data: s })}
                onDelete={onDeletePitched ? () => onDeletePitched(s.id) : null}
              />
            ))}
          </>
        )}

        {tab === "measures" && (
          <>
            {measurements.length === 0 && <EmptyState label="Aucune mesure ad-hoc" />}
            {measurements.length > 0 && onExportCotesPdf && (
              <div className="px-3 pb-1">
                <Button size="sm" onClick={onExportCotesPdf} data-testid="export-cotes-pdf-btn"
                        className="w-full rounded-sm gap-2">
                  <FileText className="h-3 w-3" /> PDF des cotes (nom du projet)
                </Button>
              </div>
            )}
            {measurements.length > 0 && onClearMeasures && (
              <div className="px-3 pb-1">
                <Button size="sm" variant="outline"
                        onClick={onClearMeasures}
                        data-testid="clear-measures-btn"
                        className="w-full rounded-sm gap-2 text-destructive hover:text-destructive">
                  <Trash2 className="h-3 w-3" /> Tout effacer ({measurements.length})
                </Button>
              </div>
            )}
            {onReportAllWallAreas && measurements.some((m) => Number(m.wall_area_net_m2 || 0) > 0) && (
              <div className="px-3 pb-1">
                <Button size="sm" variant="outline" onClick={onReportAllWallAreas}
                        data-testid="report-all-wall-areas-btn"
                        className="w-full rounded-sm gap-2">
                  <ArrowRight className="h-3 w-3" /> Reporter les surfaces de murs au devis (m²)
                </Button>
              </div>
            )}
            {(onChiffrerPage || onOpenPriceLib) && measurements.length > 0 && (
              <div className="px-3 pb-1 flex gap-2">
                {onChiffrerPage && (
                  <Button size="sm" onClick={onChiffrerPage}
                          data-testid="chiffrer-page-btn"
                          className="flex-1 rounded-sm gap-1 text-[11px]">
                    € Chiffrer toute la page
                  </Button>
                )}
                {onOpenPriceLib && (
                  <Button size="sm" variant="outline" onClick={onOpenPriceLib}
                          data-testid="open-price-lib-btn"
                          className="rounded-sm gap-1 text-[11px]" title="Bibliothèque de prix & ratios">
                    Mes prix
                  </Button>
                )}
              </div>
            )}
            {onOpenRoomPreset && (
              <div className="px-3 pb-1">
                <Button size="sm" variant="secondary" onClick={onOpenRoomPreset}
                        data-testid="open-room-preset-btn"
                        className="w-full rounded-sm gap-2 text-[11px]"
                        title="Chiffrer en un clic un ensemble type de pièce">
                  ⚡ Preset pièce (sol + plinthes + peinture + plafond)
                </Button>
              </div>
            )}
            {onMergeMeasures && (
              <div className="px-3 pb-2">
                <div className="rounded-sm border border-dashed border-border p-2 text-[11px] text-muted-foreground">
                  Cochez plusieurs cotes ci-dessous pour les <b>joindre en une seule</b> (la 1re cochée = cible, calcul automatique).
                  {mergeSel.length >= 2 && (
                    <Button size="sm" onClick={() => { onMergeMeasures(mergeSel); setMergeSel([]); }}
                            data-testid="merge-measures-btn"
                            className="mt-2 w-full rounded-sm gap-2 h-8">
                      Fusionner {mergeSel.length} cotes
                    </Button>
                  )}
                  {mergeSel.length === 1 && (
                    <p className="mt-1 text-[10px]">1 cote sélectionnée — cochez-en au moins une autre.</p>
                  )}
                </div>
              </div>
            )}
            {measurements.map((m, idx) => {
              if (editingId === m.measurement_id) return (
                <div key={m.measurement_id} className="px-3 py-2 flex items-center gap-2">
                  <Input value={editValue} onChange={(e) => setEditValue(e.target.value)}
                         autoFocus className="h-7 text-xs"
                         placeholder="ex. murs parpaing, murs en brique…"
                         onKeyDown={(e) => {
                           if (e.key === "Enter") commitEdit((v) => onRenameMeasure?.(m.measurement_id, v));
                           if (e.key === "Escape") { setEditingId(null); setEditValue(""); }
                         }}
                         data-testid={`object-row-measure-${idx}-input`} />
                  <Button size="sm" onClick={() => commitEdit((v) => onRenameMeasure?.(m.measurement_id, v))}
                          className="h-7 text-xs">OK</Button>
                </div>
              );
              const kind = m.kind;
              const hasArea = m.area_m2 != null || m.wall_area_net_m2 != null;
              const isArea = kind === "polygon" || kind === "cumulative_area" || kind === "manual_area"
                || (hasArea && kind !== "cumulative" && kind !== "distance" && kind !== "polyline" && kind !== "manual_linear");
              const isLinear = !isArea && (kind === "distance" || kind === "cumulative" || kind === "polyline"
                || kind === "manual_linear" || m.length_m != null || m.value_m != null);
              const nOpen = (m.openings || []).length;
              const dedTxt = nOpen ? ` · −${nOpen} ouv.` : "";
              const primary = m.label || (kind === "distance" ? "Distance" : kind === "polygon" ? "Surface" : kind === "cumulative" ? "Mur cumulé" : kind === "cumulative_area" ? "Surface cumulée" : kind === "manual_area" ? "Surface" : kind === "manual_linear" ? "Linéaire" : isArea ? "Surface" : "Mesure");
              const kindTxt = kind === "distance" ? "Distance"
                : kind === "polygon" ? "Surface"
                : kind === "cumulative" ? `Mur · ${(m.segments || []).length} tronçon(s)${dedTxt}`
                : kind === "cumulative_area" ? `Surface · ${(m.polygons || []).length} zone(s)`
                : kind === "manual_area" ? (m.slope_pct ? `Surface · rampant ${m.slope_pct}%` : "Surface")
                : kind === "manual_linear" ? "Linéaire"
                : isArea ? "Surface" : isLinear ? "Linéaire" : "Périmètre";
              const badge = isArea ? `${(m.area_m2 ?? m.wall_area_net_m2 ?? 0).toFixed(2)} m²` : `${(m.value_m ?? m.length_m ?? 0).toFixed(2)} m`;
              const canEditArea = isArea && onSetMeasureSurface;
              const canEditLinear = isLinear && onSetMeasureLength;
              const numVal = isArea ? Number(m.area_m2 ?? m.wall_area_net_m2 ?? 0) : Number(m.value_m ?? m.length_m ?? 0);
              const badgeNode = (canEditArea || canEditLinear) ? (
                <span className="inline-flex items-center gap-0.5" onClick={(e) => e.stopPropagation()}>
                  <input type="number" step="0.01" min="0" key={numVal} defaultValue={numVal.toFixed(2)}
                    data-testid={`object-row-measure-${idx}-value`}
                    title="Modifier directement la quantité"
                    className="h-6 w-16 rounded border border-border bg-background px-1 text-[11px] text-right num"
                    onKeyDown={(e) => { if (e.key === "Enter") e.target.blur(); }}
                    onBlur={(e) => {
                      const v = parseFloat(String(e.target.value).replace(",", "."));
                      if (v > 0 && Math.abs(v - numVal) > 1e-6) {
                        if (canEditArea) onSetMeasureSurface(m.measurement_id, v);
                        else onSetMeasureLength(m.measurement_id, v);
                      } else { e.target.value = numVal.toFixed(2); }
                    }} />
                  <span className="text-[10px] text-muted-foreground">{isArea ? "m²" : "m"}</span>
                </span>
              ) : badge;
              const areaTxt = (isLinear && m.wall_area_net_m2 != null)
                ? ` · ${Number(m.wall_area_net_m2).toFixed(2)} m² (h. ${Number(m.wall_height_m || 0)} m)` : "";
              return (
              <div key={m.measurement_id || idx}>
              <div className="flex items-center gap-1">
                {onMergeMeasures && (isLinear || isArea) && (
                  <input type="checkbox" checked={mergeSel.includes(m.measurement_id)}
                         onChange={() => toggleMergeSel(m.measurement_id)}
                         title="Sélectionner pour fusionner"
                         data-testid={`object-row-measure-${idx}-merge`}
                         className="ml-3 h-4 w-4 shrink-0 cursor-pointer" />
                )}
                <input type="color" value={m.color || "#0d9488"}
                       onChange={(e) => onColorMeasure?.(m.measurement_id, e.target.value)}
                       title="Couleur du filtre (plancher, murs…)"
                       data-testid={`object-row-measure-${idx}-color`}
                       className="ml-3 h-6 w-6 shrink-0 cursor-pointer rounded border border-border bg-transparent p-0" />
                <div className="min-w-0 flex-1">
                  <Row
                    icon={Ruler}
                    className="flex-1 min-w-0"
                    testId={`object-row-measure-${idx}`}
                    primary={primary}
                    secondary={`${kindTxt}${areaTxt} · créée ${new Date(m.created_at || Date.now()).toLocaleTimeString("fr-FR")}`}
                    badge={badgeNode}
                    badgeColor={m.color || "#0d9488"}
                    onFocus={() => onFocusObject?.({ kind: "measure", data: m })}
                    onExtra={kind === "polygon" && onConvertMeasure ? () => onConvertMeasure(m.measurement_id) : ((isLinear || kind === "cumulative_area") && onReportToDevis ? () => onReportToDevis(m) : null)}
                    extraIcon={kind === "polygon" ? Home : ArrowRight}
                    extraLabel={kind === "polygon" ? "Convertir en pièce (murs + estimation)" : "Envoyer au devis (ligne d'ouvrage)"}
                    onExtra2={kind === "polygon" && onDeductMeasure ? () => onDeductMeasure(m.measurement_id) : (isLinear && onDeductOpening ? () => onDeductOpening(m) : null)}
                    extra2Icon={kind === "polygon" ? Scissors : DoorOpen}
                    extra2Label={kind === "polygon" ? "Déduire de la pièce contenante (trémie, escalier…)" : "Déduire une ouverture (fenêtre/porte)"}
                    onEdit={onRenameMeasure ? () => startEdit(m.measurement_id, m.label || "") : null}
                    onDelete={onDeleteMeasure ? () => onDeleteMeasure(m.measurement_id) : null}
                    trailing={onChiffrer && (isArea || isLinear) ? (
                      <button type="button" onClick={(e) => { e.stopPropagation(); onChiffrer(m); }}
                              title="Chiffrer ce poste (composition + estimation)"
                              data-testid={`object-row-measure-${idx}-chiffrer`}
                              className="shrink-0 rounded-sm border border-primary/40 px-1.5 py-1 text-[11px] font-semibold text-primary hover:bg-primary/10">
                        € Chiffrer
                      </button>
                    ) : null}
                  />
                </div>
              </div>
              {onSetWallHeight && isLinear && (
                <div className="ml-9 -mt-1 mb-1 flex items-center gap-2 text-[11px] text-muted-foreground" data-testid={`object-row-measure-${idx}-height-row`}>
                  <span>Hauteur mur :</span>
                  <input type="number" step="0.05" min="0" defaultValue={m.wall_height_m || ""}
                         placeholder="2.50"
                         data-testid={`object-row-measure-${idx}-height`}
                         className="h-6 w-16 rounded border border-border bg-background px-1 text-[11px]"
                         onBlur={(e) => {
                           const h = parseFloat(String(e.target.value).replace(",", "."));
                           if ((h || 0) !== (m.wall_height_m || 0)) onSetWallHeight(m.measurement_id, h || 0);
                         }} />
                  <span>m</span>
                  {m.wall_area_net_m2 != null && (
                    <span className="font-semibold text-foreground" data-testid={`object-row-measure-${idx}-net-m2`}>
                      → {Number(m.wall_area_net_m2).toFixed(2)} m² net
                    </span>
                  )}
                </div>
              )}
              </div>
              );
            })}
          </>
        )}
      </div>
    </div>
  );
}

function EmptyState({ label }) {
  return (
    <div className="text-center py-10 text-xs text-muted-foreground">
      <p>{label}</p>
      <p className="text-[10px] mt-1 opacity-70">Utilisez les outils pour en créer.</p>
    </div>
  );
}
