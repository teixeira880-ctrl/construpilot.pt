import { useQuoteCopy } from "./quoteCopy";

export const QuoteLineProvenance = ({ line, index }) => {
  const text = useQuoteCopy();
  if (!line.price_source && !line.quantity_missing && !line.vat_assumed) return null;
  return <div className="text-xs flex flex-wrap gap-x-4 gap-y-1 text-muted-foreground" data-testid={`editor-line-provenance-${index}`}>
    {line.price_missing ? <span className="text-amber-700 dark:text-amber-400" data-testid={`editor-line-missing-price-${index}`}>{text("unpriced")}</span> : line.price_estimated ? <span className="text-amber-700 dark:text-amber-400 break-words" data-testid={`editor-line-estimated-${index}`}>{text("price")}: {line.price_reference_label || line.price_reference}</span> : line.price_source === "user_input" && <span data-testid={`editor-line-provided-${index}`}>{text("provided")}</span>}
    {line.quantity_missing && <span className="text-amber-700 dark:text-amber-400" data-testid={`editor-line-missing-qty-${index}`}>{text("quantity")}</span>}{line.vat_assumed && <span data-testid={`editor-line-assumed-vat-${index}`}>{text("vat")}</span>}
  </div>;
};