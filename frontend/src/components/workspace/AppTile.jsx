import { FAMILY_COLORS, FAMILY_GRADIENTS } from "@/components/workspace/navigation";

// Mosaico de ícone "autocolante": degradé vivo por espaço de trabalho, reflexo no topo, pictograma branco.
// A inclinação ao passar o rato / no item ativo é feita em CSS (.cp-app-tile, styles/workspace-tiles.css).
export const AppTile = ({ icon: Icon, family, size = 36, label = "", className = "" }) => {
  const fam = FAMILY_GRADIENTS[family] ? family : "compte";
  return (
    <span
      role="img"
      aria-label={label || undefined}
      aria-hidden={label ? undefined : "true"}
      data-family={fam}
      className={`cp-app-tile inline-grid place-items-center shrink-0 ${className}`}
      style={{ width: size, height: size, borderRadius: Math.round(size * 0.3), backgroundColor: FAMILY_COLORS[fam], backgroundImage: FAMILY_GRADIENTS[fam] }}
    >
      {Icon ? <Icon size={Math.round(size * 0.56)} strokeWidth={2} color="#ffffff" aria-hidden="true" /> : null}
    </span>
  );
};
