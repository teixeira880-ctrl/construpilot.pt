"""Motor gros-œuvre PT: verificação encadeada com ajuste automático + caderno de planos cotados (caso real: sala de embarque em CLT/GL,
projeto canadiano transposto para Bragança — a viga de pavimento GL 175 × 532 não verifica com a sobrecarga C3 portuguesa)."""
import pytest

pytest.importorskip("reportlab")
pymupdf = pytest.importorskip("pymupdf")

from engines.calc_lots import gros_oeuvre, outils  # noqa: E402

XS = [4.8, 9.5, 14.2, 18.9]


def _topo_cob(y):
    return 105.687 + (y - 0.62) * (104.171 - 105.687) / (18.80 - 0.62)


def smithers():
    gx = [{"nome": n, "pos_m": p} for n, p in (("9", 0), ("10", 4.8), ("11", 9.5), ("12", 14.2), ("13", 18.9), ("14", 23.6), ("15", 31.135))]
    gy = [{"nome": n, "pos_m": p} for n, p in (("A", 0), ("B", 2.2), ("D", 10.48), ("F", 18.56), ("G", 19.08))]
    m = {"projeto": "Sala de embarque (estrutura Kerkhoff 16-107 transposta)", "local": "Aeródromo de Bragança", "grelhas_x": gx, "grelhas_y": gy,
         "solo_q_adm_kpa": 150, "cota_pavimento_m": 100.0,
         "niveis": [{"nome": "nível 1", "cota_m": 100.0}, {"nome": "topo das sapatas", "cota_m": 97.77}, {"nome": "laje da caixa de ar", "cota_m": 98.3}],
         "sapatas": [], "sapatas_continuas": [], "muros": [], "pilares": [], "vigas": [], "lajes": []}
    per = [[0, 0], [31.135, 0], [31.135, 19.08], [0, 19.08], [0, 0]]
    m["sapatas_continuas"].append({"ref": "SF1", "pontos": per, "b_m": 0.6, "h_m": 0.25, "cota_topo_m": 97.77, "g_kn_m": 18, "q_kn_m": 6})
    m["muros"].append({"pontos": per, "espessura_m": 0.2, "cota_base_m": 97.77, "cota_topo_m": 99.6})
    for x in XS:
        for ya, yb in ((0.1, 4.14), (8.54, 12.42), (16.82, 18.98)):
            m["sapatas_continuas"].append({"ref": "SF3", "pontos": [[x, ya], [x, yb]], "b_m": 0.75, "h_m": 0.25, "cota_topo_m": 97.77, "g_kn_m": 40, "q_kn_m": 50})
        for y, ref, b, h in ((2.2, "PF4", 1.2, 0.3), (10.48, "PF2", 1.5, 0.45), (18.56, "PF4", 1.2, 0.3)):
            m["sapatas"].append({"ref": ref, "x_m": x, "y_m": y, "b_m": b, "l_m": b, "h_m": h, "cota_topo_m": 97.77})
            m["pilares"].append({"ref": "P", "x_m": x, "y_m": y, "b_m": 0.311, "h_m": 0.405, "material": "GL24h", "cota_base_m": 98.45,
                                 "cota_topo_m": round(_topo_cob(y) - 0.648, 3), "g_kn": 115 if ref == "PF2" else 70, "q_kn": 150 if ref == "PF2" else 60,
                                 "pedestal_m": 0.4, "cota_pedestal_base_m": 97.77})
        for ya, yb in ((3.74, 8.94), (12.02, 17.22)):
            m["vigas"].append({"ref": "VP", "piso": "pavimento", "x0_m": x, "y0_m": ya, "x1_m": x, "y1_m": yb, "b_m": 0.175, "h_m": 0.532, "material": "GL24h",
                               "g_kn_m": 9.0, "q_kn_m": 23.75, "cota_topo_ini_m": 99.576})
        m["vigas"].append({"ref": "VC", "piso": "cobertura", "x0_m": x, "y0_m": 0.62, "x1_m": x, "y1_m": 18.8, "b_m": 0.311, "h_m": 0.648, "material": "GL24h",
                           "vao_calculo_m": 8.28, "g_kn_m": 8.3, "q_kn_m": 3.4, "psi2": 0.0, "cota_topo_ini_m": 105.687, "cota_topo_fim_m": 104.171})
    m["lajes"] += [{"ref": "LT", "piso": "fundacao", "tipo": "laje_terrea", "x0_m": 0.1, "y0_m": 0.1, "x1_m": 23.5, "y1_m": 18.98, "espessura_m": 0.075, "cota_topo_m": 98.3},
                   {"ref": "L350", "piso": "pavimento", "tipo": "laje_ba", "x0_m": 23.7, "y0_m": 0.1, "x1_m": 31.035, "y1_m": 12.65, "espessura_m": 0.35,
                    "cota_topo_m": 99.95, "q_kn_m2": 5.0, "g2_kn_m2": 1.6},
                   {"ref": "PAV", "piso": "pavimento", "tipo": "vigas_i", "x0_m": 0.1, "y0_m": 0.1, "x1_m": 23.5, "y1_m": 18.98, "espessura_m": 0.424,
                    "cota_topo_m": 100.0, "espacamento_m": 0.4, "direcao_vao": "x", "descricao": "vigas I 355 // 0,40 + contraplacado + betonilha"},
                   {"ref": "CLT", "piso": "cobertura", "tipo": "clt", "x0_m": 0.0, "y0_m": -0.9, "x1_m": 23.6, "y1_m": 19.93, "espessura_m": 0.139,
                    "cota_topo_ini_m": _topo_cob(-0.9) + 0.139, "cota_topo_fim_m": _topo_cob(19.93) + 0.139, "pendente_dir": "y", "isolamento_m": 0.17,
                    "direcao_vao": "x", "descricao": "CLT 139 E + PIR 160 + TPO"}]
    return m


def test_ajusta_viga_de_pavimento_e_desenha_secao_adotada():
    m = smithers()
    r = gros_oeuvre.calcular(m)
    ver = r["verificacao"]
    vp = [e for e in ver["elementos"] if e["ref"] == "VP"]
    assert vp and all(e["original"] and "175 × 532" in e["original"] for e in vp)       # original não verificava
    assert all(e["ok"] for e in vp)                                                        # secção adotada verifica
    assert any(a.startswith("Viga VP") for a in ver["ajustes"])
    vc = [e for e in ver["elementos"] if e["ref"] == "VC"]
    assert vc and all(e["ok"] and e["original"] is None for e in vc)                      # viga de cobertura conforme sem ajuste
    assert ver["conforme"]
    assert m["vigas"][0]["h_m"] == 0.532                                                   # entrada do chamador intacta
    adot = next(v for v in r["modelo"]["vigas"] if v["ref"] == "VP")
    assert adot["h_m"] > 0.532


def test_planos_cotados_e_escala():
    r = gros_oeuvre.calcular(smithers())
    assert r["escala"] == 50
    d = pymupdf.open(stream=r["planos_pdf"], filetype="pdf")
    assert len(d) == 5                                                                     # fundações, pavimento, cobertura, cortes, quadros
    t0 = d[0].get_text()
    for cota in ("4800", "4700", "7535", "31135", "19080", "PF2", "SF3"):
        assert cota in t0, cota
    assert "Ø" in t0                                                                       # quadro de armaduras
    t3 = d[3].get_text()
    assert "+100,000" in t3 and "+97,770" in t3 and "CORTE" in t3
    assert "GO-05" in d[4].get_text()


def test_ajusta_sapata_subdimensionada():
    m = smithers()
    m["sapatas"][1]["b_m"] = m["sapatas"][1]["l_m"] = 0.9                               # PF2 demasiado pequena para 265 kN
    ver = gros_oeuvre.calcular(m)["verificacao"]
    assert any(a.startswith("Sapata PF2") for a in ver["ajustes"])


def test_ferramenta_assistente():
    names = {t["name"] for t in outils.CALC_TOOLS}
    assert "calcul_gros_oeuvre" in names and "calcul_gros_oeuvre" in outils.PROGRESS_LABELS and "calcul_gros_oeuvre" in outils.PROTOCOL_PT
    out = outils.run("calcul_gros_oeuvre", {"modelo_json": __import__("json").dumps(smithers())})
    assert out["pdf"][:4] == b"%PDF" and out["png"][:4] == b"\x89PNG"
    assert "VP" in out["resume"] and "ajust" in out["resume"].lower()
    assert pymupdf.open(stream=out["pdf"], filetype="pdf").page_count >= 6


def test_sem_grelhas_erro_claro():
    with pytest.raises(ValueError):
        gros_oeuvre.calcular({"sapatas": []})


def test_ajusta_painel_clt_subdimensionado():
    m = smithers()
    m["lajes"] = [{"ref": "C1", "piso": "cobertura", "tipo": "clt", "x0_m": 0, "y0_m": 0, "x1_m": 5, "y1_m": 5, "espessura_m": 0.14,
                   "camadas_mm": [28] * 5, "vao_m": 5.0, "g2_kn_m2": 2.5, "q_kn_m2": 1.55, "psi2": 0.0, "produto": "rezult_clt",
                   "descricao": "Rezult CLT 140-5s"}]
    r = gros_oeuvre.calcular(m)
    aj = [a for a in r["verificacao"]["ajustes"] if a.startswith("Painel CLT C1")]
    assert aj and "CLT 140" in aj[0]
    lj = r["modelo"]["lajes"][0]
    assert sum(lj["camadas_mm"]) > 140 and "140" not in lj["descricao"]
    assert all(e["ok"] for e in r["verificacao"]["elementos"] if e["tipo"] == "painel CLT")
