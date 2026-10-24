"""Processo de exemplo FICTÍCIO (moradia T3) — dados inventados para demonstração, sem valor de nenhum município real.

Os parâmetros «PDM» do exemplo são ilustrativos e estão marcados como tal; num processo real são
sempre introduzidos pelo utilizador a partir do regulamento do plano municipal aplicável.
"""
from __future__ import annotations

import copy

EXEMPLO = {
    "title": "Moradia T3 — Lote 7 (exemplo fictício)",
    "tipo_obra": "moradia_nova",
    "requerente": {"nome": "Ana Exemplo (fictícia)", "nif": "", "morada": "Rua do Exemplo, 1", "telefone": "", "email": ""},
    "terreno": {"morada": "Rua das Oliveiras, Lote 7 (fictícia)", "codigo_postal": "0000-000", "concelho": "Concelho Exemplo",
                "freguesia": "Freguesia Exemplo", "artigo_matricial": "U-0000 (fictício)", "descricao_predial": "0000/00000000",
                "area_terreno_m2": 450},
    "enquadramento": {"zona_protegida": False, "imovel_classificado": False, "confina_via_publica": True,
                      "tem_edificacao_principal": False, "tem_pdm_com_parametros": False, "tem_loteamento_pip": False,
                      "zona_urbana_consolidada": False},
    "pdm": {"plano": "PDM fictício do Concelho Exemplo (valores ilustrativos)", "classe_espaco": "Espaço habitacional (exemplo)",
            "fonte_artigos": "Valores de demonstração — substituir pelos do regulamento aplicável",
            "iu_max": 0.6, "io_max_pct": 35, "altura_fachada_max_m": 6.5, "n_pisos_max": 2,
            "afastamento_frontal_min_m": 5, "afastamento_lateral_min_m": 3, "afastamento_tardoz_min_m": 6,
            "lugares_por_fogo": 2},
    "volume": {"shape": "L", "plot_l_m": 18, "plot_w_m": 25, "footprint_l_m": 12, "footprint_w_m": 10,
               "wing_l_m": 5, "wing_w_m": 4, "levels": 2, "storey_h_m": 2.9, "espessura_laje_m": 0.3, "total_h_m": 0,
               "roof_type": "duas_aguas", "setback_front_m": 5, "setback_side_m": 3,
               "blocks": [{"name": "Telheiro", "l_m": 3.5, "w_m": 5, "x_m": 1.0, "y_m": 17, "h_m": 2.4}],
               "uso": "habitacao", "n_fogos": 1, "lugares_previstos": 2},
    "parametros": {},
}


def processo_exemplo() -> dict:
    return copy.deepcopy(EXEMPLO)
