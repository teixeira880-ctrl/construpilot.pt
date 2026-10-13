import { useState } from "react";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/context/I18nContext";
import { useConfirm } from "@/components/ConfirmProvider";

const COPY = {
  fr: { notice: "Ce document a changé dans une autre fenêtre ou dans l’assistant. Vos modifications n’ont pas été enregistrées.", reload: "Charger la version enregistrée", confirm: "Remplacer vos modifications locales par la version actuellement enregistrée ?" },
  pt: { notice: "Este documento mudou noutra janela ou no assistente. As suas alterações não foram guardadas.", reload: "Carregar a versão guardada", confirm: "Substituir as alterações locais pela versão atualmente guardada?" },
  en: { notice: "This document changed in another window or in the assistant. Your edits have not been saved.", reload: "Load saved version", confirm: "Replace your local edits with the currently saved version?" },
};
export const DocumentVersionNotice = ({ onReload }) => {
  const { lang } = useI18n();
  const text = COPY[lang] || COPY.fr;
  const confirm = useConfirm();
  const [busy, setBusy] = useState(false);
  const reload = async () => {
    if (!await confirm({ title: text.confirm, description: text.notice, confirmLabel: text.reload,
      cancelLabel: lang === "pt" ? "Cancelar" : lang === "en" ? "Cancel" : "Annuler", destructive: false })) return;
    setBusy(true);
    try { await onReload(); } finally { setBusy(false); }
  };
  return <div role="alert" className="grid gap-3 border-l-2 border-amber-500 p-3 text-sm" data-testid="editor-version-conflict"><p>{text.notice}</p><Button type="button" variant="outline" disabled={busy} onClick={reload} className="w-fit max-w-full whitespace-normal h-auto min-h-9 py-2" data-testid="editor-reload-latest"><RefreshCw size={15} />{text.reload}</Button></div>;
};