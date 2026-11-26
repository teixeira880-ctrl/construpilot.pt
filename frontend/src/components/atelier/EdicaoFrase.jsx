import { useEffect, useRef, useState } from "react";
import { Mic, MicOff, Send, Loader2, Wand2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { errorText } from "@/lib/errorText";

// Editar o projeto por frase, escrita ou dita: «aumenta a sala 2 metros», «janelas maiores no quarto 2», «piscina de 10 x 5».
// A voz usa o reconhecimento de fala do próprio browser (Chrome, Edge, Safari) — nada é gravado nem enviado além do texto.

const T = {
  pt: { titulo: "Editar por frase ou por voz", ph: "Ex.: aumenta a sala 2 metros · janelas maiores no quarto 2 · piscina de 10 x 5",
        ouvir: "Falar", parar: "Parar", enviar: "Aplicar", voz: "A ouvir…", semVoz: "Este browser não tem reconhecimento de voz.",
        exemplos: ["aumenta a sala 2 metros", "janelas maiores no quarto 2", "piscina de 10 x 5", "telhado de 4 águas"], lang: "pt-PT" },
  fr: { titulo: "Modifier par une phrase ou à la voix", ph: "Ex. : agrandis le séjour de 2 m · fenêtres plus grandes dans la chambre 2 · piscine de 10 x 5",
        ouvir: "Parler", parar: "Arrêter", enviar: "Appliquer", voz: "Écoute…", semVoz: "Ce navigateur n'a pas de reconnaissance vocale.",
        exemplos: ["agrandis le séjour de 2 m", "fenêtres plus grandes dans la chambre 2", "piscine de 10 x 5", "toit 4 pans"], lang: "fr-FR" },
  en: { titulo: "Edit with a sentence or by voice", ph: "E.g.: make the living room 2 m bigger · bigger windows in bedroom 2 · pool 10 x 5",
        ouvir: "Speak", parar: "Stop", enviar: "Apply", voz: "Listening…", semVoz: "This browser has no speech recognition.",
        exemplos: ["make the living room 2 m bigger", "bigger windows in bedroom 2", "pool 10 x 5", "hip roof"], lang: "en-GB" },
};

export default function EdicaoFrase({ pid, lang = "pt", onAlterado }) {
  const t = T[lang] || T.pt;
  const [frase, setFrase] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [resultado, setResultado] = useState(null);
  const [aOuvir, setAOuvir] = useState(false);
  const rec = useRef(null);
  const SR = typeof window !== "undefined" ? (window.SpeechRecognition || window.webkitSpeechRecognition) : null;

  useEffect(() => () => { try { rec.current?.stop(); } catch { /* */ } }, []);

  const aplicar = async (texto) => {
    const f = (texto ?? frase).trim();
    if (f.length < 2) return;
    setOcupado(true); setResultado(null);
    try {
      const { data } = await api.post(`/atelier-archi/projets/${pid}/frase`, { frase: f });
      setResultado({ feitos: data.feitos || [], falhas: data.falhas || [] });
      if (data.ok) { setFrase(""); onAlterado?.(data); }
    } catch (e) {
      setResultado({ feitos: [], falhas: [errorText(e)] });
    }
    setOcupado(false);
  };

  const ouvir = () => {
    if (!SR) { setResultado({ feitos: [], falhas: [t.semVoz] }); return; }
    if (aOuvir) { try { rec.current?.stop(); } catch { /* */ } return; }
    const r = new SR();
    r.lang = t.lang; r.interimResults = true; r.maxAlternatives = 1;
    r.onresult = (ev) => {
      const txt = Array.from(ev.results).map((x) => x[0].transcript).join(" ");
      setFrase(txt);
      if (ev.results[ev.results.length - 1].isFinal) aplicar(txt);
    };
    r.onend = () => setAOuvir(false);
    r.onerror = () => setAOuvir(false);
    rec.current = r;
    setAOuvir(true);
    r.start();
  };

  return (
    <section className="surface rounded-2xl p-4 space-y-2" data-testid="atelier-frase">
      <p className="font-medium flex items-center gap-1.5"><Wand2 className="h-4 w-4 text-primary" />{t.titulo}</p>
      <div className="flex gap-2">
        <Input value={frase} onChange={(e) => setFrase(e.target.value)} placeholder={aOuvir ? t.voz : t.ph}
          onKeyDown={(e) => { if (e.key === "Enter") aplicar(); }} data-testid="atelier-frase-input" />
        <Button variant={aOuvir ? "default" : "outline"} onClick={ouvir} title={aOuvir ? t.parar : t.ouvir} data-testid="atelier-frase-voz">
          {aOuvir ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
        </Button>
        <Button onClick={() => aplicar()} disabled={ocupado || frase.trim().length < 2} data-testid="atelier-frase-aplicar">
          {ocupado ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}<span className="hidden sm:inline ml-1">{t.enviar}</span>
        </Button>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {t.exemplos.map((x) => (
          <button key={x} type="button" className="text-xs rounded-full border border-border px-2.5 py-1 hover:border-primary/60" onClick={() => setFrase(x)}>{x}</button>
        ))}
      </div>
      {resultado && (
        <div className="text-xs space-y-0.5" data-testid="atelier-frase-resultado">
          {resultado.feitos.map((x, i) => <p key={`f${i}`} className="text-emerald-700">✓ {x}</p>)}
          {resultado.falhas.map((x, i) => <p key={`x${i}`} className="text-red-700">✗ {x}</p>)}
        </div>
      )}
    </section>
  );
}
