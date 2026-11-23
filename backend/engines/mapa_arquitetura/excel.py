"""Livro Excel do mapa de quantidades de arquitetura (DWFX), com fórmulas : azul = medido / pressuposto editável ; preto = fórmula.
Folhas : Mapa, Pressupostos, Compartimentos, Paredes, Portas, Vãos."""
from __future__ import annotations

from collections import Counter, defaultdict

from openpyxl import Workbook

from engines.mapa_estrutura.excel import BLD, N0, N2, _folha, _linha

AZ = "Azul = medido no DWFX ou pressuposto (editável) ; preto = fórmula. Nada estimado por rácio."


def gerar(modelo: dict, caminho: str, titulo: str = "") -> str:
    wb = Workbook()
    wb.remove(wb.active)
    mp = _folha(wb, "Mapa", ["Art.", "Designação", "Un", "Quantidade", "Origem"], [7, 62, 6, 14, 48], f"{titulo} — {AZ}")
    wp = _folha(wb, "Pressupostos", ["Parâmetro", "Valor", "Un", "Origem"], [52, 12, 6, 70], AZ)
    _linha(wp, 5, ["Piso — cota altimétrica do pavimento (plantas)", None, "m", "altura das paredes e origem (cortes : entre lajes ; senão piso a piso)"], negrito=True)
    r = 6
    alt_linha = {}
    for p in modelo["pisos"]:
        c = (p.get("cota") or {}).get("valor")
        _linha(wp, r, [f"{p['piso']} — cota {c:.2f}" if c is not None else f"{p['piso']} — sem cota", p.get("altura"), "m",
                       p.get("altura_origem") or ""], {2: N2}, (2,))
        alt_linha[p["piso"]] = r
        r += 1
    r += 1
    for t in modelo["pressupostos"]:
        _linha(wp, r, [t]); r += 1

    wc = _folha(wb, "Compartimentos", ["Piso", "Compartimento", "Área (m²)", "Perímetro (m)", "Interior / exterior", "Nome por", "Área escrita no desenho (m²)", "Diferença (m²)"], [16, 40, 12, 13, 16, 12, 14, 12], AZ)
    r = 5
    for p in modelo["pisos"]:
        for c in sorted(p["compartimentos"], key=lambda c: (c["exterior"], c["nome"], -c["area"])):
            ad = c.get("area_no_desenho")
            _linha(wc, r, [p["piso"], c["nome"], c["area"], c["perimetro"], "exterior" if c["exterior"] else "interior", c["origem"],
                           ad, f"=C{r}-G{r}" if ad is not None else None], {3: N2, 4: N2, 7: N2, 8: N2}, (3, 4, 7)); r += 1

    wpa = _folha(wb, "Paredes", ["Piso", "Tipo", "Espessura (m)", "Comprimento (m)", "Altura (m)", "Área bruta (m²)"], [16, 18, 13, 15, 11, 15], AZ)
    r = 5
    for p in modelo["pisos"]:
        agg = defaultdict(float)
        for w in p["paredes"]:
            agg[(w["tipo"], round(w["espessura"] * 20) / 20)] += w["comprimento"]
        for (tipo, t), L in sorted(agg.items()):
            hh = p.get("altura")
            _linha(wpa, r, [p["piso"], tipo, t, round(L, 2), hh, f"=D{r}*E{r}" if hh else None],
                   {3: N2, 4: N2, 5: N2, 6: N2}, (3, 4, 5)); r += 1

    wd = _folha(wb, "Portas", ["Piso", "Largura (m)", "Tipo", "Quantidade"], [16, 12, 12, 12], AZ)
    r = 5
    for p in modelo["pisos"]:
        for (L, tipo), n in sorted(Counter((d["L"], d["tipo"]) for d in p["portas"]).items()):
            _linha(wd, r, [p["piso"], L, tipo, n], {2: N2, 4: N0}, (2, 4)); r += 1

    wv = _folha(wb, "Vãos", ["Alçado", "Nível (0 = fila de cima)", "Largura (m)", "Altura (m)", "Área (m²)"], [42, 12, 12, 12, 12], AZ)
    r = 5
    for v in modelo["alcados"]:
        for d in v["vaos"]:
            _linha(wv, r, [v["vista"], d["nivel"], d["L"], d["H"], f"=C{r}*D{r}"], {3: N2, 4: N2, 5: N2}, (3, 4)); r += 1

    comps = [(p, c) for p in modelo["pisos"] for c in p["compartimentos"]]
    pav = sum(c["area"] for _, c in comps if not c["exterior"] and c["nome"] != "Caixa do elevador")
    san = sum(c["area"] for _, c in comps if c["nome"] in ("Instalação sanitária", "I.S.", "WC"))
    ext = sum(c["area"] for _, c in comps if c["exterior"])
    def par(tipo, area=False):
        return round(sum(w["comprimento"] * ((p.get("altura") or 0) if area else 1) for p in modelo["pisos"] for w in p["paredes"]
                         if w["tipo"] == tipo), 2)
    portas = sum(1 for p in modelo["pisos"] for d in p["portas"] if d["tipo"] == "interior")
    vaos = [d for v in modelo["alcados"] for d in v["vaos"]]
    linhas = [
        ("1", "PAVIMENTOS E TETOS", None, None, None),
        ("1.1", "Pavimento interior (sem caixa do elevador)", "m²", round(pav, 2), "folha Compartimentos"),
        ("1.2", "  dos quais instalações sanitárias", "m²", round(san, 2), "folha Compartimentos"),
        ("1.3", "Varandas, terraços e áreas exteriores fechadas", "m²", round(ext, 2), "folha Compartimentos"),
        ("1.4", "Tetos interiores", "m²", round(pav, 2), "igual ao pavimento interior"),
        ("2", "PAREDES", None, None, None),
        ("2.1", "Paredes de fachada — comprimento", "m", par("fachada"), "folha Paredes"),
        ("2.2", "Paredes de fachada — área bruta (altura de cada piso ; sem dedução de vãos)", "m²", par("fachada", True), "folha Paredes"),
        ("2.3", "Paredes interiores — comprimento", "m", par("interior"), "folha Paredes"),
        ("2.4", "Paredes interiores — área bruta (altura de cada piso ; sem dedução de portas)", "m²", par("interior", True), "folha Paredes"),
        ("3", "PORTAS E VÃOS", None, None, None),
        ("3.1", "Portas interiores", "un", portas, "folha Portas"),
        ("3.2", "Vãos exteriores nos alçados", "un", len(vaos), "folha Vãos — conferir no PDF"),
        ("3.3", "Vãos exteriores nos alçados — área", "m²", round(sum(d["L"] * d["H"] for d in vaos), 2), "folha Vãos"),
    ]
    for i, (a, d, u, q, o) in enumerate(linhas):
        _linha(mp, 5 + i, [a, d, u, q, o], {4: N2}, negrito=u is None)
    r = 6 + len(linhas)
    mp.cell(row=r, column=2, value="Ver a folha «Mapa» (completa, por capítulo e por piso, da fundação à cobertura).").font = BLD
    wb.save(caminho)
    return caminho
