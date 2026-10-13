import { Link } from "react-router-dom";
import { HardHat, User } from "lucide-react";

// Bouton bien visible de bascule d'audience (Pro <-> Particulier)
export const AudienceSwitch = ({ active = "pro", tone = "dark" }) => {
  const shell =
    tone === "dark"
      ? "bg-white/10 border border-white/15"
      : "bg-[#0F5257]/8 border border-[#0F5257]/20";
  const inactiveText = tone === "dark" ? "text-white/70 hover:text-white" : "text-[#0F5257]/70 hover:text-[#0F5257]";
  const activeCls =
    tone === "dark"
      ? "bg-primary text-primary-foreground shadow-md"
      : "bg-[#0F5257] text-white shadow-md";

  const Opt = ({ to, id, pref, icon: Icon, label, isActive }) => (
    <Link
      to={to}
      data-testid={id}
      onClick={() => { try { localStorage.setItem("construpilot_audience", pref); } catch (e) {} }}
      aria-current={isActive ? "page" : undefined}
      className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs sm:text-sm font-semibold transition-all ${
        isActive ? activeCls : inactiveText
      }`}
    >
      <Icon className="h-3.5 w-3.5" /> {label}
    </Link>
  );

  return (
    <div className={`inline-flex items-center gap-1 p-1 rounded-full ${shell}`} data-testid="nav-audience-switch-toggle">
      <Opt to="/" id="nav-audience-pro" pref="pro" icon={HardHat} label="Profissional" isActive={active === "pro"} />
      <Opt to="/particuliers" id="nav-audience-particulier" pref="particulier" icon={User} label="Particular" isActive={active === "particulier"} />
    </div>
  );
};

export default AudienceSwitch;
