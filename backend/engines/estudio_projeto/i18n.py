"""Língua de saída do Estúdio de Projeto (mesmo método do motor LSF — engines/lsf/i18n.py).

Os textos internos do motor (nomes de materiais, avisos, títulos das peças, mensagens das operações) ficam em português:
são chaves estáveis, iguais em construpilot.pt e construpilot.fr. À saída (API, SVG, PDF, DXF, CSV, IFC, Assistente)
`tr` / `traduzir` devolvem o texto na língua pedida a partir do catálogo `i18n_fr*.py`.

O modelo é a exceção: é editado no ecrã e volta ao servidor. Por isso há dois sentidos, só para os campos do modelo que
guardam nomes de catálogo (tipos de parede, camadas, nomes de piso por omissão):
    `modelo_saida`   interno → língua do site (o que o editor mostra e devolve)
    `modelo_entrada` língua do site → interno (antes de `normalizar`)
Texto escrito pelo utilizador (nomes de divisões, notas, camadas próprias) passa sem alteração nos dois sentidos.

Só o francês tem catálogo; em português tudo fica exatamente como o motor produz.
"""
from __future__ import annotations

import contextvars as _cv
import functools as _ft
import re as _re
import unicodedata as _ud
from typing import Any, Dict, List, Optional

LANGS = ("pt", "fr")

try:
    from core.market import SITE_LANG as _SITE_LANG
except Exception:  # noqa: BLE001
    _SITE_LANG = "pt"
_LANG = _cv.ContextVar("estudio_lang", default=_SITE_LANG if _SITE_LANG in LANGS else "pt")


def lingua_atual() -> str:
    return _LANG.get()


class usar_lingua:
    """with usar_lingua("fr"): … — língua dos textos produzidos por `tr` sem argumento."""

    def __init__(self, lang: Optional[str]):
        self.lang, self.tok = (lang if lang in LANGS else "pt"), None

    def __enter__(self):
        self.tok = _LANG.set(self.lang)
        return self

    def __exit__(self, *a):
        _LANG.reset(self.tok)


def _limpo(s: Any) -> str:
    return _ud.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower().strip()


@_ft.lru_cache(maxsize=1)
def _cat():
    from engines.estudio_projeto import i18n_fr as F
    exatos: Dict[str, str] = dict(F.EXATOS)
    modelos = []
    for pt, fr in F.MODELOS:
        rx = "".join("(.+?)" if p == "{}" else (r"(-?[\d.,]+)" if p == "{n}" else _re.escape(p)) for p in _re.split(r"(\{n?\})", pt))
        modelos.append((len(pt), _re.compile(rx, _re.S), fr))
    modelos.sort(key=lambda m: -m[0])
    return exatos, [(rx, fr) for _, rx, fr in modelos], dict(F.FRAGMENTOS), dict(F.CHAVES), dict(F.CAMADAS_DXF)


@_ft.lru_cache(maxsize=40000)
def _tr_fr(texto: str, parte: bool = False) -> str:
    """`parte` = valor capturado por um modelo ou pedaço de um texto composto: aí valem também os fragmentos
    (palavras soltas como «fachada» ou «duas aguas»), que nunca são traduzidos como texto inteiro."""
    exatos, modelos, fragmentos, _, _ = _cat()
    if texto in exatos:
        return exatos[texto]
    if parte and texto in fragmentos:
        return fragmentos[texto]
    s = texto.strip()
    if s != texto and s:
        t = _tr_fr(s, parte)
        return texto.replace(s, t) if t != s else texto
    for rx, fr in modelos:
        m = rx.fullmatch(texto)
        if m:
            return fr.format(*[_tr_fr(g, True) for g in m.groups()])
    for sep in ("; ", " · ", " — "):                       # textos compostos: cada parte é traduzida por si
        if sep in texto:
            partes = texto.split(sep)
            novas = [_tr_fr(p, True) for p in partes]
            if novas != partes:
                return sep.join(novas)
    return texto


def tr(texto: Any, lang: Optional[str] = None) -> Any:
    """Texto do motor na língua pedida (por omissão a de `usar_lingua`, que parte da língua do site)."""
    if not isinstance(texto, str) or not texto:
        return texto
    return _tr_fr(texto) if (lang or _LANG.get()) == "fr" else texto


def parte(valor: Any, lang: Optional[str] = None) -> Any:
    """Como `tr`, mas para um valor solto que pode ser uma chave do modelo («janela», «duas aguas», «sim»)."""
    if not isinstance(valor, str) or not valor:
        return valor
    return _tr_fr(valor, True) if (lang or _LANG.get()) == "fr" else valor


def tr_chave(nome: str, lang: Optional[str] = None) -> str:
    """Nome de propriedade ou de conjunto próprio do IFC (CP_Estudio, IdModelo…): identificador sem espaços nem acentos."""
    if (lang or _LANG.get()) != "fr":
        return nome
    return _cat()[3].get(nome, nome)


def camada_dxf(nome: str, lang: Optional[str] = None) -> str:
    if (lang or _LANG.get()) != "fr":
        return nome
    return _cat()[4].get(nome, nome)


# chaves cujo valor é lógica (identificadores, tipos, códigos, cores): nunca traduzidas
_CHAVES_LOGICAS = frozenset({
    "id", "ids", "tipo", "cor", "padrao", "forma", "ifc", "lado", "dobradica", "proprios", "codigo", "origem", "parede", "sentido",
    "cumeeira", "lado_baixo", "filename", "code", "t", "anchor", "cam", "op", "eixo", "a", "b", "pts", "updated_at"})


def traduzir(obj: Any, lang: Optional[str] = None) -> Any:
    """Cópia de um resultado (dict / list) com os textos traduzidos; as chaves de lógica não mudam. Não usar no modelo:
    para esse há `modelo_saida`."""
    lg = lang or _LANG.get()
    if lg != "fr":
        return obj
    if isinstance(obj, str):
        return _tr_fr(obj)
    if isinstance(obj, list):
        return [traduzir(x, lg) for x in obj]
    if isinstance(obj, tuple):
        return tuple(traduzir(x, lg) for x in obj)
    if isinstance(obj, dict):
        return {k: (v if k in _CHAVES_LOGICAS else traduzir(v, lg)) for k, v in obj.items()}
    return obj


# ---------------------------------------------------------------- peças desenhadas
def desenho(des: Dict[str, Any], lang: Optional[str] = None) -> Dict[str, Any]:
    """Peça desenhada (planta, alçado, corte) com título, rodapé e textos na língua de saída. A geometria não muda."""
    lg = lang or _LANG.get()
    if lg != "fr":
        return des
    out = dict(des)
    out["titulo"] = _tr_fr(des.get("titulo") or "")
    if des.get("rodape"):
        out["rodape"] = _tr_fr(des["rodape"])
    out["itens"] = [({**it, "txt": _tr_fr(it["txt"])} if it.get("t") == "text" else it) for it in des["itens"]]
    return out


def desenhos(lista: List[Dict[str, Any]], lang: Optional[str] = None) -> List[Dict[str, Any]]:
    return [desenho(d, lang) for d in lista]


# ---------------------------------------------------------------- modelo: interno ↔ língua do site
@_ft.lru_cache(maxsize=1)
def _vocabulario_modelo():
    """Nomes de catálogo que o modelo guarda (tipos de parede, camadas, pisos por omissão): interno → francês e o inverso."""
    from engines.estudio_projeto import i18n_fr as F
    from engines.estudio_projeto import materiais as MAT
    from engines.estudio_projeto import modelo as M
    exatos = _cat()[0]
    nomes = {m["nome"] for m in MAT.BIBLIOTECA}
    for t in list(MAT.PAREDES_TIPO.values()) + list(M.TIPOS_PT.values()) + list(M.TIPOS_BASE.values()):
        nomes.add(t["nome"])
        nomes.update(c["material"] for c in t["camadas"])
    nomes.update(F.PISOS)
    ida = {n: exatos[n] for n in nomes if n in exatos and exatos[n] != n}
    volta: Dict[str, str] = {}
    for pt, fr in ida.items():
        volta.setdefault(fr, pt)
    return ida, volta


def _modelo_com(m: Any, mapa: Dict[str, str]) -> Any:
    if not isinstance(m, dict):
        return m
    out = dict(m)
    if isinstance(m.get("pisos"), list):
        out["pisos"] = [({**p, "nome": mapa.get(p["nome"], p["nome"])} if isinstance(p, dict) and isinstance(p.get("nome"), str) else p)
                        for p in m["pisos"]]
    if isinstance(m.get("tipos_parede"), dict):
        tipos = {}
        for tid, t in m["tipos_parede"].items():
            if isinstance(t, dict):
                t = dict(t)
                if isinstance(t.get("nome"), str):
                    t["nome"] = mapa.get(t["nome"], t["nome"])
                if isinstance(t.get("camadas"), list):
                    t["camadas"] = [({**c, "material": mapa.get(c["material"], c["material"])}
                                     if isinstance(c, dict) and isinstance(c.get("material"), str) else c) for c in t["camadas"]]
            tipos[tid] = t
        out["tipos_parede"] = tipos
    return out


def modelo_saida(m: Dict[str, Any], lang: Optional[str] = None) -> Dict[str, Any]:
    return _modelo_com(m, _vocabulario_modelo()[0]) if (lang or _LANG.get()) == "fr" else m


def modelo_entrada(m: Any, lang: Optional[str] = None) -> Any:
    return _modelo_com(m, _vocabulario_modelo()[1]) if (lang or _LANG.get()) == "fr" else m


def catalogo_saida(cat: Dict[str, Any], lang: Optional[str] = None) -> Dict[str, Any]:
    """Catálogo do editor na língua de saída. As paredes de partida e as paredes-tipo são pedaços de modelo (o editor
    copia-as para o modelo): seguem a regra do modelo."""
    lg = lang or _LANG.get()
    if lg != "fr":
        return cat
    out = traduzir({k: v for k, v in cat.items() if k not in ("tipos_parede", "paredes_tipo")}, lg)
    for k in ("tipos_parede", "paredes_tipo"):
        if k in cat:
            out[k] = _modelo_com({"tipos_parede": cat[k]}, _vocabulario_modelo()[0])["tipos_parede"]
    return out


# ---------------------------------------------------------------- operações pedidas em francês
@_ft.lru_cache(maxsize=1)
def _indices_fr():
    from engines.estudio_projeto import i18n_fr as F
    from engines.estudio_projeto import materiais as MAT
    from engines.estudio_projeto import objetos as OBJ
    exatos = _cat()[0]
    acab = {k: [(x["id"], _limpo(exatos.get(x["nome"], x["nome"]))) for x in v] for k, v in MAT.ACABAMENTOS.items()}
    objs = [(k, _limpo(exatos.get(v["nome"], v["nome"]))) for k, v in OBJ.OBJETOS.items()]
    tipos = [(tid, _limpo(exatos.get(t["nome"], t["nome"]))) for tid, t in MAT.PAREDES_TIPO.items()]
    sinon = {campo: {_limpo(k): v for k, v in d.items()} for campo, d in F.SINONIMOS.items()}
    return acab, objs, tipos, sinon


def _acabamento_fr(tipo: str, texto: Any) -> Any:
    """Identificador do acabamento a partir do nome francês (ou de parte dele). Sem correspondência, devolve o texto
    recebido: o motor tenta então o identificador / nome interno e, se também falhar, diz que não conhece."""
    if not isinstance(texto, str) or not texto.strip():
        return texto
    t = _limpo(texto)
    lista = _indices_fr()[0][tipo]
    for ident, nome in lista:
        if ident == t or nome == t:
            return ident
    achados = [(ident, nome) for ident, nome in lista if t in nome]
    if not achados:
        pal = t.split()
        achados = [(ident, nome) for ident, nome in lista if pal and all(p in nome for p in pal)]
    return min(achados, key=lambda x: len(x[1]))[0] if achados else texto


def operacoes_entrada(m: Dict[str, Any], operacoes: List[Any], lang: Optional[str] = None) -> List[Any]:
    """Operações pedidas na língua do site → as que o motor entende. Só nomes são convertidos (acabamentos, objetos,
    tipos de parede, lados, tipos de vão, de cobertura e de escada, pisos e divisões sem nome); identificadores,
    medidas e textos livres ficam como vieram."""
    if (lang or _LANG.get()) != "fr" or not isinstance(operacoes, list):
        return operacoes
    acab, objs, tipos, sinon = _indices_fr()
    volta = _vocabulario_modelo()[1]
    pisos_fr = {_limpo(_tr_fr(p["nome"])): p["id"] for p in (m or {}).get("pisos") or []}
    out = []
    for o in operacoes:
        if not isinstance(o, dict):
            out.append(o)
            continue
        o = dict(o)
        op = o.get("op")
        for campo in ("tipo", "lado", "sentido", "de", "cumeeira", "lado_baixo"):
            mapa = sinon.get(f"{op}.{campo}") or (sinon.get(campo) if campo != "tipo" else None)
            if mapa and isinstance(o.get(campo), str) and _limpo(o[campo]) in mapa:
                o[campo] = mapa[_limpo(o[campo])]
        for k in acab:
            if o.get(k) and op in ("materiais", "divisao", "vao", "mudar_vao"):
                o[k] = _acabamento_fr(k, o[k])
        if op == "objeto" and isinstance(o.get("tipo"), str):
            t = _limpo(o["tipo"])
            pal = t.replace("_", " ").split()
            ident = next((k for k, n in objs if k == o["tipo"] or n == t), None) or \
                next((k for k, n in sorted(objs, key=lambda x: len(x[1])) if pal and all(p in n for p in pal)), None)
            if ident:
                o["tipo"] = ident
        if op in ("parede", "sala", "tipo_parede") and isinstance(o.get("tipo"), str) and o["tipo"] not in (m or {}).get("tipos_parede", {}):
            t = _limpo(o["tipo"])
            if o["tipo"] in volta:
                o["tipo"] = volta[o["tipo"]]
            else:
                ident = next((tid for tid, n in tipos if n == t), None) or next((tid for tid, n in tipos if t and t in n), None)
                if ident:
                    o["tipo"] = ident
        if isinstance(o.get("piso"), str) and _limpo(o["piso"]) in pisos_fr:
            o["piso"] = pisos_fr[_limpo(o["piso"])]
        for campo in ("nome", "divisao"):                      # « Pièce 3 » → « Divisão 3 » (divisão ainda sem nome)
            if op in ("divisao", "escada", "objeto") and isinstance(o.get(campo), str):
                mm = _re.fullmatch(r"\s*pi[eè]ce\s+(\d+)\s*", o[campo], _re.I)
                if mm:
                    o[campo] = f"Divisão {mm.group(1)}"
        out.append(o)
    return out
