"""Deteção automática do piso inferior (23/11/2026, regra de Martinho): quando o modelo não indica lower_dxf_plan_id,
o nível de cada planta é lido no NOME do ficheiro (R+2, R-1, PH-1, SS1, PH SS-2, PHss-2, sous-sol, cave, RDC, PH RDC,
fondations/FON…) e a planta do nível imediatamente abaixo, entre as plantas e os DWG anexados desta conta, é usada como
piso inferior (promovida doc_→plan_ se preciso). Tudo-ou-nada, âncora = bloco _resolve_plan_args instalado por 08268b7."""
import sys

P = "backend/routes/assistant.py"
s = open(P, encoding="utf-8").read()
if "_auto_lower_plan" in s:
    print("já aplicado", P); sys.exit(0)
anc = '''async def _resolve_plan_args(args: dict, user: dict) -> None:
    """Substitui, nos argumentos de planta, um doc_… CAD de processo pelo plan_… correspondente (importado se preciso)."""
    if not isinstance(args, dict):
        return
    for key in PLAN_ARG_KEYS:
        value = args.get(key)
        if isinstance(value, str) and value.strip() and not value.startswith("plan_"):
            pid = await _plan_from_dossier_doc(value, user)
            if pid:
                args[key] = pid
'''
if s.count(anc) != 1:
    print(f"ERRO {P}: âncora «_resolve_plan_args» encontrada {s.count(anc)}× (esperado 1)")
    for i, l in enumerate(s.splitlines(), 1):
        if "_resolve_plan_args" in l:
            print(f"   linha {i}: {l.strip()[:150]}")
    sys.exit(1)
new = r'''_NIVEIS = (
    (re.compile(r"fonda|(?<![a-z0-9])fon(?![a-z])", re.I), -99),
    (re.compile(r"sous[\s_-]?sol|(?<![a-z0-9])cave(?![a-z])", re.I), -1),
    (re.compile(r"PH\s*[._-]?\s*SS\s*-?\s*(\d)", re.I), "-n"),
    (re.compile(r"(?<![a-z0-9])SS\s*-?\s*(\d)", re.I), "-n"),
    (re.compile(r"(?<![a-z0-9])PH\s*-\s*(\d)|(?<![a-z0-9])PH(\d)(?![0-9])", re.I), "-n"),
    (re.compile(r"(?<![a-z0-9])R\s*-\s*(\d)", re.I), "-n"),
    (re.compile(r"(?<![a-z0-9])R\s*\+\s*(\d)|(?<![a-z0-9])R(\d)(?![0-9])", re.I), "+n"),
    (re.compile(r"RDC|(?<![a-z0-9])R0(?![0-9])|R\+0", re.I), 0),
)


def _nivel_do_nome(name: str) -> int | None:
    """Nível pelo nome do ficheiro: PH-1 / SS1 / PH SS-2 / PHss-2 / R-1 / sous-sol / cave → subsolos; RDC/PH RDC → 0;
    R+2 / PH R+1 → pisos; fondations/FON → abaixo de tudo. PH é o teto do nível com o mesmo número."""
    base = (name or "").rsplit("/", 1)[-1]
    for rx, val in _NIVEIS:
        m = rx.search(base)
        if not m:
            continue
        if val == "-n":
            return -int(next(g for g in m.groups() if g))
        if val == "+n":
            return int(next(g for g in m.groups() if g))
        return val
    return None


async def _auto_lower_plan(main_plan_id: str, user: dict) -> str | None:
    """Planta do nível imediatamente abaixo da principal, pelo nome, entre as plantas e os DWG/DXF anexados desta conta."""
    uid = user["user_id"]
    p = await db.plans_takeoff.find_one({"plan_id": main_plan_id, "user_id": uid}, {"_id": 0, "filename": 1, "cad_import": 1})
    main = _nivel_do_nome(((p or {}).get("cad_import") or {}).get("original_filename") or (p or {}).get("filename") or "")
    if main is None:
        return None
    cands = []
    async for q in db.plans_takeoff.find({"user_id": uid}, {"_id": 0, "plan_id": 1, "filename": 1, "cad_import": 1}).sort("created_at", -1).limit(80):
        n = _nivel_do_nome(((q.get("cad_import") or {}).get("original_filename")) or q.get("filename") or "")
        if n is not None and n < main and q["plan_id"] != main_plan_id:
            cands.append((n, 1, q["plan_id"]))
    async for d in db.assistant_docs.find({"user_id": uid, "filename": {"$regex": r"\.(dwg|dxf)$", "$options": "i"}},
                                          {"_id": 0, "doc_id": 1, "filename": 1}).sort("created_at", -1).limit(120):
        n = _nivel_do_nome(d.get("filename") or "")
        if n is not None and n < main:
            cands.append((n, 0, d["doc_id"]))
    if not cands:
        return None
    _n, _pref, ident = max(cands)
    if ident.startswith("plan_"):
        return ident
    return await _plan_from_dossier_doc(ident, user)


''' + anc + '''    if args.get("dxf_plan_id") and not args.get("lower_dxf_plan_id") and not args.get("base_plan_id"):
        auto = await _auto_lower_plan(args["dxf_plan_id"], user)
        if auto:
            args["lower_dxf_plan_id" if "lower_dxf_plan_id" in PLAN_ARG_KEYS else "base_plan_id"] = auto
'''
s = s.replace(anc, new, 1)
open(P, "w", encoding="utf-8").write(s)
print("OK", P)
