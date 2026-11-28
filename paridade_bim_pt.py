"""Paridade .pt = .fr no fio do projeto, do lado do BIM (frontend/src/pages/BimViewer.jsx, rota /bim?atelier=<pid>).

No .fr o BIM Studio recebe o projeto do Ateliê, liga a maquete ao fio e tem «Continuar no Assistente». No .pt a ponte
Ateliê→BIM vive no BimViewer: junta-se aqui
  1) o botão «Continuar no Assistente» (/assistant?atelier=<pid>),
  2) o botão «Abrir no BIM Studio», que envia o IFC do projeto para /bim/models, LIGA a maquete ao fio (bim_model_id) e
     abre o BIM Studio — o mesmo resultado que o .fr faz sozinho.
Idempotente, tudo-ou-nada. Uso: python paridade_bim_pt.py  (a partir de /app)
"""
import os
import re
import sys

os.chdir(os.environ.get("APP_DIR", "/app"))
P = "frontend/src/pages/BimViewer.jsx"
s = open(P, encoding="utf-8").read()
if "bim-assistente-atelier" in s:
    print("já aplicado", P)
    sys.exit(0)
erros = []

FUNC = '''  // Fio do projeto: a maquete do Ateliê passa para o BIM Studio e fica ligada ao projeto (o mesmo que o .fr).
  const abrirAtelierNoStudio = async () => {
    if (!atelierId || studioBusy) return;
    setStudioBusy(true);
    try {
      const base = `/atelier-archi/projets/${encodeURIComponent(atelierId)}`;
      const { data: blob } = await api.get(`${base}/modelo.ifc`, { responseType: "blob" });
      const form = new FormData();
      form.append("file", new Blob([blob], { type: "application/x-step" }), "modelo.ifc");
      form.append("name", atelier?.titulo || "Projeto do Ateliê");
      const { data } = await api.post("/bim/models", form);
      api.post(`/fio-projeto/${encodeURIComponent(atelierId)}/ligar`, { campo: "bim_model_id", valor: String(data.model_id) }).catch(() => {});
      navigate(`/bim-studio?model=${encodeURIComponent(data.model_id)}&version=${data.version}`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Não foi possível abrir o projeto do Ateliê no BIM Studio.");
    } finally {
      setStudioBusy(false);
    }
  };
'''
m = re.search(r"^(\s*)const copyToStudio = async \(\) => \{", s, re.M)
if not m:
    erros.append("âncora «const copyToStudio = async () => {» não encontrada")
else:
    s = s[:m.start()] + FUNC + s[m.start():]

BOTOES = ('''
        {atelierId && !planId && (
          <Button size="sm" variant="outline" className="h-8 gap-1" onClick={() => navigate(`/assistant?atelier=${encodeURIComponent(atelierId)}`)} data-testid="bim-assistente-atelier">
            Continuar no Assistente
          </Button>
        )}
        {atelierId && !planId && (
          <Button size="sm" variant="outline" className="h-8 gap-1" onClick={abrirAtelierNoStudio} disabled={studioBusy} data-testid="bim-studio-atelier">
            Abrir no BIM Studio
          </Button>
        )}''')
m = re.search(r'data-testid="bim-voltar-atelier">[\s\S]{0,200}?</Button>\s*\n\s*\)\}', s)
if not m:
    erros.append("bloco do botão «bim-voltar-atelier» não encontrado")
else:
    s = s[:m.end()] + BOTOES + s[m.end():]

for nome in ("studioBusy", "setStudioBusy", "navigate", "toast", "api", "atelier", "atelierId", "planId"):
    if not re.search(rf"\b{nome}\b", s):
        erros.append(f"variável «{nome}» inexistente no ficheiro")

if erros:
    for e in erros:
        print("ERRO", P, e)
    print("NADA FOI ESCRITO")
    sys.exit(1)
open(P, "w", encoding="utf-8").write(s)
print("OK", P)
