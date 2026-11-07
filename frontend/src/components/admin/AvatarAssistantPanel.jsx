import { useEffect, useState } from "react";
import { Video, PhoneOff, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { avatarStore, preloadAvatar, startAvatar, stopAvatar } from "@/components/admin/AvatarDock";

// Assistant vidéo interne : lance l'assistante, qui s'affiche ensuite dans un coin de l'écran
// (fenêtre flottante AvatarDock) et reste là quand on change de page.
const PT = typeof window !== "undefined" && /construpilot\.pt|construpilot-recon/.test(window.location.hostname);
const LANG_LABEL = {
  auto: PT ? "Automático (a língua em que fala)" : "Automatique (la langue dans laquelle vous parlez)",
  pt: "Português (PT)", fr: "Français", en: "English", es: "Español", it: "Italiano", de: "Deutsch", nl: "Nederlands",
  pl: "Polski", ro: "Română", uk: "Українська", ar: "العربية", zh: "中文", tr: "Türkçe", ru: "Русский", ja: "日本語",
};
const MAIN = ["auto", "pt", "fr", "en"];
const T = PT ? {
  title: "Assistente de vídeo da equipa",
  desc: "Uso interno apenas. A assistente aparece num canto do ecrã e fica lá enquanto navega. Lê os dados do site e, a seu pedido, mexe no site à sua frente (páginas, Assistente BTP, orçamentos, faturas…). Cada alteração espera pelo seu «sim»; pagamentos, palavras-passe e eliminações definitivas continuam proibidos.",
  notconf: "Não configurado: adicione LIVEKIT_URL, LIVEKIT_API_KEY e LIVEKIT_API_SECRET às variáveis do backend.",
  talk: "Falar", stop: "Terminar", hint: "Clique em Falar e autorize o microfone.", live: "Em direto — fale, a assistente está a ouvir (canto inferior direito).",
  connecting: "A ligar…", waiting: "Ligado — a assistente está a chegar (até 60 s na primeira vez)…",
} : {
  title: "Assistant vidéo de l'équipe",
  desc: "Usage interne uniquement. L'assistante s'affiche dans un coin de l'écran et y reste pendant la navigation. Elle lit les données du site et, à votre demande, agit sur le site sous vos yeux (pages, Assistant BTP, devis, factures…). Chaque modification attend votre « oui » ; paiements, mots de passe et suppressions définitives restent interdits.",
  notconf: "Non configuré : ajoutez LIVEKIT_URL, LIVEKIT_API_KEY et LIVEKIT_API_SECRET aux variables du backend.",
  talk: "Parler", stop: "Terminer", hint: "Cliquez sur Parler et autorisez le micro.", live: "En direct — parlez, l'assistante vous écoute (coin inférieur droit).",
  connecting: "Connexion…", waiting: "Connecté — l'assistante arrive (jusqu'à 60 s la première fois)…",
};

export default function AvatarAssistantPanel() {
  const [status, setStatus] = useState(null);
  const [s, setS] = useState(avatarStore.get());
  const [lang, setLang] = useState(PT ? "pt" : "fr");
  useEffect(() => avatarStore.subscribe(setS), []);
  useEffect(() => { preloadAvatar().catch(() => {}); }, []);
  useEffect(() => {
    api.get("/admin/avatar/status")
      .then(({ data }) => { setStatus(data); if (data.default_lang) setLang(data.default_lang); })
      .catch(() => setStatus({ configured: false }));
  }, []);
  const langs = status?.langs?.length ? status.langs : ["fr", "pt", "en"];
  const idle = s.phase === "idle";
  const busy = s.phase === "connecting" || s.phase === "waiting";
  const line = s.message || { idle: T.hint, connecting: T.connecting, waiting: T.waiting, live: T.live }[s.phase];
  return (
    <div className="space-y-4" data-testid="admin-avatar-panel">
      <div>
        <h3 className="text-lg font-semibold">{T.title}</h3>
        <p className="text-sm text-muted-foreground">{T.desc}</p>
      </div>
      {status && !status.configured && (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm" data-testid="admin-avatar-not-configured">{T.notconf}</div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        {langs.filter((l) => MAIN.includes(l)).map((l) => (
          <Button key={l} type="button" variant={lang === l ? "default" : "outline"} className="rounded-sm" disabled={!idle} onClick={() => setLang(l)}>
            {l === "auto" ? (PT ? "Auto" : "Auto") : LANG_LABEL[l] || l}
          </Button>
        ))}
        {langs.some((l) => !MAIN.includes(l)) && (
          <select aria-label={PT ? "Outras línguas" : "Autres langues"} data-testid="admin-avatar-lang-more" disabled={!idle}
            className="h-9 rounded-sm border bg-background px-2 text-sm" value={MAIN.includes(lang) ? "" : lang}
            onChange={(e) => e.target.value && setLang(e.target.value)}>
            <option value="">{PT ? "Outras línguas…" : "Autres langues…"}</option>
            {langs.filter((l) => !MAIN.includes(l)).map((l) => <option key={l} value={l}>{LANG_LABEL[l] || l}</option>)}
          </select>)}
        {idle ? (
          <Button type="button" className="rounded-sm" onClick={() => startAvatar(lang)} disabled={!status?.configured} data-testid="admin-avatar-start">
            <Video className="mr-2 h-4 w-4" /> {T.talk}
          </Button>
        ) : (
          <Button type="button" variant="destructive" className="rounded-sm" onClick={stopAvatar} data-testid="admin-avatar-stop">
            {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <PhoneOff className="mr-2 h-4 w-4" />} {T.stop}
          </Button>
        )}
      </div>
      <p className="text-sm text-muted-foreground" data-testid="admin-avatar-status">{line}</p>
    </div>
  );
}
