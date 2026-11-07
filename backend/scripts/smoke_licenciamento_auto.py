"""Teste real (rede) do piloto automático — só leitura, nada é gravado.

    cd backend && python scripts/smoke_licenciamento_auto.py "Rua do Monte 7, Padim da Graça, Braga"

Mostra, para cada fonte oficial, se respondeu e o que devolveu, e o resumo do processo gerado.
"""
import asyncio
import json
import sys
import time

sys.path.insert(0, ".")
from engines.urbanismo_pt.auto import geo as G  # noqa: E402
from engines.urbanismo_pt.auto import pipeline as P  # noqa: E402


async def main(morada: str):
    t0 = time.time()
    # conectividade bruta (estado HTTP por serviço; 0 = sem rede / bloqueado)
    for nome, url, params in (("NOMINATIM", G.NOMINATIM + "/search", {"q": "Braga", "format": "jsonv2", "limit": 1}),
                              ("PHOTON", G.PHOTON, {"q": "Braga", "limit": 1}),
                              ("DGT", G.DGT + "/collections", {"f": "json"}),
                              ("OVERPASS", G.OVERPASS, {"data": "[out:json];node(1);out;"}),
                              ("OPENTOPO", G.OPENTOPO, {"locations": "41.55,-8.42"})):
        st, js = await G._http("GET", url, params, None, "json")
        print("NET", nome, st, "json" if js is not None else "sem-dados")
    g = await G.geocode(morada)
    print("GEOCODE", json.dumps({k: g[k] for k in ("ok", "fonte", "nota")}, ensure_ascii=False), json.dumps(g.get("data"), ensure_ascii=False))
    if g["ok"]:
        lat, lon = g["data"]["lat"], g["data"]["lon"]
        cols = await G.dgt_collections()
        print("DGT_COLECOES", len(cols), [c["id"] for c in cols][:80])
        for nome, coro in (("MUNICIPIO", G.municipio(lat, lon)), ("CRUS", G.crus(lat, lon)), ("SRUP", G.servidoes(lat, lon)),
                           ("CADASTRO", G.cadastro(lat, lon)), ("VIA", G.via_proxima(lat, lon)), ("ORTO", G.ortofoto(lat, lon)),
                           ("ALTIMETRIA", G.elevacoes([(lat, lon), (lat + 0.0002, lon)]))):
            r = await coro
            data = r.get("data")
            if isinstance(data, dict) and "png" in data:
                data = {"png_bytes": len(data["png"]), "bbox": data.get("bbox")}
            print(nome, json.dumps({"ok": r["ok"], "fonte": r.get("fonte"), "nota": r.get("nota"), "data": data},
                                   ensure_ascii=False, default=str)[:900])
    r = await P.executar({"texto": f"quero uma autorização de construção na {morada}"})
    print("RESUMO", json.dumps(P.resumo_publico(r, "teste"), ensure_ascii=False, indent=1, default=str)[:5000])
    print(f"TEMPO {time.time() - t0:.1f} s")


asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "Rua do Monte 7, Padim da Graça, Braga"))
