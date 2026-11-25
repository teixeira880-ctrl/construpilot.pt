"""Programa por divisão → artigos « equipamento por divisão » dos capítulos de Eletricidade e Águas e esgotos.

Cada divisão do programa passa a ser um artigo com a lista dos seus equipamentos, e cada equipamento uma linha
quantificada do mapa de quantidades. As quantidades são calculadas por regra determinística (nunca pela IA).

Eletricidade — ATENÇÃO, diferença em relação à França : as RTIEBT (Portaria n.º 949-A/2006) NÃO fixam um número
mínimo de tomadas nem de pontos de luz por divisão. Por isso :
- o que é regulamentar é apresentado como tal :
    ITED (Manual ITED, 4.ª edição, 4.2.2) : uma tomada mista (pares de cobre + coaxial) nas salas, quartos e cozinha,
    exceto na divisão onde fica a ZAP ; ZAP obrigatória com 2 tomadas de pares de cobre, 2 coaxiais e 2 de fibra ótica ;
    RTIEBT : tomadas das casas de banho fora dos volumes 0 a 2 e protegidas por diferencial de 30 mA ; tomadas
    exteriores protegidas por diferencial de 30 mA ; máximo de 8 pontos de utilização por circuito final ;
- o resto (número de tomadas e pontos de luz) é uma BASE DE EQUIPAMENTO PROPOSTA pela ConstruPilot (conforto usual),
  identificada como tal no caderno, a confirmar pelo projeto de instalações elétricas.
Águas e esgotos : aparelhos e preparações usuais por tipo de divisão (casa de banho portuguesa com sanita).
"""
from __future__ import annotations

import unicodedata

TYPES = {
    "sejour": "Sala", "cuisine": "Cozinha", "chambre": "Quarto", "bureau": "Escritório", "sdb": "Casa de banho",
    "wc": "Instalação sanitária de serviço", "entree": "Hall de entrada", "circulation": "Corredor / circulação",
    "buanderie": "Lavandaria / despensa", "garage": "Garagem", "exterieur": "Exterior", "autre": "Outra divisão",
}


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def type_piece(p: dict) -> str:
    t = p.get("type")
    if t in TYPES:
        return t
    n = _fold(p.get("nom", ""))
    for key, mots in (("sdb", ("casa de banho", "wc completo", "i.s.", "instalacao sanitaria completa", "suite wc")),
                      ("wc", ("wc", "lavabo", "instalacao sanitaria", "sanitario")),
                      ("cuisine", ("cozinha", "kitchenette")),
                      ("sejour", ("sala", "estar", "living", "jantar")),
                      ("chambre", ("quarto", "suite")), ("bureau", ("escritorio", "biblioteca")),
                      ("entree", ("hall", "entrada", "vestibulo")),
                      ("circulation", ("corredor", "circulacao", "patamar", "escada", "galeria")),
                      ("buanderie", ("lavandaria", "despensa", "arrumos", "estendal")), ("garage", ("garagem",)),
                      ("exterieur", ("terraco", "jardim", "exterior", "varanda", "alpendre", "logradouro"))):
        if any(m in n for m in mots):
            return key
    return "autre"


def _surface(p: dict) -> float | None:
    try:
        s = float(str(p.get("surface")).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return s if s > 0 else None


def _titre(p: dict) -> str:
    nom = (p.get("nom") or TYPES[type_piece(p)]).strip()
    niv = (p.get("niveau") or "").strip()
    return (f"{nom} ({niv})" if niv else nom).upper()[:120]


def zap_index(pieces: list[dict]) -> int | None:
    """Divisão que aloja a ZAP : a indicada (zap=True) ou, por defeito, a primeira sala."""
    for i, p in enumerate(pieces or []):
        if p.get("zap"):
            return i
    for i, p in enumerate(pieces or []):
        if type_piece(p) == "sejour":
            return i
    return None


def equipements_electricite(p: dict, zap: bool = False) -> list[tuple[int, str]]:
    t, s = type_piece(p), _surface(p)
    pl = (1, "Ponto de luz no teto com caixa de derivação, comandado à entrada da divisão")
    ited = ([(1, "ZAP — Zona de Acesso Privilegiado : 2 tomadas de pares de cobre, 2 coaxiais e 2 de fibra ótica (ITED)")]
            if zap else [(1, "Tomada mista de telecomunicações (pares de cobre + coaxial) (ITED)")])
    if t == "sejour":
        return [pl, (5 if (s or 0) < 28 else 7, "Tomada 16 A com terra"),
                (2, "Tomada 16 A com terra junto às tomadas de telecomunicações")] + ited
    if t == "cuisine":
        lst = [pl]
        if s is not None and s <= 4:
            lst.append((3, "Tomada 16 A com terra sobre a bancada"))
        else:
            lst += [(4, "Tomada 16 A com terra sobre a bancada"), (2, "Tomada 16 A com terra")]
        return lst + [(1, "Saída de cabo em circuito dedicado para placa / fogão"), (1, "Tomada 16 A com terra em circuito dedicado para forno"),
                      (1, "Tomada 16 A com terra em circuito dedicado para máquina de lavar loiça"),
                      (1, "Tomada 16 A com terra para exaustor")] + ited
    if t in ("chambre", "bureau"):
        return [pl, (3, "Tomada 16 A com terra")] + ited
    if t == "sdb":
        return [pl, (1, "Tomada 16 A com terra fora dos volumes 0 a 2, protegida por diferencial de 30 mA (RTIEBT)"),
                (1, "Ligação equipotencial suplementar (RTIEBT)")]
    if t == "wc":
        return [pl]
    if t == "buanderie":
        return [pl, (1, "Tomada 16 A com terra"), (1, "Tomada 16 A com terra em circuito dedicado para máquina de lavar roupa")]
    if t == "garage":
        return [pl, (1, "Tomada 16 A com terra")]
    if t == "exterieur":
        return [(1, "Ponto de luz exterior estanque, comandado do interior"),
                (1, "Tomada exterior estanque protegida por diferencial de 30 mA (RTIEBT)")]
    lst = [pl]                                                   # hall, corredor, outra
    if s is None or s > 4:
        lst.append((1, "Tomada 16 A com terra"))
    return lst


def equipements_plomberie(p: dict) -> list[tuple[int, str]]:
    t = type_piece(p)
    if t == "sdb":
        return [(1, "Lavatório ou móvel com lavatório, misturadora, sifão e válvula — abastecimento AF/AQ e esgoto"),
                (1, "Sanita suspensa com autoclismo embutido de dupla descarga, ou de pousar — abastecimento AF e esgoto Ø 90/110"),
                (1, "Base de duche extraplana ou duche de pavimento com misturadora termostática — abastecimento AF/AQ e esgoto")]
    if t == "wc":
        return [(1, "Sanita com autoclismo de dupla descarga — abastecimento AF e esgoto Ø 90/110"),
                (1, "Lavatório de pequenas dimensões com torneira — abastecimento AF/AQ e esgoto")]
    if t == "cuisine":
        return [(1, "Preparação para lava-loiça : abastecimento AF/AQ com torneiras de segurança, esgoto sifonado"),
                (1, "Preparação para máquina de lavar loiça : abastecimento AF com torneira de segurança, esgoto sifonado")]
    if t == "buanderie":
        return [(1, "Preparação para máquina de lavar roupa : abastecimento AF com torneira de segurança, esgoto sifonado"),
                (1, "Tanque de lavar com torneira — abastecimento AF/AQ e esgoto")]
    if t == "exterieur":
        return [(1, "Torneira de rega exterior com válvula de seccionamento")]
    return []


def articles_par_piece(code_lot: str, pieces: list[dict]) -> list[dict]:
    """Artigos « por divisão » para 'electricite' ou 'plomberie' (lista vazia para os restantes capítulos)."""
    if code_lot not in ("electricite", "plomberie"):
        return []
    zi = zap_index(pieces)
    out = []
    for i, p in enumerate(pieces or []):
        eq = equipements_electricite(p, zap=(i == zi)) if code_lot == "electricite" else equipements_plomberie(p)
        extras = [str(x).strip()[:200] for x in (p.get("extras") or []) if str(x).strip()] if code_lot == "electricite" else []
        if not eq and not extras:
            continue
        lignes = [f"{q} {lib}" for q, lib in eq] + extras
        intro = ("Fornecimento, montagem e ligação dos equipamentos abaixo. Os elementos assinalados (ITED, RTIEBT) são "
                 "regulamentares ; o número de tomadas e pontos de luz é uma base de equipamento proposta, a confirmar pelo "
                 "projeto de instalações elétricas :"
                 if code_lot == "electricite" else
                 "Fornecimento, montagem e ligação dos aparelhos e preparações abaixo ; modelos a aprovar pelo dono de obra e "
                 "pelo arquiteto antes da encomenda :")
        out.append({"chapitre": "Equipamento por divisão", "titre": _titre(p),
                    "description": intro + "\n" + "\n".join(f"- {l}" for l in lignes),
                    "localisation": "Conforme peças desenhadas do arquiteto.", "code": None, "source": "pieces",
                    "variantes": [{"libelle": lib, "unite": "un", "quantite": float(q)} for q, lib in eq]
                    + [{"libelle": x, "unite": "un", "quantite": None} for x in extras]})
    if code_lot == "electricite" and out:
        types = {type_piece(p) for p in pieces}
        comuns = [(1, "Quadro de entrada com interruptores diferenciais e disjuntores, máximo de 8 pontos de utilização por circuito final, reserva mínima de 20 %"),
                  (1, "ATI — Armário de Telecomunicações Individual (ITED)"),
                  (1, "Circuito de alimentação da produção de água quente sanitária"),
                  (1, "Circuito de alimentação da ventilação mecânica")]
        if "buanderie" not in types:
            comuns.append((1, "Tomada 16 A com terra em circuito dedicado para máquina de lavar roupa (localização conforme peças desenhadas)"))
        if zi is None:
            comuns.append((1, "ZAP — Zona de Acesso Privilegiado : 2 tomadas de pares de cobre, 2 coaxiais e 2 de fibra ótica (ITED)"))
        out.append({"chapitre": "Equipamento por divisão", "titre": "EQUIPAMENTOS COMUNS DA HABITAÇÃO",
                    "description": "Fornecimento, montagem e ligação :\n" + "\n".join(f"- {q} {l}" for q, l in comuns),
                    "localisation": "Conforme peças desenhadas do arquiteto.", "code": None, "source": "pieces",
                    "variantes": [{"libelle": l, "unite": "un", "quantite": float(q)} for q, l in comuns]})
    return out
