"""O que depende do país do site (core/market.py) no Estúdio de Projeto — único ponto de acoplamento ao país.

O coração do Estúdio (modelo, derivar, desenhos, cobertura, escadas, materiais, objetos, operações, exportar, ifc) é igual
em construpilot.pt e construpilot.fr. Aqui ficam só as diferenças:

- paredes de partida do país (`tipos_base`) e paredes-tipo / materiais acrescentados à biblioteca (`_completar_biblioteca`);
- módulo de desenho do licenciamento do país (tipos de letra e cabeçalho das peças PNG);
- tipos de letra e data dos PDF, e os rótulos do carimbo das pranchas.

Os nomes ficam em português (chaves estáveis); em França são traduzidos à saída por `i18n.py`.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

try:
    from core.market import SITE_COUNTRY as _PAIS
except Exception:  # noqa: BLE001 — fora do backend (ferramentas, testes isolados): comportamento de origem
    _PAIS = "PT"
PAIS = (_PAIS or "PT").upper()

# ---------------------------------------------------------------- paredes de partida, por país
# França: mesmas espessuras das peças do permis de construire (engines/urbanism/pc_plans.py: E_EXT = 0,30 m, E_INT = 0,10 m),
# para o Estúdio abrir com as medidas do carnet PC. São hipóteses editáveis, não leituras.
TIPOS_FR: Dict[str, Dict[str, Any]] = {
    "ext_30": {"nome": "Parede exterior 30 cm (bloco de betão 20 + isolamento interior colado)", "exterior": True, "camadas": [
        {"material": "Placa de gesso com isolamento colado (EPS)", "esp_m": 0.09},
        {"material": "Bloco de betão normal", "esp_m": 0.20},
        {"material": "Reboco monomassa", "esp_m": 0.01}]},
    "int_12": {"nome": "Parede interior 10 cm (blocos de gesso maciço)", "exterior": False, "camadas": [
        {"material": "Bloco de gesso maciço", "esp_m": 0.10}]},
    "int_20": {"nome": "Parede interior resistente 20 cm (betão armado)", "exterior": False, "camadas": [
        {"material": "Betão armado", "esp_m": 0.20}]},
}

# materiais acrescentados à biblioteca em França: (categoria, nome, espessuras em cm, cor)
MATERIAIS_FR: List[Tuple[str, str, List[float], str]] = [
    ("Gesso e placas", "Bloco de gesso maciço", [5, 6, 7, 8, 10], "#f1efe8"),
    ("Gesso e placas", "Bloco de gesso hidrófugo", [5, 7, 10], "#dfeaf0"),
]

# paredes-tipo correntes em França (camadas do interior para o exterior, espessuras em cm)
PAREDES_TIPO_FR: List[Tuple[str, str, bool, List[Tuple[str, float]]]] = [
    ("fr_ext_bloco_iti_120", "Exterior — bloco de betão 20 + isolamento interior colado 13+120", True,
     [("Placa de gesso com isolamento colado (EPS)", 13.3), ("Bloco de betão normal", 20), ("Reboco monomassa", 1.5)]),
    ("fr_ext_bloco_iti_la", "Exterior — bloco de betão 20 + lã de vidro 12 em estrutura + gesso cartonado", True,
     [("Placa de gesso cartonado standard", 1.25), ("Lã de vidro em painel", 12), ("Bloco de betão normal", 20), ("Reboco monomassa", 1.5)]),
    ("fr_ext_tijolo_iti_120", "Exterior — tijolo 20 + isolamento interior colado 13+120", True,
     [("Placa de gesso com isolamento colado (EPS)", 13.3), ("Tijolo cerâmico furado 30×20×20", 20), ("Reboco monomassa", 1.5)]),
    ("fr_ext_monomur_375", "Exterior — bloco térmico 37,5 rebocado nas duas faces", True,
     [("Reboco projetado de gesso", 1.5), ("Bloco cerâmico térmico de encaixe", 37.5), ("Reboco monomassa", 1.5)]),
    ("fr_ext_bloco_ite_14", "Exterior — bloco de betão 20 + ETICS EPS cinza 14 cm", True,
     [("Reboco projetado de gesso", 1.5), ("Bloco de betão normal", 20), ("Poliestireno expandido grafitado (EPS cinza)", 14),
      ("Camada de base armada (ETICS)", 0.4), ("Acabamento acrílico (ETICS)", 0.2)]),
    ("fr_ext_betao_iti_120", "Exterior — betão armado 18 + isolamento interior colado 13+120", True,
     [("Placa de gesso com isolamento colado (EPS)", 13.3), ("Betão armado", 18)]),
    ("fr_int_gesso_7", "Interior — blocos de gesso maciço 7", False, [("Bloco de gesso maciço", 7)]),
    ("fr_int_gesso_hidro_7", "Interior — blocos de gesso hidrófugo 7 (zonas húmidas)", False, [("Bloco de gesso hidrófugo", 7)]),
    ("fr_int_bloco_20", "Interior — bloco de betão 20 rebocado a gesso nas duas faces", False,
     [("Reboco projetado de gesso", 1.5), ("Bloco de betão normal", 20), ("Reboco projetado de gesso", 1.5)]),
]


def tipos_base(tipos_pt: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Paredes de partida do país do site (as de Portugal são as do próprio `modelo.py`)."""
    return TIPOS_FR if PAIS == "FR" else tipos_pt


def _completar_biblioteca() -> None:
    """Em França, junta à biblioteca os materiais e as paredes-tipo correntes no país (à frente das restantes)."""
    if PAIS != "FR":
        return
    from engines.estudio_projeto import materiais as MAT
    if "fr_ext_bloco_iti_120" in MAT.PAREDES_TIPO:
        return
    for cat, nome, esp, cor in MATERIAIS_FR:
        if nome not in MAT._POR_NOME:
            item = {"id": MAT._slug(nome), "nome": nome, "categoria": cat, "espessuras_cm": esp, "cor": cor}
            MAT.BIBLIOTECA.append(item)
            MAT._POR_NOME[nome] = item
    novas = {tid: MAT._p(nome, ext, *cam) for tid, nome, ext, cam in PAREDES_TIPO_FR}
    antigas = dict(MAT.PAREDES_TIPO)
    MAT.PAREDES_TIPO.clear()
    MAT.PAREDES_TIPO.update({**novas, **antigas})


_completar_biblioteca()


# ---------------------------------------------------------------- desenho e PDF
def volumes():
    """Módulo de desenho do licenciamento do país: dá `_font(tamanho)` e `_header(draw, largura, título)` às peças PNG."""
    if PAIS == "FR":
        from engines.urbanism import volumes as V
    else:
        from engines.urbanismo_pt import volumes as V
    return V


_FONTES = {"regular": "Helvetica", "bold": "Helvetica-Bold"}
_TTF = (("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf", "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"))


def fontes_pdf() -> Dict[str, str]:
    """Tipos de letra dos PDF: os do licenciamento em Portugal; em França, DejaVu / Liberation do sistema (senão Helvetica)."""
    if PAIS != "FR":
        from engines.urbanismo_pt import pdf as UP
        return UP._fonts()
    if _FONTES["regular"] != "Helvetica":
        return _FONTES
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        for reg, neg in _TTF:
            if os.path.exists(reg) and os.path.exists(neg):
                if "EstudioSans" not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont("EstudioSans", reg))
                    pdfmetrics.registerFont(TTFont("EstudioSans-Bold", neg))
                _FONTES.update(regular="EstudioSans", bold="EstudioSans-Bold")
                break
    except Exception:  # noqa: BLE001 — sem TTF: Helvetica
        pass
    return _FONTES


def hoje() -> str:
    return datetime.now(timezone.utc).strftime("%d/%m/%Y")


def carimbo(processo: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Linhas (rótulo, valor) do carimbo das pranchas, sem a peça, a escala e a data (acrescentadas por `exportar`).
    Portugal: processo de licenciamento (requerente, morada, concelho). França: dossier d'urbanisme (maître d'ouvrage,
    adresse, commune, référence cadastrale)."""
    d = processo or {}
    if PAIS == "FR":
        app, ter = d.get("applicant") or {}, d.get("terrain") or {}
        cad = ter.get("cadastre") or {}
        moa = " ".join(str(x) for x in (app.get("prenom"), app.get("nom")) if x).strip()
        local = ", ".join(str(x) for x in (ter.get("voie"), " ".join(str(y) for y in (ter.get("code_postal"), ter.get("commune")) if y)) if x)
        ref = cad.get("reference") or " ".join(str(x) for x in (cad.get("section"), cad.get("numero")) if x)
        return [("Processo", d.get("title") or "—"), ("Requerente", moa or "—"), ("Local da obra", local or "—"), ("Parcela cadastral", ref or "—")]
    ter, req = d.get("terreno") or {}, d.get("requerente") or {}
    return [("Processo", d.get("title") or "—"), ("Requerente", req.get("nome") or "—"),
            ("Local", ", ".join(x for x in (ter.get("morada"), ter.get("concelho")) if x) or "—")]


def autor() -> Tuple[str, str]:
    """Linha de assinatura do carimbo."""
    if PAIS == "FR":
        return "Autor do projeto", "______________________  (arquiteto: n.º de inscrição na Ordem)"
    return "Técnico autor", "______________________  (n.º de inscrição na Ordem)"
