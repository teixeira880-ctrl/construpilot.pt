"""Aplica no pod a regra AI/AS no caminho clássico de compute_volumes (23/11/2026, testes de Martinho em Suresnes e AES/TZ):
1) cross_layer_faces.py inteiro (versão 8cd27c6 do GitHub, já transferida para /tmp/cross_layer_faces.github.py):
   lê também os símbolos de laje Revit (cota + espessura separados), a norma AES «b» (bruto = AS) / «f» (acabado, nunca AS),
   e separa os Ai de lintéis/vigas/trémies dos Ai de laje. Só substitui se o ficheiro do pod for idêntico à versão ad340d8.
2) volumes_tool.py, caminho clássico (sem símbolos de laje do pod): AI = texto «Ai:» de laje mais frequente quando não há
   etiqueta de laje; base das paredes = AS dominante lida nas etiquetas do DXF do piso inferior (lower_dxf_bytes), que o
   pod já recebe via lower_dxf_plan_id. Tudo-ou-nada: verifica todas as âncoras antes de escrever."""
import hashlib
import subprocess
import sys

PLAN = []

def patch(path, pairs, marker):
    s = open(path, encoding="utf-8").read()
    if marker in s:
        print("já aplicado", path); return
    for old, new, label in pairs:
        if s.count(old) != 1:
            print(f"ERRO {path}: âncora «{label}» encontrada {s.count(old)}× (esperado 1)"); sys.exit(1)
        s = s.replace(old, new, 1)
    PLAN.append((path, s))

# ---- 1) cross_layer_faces.py: substituição integral segura
CL = "backend/engines/metre/cross_layer_faces.py"
cur = open(CL, encoding="utf-8").read()
new_cl = open("/tmp/cross_layer_faces.github.py", encoding="utf-8").read()
if "_SLAB_SYMBOL_LAYERS" in cur:
    print("já aplicado", CL)
elif "_SLAB_SYMBOL_LAYERS" not in new_cl:
    print("ERRO: /tmp/cross_layer_faces.github.py não é a versão 8cd27c6"); sys.exit(1)
else:
    base = subprocess.run(["git", "show", "ad340d8:backend/engines/metre/cross_layer_faces.py"], capture_output=True, text=True).stdout
    if base and hashlib.sha1(cur.encode()).hexdigest() != hashlib.sha1(base.encode()).hexdigest():
        print(f"ERRO {CL}: o ficheiro do pod difere da versão ad340d8 — não substituo às cegas; manda-me o diff"); sys.exit(1)
    PLAN.append((CL, new_cl))

# ---- 2) volumes_tool.py: caminho clássico
patch("backend/engines/metre/volumes_tool.py", [
    ('''    for k, v in (levels_override or {}).items():
''', '''    lp_all = takeoff.get("levels_printed") or {}
    if levels.get("as_plancher_haut_m") is None and levels.get("ai_plancher_haut_m") is None and lp_all.get("ai_texts"):
        # Regra AI/AS: sem etiqueta de laje, a AI do pavimento superior vem dos textos «Ai:» de LAJE impressos na própria
        # planta (os Ai de lintéis, vigas e trémies já ficam fora de ai_texts desde a versão 8cd27c6 do leitor).
        from collections import Counter as _Counter
        ai_counts = _Counter(round(a["ngf"], 2) for a in lp_all["ai_texts"])
        ai_val, n_ai = ai_counts.most_common(1)[0]
        levels["ai_plancher_haut_m"] = ai_val
        levels["source"] = ((levels.get("source") or "") + f" ; AI pavimento superior = texto «Ai:» impresso mais frequente ({n_ai}× {ai_val:.2f} NGF)").strip(" ;")
        for v2, n2 in ai_counts.most_common()[1:12]:
            levels.setdefault("exceptions", []).append({"ai_ngf": v2, "count": n2,
                                                        "note": "outro texto «Ai:» impresso (zona rebaixada ou outro edifício): altura dessa zona a verificar"})
    if lower_dxf_bytes and levels.get("niveau_base_murs_m") is None:
        lower_lv = _printed_levels(lower_dxf_bytes)
        ldom = (lower_lv or {}).get("dominant")
        if ldom:
            n_l = sum(1 for t in lower_lv["slab_tags"] if t["as_ngf"] == ldom["as_plancher_haut_m"])
            levels["niveau_base_murs_m"] = ldom["as_plancher_haut_m"]
            levels["source"] = ((levels.get("source") or "") + f" ; base das paredes = AS {ldom['as_plancher_haut_m']:.2f} NGF da laje do piso inferior ({n_l} etiquetas impressas na sua planta)").strip(" ;")
        else:
            out["findings"].append({"severity": "to_clarify", "subject": "Piso inferior sem AS de laje legível",
                                    "explanation": "A planta do piso inferior não tem etiqueta de laje dominante (cota bruta + espessura): indique o nível de base das paredes."})
    for k, v in (levels_override or {}).items():
''', "levels_override"),
    ('''def compact_for_llm(res: dict) -> dict:
''', '''def _printed_levels(dxf_bytes: bytes) -> dict | None:
    """Etiquetas impressas (AS/espessura, Ai) de um DXF, com o leitor cross_layer: para a base das paredes vinda do piso inferior."""
    import io
    import ezdxf
    from ezdxf import recover
    from engines.metre import cross_layer_faces as XF
    try:
        try:
            doc = ezdxf.read(io.StringIO(dxf_bytes.decode("utf-8", "ignore")))
        except Exception:  # noqa: BLE001
            doc, _ = recover.read(io.BytesIO(dxf_bytes))
        u = {1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1.0}.get(doc.header.get("$INSUNITS", 0), 0.01)
        return XF.level_labels(doc.modelspace(), u)
    except Exception:  # noqa: BLE001 — a base em falta fica explícita nos findings, nunca um crash
        return None


def compact_for_llm(res: dict) -> dict:
''', "compact_for_llm"),
], "_printed_levels")

for _p, _s in PLAN:
    open(_p, "w", encoding="utf-8").write(_s)
    print("OK", _p)
