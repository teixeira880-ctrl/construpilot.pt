/**
 * Skeleton shimmer — placeholder enquanto dados carregam.
 * Props:
 *  - className: tailwind utilitários extra (default: h-4 w-full rounded-md)
 *  - count: nº de linhas (default 1)
 *  - testId: data-testid
 */
export default function Skeleton({ className = "h-4 w-full rounded-md", count = 1, testId = "skeleton" }) {
  if (count === 1) {
    return (
      <div
        className={`animate-pulse bg-muted ${className}`}
        aria-hidden="true"
        data-testid={testId}
      />
    );
  }
  return (
    <div className="space-y-2" data-testid={testId}>
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className={`animate-pulse bg-muted ${className}`}
          aria-hidden="true"
          data-testid={`${testId}-${i}`}
        />
      ))}
    </div>
  );
}

/** Fallback global para `<Suspense>` em rotas lazy. */
export function RouteSkeleton() {
  return (
    <div className="max-w-4xl mx-auto p-6 space-y-4" data-testid="route-skeleton">
      <div className="h-8 w-1/3 rounded-md bg-muted animate-pulse" />
      <div className="h-4 w-2/3 rounded-md bg-muted animate-pulse" />
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-6">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-32 rounded-xl bg-muted animate-pulse" />
        ))}
      </div>
    </div>
  );
}
