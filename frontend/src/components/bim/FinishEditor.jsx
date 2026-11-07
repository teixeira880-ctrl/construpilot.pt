// Editor de revestimentos por face (camadas, cores, texturas, zonas em altura) e aplicação em massa.
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { api, eur2 } from "@/lib/api";
import { PATTERN_LABELS, SIDE_LABELS, sideDisplayLabel, sideLabelKey } from "./bimGeometry";

const BTN = "inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition disabled:opacity-50";
const INPUT = "rounded-lg border border-border bg-background px-2 py-1 text-xs";

const faceKeyFor = (labelKey) => (labelKey === "teto" ? "teto" : labelKey === "pavimento" || labelKey === "cobertura" ? "pavimento" : labelKey);

function emptyLayer(preset) {
  return {
    preset: preset?.preset || null, name: preset?.name || "Pintura", color: preset?.color || "#F2EEE6",
    pattern: preset?.pattern || "liso", pattern_size_m: preset?.pattern_size_m || 0.3,
    from_m: 0, to_m: null, thickness_mm: preset?.thickness_mm || 0, item_id: null,
  };
}

export function LayerForm({ presets, library, faceLabel, isWall, onSubmit, submitLabel = "Adicionar camada" }) {
  const options = useMemo(() => {
    const key = faceKeyFor(faceLabel);
    const fit = presets.filter((p) => !key || p.faces.includes(key));
    return fit.length ? fit : presets;
  }, [presets, faceLabel]);
  const [layer, setLayer] = useState(() => emptyLayer(options[0]));
  const set = (k, v) => setLayer((l) => ({ ...l, [k]: v }));
  const pick = (id) => {
    const p = presets.find((x) => x.preset === id);
    setLayer((l) => ({ ...emptyLayer(p), from_m: l.from_m, to_m: l.to_m }));
  };
  const areaItems = library.filter((i) => ["m²", "m2"].includes((i.unit || "").toLowerCase()));
  return (
    <div className="rounded-lg border border-dashed p-2 space-y-2" data-testid="bim-layer-form">
      <div className="flex flex-wrap gap-2 items-center">
        <select className={INPUT} value={layer.preset || ""} onChange={(e) => pick(e.target.value)} aria-label="Tipo de revestimento">
          {options.map((p) => <option key={p.preset} value={p.preset}>{p.name}</option>)}
        </select>
        <input className={`${INPUT} w-40`} value={layer.name} maxLength={80} onChange={(e) => set("name", e.target.value)} aria-label="Nome" />
        <label className="flex items-center gap-1 text-xs">Cor
          <input type="color" value={layer.color} onChange={(e) => set("color", e.target.value.toUpperCase())} className="h-7 w-9 rounded border border-border bg-transparent p-0" data-testid="bim-layer-color" />
        </label>
        <select className={INPUT} value={layer.pattern} onChange={(e) => set("pattern", e.target.value)} aria-label="Textura">
          {Object.entries(PATTERN_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        {layer.pattern !== "liso" && layer.pattern !== "reboco" && (
          <label className="flex items-center gap-1 text-xs">Módulo
            <input type="number" min="0.03" max="3" step="0.01" value={layer.pattern_size_m} onChange={(e) => set("pattern_size_m", Number(e.target.value))} className={`${INPUT} w-16`} /> m
          </label>
        )}
      </div>
      <div className="flex flex-wrap gap-2 items-center text-xs">
        {isWall && (
          <>
            <label className="flex items-center gap-1">De <input type="number" min="0" step="0.05" value={layer.from_m} onChange={(e) => set("from_m", Number(e.target.value))} className={`${INPUT} w-16`} /> m</label>
            <label className="flex items-center gap-1">até <input type="number" min="0" step="0.05" placeholder="teto" value={layer.to_m ?? ""} onChange={(e) => set("to_m", e.target.value === "" ? null : Number(e.target.value))} className={`${INPUT} w-16`} /> m</label>
          </>
        )}
        <label className="flex items-center gap-1">Espessura <input type="number" min="0" step="1" value={layer.thickness_mm} onChange={(e) => set("thickness_mm", Number(e.target.value))} className={`${INPUT} w-16`} /> mm</label>
        <select className={`${INPUT} max-w-[220px]`} value={layer.item_id || ""} onChange={(e) => set("item_id", e.target.value || null)} aria-label="Artigo da biblioteca">
          <option value="">Preço: associar depois</option>
          {areaItems.map((i) => <option key={i.item_id} value={i.item_id}>{i.designation} · {eur2(i.unit_price_ht)}/m²</option>)}
        </select>
        <button type="button" className={`${BTN} bg-primary text-primary-foreground ml-auto`} onClick={() => onSubmit(layer)} data-testid="bim-layer-add">{submitLabel}</button>
      </div>
    </div>
  );
}

function Swatch({ layer }) {
  return <span className="inline-block h-4 w-4 rounded border border-border shrink-0" style={{ background: layer.color }} title={PATTERN_LABELS[layer.pattern]} />;
}

export function FacesEditor({ base, element, presets, library, selectedSide, canEdit, onSaved }) {
  const faces = element.faces;
  const doc = element.finishes || { sides: {}, swap: false };
  const [adding, setAdding] = useState(null);
  const isWall = faces?.kind === "wall";
  if (!faces) return null;

  const save = async (sides, swap) => {
    try {
      await api.put(`${base}/finishes/${element.gid}`, { sides, ...(swap === undefined ? {} : { swap }) });
      setAdding(null);
      onSaved?.();
      toast.success("Revestimentos atualizados");
    } catch (err) {
      const d = err?.response?.data?.detail;
      toast.error(Array.isArray(d) ? d.map((x) => x.msg).join("; ") : d || "Não foi possível guardar");
    }
  };
  const layersOf = (side) => doc.sides?.[side] || [];
  const move = (side, k, dir) => {
    const l = [...layersOf(side)];
    const j = k + dir;
    if (j < 0 || j >= l.length) return;
    [l[k], l[j]] = [l[j], l[k]];
    save({ [side]: l });
  };
  const sides = Object.keys(faces.sides || {});
  return (
    <div className="space-y-3" data-testid="bim-faces-editor">
      <div className="flex items-center justify-between">
        <h4 className="font-medium">Revestimentos</h4>
        {canEdit && isWall && (
          <button type="button" className={`${BTN} border border-border`} onClick={() => save({}, !doc.swap)} title="Use se o interior e o exterior estiverem trocados">⇄ Trocar interior/exterior</button>
        )}
      </div>
      {sides.map((side) => {
        const layers = layersOf(side);
        const label = sideDisplayLabel(faces, side, doc.swap);
        const area = faces.sides[side].area;
        return (
          <div key={side} className={`rounded-lg border p-2 ${selectedSide === side ? "border-[#c4733f] ring-1 ring-[#c4733f]" : ""}`}>
            <div className="flex justify-between text-xs mb-1">
              <span className="font-medium">{label}</span>
              <span className="text-muted-foreground">{area ? `${area.toLocaleString("pt-PT", { maximumFractionDigits: 2 })} m²` : "área n/d"}</span>
            </div>
            {layers.length === 0 && <p className="text-xs text-muted-foreground">Sem revestimento.</p>}
            <ol className="space-y-1">
              {layers.map((l, k) => (
                <li key={l.layer_id} className="flex items-center gap-2 text-xs">
                  <Swatch layer={l} />
                  <span className="flex-1 truncate">{l.name}{isWall && (l.from_m || l.to_m != null) ? ` · ${l.from_m || 0}–${l.to_m ?? "teto"} m` : ""}{l.thickness_mm ? ` · ${l.thickness_mm} mm` : ""}</span>
                  {canEdit && (
                    <>
                      <button type="button" className="text-muted-foreground" onClick={() => move(side, k, -1)} aria-label="Para dentro">↑</button>
                      <button type="button" className="text-muted-foreground" onClick={() => move(side, k, 1)} aria-label="Para fora">↓</button>
                      <button type="button" className="text-red-600" onClick={() => save({ [side]: layers.filter((_, j) => j !== k) })} aria-label="Remover">×</button>
                    </>
                  )}
                </li>
              ))}
            </ol>
            {layers.length > 1 && <p className="text-[11px] text-muted-foreground mt-1">Ordem: de dentro (cima) para fora (baixo); a última camada é a visível.</p>}
            {canEdit && (adding === side ? (
              <div className="mt-2"><LayerForm presets={presets} library={library} faceLabel={sideLabelKey(faces, side, doc.swap)} isWall={isWall}
                                               onSubmit={(layer) => save({ [side]: [...layers, layer] })} /></div>
            ) : (
              <button type="button" className={`${BTN} mt-2 border border-border`} onClick={() => setAdding(side)} data-testid={`bim-add-layer-${side}`}>+ Camada</button>
            ))}
          </div>
        );
      })}
    </div>
  );
}

const TARGETS = [["interior", "Faces interiores"], ["exterior", "Faces exteriores"], ["ambos", "Ambos os lados"], ["pavimento", "Pavimentos (face superior)"], ["teto", "Tetos (face inferior)"]];

export function BulkFinishPanel({ base, gids, presets, library, onDone, onClose }) {
  const [target, setTarget] = useState("interior");
  const [mode, setMode] = useState("replace");
  const [layers, setLayers] = useState([]);
  const [busy, setBusy] = useState(false);
  const run = async (clear = false) => {
    setBusy(true);
    try {
      const { data } = await api.post(`${base}/finishes/apply`, { gids, target, mode: clear ? "clear" : mode, layers: clear ? [] : layers });
      toast.success(`${clear ? "Removido de" : "Aplicado a"} ${data.faces} face(s) em ${data.elements} elemento(s)`);
      onDone?.();
    } catch (err) {
      const d = err?.response?.data?.detail;
      toast.error(Array.isArray(d) ? d.map((x) => x.msg).join("; ") : d || "Aplicação impossível");
    } finally { setBusy(false); }
  };
  return (
    <div className="rounded-xl border bg-card p-3 space-y-2 text-sm" data-testid="bim-bulk-finish">
      <div className="flex items-center justify-between">
        <p className="font-medium">Revestir {gids.length} elemento(s) visíveis</p>
        <button type="button" className="text-muted-foreground" onClick={onClose} aria-label="Fechar">×</button>
      </div>
      <p className="text-xs text-muted-foreground">Use os filtros de piso e categoria (ou isole elementos) para escolher o que revestir.</p>
      <div className="flex flex-wrap gap-2">
        <select className={INPUT} value={target} onChange={(e) => setTarget(e.target.value)} aria-label="Faces">{TARGETS.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
        <select className={INPUT} value={mode} onChange={(e) => setMode(e.target.value)} aria-label="Modo">
          <option value="replace">Substituir o existente</option>
          <option value="append">Acrescentar por cima</option>
        </select>
      </div>
      <ol className="space-y-1">
        {layers.map((l, k) => (
          <li key={`${l.name}-${k}`} className="flex items-center gap-2 text-xs"><Swatch layer={l} /><span className="flex-1">{l.name}{l.from_m || l.to_m != null ? ` · ${l.from_m || 0}–${l.to_m ?? "teto"} m` : ""}</span>
            <button type="button" className="text-red-600" onClick={() => setLayers(layers.filter((_, j) => j !== k))}>×</button></li>
        ))}
      </ol>
      <LayerForm key={target} presets={presets} library={library} faceLabel={target === "ambos" ? null : target} isWall={!["pavimento", "teto"].includes(target)}
                 submitLabel="Juntar à lista" onSubmit={(l) => setLayers([...layers, l])} />
      <div className="flex gap-2 justify-end">
        <button type="button" className={`${BTN} border border-border text-red-600`} disabled={busy || !gids.length} onClick={() => run(true)}>Remover revestimentos destas faces</button>
        <button type="button" className={`${BTN} bg-[#c4733f] text-white`} disabled={busy || !gids.length || !layers.length} onClick={() => run(false)} data-testid="bim-bulk-apply">
          Aplicar {layers.length} camada(s) · {SIDE_LABELS[target] || "ambos os lados"}
        </button>
      </div>
    </div>
  );
}
