import { useEffect, useState } from "react";
import { Monitor, Sun, Moon } from "lucide-react";

const KEY = "construpilot_theme";
const MODES = [
  { v: "auto", label: "Automático", icon: Monitor },
  { v: "light", label: "Claro", icon: Sun },
  { v: "dark", label: "Escuro", icon: Moon },
];

function applyTheme(mode) {
  const html = document.documentElement;
  let effective = mode;
  if (mode === "auto") {
    effective = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  if (effective === "dark") html.classList.add("dark");
  else html.classList.remove("dark");
}

export function initTheme() {
  const saved = localStorage.getItem(KEY) || "auto";
  applyTheme(saved);
  // Ouve mudanças do sistema quando modo é "auto"
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  const onChange = () => {
    if ((localStorage.getItem(KEY) || "auto") === "auto") applyTheme("auto");
  };
  mq.addEventListener?.("change", onChange);
}

export default function ThemeToggle({ className = "" }) {
  const [mode, setMode] = useState(() => localStorage.getItem(KEY) || "auto");

  useEffect(() => {
    localStorage.setItem(KEY, mode);
    applyTheme(mode);
  }, [mode]);

  return (
    <div
      className={`inline-flex rounded-lg border border-border bg-card p-1 gap-0.5 ${className}`}
      role="radiogroup"
      aria-label="Modo de cor"
      data-testid="theme-toggle"
    >
      {MODES.map(({ v, label, icon: Icon }) => (
        <button
          key={v}
          type="button"
          role="radio"
          aria-checked={mode === v}
          onClick={() => setMode(v)}
          className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded-md transition-colors min-h-[36px] ${
            mode === v
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground hover:bg-muted"
          }`}
          data-testid={`theme-toggle-${v}`}
        >
          <Icon className="h-3.5 w-3.5" aria-hidden="true" />
          <span>{label}</span>
        </button>
      ))}
    </div>
  );
}
