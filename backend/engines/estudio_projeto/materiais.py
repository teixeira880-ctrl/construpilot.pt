"""Biblioteca de materiais do Estúdio de Projeto.

Três usos: (1) camadas das paredes (biblioteca geral, por categoria, com as espessuras comerciais correntes em cm);
(2) acabamentos escolhidos por lista — fachada, cobertura, caixilharia, pavimento, paredes interiores e tetos — cada um
com a cor usada no 3D e nos alçados; (3) paredes-tipo prontas a usar, compostas com materiais da biblioteca.

Só nomes, categorias, espessuras de catálogo e cores de representação. Não há aqui valores térmicos, acústicos nem
preços: esses dependem do fabricante e não são inventados.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Tuple


def _slug(txt: str) -> str:
    s = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")[:40]


# ---------------------------------------------------------------- biblioteca geral (camadas)
# categoria → [(nome, [espessuras em cm], cor)]
_BIB: List[Tuple[str, List[Tuple[str, List[float], str]]]] = [
    ("Alvenaria cerâmica", [
        ("Tijolo cerâmico furado 30×20×7", [7], "#c9785a"), ("Tijolo cerâmico furado 30×20×9", [9], "#c9785a"),
        ("Tijolo cerâmico furado 30×20×11", [11], "#c9785a"), ("Tijolo cerâmico furado 30×20×15", [15], "#c9785a"),
        ("Tijolo cerâmico furado 30×20×20", [20], "#c9785a"), ("Tijolo cerâmico furado 30×20×22", [22], "#c9785a"),
        ("Tijolo cerâmico maciço", [7, 11, 22], "#b5593f"), ("Tijolo cerâmico face à vista", [11], "#b9583c"),
        ("Tijolo de burro (maciço tradicional)", [11, 22], "#a8553d"),
        ("Bloco cerâmico térmico de encaixe", [14, 19, 24, 29], "#cf8563"),
        ("Bloco cerâmico acústico", [11, 15, 20], "#c47a5c"), ("Tijolo refratário", [3, 6, 11], "#d8b98a"),
        ("Tijolo de vidro", [8, 10], "#bfe0e6"), ("Abobadilha cerâmica (aligeiramento de laje)", [12, 16, 20, 25], "#c9785a"),
        ("Tijoleira cerâmica de forro", [3, 4], "#c9785a"),
    ]),
    ("Blocos e terra", [
        ("Bloco de betão normal", [10, 15, 20, 25, 30], "#a9a9a4"), ("Bloco de betão face à vista (split)", [10, 15, 20], "#9c9c96"),
        ("Bloco de betão de argila expandida", [10, 15, 20, 25, 30], "#b4ada2"),
        ("Bloco térmico de argila expandida com isolamento", [25, 30, 35], "#b9b1a5"),
        ("Bloco de betão celular autoclavado", [7.5, 10, 12.5, 15, 20, 25, 30, 36.5], "#e4e3dd"),
        ("Bloco de cofragem perdida em betão", [20, 25, 30], "#a2a29c"),
        ("Bloco de cofragem isolante (ICF)", [25, 30, 35], "#e9ece8"), ("Bloco sílico-calcário", [11.5, 17.5, 24], "#dedbd0"),
        ("Bloco de terra comprimida (BTC)", [14, 29], "#b98a5e"), ("Adobe", [20, 30, 40], "#b48a5a"),
        ("Taipa", [40, 50, 60], "#b58c60"), ("Fardos de palha", [36, 46], "#d9c27a"),
        ("Betão de cânhamo", [20, 30, 40], "#cfc7a8"),
    ]),
    ("Pedra natural", [
        ("Alvenaria de granito", [20, 30, 40, 50, 60], "#a9a59b"), ("Cantaria de granito", [10, 15, 20], "#b3afa5"),
        ("Alvenaria de xisto", [30, 40, 50], "#6a645e"), ("Alvenaria de calcário", [30, 40, 50], "#d8d0bd"),
        ("Alvenaria de basalto", [30, 40, 50], "#4b4b4d"), ("Alvenaria de arenito", [30, 40], "#c9ad84"),
        ("Pedra seca (muro)", [40, 50, 60], "#9d978c"), ("Gabiões", [50, 100], "#8f8a80"),
        ("Placagem de granito", [2, 3, 4], "#b3afa5"), ("Placagem de calcário (moleanos / lioz)", [2, 3], "#e2dccb"),
        ("Placagem de mármore", [2, 3], "#eceae4"), ("Placagem de ardósia", [1, 2], "#4e5357"),
        ("Placagem de xisto", [2, 3], "#6a645e"), ("Placagem de basalto", [2, 3], "#4b4b4d"),
        ("Placagem de travertino", [2, 3], "#dccfb6"),
    ]),
    ("Betão e lajes", [
        ("Betão armado", [12, 15, 18, 20, 25, 30, 35, 40], "#a6a6a1"), ("Betão armado aparente (à vista)", [15, 20, 25, 30], "#b0b0ab"),
        ("Betão branco aparente", [15, 20, 25], "#e6e4de"), ("Betão ciclópico", [30, 40, 50], "#9d9d98"),
        ("Betão de limpeza", [5, 10], "#b5b5b0"), ("Betão leve de argila expandida", [5, 8, 10, 15], "#b9b2a6"),
        ("Betão celular de enchimento", [5, 8, 10], "#d9d8d2"), ("Painel pré-fabricado de betão", [12, 15, 20], "#adada8"),
        ("Painel de betão reforçado com fibra de vidro (GRC)", [1.2, 1.5, 2], "#c9c8c2"),
        ("Laje maciça de betão armado", [15, 18, 20, 22, 25, 30], "#a6a6a1"),
        ("Laje aligeirada de vigotas e abobadilhas", [16, 20, 25, 30, 35], "#b0a59b"),
        ("Laje alveolar pré-esforçada", [15, 20, 26.5, 32, 40], "#a9a9a4"),
        ("Laje fungiforme aligeirada", [25, 30, 35, 40], "#a8a8a3"),
        ("Laje mista colaborante (chapa perfilada e betão)", [10, 12, 14, 16], "#9fa3a6"),
        ("Pré-laje de betão", [5, 6, 7], "#a9a9a4"), ("Massame de betão armado", [10, 12, 15, 20], "#aeaea9"),
        ("Enrocamento / brita de base", [15, 20, 30], "#8c8a84"), ("Tout-venant compactado", [15, 20, 30], "#9a9486"),
        ("Betonilha de regularização", [3, 4, 5, 6, 8], "#bcbcb6"), ("Betonilha autonivelante", [0.5, 1, 3, 5], "#c4c4be"),
        ("Betonilha leve (argila expandida / EPS)", [5, 8, 10], "#c8c5bc"), ("Betonilha armada para piso radiante", [5, 6, 7], "#bcbcb6"),
        ("Camada de forma (pendentes)", [3, 5, 8, 10], "#c2c0b8"),
    ]),
    ("Madeira e derivados", [
        ("Painel de madeira lamelada cruzada (CLT)", [6, 8, 10, 12, 14, 16, 18, 20, 24, 28], "#d8b98a"),
        ("Madeira lamelada colada (glulam)", [8, 10, 12, 14, 16, 20], "#d6b27e"),
        ("Madeira microlaminada (LVL)", [2.7, 3.9, 4.5, 7.5], "#cfa970"),
        ("Estrutura de madeira maciça (montantes)", [9, 12, 14, 16, 20], "#d2ad78"),
        ("Madeira maciça de pinho", [2, 2.5, 4, 5, 7], "#dcbc86"), ("Madeira maciça de carvalho", [2, 2.2, 4], "#b98b56"),
        ("Madeira maciça de castanho", [2, 2.2, 4], "#a9794a"), ("Madeira maciça de criptoméria", [2, 2.5, 4], "#c99a6a"),
        ("Madeira maciça de cedro", [1.8, 2, 2.5], "#c58a5a"), ("Madeira maciça de casquinha (pinho nórdico)", [2, 2.5, 4.5], "#e0c48f"),
        ("Madeira exótica (ipê / cumaru)", [2, 2.1, 2.5], "#7a4f30"), ("Madeira termotratada", [2, 2.6], "#8a5e3a"),
        ("Madeira carbonizada (yakisugi)", [2, 2.5], "#2b2725"), ("Painel OSB 3", [0.9, 1.2, 1.5, 1.8, 2.2], "#d1a35c"),
        ("Contraplacado marítimo", [0.9, 1.2, 1.5, 1.8, 2.1], "#c99b62"), ("Contraplacado de bétula", [0.9, 1.2, 1.5, 1.8], "#e2cba0"),
        ("Aglomerado de partículas hidrófugo", [1.6, 1.9, 2.2], "#b9a27a"), ("MDF hidrófugo", [1, 1.2, 1.6, 1.9], "#a98d68"),
        ("Painel de três camadas (madeira maciça)", [1.9, 2.7, 4.2], "#d9bb85"),
        ("Painel de cimento-madeira", [0.8, 1, 1.2, 1.6, 1.9, 2.2], "#8f8f8a"),
        ("Ripado de madeira sobre sarrafos", [4, 5, 6], "#c79a66"), ("Forro de madeira (lambrim)", [1, 1.2, 1.5], "#d9b783"),
        ("Bambu laminado", [1.5, 2], "#c9a55e"),
    ]),
    ("Aço e painéis metálicos", [
        ("Estrutura em aço leve (LSF) — montantes", [9, 10, 15, 20, 25], "#9aa2a8"),
        ("Estrutura metálica laminada (perfis)", [10, 14, 16, 20, 24, 30], "#7f878d"),
        ("Chapa perfilada de aço galvanizado", [3, 4, 5.9, 7.5], "#a4acb1"), ("Chapa perfilada lacada", [3, 4, 5.9], "#6f7a82"),
        ("Chapa ondulada de aço", [1.8, 2.7], "#9aa3a9"), ("Chapa de aço corten", [0.2, 0.3, 0.4], "#8a4a2c"),
        ("Chapa de zinco-titânio", [0.07, 0.08], "#8d979d"), ("Chapa de cobre", [0.06, 0.07], "#b56a3a"),
        ("Chapa de alumínio lacado", [0.1, 0.15, 0.2], "#c7ccd0"), ("Painel de alumínio compósito", [0.3, 0.4, 0.6], "#cfd3d6"),
        ("Cassete metálica de fachada", [3, 4, 5], "#b9bfc4"), ("Chapa perfurada / metal distendido", [0.15, 0.2, 0.3], "#9da5aa"),
        ("Painel sandwich de fachada com lã de rocha", [5, 6, 8, 10, 12, 15], "#dfe2e4"),
        ("Painel sandwich de fachada com poliuretano", [3, 4, 5, 6, 8, 10], "#dfe2e4"),
        ("Painel sandwich de cobertura com poliuretano", [3, 4, 5, 6, 8, 10], "#b9503a"),
        ("Painel sandwich de cobertura com lã de rocha", [5, 8, 10, 12, 15], "#8b9298"),
        ("Painel frigorífico (PIR)", [6, 8, 10, 12, 15, 20], "#eef0f1"),
    ]),
    ("Isolamento térmico", [
        ("Poliestireno expandido (EPS)", [2, 3, 4, 5, 6, 8, 10, 12, 14, 16, 18, 20], "#f1f3f4"),
        ("Poliestireno expandido grafitado (EPS cinza)", [4, 6, 8, 10, 12, 14, 16, 20], "#9da3a8"),
        ("Poliestireno extrudido (XPS)", [2, 3, 4, 5, 6, 8, 10, 12, 14, 16], "#e9c7d6"),
        ("Lã de rocha em painel", [3, 4, 5, 6, 8, 10, 12, 14, 16, 20], "#c9b56a"),
        ("Lã de rocha em manta", [5, 6, 8, 10, 12, 16, 20], "#c9b56a"),
        ("Lã de vidro em painel", [3, 4, 5, 6, 8, 10], "#e6d36a"), ("Lã de vidro em manta", [5, 8, 10, 12, 16, 20, 24], "#e6d36a"),
        ("Aglomerado de cortiça expandida (ICB)", [2, 3, 4, 5, 6, 8, 10, 12, 15, 20], "#4f3a2a"),
        ("Poliisocianurato (PIR) em painel", [2, 3, 4, 5, 6, 8, 10, 12], "#e8dca6"),
        ("Poliuretano projetado", [3, 4, 5, 6, 8, 10], "#e3cf8a"), ("Espuma fenólica", [2, 3, 4, 5, 6, 8, 10], "#d9a8a0"),
        ("Fibra de madeira em painel", [2, 4, 6, 8, 10, 12, 14, 16, 20], "#b08a5a"),
        ("Celulose insuflada", [10, 15, 20, 25, 30], "#b9b6ae"), ("Lã de ovelha", [5, 8, 10, 12], "#e4dccb"),
        ("Fibra de cânhamo", [4, 6, 8, 10, 12], "#bfb48a"), ("Algodão reciclado", [5, 8, 10], "#9aa8c0"),
        ("Vidro celular", [4, 5, 6, 8, 10, 12], "#3d3f42"), ("Manta de aerogel", [0.5, 1, 2], "#dfe6ea"),
        ("Painel de isolamento por vácuo (VIP)", [1, 2, 3], "#b9bec2"),
        ("Argila expandida a granel", [5, 10, 15, 20], "#a9805c"), ("Perlite expandida", [5, 10, 15], "#e9e7e0"),
        ("Vermiculite expandida", [5, 10], "#c9b27a"), ("Isolamento refletivo multicamada", [0.5, 1, 2, 3], "#cfd5d9"),
        ("Placa de EPS moldado para piso radiante", [2, 3, 4.5], "#f1f3f4"),
        ("Granulado de cortiça", [5, 10, 15], "#8a6a48"),
    ]),
    ("Isolamento acústico", [
        ("Membrana acústica de alta densidade", [0.2, 0.4], "#3a3a3c"),
        ("Manta de polietileno reticulado (ruído de impacto)", [0.3, 0.5, 1], "#e6eaec"),
        ("Aglomerado de borracha reciclada", [0.3, 0.5, 1, 2], "#2f2f31"), ("Tela de cortiça (underlay)", [0.2, 0.3, 0.5], "#b08a5a"),
        ("Lã mineral acústica", [4, 5, 7], "#cdbb72"), ("Painel de fibras de poliéster", [2, 4, 5], "#eceae4"),
        ("Aglomerado de espuma de poliuretano", [2, 4, 6, 8], "#b7a7c9"),
        ("Painel absorvente de madeira ranhurada", [1.6, 1.9], "#c99b62"),
        ("Painel de lã de madeira (aglomerado com cimento)", [1.5, 2.5, 3.5, 5], "#d6cdb4"),
        ("Banda resiliente para paredes", [0.5, 1], "#55585b"),
    ]),
    ("Impermeabilização e membranas", [
        ("Membrana betuminosa APP", [0.3, 0.4], "#2e2e30"), ("Membrana betuminosa SBS", [0.3, 0.4], "#2e2e30"),
        ("Membrana betuminosa com acabamento em ardósia", [0.4], "#55595c"), ("Membrana de PVC", [0.12, 0.15, 0.18], "#c9ced2"),
        ("Membrana de TPO", [0.12, 0.15, 0.18], "#e4e7e9"), ("Membrana de EPDM", [0.11, 0.15], "#262628"),
        ("Membrana líquida de poliuretano", [0.15, 0.2], "#8f979c"), ("Membrana líquida acrílica", [0.1, 0.15], "#d9dcde"),
        ("Argamassa de impermeabilização cimentícia flexível", [0.2, 0.3, 0.4], "#a6a6a1"),
        ("Emulsão betuminosa", [0.1, 0.2], "#2e2e30"), ("Membrana drenante pitonada", [0.8, 2], "#4a4f38"),
        ("Geotêxtil", [0.1, 0.2], "#e9e9e6"), ("Barreira pára-vapor", [0.02, 0.1], "#9fb6c9"),
        ("Membrana transpirante (subtelha)", [0.05, 0.1], "#c7ccd0"), ("Barreira corta-capilaridade", [0.1, 0.3], "#2e2e30"),
        ("Manta de bentonite", [0.6], "#8f8a7a"), ("Camada drenante de seixo", [5, 8, 10], "#b6b0a4"),
        ("Substrato de cobertura verde", [8, 10, 15, 20, 30], "#5a4a38"),
    ]),
    ("Rebocos e argamassas", [
        ("Reboco tradicional de cimento e areia", [1, 1.5, 2, 2.5], "#d9d6cc"), ("Reboco de cal hidráulica natural", [1.5, 2, 2.5], "#e6e0cf"),
        ("Reboco de cal aérea", [1.5, 2], "#eee9d9"), ("Reboco bastardo (cimento e cal)", [1.5, 2], "#dedacc"),
        ("Reboco projetado de gesso", [1, 1.5, 2], "#f1efe9"), ("Reboco monomassa", [1.2, 1.5, 2], "#e4dfd2"),
        ("Reboco térmico (com cortiça ou EPS)", [2, 3, 4, 5, 6], "#e2dcc9"), ("Reboco de argila", [1.5, 2, 3], "#c2a27a"),
        ("Reboco hidrófugo", [1.5, 2], "#d6d3c9"), ("Camada de base armada (ETICS)", [0.3, 0.4, 0.5], "#cfcdc6"),
        ("Acabamento acrílico (ETICS)", [0.15, 0.2, 0.3], "#f1efe9"), ("Acabamento de silicato (ETICS)", [0.15, 0.2, 0.3], "#efede6"),
        ("Acabamento de silicone / siloxano (ETICS)", [0.15, 0.2, 0.3], "#f0eee8"),
        ("Estuque tradicional", [1, 1.5], "#f4f2ec"), ("Estuque projetado", [1, 1.5], "#f4f2ec"),
        ("Barramento (massa de acabamento)", [0.2, 0.3], "#f6f5f0"), ("Argamassa de assentamento", [1, 1.5], "#bdbbb4"),
        ("Cimento-cola", [0.3, 0.5, 1], "#b5b3ac"), ("Salpico / chapisco", [0.5], "#c9c6bc"),
        ("Marmorite", [1, 1.5], "#cfcabb"), ("Tadelakt", [0.5, 1], "#d9c2a8"),
    ]),
    ("Gesso e placas", [
        ("Placa de gesso cartonado standard", [1.25, 1.5, 1.8], "#ecebe6"), ("Placa de gesso cartonado hidrófuga", [1.25, 1.5], "#bcd8c2"),
        ("Placa de gesso cartonado corta-fogo", [1.25, 1.5, 1.8], "#e6c2c2"), ("Placa de gesso cartonado de alta dureza", [1.25, 1.5], "#c8d2e0"),
        ("Placa de gesso cartonado acústica", [1.25], "#c5cfe6"), ("Placa de gesso cartonado dupla (2 × 12,5)", [2.5], "#ecebe6"),
        ("Placa de gesso cartonado tripla (3 × 12,5)", [3.75], "#ecebe6"), ("Placa de gesso com fibras", [1, 1.25, 1.5, 1.8], "#e2dfd6"),
        ("Placa de gesso com isolamento colado (EPS)", [3.25, 4.25, 5.25, 7.25], "#eeeee9"),
        ("Placa cimentícia", [0.8, 1, 1.25], "#b9b9b3"), ("Placa de fibrocimento", [0.6, 0.8, 1, 1.2], "#a9aaa5"),
        ("Placa de silicato de cálcio", [1, 1.2, 1.5, 2, 2.5], "#e9e6dc"), ("Placa de óxido de magnésio", [0.9, 1.2], "#e4e2da"),
        ("Estrutura metálica de montantes 48", [4.8], "#b9c0c5"), ("Estrutura metálica de montantes 70", [7], "#b9c0c5"),
        ("Estrutura metálica de montantes 90", [9], "#b9c0c5"), ("Estrutura metálica de montantes 100", [10], "#b9c0c5"),
        ("Caixa de ar", [1, 2, 3, 4, 5, 6], "#f7fafc"), ("Caixa de ar ventilada", [2, 3, 4, 5], "#f2f8fb"),
    ]),
    ("Revestimentos de parede", [
        ("Azulejo cerâmico", [0.6, 0.8, 1], "#e9eef2"), ("Azulejo tradicional pintado", [0.8, 1], "#3f6fa8"),
        ("Grés porcelânico", [0.6, 0.9, 1, 1.2, 2], "#cfcdc8"), ("Grés porcelânico de grande formato", [0.6, 1.2], "#c9c7c2"),
        ("Mosaico hidráulico", [1.6, 2], "#8c9aa6"), ("Pastilha de vidro", [0.4, 0.8], "#7fb1c4"),
        ("Tijoleira de barro", [1.5, 2, 3], "#b9603f"), ("Plaqueta cerâmica (imitação tijolo)", [1, 1.5, 2], "#b5583c"),
        ("Revestimento cerâmico de fachada ventilada", [1, 1.2, 2], "#b7b3aa"), ("Painel fenólico compacto (HPL)", [0.6, 0.8, 1], "#8a6a4a"),
        ("Revestimento em cortiça", [0.3, 0.6, 1], "#a9805c"), ("Microcimento", [0.2, 0.3], "#b9b7b1"),
        ("Papel de parede", [0.05], "#e6e0d6"), ("Revestimento vinílico de parede", [0.1, 0.2], "#dcdcd8"),
        ("Painel de MDF lacado", [1.2, 1.6, 1.9], "#f2f2ef"), ("Painel folheado a madeira", [1.2, 1.6, 1.9], "#b98b56"),
        ("Espelho", [0.4, 0.5, 0.6], "#cfdde3"), ("Pedra reconstituída", [2, 3, 4], "#bdb5a5"),
        ("Tinta plástica mate", [0.02], "#f4f3ee"), ("Tinta acetinada lavável", [0.02], "#f4f3ee"), ("Tinta de silicato", [0.02], "#f1efe8"),
        ("Tinta de cal (caiação)", [0.02], "#fbfaf5"), ("Esmalte aquoso", [0.02], "#f6f6f2"), ("Tinta epóxi", [0.03], "#bfc5c9"),
        ("Tinta intumescente", [0.1], "#f0efe9"), ("Verniz / velatura para madeira", [0.02], "#c79a66"),
    ]),
    ("Pavimentos", [
        ("Soalho de madeira maciça", [1.8, 2, 2.2], "#b98b56"), ("Parquet multicamada", [1, 1.4, 1.5], "#c49a64"),
        ("Parquet de taco tradicional", [1, 1.4, 2.2], "#a9794a"), ("Pavimento flutuante laminado", [0.7, 0.8, 1, 1.2], "#c7a274"),
        ("Pavimento vinílico em réguas (LVT / SPC)", [0.2, 0.4, 0.5, 0.65], "#b9a98c"), ("Pavimento vinílico em rolo", [0.2, 0.3], "#bdbdb6"),
        ("Linóleo", [0.2, 0.25, 0.32], "#9aa58c"), ("Pavimento de borracha", [0.2, 0.3, 0.4], "#4a4d50"),
        ("Alcatifa", [0.6, 0.8, 1], "#8a8f99"), ("Pavimento de cortiça", [0.4, 0.6, 1], "#a9805c"),
        ("Pavimento de bambu", [1, 1.4, 1.5], "#c9a55e"), ("Mosaico cerâmico", [0.8, 0.9, 1], "#cfc8ba"),
        ("Grés porcelânico retificado", [0.9, 1, 2], "#c9c7c2"), ("Tijoleira de barro para pavimento", [2, 3], "#b9603f"),
        ("Pedra natural em pavimento (granito)", [2, 3, 4], "#a9a59b"), ("Pedra natural em pavimento (calcário)", [2, 3], "#e2dccb"),
        ("Pedra natural em pavimento (mármore)", [2, 3], "#eceae4"), ("Pedra natural em pavimento (ardósia)", [1, 2], "#4e5357"),
        ("Betão afagado / polido", [8, 10, 12], "#a9a9a4"), ("Microcimento em pavimento", [0.3], "#b0aea8"),
        ("Resina epóxi", [0.2, 0.3, 0.5], "#9aa3a8"), ("Resina de poliuretano", [0.2, 0.3], "#a7adb1"),
        ("Terrazzo", [1.5, 2, 3], "#cfcabb"), ("Pavimento técnico elevado", [3, 3.8], "#b9bec2"),
        ("Deck de madeira", [2.1, 2.5, 2.8], "#8a5e3a"), ("Deck compósito (WPC)", [2.1, 2.3, 2.5], "#6f5a48"),
        ("Calçada portuguesa", [5, 6, 8], "#e6e2d6"), ("Cubos de granito", [5, 8, 11], "#9d998f"),
        ("Pavê de betão", [6, 8, 10], "#a2a09a"), ("Lajetas de betão", [4, 5, 6], "#b3b1ab"),
        ("Lajetas sobre apoios reguláveis", [2, 4], "#b9b7b1"), ("Grelha de enrelvamento", [4, 8, 10], "#7f9a6a"),
        ("Saibro estabilizado", [5, 8, 10], "#cfb98a"), ("Gravilha", [4, 5, 8], "#b6b0a4"),
        ("Betuminoso", [4, 5, 6, 8], "#3a3a3c"), ("Relva sintética", [2, 3, 4], "#5d8a3a"),
    ]),
    ("Tetos", [
        ("Teto falso em gesso cartonado", [1.25, 1.5], "#f4f3ee"), ("Teto falso hidrófugo", [1.25], "#eef3ef"),
        ("Teto modular de fibra mineral", [1.5, 1.9, 2], "#eeeeea"), ("Teto modular metálico", [0.05, 0.06], "#d9dde0"),
        ("Teto em ripado de madeira", [2, 3, 4], "#c79a66"), ("Teto em painel de lã de madeira", [2.5, 3.5], "#d6cdb4"),
        ("Teto tenso (membrana)", [0.02], "#f6f6f4"), ("Teto em estuque", [1, 1.5], "#f4f2ec"),
        ("Teto em betão aparente", [0], "#b0b0ab"), ("Teto acústico perfurado", [1.25], "#f0efea"),
    ]),
    ("Vidro e translúcidos", [
        ("Vidro simples", [0.4, 0.5, 0.6, 0.8], "#bfe0e6"), ("Vidro duplo 4-16-4", [2.4], "#b5d9e2"),
        ("Vidro duplo 6-16-4 baixo emissivo", [2.6], "#b0d5df"), ("Vidro duplo 6-14-44.2 laminado", [2.9], "#aed2dc"),
        ("Vidro triplo 4-12-4-12-4", [3.6], "#a9cfda"), ("Vidro triplo 4-16-4-16-4", [4.4], "#a9cfda"),
        ("Vidro laminado 33.1", [0.64], "#bfe0e6"), ("Vidro laminado 44.2", [0.88], "#bfe0e6"),
        ("Vidro laminado 55.2", [1.08], "#bfe0e6"), ("Vidro temperado", [0.6, 0.8, 1, 1.2], "#bfe0e6"),
        ("Vidro de controlo solar", [2.4, 2.8], "#8fb8c6"), ("Vidro fosco / acidado", [0.4, 0.6, 0.8], "#dbe9ec"),
        ("Vidro perfilado (U-glass)", [4.1, 6], "#c9e2e6"), ("Policarbonato alveolar", [0.6, 1, 1.6, 2, 2.5, 3.2], "#dcecf0"),
        ("Policarbonato compacto", [0.3, 0.4, 0.5, 0.6], "#dcecf0"), ("Acrílico (PMMA)", [0.3, 0.5, 0.8, 1], "#e2f0f3"),
    ]),
]

BIBLIOTECA: List[Dict[str, Any]] = []
for _cat, _itens in _BIB:
    for _nome, _esp, _cor in _itens:
        BIBLIOTECA.append({"id": _slug(_nome), "nome": _nome, "categoria": _cat, "espessuras_cm": _esp, "cor": _cor})
CATEGORIAS: List[str] = [c for c, _ in _BIB]
_POR_NOME: Dict[str, Dict[str, Any]] = {m["nome"]: m for m in BIBLIOTECA}


# ---------------------------------------------------------------- acabamentos por lista (id → nome, grupo, cor)
def _lista(grupos: List[Tuple[str, List[Tuple[str, str, str]]]]) -> List[Dict[str, str]]:
    return [{"id": i, "nome": n, "grupo": g, "cor": c} for g, itens in grupos for i, n, c in itens]


FACHADA = _lista([
    ("Rebocos e pinturas", [
        ("reboco_branco", "Reboco pintado a branco", "#f1efe9"), ("reboco_creme", "Reboco pintado creme", "#ece3cc"),
        ("reboco_areia", "Reboco pintado cor de areia", "#d9c9a8"), ("reboco_ocre", "Reboco pintado ocre", "#d2a04a"),
        ("reboco_terracota", "Reboco pintado terracota", "#b8623f"), ("reboco_rosa_velho", "Reboco pintado rosa-velho", "#cf9f93"),
        ("reboco_azul_claro", "Reboco pintado azul-claro", "#a9c3d6"), ("reboco_verde_seco", "Reboco pintado verde-seco", "#9aa68a"),
        ("reboco_cinza_claro", "Reboco pintado cinza-claro", "#cfd0cc"), ("reboco_cinza", "Reboco pintado cinza", "#a3a5a2"),
        ("reboco_cinza_escuro", "Reboco pintado cinza-escuro", "#6d7072"), ("reboco_antracite", "Reboco pintado antracite", "#3f4245"),
        ("reboco_preto", "Reboco pintado preto", "#262729"), ("cal_branca", "Caiação tradicional branca", "#fbfaf5"),
        ("cal_barra_azul", "Caiação branca com barra azul", "#f7f6f1"), ("cal_barra_ocre", "Caiação branca com barra ocre", "#f7f6f1"),
        ("etics_branco", "ETICS com acabamento acrílico branco", "#f3f1ec"), ("etics_cinza", "ETICS com acabamento cinza", "#b9bab6"),
        ("reboco_cal_natural", "Reboco de cal à vista (natural)", "#e2d9c2"), ("reboco_argila", "Reboco de argila à vista", "#c2a27a"),
        ("marmorite", "Marmorite", "#cfcabb"),
    ]),
    ("Pedra", [
        ("granito", "Revestimento em granito da região (cantaria / placagem)", "#b0aca2"), ("granito_amarelo", "Granito amarelo", "#cdb98c"),
        ("granito_cinza_escuro", "Granito cinza-escuro", "#6f7173"), ("xisto", "Revestimento em pedra de xisto", "#68625c"),
        ("calcario", "Placagem de calcário (moleanos / lioz)", "#e2dccb"), ("marmore_branco", "Placagem de mármore branco", "#eceae4"),
        ("basalto", "Placagem de basalto", "#4b4b4d"), ("ardosia", "Placagem de ardósia", "#4e5357"),
        ("travertino", "Placagem de travertino", "#dccfb6"), ("arenito", "Placagem de arenito", "#c9ad84"),
        ("pedra_seca", "Alvenaria de pedra à vista", "#9d978c"), ("pedra_reconstituida", "Pedra reconstituída", "#bdb5a5"),
    ]),
    ("Tijolo e cerâmica", [
        ("tijolo", "Tijolo face à vista", "#be6e54"), ("tijolo_burro", "Tijolo de burro tradicional", "#a8553d"),
        ("tijolo_branco", "Tijolo face à vista branco", "#e6e2d8"), ("tijolo_cinza", "Tijolo face à vista cinza", "#8c8c88"),
        ("tijolo_preto", "Tijolo face à vista preto", "#3a3836"), ("plaqueta_ceramica", "Plaqueta cerâmica", "#b5583c"),
        ("azulejo_azul", "Azulejo tradicional azul e branco", "#5f86b5"), ("azulejo_branco", "Azulejo branco", "#f0f3f5"),
        ("azulejo_verde", "Azulejo verde vidrado", "#4f8a6a"), ("ceramica_ventilada_cinza", "Fachada ventilada cerâmica cinza", "#b7b3aa"),
        ("ceramica_ventilada_terracota", "Fachada ventilada cerâmica terracota", "#b9603f"),
        ("gres_grande_formato", "Grés porcelânico de grande formato", "#c9c7c2"),
    ]),
    ("Madeira e cortiça", [
        ("madeira", "Revestimento em ripado de madeira tratada", "#ba8c60"), ("madeira_cedro", "Ripado de cedro", "#c58a5a"),
        ("madeira_pinho", "Tabuado de pinho tratado", "#dcbc86"), ("madeira_termotratada", "Madeira termotratada", "#8a5e3a"),
        ("madeira_carbonizada", "Madeira carbonizada (yakisugi)", "#2b2725"), ("madeira_cinza", "Madeira envelhecida cinza", "#9a968e"),
        ("madeira_pintada_branca", "Tabuado pintado a branco", "#f2f1ec"), ("madeira_pintada_preta", "Tabuado pintado a preto", "#2a2b2c"),
        ("fenolico_madeira", "Painel fenólico com acabamento madeira", "#8a6a4a"), ("cortica_expandida", "Aglomerado de cortiça expandida à vista", "#4f3a2a"),
        ("composito_madeira", "Ripado compósito (WPC)", "#6f5a48"),
    ]),
    ("Betão e painéis", [
        ("betao", "Betão aparente", "#b0b0ac"), ("betao_tabua", "Betão aparente com cofragem de tábua", "#a6a6a1"),
        ("betao_branco", "Betão branco aparente", "#e6e4de"), ("betao_pigmentado", "Betão pigmentado ocre", "#c2a27a"),
        ("grc", "Painel de GRC", "#c9c8c2"), ("fibrocimento_natural", "Painel de fibrocimento natural", "#a9aaa5"),
        ("fibrocimento_antracite", "Painel de fibrocimento antracite", "#4a4d50"), ("cimento_madeira", "Painel de cimento-madeira", "#8f8f8a"),
        ("fenolico_cinza", "Painel fenólico cinza", "#8d9195"), ("fenolico_branco", "Painel fenólico branco", "#eeeeea"),
        ("taipa", "Taipa à vista", "#b58c60"),
    ]),
    ("Metal e vidro", [
        ("aco_corten", "Chapa de aço corten", "#8a4a2c"), ("zinco_natural", "Zinco natural (junta agrafada)", "#8d979d"),
        ("zinco_antracite", "Zinco antracite (junta agrafada)", "#4a4f54"), ("cobre", "Cobre", "#b56a3a"),
        ("cobre_patinado", "Cobre patinado verde", "#5f9a86"), ("aluminio_composito_branco", "Alumínio compósito branco", "#eef0f1"),
        ("aluminio_composito_prata", "Alumínio compósito prata", "#bfc5c9"), ("aluminio_composito_antracite", "Alumínio compósito antracite", "#3f4347"),
        ("chapa_ondulada", "Chapa ondulada galvanizada", "#9aa3a9"), ("chapa_perfilada_preta", "Chapa perfilada preta", "#2c2e30"),
        ("chapa_perfurada", "Chapa perfurada", "#9da5aa"), ("painel_sandwich_branco", "Painel sandwich branco", "#eef0f1"),
        ("painel_sandwich_cinza", "Painel sandwich cinza", "#9aa0a5"), ("fachada_cortina", "Fachada-cortina de vidro", "#8fb8c6"),
        ("policarbonato", "Policarbonato alveolar", "#dcecf0"),
    ]),
    ("Combinações", [
        ("misto_granito_reboco", "Granito no rés-do-chão e reboco branco no andar", "#f1efe9"),
        ("misto_madeira_reboco", "Reboco branco com apontamentos em madeira", "#f1efe9"),
        ("misto_granito_madeira", "Granito da região com revestimento em ripado de madeira na fachada principal", "#b0aca2"),
    ]),
])

COBERTURA = _lista([
    ("Telha cerâmica", [
        ("telha_ceramica", "Telha cerâmica vermelha (tipo Marselha / lusa)", "#ba6042"), ("telha_lusa", "Telha lusa vermelha", "#b85a3c"),
        ("telha_marselha", "Telha Marselha", "#b6583a"), ("telha_canudo", "Telha de canudo tradicional", "#c0704c"),
        ("telha_romana", "Telha romana", "#b9623f"), ("telha_plana_vermelha", "Telha plana cerâmica vermelha", "#a9523a"),
        ("telha_envelhecida", "Telha cerâmica envelhecida", "#a8724e"), ("telha_castanha", "Telha cerâmica castanha", "#6f4a38"),
        ("telha_cinza", "Telha cerâmica cinza", "#7d8083"), ("telha_preta", "Telha cerâmica preta", "#46484c"),
        ("telha_vidrada_verde", "Telha vidrada verde", "#3f6f55"),
    ]),
    ("Telha de betão e ardósia", [
        ("telha_betao_cinza", "Telha de betão cinza", "#85888a"), ("telha_betao_preta", "Telha de betão preta", "#3d3f42"),
        ("telha_betao_vermelha", "Telha de betão vermelha", "#a9553f"), ("ardosia_natural", "Ardósia natural", "#4e5357"),
        ("xisto_cobertura", "Lousa de xisto", "#5f5a55"), ("shingle_preto", "Telha asfáltica (shingle) preta", "#333537"),
        ("shingle_vermelho", "Telha asfáltica (shingle) vermelha", "#8f4a3a"), ("shingle_verde", "Telha asfáltica (shingle) verde", "#4f6652"),
        ("fibrocimento_ondulado", "Chapa ondulada de fibrocimento", "#a9aaa5"),
    ]),
    ("Metal", [
        ("zinco", "Chapa de zinco", "#8c969c"), ("zinco_quartzo", "Zinco quartzo (junta agrafada)", "#7c858b"),
        ("zinco_antracite_cob", "Zinco antracite (junta agrafada)", "#4a4f54"), ("cobre_cob", "Cobre", "#b56a3a"),
        ("cobre_patinado_cob", "Cobre patinado verde", "#5f9a86"), ("aluminio_agrafado", "Alumínio de junta agrafada", "#b9bfc4"),
        ("chapa_lacada_vermelha", "Chapa perfilada lacada vermelha", "#a94a3a"), ("chapa_lacada_cinza", "Chapa perfilada lacada cinza", "#7f878d"),
        ("chapa_lacada_preta", "Chapa perfilada lacada preta", "#2f3133"), ("chapa_lacada_verde", "Chapa perfilada lacada verde", "#4a6652"),
        ("sandwich_telha", "Painel sandwich imitação telha", "#b5553c"), ("sandwich_branco", "Painel sandwich branco", "#e9ecee"),
        ("sandwich_cinza", "Painel sandwich cinza", "#8b9298"), ("aco_corten_cob", "Chapa de aço corten", "#8a4a2c"),
    ]),
    ("Plana e especial", [
        ("plana_seixo", "Cobertura plana com proteção em seixo", "#b6b0a4"), ("plana_lajetas", "Cobertura plana com lajetas", "#b9b7b1"),
        ("plana_deck", "Cobertura plana com deck de madeira", "#8a5e3a"), ("plana_ceramica", "Terraço com pavimento cerâmico", "#c9c2b4"),
        ("plana_tela_ardosia", "Cobertura plana com tela de ardósia", "#5a5e61"), ("plana_branca", "Cobertura plana branca refletante", "#f0f1f1"),
        ("plana_pvc_cinza", "Cobertura plana com membrana cinza", "#a9aeb2"), ("verde_extensiva", "Cobertura verde extensiva", "#6f8f55"),
        ("verde_intensiva", "Cobertura verde intensiva (jardim)", "#4f7a3f"), ("colmo", "Colmo", "#b79a5a"),
        ("madeira_ripas", "Ripas de madeira (tavela)", "#8f6a48"), ("vidro_cob", "Cobertura envidraçada", "#9cc4d0"),
        ("policarbonato_cob", "Policarbonato", "#dcecf0"), ("fotovoltaica", "Cobertura fotovoltaica integrada", "#1f2a44"),
    ]),
])

CAIXILHARIA = _lista([
    ("Alumínio", [
        ("aluminio_antracite", "Alumínio lacado antracite com corte térmico, vidro duplo", "#2f3235"),
        ("aluminio_branco", "Alumínio lacado branco com corte térmico, vidro duplo", "#f2f2f0"),
        ("aluminio_preto", "Alumínio lacado preto mate", "#1c1d1f"), ("aluminio_cinza", "Alumínio lacado cinza", "#8a9096"),
        ("aluminio_anodizado", "Alumínio anodizado natural", "#b9bfc4"), ("aluminio_bronze", "Alumínio anodizado bronze", "#6a5440"),
        ("aluminio_champanhe", "Alumínio anodizado champanhe", "#c9b990"), ("aluminio_madeira", "Alumínio com acabamento madeira", "#8f6a45"),
        ("aluminio_verde", "Alumínio lacado verde-garrafa", "#2f4a3a"), ("aluminio_vermelho", "Alumínio lacado vermelho-óxido", "#7a2f28"),
        ("aluminio_minimalista", "Alumínio minimalista de perfil fino, preto", "#232527"),
    ]),
    ("PVC", [
        ("pvc_branco", "PVC branco, vidro duplo", "#f5f5f3"), ("pvc_antracite", "PVC antracite", "#3a3d40"),
        ("pvc_creme", "PVC creme", "#ece4cf"), ("pvc_cinza", "PVC cinza", "#9a9fa4"),
        ("pvc_carvalho", "PVC com acabamento carvalho dourado", "#a9773f"), ("pvc_nogueira", "PVC com acabamento nogueira", "#5f4030"),
    ]),
    ("Madeira e mistas", [
        ("madeira", "Madeira, vidro duplo", "#7a4b28"), ("madeira_pinho_cx", "Madeira de pinho envernizada", "#c79a5e"),
        ("madeira_carvalho_cx", "Madeira de carvalho", "#a9773f"), ("madeira_lacada_branca", "Madeira lacada a branco", "#f4f3ee"),
        ("madeira_lacada_verde", "Madeira lacada a verde tradicional", "#2f5a45"), ("madeira_lacada_azul", "Madeira lacada a azul", "#2f4f7a"),
        ("madeira_lacada_vermelha", "Madeira lacada a vermelho sangue-de-boi", "#7a2a26"),
        ("madeira_aluminio", "Madeira-alumínio (madeira interior, alumínio exterior)", "#3a3d40"),
    ]),
    ("Aço e ferro", [
        ("aco_preto", "Aço de perfil fino preto", "#1f2022"), ("aco_inox", "Aço inoxidável", "#c2c8cc"),
        ("aco_corten_cx", "Aço corten", "#8a4a2c"), ("ferro_forjado", "Ferro pintado tradicional", "#2a2c2e"),
    ]),
])

PAVIMENTO = _lista([
    ("Madeira e derivados", [
        ("soalho_carvalho", "Soalho de carvalho", "#b98b56"), ("soalho_pinho", "Soalho de pinho", "#d6b47e"),
        ("soalho_castanho", "Soalho de castanho", "#a9794a"), ("parquet_multicamada", "Parquet multicamada de carvalho", "#c49a64"),
        ("parquet_espinha", "Parquet em espinha", "#b08656"), ("flutuante_carvalho", "Flutuante laminado cor carvalho", "#c7a274"),
        ("flutuante_cinza", "Flutuante laminado cinza", "#a9a59c"), ("bambu", "Pavimento de bambu", "#c9a55e"),
        ("cortica_pav", "Pavimento de cortiça", "#a9805c"),
    ]),
    ("Cerâmica e pedra", [
        ("gres_cinza", "Grés porcelânico cinza", "#b9b7b1"), ("gres_bege", "Grés porcelânico bege", "#d6ccb8"),
        ("gres_antracite", "Grés porcelânico antracite", "#4a4c4f"), ("gres_madeira", "Grés porcelânico imitação madeira", "#a98a66"),
        ("mosaico_hidraulico", "Mosaico hidráulico", "#8c9aa6"), ("tijoleira", "Tijoleira de barro", "#b9603f"),
        ("granito_pav", "Granito", "#a9a59b"), ("calcario_pav", "Calcário (moleanos / lioz)", "#e2dccb"),
        ("marmore_pav", "Mármore", "#eceae4"), ("ardosia_pav", "Ardósia", "#4e5357"), ("terrazzo", "Terrazzo", "#cfcabb"),
    ]),
    ("Contínuos e resilientes", [
        ("betao_afagado", "Betão afagado", "#a9a9a4"), ("microcimento_pav", "Microcimento", "#b0aea8"),
        ("epoxi", "Resina epóxi", "#9aa3a8"), ("vinilico_madeira", "Vinílico em réguas cor madeira", "#b9a98c"),
        ("vinilico_cinza", "Vinílico cinza", "#a2a4a2"), ("linoleo", "Linóleo", "#9aa58c"), ("alcatifa", "Alcatifa", "#8a8f99"),
        ("borracha", "Borracha", "#4a4d50"),
    ]),
])

PAREDE_INTERIOR = _lista([
    ("Pintura", [
        ("pintura_branca", "Pintura branca mate", "#f6f5f0"), ("pintura_creme", "Pintura creme", "#ece3cc"),
        ("pintura_cinza_claro", "Pintura cinza-claro", "#d6d7d3"), ("pintura_cinza", "Pintura cinza", "#a3a5a2"),
        ("pintura_verde_seco", "Pintura verde-seco", "#9aa68a"), ("pintura_azul", "Pintura azul", "#7f9ab5"),
        ("pintura_terracota", "Pintura terracota", "#b8623f"), ("pintura_antracite", "Pintura antracite", "#3f4245"),
    ]),
    ("Revestimentos", [
        ("estuque", "Estuque liso", "#f4f2ec"), ("azulejo_branco_int", "Azulejo branco", "#f0f3f5"),
        ("azulejo_cor", "Azulejo de cor", "#7fa8b5"), ("gres_parede", "Grés porcelânico", "#cfcdc8"),
        ("microcimento_parede", "Microcimento", "#b9b7b1"), ("lambrim_madeira", "Lambrim de madeira", "#c79a66"),
        ("painel_madeira", "Painel folheado a madeira", "#b98b56"), ("mdf_lacado", "Painel de MDF lacado", "#f2f2ef"),
        ("papel_parede", "Papel de parede", "#e6e0d6"), ("pedra_vista", "Pedra à vista", "#a9a59b"),
        ("tijolo_vista_int", "Tijolo à vista", "#b9583c"), ("betao_vista_int", "Betão aparente", "#b0b0ab"),
        ("cortica_parede", "Cortiça", "#a9805c"), ("reboco_argila_int", "Reboco de argila", "#c2a27a"),
    ]),
])

TETO = _lista([
    ("Tetos", [
        ("teto_estuque", "Estuque pintado a branco", "#f6f5f0"), ("teto_gesso_cartonado", "Teto falso em gesso cartonado", "#f4f3ee"),
        ("teto_hidrofugo", "Teto falso hidrófugo", "#eef3ef"), ("teto_modular", "Teto modular de fibra mineral", "#eeeeea"),
        ("teto_acustico", "Teto acústico perfurado", "#f0efea"), ("teto_madeira", "Teto em ripado de madeira", "#c79a66"),
        ("teto_la_madeira", "Teto em painel de lã de madeira", "#d6cdb4"), ("teto_betao", "Betão aparente", "#b0b0ab"),
        ("teto_vigas_madeira", "Vigamento de madeira à vista", "#a9794a"), ("teto_metalico", "Teto modular metálico", "#d9dde0"),
        ("teto_tenso", "Teto tenso", "#f6f6f4"),
    ]),
])

ACABAMENTOS: Dict[str, List[Dict[str, str]]] = {"fachada": FACHADA, "cobertura": COBERTURA, "caixilharia": CAIXILHARIA,
                                               "pavimento": PAVIMENTO, "parede_interior": PAREDE_INTERIOR, "teto": TETO}
PADRAO = {"fachada": "reboco_branco", "cobertura": "telha_ceramica", "caixilharia": "aluminio_antracite",
          "pavimento": "gres_cinza", "parede_interior": "pintura_branca", "teto": "teto_estuque"}
_IDX = {k: {x["id"]: x for x in v} for k, v in ACABAMENTOS.items()}


def acabamento(tipo: str, ident: Any) -> Dict[str, str]:
    """Acabamento escolhido, ou o de omissão quando o identificador não existe na lista."""
    return _IDX[tipo].get(str(ident or ""), _IDX[tipo][PADRAO[tipo]])


def cores(mat: Dict[str, Any]) -> Dict[str, str]:
    return {k: acabamento(k, (mat or {}).get(k))["cor"] for k in ACABAMENTOS}


def rgb(hex_: str) -> Tuple[int, int, int]:
    h = hex_.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


# ---------------------------------------------------------------- paredes-tipo (camadas do interior para o exterior)
def _p(nome: str, exterior: bool, *camadas: Tuple[str, float]) -> Dict[str, Any]:
    return {"nome": nome, "exterior": exterior, "camadas": [{"material": m, "esp_m": round(e / 100, 4)} for m, e in camadas]}


_TIJ = "Tijolo cerâmico furado 30×20×"
PAREDES_TIPO: Dict[str, Dict[str, Any]] = {
    "ext_etics_tijolo22_eps8": _p("Exterior — tijolo 22 + ETICS EPS 8 cm", True,
        ("Reboco projetado de gesso", 1.5), (_TIJ + "22", 22), ("Poliestireno expandido (EPS)", 8), ("Camada de base armada (ETICS)", 0.4), ("Acabamento acrílico (ETICS)", 0.2)),
    "ext_etics_tijolo22_eps12": _p("Exterior — tijolo 22 + ETICS EPS 12 cm", True,
        ("Reboco projetado de gesso", 1.5), (_TIJ + "22", 22), ("Poliestireno expandido (EPS)", 12), ("Camada de base armada (ETICS)", 0.4), ("Acabamento acrílico (ETICS)", 0.2)),
    "ext_etics_termico24_la10": _p("Exterior — bloco térmico 24 + ETICS lã de rocha 10 cm", True,
        ("Reboco projetado de gesso", 1.5), ("Bloco cerâmico térmico de encaixe", 24), ("Lã de rocha em painel", 10), ("Camada de base armada (ETICS)", 0.5), ("Acabamento de silicato (ETICS)", 0.2)),
    "ext_etics_cortica": _p("Exterior — tijolo 22 + ETICS cortiça 8 cm", True,
        ("Reboco de cal hidráulica natural", 2), (_TIJ + "22", 22), ("Aglomerado de cortiça expandida (ICB)", 8), ("Camada de base armada (ETICS)", 0.5), ("Acabamento de silicato (ETICS)", 0.2)),
    "ext_dupla_15_11": _p("Exterior — parede dupla 15 + 11 com XPS 6 cm", True,
        ("Reboco tradicional de cimento e areia", 1.5), (_TIJ + "11", 11), ("Poliestireno extrudido (XPS)", 6), ("Caixa de ar", 3), (_TIJ + "15", 15), ("Reboco tradicional de cimento e areia", 2)),
    "ext_dupla_11_11": _p("Exterior — parede dupla 11 + 11 com lã de rocha 5 cm", True,
        ("Reboco tradicional de cimento e areia", 1.5), (_TIJ + "11", 11), ("Lã de rocha em painel", 5), ("Caixa de ar", 2), (_TIJ + "11", 11), ("Reboco tradicional de cimento e areia", 2)),
    "ext_face_vista": _p("Exterior — tijolo face à vista com caixa de ar", True,
        ("Reboco projetado de gesso", 1.5), (_TIJ + "15", 15), ("Lã de rocha em painel", 8), ("Caixa de ar ventilada", 3), ("Tijolo cerâmico face à vista", 11)),
    "ext_betao_etics": _p("Exterior — betão armado 20 + ETICS EPS 10 cm", True,
        ("Reboco projetado de gesso", 1.5), ("Betão armado", 20), ("Poliestireno expandido grafitado (EPS cinza)", 10), ("Camada de base armada (ETICS)", 0.4), ("Acabamento acrílico (ETICS)", 0.2)),
    "ext_betao_vista_isol_int": _p("Exterior — betão aparente 25 com isolamento interior", True,
        ("Placa de gesso cartonado standard", 1.25), ("Lã de rocha em painel", 8), ("Betão armado aparente (à vista)", 25)),
    "ext_bloco_betao_etics": _p("Exterior — bloco de betão 20 + ETICS EPS 8 cm", True,
        ("Reboco tradicional de cimento e areia", 1.5), ("Bloco de betão normal", 20), ("Poliestireno expandido (EPS)", 8), ("Camada de base armada (ETICS)", 0.4), ("Acabamento acrílico (ETICS)", 0.2)),
    "ext_bca_30": _p("Exterior — bloco de betão celular 30 rebocado", True,
        ("Reboco projetado de gesso", 1), ("Bloco de betão celular autoclavado", 30), ("Reboco monomassa", 1.5)),
    "ext_granito_50": _p("Exterior — alvenaria de granito 50 com isolamento interior", True,
        ("Placa de gesso cartonado standard", 1.25), ("Lã de rocha em painel", 6), ("Caixa de ar", 2), ("Alvenaria de granito", 50)),
    "ext_xisto_50": _p("Exterior — alvenaria de xisto 50 com reboco de cal interior", True,
        ("Reboco de cal hidráulica natural", 2.5), ("Alvenaria de xisto", 50)),
    "ext_fachada_ventilada": _p("Exterior — fachada ventilada cerâmica sobre tijolo 22", True,
        ("Reboco projetado de gesso", 1.5), (_TIJ + "22", 22), ("Lã de rocha em painel", 8), ("Caixa de ar ventilada", 4), ("Revestimento cerâmico de fachada ventilada", 1.2)),
    "ext_clt_ventilada": _p("Exterior — CLT 12 + fibra de madeira 14 + ripado ventilado", True,
        ("Placa de gesso cartonado standard", 1.25), ("Painel de madeira lamelada cruzada (CLT)", 12), ("Fibra de madeira em painel", 14), ("Membrana transpirante (subtelha)", 0.05), ("Caixa de ar ventilada", 3), ("Ripado de madeira sobre sarrafos", 4)),
    "ext_clt_etics": _p("Exterior — CLT 10 + ETICS cortiça 10 cm", True,
        ("Placa de gesso cartonado standard", 1.25), ("Painel de madeira lamelada cruzada (CLT)", 10), ("Aglomerado de cortiça expandida (ICB)", 10), ("Camada de base armada (ETICS)", 0.5), ("Acabamento de silicato (ETICS)", 0.2)),
    "ext_madeira_montantes": _p("Exterior — estrutura de madeira 14 com isolamento e OSB", True,
        ("Placa de gesso cartonado standard", 1.25), ("Barreira pára-vapor", 0.02), ("Estrutura de madeira maciça (montantes)", 14), ("Painel OSB 3", 1.5), ("Fibra de madeira em painel", 6), ("Reboco monomassa", 1.2)),
    "ext_lsf": _p("Exterior — aço leve (LSF) 15 + OSB + ETICS EPS 6 cm", True,
        ("Placa de gesso cartonado dupla (2 × 12,5)", 2.5), ("Estrutura em aço leve (LSF) — montantes", 15), ("Painel OSB 3", 1.2), ("Poliestireno expandido (EPS)", 6), ("Camada de base armada (ETICS)", 0.4), ("Acabamento acrílico (ETICS)", 0.2)),
    "ext_sandwich_10": _p("Exterior — painel sandwich de fachada 10 cm", True, ("Painel sandwich de fachada com lã de rocha", 10)),
    "ext_taipa_50": _p("Exterior — taipa 50 com reboco de argila", True, ("Reboco de argila", 2), ("Taipa", 50)),
    "ext_icf_30": _p("Exterior — bloco de cofragem isolante (ICF) 30", True,
        ("Placa de gesso cartonado standard", 1.25), ("Bloco de cofragem isolante (ICF)", 30), ("Camada de base armada (ETICS)", 0.4), ("Acabamento acrílico (ETICS)", 0.2)),
    "int_tijolo7": _p("Interior — tijolo 7 rebocado", False, ("Reboco projetado de gesso", 1.5), (_TIJ + "7", 7), ("Reboco projetado de gesso", 1.5)),
    "int_tijolo11": _p("Interior — tijolo 11 rebocado", False, ("Reboco projetado de gesso", 1.5), (_TIJ + "11", 11), ("Reboco projetado de gesso", 1.5)),
    "int_tijolo15": _p("Interior — tijolo 15 rebocado", False, ("Reboco projetado de gesso", 1.5), (_TIJ + "15", 15), ("Reboco projetado de gesso", 1.5)),
    "int_bloco_acustico": _p("Interior — bloco cerâmico acústico 15 rebocado", False,
        ("Reboco projetado de gesso", 1.5), ("Bloco cerâmico acústico", 15), ("Reboco projetado de gesso", 1.5)),
    "int_gc_48": _p("Interior — gesso cartonado, montante 48, 1 placa por face", False,
        ("Placa de gesso cartonado standard", 1.25), ("Estrutura metálica de montantes 48", 4.8), ("Placa de gesso cartonado standard", 1.25)),
    "int_gc_70_dupla": _p("Interior — gesso cartonado, montante 70, 2 placas por face", False,
        ("Placa de gesso cartonado dupla (2 × 12,5)", 2.5), ("Estrutura metálica de montantes 70", 7), ("Placa de gesso cartonado dupla (2 × 12,5)", 2.5)),
    "int_gc_hidrofugo": _p("Interior — gesso cartonado hidrófugo (zonas húmidas), montante 70", False,
        ("Placa de gesso cartonado hidrófuga", 1.25), ("Estrutura metálica de montantes 70", 7), ("Placa de gesso cartonado hidrófuga", 1.25)),
    "int_gc_corta_fogo": _p("Interior — gesso cartonado corta-fogo, montante 90, 2 placas por face", False,
        ("Placa de gesso cartonado corta-fogo", 1.5), ("Placa de gesso cartonado corta-fogo", 1.5), ("Estrutura metálica de montantes 90", 9), ("Placa de gesso cartonado corta-fogo", 1.5), ("Placa de gesso cartonado corta-fogo", 1.5)),
    "int_betao_20": _p("Interior — betão armado 20 rebocado", False,
        ("Reboco projetado de gesso", 1), ("Betão armado", 20), ("Reboco projetado de gesso", 1)),
    "int_betao_vista_20": _p("Interior — betão aparente 20", False, ("Betão armado aparente (à vista)", 20)),
    "int_bloco_betao_15": _p("Interior — bloco de betão 15 rebocado", False,
        ("Reboco tradicional de cimento e areia", 1.5), ("Bloco de betão normal", 15), ("Reboco tradicional de cimento e areia", 1.5)),
    "int_bca_10": _p("Interior — bloco de betão celular 10", False,
        ("Reboco projetado de gesso", 1), ("Bloco de betão celular autoclavado", 10), ("Reboco projetado de gesso", 1)),
    "int_clt_10": _p("Interior — CLT 10 à vista", False, ("Painel de madeira lamelada cruzada (CLT)", 10)),
    "int_clt_10_gc": _p("Interior — CLT 10 com gesso cartonado nas duas faces", False,
        ("Placa de gesso cartonado standard", 1.25), ("Painel de madeira lamelada cruzada (CLT)", 10), ("Placa de gesso cartonado standard", 1.25)),
    "int_madeira_9": _p("Interior — estrutura de madeira 9 com gesso cartonado nas duas faces", False,
        ("Placa de gesso cartonado standard", 1.25), ("Estrutura de madeira maciça (montantes)", 9), ("Placa de gesso cartonado standard", 1.25)),
    "int_meacao_dupla": _p("Interior — parede de meação dupla 11 + lã de rocha + 11", False,
        ("Reboco projetado de gesso", 1.5), (_TIJ + "11", 11), ("Lã de rocha em painel", 4), (_TIJ + "11", 11), ("Reboco projetado de gesso", 1.5)),
    "int_tijolo_vidro": _p("Interior — tijolo de vidro 8", False, ("Tijolo de vidro", 8)),
    "int_granito_40": _p("Interior — alvenaria de granito 40 à vista", False, ("Alvenaria de granito", 40)),
}


def catalogo() -> Dict[str, Any]:
    return {"biblioteca": BIBLIOTECA, "categorias": CATEGORIAS, "acabamentos": ACABAMENTOS, "padrao": PADRAO,
            "paredes_tipo": PAREDES_TIPO,
            "nota": "Nomes, espessuras de catálogo e cores de representação. Sem valores térmicos, acústicos ou preços."}


def existe(nome: str) -> bool:
    return nome in _POR_NOME
