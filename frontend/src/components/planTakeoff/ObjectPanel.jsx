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
import { Square, DoorOpen, Hash, StickyNote, Triangle, MountainSnow, Ruler, Trash2, Edit3, X, Calculator, Layers } from "lucide-react";
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

function Row({ icon: Icon, testId, primary, secondary, badge, onFocus, onEdit, onDelete, onExtra, extraLabel, extraIcon: ExtraIcon, badgeColor }) {
  return (
    <div
      data-testid={testId}
      className="flex items-center gap-2 px-3 py-2 hover:bg-muted/40 rounded-sm cursor-pointer group"
      onClick={onFocus}
    >
      <Icon className="h-4 w-4 shrink-0" style={{ color: badgeColor || undefined }} />
      <div className="min-w-0 flex-1">
        <p className="text-xs font-medium truncate">{primary}</p>
        {secondary && <p className="text-[10px] text-muted-foreground truncate">{secondary}</p>}
      </div>
      {badge && (
        <Badge variant="outline" className="text-[10px] rounded-sm num shrink-0"
               style={{ borderColor: badgeColor, color: badgeColor }}>
          {badge}
        </Badge>
      )}
      {onExtra && ExtraIcon && (
        <Button size="icon" variant="ghost" onClick={(e) => { e.stopPropagation(); onExtra(); }}
                className="h-6 w-6 opacity-0 group-hover:opacity-100 transition text-primary"
                data-testid={`${testId}-extra`}
                title={extraLabel}>
          <ExtraIcon className="h-3 w-3" />
        </Button>
      )}
      {onEdit && (
        <Button size="icon" variant="ghost" onClick={(e) => { e.stopPropagation(); onEdit(); }}
                className="h-6 w-6 opacity-0 group-hover:opacity-100 transition"
                data-testid={`${testId}-edit`}>
          <Edit3 className="h-3 w-3" />
        </Button>
      )}
      {onDelete && (
        <Button size="icon" variant="ghost" onClick={(e) => { e.stopPropagation(); onDelete(); }}
                className="h-6 w-6 opacity-0 group-hover:opacity-100 transition text-destructive"
                data-testid={`${testId}-delete`}>
          <Trash2 className="h-3 w-3" />
        </Button>
      )}
    </div>
  );
}

export default function ObjectPanel({
  open, onClose,
  rooms = [], measurements = [], annotations = {},
  onFocusObject,
  onRenameRoom, onDeleteRoom, onEstimateRoom, onAttachPreset,
  onDeleteMeasure,
  onDeleteCounter, onRenameCounter,
  onDeleteNote, onEditNote,
  onDeleteAngle,
  onDeletePitched,
}) {
  const [tab, setTab] = useState("rooms");
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
                          : `${r.perimeter_m || 0} m linéaires · ${r.height_m || 2.5} m HSP`
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
            {measurements.map((m, idx) => (
              <Row
                key={m.measurement_id || idx}
                icon={Ruler}
                testId={`object-row-measure-${idx}`}
                primary={m.kind === "distance" ? "Distance" : "Polyligne"}
                secondary={`Créée ${new Date(m.created_at || Date.now()).toLocaleTimeString("fr-FR")}`}
                badge={`${(m.length_m || 0).toFixed(2)} m`}
                badgeColor="#f97316"
                onFocus={() => onFocusObject?.({ kind: "measure", data: m })}
                onDelete={onDeleteMeasure ? () => onDeleteMeasure(m.measurement_id) : null}
              />
            ))}
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
