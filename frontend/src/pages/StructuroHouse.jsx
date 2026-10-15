import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loader2, Download, Calculator, Home, Ruler, Layers, AlertTriangle, FileText, ChevronDown } from "lucide-react";
import PromptBar from "@/components/PromptBar";
import { useIsMobile } from "@/hooks/useIsMobile";

const USE_LABEL = {
  habitacao: "Habitação",
  garagem: "Garagem",
  comercio: "Comércio",
  escritorios: "Escritórios",
  esteira: "Esteira sob cobertura",
  cobertura_plana: "Cobertura plana",
  terraco: "Terraço",
};

export default function StructuroHouse() {
  const isMobile = useIsMobile();
  const [geometry, setGeometry] = useState(null);
  const [results, setResults] = useState(null);
  const [computing, setComputing] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [uses, setUses] = useState([]);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/structuro/house/defaults");
        setGeometry(data.geometry);
        setUses(data.uses || []);
      } catch (e) {
        toast.error("Impossível carregar os valores por defeito");
      }
    })();
  }, []);

  const update = (path, value) => {
    setGeometry((prev) => {
      const next = structuredClone(prev);
      const parts = path.split(".");
      let cur = next;
      for (let i = 0; i < parts.length - 1; i++) {
        cur = cur[parts[i]];
      }
      cur[parts[parts.length - 1]] = value;
      return next;
    });
  };

  const updateLevel = (idx, field, value) => {
    setGeometry((prev) => {
      const next = structuredClone(prev);
      next.levels[idx][field] = value;
      return next;
    });
  };

  const parseArray = (str) =>
    str
      .split(/[,;\s]+/)
      .map((s) => parseFloat(s.replace(",", ".")))
      .filter((n) => !Number.isNaN(n));

  const compute = async () => {
    setComputing(true);
    setResults(null);
    try {
      const { data } = await api.post("/structuro/house/compute", { geometry });
      setResults(data);
      toast.success("Cálculo concluído");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Falha no cálculo");
    } finally {
      setComputing(false);
    }
  };

  const downloadPdf = async () => {
    setDownloading(true);
    try {
      const res = await api.post(
        "/structuro/house/pdf",
        { geometry },
        { responseType: "blob" }
      );
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `dossier-estrutural-${(geometry.name || "moradia").replace(/\s+/g, "-")}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success("Dossier descarregado");
    } catch (e) {
      toast.error("Falha a gerar o PDF");
    } finally {
      setDownloading(false);
    }
  };

  if (!geometry) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]" data-testid="structuro-house-loading">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6" data-testid="structuro-house">
      <header className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Home className="h-6 w-6 text-primary" /> Estudo estrutural de moradia
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Pré-dimensionamento NP EN 1990/1991/1992/1996/1997 (Anexos Nacionais PT). Lajes em 2 direções, descida de cargas,
            alvenaria resistente, sapatas, lintéis, cintas/pilaretes, muros de cave, escadas, medições de betão e aço.
            <strong className="text-red-600 ml-1">
              Resultado a verificar e assinar por engenheiro civil. Ação sísmica (NP EN 1998-1) não verificada.
            </strong>
          </p>
        </div>
      </header>

      {geometry && (
        <PromptBar
          appKey="moradia"
          context={{ tipologia: geometry.name, pisos: (geometry.levels || []).length }}
          placeholder="Ex.: «Moradia T3 com 180 m² em dois pisos, cave»"
          examples="Ex.: «T3 180 m², 2 pisos» · «T2 lote 400 m², área bruta 90 m²»"
          onFill={({ params = {} }) => {
            setGeometry((prev) => {
              if (!prev) return prev;
              const next = structuredClone(prev);
              if (params.tipologia) next.name = params.tipologia;
              if (params.pe_direito_m != null && Array.isArray(next.levels)) {
                next.levels = next.levels.map((lv) => ({ ...lv, h_m: Number(params.pe_direito_m) }));
              }
              if (params.pisos && Array.isArray(next.levels)) {
                const want = Math.max(1, Math.min(5, Number(params.pisos)));
                while (next.levels.length < want) {
                  next.levels.push({ ...next.levels[next.levels.length - 1] });
                }
                if (next.levels.length > want) next.levels = next.levels.slice(0, want);
              }
              return next;
            });
          }}
        />
      )}

      {/* Geometria */}
      <Collapsible
        isMobile={isMobile}
        defaultOpen
        testId="structuro-section-geometry"
        icon={<Ruler className="h-4 w-4 text-primary" />}
        title="Geometria"
      >
        <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3">
          <label className="text-sm space-y-1">
            <span className="text-muted-foreground text-xs">Designação</span>
            <Input
              value={geometry.name || ""}
              onChange={(e) => update("name", e.target.value)}
              placeholder="Moradia"
            />
          </label>
          <label className="text-sm space-y-1">
            <span className="text-muted-foreground text-xs">Comprimento exterior L (m)</span>
            <Input
              type="number"
              inputMode="decimal"
              step="0.01"
              value={geometry.outer_L_m}
              onChange={(e) => update("outer_L_m", parseFloat(e.target.value) || 0)}
            />
          </label>
          <label className="text-sm space-y-1">
            <span className="text-muted-foreground text-xs">Largura exterior W (m)</span>
            <Input
              type="number"
              inputMode="decimal"
              step="0.01"
              value={geometry.outer_W_m}
              onChange={(e) => update("outer_W_m", parseFloat(e.target.value) || 0)}
            />
          </label>
          <label className="text-sm space-y-1">
            <span className="text-muted-foreground text-xs">Espessura paredes (m)</span>
            <Input
              type="number"
              inputMode="decimal"
              step="0.01"
              value={geometry.wall_thickness_m}
              onChange={(e) => update("wall_thickness_m", parseFloat(e.target.value) || 0.2)}
            />
          </label>
          <label className="text-sm space-y-1">
            <span className="text-muted-foreground text-xs">Sistema estrutural</span>
            <select
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              value={geometry.structure}
              onChange={(e) => update("structure", e.target.value)}
            >
              <option value="alvenaria">Alvenaria resistente</option>
              <option value="betao">Paredes de betão</option>
              <option value="portico">Pórtico (pilares-vigas)</option>
            </select>
          </label>
          <label className="text-sm space-y-1">
            <span className="text-muted-foreground text-xs">Cobertura</span>
            <select
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              value={geometry.roof.type}
              onChange={(e) => update("roof.type", e.target.value)}
            >
              <option value="inclinada">Inclinada</option>
              <option value="laje_plana">Laje plana</option>
            </select>
          </label>
          <label className="text-sm space-y-1 sm:col-span-2">
            <span className="text-muted-foreground text-xs">
              Paredes interiores em X (m, da fachada esquerda; separadas por espaço ou vírgula)
            </span>
            <Input
              value={(geometry.interior_walls_x || []).join(", ")}
              onChange={(e) => update("interior_walls_x", parseArray(e.target.value))}
              placeholder="ex.: 5.6"
              data-testid="interior-walls-x"
            />
          </label>
          <label className="text-sm space-y-1">
            <span className="text-muted-foreground text-xs">Paredes interiores em Y (m)</span>
            <Input
              value={(geometry.interior_walls_y || []).join(", ")}
              onChange={(e) => update("interior_walls_y", parseArray(e.target.value))}
              placeholder="(vazio)"
            />
          </label>
        </div>
      </Collapsible>

      {/* Pisos */}
      <Collapsible
        isMobile={isMobile}
        testId="structuro-section-floors"
        icon={<Layers className="h-4 w-4 text-primary" />}
        title="Pisos"
      >
        <div className="space-y-2">
          {geometry.levels.map((lv, i) => (
            <div key={i} className="grid gap-2 sm:grid-cols-3">
              <Input
                value={lv.name}
                onChange={(e) => updateLevel(i, "name", e.target.value)}
                placeholder="Nome"
              />
              <Input
                type="number"
              inputMode="decimal"
                step="0.05"
                value={lv.storey_height_m}
                onChange={(e) => updateLevel(i, "storey_height_m", parseFloat(e.target.value) || 2.7)}
                placeholder="Pé-direito (m)"
              />
              <select
                className="h-9 rounded-md border border-input bg-background px-3 text-sm"
                value={lv.use}
                onChange={(e) => updateLevel(i, "use", e.target.value)}
              >
                {uses.map((u) => (
                  <option key={u} value={u}>
                    {USE_LABEL[u] || u}
                  </option>
                ))}
              </select>
            </div>
          ))}
        </div>
      </Collapsible>

      {/* Cave + solo */}
      <Collapsible
        isMobile={isMobile}
        testId="structuro-section-basement"
        title="Cave e solo"
      >
        <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3">
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={!!geometry.basement.present}
              onChange={(e) => update("basement.present", e.target.checked)}
            />
            Com cave
          </label>
          <label className="text-sm space-y-1">
            <span className="text-muted-foreground text-xs">Altura da cave (m)</span>
            <Input
              type="number"
              inputMode="decimal"
              step="0.05"
              value={geometry.basement.height_m || 2.5}
              onChange={(e) => update("basement.height_m", parseFloat(e.target.value) || 2.5)}
              disabled={!geometry.basement.present}
            />
          </label>
          <label className="text-sm space-y-1">
            <span className="text-muted-foreground text-xs">Tensão admissível q_ELS (kPa)</span>
            <Input
              type="number"
              inputMode="decimal"
              step="10"
              value={geometry.soil.q_els_kpa || ""}
              onChange={(e) => {
                const v = parseFloat(e.target.value);
                update("soil.q_els_kpa", Number.isNaN(v) ? null : v);
                update("soil.confirmed", !Number.isNaN(v));
              }}
              placeholder="deixar vazio sem estudo G2"
            />
          </label>
        </div>
      </Collapsible>

      {/* Ações */}
      <div className="flex flex-wrap gap-3">
        <Button onClick={compute} disabled={computing} data-testid="house-compute">
          {computing ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Calculator className="h-4 w-4 mr-2" />}
          Calcular estrutura
        </Button>
        <Button
          variant="outline"
          onClick={downloadPdf}
          disabled={downloading}
          data-testid="house-pdf"
        >
          {downloading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Download className="h-4 w-4 mr-2" />}
          Descarregar dossier PDF
        </Button>
      </div>

      {/* Resultados */}
      {results && (
        <section className="rounded-xl border border-border bg-card p-5 space-y-4" data-testid="house-results">
          <h2 className="font-semibold flex items-center gap-2">
            <FileText className="h-4 w-4 text-primary" /> Resumo do cálculo
          </h2>
          <div className="grid gap-4 md:grid-cols-2 text-sm">
            <div>
              <h3 className="font-medium mb-1">Lajes</h3>
              <ul className="space-y-1">
                {results.slabs.map((s, i) => (
                  <li key={i}>
                    <strong>{s.name}</strong> — espessura {s.h.toString().replace(".", ",")} m,{" "}
                    {s.panels.length} painéis
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h3 className="font-medium mb-1">Medições</h3>
              <ul className="space-y-1">
                <li>Betão: <strong>{String(results.quantities.concrete_m3).replace(".", ",")}</strong> m³</li>
                <li>Aço A500: <strong>{results.quantities.steel_kg}</strong> kg</li>
                <li>Rácio: {String(results.quantities.ratio_kg_m3).replace(".", ",")} kg/m³</li>
              </ul>
            </div>
          </div>

          {Object.keys(results.footings || {}).length > 0 ? (
            <div>
              <h3 className="font-medium mb-1 text-sm">Sapatas contínuas</h3>
              <ul className="text-sm space-y-1">
                {Object.entries(results.footings).map(([k, f]) => (
                  <li key={k}>
                    <strong>{k}</strong>: b={String(f.b_m).replace(".", ",")} m, h={String(f.h_m).replace(".", ",")} m,{" "}
                    {f.transv}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-sm text-amber-600 flex items-center gap-1">
              <AlertTriangle className="h-4 w-4" /> Sapatas não dimensionadas — introduza q_ELS confirmado.
            </p>
          )}

          <div>
            <h3 className="font-medium mb-1 text-sm">Avisos</h3>
            <ul className="text-xs text-muted-foreground space-y-0.5">
              {results.warnings.map((w, i) => (
                <li key={i}>• {w}</li>
              ))}
            </ul>
          </div>
        </section>
      )}
    </div>
  );
}

/**
 * Secção visual: em desktop (>=md), um painel sempre visível com título.
 * Em mobile (<md), um <details> nativo recolhível com chevron.
 * Dark mode via `dark:*` classes.
 */
function Collapsible({ isMobile, defaultOpen = false, testId, icon, title, children }) {
  if (!isMobile) {
    return (
      <section
        className="rounded-xl border border-border bg-card p-5 space-y-4 dark:border-neutral-800 dark:bg-neutral-900"
        data-testid={testId}
        data-collapsible-state="static"
      >
        <h2 className="font-semibold flex items-center gap-2 dark:text-neutral-100">
          {icon}
          {title}
        </h2>
        {children}
      </section>
    );
  }
  return (
    <details
      className="group rounded-xl border border-border bg-card dark:border-neutral-800 dark:bg-neutral-900"
      {...(defaultOpen ? { open: true } : {})}
      data-testid={testId}
      data-collapsible-state="collapsible"
    >
      <summary
        className="list-none cursor-pointer select-none flex items-center justify-between gap-2 p-5 min-h-[56px]"
        data-testid={`${testId}-summary`}
      >
        <span className="font-semibold flex items-center gap-2 dark:text-neutral-100">
          {icon}
          {title}
        </span>
        <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180 dark:text-neutral-400" />
      </summary>
      <div className="px-5 pb-5 space-y-4">{children}</div>
    </details>
  );
}

