import { Badge } from "@/components/ui/badge";
import { DIFF_STYLE } from "@/lib/api";

export const DifficultyBadge = ({ level, label }) => (
  <Badge
    variant="outline"
    data-testid={`difficulty-${level}`}
    className={`rounded-sm border font-medium ${DIFF_STYLE[level] || ""}`}
  >
    {label}
  </Badge>
);

export const Stat = ({ label, value, sub, testId, accent, onClick, badge }) => (
  <div
    className={`surface p-6 relative ${onClick ? "cursor-pointer transition-colors hover:border-primary/50" : ""}`}
    data-testid={testId}
    onClick={onClick}
    role={onClick ? "button" : undefined}
  >
    {badge != null && (
      <span data-testid={`${testId}-badge`}
            className="absolute top-3 right-3 min-w-5 h-5 px-1.5 grid place-items-center rounded-full bg-red-500 text-white text-[11px] font-bold">
        {badge}
      </span>
    )}
    <p className="overline text-muted-foreground">{label}</p>
    <p className={`num mt-3 text-2xl font-bold ${accent ? "text-primary" : ""}`}>{value}</p>
    {sub && <p className="mt-1 text-xs text-muted-foreground">{sub}</p>}
  </div>
);

export const SectionTitle = ({ over, title, children, as = "h2" }) => {
  const H = as === "h1" ? "h1" : "h2";
  return (
    <div className="mb-8">
      {over && <p className="overline">{over}</p>}
      <H className={`mt-2 font-display font-bold tracking-tight ${as === "h1" ? "text-3xl lg:text-4xl" : "text-2xl lg:text-3xl"}`}>
        {title}
      </H>
      {children && <p className="mt-2 text-base text-muted-foreground max-w-2xl">{children}</p>}
    </div>
  );
};
