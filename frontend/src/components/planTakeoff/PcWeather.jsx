import { useMemo, useState } from "react";
import { toast } from "sonner";
import { CloudRain, CloudSun, Snowflake, Sun, Cloud, CloudFog, ThermometerSnowflake, Droplets, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { computeSchedule } from "@/components/planTakeoff/PcGantt";

const wIcon = (code) => {
  if (code == null) return Cloud;
  if (code >= 71 && code <= 86) return Snowflake;
  if (code >= 51) return CloudRain;
  if (code >= 45) return CloudFog;
  if (code >= 1) return CloudSun;
  return Sun;
};
const fmt = (d) => d.toLocaleDateString("pt-PT", { weekday: "short", day: "2-digit", month: "2-digit" });

export default function PcWeather({ planning, start }) {
  const [city, setCity] = useState(() => localStorage.getItem("construpilot_site_city") || "");
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const rows = useMemo(() => computeSchedule(planning, start), [planning, start]);
  const pours = rows.filter((r) => /fondations|dalle|élévations|escalier/i.test(r.name));

  const load = async () => {
    if (!city.trim()) return toast.error("Indiquez la ville du chantier");
    setBusy(true);
    try {
      const { data: d } = await api.get(`/pc/weather?city=${encodeURIComponent(city.trim())}`);
      if (d.error) return toast.error(d.error);
      localStorage.setItem("construpilot_site_city", city.trim());
      setData(d);
      toast.success(`Météo chargée — ${d.city}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Météo indisponible"); }
    finally { setBusy(false); }
  };

  const byDate = useMemo(() => {
    const m = {};
    (data?.days || []).forEach((d) => { m[d.date] = d; });
    return m;
  }, [data]);

  return (
    <div className="space-y-2 mt-2" data-testid="pc-weather">
      <div className="flex items-center gap-2">
        <Input placeholder="Ville du chantier (ex : Marseille)" value={city}
               onChange={(e) => setCity(e.target.value)}
               onKeyDown={(e) => e.key === "Enter" && load()}
               data-testid="pc-weather-city-input"
               className="rounded-sm h-8 text-xs w-56" />
        <Button variant="outline" size="sm" onClick={load} disabled={busy}
                data-testid="pc-weather-load-btn" className="rounded-sm gap-1.5 h-8 text-xs">
          <CloudSun className="h-3.5 w-3.5" /> {busy ? "…" : "Météo coulage béton"}
        </Button>
        {data && <span className="text-[10px] text-muted-foreground">{data.city} · prévisions 16 j</span>}
      </div>
      {data && (
        <div className="grid sm:grid-cols-2 gap-2" data-testid="pc-weather-days">
          {pours.map((r, i) => {
            const iso = r.workStart.toISOString().slice(0, 10);
            const w = byDate[iso];
            const Icon = wIcon(w?.code);
            const frost = w && w.tmin != null && w.tmin <= 0;
            const rain = w && (w.precip || 0) >= 5;
            return (
              <div key={i} className={`rounded-sm border p-2 text-xs flex items-start gap-2 ${
                frost ? "border-red-500/50 bg-red-500/10"
                : rain ? "border-amber-500/50 bg-amber-500/10"
                : w ? "border-emerald-500/40 bg-emerald-500/5" : "border-border"}`}
                   data-testid={`pc-weather-pour-${i}`}>
                <Icon className={`h-5 w-5 shrink-0 ${frost ? "text-red-500" : rain ? "text-amber-500" : "text-sky-500"}`} />
                <div className="min-w-0">
                  <p className="font-medium truncate" title={r.name}>{r.name}</p>
                  <p className="text-muted-foreground num">{fmt(r.workStart)}</p>
                  {w ? (
                    <p className="num">
                      {Math.round(w.tmin)}° / {Math.round(w.tmax)}°
                      <Droplets className="inline h-3 w-3 ml-1 mr-0.5 text-sky-500" />{w.precip ?? 0} mm
                    </p>
                  ) : (
                    <p className="text-muted-foreground">Prévision indisponible (&gt; 16 j)</p>
                  )}
                  {frost && (
                    <p className="text-red-500 font-semibold flex items-center gap-1">
                      <ThermometerSnowflake className="h-3 w-3" /> Gel — coulage déconseillé
                    </p>
                  )}
                  {!frost && rain && (
                    <p className="text-amber-600 font-semibold flex items-center gap-1">
                      <CloudRain className="h-3 w-3" /> Pluie forte — protéger le coulage
                    </p>
                  )}
                  {!frost && !rain && w && (
                    <p className="text-emerald-600 font-medium flex items-center gap-1">
                      <CheckCircle2 className="h-3 w-3" /> Conditions OK pour couler
                    </p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
