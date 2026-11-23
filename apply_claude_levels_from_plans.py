"""Aplica no pod (por âncoras, idempotente): volumes de betão com as cotas IMPRESSAS nas plantas (regra AI/AS do Martinho):
- AI do pavimento superior = texto «Ai: … NGF» impresso mais frequente quando não há etiqueta de laje (B / esp. / NGF);
- base das paredes = AS dominante da laje do piso INFERIOR, lida na sua própria planta (novo argumento base_plan_id)."""
import re
import sys

PLAN = []          # todas as alterações são verificadas ANTES de escrever qualquer ficheiro


def _diag(s, label):
    key = {"assinatura": "def compute_volumes", "levels_override": "levels_override", "assinatura run": "def run_compute_concrete_volumes",
           "chamada compute_volumes": "compute_volumes,", "coupes_for_plan": "def coupes_for_plan"}.get(label, label[:20])
    for i, line in enumerate(s.splitlines(), 1):
        if key in line:
            print(f"   linha {i}: {line.strip()[:160]}")


def patch(path, pairs, marker):
    s = open(path, encoding="utf-8").read()
    if marker in s:
        print("já aplicado", path); return
    for old, new, label in pairs:
        if isinstance(old, re.Pattern):
            m = list(old.finditer(s))
            if len(m) != 1:
                print(f"ERRO {path}: âncora «{label}» encontrada {len(m)}× (esperado 1)"); _diag(s, label); sys.exit(1)
            s = s[:m[0].start()] + m[0].expand(new) + s[m[0].end():]
            continue
        if s.count(old) != 1:
            print(f"ERRO {path}: âncora «{label}» encontrada {s.count(old)}× (esperado 1)"); _diag(s, label); sys.exit(1)
        s = s.replace(old, new, 1)
    PLAN.append((path, s))

patch("backend/engines/metre/volumes_tool.py", [
    (re.compile(r"(def compute_volumes\((?:[^()]|\([^()]*\))*?)\)\s*->\s*dict:", re.S),
     r"\1, base_level: dict | None = None) -> dict:", "assinatura"),
    ("    for k, v in (levels_override or {}).items():\n",
     '''    lp_all = takeoff.get("levels_printed") or {}
    if levels.get("as_plancher_haut_m") is None and levels.get("ai_plancher_haut_m") is None and lp_all.get("ai_texts"):
        # Regra AI/AS: sem etiqueta de laje, a AI do pavimento superior vem dos textos «Ai: … NGF» impressos na própria planta.
        from collections import Counter as _Counter
        ai_counts = _Counter(round(a["ngf"], 2) for a in lp_all["ai_texts"])
        ai_val, n_ai = ai_counts.most_common(1)[0]
        levels["ai_plancher_haut_m"] = ai_val
        levels["source"] = ((levels.get("source") or "") + f" ; AI pavimento superior = texto «Ai:» impresso mais frequente ({n_ai}× {ai_val:.2f} NGF)").strip(" ;")
        for v2, n2 in ai_counts.most_common()[1:12]:
            levels.setdefault("exceptions", []).append({"ai_ngf": v2, "count": n2,
                                                        "note": "outro texto «Ai:» impresso (viga, zona rebaixada ou outro edifício): altura dessa zona a verificar"})
    if base_level and base_level.get("m") is not None and levels.get("niveau_base_murs_m") is None:
        levels["niveau_base_murs_m"] = base_level["m"]
        levels["source"] = ((levels.get("source") or "") + f" ; base das paredes = {base_level['source']}").strip(" ;")
    for k, v in (levels_override or {}).items():
''', "levels_override"),
], "base_level: dict | None = None) -> dict:")

patch("backend/engines/metre/volumes_run.py", [
    (re.compile(r"(async def run_compute_concrete_volumes\((?:[^()]|\([^()]*\))*?)\)\s*->\s*dict:", re.S),
     r"\1, base_plan_id: str | None = None) -> dict:", "assinatura run"),
    (re.compile(r"\n(?P<ind>[ \t]*)res = await asyncio\.to_thread\(compute_volumes, (?P<args>[^\n]*)\)\n"),
     '''\n    base_level = None
    if base_plan_id:
        bsrc = await load_cad_source(db, base_plan_id, user_id, "converted_dxf") or await load_cad_source(db, base_plan_id, user_id, "original")
        braw = (bsrc if isinstance(bsrc, (bytes, bytearray)) else base64.b64decode(bsrc["data_b64"])) if bsrc else None
        if braw and braw[:4] != b"AC10":
            base_level = await asyncio.to_thread(_base_from_lower_floor, braw)
        status["base_plan"] = base_level or {"error": "AS da laje do piso inferior não encontrada nessa planta (etiquetas B / espessura / NGF ausentes)"}
    res = await asyncio.to_thread(compute_volumes, \\g<args>, base_level=base_level)
''', "chamada compute_volumes"),
    ('async def coupes_for_plan(',
     '''def _base_from_lower_floor(dxf: bytes) -> dict | None:
    """Base das paredes = AS dominante da laje do piso inferior, lida nas etiquetas impressas da planta desse piso."""
    import io
    import ezdxf
    from ezdxf import recover
    from engines.metre import cross_layer_faces as XF
    try:
        doc = ezdxf.read(io.StringIO(dxf.decode("utf-8", "ignore")))
    except Exception:  # noqa: BLE001
        doc, _ = recover.read(io.BytesIO(dxf))
    u = {1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1.0}.get(doc.header.get("$INSUNITS", 0), 0.01)
    lv = XF.level_labels(doc.modelspace(), u)
    dom = lv.get("dominant")
    if not dom:
        return None
    n = sum(1 for t in lv["slab_tags"] if t["as_ngf"] == dom["as_plancher_haut_m"])
    return {"m": dom["as_plancher_haut_m"], "source": f"AS {dom['as_plancher_haut_m']:.2f} NGF da laje do piso inferior ({n} etiquetas impressas na sua planta)"}


async def coupes_for_plan(''', "coupes_for_plan"),
], "_base_from_lower_floor")

patch("backend/routes/assistant.py", [
    ('PLAN_ARG_KEYS = ("plan_id", "plan_id_a", "plan_id_b", "dxf_plan_id", "formwork_plan_id", "coupes_plan_id")',
     'PLAN_ARG_KEYS = ("plan_id", "plan_id_a", "plan_id_b", "dxf_plan_id", "formwork_plan_id", "coupes_plan_id", "base_plan_id")', "PLAN_ARG_KEYS"),
    ('''         "coupes_plan_id": {"type": ["string", "null"], "description": "caderno de cortes PDF (níveis B/F impressos)"},
''', '''         "coupes_plan_id": {"type": ["string", "null"], "description": "caderno de cortes PDF (níveis B/F impressos)"},
         "base_plan_id": {"type": ["string", "null"], "description": "planta DWG/DXF do piso INFERIOR (ex.: PH-1 para o RDC): a AS da sua laje, lida nas etiquetas impressas, é a base das paredes deste piso"},
''', "schema base_plan_id"),
    ('"required": ["dxf_plan_id", "formwork_plan_id", "coupes_plan_id", "allow_vision", "levels"]',
     '"required": ["dxf_plan_id", "formwork_plan_id", "coupes_plan_id", "base_plan_id", "allow_vision", "levels"]', "required"),
    ("allow_vision=bool(args.get(\"allow_vision\")), levels=args.get(\"levels\"), now=_now(), log_usage=_log_usage)",
     "allow_vision=bool(args.get(\"allow_vision\")), levels=args.get(\"levels\"), now=_now(), log_usage=_log_usage,\n                                                  base_plan_id=args.get(\"base_plan_id\"))", "dispatch"),
], 'base_plan_id=args.get("base_plan_id")')

patch("backend/engines/metre/tools.py", [
    ("Nunca uma altura de andar típica nem um rácio.",
     "Nunca uma altura de andar típica nem um rácio. Em compute_concrete_volumes passa SEMPRE base_plan_id = a planta DWG do piso inferior (ex.: PH-1.dwg para o RDC, RDC.dwg para o R+1): a ferramenta lê lá a AS da laje.", "regra dos níveis"),
], "passa SEMPRE base_plan_id")

for _path, _s in PLAN:
    open(_path, "w", encoding="utf-8").write(_s)
    print("OK", _path)
