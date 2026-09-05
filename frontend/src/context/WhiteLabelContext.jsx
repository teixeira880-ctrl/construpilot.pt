import { createContext, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";

/**
 * Contexte White Label : lit ?tenant=slug dans l'URL et charge la config.
 * Applique la couleur primaire via CSS variable, et fournit tenant metadata.
 */
const Ctx = createContext(null);

const readTenantFromUrl = () => {
  try {
    const u = new URL(window.location.href);
    return u.searchParams.get("tenant");
  } catch { return null; }
};

const hexToHsl = (hex) => {
  if (!hex || hex[0] !== "#") return null;
  const r = parseInt(hex.slice(1, 3), 16) / 255;
  const g = parseInt(hex.slice(3, 5), 16) / 255;
  const b = parseInt(hex.slice(5, 7), 16) / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  let h = 0, s = 0; const l = (max + min) / 2;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: h = (g - b) / d + (g < b ? 6 : 0); break;
      case g: h = (b - r) / d + 2; break;
      default: h = (r - g) / d + 4;
    }
    h /= 6;
  }
  return `${Math.round(h * 360)} ${Math.round(s * 100)}% ${Math.round(l * 100)}%`;
};

export const WhiteLabelProvider = ({ children }) => {
  const [tenant, setTenant] = useState(null);
  useEffect(() => {
    const slug = readTenantFromUrl() || sessionStorage.getItem("construpilot_tenant");
    if (!slug) return;
    sessionStorage.setItem("construpilot_tenant", slug);
    api.get(`/whitelabel/config?tenant=${encodeURIComponent(slug)}`).then(({ data }) => {
      if (data && data.tenant_slug) {
        setTenant(data);
        const hsl = hexToHsl(data.primary_color || "#FF5A00");
        if (hsl) document.documentElement.style.setProperty("--primary", hsl);
        if (data.partner_name) document.title = `${data.partner_name} — powered by ConstruPilot`;
      }
    }).catch(() => {});
  }, []);
  return <Ctx.Provider value={{ tenant }}>{children}</Ctx.Provider>;
};

export const useWhiteLabel = () => useContext(Ctx) || { tenant: null };
