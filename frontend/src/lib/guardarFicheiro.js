// Descarregar uma imagem/ficheiro de forma fiável em todos os aparelhos.
// iPad/iPhone (Safari) ignoram muitas vezes <a download> com endereços data: e com blob: revogados logo a seguir ao clique:
// aí usamos a folha de partilha do sistema («Guardar imagem» / «Guardar em Ficheiros»); sem ela, abrimos o ficheiro num
// separador novo para o utilizador o guardar. Nos computadores e no Android: descarga direta.

export function dataUrlParaBlob(dataUrl) {
  const [cab, dados = ""] = String(dataUrl).split(",", 2);
  const mime = (cab.match(/data:([^;]+)/) || [])[1] || "application/octet-stream";
  const bin = /;base64/i.test(cab) ? atob(dados) : decodeURIComponent(dados);
  const u8 = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) u8[i] = bin.charCodeAt(i);
  return new Blob([u8], { type: mime });
}

const eIOS = () => {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent || "";
  return /iPad|iPhone|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);   // iPadOS diz-se «Macintosh»
};

// `fonte`: Blob, endereço data: ou blob:. Chamar diretamente no clique (sem await antes) para a partilha ser autorizada.
export async function guardarFicheiro(fonte, nome) {
  let blob = fonte instanceof Blob ? fonte : null;
  if (!blob && typeof fonte === "string" && fonte.startsWith("data:")) blob = dataUrlParaBlob(fonte);
  if (!blob && typeof fonte === "string") blob = await (await fetch(fonte)).blob();
  if (!blob) return false;
  const tipo = blob.type || "application/octet-stream";
  if (eIOS() && typeof File !== "undefined" && navigator.canShare) {
    try {
      const f = new File([blob], nome, { type: tipo });
      if (navigator.canShare({ files: [f] })) {
        await navigator.share({ files: [f], title: nome });
        return true;
      }
    } catch (e) {
      if (e && e.name === "AbortError") return false;          // o utilizador fechou a folha de partilha
    }
  }
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = nome; a.rel = "noopener"; a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  a.remove();
  if (eIOS()) {                                              // Safari antigo sem partilha de ficheiros: abre para guardar
    setTimeout(() => { try { window.open(url, "_blank"); } catch { /* */ } }, 300);
  }
  setTimeout(() => URL.revokeObjectURL(url), 60000);
  return true;
}
