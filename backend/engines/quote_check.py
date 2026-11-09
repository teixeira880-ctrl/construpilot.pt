"""Contrôleur de devis avant envoi (Module 3).

Combine :
- des contrôles déterministes (calculs, unités, cohérence, doublons, marge, écart métré) ;
- une bibliothèque de règles métier (postes complémentaires probablement manquants) ;
- une couche IA optionnelle (analyse des descriptions) en meilleur effort.

Chaque alerte : {id, severity, category, title, message, line_indexes, data_used, fix?, source}.
severity ∈ error | warning | info. Aucun score arbitraire n'est présenté comme une probabilité.
"""
from __future__ import annotations

import re
import unicodedata


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "")).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()
    return re.sub(r"\s+", " ", s)


def _has_kw(text: str, kws: list[str]) -> bool:
    n = _norm(text)
    return any(_norm(k) in n for k in kws)


# Règles métier : un ouvrage « déclencheur » implique souvent un poste « complémentaire ».
# Présentées comme éléments À VÉRIFIER (elles peuvent être forfaitaires, incluses ailleurs ou hors périmètre).
COMPLEMENTARY_RULES = [
    {"trigger": ["demolition", "depose", "demontage", "arrachage"],
     "expect": ["evacuation", "gravats", "benne", "decharge", "dechetterie", "mise en decharge"],
     "title": "Remoção do entulho",
     "message": "Está prevista uma desmontagem / demolição; não foi identificado nenhum artigo de remoção de entulho. Está incluído noutro artigo?"},
    {"trigger": ["carrelage", "faience", "carreaux"],
     "expect": ["colle", "joint", "plinthe", "mortier colle"],
     "title": "Cola, juntas e rodapés",
     "message": "Assentamento de mosaico / azulejo detetado; verifique a presença da cola, das juntas e dos rodapés."},
    {"trigger": ["peinture", "mise en peinture"],
     "expect": ["preparation", "enduit", "sous couche", "sous-couche", "impression", "protection", "rebouchage", "ponçage", "poncage"],
     "title": "Preparação e proteção",
     "message": "Pintura detetada; verifique a preparação dos suportes (reparação / massa / primário) e a proteção dos pavimentos e mobiliário."},
    {"trigger": ["placo", "ba13", "cloison", "plaque de platre", "doublage", "faux plafond"],
     "expect": ["bande", "enduit", "joint", "tratamento das juntas"],
     "title": "Tratamento das juntas",
     "message": "Divisória / placa de gesso cartonado detetada; verifique o tratamento das juntas (fitas + massa)."},
    {"trigger": ["parquet", "sol souple", "stratifie", "moquette", "lino"],
     "expect": ["plinthe", "barre de seuil", "sous couche", "sous-couche", "ragreage", "seuil"],
     "title": "Autonivelante, rodapés e soleiras",
     "message": "Aplicação de revestimento de pavimento detetada; verifique o autonivelante / a subcamada e os rodapés / perfis de soleira."},
    {"trigger": ["fenetre", "menuiserie", "porte fenetre", "baie", "volet"],
     "expect": ["depose", "calfeutrement", "habillage", "finition", "bavette", "appui"],
     "title": "Desmontagem e acabamentos de caixilharia",
     "message": "Caixilharia detetada; verifique a desmontagem da existente e os acabamentos (calafetagem / guarnições)."},
    {"trigger": ["douche italienne", "receveur", "wc", "lavabo", "sanitaire", "plomberie"],
     "expect": ["etancheite", "raccordement", "evacuation", "alimentation", "siphon"],
     "title": "Impermeabilização e ligações",
     "message": "Prestação de sanitários / canalização detetada; verifique a impermeabilização (duche) e as ligações (alimentação / esgoto)."},
]


def _fmt_idx(indexes: list[int]) -> list[int]:
    return sorted(set(int(i) for i in indexes))


def deterministic_checks(lines: list[dict], totals: dict, policy: dict | None = None,
                         metre: dict | None = None) -> list[dict]:
    alerts: list[dict] = []
    aid = 0

    def _new(sev, cat, title, msg, idx=None, data="", fix=None, source="deterministic"):
        nonlocal aid
        aid += 1
        return {"id": f"chk_{source}_{aid}", "severity": sev, "category": cat, "title": title,
                "message": msg, "line_indexes": _fmt_idx(idx or []), "data_used": data,
                "fix": fix, "source": source}

    priced = [(i, ln) for i, ln in enumerate(lines) if (ln.get("designation") or "").strip()]

    # 1. Doublons potentiels (désignation normalisée + unité)
    seen: dict = {}
    for i, ln in priced:
        key = _norm(ln.get("designation", "")) + "|" + _norm(ln.get("unit", ""))
        seen.setdefault(key, []).append(i)
    for key, idxs in seen.items():
        if len(idxs) > 1:
            name = (lines[idxs[0]].get("designation") or "").strip()
            alerts.append(_new("warning", "doublon", "Duplicado potencial",
                               f'« {name}» aparece {len(idxs)} vezes com a mesma unidade. Verifique se não se trata de uma repetição involuntária.',
                               idxs, "designação + unidade idênticas"))

    # 2. Cohérence unité / quantité / prix
    for i, ln in priced:
        qty = ln.get("qty")
        pu = ln.get("unit_price_ht")
        if qty is None or float(qty or 0) <= 0:
            alerts.append(_new("error", "coherence", "Quantidade em falta ou nula",
                               f"A linha «{ln.get('designation')}» tem uma quantidade de {qty}. Indique uma quantidade positiva.",
                               [i], "qty ≤ 0"))
        if pu is None or float(pu or 0) <= 0:
            alerts.append(_new("error", "coherence", "Preço unitário em falta",
                               f"A linha «{ln.get('designation')}» não tem preço unitário sem IVA. O total ficaria subavaliado.",
                               [i], "PU HT ≤ 0"))
        if not ln.get("unit"):
            alerts.append(_new("warning", "coherence", "Unidade em falta",
                               f"A linha «{ln.get('designation')}» não tem unidade.",
                               [i], "unidade vazia"))

    # 3. Coût de revient > prix de vente (perte de marge)
    for i, ln in priced:
        cost = float(ln.get("cost_price_ht") or 0)
        pu = float(ln.get("unit_price_ht") or 0)
        if cost > 0 and pu > 0 and cost > pu:
            loss = round((cost - pu) * float(ln.get("qty") or 0), 2)
            alerts.append(_new("error", "marge", "Venda inferior ao custo",
                               f"« {ln.get('designation')}» : custo de produção {cost:.2f} € > preço de venda {pu:.2f} € s/ IVA (perda estimada {loss:.2f} € na linha).",
                               [i], "cost_price_ht > unit_price_ht",
                               fix=None))

    # 4. TVA manquante ou à confirmer
    default_rate = (policy or {}).get("default_rate")
    vat_missing = [i for i, ln in priced if ln.get("vat_rate") is None]
    if vat_missing:
        fix = ({"action": "set_vat", "rate": default_rate} if default_rate else None)
        alerts.append(_new("warning", "tva", "IVA não indicado",
                           f'{len(vat_missing)} linha(s) sem taxa de IVA.'
                           + (f' Taxa normal da empresa: {default_rate} %.' if default_rate else ""),
                           vat_missing, "vat_rate = null", fix=fix))
    vat_assumed = [i for i, ln in priced if ln.get("vat_assumed") and ln.get("vat_rate") is not None]
    if vat_assumed:
        alerts.append(_new("info", "tva", "IVA suposto, a confirmar",
                           f'{len(vat_assumed)} linha(s) têm uma taxa de IVA suposta automaticamente — confirme-a antes do envio.',
                           vat_assumed, "vat_assumed = true"))

    # 5. Marge globale non vérifiable si coûts inconnus
    cov = totals.get("cost_coverage") or {}
    if not cov.get("complete"):
        missing = cov.get("missing_lines", 0)
        alerts.append(_new("info", "marge", "Margem não verificável",
                           f'{missing} linha(s) sem custo de produção indicado: a margem global não pode ser controlada. Indique os custos ou assinale «custo nulo confirmado» para um controlo de margem completo.',
                           [], "cost_coverage.complete = false"))

    # 6. Écart vs quantités du métré du chantier (meilleur effort, surface de sol)
    if metre:
        slab = metre.get("slab_area_m2")
        if slab and slab > 0:
            floor_kw = ["carrelage", "parquet", "sol souple", "chape", "ragreage", "moquette", "lino", "revetement de sol"]
            for i, ln in priced:
                if (ln.get("unit") or "").lower() in ("m²", "m2") and _has_kw(ln.get("designation", ""), floor_kw):
                    qty = float(ln.get("qty") or 0)
                    if qty > 0 and abs(qty - slab) / slab > 0.15:
                        alerts.append(_new("warning", "metre", "Diferença face à medição da obra",
                                           f"« {ln.get('designation')} » : {qty:g} m² introduzidos vs {slab:g} m² de área de pavimento registada na planta da obra (diferença > 15 %). Verifique a quantidade.",
                                           [i], f"slab_area_m2 = {slab:g}"))
            alerts.append(_new("info", "metre", "Medição da obra disponível",
                               f'Medição registada na planta associada: área de pavimento {slab:g} m²'
                               + (f", paredes {metre.get('walls_ml'):g} ml" if metre.get('walls_ml') else "")
                               + ". Utilize-a para confrontar as suas quantidades.",
                               [], "plans_takeoff.structural_metre"))

    # 7. Postes complémentaires probablement manquants (règles métier — à vérifier)
    all_text = " \n ".join((ln.get("designation") or "") + " " + (ln.get("description") or "") for ln in lines)
    for rule in COMPLEMENTARY_RULES:
        trig_idx = [i for i, ln in priced
                    if _has_kw((ln.get("designation") or "") + " " + (ln.get("description") or ""), rule["trigger"])]
        if trig_idx and not _has_kw(all_text, rule["expect"]):
            alerts.append(_new("warning", "poste_manquant", rule["title"], rule["message"],
                               trig_idx, "regra profissional · a verificar (pode estar incluído noutro lado)", source="rule"))

    return alerts


async def ai_checks(lines: list[dict], context: str = "") -> list[dict]:
    """Analyse IA des descriptions pour repérer oublis/ambiguïtés (meilleur effort)."""
    import json
    from engines.ai import _complete, _json
    slim = [{"i": i, "designation": (ln.get("designation") or "")[:160],
             "unit": ln.get("unit") or "", "qty": ln.get("qty"),
             "description": (ln.get("description") or "")[:300]}
            for i, ln in enumerate(lines) if (ln.get("designation") or "").strip()][:120]
    if not slim:
        return []
    system = ("És orçamentista da construção (Portugal). Relês um orçamento antes do envio e assinalas APENAS pontos concretos a verificar: trabalho complementar provavelmente esquecido, ambiguidade de uma designação, incoerência aparente. Não reescreves o orçamento e não inventas preços. Devolves APENAS JSON válido, com textos em português europeu.")
    prompt = (
        (f'Contexto: {context[:300]}\n\n' if context else "")
        + f'Linhas do orçamento: {json.dumps(slim, ensure_ascii=False)}\n\nDevolve APENAS este JSON: {{ "alerts": [ {{\n  "line_indexes": [índices das linhas em causa, [] se global],\n  "severity": "warning"|"info",\n  "category": "poste_manquant"|"ambiguite"|"coherence",\n  "title": "título curto (máx. 6 palavras)",\n  "message": "explicação concreta, formulada como uma pergunta ou uma verificação a fazer" }} ] }}\nMáximo 8 alertas, os mais úteis. Apresenta as dependências como elementos A VERIFICAR (um artigo pode ser global, incluído noutro lado ou fora do âmbito). Não inventes alertas sem indício real. Textos em português europeu.'
    )
    try:
        data = _json(await _complete(system, prompt, feature="quote_check"), {"alerts": []})
    except Exception:
        return []
    out: list[dict] = []
    for n, a in enumerate((data.get("alerts") or [])[:8]):
        title = str(a.get("title") or "").strip()[:80]
        msg = str(a.get("message") or "").strip()[:500]
        if not title or not msg:
            continue
        sev = a.get("severity") if a.get("severity") in ("warning", "info") else "info"
        cat = a.get("category") if a.get("category") in ("poste_manquant", "ambiguite", "coherence") else "poste_manquant"
        idx = []
        for v in (a.get("line_indexes") or []):
            try:
                iv = int(v)
                if 0 <= iv < len(lines):
                    idx.append(iv)
            except (TypeError, ValueError):
                continue
        out.append({"id": f"chk_ai_{n+1}", "severity": sev, "category": cat, "title": title,
                    "message": msg, "line_indexes": _fmt_idx(idx), "data_used": "análise IA das descrições",
                    "fix": None, "source": "ai"})
    return out


_SEV_ORDER = {"error": 0, "warning": 1, "info": 2}


def _alert_key(a: dict, lines: list[dict]) -> str:
    """Clé stable d'une alerte (indépendante de l'ordre des lignes) pour persister son traitement."""
    import hashlib
    desigs = "|".join(sorted(_norm(lines[i].get("designation", "")) for i in a.get("line_indexes", [])
                             if 0 <= i < len(lines)))
    raw = f"{a.get('category')}|{_norm(a.get('title',''))}|{desigs}"
    return "k_" + hashlib.md5(raw.encode()).hexdigest()[:12]


async def run_quote_check(lines: list[dict], totals: dict, policy: dict | None = None,
                          metre: dict | None = None, use_ai: bool = True, context: str = "") -> dict:
    alerts = deterministic_checks(lines, totals, policy, metre)
    ai_used = False
    if use_ai:
        ai = await ai_checks(lines, context)
        if ai:
            ai_used = True
            alerts += ai
    alerts.sort(key=lambda a: _SEV_ORDER.get(a["severity"], 3))
    for a in alerts:
        a["key"] = _alert_key(a, lines)
    counts = {"error": 0, "warning": 0, "info": 0}
    for a in alerts:
        counts[a["severity"]] = counts.get(a["severity"], 0) + 1
    return {"alerts": alerts, "counts": counts, "total": len(alerts), "ai_used": ai_used,
            "checked_lines": sum(1 for ln in lines if (ln.get("designation") or "").strip())}
