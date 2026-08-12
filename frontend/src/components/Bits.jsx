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

export const Stat = ({ label, value, sub, testId, accent }) => (
  <div className="surface p-6" data-testid={testId}>
    <p className="overline text-muted-foreground">{label}</p>
    <p className={`num mt-3 text-2xl font-bold ${accent ? "text-primary" : ""}`}>{value}</p>
    {sub && <p className="mt-1 text-xs text-muted-foreground">{sub}</p>}
  </div>
);

export const SectionTitle = ({ over, title, children }) => (
  <div className="mb-8">
    {over && <p className="overline">{over}</p>}
    <h2 className="mt-2 font-display text-2xl lg:text-3xl font-bold tracking-tight">{title}</h2>
    {children && <p className="mt-2 text-base text-muted-foreground max-w-2xl">{children}</p>}
  </div>
);
