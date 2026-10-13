import { useEffect, useState } from "react";
import { Users } from "lucide-react";
import { api } from "@/lib/api";

export const SignupCounter = () => {
  const [count, setCount] = useState(null);
  useEffect(() => {
    let alive = true;
    const fetchCount = () => api.get("/leads/public-count").then(({ data }) => alive && setCount(data.count)).catch(() => {});
    fetchCount();
    const id = setInterval(fetchCount, 15000);
    return () => { alive = false; clearInterval(id); };
  }, []);
  return null; // Compteur masqué (pas de mention du nombre d'inscrits)
  // eslint-disable-next-line no-unreachable
  if (count === null) return null;
  return (
    <div className="flex items-center justify-center gap-2 text-xs text-muted-foreground py-2 bg-secondary/40" data-testid="signup-counter">
      <span className="relative flex h-2 w-2">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary/60" />
        <span className="relative inline-flex rounded-full h-2 w-2 bg-primary" />
      </span>
      <Users className="h-3.5 w-3.5 text-primary" />
      <b className="text-foreground num">{count.toLocaleString("pt-PT")}</b> profissionais da construção já aderiram ao ConstruPilot
    </div>
  );
};

export default SignupCounter;
