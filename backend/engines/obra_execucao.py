"""Execução de obra — motor puro (sem base de dados nem rede): assessor de voz, mapa de avanço por zona,
tesouraria da obra e câmaras.

Idêntico no .pt e no .fr: tudo o que depende da língua ou do país está em engines/obra_execucao_txt.py.
Regra de ouro: nada é inventado. O assessor só propõe o que está no relato e o utilizador confirma tudo
antes de gravar; a tesouraria só usa valores registados (ou previstos e identificados como tal).
"""
from __future__ import annotations

import calendar
import difflib
import re
import secrets
import unicodedata
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Optional
from urllib.parse import urlparse

from engines import obra_execucao_txt as TX

MAX_TEXTO = 6000
MAX_PISOS, MAX_ZONAS, MAX_ATIVIDADES = 30, 400, 40
MAX_CAMARAS = 12
QSE_TIPOS = ("incidente", "quase_acidente", "epi", "nao_conformidade", "ambiente")
GRAVIDADES = ("baixa", "media", "alta", "critica")
RFI_PERFIS = ("arquiteto", "fiscalizacao", "dono_obra")


# ====================================================================== utilitários
def norm(s: Any) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"(\d)[.,](\d)", r"\1.\2", s)                   # 2,5 → 2.5 (decimal falado/escrito)
    s = re.sub(r"[^a-z0-9%?.]+", " ", s)
    return re.sub(r"\s+", " ", re.sub(r"(?<!\d)\.|\.(?!\d)", " ", s)).strip()


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(5)}"


def parse_date(s: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(s or "")[:10])
    except ValueError:
        return None


def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def _id_seguro(v: Any, prefix: str) -> str:
    """Identificadores usados como chaves Mongo: só letras, números, _ e -."""
    v = str(v or "")[:40]
    return v if re.fullmatch(r"[A-Za-z0-9_-]{1,40}", v) else new_id(prefix)


def _cap(s: Any, n: int) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()[:n]


# ====================================================================== assessor de voz
def _frases(texto: str) -> list[str]:
    partes = re.split(r"(?<=[.!?;])\s+|\n+|\s+e depois\s+|\s+depois disso\s+|\s+et ensuite\s+|\s+puis\s+", texto or "")
    return [p.strip(" .;") for p in partes if p and p.strip(" .;")]


def _numero(tok: str) -> Optional[float]:
    t = tok.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return TX.NUMEROS.get(norm(tok))


_NUM_RX = r"(\d+(?:[.,]\d+)?|" + "|".join(sorted((re.escape(k) for k in TX.NUMEROS), key=len, reverse=True)) + r")"
_UNI_RX = "|".join(sorted((re.escape(k) for k in TX.UNIDADES), key=len, reverse=True))


def _melhor(nome: str, opcoes: Iterable[str], corte: float = 0.78) -> Optional[str]:
    """Correspondência tolerante (ditado com erros) com uma lista conhecida; devolve a opção original."""
    n = norm(nome)
    if not n:
        return None
    best, score = None, 0.0
    for o in opcoes:
        on = norm(o)
        if not on:
            continue
        if on == n:
            return o
        s = difflib.SequenceMatcher(None, n, on).ratio()
        if (n in on or on in n) and min(len(n), len(on)) >= 4:
            s = max(s, 0.9)
        if s > score:
            best, score = o, s
    return best if score >= corte else None


def _quantidades(frase_n: str) -> list[dict]:
    """«40 sacos de cimento», «12 m3 de betão», «200 tijolos» → [{quantidade, unidade, material}]."""
    out = []
    rx = re.compile(r"\b" + _NUM_RX + r"\s*(" + _UNI_RX + r")?\b(?:\s+(?:" + "|".join(TX.LIGACAO) + r")\b)?\s*")
    heads = [m for m in rx.finditer(frase_n) if _numero(m.group(1))]
    for i, m in enumerate(heads):
        q = _numero(m.group(1))
        if q is None or q <= 0:
            continue
        uni_falada = (m.group(2) or "").strip()
        if not uni_falada and q == 1 and not re.fullmatch(r"\d+(?:\.\d+)?", m.group(1)):
            continue   # «uma laje», «une dalle»: artigo, não quantidade
        fim = heads[i + 1].start() if i + 1 < len(heads) else len(frase_n)
        mat = []
        for w in frase_n[m.end():fim].split():
            if w in TX.FIM_MATERIAL or w.endswith("%"):
                break
            mat.append(w)
            if len(mat) >= 5:
                break
        while mat and mat[-1] in TX.LIGACAO:
            mat.pop()
        material = " ".join(mat).strip()
        if uni_falada in TX.UNIDADE_E_MATERIAL:
            material = (TX.UNIDADE_E_MATERIAL[uni_falada] + (" " + material if material else "")).strip()
        if norm(material) in TX.UNIDADE_E_MATERIAL:          # «3 paletes de tijolos», «3 palettes de parpaings»
            material = TX.UNIDADE_E_MATERIAL[norm(material)]
        if not material or norm(material) in TX.UNIDADES or (not uni_falada and frase_n[m.end():m.end() + 1] == "%"):
            continue
        out.append({"quantidade": q, "unidade": TX.UNIDADES.get(uni_falada, "un" if uni_falada else ""), "material": material})
    return out


def _original(frase: str, alvo: str) -> str:
    """Recupera do relato original o texto do material (acentos, maiúsculas, «C25/30»)."""
    toks = frase.split()
    for i in range(len(toks)):
        acc = ""
        for j in range(i, min(i + 8, len(toks))):
            acc = (acc + " " + norm(toks[j])).strip()
            if acc == alvo or (acc.startswith(alvo + " ") and j > i):
                txt = " ".join(toks[i:j + 1]).strip(" ,.;:")
                return txt[:1].upper() + txt[1:]
            if not alvo.startswith(acc):
                break
    return alvo[:1].upper() + alvo[1:]


def _efetivos(frase_n: str) -> list[dict]:
    out = []
    rx = re.compile(_NUM_RX + r"\s+" + TX.PESSOAS + r"(?:\s+(?:da|de|do|du|des)\s+(?:l\s+|la\s+)?(?:(?:equipa|equipe)\s+(?:de\s+|do\s+|da\s+|du\s+)?(?:l\s+)?)?([a-z ]{2,40}))?")
    for m in rx.finditer(frase_n):
        n = _numero(m.group(1))
        if not n or n != int(n) or n > 500:
            continue
        equipa = (m.group(3) or "").split(" e ")[0].split(" et ")[0].strip()
        equipa = " ".join(w for w in equipa.split()[:4] if w not in TX.FIM_MATERIAL)
        out.append({"equipa": (equipa or m.group(2)).capitalize(), "n": int(n)})
    return out


def _avanco(frase_n: str, zonas: list[dict], atividades: list[dict]) -> Optional[dict]:
    if not zonas or not atividades:
        return None
    pct = None
    m = re.search(r"(\d{1,3}(?:[.,]\d+)?)\s?%", frase_n) or re.search(r"(\d{1,3})\s(por cento|pour cent)", frase_n)
    if m:
        pct = _num(m.group(1).replace(",", "."))
    elif re.search(TX.CONCLUIDO, frase_n):
        pct = 100.0
    if pct is None or not 0 <= pct <= 100:
        return None
    def alternativas(nome: str) -> list[str]:
        return [norm(x) for x in re.split(r"/|\(|\)|,| e | et ", nome) if len(norm(x)) >= 4]
    cand = [(a, max(len(x) for x in alternativas(a["nome"]) if re.search(r"\b" + re.escape(x) + r"\b", frase_n)))
            for a in atividades if any(re.search(r"\b" + re.escape(x) + r"\b", frase_n) for x in alternativas(a["nome"]))]
    ativ = max(cand, key=lambda x: x[1], default=(None, 0))[0]
    if not ativ:   # ditado aproximado: compara cada atividade com janelas de palavras
        palavras = frase_n.split()
        for a in atividades:
            k = len(norm(a["nome"]).split())
            if any(_melhor(" ".join(palavras[i:i + k]), [a["nome"]], 0.85) for i in range(len(palavras))):
                ativ = a
                break
    zona = max(((z, len(norm(z["nome"]))) for z in zonas if norm(z["nome"]) and re.search(r"\b" + re.escape(norm(z["nome"])) + r"\b", frase_n)),
               key=lambda x: x[1], default=(None, 0))[0]
    if not ativ or not zona:
        return None
    return {"zona_id": zona["zona_id"], "zona": zona["nome"], "atividade_id": ativ["atividade_id"], "atividade": ativ["nome"],
            "pct": round(pct, 1)}


def interpretar_local(texto: str, materiais: Iterable[dict] = (), zonas: Iterable[dict] = (),
                      atividades: Iterable[dict] = ()) -> dict:
    """Interpretação determinística (sem IA, funciona sem internet). Só extrai o que está explicitamente dito."""
    materiais, zonas, atividades = list(materiais), list(zonas), list(atividades)
    nomes_mat = [m.get("material") for m in materiais if m.get("material")]
    unid_mat = {norm(m.get("material")): m.get("unidade") or "" for m in materiais}
    diario = {"trabalhos": [], "ocorrencias": [], "entregas": [], "visitas": [], "observacoes": [], "efetivos": []}
    stock, qse, rfi, avanco = [], [], [], []
    for frase in _frases(texto):
        fn = norm(frase)
        usada = False
        # stock
        e_ent, e_sai = re.search(r"\b" + TX.VERBOS_ENTRADA, fn), re.search(r"\b" + TX.VERBOS_SAIDA, fn)
        trabalho = False
        if e_ent or e_sai:
            for q in _quantidades(fn[(e_ent or e_sai).start():]):
                conhecido = _melhor(q["material"], nomes_mat)
                material = conhecido or _original(frase, q["material"])
                unidade = (unid_mat.get(norm(conhecido)) if conhecido else None) or q["unidade"]
                mov = "entrada" if e_ent and (not e_sai or e_ent.start() <= e_sai.start()) else "saida"
                stock.append({"mov": mov, "material": material, "unidade": unidade, "quantidade": q["quantidade"],
                              "material_conhecido": bool(conhecido), "frase": frase})
                trabalho = trabalho or mov == "saida"
                if mov == "entrada":
                    diario["entregas"].append(f"{_fmt(q['quantidade'])} {unidade} {material}".strip())
                usada = True
        # efetivos
        ef = _efetivos(fn)
        if ef:
            diario["efetivos"].extend(ef)
            usada = True
        # qualidade e segurança
        for rx, tipo, grav in TX.QSE_REGRAS:
            if re.search(rx, fn):
                qse.append({"tipo": tipo, "titulo": _cap(frase, 120), "descricao": frase, "gravidade": grav,
                            "local": _local(fn, zonas), "frase": frase})
                diario["ocorrencias"].append(frase)
                usada = True
                break
        # pedidos de esclarecimento
        if re.search(TX.RFI_REGRAS, fn) or frase.rstrip().endswith("?"):
            dest = next((p for k, p in TX.RFI_DESTINO if k in fn), None)
            rfi.append({"assunto": _cap(frase, 90), "pergunta": frase, "destinatario_perfil": dest, "frase": frase})
            usada = True
        # avanço por zona
        av = _avanco(fn, zonas, atividades)
        if av:
            avanco.append({**av, "frase": frase})
        # diário: visitas, ocorrências, trabalhos
        if re.search(TX.VISITA_REGRAS, fn):
            diario["visitas"].append(frase)
            usada = True
        elif re.search(TX.OCORRENCIA_REGRAS, fn) and frase not in diario["ocorrencias"]:
            diario["ocorrencias"].append(frase)
            usada = True
        if not usada or av or trabalho:
            diario["trabalhos"].append(frase)
    return normalizar({"diario": {k: ("\n".join(v) if k != "efetivos" else v) for k, v in diario.items()},
                       "stock": stock, "qse": qse, "rfi": rfi, "avanco": avanco}, materiais, zonas, atividades, fonte="local")


def _fmt(q: float) -> str:
    return str(int(q)) if q == int(q) else str(q).replace(".", ",")


def _local(fn: str, zonas: list[dict]) -> str:
    for z in sorted(zonas, key=lambda z: -len(norm(z.get("nome")))):
        if norm(z.get("nome")) and re.search(r"\b" + re.escape(norm(z["nome"])) + r"\b", fn):
            return z["nome"]
    return ""


def normalizar(bruto: Any, materiais: Iterable[dict] = (), zonas: Iterable[dict] = (), atividades: Iterable[dict] = (),
               fonte: str = "ia") -> dict:
    """Valida e limpa uma interpretação (da IA ou local). O que não for válido é descartado, nunca corrigido à sorte."""
    materiais, zonas, atividades = list(materiais), list(zonas), list(atividades)
    b = bruto if isinstance(bruto, dict) else {}
    d = b.get("diario") if isinstance(b.get("diario"), dict) else {}
    diario = {k: _cap_multi(d.get(k), 4000 if k != "trabalhos" else 8000) for k in ("trabalhos", "ocorrencias", "entregas", "visitas", "observacoes")}
    efs, vistos = [], set()
    for e in d.get("efetivos") or []:
        if not isinstance(e, dict):
            continue
        n = _num(e.get("n"))
        eq = _cap(e.get("equipa"), 120)
        if n and n == int(n) and 0 < n <= 500 and norm(eq) not in vistos:
            vistos.add(norm(eq))
            efs.append({"equipa": eq or TX.EQUIPA_PADRAO, "n": int(n)})
    diario["efetivos"] = efs[:40]
    nomes_mat = [m.get("material") for m in materiais if m.get("material")]
    unid_mat = {norm(m.get("material")): m.get("unidade") or "" for m in materiais}
    props: list[dict] = []
    if any(diario[k] for k in ("trabalhos", "ocorrencias", "entregas", "visitas", "observacoes")) or efs:
        props.append({"id": "p1", "tipo": "diario", "campos": diario, "selecionada": True})
    for s in (b.get("stock") or [])[:40]:
        if not isinstance(s, dict):
            continue
        q = _num(s.get("quantidade"))
        mov = s.get("mov") if s.get("mov") in ("entrada", "saida") else None
        mat = _cap(s.get("material"), 200)
        if not mov or not mat or q is None or not 0 < q <= 1_000_000:
            continue
        conhecido = _melhor(mat, nomes_mat)
        unidade = _cap((unid_mat.get(norm(conhecido)) if conhecido else None) or s.get("unidade"), 20)
        props.append({"id": f"p{len(props) + 1}", "tipo": "stock", "mov": mov, "material": conhecido or mat, "unidade": unidade,
                      "quantidade": q, "material_conhecido": bool(conhecido), "frase": _cap(s.get("frase"), 400), "selecionada": True})
    for s in (b.get("qse") or [])[:10]:
        if not isinstance(s, dict) or s.get("tipo") not in QSE_TIPOS or len(_cap(s.get("titulo"), 200)) < 2:
            continue
        props.append({"id": f"p{len(props) + 1}", "tipo": "qse", "qse_tipo": s["tipo"], "titulo": _cap(s.get("titulo"), 200),
                      "descricao": _cap(s.get("descricao"), 6000), "gravidade": s.get("gravidade") if s.get("gravidade") in GRAVIDADES else "media",
                      "local": _cap(s.get("local"), 200), "frase": _cap(s.get("frase"), 400), "selecionada": True})
    for s in (b.get("rfi") or [])[:10]:
        if not isinstance(s, dict) or len(_cap(s.get("pergunta"), 6000)) < 3:
            continue
        assunto = _cap(s.get("assunto") or s.get("pergunta"), 200)
        props.append({"id": f"p{len(props) + 1}", "tipo": "rfi", "assunto": assunto if len(assunto) >= 3 else _cap(s.get("pergunta"), 200),
                      "pergunta": _cap(s.get("pergunta"), 6000),
                      "destinatario_perfil": s.get("destinatario_perfil") if s.get("destinatario_perfil") in RFI_PERFIS else None,
                      "frase": _cap(s.get("frase"), 400), "selecionada": True})
    zmap = {z["zona_id"]: z for z in zonas}
    amap = {a["atividade_id"]: a for a in atividades}
    vistos_av = set()
    for s in (b.get("avanco") or [])[:60]:
        if not isinstance(s, dict):
            continue
        pct = _num(s.get("pct"))
        z = zmap.get(s.get("zona_id")) or next((zz for zz in zonas if norm(zz["nome"]) == norm(s.get("zona"))), None)
        a = amap.get(s.get("atividade_id")) or next((aa for aa in atividades if norm(aa["nome"]) == norm(s.get("atividade"))), None)
        if a is None and s.get("atividade"):
            nome = _melhor(s.get("atividade"), [aa["nome"] for aa in atividades], 0.85)
            a = next((aa for aa in atividades if aa["nome"] == nome), None)
        if not z or not a or pct is None or not 0 <= pct <= 100 or (z["zona_id"], a["atividade_id"]) in vistos_av:
            continue
        vistos_av.add((z["zona_id"], a["atividade_id"]))
        props.append({"id": f"p{len(props) + 1}", "tipo": "avanco", "zona_id": z["zona_id"], "zona": z["nome"],
                      "atividade_id": a["atividade_id"], "atividade": a["nome"], "pct": round(pct, 1),
                      "frase": _cap(s.get("frase"), 400), "selecionada": True})
    return {"propostas": props, "fonte": fonte}


def _cap_multi(s: Any, n: int) -> str:
    linhas = [re.sub(r"[ \t]+", " ", x).strip() for x in str(s or "").splitlines()]
    return "\n".join(x for x in linhas if x)[:n]


def juntar_texto(atual: str, novo: str, limite: int) -> str:
    """Acrescenta ao texto do diário sem repetir linhas já escritas."""
    atual = (atual or "").strip()
    existentes = {norm(x) for x in atual.splitlines()}
    novas = [x for x in (novo or "").splitlines() if x.strip() and norm(x) not in existentes]
    return ("\n".join([atual] + novas) if atual else "\n".join(novas)).strip()[:limite]


# ====================================================================== mapa da obra (avanço por zona)
def estrutura_valida(pisos: list[dict], zonas: list[dict], atividades: list[dict]) -> tuple[Optional[str], dict]:
    """Valida e normaliza a estrutura. Devolve (erro, estrutura)."""
    if len(pisos) > MAX_PISOS or len(zonas) > MAX_ZONAS or len(atividades) > MAX_ATIVIDADES:
        return "demasiados elementos", {}
    out_p, ids_p = [], set()
    for i, p in enumerate(pisos):
        pid = _id_seguro(p.get("piso_id"), "piso")
        nome = _cap(p.get("nome"), 80)
        if not nome or pid in ids_p:
            return "piso sem nome ou repetido", {}
        ids_p.add(pid)
        out_p.append({"piso_id": pid, "nome": nome, "ordem": i, **({"planta": p["planta"]} if isinstance(p.get("planta"), dict) else {})})
    out_z, ids_z = [], set()
    for z in zonas:
        zid = _id_seguro(z.get("zona_id"), "zona")
        nome = _cap(z.get("nome"), 80)
        if not nome or zid in ids_z:
            return "zona sem nome ou repetida", {}
        if z.get("piso_id") not in ids_p:
            return f"a zona «{nome}» não pertence a nenhum piso", {}
        ids_z.add(zid)
        r = z.get("ret")
        ret = None
        if isinstance(r, dict):
            vals = [_num(r.get(k)) for k in ("x", "y", "w", "h")]
            if any(v is None for v in vals) or vals[2] <= 0 or vals[3] <= 0 or vals[0] < 0 or vals[1] < 0 \
                    or vals[0] + vals[2] > 100.01 or vals[1] + vals[3] > 100.01:
                return f"retângulo inválido na zona «{nome}»", {}
            ret = dict(zip(("x", "y", "w", "h"), (round(v, 2) for v in vals)))
        area = _num(z.get("area_m2"))
        out_z.append({"zona_id": zid, "piso_id": z["piso_id"], "nome": nome, "ret": ret,
                      "area_m2": round(area, 2) if area and 0 < area < 1e6 else None})
    out_a, ids_a = [], set()
    for a in atividades:
        aid = _id_seguro(a.get("atividade_id"), "atv")
        nome = _cap(a.get("nome"), 80)
        peso = _num(a.get("peso"))
        peso = 1.0 if peso is None else peso
        if not nome or aid in ids_a or norm(nome) in {norm(x["nome"]) for x in out_a}:
            return "atividade sem nome ou repetida", {}
        if not 0 < peso <= 100:
            return f"peso inválido na atividade «{nome}»", {}
        ids_a.add(aid)
        out_a.append({"atividade_id": aid, "nome": nome, "peso": peso})
    return None, {"pisos": out_p, "zonas": out_z, "atividades": out_a}


def modelo_atividades(chave: str) -> list[dict]:
    m = TX.MODELOS_ATIVIDADES.get(chave)
    if not m:
        return []
    return [{"atividade_id": f"atv_{i + 1:02d}", "nome": n, "peso": p} for i, (n, p) in enumerate(m["itens"])]


def _media(valores: list[tuple[float, float]]) -> Optional[float]:
    tot = sum(p for _, p in valores)
    return round(sum(v * p for v, p in valores) / tot, 1) if tot > 0 else None


def resumo_mapa(mapa: dict) -> dict:
    """Avanço ponderado por zona, por piso, por atividade e global (só a partir do que foi registado)."""
    pisos, zonas, ativ = mapa.get("pisos") or [], mapa.get("zonas") or [], mapa.get("atividades") or []
    prog = mapa.get("progresso") or {}
    pct = lambda z, a: float((prog.get(f"{z}|{a}") or {}).get("pct") or 0)  # noqa: E731
    zres = []
    for z in zonas:
        av = _media([(pct(z["zona_id"], a["atividade_id"]), a["peso"]) for a in ativ])
        zres.append({"zona_id": z["zona_id"], "piso_id": z["piso_id"], "nome": z["nome"], "avanco": av if av is not None else 0.0,
                     "por_atividade": {a["atividade_id"]: pct(z["zona_id"], a["atividade_id"]) for a in ativ}})
    usa_area = bool(zonas) and all(z.get("area_m2") for z in zonas)
    peso_z = {z["zona_id"]: (z["area_m2"] if usa_area else 1.0) for z in zonas}
    pres = []
    for p in pisos:
        zs = [z for z in zres if z["piso_id"] == p["piso_id"]]
        pres.append({"piso_id": p["piso_id"], "nome": p["nome"], "zonas": len(zs),
                     "avanco": _media([(z["avanco"], peso_z[z["zona_id"]]) for z in zs]) or 0.0, "tem_planta": bool(p.get("planta"))})
    ares = [{"atividade_id": a["atividade_id"], "nome": a["nome"], "peso": a["peso"],
             "avanco": _media([(pct(z["zona_id"], a["atividade_id"]), peso_z[z["zona_id"]]) for z in zonas]) or 0.0} for a in ativ]
    glob = _media([(z["avanco"], peso_z[z["zona_id"]]) for z in zres]) or 0.0
    registos = [v for v in prog.values() if isinstance(v, dict)]
    ultimo = max((v.get("at") or "" for v in registos), default=None)
    return {"global": glob, "pisos": pres, "zonas": zres, "atividades": ares, "base": "area" if usa_area else "zonas_iguais",
            "registos": len(registos), "ultimo_registo": ultimo or None,
            "concluidas": sum(1 for z in zres if z["avanco"] >= 100), "por_iniciar": sum(1 for z in zres if z["avanco"] <= 0)}


def cor_avanco(pct: float) -> str:
    """Escala usada no ecrã e no PDF: cinzento (0) → âmbar → verde (100)."""
    if pct <= 0:
        return "#e2e8f0"
    if pct < 25:
        return "#fde68a"
    if pct < 50:
        return "#fcd34d"
    if pct < 75:
        return "#a7f3d0"
    if pct < 100:
        return "#34d399"
    return "#047857"


# ====================================================================== tesouraria da obra
def _fim_mes(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def _evento(data_: date, valor: float, estado: str, categoria: str, origem: str, descricao: str, ref: str = "", vencido: bool = False) -> dict:
    return {"data": data_.isoformat(), "valor": round(valor, 2), "estado": estado, "categoria": categoria, "origem": origem,
            "descricao": _cap(descricao, 200), "ref": ref, "vencido": vencido}


def tesouraria(faturas: Iterable[dict], encomendas: Iterable[dict], horas: Iterable[dict], manuais: Iterable[dict],
               hoje: date, taxa_horaria: Optional[float] = None, prazo_fornecedor: int = 30) -> dict:
    """Fluxo de caixa da obra: realizado até hoje e previsto depois, por mês, com o pior saldo previsto."""
    ev: list[dict] = []
    notas, alertas = [], []
    vencidas, valor_vencido = 0, 0.0
    n_fat = 0
    for f in faturas:
        if f.get("status") in ("draft", "cancelled", "canceled", "annulee", "anulada") or f.get("trashed_at"):
            continue
        n_fat += 1
        ref = f.get("number") or f.get("doc_id") or ""
        for p in f.get("payments") or []:
            v, d = _num(p.get("amount")), parse_date(p.get("date"))
            if v and d:
                ev.append(_evento(d, v, "realizado", "cliente", "fatura", f"{ref} — {f['title']}" if f.get("title") else ref, ref))
        resto = _num(f.get("remaining_due"))
        if resto is None:
            tot = _num((f.get("totals") or {}).get("ttc")) or 0
            resto = tot - sum(_num(p.get("amount")) or 0 for p in f.get("payments") or [])
        if resto and resto > 0.009:
            venc = parse_date(f.get("due_date")) or parse_date(f.get("issue_date")) or hoje
            atrasada = venc < hoje
            if atrasada:
                vencidas += 1
                valor_vencido += resto
            ev.append(_evento(max(venc, hoje), resto, "previsto", "cliente", "fatura", f"{ref} — por receber", ref, atrasada))
    if n_fat:
        notas.append(TX.TES_NOTAS["faturas"])
    n_enc = 0
    for o in encomendas:
        v = _num(o.get("amount"))
        if not v or v <= 0:
            continue
        n_enc += 1
        d = parse_date((o.get("delivery") or {}).get("expected_date")) or \
            ((parse_date(o.get("sent_at")) or parse_date(o.get("created_at")) or hoje) + timedelta(days=prazo_fornecedor))
        ev.append(_evento(d, -v, "realizado" if d <= hoje else "previsto", "fornecedor", "encomenda",
                          f"{o.get('supplier') or ''}", o.get("order_id") or ""))
    if n_enc:
        notas.append(TX.TES_NOTAS["encomendas"].format(prazo=prazo_fornecedor))
    por_mes: dict[date, float] = {}
    sem_taxa = False
    for h in horas:
        hv, d = _num(h.get("hours")), parse_date(h.get("date"))
        if h.get("status") != "validated" or not hv or hv <= 0 or not d:
            continue
        if not taxa_horaria or taxa_horaria <= 0:
            sem_taxa = True
            continue
        fm = _fim_mes(d)
        por_mes[fm] = por_mes.get(fm, 0) + hv * taxa_horaria
    for fm, v in sorted(por_mes.items()):
        ev.append(_evento(fm, -v, "realizado" if fm <= hoje else "previsto", "mao_obra", "horas", f"{fm.strftime('%m/%Y')}"))
    if por_mes:
        notas.append(TX.TES_NOTAS["mao_obra"])
    if sem_taxa:
        notas.append(TX.TES_NOTAS["sem_taxa"])
    n_man = 0
    for m in manuais:
        v, d = _num(m.get("valor")), parse_date(m.get("data"))
        if not v or not d or m.get("tipo") not in ("entrada", "saida"):
            continue
        n_man += 1
        estado = "realizado" if m.get("realizado") else "previsto"
        ev.append(_evento(d if estado == "realizado" else max(d, hoje), v if m["tipo"] == "entrada" else -v, estado,
                          m.get("categoria") if m.get("categoria") in TX.CATEGORIAS_TES else "outro", "manual",
                          f"{m.get('descricao') or ''}{' — ' + m['contraparte'] if m.get('contraparte') else ''}",
                          m.get("mov_id") or "", vencido=estado == "previsto" and d < hoje))
    if n_man:
        notas.append(TX.TES_NOTAS["manuais"])
    ev.sort(key=lambda e: (e["data"], -e["valor"]))
    saldo, pior, pior_data = 0.0, 0.0, None
    meses: dict[str, dict] = {}
    for e in ev:
        saldo += e["valor"]
        mk = e["data"][:7]
        mm = meses.setdefault(mk, {"mes": mk, "entradas": 0.0, "saidas": 0.0, "entradas_previstas": 0.0, "saidas_previstas": 0.0})
        chave = ("entradas" if e["valor"] > 0 else "saidas") + ("_previstas" if e["estado"] == "previsto" else "")
        mm[chave] += abs(e["valor"])
        mm["saldo"] = round(saldo, 2)
        if saldo < pior - 0.004:
            pior, pior_data = saldo, e["data"]
    for m in meses.values():
        for k in ("entradas", "saidas", "entradas_previstas", "saidas_previstas"):
            m[k] = round(m[k], 2)
    real = [e for e in ev if e["estado"] == "realizado"]
    prev = [e for e in ev if e["estado"] == "previsto"]
    kpis = {"recebido": round(sum(e["valor"] for e in real if e["valor"] > 0), 2),
            "pago": round(-sum(e["valor"] for e in real if e["valor"] < 0), 2),
            "por_receber": round(sum(e["valor"] for e in prev if e["valor"] > 0), 2),
            "por_pagar": round(-sum(e["valor"] for e in prev if e["valor"] < 0), 2),
            "vencido": round(valor_vencido, 2), "faturas_vencidas": vencidas}
    kpis["saldo_atual"] = round(kpis["recebido"] - kpis["pago"], 2)
    kpis["saldo_final_previsto"] = round(saldo, 2)
    kpis["pior_saldo"] = round(pior, 2) if pior_data else None
    kpis["pior_saldo_data"] = pior_data
    if vencidas:
        alertas.append(TX.TES_ALERTAS["vencido"].format(n=vencidas, valor=f"{valor_vencido:,.2f}".replace(",", " ").replace(".", ",")))
    if pior_data:
        alertas.append(TX.TES_ALERTAS["negativo"].format(data="/".join(reversed(pior_data.split("-"))),
                                                          valor=f"{pior:,.2f}".replace(",", " ").replace(".", ",")))
    return {"kpis": kpis, "meses": [meses[k] for k in sorted(meses)], "eventos": ev[-400:], "alertas": alertas,
            "notas": notas, "hoje": hoje.isoformat(), "fontes": {"faturas": n_fat, "encomendas": n_enc, "manuais": n_man,
                                                                 "meses_mao_obra": len(por_mes)}}


# ====================================================================== câmaras
def camara_valida(c: dict) -> tuple[Optional[str], dict]:
    nome = _cap(c.get("nome"), 80) or TX.CAMARA_PADRAO
    url = str(c.get("url") or "").strip()[:800]
    tipo = c.get("tipo") if c.get("tipo") in ("imagem", "video", "embed") else "imagem"
    u = urlparse(url)
    if u.scheme != "https" or not u.netloc or u.username or u.password:
        return TX.T["camara_url"], {}
    if tipo == "embed" and u.hostname not in TX.EMBED_HOSTS:
        return TX.T["camara_embed"].format(hosts=", ".join(sorted({h.removeprefix("www.") for h in TX.EMBED_HOSTS}))), {}
    refresh = int(_num(c.get("atualizar_s")) or 30)
    return None, {"camara_id": _id_seguro(c.get("camara_id"), "cam"), "nome": nome, "url": url, "tipo": tipo,
                  "atualizar_s": min(max(refresh, 5), 600), "partilhar": bool(c.get("partilhar")),
                  "zona": _cap(c.get("zona"), 80)}


def agora_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
