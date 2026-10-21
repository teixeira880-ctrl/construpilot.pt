import { useI18n } from "@/context/I18nContext";

const COPY = {
  fr: { reading: "Leitura CAD", complete: "objetos suportados", partial: "leitura parcial — detalhes", unit: "Un.", calibration: "ver calibração", space: "Espaço analisado", verify: "O reconhecimento das camadas e dos materiais deve ser confirmado na planta.", converted: "DWG → DXF", engine: "Motor", format: "Formato", cached: "Resultado da conversão reutilizado", choose: "Qual é a unidade desta planta?", why: "O ficheiro não indica a unidade. Escolha a unidade utilizada no programa de desenho para obter medidas corretas.", cancel: "Cancelar importação", units: ["Pés", "Pés", "Pés", "Polegadas", "Pés"] },
  pt: { reading: "Leitura CAD", complete: "objetos suportados", partial: "leitura parcial — detalhes", unit: "Unidade", calibration: "ver calibração", space: "Espaço analisado", verify: "O reconhecimento das camadas e dos materiais deve ser confirmado na planta.", converted: "DWG → DXF", engine: "Motor", format: "Formato", cached: "Resultado da conversão reutilizado", choose: "Qual é a unidade desta planta?", why: "O ficheiro não indica a unidade. Escolha a unidade utilizada no programa de desenho para obter medidas corretas.", cancel: "Cancelar importação", units: ["Milímetros", "Centímetros", "Metros", "Polegadas", "Pés"] },
  en: { reading: "CAD reading", complete: "supported objects", partial: "partial reading — details", unit: "Unit", calibration: "see calibration", space: "Analysed space", verify: "Layer and material recognition must still be checked against the drawing.", converted: "DWG → DXF", engine: "Engine", format: "Format", cached: "Conversion result reused", choose: "What is this drawing's unit?", why: "The file does not declare its unit. Choose the unit used in the drawing software for correct measurements.", cancel: "Cancel import", units: ["Millimetres", "Centimetres", "Metres", "Inches", "Feet"] },
};
const DIAGNOSTICS = {
  fr: { XREF_UNRESOLVED: "Referência externa em falta", BLOCK_RECURSION: "Bloco aninhado não resolvido", TRANSFORM_UNSUPPORTED: "Transformação não suportada", BLOCK_UNREADABLE: "Bloco ilegível", DIMENSION_RENDER_MISSING: "Representação de uma cota em falta", UNSUPPORTED_ENTITIES: "Alguns tipos de objetos não são analisados", PAPERSPACE_NOT_ANALYZED: "Existem apresentações em papel: apenas o espaço de modelo é analisado" },
  pt: { XREF_UNRESOLVED: "Referência externa em falta", BLOCK_RECURSION: "Bloco aninhado não resolvido", TRANSFORM_UNSUPPORTED: "Transformação não suportada", BLOCK_UNREADABLE: "Bloco ilegível", DIMENSION_RENDER_MISSING: "Representação de uma cota em falta", UNSUPPORTED_ENTITIES: "Alguns tipos de objetos não são analisados", PAPERSPACE_NOT_ANALYZED: "Existem apresentações em papel: apenas o espaço de modelo é analisado" },
  en: { XREF_UNRESOLVED: "Missing external reference", BLOCK_RECURSION: "Unresolved nested block", TRANSFORM_UNSUPPORTED: "Unsupported transformation", BLOCK_UNREADABLE: "Unreadable block", DIMENSION_RENDER_MISSING: "Missing dimension drawing", UNSUPPORTED_ENTITIES: "Some object types are not analysed", PAPERSPACE_NOT_ANALYZED: "Paper layouts present: only model space is analysed" },
};

export function CadImportInfo({ info, testId = "cad-import-info" }) {
  const { lang } = useI18n();
  if (!info) return null;
  const t = COPY[lang] || COPY.fr;
  const labels = DIAGNOSTICS[lang] || DIAGNOSTICS.fr;
  const conversion = info.conversion;
  return <details className="border rounded-sm p-2 text-xs space-y-1 break-words" data-testid={testId}>
    <summary data-testid={`${testId}-toggle`}>{t.reading} · {info.complete ? t.complete : t.partial}</summary>
    <p data-testid={`${testId}-units`}>{t.unit}: {info.units?.name || info.unit?.name || t.calibration}. {t.space}: {info.layout || "Model"}.</p>
    {conversion && <div className="border-l-2 border-primary pl-2 space-y-1" data-testid={`${testId}-conversion`}>
      <p className="font-medium" data-testid={`${testId}-provider`}>{t.converted} · {conversion.provider === "autodesk" ? "Autodesk AutoCAD" : conversion.provider === "oda" ? "ODA" : "CloudConvert"}</p>
      {conversion.engine && <p data-testid={`${testId}-engine`}>{t.engine}: {conversion.engine}</p>}
      {conversion.format_version && <p data-testid={`${testId}-format`}>{t.format}: {conversion.format_version}</p>}
      {conversion.cached && <p className="text-muted-foreground" data-testid={`${testId}-cached`}>{t.cached}</p>}
    </div>}
    {(info.diagnostics || []).map((d, i) => <p key={i} data-testid={`${testId}-diagnostic-${i}`}>{labels[d.code] || d.code}{d.block ? ` : ${d.block}` : ""}{d.types ? ` (${d.types.join(", ")})` : ""}</p>)}
    <p data-testid={`${testId}-verification-note`}>{t.verify}</p>
  </details>;
}

export function CadUnitPicker({ file, onChoose, onCancel }) {
  const { lang } = useI18n();
  const t = COPY[lang] || COPY.fr;
  return <div role="dialog" aria-modal="true" aria-label={t.choose} data-testid="cad-unit-dialog" className="fixed inset-0 z-50 bg-black/40 grid place-items-center p-4">
    <div className="bg-background border rounded-md p-5 max-w-md min-w-0 grid gap-3 shadow-xl">
      <b>{t.choose}</b><p className="text-sm break-all" data-testid="cad-unit-filename">{file.name}</p>
      <p className="text-sm" data-testid="cad-unit-explanation">{t.why}</p>
      <div className="flex flex-wrap gap-2">{["mm", "cm", "m", "inches", "feet"].map((value, i) => <button key={value} data-testid={`cad-unit-${value}`} className="border px-3 py-2 rounded-sm hover:bg-muted transition-colors" onClick={() => onChoose(value)}>{t.units[i]}</button>)}</div>
      <button className="underline text-sm" data-testid="cad-unit-cancel" onClick={onCancel}>{t.cancel}</button>
    </div>
  </div>;
}