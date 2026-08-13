/**
 * PresetPicker — Sélecteur de modèles réutilisables (Vague B, inspiré QuoterPlan).
 *
 * Affiche un bouton "Modèle" qui ouvre un dropdown listant les presets de l'utilisateur
 * filtrés par `kind` (wall / floor / opening / …). Sélection = appelle `onApply(preset)`.
 * Un bouton "Créer nouveau" ouvre un mini-form pour sauver le preset courant.
 *
 * Placé à côté du bouton "Fermer pièce" / "Fermer toiture" / "Nouveau compteur".
 */
import React, { useEffect, useRef, useState } from "react";
import { Layers, Plus, Trash2, ChevronDown, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { api } from "@/lib/api";

export default function PresetPicker({
  kinds = [],           // liste de kinds à afficher (ex: ["wall", "insulation"])
  onApply,              // callback(preset) — appliquer le modèle sélectionné
  currentSelection,     // objet à sauver comme preset ({ name, unit, price_per_unit, params })
  testIdPrefix = "preset",
  compact = false,
}) {
  const [open, setOpen] = useState(false);
  const [presets, setPresets] = useState([]);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newPrice, setNewPrice] = useState("");
  const [loading, setLoading] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const onDocClick = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  const load = async () => {
    try {
      const { data } = await api.get("/tool-presets");
      setPresets(data.presets || []);
    } catch { /* silent */ }
  };

  const seedDefaults = async () => {
    setLoading(true);
    try {
      const { data } = await api.post("/tool-presets/seed-defaults");
      if (data.created > 0) {
        toast.success(`${data.created} modèles d'usine ajoutés`);
        await load();
      } else {
        toast.info(`Vous avez déjà ${data.already_had} modèles`);
      }
    } catch (e) {
      toast.error("Import impossible");
    } finally {
      setLoading(false);
    }
  };

  const create = async () => {
    if (!newName.trim()) return toast.error("Nom requis");
    const kind = kinds[0] || "other";
    try {
      const body = {
        name: newName.trim(),
        kind,
        unit: currentSelection?.unit || "m²",
        color: currentSelection?.color || "#f97316",
        price_per_unit: newPrice ? Number(newPrice) : (currentSelection?.price_per_unit ?? null),
        params: currentSelection?.params || {},
      };
      await api.post("/tool-presets", body);
      toast.success(`Modèle « ${newName.trim()} » sauvegardé`);
      setNewName(""); setNewPrice(""); setCreating(false);
      await load();
    } catch {
      toast.error("Création impossible");
    }
  };

  const remove = async (preset_id) => {
    if (!window.confirm("Supprimer ce modèle ?")) return;
    try {
      await api.delete(`/tool-presets/${preset_id}`);
      toast.success("Modèle supprimé");
      await load();
    } catch {
      toast.error("Suppression impossible");
    }
  };

  const filtered = kinds.length
    ? presets.filter((p) => kinds.includes(p.kind))
    : presets;

  return (
    <div ref={ref} className="relative inline-block">
      <Button
        size="sm" variant="outline"
        onClick={() => {
          const next = !open;
          setOpen(next);
          if (next && presets.length === 0) load();
        }}
        data-testid={`${testIdPrefix}-picker-btn`}
        className="rounded-sm gap-1.5 h-8 text-xs"
      >
        <Layers className="h-3 w-3" />
        {compact ? "" : "Modèle"}
        <ChevronDown className="h-3 w-3 opacity-60" />
      </Button>
      {open && (
        <div
          className="absolute top-full mt-1 right-0 w-72 bg-background border border-border rounded-sm shadow-lg z-30 max-h-96 overflow-hidden flex flex-col"
          data-testid={`${testIdPrefix}-picker-menu`}
        >
          <div className="px-3 py-2 border-b border-border flex items-center justify-between">
            <p className="text-[10px] uppercase tracking-wider font-medium text-muted-foreground">
              Modèles {kinds.length ? `(${kinds.join(", ")})` : "réutilisables"}
            </p>
            {presets.length === 0 && (
              <Button size="sm" variant="ghost" onClick={seedDefaults}
                      disabled={loading} className="h-6 text-[10px] gap-1"
                      data-testid={`${testIdPrefix}-seed-defaults`}>
                <Sparkles className="h-3 w-3" /> Modèles d'usine
              </Button>
            )}
          </div>
          <div className="overflow-y-auto flex-1">
            {filtered.length === 0 && (
              <div className="text-center py-6 text-xs text-muted-foreground px-4">
                {presets.length === 0
                  ? "Aucun modèle. Cliquez « Modèles d'usine » pour démarrer avec 6 presets prêts."
                  : `Aucun modèle de type ${kinds.join(", ")}. Créez-en un.`}
              </div>
            )}
            {filtered.map((p) => (
              <div
                key={p.preset_id}
                data-testid={`${testIdPrefix}-item-${p.preset_id}`}
                className="flex items-center gap-2 px-3 py-2 hover:bg-muted/40 cursor-pointer group"
                onClick={() => { onApply?.(p); setOpen(false); toast.success(`Modèle « ${p.name} » appliqué`); }}
              >
                <div className="h-3 w-3 rounded-sm shrink-0" style={{ background: p.color }} />
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium truncate">{p.name}</p>
                  <p className="text-[10px] text-muted-foreground truncate">
                    {p.kind} · {p.price_per_unit != null ? `${p.price_per_unit} €/${p.unit}` : p.unit}
                  </p>
                </div>
                <Button size="icon" variant="ghost"
                        onClick={(e) => { e.stopPropagation(); remove(p.preset_id); }}
                        className="h-6 w-6 opacity-0 group-hover:opacity-100 text-destructive"
                        data-testid={`${testIdPrefix}-delete-${p.preset_id}`}>
                  <Trash2 className="h-3 w-3" />
                </Button>
              </div>
            ))}
          </div>
          <div className="border-t border-border p-2">
            {creating ? (
              <div className="space-y-2">
                <Input value={newName} onChange={(e) => setNewName(e.target.value)}
                       placeholder="Nom du modèle" className="h-8 text-xs"
                       autoFocus
                       data-testid={`${testIdPrefix}-new-name`}
                       onKeyDown={(e) => { if (e.key === "Enter") create(); if (e.key === "Escape") setCreating(false); }} />
                <div className="flex gap-2">
                  <Input value={newPrice} onChange={(e) => setNewPrice(e.target.value)}
                         placeholder="Prix €/unité" type="number" className="h-8 text-xs num"
                         data-testid={`${testIdPrefix}-new-price`} />
                  <Button size="sm" onClick={create} className="h-8 text-xs shrink-0"
                          data-testid={`${testIdPrefix}-new-save`}>
                    Enregistrer
                  </Button>
                </div>
              </div>
            ) : (
              <Button size="sm" variant="ghost" onClick={() => setCreating(true)}
                      className="w-full justify-start gap-2 h-8 text-xs"
                      data-testid={`${testIdPrefix}-new-btn`}>
                <Plus className="h-3 w-3" /> Créer un nouveau modèle
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
