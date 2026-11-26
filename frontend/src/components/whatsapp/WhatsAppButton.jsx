import { useState } from "react";
import { X } from "lucide-react";
import { WA } from "./txt";

/** Logótipo WhatsApp (traço simples, sem dependências). */
export const WaIcon = ({ className = "h-6 w-6" }) => (
  <svg viewBox="0 0 32 32" className={className} aria-hidden="true" fill="currentColor">
    <path d="M16.04 3C9.4 3 4 8.36 4 14.96c0 2.3.66 4.46 1.82 6.3L4 29l7.96-1.78a12.1 12.1 0 0 0 4.08.7C22.66 27.92 28 22.56 28 15.96 28 9.36 22.66 3 16.04 3Zm0 22.7c-1.3 0-2.56-.24-3.74-.7l-.27-.1-4.72 1.06 1.08-4.5-.17-.29a9.6 9.6 0 0 1-1.5-5.2c0-5.34 4.4-9.7 9.32-9.7 5.06 0 9.6 4.36 9.6 9.7s-4.4 9.73-9.6 9.73Zm5.3-7.25c-.29-.15-1.72-.85-1.99-.94-.27-.1-.46-.15-.66.14-.2.3-.76.94-.93 1.13-.17.2-.34.22-.63.07-.29-.14-1.22-.45-2.32-1.43-.86-.76-1.44-1.7-1.61-1.99-.17-.29-.02-.45.13-.59.13-.13.29-.34.44-.51.14-.17.19-.29.29-.49.1-.19.05-.37-.03-.51-.07-.15-.66-1.58-.9-2.16-.24-.57-.48-.49-.66-.5h-.56c-.2 0-.51.07-.78.36-.27.3-1.02 1-1.02 2.42 0 1.43 1.05 2.81 1.19 3 .15.2 2.06 3.13 4.98 4.39.7.3 1.24.48 1.67.61.7.22 1.34.19 1.84.12.56-.08 1.72-.7 1.97-1.38.24-.68.24-1.26.17-1.38-.07-.12-.27-.2-.56-.34Z" />
  </svg>
);

/**
 * Botão WhatsApp flutuante com os contactos que a empresa escolheu para este sítio
 * (gerente e colaboradores). `contactos` = [{ nome, funcao, link }] vindos do servidor; nada se mostra se vazio.
 */
export default function WhatsAppButton({ contactos, inline = false }) {
  const [aberto, setAberto] = useState(false);
  if (!contactos?.length) return null;
  const um = contactos.length === 1;
  const btn = "inline-flex items-center gap-2 rounded-full bg-[#25D366] text-white font-semibold shadow-lg hover:bg-[#1ebe5b] focus:outline-none focus:ring-4 focus:ring-[#25D366]/40 transition";
  const principal = um
    ? <a href={contactos[0].link} target="_blank" rel="noopener noreferrer" className={`${btn} px-4 py-3`} data-testid="whatsapp-btn" aria-label={`${WA.falar} ${contactos[0].nome}`}><WaIcon /> <span className="hidden sm:inline">{WA.falar_whatsapp}</span></a>
    : <button type="button" onClick={() => setAberto((x) => !x)} className={`${btn} px-4 py-3`} aria-expanded={aberto} data-testid="whatsapp-btn"><WaIcon /> <span className="hidden sm:inline">{WA.falar_whatsapp}</span></button>;
  return (
    <div className={inline ? "relative inline-block" : "fixed bottom-5 right-5 z-50 print:hidden"} data-testid="whatsapp-widget">
      {aberto && !um && (
        <div className={`${inline ? "absolute bottom-14 right-0" : "absolute bottom-16 right-0"} w-72 rounded-2xl border border-slate-200 bg-white text-slate-900 shadow-2xl overflow-hidden`} role="dialog" aria-label={WA.escolha}>
          <div className="flex items-center justify-between bg-[#075E54] text-white px-4 py-3"><span className="text-sm font-semibold">{WA.escolha}</span>
            <button type="button" onClick={() => setAberto(false)} aria-label={WA.fechar}><X className="h-4 w-4" /></button></div>
          <ul className="divide-y">{contactos.map((c, i) => (
            <li key={i}><a href={c.link} target="_blank" rel="noopener noreferrer" className="flex items-center gap-3 px-4 py-3 hover:bg-emerald-50" data-testid={`whatsapp-contacto-${i}`}>
              <span className="h-9 w-9 rounded-full bg-[#25D366]/15 text-[#128C7E] grid place-items-center font-bold shrink-0">{(c.nome || "?").trim().charAt(0).toUpperCase()}</span>
              <span className="min-w-0 flex-1"><span className="block text-sm font-semibold truncate">{c.nome}</span>{c.funcao && <span className="block text-xs text-slate-500 truncate">{c.funcao}</span>}</span>
              <WaIcon className="h-5 w-5 text-[#25D366]" /></a></li>))}</ul>
        </div>)}
      {principal}
    </div>
  );
}
