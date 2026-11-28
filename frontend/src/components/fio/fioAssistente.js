// Fio do projeto → Assistente: abre (ou retoma) a conversa ligada ao projeto do Ateliê e prepara o pedido.
import { useEffect } from "react";
import { api } from "@/lib/api";

const PROMPT = {
  pt: (pid) => `Projeto do Ateliê (projet_id: ${pid}). Lê-o com fio_ler_projeto e segue o fio sem perder dados e respeitando a geometria: `
    + "estudo térmico com as indicações para ser aprovado, plantas de execução, orçamento com as quantidades da maquete e dossier final com as imagens 3D e os renders. Começa por: ",
  fr: (pid) => `Projet de l'Atelier (projet_id: ${pid}). Lis-le avec fio_ler_projeto et suis le fil sans perdre de données et en respectant la géométrie : `
    + "étude thermique avec les indications pour qu'elle soit conforme, plans d'exécution, devis avec les quantités de la maquette et dossier final avec les images 3D et les rendus. Commence par : ",
  en: (pid) => `Atelier project (projet_id: ${pid}). Read it with fio_ler_projeto and follow the thread without losing data and respecting the geometry: `
    + "thermal study with what is needed for approval, execution drawings, quote from the model quantities and final dossier with 3D images and renders. Start with: ",
};

export function fioPrompt(pid, lang) {
  return (PROMPT[lang] || PROMPT.fr)(pid);
}

// Hook montado no Assistente: ?atelier=<pid> sem ?conversation → conversa do projeto (retomada ou nova) e ligação no fio.
export function useFioConversa(searchParams, setSearchParams, titulo) {
  const atelier = searchParams.get("atelier") || "";
  useEffect(() => {
    if (!atelier || searchParams.get("conversation")) return;
    let ativo = true;
    (async () => {
      try {
        let alvo = null;
        try {
          const [{ data: fio }, { data: lista }] = await Promise.all([
            api.get(`/fio-projeto/${encodeURIComponent(atelier)}`), api.get("/assistant/conversations")]);
          const ligadas = (fio.ligacoes || []).filter((l) => l.campo === "conversation_id").map((l) => l.valor);
          alvo = [...ligadas].reverse().map((id) => lista.find((c) => c.conversation_id === id)).find(Boolean) || null;
          titulo = titulo || fio?.projeto?.titulo;
        } catch { /* sem fio ainda: conversa nova */ }
        if (!alvo) {
          alvo = (await api.post("/assistant/conversations", { title: titulo ? String(titulo).slice(0, 120) : undefined })).data;
          api.post(`/fio-projeto/${encodeURIComponent(atelier)}/ligar`, { campo: "conversation_id", valor: alvo.conversation_id }).catch(() => {});
        }
        if (ativo) setSearchParams({ conversation: alvo.conversation_id, atelier }, { replace: true });
      } catch { /* o Assistente continua utilizável sem o fio */ }
    })();
    return () => { ativo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [atelier]);
  return atelier;
}

// Junta ao dossier do projeto uma imagem que o navegador já tem (vista 3D do BIM, render real): data URL ou Blob.
export async function guardarImagemNoFio(pid, imagem, tipo = "outra", legenda = "") {
  if (!pid || !imagem) return null;
  if (typeof imagem === "string") {
    const { data } = await api.post(`/fio-projeto/${encodeURIComponent(pid)}/imagens/b64`, { image_b64: imagem, tipo, legenda });
    return data;
  }
  const fd = new FormData();
  fd.append("file", imagem, "imagem.png"); fd.append("tipo", tipo); fd.append("legenda", legenda);
  const { data } = await api.post(`/fio-projeto/${encodeURIComponent(pid)}/imagens`, fd);
  return data;
}
