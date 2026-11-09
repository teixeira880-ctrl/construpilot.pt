// Comptes multilingues (users.doc_langs, ex. CLT Rezult : ["en", "uk"]).
// Le PDF principal sort dans la 1re langue (imposée côté serveur) ; ce helper télécharge
// automatiquement les versions supplémentaires (ex. ukrainien) juste après.
import { api } from "@/lib/api";
import { filenameFromResponse } from "@/lib/downloadName";

export function extraDocLangs(user) {
  const langs = Array.isArray(user?.doc_langs) ? user.doc_langs : [];
  return langs.slice(1);
}

export async function downloadExtraPdfs(user, docId, fallbackName = "document") {
  for (const lg of extraDocLangs(user)) {
    try {
      const res = await api.get(`/documents/${docId}/pdf`, { params: { lang: lg }, responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = filenameFromResponse(res, `${fallbackName}_${lg.toUpperCase()}.pdf`);
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      /* la version principale est déjà téléchargée ; on n'interrompt pas l'utilisateur */
    }
  }
}
