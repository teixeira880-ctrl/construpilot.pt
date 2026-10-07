import React, { useState } from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/**
 * Card inline amarelo que apresenta um `MissingDataRequest`.
 * O utilizador responde directamente e dispara um novo turno.
 */
export default function MissingDataCard({ pedido, onResponder, pending = false }) {
  const [valor, setValor] = useState("");
  const criticidadeLabel = {
    bloqueante: { texto: "Bloqueante", cor: "bg-red-500/15 text-red-700 border-red-400" },
    importante: { texto: "Importante", cor: "bg-amber-500/15 text-amber-800 border-amber-400" },
    opcional:   { texto: "Opcional",   cor: "bg-slate-500/15 text-slate-700 border-slate-400" },
  }[pedido?.criticidade || "importante"];

  const tipoInput = _inferirTipo(pedido?.unit);
  const placeholder = pedido?.suggested_default != null
    ? String(pedido.suggested_default)
    : _placeholderPorUnidade(pedido?.unit);

  const submeter = () => {
    const v = (valor || "").trim();
    if (!v) return;
    const resposta = pedido?.unit
      ? `${pedido.question_pt} → ${v} ${pedido.unit}`
      : `${pedido.question_pt} → ${v}`;
    onResponder?.(resposta);
    setValor("");
  };

  return (
    <div
      className="btp-missing-card"
      data-testid={`btp-missing-${pedido?.field || "x"}`}
    >
      <div className="flex items-start gap-2 mb-2">
        <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
        <div className="flex-1">
          <div className="font-medium">{pedido?.question_pt}</div>
          <div className="text-xs opacity-80 mt-0.5 flex items-center gap-2 flex-wrap">
            <code className="font-mono">{pedido?.field}</code>
            {pedido?.unit && <span>· unidade: {pedido.unit}</span>}
            <span className={`px-2 py-0.5 rounded border text-[10px] ${criticidadeLabel?.cor}`}>
              {criticidadeLabel?.texto}
            </span>
          </div>
        </div>
      </div>
      <div className="flex gap-2 items-center">
        <Input
          type={tipoInput}
          placeholder={placeholder}
          value={valor}
          onChange={(e) => setValor(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") submeter(); }}
          disabled={pending}
          data-testid={`btp-missing-input-${pedido?.field || "x"}`}
          className="flex-1 bg-white dark:bg-slate-900"
        />
        <Button
          size="sm"
          onClick={submeter}
          disabled={pending || !valor.trim()}
          data-testid={`btp-missing-submit-${pedido?.field || "x"}`}
        >
          Responder
        </Button>
      </div>
    </div>
  );
}


function _inferirTipo(unit) {
  if (!unit) return "text";
  if (/[²³]|m²|m³|kg|EUR|€|%/.test(unit)) return "number";
  return "text";
}


function _placeholderPorUnidade(unit) {
  if (!unit) return "A sua resposta…";
  if (unit.includes("m²")) return "ex.: 180";
  if (unit.includes("kg/m³")) return "ex.: 100";
  if (unit.includes("EUR") || unit.includes("€")) return "ex.: 2500";
  return `Valor em ${unit}`;
}
