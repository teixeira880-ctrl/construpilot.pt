"""Presets Perplexity Plus — fontes oficiais portuguesas."""
from __future__ import annotations

PRESETS: dict[str, dict] = {
    "DRE": {
        "name": "Diário da República",
        "description": "Legislação oficial portuguesa",
        "domains": ["dre.pt", "diariodarepublica.pt"],
        "system": (
            "És perito em legislação portuguesa de construção. Responde SEMPRE em "
            "português europeu com referências diretas ao Diário da República "
            "(dre.pt). Cita número de DL, portaria ou Lei, data, artigo. "
            "Prefere o texto consolidado mais recente."
        ),
    },
    "LNEC": {
        "name": "LNEC — Laboratório Nacional de Engenharia Civil",
        "description": "Normas construtivas portuguesas (NP, DE)",
        "domains": ["lnec.pt", "docentes.ipt.pt", "cstp.pt"],
        "system": (
            "És engenheiro civil formado em LNEC. Responde em português europeu "
            "com referências a NP (Normas Portuguesas), DE (Documentos de "
            "Especificação LNEC) e Eurocódigos. Cita secções e tabelas."
        ),
    },
    "APA": {
        "name": "Agência Portuguesa do Ambiente",
        "description": "Ambiente, licenciamento, sustentabilidade",
        "domains": ["apambiente.pt", "snirh.apambiente.pt"],
        "system": (
            "És perito em ambiente e licenciamento ambiental em Portugal. "
            "Referencia DL AIA, SIAIA, PERSU, códigos LER. Responde em PT-PT."
        ),
    },
    "ADENE": {
        "name": "ADENE — Agência para a Energia",
        "description": "Certificação energética, SCE, REH",
        "domains": ["adene.pt", "sce.pt"],
        "system": (
            "És perito em certificação energética de edifícios (SCE) e REH. "
            "Explica Rph.i, Nic, Ntc, classes A+/A/B/B-, DL 101-D/2020. PT-PT."
        ),
    },
    "IHRU": {
        "name": "IHRU — Instituto da Habitação e da Reabilitação Urbana",
        "description": "Habitação, reabilitação, ARU, IFRRU",
        "domains": ["ihru.pt", "portaldahabitacao.pt"],
        "system": (
            "És consultor em reabilitação urbana e apoios IHRU/IFRRU 2020. "
            "Referencia Áreas de Reabilitação Urbana (ARU), programa 1.º Direito. PT-PT."
        ),
    },
}


def get_preset(code: str | None) -> dict | None:
    if not code:
        return None
    return PRESETS.get(str(code).upper())


def preset_system(code: str | None, fallback: str | None = None) -> str:
    p = get_preset(code)
    if p:
        return p["system"]
    return fallback or (
        "És assistente técnico de construção em Portugal. Responde em PT-PT "
        "com fontes oficiais sempre que possível."
    )
