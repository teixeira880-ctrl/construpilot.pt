import { FAMILY_COLORS, FAMILY_GRADIENTS, AssistantIcon } from "@/components/workspace/navigation";

// Tuile d'icône d'app : dégradé vif par espace de travail, reflet en haut, pictogramme blanc (trait 2).
// L'inclinaison au survol / sur l'élément actif est gérée en CSS (.cp-app-tile, styles/workspace-tiles.css).
// L'Assistant conserve son identité (AssistantMark) et remplit la tuile.
export const AppTile = ({ icon: Icon, family, size = 36, label = "", className = "" }) => {
  const fam = FAMILY_GRADIENTS[family] ? family : "compte";
  const radius = Math.round(size * 0.3);
  const isAssistant = Icon === AssistantIcon;
  const common = {
    role: "img",
    "aria-label": label || undefined,
    className: `cp-app-tile inline-grid place-items-center shrink-0 ${className}`,
    style: { width: size, height: size, borderRadius: radius },
  };
  if (isAssistant) {
    return (
      <span {...common} style={{ ...common.style, overflow: "hidden" }}>
        <Icon size={size} />
      </span>
    );
  }
  return (
    <span {...common} data-family={fam}
      style={{ ...common.style, backgroundColor: FAMILY_COLORS[fam], backgroundImage: FAMILY_GRADIENTS[fam] }}>
      {Icon ? <Icon size={Math.round(size * 0.56)} strokeWidth={2} color="#ffffff" aria-hidden="true" /> : null}
    </span>
  );
};
