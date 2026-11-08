"""Dossier completo a partir de um processo já calculado (JSON), com as imagens FOTORREALISTAS reais
(cadeia OpenAI → Runway → Gemini, juiz Claude) — para correr no servidor que tem as chaves.

Uso:  PYTHONPATH=backend python scripts/urbanismo_pt/dossier_offline.py <processo.json> <pasta_saida>

Escreve na pasta: pecas_desenhadas.pdf, processo_licenciamento.zip, cada imagem (fotorrealista e exata) em JPEG
e imagens.json (fornecedor, geometria, verificada, tentativas). Só as imagens VERIFICADAS (geometria igual ao projeto)
entram no dossier; as restantes ficam na pasta, marcadas, para comparação. Não grava nada na base de dados.
"""
import asyncio
import io
import json
import os
import sys
import time

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "construpilot")

from engines.urbanismo_pt import pdf as UP, regras as R   # noqa: E402
from engines.urbanismo_pt.auto import coerencia as C, imagens as IM, interiores as INT, render3d as R3   # noqa: E402
from routes.urbanismo_auto import TITULOS_IMG, _anexar_relatorio, modelo3d   # noqa: E402

EXTERIORES = ["perspetiva", "piscina", "frente", "tardoz", "aerea", "perspetiva_entardecer"]


async def main(src: str, out: str) -> None:
    os.makedirs(out, exist_ok=True)
    d = json.load(open(src, encoding="utf-8"))
    m = modelo3d(d)
    sol = (d["auto"].get("implantacao") or {}).get("fachada_sol") or "frente"
    sem = asyncio.Semaphore(3)
    res = []
    t0 = time.time()

    async def ext(v):
        base, luz = IM.VARIANTES.get(v, (v, "dia"))
        ex = R3.vista(m, base, sol)
        open(f"{out}/exata_{v}.jpg", "wb").write(IM._jpeg(ex["png"], 92))
        async with sem:
            fr = await IM.fotorrealista(d, ex, sessao="dossier_offline", luz=luz, nome=v)
        res.append((v, fr))

    async def inte(nome, comp, piso):
        ex = INT.vista(d, nome, comp, piso)
        open(f"{out}/exata_{nome}.jpg", "wb").write(IM._jpeg(ex["png"], 92))
        async with sem:
            fr = await IM.fotorrealista(d, ex, sessao="dossier_offline", limiar=IM.LIMIAR_INTERIOR, nome=nome,
                                        prompt_fn=lambda estrito: INT.prompt_interior(d, nome, comp, estrito))
        res.append((nome, fr))

    vistas = [v for v in EXTERIORES if v != "piscina" or m.get("piscina")]
    await asyncio.gather(*[ext(v) for v in vistas], *[inte(n, c, p) for n, c, p in INT.escolher(d)],
                         return_exceptions=True)
    ordem = {v: k for k, v in enumerate(vistas + [n for n, _, _ in INT.escolher(d)])}
    res.sort(key=lambda t: ordem.get(t[0], 99))
    meta, sims = [], []
    imp = IM.implantacao_humanizada(m)
    open(f"{out}/implantacao.jpg", "wb").write(imp)
    sims.append({"code": "SIMULACOES_3D", "title": "Planta de implantação a cores (à escala)", "filename": "simulacao_01_implantacao.jpg",
                 "png": imp, "data": imp})
    for v, fr in res:
        nome = f"{'fotorrealista' if fr['tipo'] == 'fotorrealista' else 'exata'}_{v}{'' if fr['verificada'] else '_NAO_VERIFICADA'}.jpg"
        open(f"{out}/{nome}", "wb").write(fr["jpeg"])
        meta.append({"vista": v, "ficheiro": nome, **{k: fr.get(k) for k in ("tipo", "fornecedor", "geometria", "verificada",
                                                                             "qualidade", "tentativas", "nota")}})
        if fr["tipo"] == "fotorrealista" and fr["verificada"]:
            tit = f"Simulação fotorrealista — {TITULOS_IMG.get(v, v)} (geometria verificada com o projeto)"
            sims.append({"code": "SIMULACOES_3D", "title": tit, "filename": f"simulacao_{len(sims) + 1:02d}_{v}.jpg",
                         "png": fr["jpeg"], "data": fr["jpeg"]})
    json.dump(meta, open(f"{out}/imagens.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    open(f"{out}/pecas_desenhadas.pdf", "wb").write(UP.pecas_desenhadas_pdf(d, UP.desenhos(d, None) + sims))
    verif = R.verificar(d)
    coer = C.verificar(d, verif)
    z = UP.export_zip(d, verif, [{"code": s["code"], "filename": s["filename"], "data": s["data"]} for s in sims])
    open(f"{out}/processo_licenciamento.zip", "wb").write(_anexar_relatorio(z, d, coer))
    for x in meta:
        print(json.dumps({k: x[k] for k in ("vista", "tipo", "fornecedor", "geometria", "verificada")}, ensure_ascii=False))
    print("NO_DOSSIER", len(sims) - 1, "imagens fotorrealistas verificadas")
    print("SEGUNDOS", int(time.time() - t0))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2]))
