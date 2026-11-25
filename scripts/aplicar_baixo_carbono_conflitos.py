#!/usr/bin/env python3
"""Integração da Carta de obra de baixo carbono (commit 9dca665) nos 3 ficheiros que divergiram no Emergent.

Uso (no /app do Emergent, durante o cherry-pick em conflito) :
    git checkout --ours backend/engines/bet_core/assistant_tool.py backend/tests/bet_core/test_samples.py frontend/src/pages/ChantierDetail.jsx backend/server.py
    python3 scripts_tmp/aplicar_baixo_carbono_conflitos.py /app
Mantém TUDO o que já existe no HEAD (ZIP > 30 páginas, imagens 3D, quote_doc_id, separador « colab »…) e só ACRESCENTA
a carta de baixo carbono. Idempotente. Se uma âncora não for encontrada : sai com código 2 sem escrever nada.
Escrito pelo Claude — o agente só o executa.
"""
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "/app")
FALHAS = []


def edit(rel, fn):
    p = ROOT / rel
    s = p.read_text(encoding="utf-8")
    novo = fn(s)
    return p, s, novo


def need(cond, msg):
    if not cond:
        FALHAS.append(msg)


# --------------------------------------------------------------------------------------------- assistant_tool.py
def assistant(s):
    if "carbone_pdf" in s and "bas_carbone_etudes" in s:
        return s
    # 1) nome dos ficheiros entregues
    if '"Carta_baixo_carbono"' not in s:
        n = s.count("_BET_PREFIXES = (")
        need(n == 1, "assistant_tool: _BET_PREFIXES não encontrado")
        s = s.replace("_BET_PREFIXES = (", '_BET_PREFIXES = ("Carta_baixo_carbono", ', 1)
    # 2) formato pdf / xlsx
    m = re.search(r'fmt = \("pdf" if kind in \(([^)]*)\)', s)
    need(m is not None, "assistant_tool: linha fmt (pdf) não encontrada")
    if m and "carbone_pdf" not in m.group(1):
        s = s[:m.end(1)] + ', "carbone_pdf"' + s[m.end(1):]
    if 'kind == "estimate_xlsx"' in s:
        s = s.replace('kind == "estimate_xlsx"', 'kind in ("estimate_xlsx", "carbone_xlsx")', 1)
    else:
        m = re.search(r'"xlsx" if kind in \(([^)]*)\)', s)
        need(m is not None, "assistant_tool: linha fmt (xlsx) não encontrada")
        if m and "carbone_xlsx" not in m.group(1):
            s = s[:m.end(1)] + ', "carbone_xlsx"' + s[m.end(1):]
    # 3) títulos
    m = re.search(r'^( *)labels\["re2020_pdf"\] = [^\n]*\n', s, re.M)
    need(m is not None, 'assistant_tool: labels["re2020_pdf"] não encontrado')
    if m and 'labels["carbone_pdf"]' not in s:
        ind = m.group(1)
        s = s[:m.end()] + (f'{ind}labels["carbone_pdf"] = "Carta de obra de baixo carbono (dossier PDF)"\n'
                           f'{ind}labels["carbone_xlsx"] = "Carta de obra de baixo carbono (quadro Excel a completar)"\n') + s[m.end():]
    # 4) tipos guardados (todos os ciclos que incluem re2020_pdf)
    n = 0

    def add_kinds(mm):
        nonlocal n
        n += 1
        inner = mm.group(1)
        return mm.group(0) if "carbone_pdf" in inner else mm.group(0).replace(inner, inner + ', "carbone_pdf", "carbone_xlsx"', 1)
    s = re.sub(r'for kind in \(([^)]*"re2020_pdf"[^)]*)\)', add_kinds, s)
    need(n >= 1, 'assistant_tool: ciclo « for kind in (... "re2020_pdf") » não encontrado')
    # 5) dossier do estudo guardado para Obra › Baixo carbono (antes do passo « Terminé »)
    m = re.search(r'^( *)await step\("Terminé"', s, re.M)
    need(m is not None, 'assistant_tool: await step("Terminé" não encontrado')
    if m and "bas_carbone_etudes" not in s:
        i = m.group(1)
        bloco = (f'{i}if res.get("carbone_dossier"):        # retomado depois em Obra › Baixo carbono (importação do estudo)\n'
                 f'{i}    try:\n'
                 f'{i}        await db.bas_carbone_etudes.update_one(\n'
                 f'{i}            {{"user_id": uid, "job_id": job_id}},\n'
                 f'{i}            {{"$set": {{"user_id": uid, "job_id": job_id, "conversation_id": cid, "dossier": res["carbone_dossier"],\n'
                 f'{i}                      "nom": (res["carbone_dossier"].get("projet") or {{}}).get("nom") or "", "created_at": _now()}}}}, upsert=True)\n'
                 f'{i}    except Exception:  # noqa: BLE001\n'
                 f'{i}        log.warning("baixo carbono: dossier do estudo não guardado", exc_info=True)\n')
        s = s[:m.start()] + bloco + s[m.start():]
    return s


# --------------------------------------------------------------------------------------------- test_samples.py
def samples(s):
    if "carbone_pdf" in s:
        return s
    linhas = s.split("\n")
    ok = False
    out = []
    for ln in linhas:
        out.append(ln)
        if '"kind"' in ln and 'st["artifacts"]' in ln and "assert" in ln and "==" in ln:
            ind = ln[:len(ln) - len(ln.lstrip())]
            if re.search(r'st\["artifacts"\]\]\[:\d+\] ==', ln):          # lista parcial ([:5]) : asserção acrescentada à parte
                out.append(f'{ind}assert {{"carbone_pdf", "carbone_xlsx"}} <= {{a["kind"] for a in st["artifacts"]}}   # + carta de baixo carbono')
            else:                                                             # lista completa : os 2 entregáveis no fim
                j = ln.rfind("]")
                out[-1] = ln[:j] + ', "carbone_pdf", "carbone_xlsx"' + ln[j:] + "   # + carta de baixo carbono"
            ok = True
            break
    if ok:
        out += linhas[len(out) - (1 if re.search(r'carbone_pdf", "carbone_xlsx"\} <=', out[-1]) else 0):]
    need(ok, "test_samples: asserção da lista de entregáveis não encontrada")
    return "\n".join(out)


# --------------------------------------------------------------------------------------------- ChantierDetail.jsx
def chantier(s):
    if "BasCarbonePanel" in s:
        return s
    m = re.search(r'^import \{ ReceptionPanel \} from "@/components/chantiers/ReceptionPanel";\n', s, re.M)
    need(m is not None, "ChantierDetail: import ReceptionPanel não encontrado")
    if m:
        s = s[:m.end()] + 'import { BasCarbonePanel } from "@/components/chantiers/BasCarbonePanel";\n' + s[m.end():]
    m = re.search(r'\[([^\[\]]*"reception"[^\[\]]*)\]\.includes\(requestedTab\)', s)
    need(m is not None, "ChantierDetail: lista .includes(requestedTab) com « reception » não encontrada")
    if m:
        s = s[:m.end(1)] + ', "carbone"' + s[m.end(1):]
    n = s.count('["reception", "Receção"]')
    need(n == 1, "ChantierDetail: separador [\"reception\", \"Receção\"] não encontrado (ou repetido)")
    s = s.replace('["reception", "Receção"]', '["carbone", "Baixo carbono"], ["reception", "Receção"]', 1)
    m = re.search(r'^( *)\{tab === "reception" && <ReceptionPanel[^\n]*\n', s, re.M)
    need(m is not None, "ChantierDetail: render do ReceptionPanel não encontrado")
    if m:
        s = s[:m.end()] + f'{m.group(1)}{{tab === "carbone" && <BasCarbonePanel chantierId={{chantierId}} />}}\n' + s[m.end():]
    return s


# --------------------------------------------------------------------------------------------- server.py (v3)
def server(s):
    if "bas_carbone_routes" not in s:
        m = re.search(r'^api_router\.include_router\(chantiers_routes\.router\)\n', s, re.M)
        need(m is not None, "server.py: api_router.include_router(chantiers_routes.router) não encontrado")
        if m:
            s = s[:m.end()] + ('from routes import bas_carbone as bas_carbone_routes  # noqa: E402\n'
                               'api_router.include_router(bas_carbone_routes.router)\n') + s[m.end():]
    if '"bas_carbone_chantier"' not in s:
        m = re.search(r'^( *)await db\.chantiers\.create_index\("chantier_id", unique=True\)\n', s, re.M)
        need(m is not None, 'server.py: create_index("chantier_id", unique=True) não encontrado')
        if m:
            i = m.group(1)
            s = s[:m.end()] + (f'{i}await db.bas_carbone.create_index([("chantier_id", 1), ("user_id", 1)], unique=True, name="bas_carbone_chantier")\n'
                               f'{i}await db.bas_carbone_etudes.create_index([("user_id", 1), ("job_id", 1)], unique=True, name="bas_carbone_etude_job")\n') + s[m.end():]
    return s


ALVOS = [("backend/engines/bet_core/assistant_tool.py", assistant), ("backend/tests/bet_core/test_samples.py", samples),
         ("frontend/src/pages/ChantierDetail.jsx", chantier), ("backend/server.py", server)]
resultados = [edit(rel, fn) for rel, fn in ALVOS]
for rel, _ in ALVOS:
    txt = (ROOT / rel).read_text(encoding="utf-8")
    need("<<<<<<<" not in txt and ">>>>>>>" not in txt, f"{rel}: ainda tem marcadores de conflito — fazer antes git checkout --ours")
if FALHAS:
    print("FALHA — nada foi escrito :")
    for f in FALHAS:
        print(" -", f)
    sys.exit(2)
for p, antes, depois in resultados:
    if antes != depois:
        p.write_text(depois, encoding="utf-8")
    print(("ALTERADO  " if antes != depois else "JÁ OK     ") + str(p.relative_to(ROOT)))
print("OK")
