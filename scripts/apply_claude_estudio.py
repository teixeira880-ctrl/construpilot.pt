#!/usr/bin/env python3
"""Liga o Estúdio de Projeto (modelo único) aos dois ficheiros existentes que ele toca. Idempotente.

Uso (na raiz da aplicação):  python3 scripts/apply_claude_estudio.py [--check]
Os ficheiros novos vêm do ramo com `git checkout FETCH_HEAD -- <ficheiros>`; este script só faz as ligações:
  backend/server.py                        → regista as rotas /api/estudio-projeto
  frontend/src/pages/LicenciamentoAuto.jsx → cartão «Estúdio de Projeto» na página do processo
Se uma âncora não existir exatamente uma vez, escreve ERRO e não altera nada.
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CHECK = "--check" in sys.argv

EDICOES = {
    "backend/server.py": ("estudio_projeto_routes", [
        ("api_router.include_router(urbanismo_auto_routes.router)\n",
         "api_router.include_router(urbanismo_auto_routes.router)\n"
         "from routes import estudio_projeto as estudio_projeto_routes  # noqa: E402  — Estúdio de Projeto (modelo único do edifício)\n"
         "api_router.include_router(estudio_projeto_routes.router)\n"),
    ]),
    "backend/routes/urbanismo_auto.py": ("_estudio.anexar_ao_zip", [
        ('    data = await _anexar_blender(data, d, pid, user["user_id"])\n',
         '    data = await _anexar_blender(data, d, pid, user["user_id"])\n'
         '    from routes import estudio_projeto as _estudio  # noqa: PLC0415 — pasta «Estudio-de-Projeto» quando há modelo guardado\n'
         '    data = await _estudio.anexar_ao_zip(data, pid, user["user_id"])\n'),
    ]),
    "backend/engines/assistant_autorizacao_tool.py": ("assistant_estudio_tool", [
        ('AUTORIZACAO_TOOL_NAMES = {t["name"] for t in AUTORIZACAO_TOOLS}\n',
         'from engines.assistant_estudio_tool import ESTUDIO_INSTRUCTIONS, ESTUDIO_TOOL_NAMES, ESTUDIO_TOOLS, run_estudio_tool  # noqa: E402\n'
         'AUTORIZACAO_TOOLS += ESTUDIO_TOOLS        # Estúdio de Projeto: ver e editar o modelo do edifício\n'
         'AUTORIZACAO_TOOL_NAMES = {t["name"] for t in AUTORIZACAO_TOOLS}\n'),
        ('\n\ndef _pedido(args: dict) -> dict:\n',
         '\nAUTORIZACAO_INSTRUCTIONS += ESTUDIO_INSTRUCTIONS\n\n\ndef _pedido(args: dict) -> dict:\n'),
        ('async def run_autorizacao_tool(name: str, args: dict, user: dict, conv: dict) -> dict:\n',
         'async def run_autorizacao_tool(name: str, args: dict, user: dict, conv: dict) -> dict:\n'
         '    if name in ESTUDIO_TOOL_NAMES:\n        return await run_estudio_tool(name, args, user, conv)\n'),
    ]),
    "frontend/src/pages/LicenciamentoAuto.jsx": ("EstudioProjetoLazy", [
        ('import { useCallback, useEffect, useRef, useState } from "react";',
         'import { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react";'),
        ('Loader2, MapPin, ShieldCheck, Sparkles, Wand2 } from "lucide-react";',
         'Loader2, MapPin, PenLine, ShieldCheck, Sparkles, Wand2 } from "lucide-react";'),
        ('import ImagensBlender from "@/components/licenciamento/ImagensBlender";\n',
         'import ImagensBlender from "@/components/licenciamento/ImagensBlender";\n\n'
         '// Estúdio de Projeto (editor do modelo único): só é carregado quando o utilizador o abre\n'
         'const EstudioProjetoLazy = lazy(() => import("@/components/licenciamento/EstudioProjeto"));\n'),
        ('  const [erro, setErro] = useState("");\n  const casa = useRef(null);\n',
         '  const [erro, setErro] = useState("");\n  const [estudio, setEstudio] = useState(false);\n  const casa = useRef(null);\n'),
        ('      <ImagensBlender pid={pid} />\n',
         '      <Card className="p-4 space-y-3" data-testid="lic-auto-estudio">\n'
         '        <div className="flex flex-wrap items-center justify-between gap-2">\n'
         '          <div className="font-medium flex items-center gap-2"><PenLine className="h-4 w-4" />Estúdio de Projeto</div>\n'
         '          <Button size="sm" variant={estudio ? "outline" : "default"} onClick={() => setEstudio(x => !x)} data-testid="lic-auto-estudio-abrir">\n'
         '            {estudio ? "Fechar o Estúdio" : "Abrir o Estúdio"}</Button>\n'
         '        </div>\n'
         '        {!estudio && <p className="text-sm text-muted-foreground">Edite a casa em planta — paredes, portas, janelas, pisos e cobertura. O 3D,\n'
         '          os alçados, os cortes e as medições são calculados a partir do mesmo modelo, com as medidas deste processo como ponto de partida.</p>}\n'
         '        {estudio && <Suspense fallback={<div className="p-8 flex justify-center"><Loader2 className="h-6 w-6 animate-spin" /></div>}><EstudioProjetoLazy pid={pid} /></Suspense>}\n'
         '      </Card>\n\n'
         '      <ImagensBlender pid={pid} />\n'),
    ]),
}


def main() -> int:
    novos = {}
    for rel, (marca, pares) in EDICOES.items():
        f = RAIZ / rel
        if not f.exists():
            print(f"ERRO ficheiro em falta: {rel}")
            return 1
        s = f.read_text(encoding="utf-8")
        if marca in s:
            print(f"JA_APLICADO {rel}")
            continue
        for antes, depois in pares:
            if s.count(antes) != 1:
                print(f"ERRO âncora encontrada {s.count(antes)}× em {rel}: {antes[:70]!r}")
                return 1
            s = s.replace(antes, depois)
        novos[f] = s
    for f, s in novos.items():
        if not CHECK:
            f.write_text(s, encoding="utf-8")
        print(f"{'VERIFICADO' if CHECK else 'OK'} {f.relative_to(RAIZ)}")
    print("FIM_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
