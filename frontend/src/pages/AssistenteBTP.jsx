import React from "react";
import { Sparkles } from "lucide-react";
import AssistenteBTPChat from "@/components/btp/AssistenteBTPChat";

/**
 * Página do Assistente BTP (Fase B). Container simples que injecta o
 * componente de chat. O layout real vive no componente para permitir
 * reutilização noutros locais da plataforma.
 */
export default function AssistenteBTP() {
  return (
    <div className="min-h-[calc(100vh-72px)]">
      <div className="border-b border-slate-200 dark:border-slate-800 bg-white/70 dark:bg-slate-900/70 backdrop-blur">
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <img
              src="/assistente-obras-logo.png"
              alt=""
              className="h-8 w-8 rounded-md shadow-sm"
            />
            <div>
              <div className="font-semibold text-lg leading-tight">
                Assistente BTP
              </div>
              <div className="text-xs opacity-70 flex items-center gap-2">
                <span className="inline-flex items-center gap-1 bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 border border-indigo-500/30 px-2 py-0.5 rounded-full">
                  <Sparkles className="h-3 w-3" /> Autónomo
                </span>
                <span>Gemini pro-latest + flash-latest</span>
              </div>
            </div>
          </div>
          <a
            href="/btp-solver"
            className="text-xs opacity-70 hover:opacity-100 underline"
            data-testid="btp-legado-link"
          >
            Versão anterior
          </a>
        </div>
      </div>
      <AssistenteBTPChat />
    </div>
  );
}
