"""Processo completo (projeto de execução, processo de licenciamento, processo de concurso…): importação de dezenas de ficheiros
ou de um ZIP, inventário classificado por especialidade e por piso — contexto português (RJUE, especialidades, peças escritas).

- expand(name, data): descomprime um ZIP em segurança (tamanho, número, taxa de compressão, caminhos, ZIP aninhado num só nível).
- classify(name, text): especialidade (arquitetura, estabilidade, cofragem, armaduras, águas e esgotos, eletricidade/ITED, AVAC, gás,
  térmica, acústica, SCIE, estudo geotécnico, caderno de encargos, mapa de quantidades, licenciamento RJUE, PSS…) + piso
  (Fundações, Cave -1, R/C, Piso 1…, Cobertura) e, quando o nome segue a codificação dos gabinetes (XYZ_PE_EST_Z1_P1_ARM_0171),
  zona, natureza, elemento, número e revisão.
- register_from_rows / register_from_text: «Lista de desenhos» (XLS/PDF) → desenhos esperados com a última revisão.
- check_register(files, register): desenhos em falta, revisões desatualizadas, várias revisões, ficheiros fora da lista.

Porta do motor .fr (engines/dossier.py) adaptada a Portugal; continua a reconhecer as codificações francesas (RDC, R+1, SS1, COF…).
"""
from __future__ import annotations

import io
import re
import unicodedata
import zipfile
from pathlib import PurePosixPath

ALLOWED = {"pdf", "dwg", "dxf", "xlsx", "xls", "csv", "docx", "txt", "png", "jpg", "jpeg", "webp"}
IMAGES = {"png", "jpg", "jpeg", "webp"}
MAX_FILES = 400
MAX_FILE = 200 * 1024 * 1024
MAX_TOTAL = 1536 * 1024 * 1024
MAX_RATIO = 200          # bomba ZIP: tamanho descomprimido / comprimido

# Especialidades / peças de um processo de obra português → rótulo PT-PT e grupo.
LABELS = {
    "arquitetura": "Projeto de arquitetura",
    "estabilidade": "Estabilidade / estruturas",
    "cofragem": "Plantas de cofragem",
    "armaduras": "Plantas de armaduras",
    "nota_calculo": "Notas / memórias de cálculo",
    "geotecnia": "Estudo geotécnico",
    "aguas_esgotos": "Águas, esgotos e pluviais",
    "eletricidade": "Instalações elétricas / ITED",
    "avac": "AVAC / ventilação",
    "gas": "Gás",
    "termica": "Comportamento térmico / SCE",
    "acustica": "Acústica (RRAE)",
    "scie": "Segurança contra incêndio (SCIE)",
    "topografia": "Levantamento topográfico / implantação",
    "caderno_encargos": "Caderno de encargos",
    "mapa_quantidades": "Mapa de quantidades / medições",
    "memoria_descritiva": "Memória descritiva e justificativa",
    "licenciamento": "Licenciamento / comunicação prévia (RJUE)",
    "seguranca_saude": "Plano de segurança e saúde",
    "lista_desenhos": "Lista de desenhos",
    "fotografia": "Fotografias",
    "outro": "Outros",
}
GROUPS = {
    "projeto_arquitetura": ("arquitetura",),
    "especialidades": ("estabilidade", "cofragem", "armaduras", "nota_calculo", "aguas_esgotos", "eletricidade", "avac", "gas",
                       "termica", "acustica", "scie"),
    "elementos_base": ("geotecnia", "topografia", "fotografia"),
    "pecas_escritas": ("caderno_encargos", "mapa_quantidades", "memoria_descritiva", "seguranca_saude", "lista_desenhos"),
    "licenciamento": ("licenciamento",),
}
GROUP_LABELS = {"projeto_arquitetura": "Projeto de arquitetura", "especialidades": "Projetos de especialidades",
                "elementos_base": "Elementos de base (geotecnia, topografia, fotografias)", "pecas_escritas": "Peças escritas",
                "licenciamento": "Licenciamento (RJUE)", "outros": "Outros"}
PLAN_DISCIPLINES = {"arquitetura", "estabilidade", "cofragem", "armaduras", "aguas_esgotos", "eletricidade", "avac", "gas", "topografia"}


class DossierError(ValueError):
    pass


def ext_of(name: str) -> str:
    return name.lower().rsplit(".", 1)[-1] if "." in name else ""


def _plain(s: str) -> str:
    """minúsculas sem acentos (pavimentos e alçados → pavimentos e alcados)."""
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c)).lower()


def expand(name: str, data: bytes, _depth: int = 0) -> tuple[list[tuple[str, bytes]], list[str]]:
    """→ ([(caminho, bytes)], [ficheiros ignorados com o motivo])."""
    if ext_of(name) != "zip" and not data.startswith(b"PK\x03\x04"):
        ok = ext_of(name) in ALLOWED
        return ([(name, data)] if ok else []), ([] if ok else [f"{name}: formato não suportado"])
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise DossierError(f"{name}: arquivo ZIP ilegível ou danificado") from None
    out, skipped, total = [], [], 0
    infos = [i for i in zf.infolist() if not i.is_dir()]
    if len(infos) > MAX_FILES:
        raise DossierError(f"{name}: {len(infos)} ficheiros (máximo {MAX_FILES} por arquivo)")
    for info in infos:
        path = PurePosixPath(info.filename.replace("\\", "/"))
        base = path.name
        if any(p in ("..", "") for p in path.parts[:-1]) or path.is_absolute():
            skipped.append(f"{info.filename}: caminho recusado")
            continue
        if base.startswith(".") or "__MACOSX" in path.parts or base.lower() in ("thumbs.db", "desktop.ini"):
            continue
        if info.flag_bits & 0x1:
            skipped.append(f"{info.filename}: ficheiro encriptado")
            continue
        if info.file_size > MAX_FILE:
            skipped.append(f"{info.filename}: demasiado volumoso (> 200 MB)")
            continue
        if info.compress_size and info.file_size / max(info.compress_size, 1) > MAX_RATIO:
            skipped.append(f"{info.filename}: taxa de compressão anómala")
            continue
        total += info.file_size
        if total > MAX_TOTAL:
            raise DossierError(f"{name}: conteúdo descomprimido > {MAX_TOTAL // 1024 // 1024} MB")
        e = ext_of(base)
        if e == "zip":
            if _depth >= 1:
                skipped.append(f"{info.filename}: ZIP aninhado em mais de um nível")
                continue
            inner, sk = expand(base, zf.read(info), _depth + 1)
            out += [(f"{path.parent}/{n}" if str(path.parent) != "." else n, d) for n, d in inner]
            skipped += sk
            continue
        if e not in ALLOWED:
            skipped.append(f"{info.filename}: formato não suportado")
            continue
        out.append((str(path), zf.read(info)))
    if len(out) > MAX_FILES:
        raise DossierError(f"{name}: mais de {MAX_FILES} ficheiros úteis")
    return out, skipped


def _w(alts: str) -> str:
    return r"(^|[^a-z])(" + alts + r")([^a-z]|$)"


# Ordem relevante: peças escritas e especialidades antes da arquitetura (palavras genéricas: planta, corte, alçado).
_DISC = [
    ("cofragem", _w(r"cof|coff|cofragem|cofragens|coffrage|formwork")),
    ("armaduras", _w(r"arm|armaduras?|fer|ferr|ferraillage|rebar")),
    ("nota_calculo", r"notas? de calculo|memorias? de calculo|" + _w(r"ndc|ndh")),
    ("geotecnia", r"estudo geotecnico|relatorio geotecnico|prospecao geotecnica|" + _w(r"geotec\w*|geo|g1|g2|sondagens?|spt")),
    ("caderno_encargos", r"caderno de encargos|clausulas tecnicas|especificacoes tecnicas|" + _w(r"ce|cctp|cctc|caderno")),
    ("mapa_quantidades", r"mapas?( de)? (quantidades|trabalhos|medicoes)|" + _w(r"mq|mqt|mtq|quantidades|medicoes|medicao|orcamento|dpgf|dqe|bpu")),
    ("lista_desenhos", r"lista de desenhos|lista de pecas desenhadas|indice de desenhos|liste des plans|" + _w(r"bordereau|ld")),
    ("licenciamento", r"comunicacao previa|termos? de responsabilidade|pedido de informacao previa|autorizacao de utilizacao|"
                      + _w(r"licen\w*|rjue|alvara|pip|permis")),
    ("seguranca_saude", r"plano de seguranca|seguranca e saude|compilacao tecnica|" + _w(r"pss")),
    ("scie", r"seguranca contra incendio|medidas de autoprotecao|" + _w(r"scie|fsci|incendio")),
    ("termica", r"comportamento termico|pre certificado|certificado energetico|" + _w(r"termic\w*|reh|recs|sce")),
    ("acustica", _w(r"acustic\w*|rrae|ruido")),
    ("aguas_esgotos", r"redes prediais|aguas e esgotos|" + _w(r"aguas?|esgotos?|drenagem|pluviais|abastecimento|aae|aap|aar|hidraulic\w*|canaliza\w*|plb|plomb\w*")),
    ("gas", _w(r"gas")),
    ("eletricidade", _w(r"eletric\w*|electric\w*|ited|itur|telecom\w*|iel|ele|elec\w*|cfo|cfa")),
    ("avac", _w(r"avac|hvac|cvc|climatiza\w*|ventila\w*|vmc|aquecimento|chauf\w*")),
    ("topografia", r"levantamento topografico|" + _w(r"topograf\w*|levantamento|implanta\w*")),
    ("estabilidade", r"betao armado|" + _w(r"estab\w*|est|estrutur\w*|fundac\w*|chp|charpente|metalic\w*")),
    ("memoria_descritiva", r"memoria descritiva|" + _w(r"md|mdj")),
    ("arquitetura", _w(r"arq\w*|arc|archi\w*|ep|ap|apd|aps|pro|dce|plan|plantas?|alcados?|fachadas?|facade|cortes?|coupe|perfis?")),
]
_TEXT_HINTS = [   # 1.ª página de um PDF sem nome expressivo
    ("cofragem", r"planta de cofragem|plan de coffrage"),
    ("armaduras", r"planta de armaduras|pormenores de armaduras|plan de ferraillage"),
    ("geotecnia", r"estudo geotecnico|relatorio geotecnico|prospecao geotecnica|etude geotechnique"),
    ("caderno_encargos", r"caderno de encargos|clausulas tecnicas|cahier des clauses techniques"),
    ("mapa_quantidades", r"mapa de quantidades|mapa de trabalhos e quantidades|decomposition du prix global"),
    ("licenciamento", r"comunicacao previa|licenciamento|regime juridico da urbanizacao|termo de responsabilidade"),
    ("seguranca_saude", r"plano de seguranca e saude"),
    ("scie", r"seguranca contra incendio"),
    ("termica", r"comportamento termico|desempenho energetico"),
    ("memoria_descritiva", r"memoria descritiva"),
]

# --------------------------------------------------------------------------------------------- pisos
# Normalização: Fundações · Cave -2 · Cave -1 · R/C · Piso 1 … · Sótão · Cobertura (aceita também RDC, R+1, SS1, TERRASSE…).
_LEVEL = re.compile(
    r"(?:^|[^a-z0-9])(?:"
    r"(?P<rc>r ?[/. -]? ?c|res do chao|res-do-chao|rdc|piso 0|r0)"
    r"|(?:piso|pisos|andar|nivel|r ?\+)\s*\+?\s*(?P<up>\d{1,2})"
    r"|(?P<up2>\d{1,2}) ?\.?o? ?(?:piso|andar)"
    r"|(?:piso|nivel)\s*-\s*(?P<dn>\d)"
    r"|(?:sub ?cave|cave|ss)\s*-?\s*(?P<cv>\d)"
    r"|(?P<cave>cave|sub ?cave)"
    r"|(?P<cob>cobertura|terraco|terrasse|toiture|telhado)"
    r"|(?P<sot>sotao|aproveitamento da cobertura)"
    r"|(?P<fun>fundac\w*|fundos|fond\w*|fun|fon)"
    r")(?=$|[^a-z0-9])")


def _level_from_match(m) -> str | None:
    if m.group("rc"):
        return "R/C"
    up = m.group("up") or m.group("up2")
    if up:
        n = int(up)
        return "R/C" if n == 0 else f"Piso {n}"
    cv = m.group("dn") or m.group("cv")
    if cv:
        return f"Cave -{int(cv)}" if int(cv) > 0 else "R/C"
    if m.group("cave"):
        return "Cave -1"
    if m.group("cob"):
        return "Cobertura"
    if m.group("sot"):
        return "Sótão"
    if m.group("fun"):
        return "Fundações"
    return None


def level_of(name: str) -> str | None:
    s = re.sub(r"\.[a-z0-9]{2,4}$", "", _plain(PurePosixPath(name.replace("\\", "/")).name))
    s = re.sub(r"[_]+", " ", s)
    for m in _LEVEL.finditer(s):
        lv = _level_from_match(m)
        if lv:
            return lv
    return None


def _norm_code_level(lvl: str) -> str | None:
    lvl = (lvl or "").upper()
    if lvl in ("", "GEN"):
        return None
    if lvl in ("FON", "FND", "INF", "FUN"):
        return "Fundações"
    if lvl in ("TER", "TT", "TOI", "COB"):
        return "Cobertura"
    if lvl in ("RDC", "RC", "R0", "P0"):
        return "R/C"
    m = re.fullmatch(r"(?:R\+?|P)(\d{1,2})", lvl)
    if m:
        return "R/C" if int(m.group(1)) == 0 else f"Piso {int(m.group(1))}"
    m = re.fullmatch(r"(?:SS|S|CV|C)(\d)", lvl)
    if m:
        return f"Cave -{int(m.group(1))}"
    return lvl


# ------------------------------------------------------------------ codificação das peças desenhadas (gabinetes de projeto)
# XYZ_PE_EST_Z1_P1_ARM_0171 · XYZ_EXE_BET__Z2_SS1_COF_5102 · EXE_XYZ_BET_GEN_NDC_4000 · XYZ_EXE_BET_TZ_R1_COF_0100_-_Planta_-_A
_PHASES = "ESQ|EP|AP|PB|PE|PIP|LIC|DIAG|APS|APD|AVP|PRO|PC|DCE|ACT|EXE|VISA|DOE|TF"
_NATURES = {"COF": "cofragem", "CPE": "cofragem", "ARM": "armaduras", "FER": "armaduras", "NDC": "nota_calculo", "NDH": "nota_calculo",
            "MDC": "nota_calculo", "PLN": "arquitetura", "ARC": "arquitetura", "ARQ": "arquitetura", "CHP": "estabilidade",
            "EST": "estabilidade", "FUN": "estabilidade", "PRE": "estabilidade", "IMP": "topografia", "TOP": "topografia",
            "AAE": "aguas_esgotos", "AGU": "aguas_esgotos", "ESG": "aguas_esgotos", "PLU": "aguas_esgotos", "ELE": "eletricidade",
            "ITD": "eletricidade", "AVA": "avac", "GAS": "gas", "TRM": "termica", "ACU": "acustica", "SCI": "scie"}
_CODE = re.compile(r"(?:^|[^A-Z0-9])(?:[A-Z0-9]{2,6}_)?(?:(?P<phase>" + _PHASES + r")_)?(?:[A-Z0-9]{2,6}_)?(?:(?P<phase2>" + _PHASES + r")_)?"
                   r"(?:BET|STR|EST|ARC|ARQ|MOE|ESP)_+(?P<zone>TZ|GEN|Z\d{1,2}|ZN?\d{1,2}|BAT[A-Z0-9]?|B\d|ED\d{1,2})_+"
                   r"(?P<lvl>FON|FND|FUN|INF|SS\d|S\d|CV\d|RDC|RC|R\+?\d{1,2}|P\d{1,2}|TER|TT|TOI|COB|GEN)?_*"
                   r"(?P<nat>[A-Z]{3})[ _-]*(?P<num>\d{4})(?![0-9])", re.I)
_IND = re.compile(r"(?:[ _-]+(?:rev(?:is[aã]o)?|ind(?:ice)?)?[ _.-]*(?P<ind>[A-Z0-9]))\s*$", re.I)
_ELEMENTS = [("pilares", r"poteau|pilar"), ("paredes", r"voile|parede|muro|nucleo"), ("vigas", r"poutre|viga(?! de fundac)"),
             ("lajes", r"dalle(?!ge)|laje"), ("massame", r"dallage|massame|pavimento terreo"),
             ("lintéis de fundação", r"longrine|viga de fundac|lintel de fundac"), ("sapatas", r"semelle|sapata"),
             ("estacas", r"\bvpp\b|pieu|micropieu|estaca|microestaca"), ("escadas", r"escalier|escada"),
             ("cortes", r"coupe|corte"), ("ensoleiramento", r"radier|ensoleiramento")]


def code_key(zone: str | None, nature: str | None, num: str | None) -> str | None:
    """Chave estável de um desenho (zona + natureza + número): «R1»/«R+1» ou «COF»/«CPE» não impedem a associação."""
    if not num:
        return None
    nat = (nature or "").upper()
    nat = "COF" if nat == "CPE" else "ARM" if nat == "FER" else nat
    return f"{(zone or '').upper()}-{nat}-{num}"


def parse_code(name: str) -> dict | None:
    stem = re.sub(r"\.[a-z0-9]{2,4}$", "", PurePosixPath(name.replace("\\", "/")).name, flags=re.I)
    m = _CODE.search(stem.upper().replace("–", "-"))
    if not m:
        return None
    level = _norm_code_level(m.group("lvl") or "")
    rest = stem[m.end():]
    ind = _IND.search(rest) if rest else None
    nat = m.group("nat").upper()
    low = _plain(stem)
    element = next((e for e, rx in _ELEMENTS if re.search(rx, low)), None)
    ph = re.search(r"(?:^|_)(" + _PHASES + r")(?=_)", stem.upper()[:m.end()])
    return {"phase": ph.group(1) if ph else None, "zone": m.group("zone").upper(), "level_code": level,
            "nature": nat, "number": m.group("num"), "indice": ind.group("ind").upper() if ind else None, "element": element,
            "key": code_key(m.group("zone"), nat, m.group("num"))}


def classify(name: str, text: str = "") -> dict:
    code = parse_code(name)
    low = re.sub(r"[_\-.]+", " ", _plain(PurePosixPath(name.replace("\\", "/")).name))
    low = re.sub(r"\s(pdf|dwg|dxf|xlsx?|csv|docx|txt|png|jpe?g|webp)$", "", low)
    folder = re.sub(r"[_\-.]+", " ", _plain(str(PurePosixPath(name.replace("\\", "/")).parent)))
    disc = _NATURES.get(code["nature"]) if code else None
    if not disc and ext_of(name) in IMAGES and re.search(_w(r"fotos?|fotografias?|img|dsc|photos?|imagem"), low):
        disc = "fotografia"
    disc = disc or next((d for d, rx in _DISC if re.search(rx, low)), None)
    t = _plain((text or "")[:4000])
    if disc is None and t:
        disc = next((d for d, rx in _TEXT_HINTS if re.search(rx, t)), None)
    if disc is None and folder not in ("", "."):        # pasta «03_Especialidades/Estabilidade/…»
        disc = next((d for d, rx in _DISC if d != "arquitetura" and re.search(rx, folder)), None) \
            or ("arquitetura" if re.search(_w(r"arq\w*|arquitetura"), folder) else None)
    e = ext_of(name)
    if disc is None and re.search(r"lista\s+de\s+(desenhos|pecas desenhadas)|liste\s+des\s+plans", _plain((text or "")[:3000])):
        disc = "lista_desenhos"
    if disc is None and e in IMAGES:
        disc = "fotografia"
    level = (code or {}).get("level_code") or level_of(name)
    out = {"discipline": disc or "outro", "level": level, "format": e, "cad": e in ("dwg", "dxf")}
    if code:
        out.update(zone=code["zone"], nature=code["nature"], number=code["number"], indice=code["indice"], element=code["element"],
                   phase=code["phase"], plan_key=code["key"])
    return out


_ORDER = ["Fundações"] + [f"Cave -{i}" for i in range(5, 0, -1)] + ["R/C"] + [f"Piso {i}" for i in range(1, 40)] + ["Sótão", "Cobertura"]


def level_key(level: str | None) -> tuple:
    if not level:
        return (999, "")
    try:
        return (_ORDER.index(level), level)
    except ValueError:
        return (998, level)


def group_of(discipline: str | None) -> str:
    return next((g for g, ds in GROUPS.items() if discipline in ds), "outros")


def inventory(files: list[dict]) -> dict:
    """files: [{doc_id, filename, discipline, level, format, pages}] → síntese para o Assistente (sem o conteúdo)."""
    by, groups = {}, {}
    for f in files:
        d = f.get("discipline") or "outro"
        by.setdefault(d, []).append(f)
        groups[group_of(d)] = groups.get(group_of(d), 0) + 1
    return {"total": len(files),
            "por_especialidade": {k: {"rotulo": LABELS.get(k, k), "ficheiros": len(v),
                                      "pisos": sorted({x.get("level") for x in v if x.get("level")}, key=level_key),
                                      "formatos": sorted({x.get("format") or "" for x in v})} for k, v in sorted(by.items())},
            "por_grupo": {GROUP_LABELS.get(g, g): n for g, n in sorted(groups.items())},
            "zonas": {z: sum(1 for f in files if f.get("zone") == z) for z in sorted({f.get("zone") for f in files if f.get("zone")})},
            "plantas_cad": sum(1 for f in files if f.get("format") in ("dwg", "dxf")),
            "pdf": sum(1 for f in files if f.get("format") == "pdf")}


def missing_pieces(files: list[dict]) -> list[str]:
    """Peças habituais de um processo de obra em Portugal ausentes do inventário (indicativo: depende do tipo de obra)."""
    have = {f.get("discipline") for f in files}
    expected = [("arquitetura", "projeto de arquitetura"), ("estabilidade", "projeto de estabilidade"),
                ("aguas_esgotos", "projeto de águas, esgotos e pluviais"), ("eletricidade", "projeto de instalações elétricas / ITED"),
                ("termica", "projeto de comportamento térmico (REH/SCE)"), ("geotecnia", "estudo geotécnico"),
                ("caderno_encargos", "caderno de encargos"), ("mapa_quantidades", "mapa de quantidades")]
    struct = {"estabilidade", "cofragem", "armaduras", "nota_calculo"}
    return [label for d, label in expected if d not in have and not (d == "estabilidade" and have & struct)]


# ------------------------------------------------------------------ lista de desenhos
_DATE = re.compile(r"(\d{2})[/.-](\d{2})[/.-](\d{4})")
_IND_CELL = re.compile(r"^[A-Z0-9]$|^0(?:\.0)?$", re.I)
_FNAME_DATE = re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)")


def _excel_date(v) -> str | None:
    if isinstance(v, (int, float)) and not isinstance(v, bool) and 20000 < float(v) < 80000:
        import datetime as _dt
        return (_dt.date(1899, 12, 30) + _dt.timedelta(days=int(v))).isoformat()
    m = _DATE.search(str(v or ""))
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def _ind(v) -> str | None:
    t = str(v).strip().upper()
    if t in ("0", "0.0"):
        return "0"
    return t if _IND_CELL.match(t) else None


def register_from_rows(rows: list[list], source: str = "") -> list[dict]:
    """Linhas de uma lista de desenhos XLS/XLSX (uma linha = um desenho) → [{key, code, zone, level, nature, element, description, indice, date}]."""
    out = []
    for row in rows:
        cells = [c for c in row if str(c).strip() not in ("", "None")]
        for i, c in enumerate(cells):
            code = parse_code(str(c).strip() + ".x")
            if not code:
                continue
            after = cells[i + 1:]
            desc = next((str(x).strip() for x in after if len(str(x).strip()) > 3 and not _excel_date(x)), "")
            ind = next((_ind(x) for x in after if _ind(x)), None)
            date = next((_excel_date(x) for x in after if _excel_date(x)), None)
            low = _plain(desc)
            out.append({"key": code["key"], "code": str(c).strip(), "zone": code["zone"], "level": code["level_code"], "nature": code["nature"],
                        "element": next((e for e, rx in _ELEMENTS if re.search(rx, low)), code["element"]), "description": desc[:160],
                        "indice": ind, "date": date, "source": source})
            break
    return out


_REG_TITLE = r"lista\s+de\s+desenhos|lista\s+de\s+pe[cç]as\s+desenhadas|[ií]ndice\s+de\s+desenhos|liste\s+des\s+plans|bordereau"


def register_from_text(text: str, source: str = "") -> list[dict]:
    """Lista de desenhos em PDF: o texto é cortado nos códigos dos desenhos."""
    if not re.search(_REG_TITLE, text or "", re.I):
        return []
    flat = " ".join((text or "").split())
    hits = list(re.finditer(r"[A-Z0-9]+(?:_+[A-Z0-9+]+){3,}[ _]*\d{4}", flat))
    rows = []
    for k, m in enumerate(hits):
        seg = flat[m.end(): hits[k + 1].start() if k + 1 < len(hits) else len(flat)]
        seg = re.split(r"\b(?:COF|CPE|ARM|NDC|EST|ARQ|Cofragem|Armaduras|Coffrage)\s+\d{4}\b|LISTA DE DESENHOS|LISTE DES PLANS", seg)[0]
        dm = _DATE.search(seg)
        head = seg[:dm.start()] if dm else seg
        im = re.search(r"(?i:(?<!piso)(?<!cave)(?<!andar)(?<!nivel)(?<!n\.º))\s([A-Z0-9])\s*$", head)   # «Piso 2» não é a revisão 2
        desc = head[:im.start()] if im else head
        rows.append([m.group(0), desc.strip(), im.group(1) if im else "", dm.group(0) if dm else ""])
    return register_from_rows(rows, source)


def _ind_rank(ind: str | None) -> int:
    if not ind:
        return -1
    return 0 if ind == "0" else (ord(ind) - 64) if ind.isalpha() else int(ind)


def _source_date(src: str) -> str:
    m = _FNAME_DATE.search(src or "")
    return f"20{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def merge_registers(regs: list[list[dict]]) -> list[dict]:
    """Várias listas sucessivas: para cada desenho prevalece a revisão mais alta (e depois a data mais recente)."""
    best = {}
    for reg in regs:
        for r in reg:
            cur = best.get(r["key"])
            score = (_ind_rank(r.get("indice")), r.get("date") or "", _source_date(r.get("source")))
            if cur is None or score > cur[0]:
                best[r["key"]] = (score, r)
    return sorted((v[1] for v in best.values()), key=lambda r: (r["zone"], level_key(r.get("level")), r["nature"], r["key"]))


def check_register(files: list[dict], register: list[dict]) -> dict:
    """Controlo do processo face à lista de desenhos: em falta, revisões desatualizadas, várias revisões, fora da lista."""
    plans = [f for f in files if f.get("plan_key") and f.get("format") in ("dwg", "dxf", "pdf")]
    by_key = {}
    for f in plans:
        by_key.setdefault(f["plan_key"], []).append(f)
    missing, outdated, ok, doubles = [], [], [], []
    for r in register:
        have = by_key.get(r["key"], [])
        if not have:
            if r.get("indice") or r.get("date"):              # desenho sem revisão nem data: ainda não emitido
                missing.append({"code": r["code"], "description": r["description"], "revisao": r.get("indice"), "zona": r["zone"], "piso": r.get("level")})
            continue
        top = max(have, key=lambda f: _ind_rank(f.get("indice")))
        if len({f.get("indice") for f in have}) > 1:
            doubles.append({"code": r["code"], "revisoes": sorted({f.get("indice") or "?" for f in have}), "considerado": top.get("filename")})
        if r.get("indice") and top.get("indice") and _ind_rank(top["indice"]) < _ind_rank(r["indice"]):
            outdated.append({"code": r["code"], "ficheiro": top.get("filename"), "revisao_ficheiro": top["indice"], "revisao_lista": r["indice"]})
        else:
            ok.append(r["code"])
    keys = {r["key"] for r in register}
    extra = [f.get("filename") for f in plans if f["plan_key"] not in keys]
    return {"desenhos_na_lista": len(register), "presentes": len(ok), "em_falta": missing[:200], "revisoes_desatualizadas": outdated[:200],
            "varias_revisoes": doubles[:100], "fora_da_lista": extra[:100],
            "zonas": sorted({r["zone"] for r in register}), "pisos": sorted({r.get("level") for r in register if r.get("level")}, key=level_key)}


def latest_per_plan(files: list[dict]) -> list[dict]:
    """Mantém, para cada desenho codificado, o ficheiro com a revisão mais alta (e sempre os ficheiros não codificados)."""
    best, rest = {}, []
    for f in files:
        k = f.get("plan_key")
        if not k:
            rest.append(f)
            continue
        if k not in best or _ind_rank(f.get("indice")) > _ind_rank(best[k].get("indice")):
            best[k] = f
    return rest + list(best.values())
